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

"""Second direct engine demonstration — a transactional store, and its oracle.

This is the *second* SUT, and it exists to answer one question the first cannot:
**does the flagship finding survive a change of domain?** A study with one system
under test measures that system. Two systems that disagree tell you the finding
was about the first one; two that agree make it worth repeating elsewhere.

So this SUT is deliberately unlike `record_pipeline` in every dimension that
could carry the earlier result:

===================  ==============================  ==============================
dimension            `record_pipeline` (SUT 1)       `txn_store` (SUT 2)
===================  ==============================  ==============================
state                none survives an operation      **mutable store, state is the point**
composition          pure function composition       **scoped effects with rollback**
oracle technique     differential (two evaluators)   **invariant + metamorphic + naive replay**
what an op does      maps a value stream             **mutates a keyed store and its index**
failure of interest  wrong output value              **wrong surviving state**
===================  ==============================  ==============================

The engine's half is unchanged, and that is the second thing this file
demonstrates: the same `FW_Group` / `FW_PermutR` / `FW_Optional` / five-link
nested brace chain composes a *transaction tree* exactly as it composed a
pipeline tree. The engine never learns what a transaction is.

Node model::

    Node := Op(kind, params)              # put / delete / bump / read / purge
          | Block(children)               # plain sequence, no scope
          | Txn(children, commit)         # a transaction scope: commits or rolls back
          | Repeat(child, count)

The oracle is exact and independent of the code it judges, in **four** layers,
three of which have no analogue in SUT 1:

1. **Structural invariant** (`index_incoherence`) — the secondary index must be
   exactly the inverse of the primary map, checked after *every* operation. This
   is a relation between two of the SUT's own structures, so it needs no second
   implementation and no expected value.
2. **Metamorphic** (`rollback identity`) — a transaction that rolls back must
   leave the store byte-identical to its state when the transaction opened. The
   harness takes its own snapshot to compare against; it never consults the SUT's
   savepoint stack, which is the thing under suspicion.
3. **Naive replay** (`replay_mismatch`) — the surviving state must equal what you
   get by applying the *effective* operations to a plain dictionary with no index
   and no savepoint machinery at all. Twenty lines that cannot share a defect
   with the implementation they check.
4. **Structural bound** (`max_store_size`) — computed from the tree without
   executing it: only `put` can introduce a key, so the final store cannot be
   larger than the initial one plus the number of `put` nodes.

A **service contract** decides the domain question separately, and a contract
violation is never reported as a defect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, Union

#: The fixed initial store. Keys 1 and 2 deliberately share a value, so index
#: buckets with more than one member exist from the start — a delete that forgets
#: the multi-member case behaves differently from one that forgets the singleton
#: case, and both are reachable.
INITIAL: "Mapping[int, int]" = {1: 5, 2: 5, 3: -2, 4: 0}

#: Declared service contract on the SURVIVING state.
CONTRACT_LOW = -30
CONTRACT_HIGH = 30

VERDICT_PASS = 0
VERDICT_CONSTRUCTION = 2         # malformed/unbuildable candidate structure
VERDICT_RUNTIME = 3              # execution raised
VERDICT_ORACLE_DISAGREEMENT = 4  # invariant/metamorphic/replay/bound violated
VERDICT_CONTRACT = 5             # domain acceptance: the contract was violated

VERDICT_MESSAGES: "Mapping[int, str]" = {
    VERDICT_PASS: "transaction tree executed and satisfied the store service contract",
    VERDICT_CONSTRUCTION: "candidate construction/compile/validation failure",
    VERDICT_RUNTIME: "transaction execution failure",
    VERDICT_ORACLE_DISAGREEMENT: "independent oracle disagreement (index, rollback, replay or bound)",
    VERDICT_CONTRACT: "store service contract violated",
}

OP_KINDS = ("put", "delete", "bump", "read", "purge")


class StoreError(ValueError):
    """A structurally invalid candidate: unknown operation, missing parameter, or
    a marker stream that does not close."""


# ------------------------------------------------------------- node model ----
@dataclass(frozen=True)
class Op:
    kind: str
    params: "tuple[tuple[str, int], ...]" = ()

    def param(self, name: str) -> int:
        for key, value in self.params:
            if key == name:
                return value
        raise StoreError(f"operation {self.kind!r} is missing required parameter {name!r}")


@dataclass(frozen=True)
class Block:
    children: "tuple[Node, ...]"


@dataclass(frozen=True)
class Txn:
    """A transaction scope. `commit` decides whether its effects survive."""

    children: "tuple[Node, ...]"
    commit: bool


@dataclass(frozen=True)
class Repeat:
    child: "Node"
    count: int


Node = Union[Op, Block, Txn, Repeat]


@dataclass(frozen=True)
class Marker:
    """A scope boundary emitted by a Bundle fragment. `tag` pairs an open with its
    close, which is what lets independently generated brace operands nest."""

    tag: int
    opening: bool
    kind: str = ""
    params: "tuple[tuple[str, int], ...]" = ()


StreamItem = Union[Node, Marker]


# ------------------------------------------------ fragment emission helpers --
def _params(**kwargs: int) -> "tuple[tuple[str, int], ...]":
    return tuple(sorted((str(k), int(v)) for k, v in kwargs.items()))


def emit_op(stream: list, kind: str, **params: int) -> None:
    """Append one operation. Called from a BODY fragment."""
    stream.append(Op(kind=str(kind), params=_params(**params)))


def emit_node(stream: list, node: Node) -> None:
    """Append a whole prebuilt substructure (a `bundle`)."""
    stream.append(node)


def emit_open(stream: list, tag: int, kind: str, **params: int) -> None:
    """Open a nested scope. `kind` is ``block``/``txn``/``repeat``."""
    stream.append(Marker(tag=int(tag), opening=True, kind=str(kind), params=_params(**params)))


def emit_close(stream: list, tag: int) -> None:
    """Close the scope opened with the same `tag`."""
    stream.append(Marker(tag=int(tag), opening=False))


#: Named operation groups a `FW_Group` sheet can drop in whole. These are seed
#: material for the engine to compose, not hand-written final candidates.
_BUNDLES: "Mapping[str, Node]" = {
    # Both bundles leave the store contract-satisfying on their own, so any
    # contract failure the demonstration reports is attributable to the
    # *composition*, not to a bundle.
    "seed": Block((Op("put", _params(key=5, value=7)),
                   Op("put", _params(key=6, value=7)))),
    "shuffle": Block((Op("bump", _params(delta=3, key=1)),
                      Op("bump", _params(delta=-3, key=2)))),
    "trim": Block((Op("delete", _params(key=4)),
                   Op("put", _params(key=7, value=-1)))),
}


def bundle(name: str) -> Node:
    try:
        return _BUNDLES[name]
    except KeyError:
        raise StoreError(f"unknown bundle {name!r}; known: {sorted(_BUNDLES)}")


# ------------------------------------------------------------ stream parsing --
def parse_topology(stream: "Sequence[StreamItem]") -> Node:
    """Build the highest-order *complete* structure in `stream`.

    Core legitimately re-emits helper sheets outside the brace that wove them, so
    the stream can contain an unclosed frame or an immediately-closed empty scope.
    Both are debris: they are dropped rather than failing the candidate. Among the
    completed non-empty roots the deepest one wins, ties broken by position, which
    makes the selection a pure function of the stream.
    """
    roots: "list[Node]" = []
    stack: "list[tuple[Marker, list]]" = []
    for item in stream:
        if isinstance(item, Marker):
            if item.opening:
                stack.append((item, []))
                continue
            for index in range(len(stack) - 1, -1, -1):
                if stack[index][0].tag == item.tag:
                    opener, children = stack[index]
                    del stack[index:]
                    if children:                    # an empty scope is helper debris
                        node = _build_scope(opener, tuple(children))
                        (stack[-1][1] if stack else roots).append(node)
                    break
            continue
        (stack[-1][1] if stack else roots).append(item)
    if not roots:
        raise StoreError("no complete structure in the candidate stream")
    best = max(range(len(roots)), key=lambda i: (depth(roots[i]), i))
    return roots[best]


def _build_scope(opener: Marker, children: "tuple[Node, ...]") -> Node:
    if not children:
        raise StoreError(f"{opener.kind!r} scope {opener.tag} closed with no children")
    if opener.kind == "block":
        return Block(children)
    if opener.kind == "txn":
        return Txn(children, bool(dict(opener.params).get("commit", 1)))
    if opener.kind == "repeat":
        count = dict(opener.params).get("count", 2)
        if not 1 <= count <= 8:
            raise StoreError(f"repeat count {count} outside the bounded range 1..8")
        body = children[0] if len(children) == 1 else Block(children)
        return Repeat(body, int(count))
    raise StoreError(f"unknown scope kind {opener.kind!r}")


# ------------------------------------------------------------------ the SUT --
class Store:
    """A keyed store with a denormalized secondary index.

    The index is what makes this interesting: it is redundant state that every
    mutating path must keep in step, which is precisely the kind of obligation
    real code forgets. Layer 1 of the oracle checks nothing else.
    """

    __slots__ = ("data", "index")

    def __init__(self, initial: "Mapping[int, int]" = INITIAL):
        self.data: "dict[int, int]" = dict(initial)
        self.index: "dict[int, set[int]]" = {}
        for key, value in self.data.items():
            self.index.setdefault(value, set()).add(key)

    def snapshot(self) -> "tuple[dict, dict]":
        """A genuinely independent deep copy — the harness compares against this,
        so sharing structure with the live store would silently disarm layer 2."""
        return (dict(self.data), {v: set(ks) for v, ks in self.index.items() if ks})

    def restore(self, snap: "tuple[dict, dict]") -> None:
        self.data = dict(snap[0])
        self.index = {v: set(ks) for v, ks in snap[1].items()}

    def state(self) -> "tuple[dict, dict]":
        return self.snapshot()


def _op_put(store: Store, op: Op) -> None:
    key, value = op.param("key"), op.param("value")
    _unindex(store, key)
    store.data[key] = value
    store.index.setdefault(value, set()).add(key)


def _op_delete(store: Store, op: Op) -> None:
    key = op.param("key")
    if key in store.data:
        _unindex(store, key)
        del store.data[key]


def _op_bump(store: Store, op: Op) -> None:
    key, delta = op.param("key"), op.param("delta")
    if key in store.data:
        _unindex(store, key)
        store.data[key] += delta
        store.index.setdefault(store.data[key], set()).add(key)


def _op_read(store: Store, op: Op) -> None:
    """A pure read. It exists so that "did anything change between these two
    points" can be a real factor rather than a constant."""
    store.data.get(op.param("key"))


