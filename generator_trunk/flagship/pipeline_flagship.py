"""Flagship SUT: a mutable record-pipeline executor with versioned defects.

The question this flagship answers is **not** "can the engine generate many
rows". It is: *does advanced combinatorial construction find defects that
credible alternative construction methods miss, on the same SUT, with the same
oracle and the same budget?*

The SUT under test is the **compiled evaluator** in
`engine_demo/record_pipeline.py`. This module supplies three versions of it —
one correct, two defective — and the oracle is the *independently written
recursive interpreter* plus the exact service contract. The oracle is therefore
genuinely independent of the thing it judges: a mutant changes the compiled
path only, so nothing can mark its own homework.

Two defects, chosen for what they demonstrate rather than for being easy:

``single_fault``
    ``clamp`` writes ``high - 1`` instead of ``high`` when clamping. Any candidate
    whose data actually exceeds an upper bound exposes it — a single-factor
    property. This is the control: a defect every credible method should find.
    (An earlier form of this mutant used an off-by-one in the *condition*
    (``x > high + 1``); on this corpus no value ever equals ``high + 1``, so it
    was unreachable and every method scored a false MISS. An undetectable mutant
    measures nothing, so it was replaced.)

``interaction_only``
    ``dedupe`` keys on ``abs(x)`` instead of ``x``. Harmless until a stream
    contains both ``+v`` and ``-v``, which requires a negation stage **and** a
    parallel merge that brings both signs together **and** a dedupe after them.
    No single factor exposes it. This is the fault class the Bundle exists to
    find, and the one flat construction misses.

Both are real programming mistakes, not markers planted to be detected.
"""
from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from generator_trunk.engine_demo import record_pipeline as rp

SUT_REVISION = "flagship-pipeline/v1"
ORACLE_REVISION = "differential+contract/v1"

# The outcome taxonomy, the version vocabulary, the suite generators and the
# scoring loop are domain-neutral and live in the control plane. They are
# re-exported here so this study's own call sites and documented commands stay
# unchanged, and so a second study never has to import this one to obtain them.
from generator_trunk.bundle.study import (                         # noqa: F401
    BROKEN, candidate_hash, CORRECT, DOMAIN_FAIL, INFRA_FAIL, INTERACTION_ONLY,
    PASS, SINGLE_FAULT, TIMEOUT, Verdict, VERSIONS,
    cartesian_suite as _cartesian_suite, evaluate_suite as _evaluate_suite,
    format_random_report, ofat_structural_suite as _ofat_structural_suite,
    pairwise_suite as _pairwise_suite, random_suite as _random_suite,
    threewise_suite as _threewise_suite, twise_suite as _twise_suite,
)
from generator_trunk.bundle import study as _study


# --------------------------------------------------------------- the SUT ----
def _mutant_clamp(atom: rp.Atom):
    """single_fault: `>` instead of `>=` at the upper bound — an off-by-one that
    lets one value through unclamped when it exactly equals the bound."""
    low, high = atom.param("low"), atom.param("high")

    def run(data, ops):
        out = []
        for x in data:
            rp._visit(ops, x)
            if x < low:
                out.append(low)
            elif x > high:
                out.append(high - 1)     # BUG: should be `high`
            else:
                out.append(x)
        return out
    return run


def _mutant_dedupe(data, ops):
    """interaction_only: keys on abs(x). Identical to correct dedupe until a
    stream holds both +v and -v, which needs negation AND a merge AND a dedupe
    after them."""
    seen, out = set(), []
    for x in data:
        rp._visit(ops, x)
        key = abs(x)                     # BUG: should be `x`
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def compiled_evaluator(version: str) -> Callable:
    """Return the compiled evaluator for *version*.

    Only the COMPILED path is mutated. `record_pipeline.reference_eval` — the
    oracle — is untouched, so a mutant cannot hide behind an oracle that shares
    its defect.
    """
    if version not in VERSIONS:
        raise ValueError(f"unknown SUT version {version!r}; known: {VERSIONS}")
    original = rp._compile_atom

    def patched(atom: rp.Atom):
        if version == SINGLE_FAULT and atom.kind == "clamp":
            return _mutant_clamp(atom)
        if version == INTERACTION_ONLY and atom.kind == "dedupe":
            return _mutant_dedupe
        return original(atom)
    return patched


