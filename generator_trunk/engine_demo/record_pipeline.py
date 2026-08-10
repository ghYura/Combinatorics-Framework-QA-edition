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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Direct engine demonstration — domain adapter and exact oracle.

This module is the *domain realization* half of the engine-first demonstration.
The Bundle owns **structural enumeration**: `FW_Group`, `FW_PermutR` and a
three-link nested-brace chain in `direct_engine_smoke/scenario.toml` emit an
ordered marker stream. This module turns that stream into an immutable recursive
pipeline, executes it, and judges it.

Nothing here imports a reference application, an LLM, a network client, or an
external system under test: the whole demonstration is Python's standard library
plus integers, so the engine's advanced composition can be exercised in a
release gate on a bare checkout.

Node model (the structure the engine composes)::

    Node := Atom(kind, params)
          | Sequence(children)
          | Parallel(children, reducer)
          | Repeat(child, count)

Every node denotes a total function ``tuple[int, ...] -> tuple[int, ...]``, so
any nesting the engine produces is executable.

The oracle is exact and independent of the thing it judges, in three layers:

1. **Differential.** :func:`run_compiled` lowers the tree into closures and
   folds them; :func:`reference_eval` walks the same tree by direct structural
   recursion with a separately written dispatch chain. The two implementations
   are deliberately *not* factored together — that duplication is the oracle.
   Disagreement is a defect, never a domain answer.
2. **Structural.** :func:`max_output_length` bounds the output length from the
   tree alone, without executing anything, because every atom here is
   non-expanding. An execution that exceeds its own structural bound is a defect.
3. **Service contract.** :func:`contract_violation` decides the domain question
   exactly: is the produced record stream non-empty, non-decreasing, and inside
   the declared value band? This is the only check allowed to report a *domain*
   failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, Union

#: The fixed, deterministic input corpus. Non-decreasing, with duplicates,
#: negatives and a zero, so ordering/dedup/threshold stages all have something
#: to act on. A candidate never chooses its own data: the corpus is a controlled
#: variable, the pipeline structure is the independent one.
CORPUS: "tuple[int, ...]" = (-7, -3, -3, 0, 2, 5, 5, 9, 14)

#: Declared service contract: every emitted record must land inside this band.
CONTRACT_LOW = -30
CONTRACT_HIGH = 30

VERDICT_PASS = 0
VERDICT_CONSTRUCTION = 2       # malformed/unbuildable candidate structure
VERDICT_RUNTIME = 3            # execution raised
VERDICT_ORACLE_DISAGREEMENT = 4  # invariant/safety: the two oracles disagree
VERDICT_CONTRACT = 5           # domain acceptance: the contract was violated

VERDICT_MESSAGES: "Mapping[int, str]" = {
    VERDICT_PASS: "pipeline executed and satisfied the record service contract",
    VERDICT_CONSTRUCTION: "candidate construction/compile/validation failure",
    VERDICT_RUNTIME: "pipeline execution failure",
    VERDICT_ORACLE_DISAGREEMENT: "independent oracle disagreement or structural-bound violation",
    VERDICT_CONTRACT: "record service contract violated",
}


class PipelineError(ValueError):
    """A structurally invalid pipeline: unknown atom, bad parameters, or a
    marker stream that does not close."""


# ------------------------------------------------------------- node model ----
@dataclass(frozen=True)
class Atom:
    kind: str
    params: "tuple[tuple[str, int], ...]" = ()

    def param(self, name: str) -> int:
        for key, value in self.params:
            if key == name:
                return value
        raise PipelineError(f"atom {self.kind!r} is missing required parameter {name!r}")


@dataclass(frozen=True)
class Sequence_:
    children: "tuple[Node, ...]"


@dataclass(frozen=True)
class Parallel:
    children: "tuple[Node, ...]"
    reducer: str


@dataclass(frozen=True)
class Repeat:
    child: "Node"
    count: int


Node = Union[Atom, Sequence_, Parallel, Repeat]

ATOM_KINDS = ("scale", "offset", "clamp", "drop_below", "dedupe", "sort")
REDUCERS = ("merge", "concat")


@dataclass(frozen=True)
class Marker:
    """A scope boundary emitted by a Bundle fragment. `tag` pairs an open with
    its close, which is what lets independently generated brace operands nest."""

    tag: int
    opening: bool
    kind: str = ""
    params: "tuple[tuple[str, int], ...]" = ()
    reducer: str = ""


StreamItem = Union[Node, Marker]


# ------------------------------------------------- fragment emission helpers --
def _params(**kwargs: int) -> "tuple[tuple[str, int], ...]":
    return tuple(sorted((str(k), int(v)) for k, v in kwargs.items()))


