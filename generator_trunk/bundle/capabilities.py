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

"""The one declarative capability registry.

Which operator-visible combinations the Bundle supports was previously encoded
only as a sequence of `if` statements inside `stages.preflight` (plus a couple in
`cli._run`), restated by hand in several documents, and re-asserted independently
by each GUI's option list. Three copies of one truth drift, and the audit found
exactly that: a UI offering profiles the engine cannot resolve.

This module is the single source. Everything else is generated from it:

* ``bundle_run.py capabilities --json`` — the machine-readable matrix;
* ``--markdown`` — the human support table in the documentation;
* preflight acceptance/rejection, with a **stable reason code** per refusal;
* CI case definitions (every `SUPPORTED` row names the test that proves it);
* doctor diagnostics and GUI option availability (`available_values`).

Design rules this file follows, all of them consequences of the same principle
— the matrix must not be able to claim more than the engine does:

1. **Unknown combinations fail closed.** `classify` returns `UNSUPPORTED` for an
   unrecognized dimension value rather than assuming it is fine.
2. **Every `SUPPORTED` row references real evidence.** A test asserts that each
   `evidence` id resolves to a test that exists.
3. **A rule's reason is the operator-facing message.** Preflight raises the
   rule's own text, so the matrix and the error cannot disagree.
4. **Documentation is an output.** Nothing here is scraped from a document.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

from .policy import PROFILES

SCHEMA = "bundle.capability-matrix/v1"

SUPPORTED = "SUPPORTED"
EXPERIMENTAL = "EXPERIMENTAL"
UNSUPPORTED = "UNSUPPORTED"
LEVELS = (SUPPORTED, EXPERIMENTAL, UNSUPPORTED)


@dataclass(frozen=True)
class Dimension:
    """One operator-visible axis of a run."""

    id: str
    title: str
    values: "tuple[str, ...]"
    description: str
    default: str = ""
    enumerated: bool = True      # False -> not expanded into the matrix product

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "values": list(self.values),
                "description": self.description, "default": self.default,
                "enumerated": self.enumerated}


#: Every operator-visible dimension. `values` for the numeric axes are the
#: *equivalence classes* that change behaviour (K=1 vs K>1), not every integer:
#: enumerating 1..64 pool sizes would add rows without adding information.
DIMENSIONS: "tuple[Dimension, ...]" = (
    Dimension("language", "Candidate language", ("python", "java"),
              "Which Executor runs the candidates.", "python"),
    Dimension("candidate_sink", "Candidate transport", ("loose-files", "sharded", "grpc"),
              "How the Reader delivers candidates to the Executor.", "loose-files"),
    Dimension("handoff", "Handoff contract", ("v2", "legacy"),
              "bundle.handoff/v2 manifest, or the legacy file handshake.", "v2"),
    Dimension("run_mode", "Run mode", ("verdict", "stress"),
              "Per-candidate verdict, or the py_stress combinatorial storm.", "verdict"),
    Dimension("execution_policy", "Execution policy profile",
              ("generated-default", "networked-api-probe", "trusted-local"),
              "The sandbox/resource/network rules candidates run under. No default: a run "
              "refuses until one is chosen.", ""),
    Dimension("executor_pool", "Executor pool", ("single", "multi"),
              "One Executor process, or N members owning one Reader directory each.", "single"),
    Dimension("repeat", "Repeat count", ("k1", "k_gt_1"),
              "K=1, or K>1 repeated measurement of each candidate.", "k1"),
    Dimension("analyzer", "Analyzer", ("none", "formal", "exploratory"),
              "No analysis, a formal declared-objective front, or exploratory auto-discovery.",
              "none"),
    # Contextual axes are validated and classified for real runs, but are not
    # multiplied into the compact published product.  "Not enumerated" must
    # never mean "ignored" -- normalize() handles every dimension below.
    Dimension("network_mode", "Candidate network", ("disabled", "allowlist", "unrestricted"),
              "Derived from the execution policy, not chosen independently.", "", enumerated=False),
    Dimension("repeat_policy", "Repeat policy", ("local", "disperse", "nested"),
              "Only `local` is launcher-executable; the others are plan-only seams.",
              "local", enumerated=False),
    Dimension("repeat_scope", "Repeat scope", ("all", "metrics"),
              "Full verdicts per repeat, or one verdict plus metric-only re-measurements.",
              "metrics", enumerated=False),
    Dimension("repeat_environments", "Repeat environments", ("inactive", "configured"),
              "Whether an explicit environment count is configured for a nested repeat plan.",
              "inactive", enumerated=False),
    Dimension("lifecycle", "Lifecycle verb", ("run", "resume", "cancel", "cleanup"),
              "The run/lifecycle operation being requested.", "run", enumerated=False),
    Dimension("entrypoint", "Entry point", ("direct", "gateway"),
              "The local CLI, or the multi-tenant evaluation gateway.", "direct", enumerated=False),
)

DIMENSIONS_BY_ID: "Mapping[str, Dimension]" = {d.id: d for d in DIMENSIONS}
ENUMERATED = tuple(d for d in DIMENSIONS if d.enumerated)


@dataclass(frozen=True)
class Rule:
    """One structural constraint, with the message preflight actually raises."""

    code: str                         # stable reason code
    level: str                        # UNSUPPORTED or EXPERIMENTAL
    title: str
    reason: str                       # the operator-facing message
    applies: "Callable[[Mapping[str, str]], bool]"
    requires: "tuple[str, ...]" = ()          # backend/artifact prerequisites
    security_boundary: str = ""
    evidence: "tuple[str, ...]" = ()          # test ids that prove the behaviour
    since: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "level": self.level, "title": self.title,
                "reason": self.reason, "requires": list(self.requires),
                "security_boundary": self.security_boundary,
                "evidence": list(self.evidence), "since": self.since}


def _lang(s: Mapping) -> str:
    return s.get("language", "")


#: Structural constraints, in evaluation order. Each mirrors a condition that
#: `stages.preflight` / `cli._run` enforced independently before this registry
#: existed; `test_bundle_capabilities.py` characterizes that equivalence.
RULES: "tuple[Rule, ...]" = (
    # ---- policy-derived context -------------------------------------------
    Rule("POLICY_NETWORK_MODE_MISMATCH", UNSUPPORTED,
         "Network mode must match the selected execution policy",
         "network_mode is derived from execution_policy and cannot be overridden independently",
         lambda s: bool(s["execution_policy"] and s["network_mode"])
         and s["network_mode"] != PROFILES[s["execution_policy"]].network.value,
         evidence=("test_bundle_capabilities.py",), since="2026-07-31"),
    # ---- executor pool -----------------------------------------------------
    Rule("POOL_REQUIRES_JAVA", UNSUPPORTED, "Executor pool requires Java candidates",
         "executor_pool_size>1 requires Java candidates (--lang java): py_executor's "
         "manifest gate accepts exactly one source directory",
         lambda s: s["executor_pool"] == "multi" and _lang(s) != "java",
         requires=("Java Executor fat jar",), evidence=("test_bundle_capabilities.py",),
         since="2026-07-04"),
    Rule("POOL_REQUIRES_LOOSE_FILES", UNSUPPORTED, "Executor pool requires loose files",
         "executor_pool_size>1 requires the loose-files transport: the pool assigns one Reader "
         "round-robin directory per member; sharded/grpc pooling is a different mechanism "
         "(shard splitter / gRPC target pool) and is not implemented",
         lambda s: s["executor_pool"] == "multi" and s["candidate_sink"] != "loose-files",
         evidence=("test_bundle_capabilities.py",), since="2026-07-04"),
    Rule("POOL_REQUIRES_VERDICT", UNSUPPORTED, "Executor pool cannot run stress mode",
         "executor_pool_size>1 cannot run --mode stress",
         lambda s: s["executor_pool"] == "multi" and s["run_mode"] == "stress",
         evidence=("test_bundle_capabilities.py",), since="2026-07-04"),
    Rule("POOL_REQUIRES_HANDOFF_V2", UNSUPPORTED, "Executor pool requires Handoff v2",
         "executor_pool_size>1 requires the Handoff v2 flow (--legacy-handoff has no declared "
         "source list for members to own)",
         lambda s: s["executor_pool"] == "multi" and s["handoff"] != "v2",
         evidence=("test_bundle_capabilities.py",), since="2026-07-04"),
    Rule("POOL_INCOMPATIBLE_WITH_REPEAT", UNSUPPORTED, "Executor pool is incompatible with K>1",
         "executor_pool_size>1 with repeat_each_candidate>1 is not supported: K>1 is the "
         "in-executor single-host path; multi-env repeat campaigns are the Java "
         "BundleControlPlane's dispatch job (see CONTROL_PLANE_SEAM.md)",
         lambda s: s["executor_pool"] == "multi" and s["repeat"] != "k1",
         evidence=("test_bundle_capabilities.py",), since="2026-07-04"),
    # ---- live gRPC candidate transport -------------------------------------
    Rule("GRPC_REQUIRES_JAVA", UNSUPPORTED, "Live gRPC transport requires Java candidates",
         "candidate_sink=grpc requires Java candidates (--lang java): the gRPC ingestion server "
         "lives in the Java Executor (MainWatch -grpcPort)",
         lambda s: s["candidate_sink"] == "grpc" and _lang(s) != "java",
         requires=("Java Executor fat jar",), evidence=("test_bundle_grpc_bind.py",),
         since="2026-07-03"),
    Rule("GRPC_REQUIRES_VERDICT", UNSUPPORTED, "Live gRPC transport cannot run stress mode",
         "candidate_sink=grpc cannot run --mode stress: py_stress reads loose candidate files, "
         "which a grpc run never writes",
         lambda s: s["candidate_sink"] == "grpc" and s["run_mode"] == "stress",
         evidence=("test_bundle_grpc_bind.py",), since="2026-07-03"),
    Rule("GRPC_REQUIRES_HANDOFF_V2", UNSUPPORTED, "Live gRPC transport requires Handoff v2",
         "candidate_sink=grpc requires the Handoff v2 flow; --legacy-handoff is not supported "
         "with the live stream transport",
         lambda s: s["candidate_sink"] == "grpc" and s["handoff"] != "v2",
         evidence=("test_bundle_grpc_bind.py",), since="2026-07-03"),
    Rule("GRPC_REQUIRES_TRUSTED_LOCAL", UNSUPPORTED,
         "Live gRPC transport requires the trusted-local profile",
         "candidate_sink=grpc currently requires --execution-policy-profile trusted-local: the "
         "live-feed Executor starts before the Reader (no manifest/policy document at launch) and "
         "runs under the explicit -Dfw.exec.trusted=true opt-in; container-sandboxed gRPC "
         "ingestion is not supported yet",
         lambda s: (s["candidate_sink"] == "grpc"
                    and s["execution_policy"] not in (UNDECIDED, "trusted-local")),
         security_boundary="unsandboxed host execution; loopback-only, plaintext, unauthenticated",
         evidence=("test_bundle_grpc_bind.py", "test_bundle_execution_safety.py"),
         since="2026-07-03"),
    # ---- Java routing ------------------------------------------------------
    Rule("JAVA_REQUIRES_VERDICT", UNSUPPORTED, "Java candidates cannot run stress mode",
         "Java candidates cannot use --mode stress: py_stress is Python-specific; use "
         "--mode verdict so the Handoff is routed to the Java Executor",
         lambda s: _lang(s) == "java" and s["run_mode"] == "stress",
         evidence=("test_bundle_java_routing.py",), since="2026-06-11"),
    Rule("JAVA_REQUIRES_HANDOFF_V2", UNSUPPORTED, "Java candidates require Handoff v2",
         "Java candidates require Handoff v2; --legacy-handoff cannot provide the manifest "
         "language/count needed by the Java Executor",
         lambda s: _lang(s) == "java" and s["handoff"] != "v2",
         evidence=("test_bundle_java_routing.py",), since="2026-06-11"),
    # ---- stress mode -------------------------------------------------------
    Rule("STRESS_HAS_NO_ANALYZER", UNSUPPORTED, "Stress mode produces no Analyzer corpus",
         "--mode stress does not emit the per-candidate K=V metrics corpus the Analyzer "
         "consumes; use --mode verdict for an analysed run",
         lambda s: s["run_mode"] == "stress" and s["analyzer"] != "none",
         evidence=("test_bundle_capabilities.py",), since="2026-06-11"),
    # ---- repeat launcher boundary -----------------------------------------
    Rule("REPEAT_REQUIRES_HANDOFF_V2", UNSUPPORTED,
         "K>1 requires Handoff v2",
         "repeat_each_candidate>1 requires Handoff v2; the legacy handoff cannot carry the "
         "repeat manifest",
         lambda s: s["repeat"] == "k_gt_1" and s["handoff"] != "v2",
         evidence=("test_bundle_repeat_runtime.py",), since="2026-07-01"),
    Rule("REPEAT_POLICY_NOT_LAUNCHER_EXECUTABLE", UNSUPPORTED,
         "K>1 is executable only under the local repeat policy",
         "repeat_each_candidate>1 is executable only with repeat_policy=local; disperse and "
         "nested are planning/control-plane seams, not launcher runtime paths",
         lambda s: s["repeat"] == "k_gt_1" and s["repeat_policy"] != "local",
         evidence=("test_bundle_repeat_runtime.py",), since="2026-07-01"),
    Rule("NESTED_REPEAT_REQUIRES_ENVIRONMENTS", UNSUPPORTED,
         "Nested K>1 requires an explicit environment count",
         "repeat_policy=nested with repeat_each_candidate>1 requires "
         "repeat_environments>=1; refusing to under-budget the environment multiplier",
         lambda s: (s["repeat"] == "k_gt_1" and s["repeat_policy"] == "nested"
                    and s["repeat_environments"] != "configured"),
         evidence=("test_bundle_config.py",), since="2026-07-01"),
    # ---- experimental surfaces --------------------------------------------
    Rule("GRPC_EXPERIMENTAL", EXPERIMENTAL, "Live gRPC transport is experimental",
         "The live Reader->Executor candidate stream is a specialized path: Java + verdict + "
         "Handoff v2 + trusted-local only, loopback-only, plaintext and unauthenticated. It is "
         "not a remote transport and not a security boundary.",
         lambda s: s["candidate_sink"] == "grpc",
         requires=("Java Executor fat jar", "loopback bind host"),
         security_boundary="local trusted host only",
         evidence=("test_bundle_grpc_bind.py",), since="2026-07-03"),
    Rule("POOL_EXPERIMENTAL", EXPERIMENTAL, "Executor pool is experimental",
         "The Java Executor pool is a v1 single-host mechanism: Java + loose files + Handoff v2 "
         "+ verdict + K=1 only.",
         lambda s: s["executor_pool"] == "multi",
         requires=("Java Executor fat jar",), evidence=("test_bundle_capabilities.py",),
         since="2026-07-04"),
    Rule("LEGACY_HANDOFF_EXPERIMENTAL", EXPERIMENTAL, "Legacy handoff is a compatibility path",
         "The legacy file handshake is retained for pre-v2 consumers. It carries no manifest, so "
         "language/count cross-checks and resume reuse are weaker.",
         lambda s: s["handoff"] == "legacy",
         evidence=("test_bundle_handoff.py",), since="2026-06-11"),
    Rule("TRUSTED_LOCAL_UNSANDBOXED", EXPERIMENTAL, "trusted-local has no isolation boundary",
         "trusted-local executes candidates on the host with full filesystem, network and "
         "environment access. It requires an explicit origin classification and a recorded "
         "reason, and is refused for generated, imported or network-facing origins.",
         lambda s: s["execution_policy"] == "trusted-local",
         security_boundary="none - reviewed code only",
         evidence=("test_bundle_execution_safety.py",), since="2026-07-31"),
    Rule("REPEAT_LOCAL_ONLY", EXPERIMENTAL, "K>1 is launcher-executable for the local policy only",
         "K>1 runs under repeat_policy=local. disperse/nested exist as Java BundleControlPlane "
         "planning seams and are refused by the launcher.",
         lambda s: s["repeat"] != "k1" and s["repeat_policy"] == "local",
         evidence=("test_bundle_repeat_runtime.py",), since="2026-07-01"),
    Rule("GATEWAY_EXPERIMENTAL", EXPERIMENTAL, "Gateway entry is experimental",
         "The gateway is a bounded evaluation surface, not a compatibility-equivalent "
         "replacement for the direct local CLI.",
         lambda s: s["entrypoint"] == "gateway",
         evidence=("test_bundle_gateway.py",), since="2026-07-31"),
)

RULES_BY_CODE: "Mapping[str, Rule]" = {r.code: r for r in RULES}


@dataclass(frozen=True)
class Verdict:
    """The classification of one combination."""

    level: str
    codes: "tuple[str, ...]" = ()
    reasons: "tuple[str, ...]" = ()
    requires: "tuple[str, ...]" = ()
    security_boundary: str = ""
    evidence: "tuple[str, ...]" = ()
    selection: "Mapping[str, str]" = field(default_factory=dict)

    @property
    def blocking_code(self) -> str:
        """The first UNSUPPORTED code, or '' when the combination is runnable."""
        for code in self.codes:
            if RULES_BY_CODE[code].level == UNSUPPORTED:
                return code
        return ""

    def to_dict(self) -> dict:
        return {"level": self.level, "codes": list(self.codes), "reasons": list(self.reasons),
                "requires": list(self.requires), "security_boundary": self.security_boundary,
                "evidence": list(self.evidence), "selection": dict(self.selection)}


class UnknownDimensionValue(ValueError):
    """A selection named a dimension value the registry does not define."""


#: A dimension with no default has not been decided yet. Only `execution_policy`
#: is like this, deliberately (audit F1: there is no default execution policy).
#: Preflight runs before the policy is resolved, so it must be able to classify
#: the structural dimensions without inventing one — and a rule that depends on
#: the policy simply does not fire while it is undecided. The run is refused a
#: moment later by `policy.authorize_execution`, with a better message than a
#: capability rule could give.
UNDECIDED = ""


def normalize(selection: Mapping) -> "dict[str, str]":
    """Fill defaults and validate *every* dimension.

    Contextual/non-enumerated axes are still part of the runtime contract.  The
    earlier implementation looped over ``ENUMERATED`` and therefore silently
    discarded bogus repeat/lifecycle/entrypoint values.  Unknown dimension
    names now fail too; otherwise a misspelled safety-relevant key looks valid.
    """
    unknown = set(selection) - set(DIMENSIONS_BY_ID)
    if unknown:
        raise UnknownDimensionValue(f"unknown capability dimension(s): {sorted(unknown)}")
    out: "dict[str, str]" = {}
    for dimension in DIMENSIONS:
        if dimension.id == "network_mode" and dimension.id not in selection:
            policy_name = out.get("execution_policy", UNDECIDED)
            raw = (PROFILES[policy_name].network.value if policy_name else UNDECIDED)
        else:
            raw = selection.get(dimension.id, dimension.default)
        value = str(raw if raw is not None else "").strip()
        if not value:
            value = dimension.default
        if value == UNDECIDED and not dimension.default:
            out[dimension.id] = UNDECIDED          # not chosen yet; see UNDECIDED
            continue
        if value not in dimension.values:
            raise UnknownDimensionValue(
                f"unknown {dimension.id}={value!r}; known values: {list(dimension.values)}")
        out[dimension.id] = value
    return out


def classify(selection: Mapping) -> Verdict:
    """Classify one combination as SUPPORTED, EXPERIMENTAL or UNSUPPORTED.

    An unknown dimension value raises rather than being classified — the matrix
    must never imply that a value it has never heard of is acceptable.
    """
    resolved = normalize(selection)
    codes, reasons, requires, evidence, boundary = [], [], [], [], ""
    for rule in RULES:
        if not rule.applies(resolved):
            continue
        codes.append(rule.code)
        reasons.append(rule.reason)
        requires.extend(rule.requires)
        evidence.extend(rule.evidence)
        if rule.security_boundary and not boundary:
            boundary = rule.security_boundary
    if any(RULES_BY_CODE[c].level == UNSUPPORTED for c in codes):
        level = UNSUPPORTED
    elif codes:
        level = EXPERIMENTAL
    else:
        level = SUPPORTED
    if level == SUPPORTED:
        evidence = list(BASELINE_EVIDENCE)
    return Verdict(level=level, codes=tuple(codes), reasons=tuple(reasons),
                   requires=tuple(dict.fromkeys(requires)), security_boundary=boundary,
                   evidence=tuple(dict.fromkeys(evidence)), selection=resolved)


#: Tests that prove the ordinary, fully-supported path end to end. Every
#: SUPPORTED row cites these, so no row can claim support with no evidence.
BASELINE_EVIDENCE = ("engine_demo/test_engine_demo.py", "test_bundle_runs.py",
                     "test_bundle_counts.py")


# ------------------------------------------------------------------ matrix ---
def iter_selections() -> "Iterable[dict[str, str]]":
    """Every compact product row, completed with validated contextual defaults."""
    ids = [d.id for d in ENUMERATED]
    for combo in itertools.product(*[d.values for d in ENUMERATED]):
        yield normalize(dict(zip(ids, combo)))


def capability_matrix() -> dict:
    """The versioned matrix: dimensions, rules and every classified combination.

    Deterministic for a given source revision, so a checked-in golden fixture or
    a CI freshness check can compare byte-for-byte.
    """
    rows = [classify(selection).to_dict() for selection in iter_selections()]
    counts = {level: sum(1 for r in rows if r["level"] == level) for level in LEVELS}
    return {
        "schema": SCHEMA,
        "dimensions": [d.to_dict() for d in DIMENSIONS],
        "rules": [r.to_dict() for r in RULES],
        "baseline_evidence": list(BASELINE_EVIDENCE),
        "counts": counts,
        "combinations": rows,
        "notes": [
            "Unknown dimension values are refused, not classified: the matrix never implies that "
            "a value it does not define is acceptable.",
            "Numeric axes are enumerated as behaviour-changing equivalence classes (K=1 vs K>1, "
            "single vs multi pool), not as every integer.",
            "EXPERIMENTAL means runnable but narrow or without a migration guarantee. It is not a "
            "weaker form of UNSUPPORTED: an UNSUPPORTED row is refused before any side effect.",
            "A finite matrix over these dimensions says nothing about arbitrary SUT, plugin or "
            "scenario combinations.",
        ],
    }


def available_values(dimension_id: str, selection: Mapping) -> "list[dict]":
    """For a GUI: each value of *dimension_id* with whether it is selectable in
    the context of *selection*, and if not, why.

    This is what stops a UI from offering something the engine will refuse — the
    failure mode the audit found in Face 1 New.
    """
    dimension = DIMENSIONS_BY_ID[dimension_id]
    out = []
    for value in dimension.values:
        probe = dict(selection)
        if dimension_id == "execution_policy":
            # network_mode is derived from the profile.  A normalized current
            # selection contains the old derived value; retaining it while
            # probing another profile would manufacture a mismatch.
            probe.pop("network_mode", None)
        probe[dimension_id] = value
        try:
            verdict = classify(probe)
        except UnknownDimensionValue as exc:
            out.append({"value": value, "level": UNSUPPORTED, "enabled": False,
                        "reason": str(exc), "code": "UNKNOWN_VALUE"})
            continue
        blocking = verdict.blocking_code
        out.append({
            "value": value,
            "level": verdict.level,
            "enabled": verdict.level != UNSUPPORTED,
            "code": blocking,
            "reason": (RULES_BY_CODE[blocking].reason if blocking else ""),
        })
    return out


def ci_cases() -> "list[dict]":
    """One CI case per SUPPORTED/EXPERIMENTAL combination, with the evidence that
    must cover it. Consumed by the release pipeline to check that no supported
    row is untested."""
    cases = []
    for selection in iter_selections():
        verdict = classify(selection)
        if verdict.level == UNSUPPORTED:
            continue
        cases.append({
            "id": "-".join(f"{k}={v}" for k, v in sorted(selection.items())),
            "level": verdict.level,
            "selection": dict(selection),
            "evidence": list(verdict.evidence),
            "requires": list(verdict.requires),
        })
    return cases


# ------------------------------------------------------------- rendering -----
def format_matrix_markdown(matrix: "dict | None" = None) -> str:
    """The human support table. Generated — never hand-maintained.

    Only the runnable rows and the rule table are rendered: printing all
    UNSUPPORTED combinations would be a wall of noise whose information content
    is entirely in the rules.
    """
    matrix = matrix or capability_matrix()
    counts = matrix["counts"]
    lines = [
        "<!-- GENERATED by `bundle_run.py capabilities --markdown`. Do not edit by hand. -->",
        "# Supported capability matrix",
        "",
        f"Schema `{matrix['schema']}`. "
        f"{counts[SUPPORTED]} supported, {counts[EXPERIMENTAL]} experimental, "
        f"{counts[UNSUPPORTED]} unsupported "
        f"of {sum(counts.values())} enumerated combinations.",
        "",
        "## Dimensions",
        "",
        "| Dimension | Values | Default | Description |",
        "|---|---|---|---|",
    ]
    for dimension in matrix["dimensions"]:
        default = f"`{dimension['default']}`" if dimension["default"] else "_none_"
        marker = "" if dimension["enumerated"] else " _(not enumerated)_"
        lines.append(f"| **{dimension['title']}**{marker} | "
                     f"{', '.join('`' + v + '`' for v in dimension['values'])} | {default} | "
                     f"{dimension['description']} |")

    lines += ["", "## Rules", "",
              "| Code | Level | Constraint | Required | Security boundary | Since |",
              "|---|---|---|---|---|---|"]
    for rule in matrix["rules"]:
        lines.append(
            f"| `{rule['code']}` | {rule['level']} | {rule['title']} | "
            f"{', '.join(rule['requires']) or '—'} | {rule['security_boundary'] or '—'} | "
            f"{rule['since'] or '—'} |")

    lines += ["", "## Runnable combinations", "",
              "| Language | Transport | Handoff | Mode | Policy | Pool | Repeat | Analyzer | Level | Notes |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for row in matrix["combinations"]:
        if row["level"] == UNSUPPORTED:
            continue
        s = row["selection"]
        notes = ", ".join(f"`{c}`" for c in row["codes"]) or "—"
        lines.append(
            f"| {s['language']} | {s['candidate_sink']} | {s['handoff']} | {s['run_mode']} | "
            f"{s['execution_policy']} | {s['executor_pool']} | {s['repeat']} | {s['analyzer']} | "
            f"{row['level']} | {notes} |")

    lines += ["", "## Interpretation limits", ""]
    lines += [f"- {note}" for note in matrix["notes"]]
    lines.append("")
    return "\n".join(lines)


def format_matrix_text(matrix: "dict | None" = None) -> str:
    """Concise terminal rendering."""
    matrix = matrix or capability_matrix()
    counts = matrix["counts"]
    lines = [f"capability matrix {matrix['schema']}",
             f"  dimensions: {len(matrix['dimensions'])}  rules: {len(matrix['rules'])}",
             f"  combinations: {sum(counts.values())} "
             f"({counts[SUPPORTED]} supported, {counts[EXPERIMENTAL]} experimental, "
             f"{counts[UNSUPPORTED]} unsupported)"]
    for rule in matrix["rules"]:
        lines.append(f"  [{rule['level']:<12}] {rule['code']:<32} {rule['title']}")
    return "\n".join(lines)