def run_under(version: str, node, data: "Sequence[int]" = rp.CORPUS):
    """Execute *node* under the selected SUT version. Deterministic; no state
    survives the call, so every candidate starts from the same baseline."""
    import contextlib
    saved = rp._compile_atom
    rp._compile_atom = compiled_evaluator(version)
    try:
        return rp.run_compiled(node, data)
    finally:
        rp._compile_atom = saved


#: Environment variable the Bundle-generated candidates read to select the SUT
#: version. One scenario therefore serves all three versions, which is what makes
#: the three runs comparable: nothing but this variable differs between them.
SUT_VERSION_ENV = "FLAGSHIP_SUT_VERSION"


def selected_version() -> str:
    """The SUT version for this process, from the environment.

    Defaults to `correct` deliberately: a misconfigured run tests the *control*
    and reports no detections, rather than silently reporting a mutant's failures
    as if they came from the shipped code.
    """
    import os
    version = os.environ.get(SUT_VERSION_ENV, CORRECT).strip() or CORRECT
    if version not in VERSIONS:
        raise ValueError(f"{SUT_VERSION_ENV}={version!r} is not one of {VERSIONS}")
    return version


def evaluate_stream_under(stream, version: "str | None" = None,
                          data: "Sequence[int]" = rp.CORPUS) -> "rp.Result":
    """Build, execute and judge a Bundle-emitted marker stream under a SUT version.

    This is the entry point the **real engine chain** calls: a candidate assembled
    by Core and delivered by the Reader ends in a fragment that calls this and
    reports `FW_VAR = result.code`. It reuses `record_pipeline.evaluate` unchanged,
    so the Bundle-native run and the in-process baseline study share one parser,
    one executor and one oracle — a difference between the two chains is then a
    real difference, not two implementations disagreeing.
    """
    saved = rp._compile_atom
    rp._compile_atom = compiled_evaluator(version or selected_version())
    try:
        return rp.evaluate(stream, data)
    finally:
        rp._compile_atom = saved


# ------------------------------------------------------------- the oracle ---
def _signature(node) -> str:
    """The structural features present, as a stable sorted token string. This is
    what lets a detection be attributed to a minimal combination rather than to
    'something in this candidate'."""
    features = set()

    def walk(n):
        if isinstance(n, rp.Atom):
            features.add(f"atom:{n.kind}")
            if n.kind == "scale" and dict(n.params).get("k", 0) < 0:
                features.add("negation")
        elif isinstance(n, rp.Parallel):
            features.add(f"parallel:{n.reducer}")
            for c in n.children:
                walk(c)
        elif isinstance(n, rp.Sequence_):
            for c in n.children:
                walk(c)
        elif isinstance(n, rp.Repeat):
            features.add("repeat")
            walk(n.child)
    walk(node)
    return ",".join(sorted(features))


def judge(node, version: str, data: "Sequence[int]" = rp.CORPUS) -> Verdict:
    """Exact oracle. Independent of the mutated compiled path in two ways:

    1. **differential** — the untouched reference interpreter recomputes the
       result and must agree;
    2. **contract** — the declared service contract decides the domain question.

    A disagreement is a DEFECT DETECTION, never a domain answer, and infrastructure
    failure is never reported as a discovered defect.
    """
    try:
        stats = rp.topology_stats(node)
    except rp.PipelineError as exc:
        return Verdict(BROKEN, rp._token(exc), False)
    try:
        produced, ops = run_under(version, node, data)
    except rp.PipelineError as exc:
        return Verdict(BROKEN, rp._token(exc), False, **stats)
    except Exception as exc:                                   # noqa: BLE001
        return Verdict(INFRA_FAIL, rp._token(exc), False, **stats)
    try:
        expected = rp.reference_eval(node, data)               # the oracle
    except Exception as exc:                                   # noqa: BLE001
        return Verdict(INFRA_FAIL, f"oracle_{rp._token(exc)}", False, **stats)

    if produced != expected:
        return Verdict(DOMAIN_FAIL, "differential_mismatch", True,
                       defect_signature=_signature(node), ops=ops,
                       retained=len(produced), **stats)
    if len(produced) > rp.max_output_length(node, len(data)):
        return Verdict(DOMAIN_FAIL, "length_bound_exceeded", True,
                       defect_signature=_signature(node), ops=ops,
                       retained=len(produced), **stats)
    violation = rp.contract_violation(produced)
    if violation:
        # A contract violation the reference ALSO produces is the pipeline's own
        # declared behaviour, not a SUT defect. Keeping these apart is what stops
        # a baseline from scoring domain rejections as defect discoveries.
        return Verdict(DOMAIN_FAIL, violation, False, ops=ops,
                       retained=len(produced), **stats)
    return Verdict(PASS, "", False, ops=ops, retained=len(produced), **stats)


