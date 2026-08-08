#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

r"""fintech_oot — combinatorial test design for the CURRENT finance_stack simulator
(the refactored multi-bank ecosystem: clients, accounts, cards, two-party transfers,
risk, sanctions, interbank ON_HOLD/recover, time-config).

Strategy (per the user's guidance):
  * MANY SMALL BATCHES, each a focused dispersed spec → its own Bundle run, so no
    single batch explodes while collectively covering a large interaction surface.
  * Each candidate exercises the LIVE 2-connected-instance cluster over signed HTTP
    (HMAC enforcement + cross-node connectivity) AND runs the deep parameter/factor
    combinatorics IN-PROCESS (isolated per candidate, so candidates never interfere).
  * EXTERNAL FACTORS are modeled as FW_Optional "sudden actions" fired at DIFFERENT
    positions of the flow (after_register / after_initiate / after_confirm) and in
    different subsets — peer hold/down/recover, freeze, sanction, ttl-shrink,
    force-expire, velocity burst.
  * RULE VARIETY: FW_Combi(1) (params), FW_Combi(2) (compound faults), FW_Permut
    (confirm order), FW_Subsets (optional ops), FW_Optional (external factors).

Emits one dispersed .toml per batch under  batches/<batch>/<batch>.toml
Run a batch through the Bundle:  python3 ../bundle_run.py batches/<batch>
"""
from __future__ import annotations

import itertools
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCHES = HERE / "batches"