def emit_atom(stream: list, kind: str, **params: int) -> None:
    """Append one atom. Called from a BODY fragment."""
    stream.append(Atom(kind=str(kind), params=_params(**params)))


def emit_node(stream: list, node: Node) -> None:
    """Append a whole prebuilt substructure (a `template`)."""
    stream.append(node)


def emit_open(stream: list, tag: int, kind: str, *, reducer: str = "", **params: int) -> None:
    """Open a nested scope. `kind` is ``sequence``/``parallel``/``repeat``."""
    stream.append(Marker(tag=int(tag), opening=True, kind=str(kind),
                         params=_params(**params), reducer=str(reducer)))


def emit_close(stream: list, tag: int) -> None:
    """Close the scope opened with the same `tag`."""
    stream.append(Marker(tag=int(tag), opening=False))


#: Named substructures a `FW_Group` sheet can drop in whole. Templates are seed
#: atoms for the engine to compose — not hand-written final candidates.
_TEMPLATES: "Mapping[str, Node]" = {
    # Both templates are monotone non-decreasing maps, so neither can create an
    # ordering violation on its own: any contract failure the smoke reports is
    # attributable to the *composition*, not to a template.
    "normalize": Sequence_((Atom("offset", _params(k=3)),
                            Atom("clamp", _params(low=-40, high=40)))),
    "spread": Sequence_((Atom("scale", _params(k=3)),
                         Atom("offset", _params(k=-5)),
                         Atom("clamp", _params(low=-28, high=28)))),
    "guard": Atom("drop_below", _params(threshold=0)),
    "compact": Atom("dedupe"),
}


def template(name: str) -> Node:
    try:
        return _TEMPLATES[name]
    except KeyError:
        raise PipelineError(f"unknown template {name!r}; known: {sorted(_TEMPLATES)}")


# ------------------------------------------------------------ stream parsing --
def parse_topology(stream: "Sequence[StreamItem]") -> Node:
    """Build the highest-order *complete* structure in `stream`.

    Core legitimately re-emits helper sheets outside the brace that wove them,
    so the stream can contain an unclosed frame or an immediately-closed empty
    scope. Both are debris: they are dropped rather than failing the candidate.
    Among the completed non-empty roots the deepest one wins, ties broken by
    position, which makes the selection a pure function of the stream.
    """
    roots: "list[Node]" = []
    stack: "list[tuple[Marker, list]]" = []
    for item in stream:
        if isinstance(item, Marker):
            if item.opening:
                stack.append((item, []))
                continue
            # closing marker: unwind to the matching open, discarding debris
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
        raise PipelineError("no complete structure in the candidate stream")
    best = max(range(len(roots)), key=lambda i: (depth(roots[i]), i))
    return roots[best]


def _build_scope(opener: Marker, children: "tuple[Node, ...]") -> Node:
    if not children:
        raise PipelineError(f"{opener.kind!r} scope {opener.tag} closed with no children")
    if opener.kind == "sequence":
        return Sequence_(children)
    if opener.kind == "parallel":
        reducer = opener.reducer or "merge"
        if reducer not in REDUCERS:
            raise PipelineError(f"unknown reducer {reducer!r}; known: {REDUCERS}")
        return Parallel(children, reducer)
    if opener.kind == "repeat":
        count = dict(opener.params).get("count", 2)
        if not 1 <= count <= 8:
            raise PipelineError(f"repeat count {count} outside the bounded range 1..8")
        body = children[0] if len(children) == 1 else Sequence_(children)
        return Repeat(body, int(count))
    raise PipelineError(f"unknown scope kind {opener.kind!r}")


# ----------------------------------------------------- evaluator #1: compiled --
# Lowered to closures once, then folded. Kept deliberately separate from the
# reference interpreter below: the two are the differential oracle, so factoring
# their shared "obvious" logic together would silently delete the check.
def _compile_atom(atom: Atom) -> "Callable[[list, list], list]":
    kind = atom.kind
    if kind == "scale":
        k = atom.param("k")
        return lambda data, ops: [_visit(ops, x * k) for x in data]
    if kind == "offset":
        k = atom.param("k")
        return lambda data, ops: [_visit(ops, x + k) for x in data]
    if kind == "clamp":
        low, high = atom.param("low"), atom.param("high")
        if low > high:
            raise PipelineError(f"clamp low {low} exceeds high {high}")
        return lambda data, ops: [_visit(ops, low if x < low else (high if x > high else x))
                                  for x in data]
    if kind == "drop_below":
        threshold = atom.param("threshold")
        return lambda data, ops: [x for x in data if _visit(ops, x) >= threshold]
    if kind == "dedupe":
        return _compiled_dedupe
    if kind == "sort":
        return lambda data, ops: sorted(_visit(ops, x) for x in data)
    raise PipelineError(f"unknown atom kind {kind!r}; known: {ATOM_KINDS}")


