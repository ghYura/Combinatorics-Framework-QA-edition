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

"""Second flagship SUT: a transactional store with versioned defects.

`pipeline_flagship` asked whether advanced combinatorial construction finds
defects credible alternatives miss. It answered on one SUT. This module asks the
only question that matters next: **does that answer survive a different domain?**

The SUT is `engine_demo/txn_store` — stateful where the record pipeline is pure,
scoped-with-rollback where it composes functions, judged by an invariant plus a
metamorphic relation plus a naive replay where it was judged by a differential.
If the earlier finding were an artefact of pure function composition or of
differential oracles, it should not reproduce here.

Everything else is held fixed on purpose. Same three version names, same baseline
generators, same comparison code, same cost metrics, same factor-space widths.
A difference in results is then a difference in the SUT, which is the variable
under study.

Two defects, chosen to be the same *classes* as SUT 1's so the comparison is
like-for-like, and to be real mistakes rather than planted markers:

``single_fault``
    ``delete`` removes the key from the primary map but leaves it in the
    secondary index. Any candidate that deletes an existing key exposes it —
    a single-factor property, and the most common denormalized-index bug there is.

``interaction_only``
    The copy-on-write ``dirty`` flag is stored per transaction DEPTH instead of
    per transaction ENTRY. A scope re-entered at a depth that already ran once
    inherits the previous entry's flag, skips taking its own snapshot, and rolls
    back to the stale one. Exposing it needs THREE independent things at once:
    a repeated scope (same depth entered twice), a rollback (otherwise nothing is
    restored), and a write between the two entries (otherwise there is nothing to
    lose). No single factor and no pair reaches it.
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

from generator_trunk.bundle import study
from generator_trunk.engine_demo import txn_store as ts

SUT_REVISION = "flagship-txn-store/v1"
ORACLE_REVISION = "invariant+metamorphic+replay+bound/v1"

CORRECT = study.CORRECT
SINGLE_FAULT = study.SINGLE_FAULT
INTERACTION_ONLY = study.INTERACTION_ONLY
VERSIONS = study.VERSIONS

#: Environment variable the Bundle-generated candidates read to select the SUT
#: version, mirroring the first flagship so one runner serves both.
SUT_VERSION_ENV = "FLAGSHIP_SUT_VERSION"


# --------------------------------------------------------------- the SUT ----
def _mutant_delete(store: "ts.Store", op: "ts.Op") -> None:
    """single_fault: drops the key from the map without unindexing it.

    The index then claims a key that no longer exists. Layer 1 of the oracle —
    the coherence invariant — catches it on the very next check.
    """
    key = op.param("key")
    if key in store.data:
        del store.data[key]                       # BUG: no `_unindex(store, key)`


def _mutant_savepoint_enter(state: dict) -> None:
    """interaction_only: keys the copy-on-write flag by DEPTH, not by entry.

    A transaction entered at a depth that has already been used inherits the
    earlier entry's `dirty` flag. Believing it already has a snapshot, it takes
    none — so its rollback restores the *previous* transaction's snapshot and
    discards everything written in between.
    """
    depth = len(state["stack"])
    seen = state.setdefault("by_depth", {})
    if depth in seen:
        state["stack"].append(seen[depth])        # BUG: reuses a foreign entry
        return
    entry = {"snapshot": None, "dirty": False}
    seen[depth] = entry
    state["stack"].append(entry)


def install(version: str) -> "dict[str, object]":
    """Patch in the selected version's defect. Returns the saved originals.

    Only the SUT's own primitives are replaced. The oracle — `index_incoherence`,
    the harness snapshot in `_run`, `effective_ops`, `naive_apply`,
    `max_store_size` — is never touched, so nothing marks its own homework.
    """
    if version not in VERSIONS:
        raise ValueError(f"unknown SUT version {version!r}; known: {VERSIONS}")
    saved = {"delete": ts._OPS["delete"], "enter": ts._savepoint_enter}
    if version == SINGLE_FAULT:
        ts._OPS["delete"] = _mutant_delete
    elif version == INTERACTION_ONLY:
        ts._savepoint_enter = _mutant_savepoint_enter
    return saved


def restore(saved: "Mapping[str, object]") -> None:
    ts._OPS["delete"] = saved["delete"]
    ts._savepoint_enter = saved["enter"]


def selected_version() -> str:
    """The SUT version for this process, from the environment.

    Defaults to `correct`: a misconfigured run tests the control and reports no
    detections, rather than silently attributing a mutant's failures to the
    shipped code.
    """
    import os
    version = os.environ.get(SUT_VERSION_ENV, CORRECT).strip() or CORRECT
    if version not in VERSIONS:
        raise ValueError(f"{SUT_VERSION_ENV}={version!r} is not one of {VERSIONS}")
    return version


def evaluate_stream_under(stream, version: "str | None" = None,
                          initial: "Mapping[int, int]" = ts.INITIAL) -> "ts.Result":
    """Entry point the **real engine chain** calls.

    A candidate assembled by Core and delivered by the Reader ends in a fragment
    that calls this and reports `FW_VAR = result.code`. It reuses `txn_store.evaluate`
    unchanged, so the Bundle-native run and the in-process study share one parser,
    one executor and one oracle.
    """
    saved = install(version or selected_version())
    try:
        return ts.evaluate(stream, initial)
    finally:
        restore(saved)


# ------------------------------------------------------------- the oracle ---
def judge(node, version: str, initial: "Mapping[int, int]" = ts.INITIAL) -> "study.Verdict":
    """Judge one prebuilt node, in the harness's shared outcome taxonomy.

    Returning the harness's own `Verdict` is what lets the two SUTs share one
    comparison implementation — a second copy of the scoring logic would be a
    second place for the two studies to quietly differ. Note what this module does
    NOT import: the record-pipeline study. Two studies meet in the control plane,
    not in each other.
    """
    result = evaluate_stream_under([node], version, initial)
    if result.code == ts.VERDICT_CONSTRUCTION:
        return study.Verdict(study.BROKEN, result.reason, False, stages=result.stages,
                         depth=result.depth, branches=result.branches)
    if result.code == ts.VERDICT_RUNTIME:
        return study.Verdict(study.INFRA_FAIL, result.reason, False, stages=result.stages,
                         depth=result.depth, branches=result.branches)
    common = {"stages": result.stages, "depth": result.depth, "branches": result.branches,
              "ops": result.ops, "retained": result.retained}
    if result.code == ts.VERDICT_ORACLE_DISAGREEMENT:
        return study.Verdict(study.DOMAIN_FAIL, result.reason, True,
                         defect_signature=signature(node), **common)
    if result.code == ts.VERDICT_CONTRACT:
        # The contract is the store's own declared behaviour. Scoring a domain
        # rejection as a defect discovery is the specific way a comparison
        # flatters whichever method generates the most candidates.
        return study.Verdict(study.DOMAIN_FAIL, result.reason, False, **common)
    return study.Verdict(study.PASS, "", False, **common)


def signature(node) -> str:
    """The structural features present, as a stable sorted token string — what
    lets a detection be attributed to a minimal combination."""
    features = set()

    def walk(n):
        if isinstance(n, ts.Op):
            features.add(f"op:{n.kind}")
        elif isinstance(n, ts.Txn):
            features.add("txn:commit" if n.commit else "txn:rollback")
            for child in n.children:
                walk(child)
        elif isinstance(n, ts.Block):
            for child in n.children:
                walk(child)
        elif isinstance(n, ts.Repeat):
            features.add("repeat")
            walk(n.child)
    walk(node)
    return ",".join(sorted(features))


# ------------------------------------------------------------- the factors --
#: The same shape as SUT 1's L2 space — eight binary factors, five of them value
#: axes and three structural — so the two studies are comparable at equal width.
FACTORS: "Mapping[str, tuple]" = {
    # --- value axes -------------------------------------------------------
    "group": ("seed", "shuffle"),           # FW_Group: a recombined prior result
    "first": ("put_a", "bump_a"),           # FW_PermutR position 1
    "second": ("put_a", "bump_a"),          # FW_PermutR position 2
    "side": ("put_b", "read_b"),            # write vs read BETWEEN scope entries
    # `purge` deletes THROUGH the index; `delete_c` goes through the delete path
    # the single-factor mutant lives in. An earlier version had `bump_c` here and
    # no level reached `delete` at all, so every method scored a false MISS on a
    # mutant nothing could execute. Recorded because it is the same unreachable-
    # mutant trap the first flagship hit, caught the second time by running it.
    "final": ("purge", "delete_c"),         # the trailing operation
    # --- STRUCTURAL axes --------------------------------------------------
    "outcome": ("commit", "rollback"),      # brace operand: does the scope survive
    "sudden": ("absent", "present"),        # FW_Optional: a transient burst
    "nesting": ("flat", "repeated"),        # brace operand: same depth entered twice
}

_OPS = {
    "put_a": ts.Op("put", ts._params(key=1, value=9)),
    "bump_a": ts.Op("bump", ts._params(delta=4, key=1)),
    "put_b": ts.Op("put", ts._params(key=3, value=11)),
    # A read must not arm the copy-on-write savepoint. That is what makes "did
    # anything write between the two entries" a genuine third factor rather than
    # a constant, and it is why the interaction defect needs three things at once.
    "read_b": ts.Op("read", ts._params(key=3)),
    "purge": ts.Op("purge", ts._params(value=5)),
    "delete_c": ts.Op("delete", ts._params(key=2)),
    # --- extra levels used only by the WIDE space ---------------------------
    "read_a": ts.Op("read", ts._params(key=1)),
    "delete_b": ts.Op("delete", ts._params(key=3)),
    "bump_c": ts.Op("bump", ts._params(delta=2, key=2)),
}

#: The WIDE space: the same eight axes, three levels on each value axis instead
#: of two. Widening the value axes and leaving the three structural axes binary
#: is deliberate — it is the same manipulation SUT 1's L3 applied, so whatever
#: happens to the sampling methods here is comparable to what happened there.
WIDE_FACTORS: "Mapping[str, tuple]" = {
    "group": ("seed", "shuffle", "trim"),
    "first": ("put_a", "bump_a", "read_a"),
    "second": ("put_a", "bump_a", "read_a"),
    "side": ("put_b", "read_b", "delete_b"),
    "final": ("purge", "delete_c", "bump_c"),
    "outcome": ("commit", "rollback"),
    "sudden": ("absent", "present"),
    "nesting": ("flat", "repeated"),
}


#: The optional "sudden action": a transient double increment inside the
#: transaction. Present or absent — the FW_Optional axis.
_SUDDEN = ts.Repeat(ts.Op("bump", ts._params(delta=1, key=2)), 2)


def build(assignment: Mapping) -> "ts.Block":
    """Assemble one transaction tree from a factor assignment.

    Byte-identical to what the engine assembles in `bundle_native_s2/scenario.toml`
    for the same assignment; scope tags in the comments are that scenario's brace
    tags. Every construction method calls this, so a difference in results is a
    difference in which assignments were *chosen*.
    """
    inner = [ts.bundle(assignment["group"]),                       # tag 1: BLOCK
             _OPS[assignment["first"]],
             _OPS[assignment["second"]]]
    if assignment.get("sudden", "absent") == "present":
        inner.append(_SUDDEN)                                      # FW_Optional
    scope = ts.Txn((ts.Block(tuple(inner)),),                      # tag 2: TXN
                   assignment.get("outcome", "commit") == "commit")
    # The side operation sits INSIDE the repeated scope but OUTSIDE the
    # transaction. That placement is the experiment: it is the write whose loss
    # the stale-snapshot defect causes, and only a repeated scope re-enters the
    # transaction after it.
    body = ts.Block((scope, _OPS[assignment["side"]]))
    nested = (ts.Repeat(body, 2) if assignment.get("nesting", "flat") == "repeated"
              else ts.Block((body,)))                              # tag 4: NEST
    return ts.Block((nested, _OPS[assignment["final"]]))           # tag 3: ROOT


def isolated_nodes() -> "list":
    """The genuinely FLAT baseline: each operation and each group exercised alone,
    with no transaction and no repetition.

    This is the conventional suite. It cannot express a defect that only exists in
    the composition, which is the point of including it.
    """
    nodes = [ts.Block((op,)) for op in _OPS.values()]
    nodes += [ts.Block((ts.bundle(name),)) for name in FACTORS["group"]]
    return nodes


def manual_suite() -> "list[dict]":
    """What an experienced engineer writes by hand: the happy path, each operation
    once, both transaction outcomes, and one case per structural axis.

    Given every axis on purpose. What it is not given is *systematic* coverage of
    their combinations, which is the difference under study.
    """
    return [
        {"group": "seed", "first": "put_a", "second": "put_a",
         "side": "put_b", "final": "purge"},
        {"group": "shuffle", "first": "bump_a", "second": "bump_a",
         "side": "put_b", "final": "delete_c"},
        {"group": "seed", "first": "bump_a", "second": "put_a",
         "side": "read_b", "final": "purge"},
        {"group": "shuffle", "first": "put_a", "second": "bump_a",
         "side": "put_b", "final": "purge", "outcome": "rollback"},
        {"group": "seed", "first": "put_a", "second": "bump_a",
         "side": "read_b", "final": "delete_c", "sudden": "present"},
        {"group": "shuffle", "first": "bump_a", "second": "put_a",
         "side": "put_b", "final": "delete_c", "nesting": "repeated"},
    ]


BASELINES: "Mapping[str, Callable]" = {
    "isolated-operations (non-composing)": lambda *_: isolated_nodes(),
    "one-factor-at-a-time (composing)": lambda factors=FACTORS: study.ofat_structural_suite(factors),
    "manual-regression": lambda *_: manual_suite(),
    "pairwise-covering-array (t=2)": lambda factors=FACTORS: study.pairwise_suite(factors),
    "3-way-covering-array (t=3)": lambda factors=FACTORS: study.threewise_suite(factors),
    "flat-cartesian": lambda factors=FACTORS: study.cartesian_suite(factors),
}


def compare(factors: "Mapping | None" = None, builder=None,
            baselines: "Mapping | None" = None) -> dict:
    """The second SUT's comparison, through the shared harness.

    Reusing `bundle.study` rather than copying it is the point: if the two studies
    disagree, the disagreement is in the SUT and not in how the scoring was done.
    This module imports the harness, never the first study — two studies meet in
    the control plane, not in each other.
    """
    report = study.compare(factors or FACTORS, builder or build,
                           baselines or BASELINES, judge)
    report["sut_revision"] = SUT_REVISION
    report["oracle_revision"] = ORACLE_REVISION
    report["corpus"] = dict(ts.INITIAL)
    return report


def format_comparison(report: "dict | None" = None) -> str:
    return study.format_comparison(report or compare())


def random_baseline_report(factors: "Mapping | None" = None, budget: int = 0,
                           seeds: int = 50) -> dict:
    """Random sampling at the 2-way array's budget, over many seeds."""
    return study.random_baseline_report(factors or FACTORS, build, judge, budget, seeds)
