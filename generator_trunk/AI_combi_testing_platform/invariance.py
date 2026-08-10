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

"""Metamorphic verdicts: use the combinatorial design itself as the oracle.

The rest of this platform scores a response against an exact answer, which is
why its task families are ones a solver can settle (`ordering`, `cancellation`).
That is honest, and it is also the ceiling: a target can only be tested on
questions someone can independently answer.

This module removes that constraint. When a space is generated combinatorially
you know, *by construction*, which points must agree — reordering independent
constraints, renaming entities, adding declared-neutral context, or changing the
output serialization cannot change what the answer is. Those are metamorphic
relations, and `FW_Permut`/`FW_Combi` over an invariant axis enumerates the
whole equivalence class for free.

So the verdict becomes a property of a *group*: did every member of this orbit
produce the same answer? No ground truth is required to ask that. A model can be
wrong about every member and still be self-consistent; it can be right about
most and still be fragile. Those are different findings, and only the group
knows which one happened.

Two granularities, both emitted:

* the **joint orbit** — everything that may vary invariantly varies at once.
  This is the real equivalence class and the strongest detector.
* a **per-axis orbit** — one relation varies, everything else is held. Weaker,
  but it *attributes* a violation to the axis that caused it.

What is deliberately NOT invariant is as important as what is. A contradictory
distractor is designed to interfere; a `loaded` semantic mode is designed to
mislead. Including them would manufacture violations that are correct behaviour,
which is the metamorphic-testing failure mode: a relation that is not actually a
relation turns every result into noise.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Mapping

#: Plan fields that define *which question was asked*. Two candidates that
#: differ on any of these are asking different things and are never comparable.
TASK_IDENTITY_FIELDS = (
    "task_family",
    "seed",
    "complexity",
    "adapter_id",
    "prompt_version",
    "semantic_mode",
    "generation_revision",
)


@dataclass(frozen=True)
class InvarianceRelation:
    """A presentation change that must not change the answer."""

    name: str
    axis: str
    #: Values across which the answer must agree. `None` means "any value of
    #: this axis" (used for numeric axes such as neutral filler length).
    invariant_values: tuple[str, ...] | None
    rationale: str

    def holds_for(self, value: Any) -> bool:
        if self.invariant_values is None:
            return True
        return str(value) in self.invariant_values


#: The relations this platform is willing to assert. Each rationale is the
#: argument for why a disagreement is a defect rather than a difference.
RELATIONS: tuple[InvarianceRelation, ...] = (
    InvarianceRelation(
        name="neutral_context",
        axis="long_range",
        invariant_values=None,
        rationale=(
            "Filler notes declare themselves 'descriptive only and add no rule'. "
            "Adding or removing them cannot change a correct answer."
        ),
    ),
    InvarianceRelation(
        name="output_schema",
        axis="schema",
        invariant_values=("json", "plain", "csv"),
        rationale=(
            "json/plain/csv are serializations of the same content; the oracle "
            "parses each back to the same canonical ExactAnswer."
        ),
    ),
    InvarianceRelation(
        name="constraint_order",
        axis="constraint_order",
        invariant_values=("forward", "reverse"),
        rationale=(
            "The task asks for the alphabetically first order satisfying ALL "
            "constraints; a conjunction does not depend on listing order."
        ),
    ),
    InvarianceRelation(
        name="instruction_order",
        axis="instruction_order",
        invariant_values=("task_first", "constraints_first", "mixed"),
        rationale=(
            "Section order changes where the reader meets the task, not what "
            "the task is."
        ),
    ),
    InvarianceRelation(
        name="neutral_distractor",
        axis="distractor",
        invariant_values=("none", "neutral"),
        rationale=(
            "A declared-irrelevant fact adds no rule. 'contradictory' is "
            "excluded: it is designed to interfere, so disagreement there is "
            "not automatically a defect."
        ),
    ),
    InvarianceRelation(
        name="paraphrase",
        axis="paraphrase",
        invariant_values=("direct", "compact"),
        rationale=(
            "Restating the same request more tersely does not change it. "
            "'inverted' is excluded — it restructures the ask, and asserting "
            "invariance there would be an unproven claim about meaning."
        ),
    ),
)

RELATIONS_BY_NAME: Mapping[str, InvarianceRelation] = {r.name: r for r in RELATIONS}

#: Every axis that may vary inside a joint orbit.
INVARIANT_AXES: tuple[str, ...] = tuple(r.axis for r in RELATIONS)

JOINT_RELATION = "joint"


def answer_digest(parsed: Any) -> str:
    """A canonical, serialization-independent digest of a parsed answer.

    Comparison happens on the oracle's `ExactAnswer` (a tuple of identifiers or
    a `Fraction`), never on response text — otherwise every schema change would
    register as a disagreement and the schema relation could never pass.
    """
    if parsed is None:
        return "unparsed"
    if isinstance(parsed, Fraction):
        canonical = f"fraction:{parsed.numerator}/{parsed.denominator}"
    elif isinstance(parsed, (tuple, list)):
        canonical = "sequence:" + "\x1f".join(str(item) for item in parsed)
    else:                                                    # pragma: no cover
        canonical = f"scalar:{parsed}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def lenient_answer(response: str, schema: str) -> Any:
    """Recover the semantic answer from a response the strict parser rejected.

    Measured against a live model: a format-only failure (a stray ``JSON``
    prefix) turned two *substantively different* answers into two `unparsed`
    digests, so the orbit could not compare them and a real invariance
    violation was reported as clean. Format compliance and semantic agreement
    are different findings; letting the stricter one erase the other loses the
    more interesting half.

    This is used **only** for orbit comparison. The oracle's verdict stays
    strict, so a contract breach is still a failure -- it simply no longer
    hides what the model actually said.
    """
    from .oracles.exact import _parse_ordering

    text = (response or "").strip()
    parsed = _parse_ordering(text, schema)
    if parsed is not None:
        return parsed
    # strip common preambles/fences the strict contract forbids
    for line in text.splitlines():
        line = line.strip().strip("`")
        if not line or line.lower() in ("json", "csv", "plain"):
            continue
        for candidate_schema in (schema, "json", "plain", "csv"):
            parsed = _parse_ordering(line, candidate_schema)
            if parsed is not None:
                return parsed
    return None


def _plan_value(plan: Any, field: str) -> str:
    return str(getattr(plan, field, ""))


def orbit_key(plan: Any, task_hash: str, relation: str = JOINT_RELATION) -> str:
    """Identity of everything held fixed for *relation*.

    Members of one orbit differ only in axes the relation permits to vary, so
    they must produce identical answers. The task hash is included explicitly:
    two plans with the same seed but a different generated task are not
    comparable, and silently comparing them would invent violations.
    """
    if relation == JOINT_RELATION:
        varying = set(INVARIANT_AXES)
    else:
        varying = {RELATIONS_BY_NAME[relation].axis}
    parts = [f"relation={relation}", f"task_hash={task_hash}"]
    parts += [f"{f}={_plan_value(plan, f)}" for f in TASK_IDENTITY_FIELDS]
    parts += [
        f"{axis}={_plan_value(plan, axis)}"
        for axis in sorted(set(INVARIANT_AXES) - varying)
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def applicable_relations(plan: Any) -> tuple[str, ...]:
    """Relations whose invariance this plan's own axis values actually assert.

    A plan rendered with a contradictory distractor is outside the
    `neutral_distractor` relation, so it must not be pooled into that orbit.
    """
    names = [
        r.name for r in RELATIONS if r.holds_for(getattr(plan, r.axis, None))
    ]
    if len(names) == len(RELATIONS):
        names.append(JOINT_RELATION)
    return tuple(names)


@dataclass(frozen=True)
class OrbitVerdict:
    """The outcome of one equivalence class."""

    relation: str
    orbit_key: str
    members: int
    distinct_answers: int
    unparsed_members: int
    majority_share: float

    @property
    def consistent(self) -> bool:
        return self.distinct_answers <= 1

    @property
    def status(self) -> str:
        if self.members < 2:
            return "SINGLETON"          # nothing to compare; not evidence
        if self.unparsed_members == self.members:
            return "UNPARSED"
        return "CONSISTENT" if self.consistent else "VIOLATED"


def evaluate_orbits(records: Iterable[Mapping[str, Any]]) -> list[OrbitVerdict]:
    """Group emitted metrics by orbit and decide each equivalence class.

    *records* are dicts carrying at least `orbit_<relation>` keys and
    `answer_digest`, i.e. the dimensions the engine writes for every candidate.
    Unparsed answers are counted but never treated as agreement: a model that
    fails to answer twice has not demonstrated consistency.
    """
    grouped: dict[tuple[str, str], list[str]] = {}
    for record in records:
        digest = str(record.get("answer_digest", "unparsed"))
        for key, value in record.items():
            if not str(key).startswith("orbit_"):
                continue
            relation = str(key)[len("orbit_"):]
            grouped.setdefault((relation, str(value)), []).append(digest)

    verdicts: list[OrbitVerdict] = []
    for (relation, key), digests in sorted(grouped.items()):
        parsed = [d for d in digests if d != "unparsed"]
        distinct = len(set(parsed))
        majority = (
            max((parsed.count(d) for d in set(parsed)), default=0) / len(digests)
            if digests else 0.0
        )
        verdicts.append(OrbitVerdict(
            relation=relation,
            orbit_key=key,
            members=len(digests),
            distinct_answers=distinct,
            unparsed_members=len(digests) - len(parsed),
            majority_share=round(majority, 4),
        ))
    return verdicts


def summarize(verdicts: Iterable[OrbitVerdict]) -> dict[str, Any]:
    """Report shape: per-relation violation rates plus an overall figure.

    `comparable` counts only orbits with at least two members — a singleton
    proves nothing, and folding singletons into the denominator would let a
    sparse run look consistent for free.
    """
    by_relation: dict[str, dict[str, int]] = {}
    for verdict in verdicts:
        bucket = by_relation.setdefault(
            verdict.relation, {"orbits": 0, "comparable": 0, "violated": 0, "singleton": 0})
        bucket["orbits"] += 1
        if verdict.status == "SINGLETON":
            bucket["singleton"] += 1
            continue
        bucket["comparable"] += 1
        if verdict.status == "VIOLATED":
            bucket["violated"] += 1

    relations = {}
    for name, bucket in sorted(by_relation.items()):
        comparable = bucket["comparable"]
        relations[name] = {
            **bucket,
            "violation_rate": (
                round(bucket["violated"] / comparable, 4) if comparable else None),
        }
    total_comparable = sum(b["comparable"] for b in by_relation.values())
    total_violated = sum(b["violated"] for b in by_relation.values())
    return {
        "relations": relations,
        "comparable_orbits": total_comparable,
        "violated_orbits": total_violated,
        "invariance_violation_rate": (
            round(total_violated / total_comparable, 4) if total_comparable else None),
    }