# ------------------------------------------------ candidate identity --------

# ------------------------------------------------------------- baselines ----
# The same raw factors every method draws from. Keeping this single declaration
# is what makes the comparison fair: no method gets a richer vocabulary.
FACTORS: "Mapping[str, tuple]" = {
    # --- value axes -------------------------------------------------------
    "module": ("normalize", "spread"),      # FW_Group: a recombined prior result
    "first": ("sort", "negate"),            # FW_PermutR position 1
    "second": ("sort", "negate"),           # FW_PermutR position 2
    "side": ("guard", "compact"),           # the brace's second operand
    "final": ("compact", "clip"),           # the trailing stage
    # --- STRUCTURAL axes --------------------------------------------------
    # These change the SHAPE of the candidate, not just a value in it. Every
    # construction method gets them, so no method is handicapped by being denied
    # structure it could in principle express.
    "reducer": ("merge", "concat"),         # how the brace joins its operands
    "fault": ("absent", "present"),         # FW_Optional: a sudden duplicate-batch event
    "nesting": ("flat", "repeated"),        # FW_Repeat around the joined result
}

# Built through `record_pipeline._params` — the same normalizer the engine-side
# `emit_atom` uses. Param tuples are part of a node's identity (`repr` feeds
# `candidate_hash`), so hand-writing them in a different key order would make two
# structurally identical trees compare unequal and silently break Part F.
_ATOMS = {
    "sort": rp.Atom("sort"),
    "negate": rp.Atom("scale", rp._params(k=-1)),
    "guard": rp.Atom("drop_below", rp._params(threshold=0)),
    "compact": rp.Atom("dedupe"),
    "clip": rp.Atom("clamp", rp._params(low=-30, high=30)),
}


#: The optional "sudden action": a transient duplicate-batch event, modelled as a
#: repeat of the guard branch. It is the FW_Optional axis — present or absent.
_FAULT = rp.Repeat(rp.Atom("drop_below", rp._params(threshold=-99)), 2)


def build(assignment: Mapping) -> rp.Sequence_:
    """Assemble one pipeline from a factor assignment, including its STRUCTURE.

    Every construction method calls this, so a difference in results is a
    difference in which assignments were *chosen*, never in how they were built.
    Structural factors change the shape here, so a method that can select them
    can reach the shapes — this is deliberately not rigged against the baselines.

    The tree built here is **byte-identical** to the one the real engine assembles
    in `bundle_native/scenario.toml` for the same assignment. That is deliberate:
    Part F reconciles the two chains candidate-for-candidate, which is only
    meaningful if both produce the same structures. Scope tags in the comment
    below are the brace tags in that scenario.
    """
    inner_children = [rp.template(assignment["module"]),          # tag 1: SEQ
                      _ATOMS[assignment["first"]],
                      _ATOMS[assignment["second"]]]
    if assignment.get("fault", "absent") == "present":
        inner_children.append(_FAULT)                             # tag 5: FW_Optional
    inner = rp.Sequence_(tuple(inner_children))
    joined = rp.Parallel((inner, _ATOMS[assignment["side"]]),     # tag 2: PAR
                         assignment.get("reducer", "merge"))
    # tag 4: the nesting scope is always present; only its KIND varies. A
    # single-child `sequence` is semantically transparent, so `flat` really is
    # the unnested pipeline — but the engine still emits a scope there, and the
    # two chains must agree on the tree, not merely on the behaviour.
    nested = (rp.Repeat(joined, 2) if assignment.get("nesting", "flat") == "repeated"
              else rp.Sequence_((joined,)))
    return rp.Sequence_((nested, _ATOMS[assignment["final"]]))    # tag 3: ROOT