# ---------------------------------------------------------------------------
# Shared HEAD — constant frame. Pre-declares EVERY working name with a safe
# default so ANY combination (any batch, optional present/absent) is runnable.
# ---------------------------------------------------------------------------
HEAD = r'''import sys, os, time, uuid, json
from pathlib import Path
_SOURCE_PATH = Path(globals().get("__file__", Path.cwd())).resolve()
_GENERATOR_ROOT = next((
    parent for parent in (_SOURCE_PATH, *_SOURCE_PATH.parents)
    if (parent / "sut_paths.py").is_file()
), None)
if _GENERATOR_ROOT is not None:
    sys.path.insert(0, str(_GENERATOR_ROOT))
    from sut_paths import project_path
    FINTECH_SRC = str(project_path("fintech"))
else:
    _sut_root = os.environ.get("BUNDLE_SUT_ROOT")
    if not _sut_root:
        raise RuntimeError(
            "candidate is outside the Bundle checkout; set BUNDLE_SUT_ROOT "
            "to the directory containing fin_tech_to_test"
        )
    FINTECH_SRC = str(
        Path(_sut_root).expanduser().resolve() / "fin_tech_to_test")
if FINTECH_SRC not in sys.path:
    sys.path.insert(0, FINTECH_SRC)
from decimal import Decimal
from finance_stack.ecosystem import Ecosystem
from finance_stack.identity import KycStatus
from finance_stack.ledger import AccountStatus, CardBrand, CardStatus
from finance_stack.clearing import Party, TransferStatus
from finance_stack.kernel import (Money, ServiceError, ValidationError, NotFoundError,
    InsufficientFundsError, PolicyError, StateError, AuthError, PeerUnavailableError,
    sign_request, verify_request)
try:
    import httpx as _httpx
except Exception:
    _httpx = None

# ---- live 2-instance cluster (toBank1/AURUM <-> toBank2/NORD) ----
TARGET1 = os.environ.get("OOT_TARGET1", "http://127.0.0.1:8121")
TARGET2 = os.environ.get("OOT_TARGET2", "http://127.0.0.1:8122")
HTTP_SECRET = os.environ.get("OOT_SECRET", "oot-secret")
REPLAY_WINDOW = 300

# ---- parameters (reassigned by FW_Combi(1) slots) ----
CURRENCY = "USD"
AMOUNT   = "100.00"
AUTH     = "valid_hmac"
TOPOLOGY = "intra"
KYC      = "VERIFIED"
BRAND    = "VISA"
LIMIT    = "500.00"
EXPIRY   = "2030-12"
CONFIRM_DECISION = "both"     # both | reject_sender | reject_receiver
REVIEW           = "none"     # none | approve | deny  (review-tier amounts)
TGT_CURRENCY     = ""         # "" = same as CURRENCY; else dst opened with this (mismatch)
TIME_SYNC        = "none"     # none | confirmation_ttl_seconds | risk_window_seconds | replay_window_seconds
TIME_VALUE       = "60"
PROPAGATE        = "self"     # self | connected
ACCEPT_SYNC      = "true"     # node2's accept_time_sync flag before propagation
LIVE_XFER        = "off"      # on | off  (real cross-bank settle over HTTP via the 2 instances)

# ---- accumulators (appended by Permut / Subsets / Combi(2) / Optional slots) ----
OPSEQ   = ["SENDER", "RECEIVER"]   # confirm order (FW_Permut may reorder)
OPT     = []                       # optional ops present (FW_Subsets)
FAULTS  = []                       # compound preconditions (FW_Combi(2))
FACTORS = []                       # external sudden-actions (FW_Optional): "<position>:<name>"

def _ik(tag="t"):
    return tag + "-" + uuid.uuid4().hex

EVENTS = []
def _note(step, outcome):
    EVENTS.append(step + "=" + str(outcome))

class _Peer:
    mode = "ok"
    def post_inbound(self, account_id, money, reference):
        if self.mode == "ok":
            return
        if self.mode == "hold":
            raise PeerUnavailableError("peer hold", retryable=True, bank="NORD")
        if self.mode == "down":
            raise PeerUnavailableError("peer down", retryable=False, bank="NORD")
    def place_hold(self, *a): pass
    def release_hold(self, *a): pass
    def post_outbound(self, *a): pass
PEER = _Peer()

# In stress mode the heavy in-process world is not built — a candidate only
# needs to expose its signed "shot" (fw_fire) for the combinatorial storm.
if os.environ.get("OOT_MODE") != "stress":
    eco = Ecosystem()
    eco.add_bank("AURUM", "Aurum Bank")
    eco.add_remote_bank("NORD", "Nord (peer)", PEER)
else:
    eco = None

sender = receiver = None
src_acc = dst_acc = None
card = None
transfer = None
ref = None
tokens = {}
crash_msg = None
auth_enforced = 1
connected = 1
officer = None
_requires_review = False
time_sync_ok = 1
live_xfer_ok = 1
http_settled = 0

METRICS = {"app": "fintech_oot", "currency": "USD", "amount": "100.00", "auth": "valid_hmac",
           "topology": "intra", "kyc": "VERIFIED", "brand": "VISA", "limit": "500.00",
           "expiry": "2030-12", "factors": "none", "transfer_status": "NONE",
           "settled": 0, "blocked": 0, "on_hold": 0, "rejected": 0, "expired": 0,
           "auth_enforced": 1, "connected": 1, "balanced": 1, "crash": 0,
           "confirm_decision": "both", "review": "none", "time_sync": "none",
           "live_xfer": "off", "http_settled": 0, "http_final": "NONE",
           "violations": 0, "score": 100, "FW_VAR": 0}
FW_VAR = 0
FW_CUSTOM_VAR = 0

def _http(base, path, method="POST", payload=None, secret=None):
    if _httpx is None:
        return None, None
    secret = secret or HTTP_SECRET
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    ts = str(int(time.time())); nn = uuid.uuid4().hex
    headers = {"x-timestamp": ts, "x-nonce": nn,
               "x-signature": sign_request(secret, method, path, body, ts, nn),
               "content-type": "application/json"}
    try:
        r = _httpx.request(method, base + path, content=body, headers=headers, timeout=6.0)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except Exception:
        return None, None

def fw_fire(_client):
    """One signed 'shot' for the combinatorial storm — its shape varies by this
    candidate's slots (AUTH → valid/bad/missing/expired signature; TOPOLOGY →
    direct node1 vs node1->node2 proxy). Returns the HTTP status (or raises on a
    transport error). 401s from bad auth are CORRECT behavior, not server errors.
    """
    _body = json.dumps({"display_name": "S" + uuid.uuid4().hex[:6],
                        "email": uuid.uuid4().hex[:8] + "@oot.test", "kyc_status": "VERIFIED"}).encode("utf-8")
    if TOPOLOGY == "cross":
        _base, _path = TARGET1, "/toBank2/v1/clients"     # via node1's proxy to node2
    else:
        _base, _path = TARGET1, "/toBank1/v1/clients"
    _ts = str(int(time.time())); _nn = uuid.uuid4().hex
    if AUTH == "valid_hmac":
        _h = {"x-timestamp": _ts, "x-nonce": _nn, "content-type": "application/json",
              "x-signature": sign_request(HTTP_SECRET, "POST", _path, _body, _ts, _nn)}
    elif AUTH == "bad_signature":
        _h = {"x-timestamp": _ts, "x-nonce": _nn, "x-signature": "00" * 32, "content-type": "application/json"}
    elif AUTH == "expired_timestamp":
        _old = str(int(time.time()) - REPLAY_WINDOW - 60)
        _h = {"x-timestamp": _old, "x-nonce": _nn, "content-type": "application/json",
              "x-signature": sign_request(HTTP_SECRET, "POST", _path, _body, _old, _nn)}
    else:  # missing_headers
        _h = {"content-type": "application/json"}
    return _client.request("POST", _base + _path, content=_body, headers=_h).status_code

def _apply(position):
    """Fire external 'sudden action' factors registered for this flow position."""
    global ref
    for f in list(FACTORS):
        if not f.startswith(position + ":"):
            continue
        name = f.split(":", 1)[1]
        try:
            if name == "freeze" and src_acc is not None:
                eco.bank("AURUM").ledger.set_status(src_acc.account_id, AccountStatus.FROZEN)
            elif name == "sanction_sender" and sender is not None:
                eco.network.sanctions.add_client(sender.client_id)
            elif name == "sanction_receiver" and receiver is not None:
                eco.network.sanctions.add_client(receiver.client_id)
            elif name == "sanction_bank":
                eco.network.set_bank_sanctioned("NORD", True)
            elif name == "peer_hold":
                PEER.mode = "hold"
            elif name == "peer_down":
                PEER.mode = "down"
            elif name == "peer_recover":
                PEER.mode = "ok"; eco.retry_on_hold()
            elif name == "ttl_shrink":
                eco.update_time_config({"confirmation_ttl_seconds": 1})
            elif name == "force_expire" and ref is not None:
                eco.bank("AURUM").clearing.expire_due(now=time.time() + 100000)
            elif name == "velocity_burst" and src_acc is not None and dst_acc is not None:
                for _i in range(9):
                    try:
                        eco.initiate_transfer(src_acc.account_id, dst_acc.account_id, "1.00", _ik("burst"))
                    except Exception:
                        pass
            elif name == "flag_sender" and sender is not None:
                eco.identity.flag_client(sender.client_id, "manual_review")
            _note("factor_" + name, "fired")
        except Exception:
            pass  # external perturbations are best-effort
'''