def _op_purge(store: Store, op: Op) -> None:
    """Delete every key currently holding `value`, resolved THROUGH the index.

    This is why the index exists, and it is what makes an incoherent index a
    correctness problem rather than a tidiness one.
    """
    value = op.param("value")
    for key in sorted(store.index.get(value, ())):
        if key in store.data:
            del store.data[key]
    store.index.pop(value, None)


def _unindex(store: Store, key: int) -> None:
    old = store.data.get(key)
    if old is None:
        return
    bucket = store.index.get(old)
    if bucket:
        bucket.discard(key)
        if not bucket:
            del store.index[old]


#: Dispatch table. Mutants replace an entry here, so the *only* thing a mutant
#: changes is the implementation of one operation or one savepoint primitive —
#: never the oracle.
_OPS = {"put": _op_put, "delete": _op_delete, "bump": _op_bump,
        "read": _op_read, "purge": _op_purge}


def _apply(store: Store, op: Op) -> None:
    try:
        handler = _OPS[op.kind]
    except KeyError:
        raise StoreError(f"unknown operation {op.kind!r}; known: {OP_KINDS}")
    handler(store, op)


# ------------------------------------------------------ savepoint machinery --
# Copy-on-write: entering a transaction is free, and the snapshot is materialized
# only when something actually mutates inside it. Real stores do this, and it is
# where the second mutant lives.
def _savepoint_enter(state: dict) -> None:
    """Push one stack entry per ENTRY. `dirty` belongs to the entry, not to the
    depth: two different transactions that happen to run at the same depth are
    two different transactions."""
    state["stack"].append({"snapshot": None, "dirty": False})