def _visit(ops: list, value: int) -> int:
    ops[0] += 1
    return value


def _compiled_dedupe(data: list, ops: list) -> list:
    seen, out = set(), []
    for x in data:
        _visit(ops, x)
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _compile(node: Node) -> "Callable[[list, list], list]":
    if isinstance(node, Atom):
        return _compile_atom(node)
    if isinstance(node, Sequence_):
        steps = [_compile(child) for child in node.children]

        def run_sequence(data, ops):
            for step in steps:
                data = step(data, ops)
            return data
        return run_sequence
    if isinstance(node, Parallel):
        branches = [_compile(child) for child in node.children]
        reducer = node.reducer

        def run_parallel(data, ops):
            outputs = [branch(list(data), ops) for branch in branches]
            return _merge(outputs, ops) if reducer == "merge" else [x for o in outputs for x in o]
        return run_parallel
    if isinstance(node, Repeat):
        body, count = _compile(node.child), node.count

        def run_repeat(data, ops):
            for _ in range(count):
                data = body(data, ops)
            return data
        return run_repeat
    raise PipelineError(f"unknown node type {type(node).__name__}")


def _merge(outputs: "list[list]", ops: list) -> list:
    """Order-preserving merge: compares heads only, exactly like the merge step
    of a mergesort. It therefore produces a non-decreasing result *iff* every
    input branch is already non-decreasing — the property that makes branch
    order observable instead of silently repaired."""
    cursors = [0] * len(outputs)
    out: list = []
    while True:
        best = -1
        for i, out_i in enumerate(outputs):
            if cursors[i] < len(out_i) and (best < 0 or out_i[cursors[i]] < outputs[best][cursors[best]]):
                best = i
        if best < 0:
            return out
        out.append(_visit(ops, outputs[best][cursors[best]]))
        cursors[best] += 1


def run_compiled(node: Node, data: "Sequence[int]" = CORPUS) -> "tuple[tuple[int, ...], int]":
    """Execute `node` via the compiled path. Returns (output, element visits)."""
    ops = [0]
    return tuple(_compile(node)(list(data), ops)), ops[0]


# ---------------------------------------------------- evaluator #2: reference --
# An independent structural interpreter. No closures, no shared helpers with the
# compiled path, no operation counter — a second opinion, not a refactor.
def reference_eval(node: Node, data: "Sequence[int]" = CORPUS) -> "tuple[int, ...]":
    """Execute `node` by direct recursion. The differential half of the oracle."""
    values = tuple(data)
    if isinstance(node, Atom):
        kind = node.kind
        if kind == "scale":
            k = node.param("k")
            return tuple(v * k for v in values)
        if kind == "offset":
            k = node.param("k")
            return tuple(v + k for v in values)
        if kind == "clamp":
            low, high = node.param("low"), node.param("high")
            if low > high:
                raise PipelineError(f"clamp low {low} exceeds high {high}")
            return tuple(max(low, min(high, v)) for v in values)
        if kind == "drop_below":
            threshold = node.param("threshold")
            return tuple(v for v in values if not v < threshold)
        if kind == "dedupe":
            out: "list[int]" = []
            for v in values:
                if v not in out:
                    out.append(v)
            return tuple(out)
        if kind == "sort":
            return tuple(sorted(values))
        raise PipelineError(f"unknown atom kind {kind!r}; known: {ATOM_KINDS}")
    if isinstance(node, Sequence_):
        for child in node.children:
            values = reference_eval(child, values)
        return values
    if isinstance(node, Parallel):
        branch_outputs = [reference_eval(child, values) for child in node.children]
        if node.reducer == "concat":
            return tuple(v for branch in branch_outputs for v in branch)
        if node.reducer != "merge":
            raise PipelineError(f"unknown reducer {node.reducer!r}; known: {REDUCERS}")
        # Same specification as _merge, expressed as a repeated minimum-head pick
        # over remaining suffixes rather than an index cursor walk.
        remaining = [list(branch) for branch in branch_outputs]
        merged: "list[int]" = []
        while any(remaining):
            live = [i for i, branch in enumerate(remaining) if branch]
            pick = min(live, key=lambda i: remaining[i][0])
            merged.append(remaining[pick].pop(0))
        return tuple(merged)
    if isinstance(node, Repeat):
        for _ in range(node.count):
            values = reference_eval(node.child, values)
        return values
    raise PipelineError(f"unknown node type {type(node).__name__}")