# ---------------------------------------------------------------------------
# Shared TAIL — runs the flow (live + in-process) and the independent oracle.
# ---------------------------------------------------------------------------
TAIL = r'''# ============ LIVE phase: exercise the 2 connected instances over HMAC HTTP ===
_cli = {"display_name": "OOT " + _ik("u"), "email": _ik("e") + "@oot.test", "kyc_status": "VERIFIED"}
_path = "/toBank1/v1/clients"
if AUTH == "valid_hmac":
    _sc, _ = _http(TARGET1, _path, "POST", _cli)
    if _sc is None:
        connected = 0
    elif _sc == 401:
        auth_enforced = 0
elif AUTH == "bad_signature":
    _sc, _ = _http(TARGET1, _path, "POST", _cli, secret="wrong-secret")
    if _sc is not None and _sc != 401:
        auth_enforced = 0
elif AUTH == "missing_headers" and _httpx is not None:
    try:
        if _httpx.post(TARGET1 + _path, json=_cli, timeout=6.0).status_code != 401:
            auth_enforced = 0
    except Exception:
        connected = 0
elif AUTH == "expired_timestamp" and _httpx is not None:
    _b = json.dumps(_cli).encode(); _old = str(int(time.time()) - REPLAY_WINDOW - 60); _nn = uuid.uuid4().hex
    _sig = sign_request(HTTP_SECRET, "POST", _path, _b, _old, _nn)
    try:
        _r = _httpx.post(TARGET1 + _path, content=_b, headers={"x-timestamp": _old, "x-nonce": _nn,
                         "x-signature": _sig, "content-type": "application/json"}, timeout=6.0)
        if _r.status_code != 401:
            auth_enforced = 0
    except Exception:
        connected = 0
if _httpx is not None:
    try:
        if _httpx.get(TARGET1 + "/toBank2/health", timeout=6.0).status_code != 200:
            connected = 0
    except Exception:
        connected = 0

# ---- LIVE time-unit sync between the two banks (cross-instance) ----
if _httpx is not None and TIME_SYNC != "none":
    _base = 4321
    _http(TARGET2, "/toBank2/v1/time-config", "PUT", {"values": {TIME_SYNC: _base}, "accept_sync": (ACCEPT_SYNC == "true")})
    _http(TARGET1, "/toBank1/v1/time-config", "PUT", {"values": {TIME_SYNC: int(TIME_VALUE)}, "propagate": PROPAGATE})
    _sc, _r2 = _http(TARGET2, "/toBank2/v1/time-config", "GET")
    if isinstance(_r2, dict) and TIME_SYNC in _r2:
        _should = (PROPAGATE == "connected" and ACCEPT_SYNC == "true")
        if _r2.get(TIME_SYNC) != (int(TIME_VALUE) if _should else _base):
            time_sync_ok = 0

# ---- LIVE cross-bank settlement: real money movement across the 2 instances ----
if _httpx is not None and LIVE_XFER == "on" and AUTH == "valid_hmac":
    _, _la = _http(TARGET1, "/toBank1/v1/clients", "POST", {"display_name": "LX " + _ik("u"), "email": _ik("e") + "@oot.test", "kyc_status": "VERIFIED"})
    _, _lb = _http(TARGET2, "/toBank2/v1/clients", "POST", {"display_name": "LY " + _ik("u"), "email": _ik("e") + "@oot.test", "kyc_status": "VERIFIED"})
    if isinstance(_la, dict) and isinstance(_lb, dict):
        _, _laa = _http(TARGET1, "/toBank1/v1/banks/AURUM/accounts", "POST", {"client_id": _la["client_id"], "currency": "USD", "initial_deposit": "500.00"})
        _, _lbb = _http(TARGET2, "/toBank2/v1/banks/NORD/accounts", "POST", {"client_id": _lb["client_id"], "currency": "USD"})
        if isinstance(_laa, dict) and isinstance(_lbb, dict):
            _, _lc = _http(TARGET1, "/toBank1/v1/transfers", "POST", {"source_account_id": _laa["account_id"], "target_bank": "NORD", "target_account_id": _lbb["account_id"], "amount": AMOUNT, "idempotency_key": _ik("lx")})
            if isinstance(_lc, dict) and isinstance(_lc.get("transfer"), dict) and _lc["transfer"].get("status") == "AWAITING_CONFIRMATION":
                _lref = _lc["transfer"]["reference"]; _ltok = _lc["confirmation_tokens"]
                for _lp in OPSEQ:
                    _http(TARGET1, "/toBank1/v1/transfers/" + _lref + "/confirm", "POST", {"party": _lp, "token": _ltok[_lp]})
                _, _lfin = _http(TARGET1, "/toBank1/v1/transfers/" + _lref, "GET")
                if isinstance(_lfin, dict):
                    METRICS["http_final"] = _lfin.get("status") or "NONE"
                    if _lfin.get("status") == "SETTLED":
                        http_settled = 1
                    elif AMOUNT == "100.00":
                        live_xfer_ok = 0

# ============ IN-PROCESS combinatorial flow (isolated per candidate) ==========
_kyc = {"VERIFIED": KycStatus.VERIFIED, "PENDING": KycStatus.PENDING,
        "REJECTED": KycStatus.REJECTED}.get(KYC, KycStatus.VERIFIED)
try:
    sender = eco.register_client("Alice " + _ik("s"), _ik("a") + "@oot.test", kyc_status=_kyc)
    receiver = eco.register_client("Bob " + _ik("r"), _ik("b") + "@oot.test", kyc_status=KycStatus.VERIFIED)
    _note("register", "ok")
except Exception as _e:
    crash_msg = "register:" + type(_e).__name__
try:
    from finance_stack.identity import ROLE_CUSTOMER as _RC, ROLE_COMPLIANCE as _RK
    officer = eco.register_client("Officer " + _ik("o"), _ik("o") + "@oot.test",
                                  kyc_status=KycStatus.VERIFIED, roles={_RC, _RK})
except Exception:
    officer = None
_apply("after_register")

try:
    src_acc = eco.open_account("AURUM", sender.client_id, CURRENCY, "1000.00")
    _note("open_src", "ok")
except ValidationError:
    _note("open_src", "ValidationError")
except Exception as _e:
    crash_msg = crash_msg or ("open_src:" + type(_e).__name__)
if TOPOLOGY == "intra" and src_acc is not None and receiver is not None:
    try:
        dst_acc = eco.open_account("AURUM", receiver.client_id, (TGT_CURRENCY or CURRENCY), "0.00")
    except Exception:
        pass

# card CRUD (brand/limit/expiry boundary; optional block/delete ops)
if src_acc is not None:
    try:
        _brand = {"VISA": CardBrand.VISA, "MASTERCARD": CardBrand.MASTERCARD,
                  "AMEX": CardBrand.AMEX}.get(BRAND)
        if _brand is None:
            _note("card", "bad_brand")
        else:
            _lim = None if str(LIMIT) in ("none", "None", "") else LIMIT
            card = eco.bank("AURUM").ledger.issue_card(src_acc.account_id, _brand, spending_limit=_lim, expiry=EXPIRY)
            _note("card", "issued")
            if "block_card" in OPT:
                eco.bank("AURUM").ledger.update_card(card.card_id, status=CardStatus.BLOCKED)
            if "delete_card" in OPT:
                eco.bank("AURUM").ledger.delete_card(card.card_id)
    except (ValidationError, StateError) as _e:
        _note("card", type(_e).__name__)
    except Exception as _e:
        crash_msg = crash_msg or ("card:" + type(_e).__name__)
_apply("after_open")

# compound faults (FW_Combi(2)) applied before the transfer
for _f in FAULTS:
    try:
        if _f == "frozen" and src_acc is not None:
            eco.bank("AURUM").ledger.set_status(src_acc.account_id, AccountStatus.FROZEN)
        elif _f == "sanction_sender" and sender is not None:
            eco.network.sanctions.add_client(sender.client_id)
        elif _f == "sanction_receiver" and receiver is not None:
            eco.network.sanctions.add_client(receiver.client_id)
        elif _f == "kyc_pending" and sender is not None:
            eco.identity.set_kyc(sender.client_id, KycStatus.PENDING)
        elif _f == "flagged" and sender is not None:
            eco.identity.flag_client(sender.client_id, "compound")
        elif _f == "block_card" and card is not None:
            eco.bank("AURUM").ledger.update_card(card.card_id, status=CardStatus.BLOCKED)
    except Exception:
        pass

# capture the ACTUAL preconditions at initiate time (robust oracle, no name-guessing)
_pre_state = {
    "frozen": bool(src_acc is not None and src_acc.status is AccountStatus.FROZEN),
    "sanctioned_sender": bool(sender is not None and sender.client_id in eco.network.sanctions.client_ids),
    "sanctioned_receiver": bool(receiver is not None and receiver.client_id in eco.network.sanctions.client_ids),
    "unverified": bool(sender is not None and not sender.is_verified),
    "bank_sanctioned": bool(TOPOLOGY == "cross" and eco.network.try_bank("NORD") is not None and eco.network.try_bank("NORD").sanctioned),
}

# initiate transfer (amount boundary, topology)
if src_acc is not None:
    try:
        if TOPOLOGY == "cross":
            transfer = eco.initiate_remote_transfer(src_acc.account_id, "NORD", "acc_remote_oot", AMOUNT, _ik("x"))
        elif dst_acc is not None:
            transfer = eco.initiate_transfer(src_acc.account_id, dst_acc.account_id, AMOUNT, _ik("x"))
        if transfer is not None:
            ref = transfer.reference; tokens = dict(transfer.tokens); _note("initiate", transfer.status.value)
    except ValidationError:
        _note("initiate", "ValidationError")
    except (NotFoundError, StateError, InsufficientFundsError) as _e:
        _note("initiate", type(_e).__name__)
    except Exception as _e:
        crash_msg = crash_msg or ("initiate:" + type(_e).__name__)
_requires_review = bool(transfer is not None and getattr(transfer, "requires_review", False))
_apply("after_initiate")

# two-party confirmation (FW_Permut order) — honoring CONFIRM_DECISION
def _act(party_name, decision="CONFIRM"):
    global crash_msg
    if ref is None or not tokens:
        return
    try:
        _p = Party(party_name); _tok = tokens.get(_p)
        if _tok is None:
            return
        eco.confirm_transfer(ref, _p, _tok, decision)
        _note(("confirm_" if decision == "CONFIRM" else "reject_") + party_name, "ok")
    except (StateError, AuthError, ValidationError) as _e:
        _note("act_" + party_name, type(_e).__name__)
    except Exception as _e:
        crash_msg = crash_msg or ("confirm:" + type(_e).__name__)
for _party in OPSEQ:
    if CONFIRM_DECISION == "reject_sender" and _party == "SENDER":
        _act(_party, "REJECT")
    elif CONFIRM_DECISION == "reject_receiver" and _party == "RECEIVER":
        _act(_party, "REJECT")
    else:
        _act(_party, "CONFIRM")
# compliance review for review-tier transfers
if ref is not None and REVIEW != "none" and officer is not None:
    try:
        _t = eco.get_transfer(ref)
        if _t.status is TransferStatus.AWAITING_REVIEW:
            eco.review_transfer(ref, REVIEW == "approve", officer.client_id)
    except Exception:
        pass
_apply("after_confirm")

if ref is not None:
    try:
        transfer = eco.get_transfer(ref)
        METRICS["transfer_status"] = transfer.status.value
    except Exception:
        pass

# ============ ORACLE — invariants that must ALWAYS hold for a correct SUT =====
_status = METRICS["transfer_status"]
_settled = (_status == "SETTLED")
METRICS["settled"] = int(_settled)
METRICS["blocked"] = int(_status == "BLOCKED")
METRICS["on_hold"] = int(_status == "ON_HOLD")
METRICS["rejected"] = int(_status == "REJECTED")
METRICS["expired"] = int(_status == "EXPIRED")
_v = []
if crash_msg is not None:
    _v.append("crash")
try:
    eco.assert_all_balanced()
except Exception:
    _v.append("unbalanced"); METRICS["balanced"] = 0
try:
    for _b in eco.banks.values():
        for _a in _b.ledger.list_accounts():
            if _a.balance.amount < 0 or _a.available.amount < 0:
                _v.append("negative_balance")
                raise StopIteration
except StopIteration:
    pass
except Exception:
    pass
if auth_enforced == 0:
    _v.append("auth_bypass")
# a transfer must NEVER reach SETTLED when an actual precondition forbids it
if _settled:
    if _pre_state["sanctioned_sender"] or _pre_state["bank_sanctioned"]:
        _v.append("sanctioned_settled")
    if _pre_state["sanctioned_receiver"] and TOPOLOGY == "intra":
        _v.append("sanctioned_settled")
    if _pre_state["frozen"]:
        _v.append("frozen_settled")
    if _pre_state["unverified"]:
        _v.append("unverified_settled")
    try:
        if Decimal(AMOUNT) <= 0:
            _v.append("nonpositive_settled")
        if Decimal(AMOUNT) >= 10000:
            _v.append("overlimit_settled")
    except Exception:
        pass
if _settled and CONFIRM_DECISION in ("reject_sender", "reject_receiver"):
    _v.append("rejected_settled")
if _settled and REVIEW == "deny" and _requires_review:
    _v.append("denied_settled")
if time_sync_ok == 0:
    _v.append("time_sync_failed")
if live_xfer_ok == 0:
    _v.append("live_xfer_failed")

METRICS["auth_enforced"] = auth_enforced
METRICS["connected"] = connected
METRICS["crash"] = 1 if crash_msg else 0
METRICS["currency"] = CURRENCY or "EMPTY"
METRICS["amount"] = AMOUNT
METRICS["auth"] = AUTH
METRICS["topology"] = TOPOLOGY
METRICS["kyc"] = KYC
METRICS["brand"] = BRAND
METRICS["limit"] = str(LIMIT)
METRICS["expiry"] = EXPIRY or "EMPTY"
METRICS["factors"] = "|".join(FACTORS) if FACTORS else "none"
METRICS["confirm_decision"] = CONFIRM_DECISION
METRICS["review"] = REVIEW
METRICS["time_sync"] = TIME_SYNC
METRICS["live_xfer"] = LIVE_XFER
METRICS["http_settled"] = http_settled
METRICS["violations"] = len(_v)
METRICS["score"] = max(0, 100 - 20 * len(_v))
if "crash" in _v:
    FW_VAR = 2
elif "auth_bypass" in _v or "sanctioned_settled" in _v:
    FW_VAR = 4
elif "unbalanced" in _v or "negative_balance" in _v:
    FW_VAR = 6
elif _v:
    FW_VAR = 3
else:
    FW_VAR = 0
METRICS["FW_VAR"] = FW_VAR
FW_CUSTOM_VAR = FW_VAR
def _fmt(v):
    return str(v).replace(" ", "_")
print(" ".join("%s=%s" % (k, _fmt(v)) for k, v in METRICS.items()))
'''