def _savepoint_touch(state: dict, store: Store) -> None:
    """Materialize the snapshot for every open scope that has not taken one yet."""
    for entry in state["stack"]:
        if not entry["dirty"]:
            entry["dirty"] = True
            entry["snapshot"] = store.snapshot()


def _savepoint_leave(state: dict, store: Store, commit: bool) -> None:
    entry = state["stack"].pop()
    if not commit and entry["dirty"]:
        store.restore(entry["snapshot"])


#: Operations that mutate. A read must not arm a savepoint — that is the whole
#: point of copy-on-write, and it is what makes "did anything write here" an
#: observable factor.
_MUTATING = frozenset({"put", "delete", "bump", "purge"})


# ---------------------------------------------------------------- execution --
def execute(node: Node, store: "Store | None" = None) -> "tuple[Store, int, list[str]]":
    """Run `node`, checking the online oracle layers as it goes.

    Returns (store, operations executed, oracle findings). Findings are collected
    rather than raised so that one candidate reports every layer it violated,
    which is what makes a detection attributable to a mechanism.
    """
    store = store if store is not None else Store()
    state = {"stack": []}
    findings: "list[str]" = []
    counter = [0]
    _run(node, store, state, findings, counter)
    if state["stack"]:
        raise StoreError("candidate ended with an open transaction scope")
    return store, counter[0], findings


