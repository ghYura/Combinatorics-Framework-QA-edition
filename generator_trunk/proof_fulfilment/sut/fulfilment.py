#!/usr/bin/env python3
"""
fulfilment - a deterministic simulation of a multi-service order pipeline.

Five services exchange messages over a bus. Nothing is real: no sockets, no
threads, no clock. The TEST decides which in-flight message is delivered next,
which is duplicated, which is lost, and when a service restarts. That makes the
delivery schedule an ordinary data structure a test can enumerate, which is how
serious distributed-systems testing is done (deterministic simulation) and the
only way results are reproducible.

    gateway   - owns the order saga: reserve -> authorize -> capture -> ship,
                with compensation on any failure
    inventory - stock reservation and release
    payment   - authorize / capture / void, with idempotency keys
    shipping  - creates shipments
    ledger    - the money record

Every service is written the way these are usually written: it keeps an
in-memory set of processed message ids for idempotency, persists its business
rows, and retries on timeout.

Public API (what a test drives):
    submit(oid, sku, qty, amount)   enqueue a new order
    deliver(k)                      deliver the k-th in-flight message (clamped)
    duplicate(k)                    deliver it AGAIN without removing it
    drop(k)                         lose it
    restart(service)                the process comes back with persisted rows only
    tick(n)                         advance time; timeouts fire retries
    drain(limit)                    deliver until quiescent
    audit()                         the ids of violated invariants (external checker)

Invariants (checked by audit(), never consulted by the code):
    J1  ledger balance == captures - refunds
    J2  no stock stays reserved for an order that reached a terminal state
    J3  nothing ships without a captured payment
    J4  an order ships at most once
    J5  an authorization is captured at most once
    J6  a failed order ends with zero net money movement
    J7  reserved stock is never negative, and on_hand + reserved is conserved
    J8  a terminal order never moves again
"""

# --------------------------------------------------------------------------
# catalogue / configuration defaults
# --------------------------------------------------------------------------

SKUS = {"widget": 50, "gadget": 8, "doohickey": 1}

TERMINAL = ("SHIPPED", "FAILED", "CANCELLED")


class Msg(object):
    __slots__ = ("id", "to", "kind", "body", "sent_at")

    def __init__(self, mid, to, kind, body, sent_at):
        self.id = mid
        self.to = to
        self.kind = kind
        self.body = body
        self.sent_at = sent_at

    def __repr__(self):
        return "%s->%s:%s" % (self.id, self.to, self.kind)


# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------

class Inventory(object):
    """Stock reservation. `on_hand` is what is physically present; `reserved`
    is what is spoken for. Their sum must be conserved by every operation."""

    def __init__(self):
        self.on_hand = dict(SKUS)
        self.reserved = dict((k, 0) for k in SKUS)
        self.by_order = {}          # oid -> (sku, qty)   persisted
        self.seen = set()           # processed message ids -- IN MEMORY ONLY

    def reserve(self, oid, sku, qty):
        if oid in self.by_order:
            return True             # already reserved for this order
        if self.on_hand.get(sku, 0) < qty:
            return False
        self.on_hand[sku] -= qty
        self.reserved[sku] += qty
        self.by_order[oid] = (sku, qty)
        return True

    def release(self, oid):
        rec = self.by_order.pop(oid, None)
        if rec is None:
            return False
        sku, qty = rec
        self.reserved[sku] -= qty
        self.on_hand[sku] += qty
        return True

    def consume(self, oid):
        rec = self.by_order.pop(oid, None)
        if rec is None:
            return False
        sku, qty = rec
        self.reserved[sku] -= qty
        return True

    def restart(self):
        self.seen = set()           # the idempotency set does not survive


class Payment(object):
    def __init__(self):
        self.auths = {}             # auth_id -> {oid, amount, state}
        self.captured = []          # list of amounts
        self.voided = []
        self.by_key = {}            # idempotency key -> auth_id  (persisted)
        self.seen = set()           # IN MEMORY ONLY
        self._next = 1

    def authorize(self, oid, amount, key):
        if key in self.by_key:
            return self.by_key[key]
        aid = "auth-%d" % self._next
        self._next += 1
        self.auths[aid] = {"oid": oid, "amount": amount, "state": "AUTHORIZED"}
        self.by_key[key] = aid
        return aid

    def capture(self, aid):
        a = self.auths.get(aid)
        if a is None:
            return None
        a["state"] = "CAPTURED"
        self.captured.append(a["amount"])
        return a["amount"]

    def void(self, aid):
        a = self.auths.get(aid)
        if a is None:
            return None
        if a["state"] == "CAPTURED":
            self.voided.append(a["amount"])
            a["state"] = "REFUNDED"
            return a["amount"]
        a["state"] = "VOIDED"
        return 0

    def restart(self):
        self.seen = set()