def manual_suite() -> "list[dict]":
    """What an experienced engineer writes by hand: the happy path, each stage
    exercised once, the two orderings they think of, and — because this engineer
    knows the system — one case per structural axis.

    Deliberately not strawman-bad. Denying this baseline the structural axes would
    guarantee it loses on the interaction defect, and a rigged loss is worth
    nothing. It gets every axis; what it does not get is *systematic* coverage of
    their combinations, which is the actual difference under study.
    """
    return [
        {"module": "normalize", "first": "sort", "second": "sort",
         "side": "guard", "final": "compact"},
        {"module": "spread", "first": "sort", "second": "sort",
         "side": "guard", "final": "clip"},
        {"module": "normalize", "first": "negate", "second": "sort",
         "side": "guard", "final": "clip"},
        {"module": "normalize", "first": "sort", "second": "negate",
         "side": "compact", "final": "compact"},
        {"module": "spread", "first": "sort", "second": "sort",
         "side": "compact", "final": "clip"},
        {"module": "spread", "first": "negate", "second": "negate",
         "side": "guard", "final": "compact"},
        # the structural cases a knowledgeable engineer adds by hand
        {"module": "normalize", "first": "sort", "second": "negate",
         "side": "guard", "final": "compact", "reducer": "concat"},
        {"module": "normalize", "first": "sort", "second": "sort",
         "side": "guard", "final": "compact", "fault": "present"},
        {"module": "spread", "first": "negate", "second": "sort",
         "side": "compact", "final": "clip", "nesting": "repeated"},
    ]








def ofat_nodes() -> "list":
    """One-factor-at-a-time: each stage exercised in isolation, plus each module.

    This is the genuinely FLAT baseline and the one the comparison needs. The
    other three all call `build()`, so they inherit the composed structure —
    parallel merge, ordered motif, trailing stage — and differ only in which
    VALUES they assign. A conventional non-combinatorial suite does not compose
    at all, and cannot express a defect that only exists in the composition.
    """
    nodes = [rp.Sequence_((atom,)) for atom in _ATOMS.values()]
    nodes += [rp.Sequence_((rp.template(m),)) for m in FACTORS["module"]]
    return nodes




# ------------------------------------- this study's bindings of the harness ---
# Thin wrappers that supply THIS study's factor space, builder and oracle. The
# harness itself takes all four explicitly; defaulting them here is a convenience
# for the record-pipeline study, not a property of the machinery.
def cartesian_suite(factors: "Mapping | None" = None):
    return _cartesian_suite(factors or FACTORS)


def twise_suite(factors: "Mapping | None" = None, t: int = 2):
    return _twise_suite(factors or FACTORS, t)


def pairwise_suite(factors: "Mapping | None" = None):
    return _pairwise_suite(factors or FACTORS)


def threewise_suite(factors: "Mapping | None" = None):
    return _threewise_suite(factors or FACTORS)


def ofat_structural_suite(factors: "Mapping | None" = None):
    return _ofat_structural_suite(factors or FACTORS)


def random_suite(factors: "Mapping | None" = None, budget: int = 8, seed: int = 0):
    return _random_suite(factors or FACTORS, budget, seed)


def evaluate_suite(assignments, version: str, builder=None, judge_fn=None) -> dict:
    return _evaluate_suite(assignments, version, builder or build, judge_fn or judge)


def compare(factors: "Mapping | None" = None, builder=None,
            baselines: "Mapping | None" = None, judge_fn=None) -> dict:
    report = _study.compare(factors or FACTORS, builder or build,
                            baselines or BASELINES, judge_fn or judge)
    report.update(sut_revision=SUT_REVISION, oracle_revision=ORACLE_REVISION,
                  corpus=list(rp.CORPUS))
    return report


def format_comparison(report: "dict | None" = None) -> str:
    return _study.format_comparison(report or compare())


def random_baseline_report(factors: "Mapping | None" = None, builder=None,
                           judge_fn=None, budget: int = 0, seeds: int = 50,
                           versions=VERSIONS) -> dict:
    return _study.random_baseline_report(factors or FACTORS, builder or build,
                                         judge_fn or judge, budget, seeds, versions)


#: A baseline is `Callable[[Mapping], list]` — it receives the factor space and
#: returns a suite. The two that ignore it (a fixed hand suite, and the
#: non-composing node list) still accept it, so the harness can call every method
#: the same way. A method that needed a different signature would be a method the
#: comparison could not run identically.
BASELINES: "Mapping[str, Callable[[Mapping], list]]" = {
    "isolated-stages (non-composing)": lambda factors=None: ofat_nodes(),
    "one-factor-at-a-time (composing)": ofat_structural_suite,
    "manual-regression": lambda factors=None: manual_suite(),
    "pairwise-covering-array (t=2)": pairwise_suite,
    "3-way-covering-array (t=3)": threewise_suite,
    "flat-cartesian": cartesian_suite,
}


# --------------------------------------------------------- the comparison ---