def _run(node: Node, store: Store, state: dict, findings: list, counter: list) -> None:
    if isinstance(node, Op):
        if node.kind in _MUTATING:
            _savepoint_touch(state, store)
        _apply(store, node)
        counter[0] += 1
        # LAYER 1, after every operation: the index must be the exact inverse of
        # the map. Checking here rather than at the end is what makes the finding
        # point at an operation instead of at a candidate.
        incoherence = index_incoherence(store)
        if incoherence and incoherence not in findings:
            findings.append(incoherence)
        return
    if isinstance(node, Block):
        for child in node.children:
            _run(child, store, state, findings, counter)
        return
    if isinstance(node, Txn):
        # LAYER 2 (metamorphic): the harness takes its OWN snapshot. It never
        # reads the savepoint stack, because the savepoint stack is exactly what
        # a rollback defect corrupts.
        before = store.snapshot()
        _savepoint_enter(state)
        for child in node.children:
            _run(child, store, state, findings, counter)
        _savepoint_leave(state, store, node.commit)
        if not node.commit and store.state() != before and "rollback_leaked" not in findings:
            findings.append("rollback_leaked")
        return
    if isinstance(node, Repeat):
        for _ in range(node.count):
            _run(node.child, store, state, findings, counter)
        return
    raise StoreError(f"unknown node type {type(node).__name__}")


# ------------------------------------------- oracle layer 1: the invariant ----
def index_incoherence(store: Store) -> str:
    """`""` when the secondary index is exactly the inverse of the primary map."""
    expected: "dict[int, set[int]]" = {}
    for key, value in store.data.items():
        expected.setdefault(value, set()).add(key)
    actual = {v: set(ks) for v, ks in store.index.items() if ks}
    return "" if actual == expected else "index_incoherent"


# -------------------------------------- oracle layer 3: naive replay ---------
def effective_ops(node: Node) -> "list[Op]":
    """The operations whose effects survive, derived from the tree ALONE.

    A rolled-back transaction contributes nothing; a committed one contributes its
    children. No store, no index, no savepoints — this is a pure reading of what
    the candidate *means*, which is why it can judge what the candidate *did*.
    """
    if isinstance(node, Op):
        return [node]
    if isinstance(node, Block):
        return [op for child in node.children for op in effective_ops(child)]
    if isinstance(node, Txn):
        if not node.commit:
            return []
        return [op for child in node.children for op in effective_ops(child)]
    if isinstance(node, Repeat):
        return [op for _ in range(node.count) for op in effective_ops(node.child)]
    raise StoreError(f"unknown node type {type(node).__name__}")


def naive_apply(ops: "Sequence[Op]", initial: "Mapping[int, int]" = INITIAL) -> "dict[int, int]":
    """Apply operations to a plain dictionary. No index, no scopes, no savepoints.

    Deliberately not factored together with `_OPS`: the duplication IS the oracle.
    """
    data = dict(initial)
    for op in ops:
        if op.kind == "put":
            data[op.param("key")] = op.param("value")
        elif op.kind == "delete":
            data.pop(op.param("key"), None)
        elif op.kind == "bump":
            key = op.param("key")
            if key in data:
                data[key] += op.param("delta")
        elif op.kind == "purge":
            value = op.param("value")
            for key in [k for k, v in data.items() if v == value]:
                del data[key]
        elif op.kind == "read":
            pass
        else:
            raise StoreError(f"unknown operation {op.kind!r}; known: {OP_KINDS}")
    return data


# ------------------------------------ oracle layer 4: the structural bound ----
def max_store_size(node: Node, initial_size: int = len(INITIAL)) -> int:
    """Upper bound on the surviving key count, from the structure alone.

    Sound because only `put` can introduce a key: everything else removes keys,
    changes values, or reads. Nothing is executed, so this is genuinely
    independent evidence rather than a second reading of the same run.
    """
    return initial_size + _put_count(node)