CUSTOM_VARS = [
    (2, "unexpected crash / unhandled exception in the simulator"),
    (3, "domain invariant violated (wrong terminal state / amount / kyc / frozen)"),
    (4, "security bypass (auth accepted bad request OR sanctioned party settled)"),
    (6, "ledger integrity violated (unbalanced or negative balance)"),
]


# ---------------------------------------------------------------------------
# Helper to build a slot value list of "VAR = <repr>" assignment lines.
# ---------------------------------------------------------------------------
def assign(var, values):
    return [f'{var} = {v!r}\n' for v in values]


def factor(position, name):
    """A FW_Optional 'sudden action' piece: register an external factor at <position>."""
    return [f'FACTORS.append("{position}:{name}")\n']


def opseq_pieces():
    return ['OPSEQ = ["SENDER", "RECEIVER"]\n', 'OPSEQ = ["RECEIVER", "SENDER"]\n']


# ---------------------------------------------------------------------------
# BATCHES — each a small, focused dispersed spec.
#   slot = (sheet, key, verb, values, flags)
# ---------------------------------------------------------------------------
def batches():
    B = {}

    # 1) AUTH matrix against the LIVE cluster (HMAC enforcement) × topology.
    B["auth_matrix"] = [
        ("AUTH", "auth", "FW_Combi(1)", assign("AUTH", ["valid_hmac", "missing_headers", "bad_signature", "expired_timestamp"]), []),
        ("TOPOLOGY", "topo", "FW_Combi(1)", assign("TOPOLOGY", ["intra", "cross"]), []),
        ("CURRENCY", "cur", "FW_Combi(1)", assign("CURRENCY", ["USD", "XX"]), []),
    ]

    # 2) Card-account CRUD: brand × limit × expiry (boundary/equivalence) × optional ops (Subsets).
    B["cards_crud"] = [
        ("BRAND", "brand", "FW_Combi(1)", assign("BRAND", ["VISA", "MASTERCARD", "AMEX", "DISCOVER"]), []),
        ("LIMIT", "limit", "FW_Combi(1)", assign("LIMIT", ["500.00", "0.00", "none", "-1.00"]), []),
        ("EXPIRY", "expiry", "FW_Combi(1)", assign("EXPIRY", ["2030-12", "2030-13", "2030/12", ""]), []),
        ("CARDOPS", "cardops", "FW_Subsets", ['OPT.append("block_card")\n', 'OPT.append("delete_card")\n'], []),
    ]

    # 3) Intra-bank transfer: amount tiers × currency × confirm order (Permut) × compound faults (Combi(2)).
    B["intra_transfer"] = [
        ("AMOUNT", "amt", "FW_Combi(1)", assign("AMOUNT", ["100.00", "0.00", "-1.00", "2000.00", "15000.00"]), []),
        ("CURRENCY", "cur", "FW_Combi(1)", assign("CURRENCY", ["USD", "XX", ""]), []),
        ("OPSEQ", "opseq", "FW_Permut", opseq_pieces(), []),
        ("FAULTS", "faults", "FW_Combi(2)",
         ['FAULTS.append("frozen")\n', 'FAULTS.append("sanction_sender")\n', 'FAULTS.append("kyc_pending")\n'], []),
    ]

    # 4) Cross-bank transfer + EXTERNAL FACTORS as FW_Optional sudden-actions in different positions.
    B["cross_factors"] = [
        ("TOPO", "topo", "FW_Combi(1)", assign("TOPOLOGY", ["cross"]), []),
        ("AMOUNT", "amt", "FW_Combi(1)", assign("AMOUNT", ["100.00", "2000.00"]), []),
        ("OPSEQ", "opseq", "FW_Permut", opseq_pieces(), []),
        ("FPEER", "fpeer", "FW_Combi(1)", factor("after_initiate", "peer_hold") + factor("after_initiate", "peer_down"), ["FW_Optional"]),
        ("FRECOVER", "frecover", "FW_Combi(1)", factor("after_confirm", "peer_recover"), ["FW_Optional"]),
        ("FTTL", "fttl", "FW_Combi(1)", factor("after_initiate", "force_expire"), ["FW_Optional"]),
    ]

    # 5) Risk gates: KYC × amount tiers × FW_Optional velocity burst / manual flag.
    B["risk_gates"] = [
        ("KYC", "kyc", "FW_Combi(1)", assign("KYC", ["VERIFIED", "PENDING", "REJECTED"]), []),
        ("AMOUNT", "amt", "FW_Combi(1)", assign("AMOUNT", ["100.00", "2000.00", "15000.00"]), []),
        ("FVEL", "fvel", "FW_Combi(1)", factor("after_register", "velocity_burst"), ["FW_Optional"]),
        ("FFLAG", "fflag", "FW_Combi(1)", factor("after_register", "flag_sender"), ["FW_Optional"]),
    ]

    # 6) Sanctions screening: topology × FW_Optional sanction sender/receiver/bank (different positions).
    B["sanctions"] = [
        ("TOPOLOGY", "topo", "FW_Combi(1)", assign("TOPOLOGY", ["intra", "cross"]), []),
        ("FSAN_S", "fsans", "FW_Combi(1)", factor("after_register", "sanction_sender"), ["FW_Optional"]),
        ("FSAN_R", "fsanr", "FW_Combi(1)", factor("after_register", "sanction_receiver"), ["FW_Optional"]),
        ("FSAN_B", "fsanb", "FW_Combi(1)", factor("after_register", "sanction_bank"), ["FW_Optional"]),
    ]

    # 7) Identity + accounts: KYC × currency (equivalence) × deposit not used here; freeze factor.
    B["identity_accounts"] = [
        ("KYC", "kyc", "FW_Combi(1)", assign("KYC", ["VERIFIED", "PENDING", "REJECTED"]), []),
        ("CURRENCY", "cur", "FW_Combi(1)", assign("CURRENCY", ["USD", "EUR", "usd", "XX", ""]), []),
        ("FFREEZE", "ffreeze", "FW_Combi(1)", factor("after_open", "freeze"), ["FW_Optional"]),
    ]

    # 8) Transfer lifecycle: confirm decision (reject A/B) × compliance review × amount tier.
    B["transfer_lifecycle"] = [
        ("CONFIRM", "confirm", "FW_Combi(1)", assign("CONFIRM_DECISION", ["both", "reject_sender", "reject_receiver"]), []),
        ("REVIEW", "review", "FW_Combi(1)", assign("REVIEW", ["none", "approve", "deny"]), []),
        ("AMOUNT", "amt", "FW_Combi(1)", assign("AMOUNT", ["100.00", "2000.00"]), []),
    ]

    # 9) Currency matrix: source vs target currency (mismatch → ValidationError, no settle).
    B["currency_matrix"] = [
        ("CURRENCY", "cur", "FW_Combi(1)", assign("CURRENCY", ["USD", "EUR", "usd"]), []),
        ("TGTCUR", "tgtcur", "FW_Combi(1)", assign("TGT_CURRENCY", ["USD", "EUR", ""]), []),
    ]

    # 10) Compound TRIPLE faults via FW_Combi(3) — C(5,3)=10 simultaneous pre-conditions.
    B["compound_faults3"] = [
        ("FAULTS3", "faults3", "FW_Combi(3)",
         ['FAULTS.append("frozen")\n', 'FAULTS.append("sanction_sender")\n',
          'FAULTS.append("sanction_receiver")\n', 'FAULTS.append("kyc_pending")\n',
          'FAULTS.append("block_card")\n'], []),
    ]

    # 11) LIVE cross-instance time-unit sync (propagate + accept-flag override) over the 2 nodes.
    B["time_sync"] = [
        ("TFIELD", "tfield", "FW_Combi(1)", assign("TIME_SYNC", ["confirmation_ttl_seconds", "risk_window_seconds", "replay_window_seconds"]), []),
        ("TVALUE", "tvalue", "FW_Combi(1)", assign("TIME_VALUE", ["1", "60"]), []),
        ("PROP", "prop", "FW_Combi(1)", assign("PROPAGATE", ["self", "connected"]), []),
        ("ACCEPT", "accept", "FW_Combi(1)", assign("ACCEPT_SYNC", ["true", "false"]), []),
    ]

    # 12) LIVE cross-bank settlement: real money moved AURUM->NORD over HTTP + two-party confirm.
    B["live_crossbank"] = [
        ("LIVEXFER", "livex", "FW_Combi(1)", assign("LIVE_XFER", ["on"]), []),
        ("AMOUNT", "amt", "FW_Combi(1)", assign("AMOUNT", ["100.00", "2000.00"]), []),
        ("OPSEQ", "opseq", "FW_Permut", opseq_pieces(), []),
    ]

    return B