class Shipping(object):
    def __init__(self):
        self.shipments = {}         # oid -> shipment id
        self.log = []               # every ship call, even repeats
        self.seen = set()
        self._next = 1

    def ship(self, oid):
        sid = "shp-%d" % self._next
        self._next += 1
        self.shipments[oid] = sid
        self.log.append(oid)
        return sid

    def restart(self):
        self.seen = set()


class Ledger(object):
    def __init__(self):
        self.entries = []

    def record(self, kind, oid, amount):
        self.entries.append({"kind": kind, "oid": oid, "amount": amount})

    def balance(self):
        b = 0
        for e in self.entries:
            b += e["amount"] if e["kind"] == "capture" else -e["amount"]
        return b


# --------------------------------------------------------------------------
# the system: bus + saga
# --------------------------------------------------------------------------

class System(object):

    def __init__(self, timeout=3, compensate_order="release_first", retry=True):
        self.timeout = timeout
        self.compensate_order = compensate_order   # release_first | void_first
        self.retry = retry

        self.now = 0
        self.inv = Inventory()
        self.pay = Payment()
        self.shp = Shipping()
        self.led = Ledger()

        self.bus = []               # in-flight messages
        self.orders = {}            # oid -> saga state
        self.delivered = []         # trace
        self._mid = 1

    # ---------------------------------------------------------------- bus

    def _send(self, to, kind, body):
        m = Msg("m%d" % self._mid, to, kind, body, self.now)
        self._mid += 1
        self.bus.append(m)
        return m

    def _pick(self, k):
        if not self.bus:
            return None
        if k < 0:
            k = len(self.bus) + k
        k = max(0, min(k, len(self.bus) - 1))
        return k

    def deliver(self, k=0):
        i = self._pick(k)
        if i is None:
            return None
        m = self.bus.pop(i)
        self._handle(m)
        return m

    def duplicate(self, k=0):
        """At-least-once delivery: hand the message over without consuming it."""
        i = self._pick(k)
        if i is None:
            return None
        m = self.bus[i]
        self._handle(m)
        return m

    def drop(self, k=0):
        i = self._pick(k)
        if i is None:
            return None
        return self.bus.pop(i)

    def drain(self, limit=200):
        n = 0
        while self.bus and n < limit:
            self.deliver(0)
            n += 1
        return n

    def restart(self, service):
        getattr(self, {"inventory": "inv", "payment": "pay",
                       "shipping": "shp"}[service]).restart()

    def tick(self, n=1):
        for _ in range(n):
            self.now += 1
            if not self.retry:
                continue
            for oid, o in list(self.orders.items()):
                if o["state"] in TERMINAL or o["awaiting"] is None:
                    continue
                if self.now - o["sent_at"] >= self.timeout:
                    o["attempt"] += 1
                    self._resend(oid)

    # -------------------------------------------------------------- saga

    def submit(self, oid, sku="widget", qty=1, amount=100):
        self.orders[oid] = {
            "id": oid, "sku": sku, "qty": qty, "amount": amount,
            "state": "NEW", "auth": None, "attempt": 0,
            "awaiting": None, "sent_at": self.now, "moves": 0,
        }
        self._goto(oid, "RESERVING")

    def _goto(self, oid, state):
        o = self.orders[oid]
        o["state"] = state
        o["moves"] += 1
        o["sent_at"] = self.now
        if state == "RESERVING":
            o["awaiting"] = "reserved"
            self._send("inventory", "reserve",
                       {"oid": oid, "sku": o["sku"], "qty": o["qty"]})
        elif state == "AUTHORIZING":
            o["awaiting"] = "authorized"
            self._send("payment", "authorize",
                       {"oid": oid, "amount": o["amount"], "key": self._key(oid)})
        elif state == "CAPTURING":
            o["awaiting"] = "captured"
            self._send("payment", "capture", {"oid": oid, "auth": o["auth"]})
        elif state == "SHIPPING":
            o["awaiting"] = "shipped"
            self._send("shipping", "ship", {"oid": oid})
        elif state == "COMPENSATING":
            o["awaiting"] = "compensated"
            self._compensate(oid)
        else:
            o["awaiting"] = None

    def _key(self, oid):
        """Idempotency key for the payment authorization."""
        o = self.orders[oid]
        return "%s:%d" % (oid, o["attempt"])

    def _resend(self, oid):
        o = self.orders[oid]
        self._goto(oid, o["state"])

    def _compensate(self, oid):
        o = self.orders[oid]
        if self.compensate_order == "release_first":
            self._send("inventory", "release", {"oid": oid})
            if o["auth"]:
                self._send("payment", "void", {"oid": oid, "auth": o["auth"]})
        else:
            if o["auth"]:
                self._send("payment", "void", {"oid": oid, "auth": o["auth"]})
            self._send("inventory", "release", {"oid": oid})

    # ----------------------------------------------------------- handlers

    def _handle(self, m):
        self.delivered.append(m.kind)
        if m.to == "inventory":
            self._inventory(m)
        elif m.to == "payment":
            self._payment(m)
        elif m.to == "shipping":
            self._shipping(m)
        elif m.to == "gateway":
            self._gateway(m)

    def _inventory(self, m):
        if m.id in self.inv.seen:
            return
        self.inv.seen.add(m.id)
        b = m.body
        if m.kind == "reserve":
            ok = self.inv.reserve(b["oid"], b["sku"], b["qty"])
            self._send("gateway", "reserved", {"oid": b["oid"], "ok": ok})
        elif m.kind == "release":
            self.inv.release(b["oid"])
        elif m.kind == "consume":
            self.inv.consume(b["oid"])

    def _payment(self, m):
        if m.id in self.pay.seen:
            return
        self.pay.seen.add(m.id)
        b = m.body
        if m.kind == "authorize":
            aid = self.pay.authorize(b["oid"], b["amount"], b["key"])
            self._send("gateway", "authorized", {"oid": b["oid"], "auth": aid})
        elif m.kind == "capture":
            amt = self.pay.capture(b["auth"])
            if amt is not None:
                self.led.record("capture", b["oid"], amt)
            self._send("gateway", "captured", {"oid": b["oid"], "ok": amt is not None})
        elif m.kind == "void":
            amt = self.pay.void(b["auth"])
            if amt:
                self.led.record("refund", b["oid"], amt)

    def _shipping(self, m):
        if m.id in self.shp.seen:
            return
        self.shp.seen.add(m.id)
        b = m.body
        if m.kind == "ship":
            sid = self.shp.ship(b["oid"])
            self._send("gateway", "shipped", {"oid": b["oid"], "shipment": sid})

    def _gateway(self, m):
        b = m.body
        o = self.orders.get(b["oid"])
        if o is None:
            return
        if m.kind == "reserved":
            if b["ok"]:
                self._goto(o["id"], "AUTHORIZING")
            else:
                o["state"] = "FAILED"
                o["awaiting"] = None
        elif m.kind == "authorized":
            o["auth"] = b["auth"]
            self._goto(o["id"], "CAPTURING")
        elif m.kind == "captured":
            if b["ok"]:
                self._goto(o["id"], "SHIPPING")
            else:
                self._goto(o["id"], "COMPENSATING")
        elif m.kind == "shipped":
            self._send("inventory", "consume", {"oid": o["id"]})
            o["state"] = "SHIPPED"
            o["awaiting"] = None

    # ---------------------------------------------------------------- audit

    def audit(self):
        bad = []

        captures = sum(e["amount"] for e in self.led.entries if e["kind"] == "capture")
        refunds = sum(e["amount"] for e in self.led.entries if e["kind"] == "refund")
        if self.led.balance() != captures - refunds:
            bad.append("J1")

        # J2 no stock still reserved for a terminated order
        for oid, o in self.orders.items():
            if o["state"] in TERMINAL and oid in self.inv.by_order:
                if o["state"] != "SHIPPED":
                    bad.append("J2")
                    break

        # J3 nothing ships without a capture
        for oid in self.shp.shipments:
            o = self.orders.get(oid)
            aid = o and o["auth"]
            a = self.pay.auths.get(aid) if aid else None
            if a is None or a["state"] not in ("CAPTURED", "REFUNDED"):
                bad.append("J3")
                break

        # J4 an order ships at most once
        if len(self.shp.log) != len(set(self.shp.log)):
            bad.append("J4")

        # J5 an authorization is captured at most once
        counts = {}
        for e in self.led.entries:
            if e["kind"] == "capture":
                counts[e["oid"]] = counts.get(e["oid"], 0) + 1
        if any(v > 1 for v in counts.values()):
            bad.append("J5")

        # J6 a failed order has no net money movement
        for oid, o in self.orders.items():
            if o["state"] == "FAILED":
                net = sum(e["amount"] if e["kind"] == "capture" else -e["amount"]
                          for e in self.led.entries if e["oid"] == oid)
                if net != 0:
                    bad.append("J6")
                    break

        # J7 reserved never negative; on_hand + reserved conserved per sku
        for sku, base in SKUS.items():
            if self.inv.reserved[sku] < 0 or self.inv.on_hand[sku] < 0:
                bad.append("J7")
                break
            shipped_qty = sum(o["qty"] for o in self.orders.values()
                              if o["state"] == "SHIPPED" and o["sku"] == sku)
            if self.inv.on_hand[sku] + self.inv.reserved[sku] + shipped_qty != base:
                bad.append("J7")
                break

        # J8 a terminal order never moved again
        for oid, o in self.orders.items():
            if o["state"] in TERMINAL and o.get("moved_after_terminal"):
                bad.append("J8")
                break

        return sorted(set(bad))

    def summary(self):
        return {
            "orders": dict((o["id"], o["state"]) for o in self.orders.values()),
            "inflight": len(self.bus),
            "balance": self.led.balance(),
            "shipped": len(self.shp.log),
            "reserved": dict(self.inv.reserved),
            "on_hand": dict(self.inv.on_hand),
        }