def _put_count(node: Node) -> int:
    if isinstance(node, Op):
        return 1 if node.kind == "put" else 0
    if isinstance(node, (Block, Txn)):
        return sum(_put_count(child) for child in node.children)
    if isinstance(node, Repeat):
        return node.count * _put_count(node.child)
    raise StoreError(f"unknown node type {type(node).__name__}")


def depth(node: Node) -> int:
    if isinstance(node, Op):
        return 1
    if isinstance(node, (Block, Txn)):
        return 1 + max((depth(child) for child in node.children), default=0)
    if isinstance(node, Repeat):
        return 1 + depth(node.child)
    raise StoreError(f"unknown node type {type(node).__name__}")


def op_count(node: Node) -> int:
    if isinstance(node, Op):
        return 1
    if isinstance(node, (Block, Txn)):
        return sum(op_count(child) for child in node.children)
    if isinstance(node, Repeat):
        return node.count * op_count(node.child)
    raise StoreError(f"unknown node type {type(node).__name__}")


def _txn_count(node: Node) -> int:
    if isinstance(node, Op):
        return 0
    if isinstance(node, Txn):
        return 1 + sum(_txn_count(c) for c in node.children)
    if isinstance(node, Block):
        return sum(_txn_count(c) for c in node.children)
    if isinstance(node, Repeat):
        return _txn_count(node.child)
    raise StoreError(f"unknown node type {type(node).__name__}")


def topology_stats(node: Node) -> "dict[str, int]":
    """Metric names match `record_pipeline` so both SUTs feed the same Analyzer
    goals unchanged — `branches` counts transaction scopes here."""
    return {"stages": op_count(node), "depth": depth(node), "branches": _txn_count(node)}


# ------------------------------------------------------- the service contract --
def contract_violation(store: Store) -> str:
    """Exact domain verdict on the SURVIVING state, or ``""`` when it is
    acceptable. This is the only check allowed to report a domain failure."""
    if not store.data:
        return "empty_store"
    for value in store.data.values():
        if value < CONTRACT_LOW or value > CONTRACT_HIGH:
            return "value_out_of_band"
    return ""


# --------------------------------------------------------------- the verdict --
@dataclass(frozen=True)
class Result:
    code: int
    reason: str
    stages: int = 0
    depth: int = 0
    branches: int = 0
    ops: int = 0
    retained: int = 0

    def metrics_line(self) -> str:
        """One whitespace-separated ``K=V`` record, same keys and directions as
        the record pipeline so one Analyzer configuration serves both SUTs."""
        return (f"app=txn_store stages={self.stages} depth={self.depth} "
                f"branches={self.branches} ops={self.ops} retained={self.retained} "
                f"reason={self.reason or 'ok'} FW_VAR={self.code}")


def evaluate(stream: "Sequence[StreamItem]",
             initial: "Mapping[int, int]" = INITIAL) -> Result:
    """Build, execute and judge one candidate. Never raises: every failure mode
    becomes a classified verdict so the Executor's outcome taxonomy stays
    meaningful (a construction defect is not a domain answer)."""
    try:
        node = parse_topology(stream)
        stats = topology_stats(node)
    except StoreError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc))
    try:
        store, ops, findings = execute(node, Store(initial))
    except StoreError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc), **stats)
    except Exception as exc:                                    # noqa: BLE001
        return Result(code=VERDICT_RUNTIME, reason=_token(exc), **stats)
    try:
        expected = naive_apply(effective_ops(node), initial)    # layer 3
        bound = max_store_size(node, len(initial))              # layer 4
    except StoreError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc), ops=ops, **stats)

    if findings:
        # Layers 1 and 2 fired during execution. The first finding names the
        # mechanism, which is what lets a detection be attributed.
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason=findings[0],
                      ops=ops, retained=len(store.data), **stats)
    if store.data != expected:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason="replay_mismatch",
                      ops=ops, retained=len(store.data), **stats)
    if len(store.data) > bound:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason="size_bound_exceeded",
                      ops=ops, retained=len(store.data), **stats)
    violation = contract_violation(store)
    code = VERDICT_CONTRACT if violation else VERDICT_PASS
    return Result(code=code, reason=violation, ops=ops, retained=len(store.data), **stats)


def _token(exc: Exception) -> str:
    """Collapse an exception into a stable, whitespace-free reason token so the
    metrics line stays parseable."""
    return type(exc).__name__.lower()