# ---------------------------------------------------------------------------
# Emit a dispersed .toml per batch.
# ---------------------------------------------------------------------------
def _toml_slot(sheet, key, verb, values, flags):
    out = ["[[slots]]", f'sheet = "{sheet}"', f'key = "{key}"', f'verb = "{verb}"', "raw = true"]
    if flags:
        out.append("flags = [" + ", ".join(f'"{f}"' for f in flags) + "]")
    out.append("values = [")
    for v in values:
        assert "'''" not in v, "code piece must not contain triple single-quote"
        out.append("'''" + v + "''',")
    out.append("]")
    return "\n".join(out) + "\n"


def emit():
    BATCHES.mkdir(parents=True, exist_ok=True)
    manifest = ["# fintech_oot — small Bundle batches (run each: `python3 ../bundle_run.py batches/<name>`)\n"]
    for name, slots in batches().items():
        d = BATCHES / name
        d.mkdir(parents=True, exist_ok=True)
        body = [
            f'title = "fintech_oot — {name} (current finance_stack simulator, 2 live instances + in-process)"',
            f'note  = "small focused batch; LIVE HMAC cluster + in-process param/factor combinatorics; FW_Optional external sudden-actions"',
            'goals = ["violations", "score", "settled", "on_hold", "blocked"]',
            f'args  = ["mode=fintech_oot", "batch={name}"]',
            "",
            _toml_slot("HEAD", "head", "FW_Combi(1)", [HEAD], []),
        ]
        n = 1
        prod = 1
        opt = 1
        for (sheet, key, verb, values, flags) in slots:
            body.append(_toml_slot(sheet, key, verb, values, flags))
            # rough size estimate
            if "FW_Optional" in flags:
                opt *= (len(values) + 1)
            elif verb == "FW_Permut":
                import math
                prod *= math.factorial(len(values))
            elif verb == "FW_Subsets":
                prod *= 2 ** len(values)
            elif verb.startswith("FW_Combi("):
                k = int(verb[len("FW_Combi("):-1])
                prod *= (len(values) if k == 1 else len(list(itertools.combinations(values, k))))
        # In stress mode the full verdict flow is skipped — candidates only fire().
        tail_guarded = ("import os as _oot_os\n"
                        "if _oot_os.environ.get('OOT_MODE') == 'stress':\n"
                        "    pass\n"
                        "else:\n" + textwrap.indent(TAIL, "    "))
        body.append(_toml_slot("TAIL", "tail", "FW_Combi(1)", [tail_guarded], []))
        for code, msg in CUSTOM_VARS:
            body.append(f"[[custom_vars]]\ncode = {code}\nmsg  = \"{msg}\"\n")
        (d / f"{name}.toml").write_text("\n".join(body), encoding="utf-8")
        est = prod * opt
        manifest.append(f"- **{name}**  → ~{prod}×{opt} = {est} candidates   ({len(slots)} variation slots)")
        print(f"  emitted {name}/{name}.toml   est ~{est} candidates (non-opt {prod} × optional {opt})")
    (BATCHES / "MANIFEST.md").write_text("\n".join(manifest), encoding="utf-8")


if __name__ == "__main__":
    emit()
