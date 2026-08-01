"""In-process twins of the Bundle-native flagship levels.

Each level's scenario is authored twice: once as a spec the **engine** executes
(``bundle_native_l*/scenario.toml``) and once as a Python function that builds the
same tree from the same factor assignment. The twin exists for exactly one
purpose — to make the full-chain reconciliation *falsifiable*. Agreeing on a row
count only shows both sides produced the same number of things; agreeing on the
whole multiset of executed measurements shows they produced the same things.

The twin is not a second implementation of the pipeline. It builds nodes and hands
them to the same `record_pipeline` parser, executor and oracle the candidates use,
so a disagreement can only mean the two chains built different structures.

L2 lives in `pipeline_flagship` because the baseline comparison shares its factor
space. L3 and L4 live here.
"""
from __future__ import annotations

import itertools
from typing import Mapping

from generator_trunk.engine_demo import record_pipeline as rp

#: The L3/L4 factor space, mirroring `bundle_native_l3/scenario.toml` sheet for
#: sheet. `motif` is the FW_PermutR axis: ordered, with repetition, so it is
#: enumerated as a product rather than a list of values.
L3_MODULES = ("normalize", "spread", "offset4")
L3_MOTIF_STAGES = ("sort", "negate", "guard0")
L3_SIDES = ("guard", "compact")
L3_REDUCERS = ("merge", "concat")
L3_NESTINGS = ("flat", "repeated")
L3_CLIP_LOW = (-30, 12)
L3_CLIP_HIGH = (30, -12)

_MODULE_NODES = {
    "normalize": rp.template("normalize"),
    "spread": rp.template("spread"),
    "offset4": rp.Atom("offset", rp._params(k=4)),
}
_MOTIF_NODES = {
    "sort": rp.Atom("sort"),
    "negate": rp.Atom("scale", rp._params(k=-1)),
    "guard0": rp.Atom("drop_below", rp._params(threshold=0)),
}
_SIDE_NODES = {"guard": rp.template("guard"), "compact": rp.template("compact")}

_FAULT = rp.Repeat(rp.Atom("drop_below", rp._params(threshold=-99)), 2)
_SURGE = rp.Atom("scale", rp._params(k=2))

#: Motif arity per level — the ONLY difference between the L3 and L4 specs.
MOTIF_ARITY = {"l3": 2, "l4": 3}


def build_l3(assignment: Mapping) -> rp.Sequence_:
    """Assemble one L3/L4 pipeline. Scope tags match the scenario's brace tags."""
    inner = [_MODULE_NODES[assignment["module"]]]                     # tag 1: SEQ
    inner += [_MOTIF_NODES[stage] for stage in assignment["motif"]]
    if assignment["fault"] == "present":
        inner.append(_FAULT)                                          # FW_Optional #1
    joined = rp.Parallel((rp.Sequence_(tuple(inner)),                 # tag 2: PAR
                          _SIDE_NODES[assignment["side"]]), assignment["reducer"])
    nest = [joined]                                                   # tag 4: NEST
    if assignment["surge"] == "present":
        nest.append(_SURGE)                                           # FW_Optional #2
    # `_build_scope` collapses a single-child repeat to the child itself and wraps
    # multiple children in a sequence. The twin must reproduce that, not a tidier
    # equivalent, or two identical pipelines would compare unequal.
    if assignment["nesting"] == "repeated":
        nested = rp.Repeat(nest[0] if len(nest) == 1 else rp.Sequence_(tuple(nest)), 2)
    else:
        nested = rp.Sequence_(tuple(nest))
    final = rp.Atom("clamp", rp._params(low=assignment["clip_low"],
                                        high=assignment["clip_high"]))
    return rp.Sequence_((nested, final))                              # tag 3: ROOT


def sieved(assignment: Mapping) -> bool:
    """True when the constraint sidecar removes this assignment.

    One rule, stated the same way here and in the spec: a clamp whose low exceeds
    its high cannot be constructed. Restating it rather than importing it is
    deliberate — the point is to check that the engine's sieve does what the spec
    *says*, and a shared implementation could not detect a spec that says something
    else.
    """
    return assignment["clip_low"] > assignment["clip_high"]


def l3_suite(level: str = "l3", *, apply_sieve: bool = True) -> "list[dict]":
    """The level's whole factor space, in the engine's own order."""
    arity = MOTIF_ARITY[level]
    space = []
    for module, motif, side, reducer, nesting, low, high, fault, surge in itertools.product(
            L3_MODULES, itertools.product(L3_MOTIF_STAGES, repeat=arity), L3_SIDES,
            L3_REDUCERS, L3_NESTINGS, L3_CLIP_LOW, L3_CLIP_HIGH,
            ("absent", "present"), ("absent", "present")):
        assignment = {"module": module, "motif": motif, "side": side,
                      "reducer": reducer, "nesting": nesting, "clip_low": low,
                      "clip_high": high, "fault": fault, "surge": surge}
        if apply_sieve and sieved(assignment):
            continue
        space.append(assignment)
    return space


# ---------------------------------------------- the same comparison, wider ----
#: The L3 space expressed as flat factors, so the SAME baseline generators run
#: over it. The ordered motif is two positional factors rather than one compound
#: axis: that is how a pairwise tool would actually be handed the problem, and
#: giving the baselines a shape they cannot consume would rig the comparison.
L3_FACTORS = {
    "module": L3_MODULES,
    "motif1": L3_MOTIF_STAGES,
    "motif2": L3_MOTIF_STAGES,
    "side": L3_SIDES,
    "reducer": L3_REDUCERS,
    "nesting": L3_NESTINGS,
    "clip_low": L3_CLIP_LOW,
    "clip_high": L3_CLIP_HIGH,
    "fault": ("absent", "present"),
    "surge": ("absent", "present"),
}


def build_l3_flat(assignment: Mapping) -> rp.Sequence_:
    """`build_l3` for a flat assignment, with the sieve rule applied.

    A method that selects an unconstructible clamp gets an unconstructible
    candidate — the sieve is part of the *engine* path, not a favour extended to
    the baselines. Rather than silently repairing it, the invalid pair is built as
    authored and the oracle classifies it as a construction failure, which is
    exactly what running that candidate would cost in practice.
    """
    return build_l3({**assignment, "motif": (assignment["motif1"], assignment["motif2"])})