# ------------------------------------------------- evaluator #3: structural ----
def max_output_length(node: Node, n: int) -> int:
    """Upper bound on the output length, computed from the structure alone.

    Sound because every atom in :data:`ATOM_KINDS` is non-expanding: pointwise
    maps and ``sort`` preserve length, ``dedupe``/``drop_below`` can only shrink
    it. Nothing is executed, so this is genuinely independent evidence rather
    than a second reading of the same run.
    """
    if isinstance(node, Atom):
        return n
    if isinstance(node, Sequence_):
        for child in node.children:
            n = max_output_length(child, n)
        return n
    if isinstance(node, Parallel):
        return sum(max_output_length(child, n) for child in node.children)
    if isinstance(node, Repeat):
        for _ in range(node.count):
            n = max_output_length(node.child, n)
        return n
    raise PipelineError(f"unknown node type {type(node).__name__}")


def depth(node: Node) -> int:
    if isinstance(node, Atom):
        return 1
    if isinstance(node, Sequence_) or isinstance(node, Parallel):
        return 1 + max((depth(child) for child in node.children), default=0)
    if isinstance(node, Repeat):
        return 1 + depth(node.child)
    raise PipelineError(f"unknown node type {type(node).__name__}")


def atom_count(node: Node) -> int:
    if isinstance(node, Atom):
        return 1
    if isinstance(node, Sequence_) or isinstance(node, Parallel):
        return sum(atom_count(child) for child in node.children)
    if isinstance(node, Repeat):
        return node.count * atom_count(node.child)
    raise PipelineError(f"unknown node type {type(node).__name__}")


def topology_stats(node: Node) -> "dict[str, int]":
    return {"stages": atom_count(node), "depth": depth(node),
            "branches": _branch_count(node)}


def _branch_count(node: Node) -> int:
    if isinstance(node, Atom):
        return 0
    if isinstance(node, Parallel):
        return len(node.children) + sum(_branch_count(c) for c in node.children)
    if isinstance(node, Sequence_):
        return sum(_branch_count(c) for c in node.children)
    if isinstance(node, Repeat):
        return _branch_count(node.child)
    raise PipelineError(f"unknown node type {type(node).__name__}")


# ------------------------------------------------------- the service contract --
def contract_violation(output: "Sequence[int]") -> str:
    """Exact domain verdict: the stable reason this record stream violates the
    declared contract, or ``""`` when it satisfies it."""
    if not output:
        return "empty_output"
    for previous, current in zip(output, output[1:]):
        if current < previous:
            return "not_non_decreasing"
    for value in output:
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
        """One whitespace-separated ``K=V`` record. Every value is a finite
        integer with a declared direction, and the reason is a stable token —
        never free text that could be mistaken for a measurement."""
        return (f"app=engine_demo stages={self.stages} depth={self.depth} "
                f"branches={self.branches} ops={self.ops} retained={self.retained} "
                f"reason={self.reason or 'ok'} FW_VAR={self.code}")


def evaluate(stream: "Sequence[StreamItem]", data: "Sequence[int]" = CORPUS) -> Result:
    """Build, execute and judge one candidate. Never raises: every failure mode
    becomes a classified verdict so the Executor's outcome taxonomy stays
    meaningful (a construction defect is not a domain answer)."""
    try:
        node = parse_topology(stream)
        stats = topology_stats(node)
    except PipelineError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc))
    try:
        compiled, ops = run_compiled(node, data)
        referenced = reference_eval(node, data)
        bound = max_output_length(node, len(data))
    except PipelineError as exc:
        return Result(code=VERDICT_CONSTRUCTION, reason=_token(exc), **stats)
    except Exception as exc:                                    # noqa: BLE001
        return Result(code=VERDICT_RUNTIME, reason=_token(exc), **stats)
    if compiled != referenced:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason="differential_mismatch",
                      ops=ops, retained=len(compiled), **stats)
    if len(compiled) > bound:
        return Result(code=VERDICT_ORACLE_DISAGREEMENT, reason="length_bound_exceeded",
                      ops=ops, retained=len(compiled), **stats)
    violation = contract_violation(compiled)
    code = VERDICT_CONTRACT if violation else VERDICT_PASS
    return Result(code=code, reason=violation, ops=ops, retained=len(compiled), **stats)


def _token(exc: Exception) -> str:
    """Collapse an exception into a stable, whitespace-free reason token so the
    metrics line stays parseable."""
    return type(exc).__name__.lower()
