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

"""Reference-coverage audit — what the engine can compose vs. what each
registered coverage target actually exercises.

The question this answers is deliberately narrow and factual: *does the
application layer expose the engine's composition vocabulary, or does it hide
part of it?* It is answered by parsing real specifications with the same
`fwgen` grammar the Core is verified against — never by reading documentation,
and never by collapsing the answer into a single "power percentage". Each
capability is reported per target as ``EXERCISED`` (this target's specs use it)
or ``UNEXERCISED`` (the engine supports it; this target does
not use it).

Policy restrictions are reported *separately*, as the concrete flags the
application's launcher pins. They are deliberately not folded into a
per-capability "restricted" verdict: which capability a pinned ``--lang`` or a
budget ceiling forecloses is not something the launcher source states, and this
audit may not guess it.

Overhead is reported the same way: separately per phase, measured from the
engine's own stage records, never as one fused number. Nothing here estimates,
extrapolates, or hand-writes a measurement — an unmeasured field stays absent.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from . import architecture as arch
from .stages import fg                       # the verified fwgen grammar/loader

SCHEMA = "bundle.reference-coverage/v1"

EXERCISED = "EXERCISED"
UNEXERCISED = "UNEXERCISED"
RESTRICTED = "RESTRICTED"


@dataclass(frozen=True)
class Capability:
    """One engine composition capability.

    ``tokens`` are the ``FW_`` names this capability owns; a test cross-checks
    that every name in `fwgen`'s grammar is owned by exactly one capability, so
    the registry cannot silently fall behind the engine. ``probe`` is a concrete
    token `fwgen` must accept, so the registry cannot claim a capability the
    engine does not actually parse.
    """

    id: str
    kind: str                       # operator | flag | composition
    order: int                      # 1 = first-order, 2 = second-order, 3 = third-order+
    title: str
    tokens: "tuple[str, ...]"
    probe: str

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "order": self.order, "title": self.title,
                "tokens": list(self.tokens), "probe": self.probe}


CAPABILITIES: "tuple[Capability, ...]" = (
    # --- first order: one axis of freedom over one sheet's values ---
    Capability("operator.combi", "operator", 1, "unordered k-subset without repetition",
               ("FW_Combi",), "FW_Combi(2)"),
    Capability("operator.combi_repetition", "operator", 1, "unordered k-multiset with repetition",
               ("FW_CombiR",), "FW_CombiR(2)"),
    Capability("operator.permut", "operator", 1, "ordered selection without repetition",
               ("FW_Permut",), "FW_Permut(2)"),
    Capability("operator.permut_repetition", "operator", 1, "ordered length-k sequence with repetition",
               ("FW_PermutR",), "FW_PermutR(2)"),
    Capability("operator.subsets", "operator", 1, "powerset over a sheet's values",
               ("FW_Subsets",), "FW_Subsets"),
    Capability("operator.subsets_bounded", "operator", 1, "size-bounded subset families",
               (), "FW_Subsets_RANGE(1,2)"),
    Capability("operator.cartes", "operator", 1, "Cartesian relation to another sheet",
               ("FW_Cartes",), "FW_Cartes(OTHER)"),
    Capability("operator.separator", "operator", 1, "interleave a helper fragment between elements",
               ("FW_Separator",), "FW_Separator(GLUE)"),
    # --- second order: operate on PRIOR RESULT TABLES, not on raw values ---
    Capability("operator.group", "composition", 2,
               "FW_Group: re-combine one prior result's rows as atoms, with FW_ReplaceRE rewrites",
               ("FW_Group",), "FW_Group"),
    Capability("composition.brace", "composition", 2,
               "brace: binary join of two prior result tables",
               (), "FW_(,,A,,B,,,,M:N)"),
    # --- third order and beyond: consume a prior brace result ---
    Capability("composition.brace_nested", "composition", 3,
               "nested FW_(): consume the most recent prior brace result as rows",
               (), "FW_(,,FW_(),,B,,,,M:N)"),
    Capability("composition.brace_nested_grouped", "composition", 3,
               "nested FW_()G: consume the most recent prior brace result in grouped form",
               (), "FW_(,,FW_()G,,B,,,,M:N)"),
    # --- orthogonal structural axes ---
    Capability("flag.optional", "flag", 1, "FW_Optional: presence itself is a degree of freedom",
               ("FW_Optional",), "FW_Optional"),
    Capability("flag.exclude", "flag", 2,
               "FW_Exclude: keep an operand/intermediate out of the final mandatory product",
               ("FW_Exclude",), "FW_Exclude"),
    Capability("flag.reuse", "flag", 2, "FW_Reuse: expose a result table for later composition",
               ("FW_Reuse",), "FW_Reuse"),
    Capability("flag.reuse_table_only", "flag", 2, "FW_ReuseTableOnly: retain the table form",
               ("FW_ReuseTableOnly",), "FW_ReuseTableOnly"),
    Capability("flag.heading", "flag", 1, "FW_Heading: set a sheet aside as a heading",
               ("FW_Heading",), "FW_Heading"),
    Capability("flag.last_in_queue", "flag", 1, "FW_LastInQueue: force a sheet to the end",
               ("FW_LastInQueue",), "FW_LastInQueue"),
    Capability("flag.concatenator", "flag", 1, "FW_Concatenator: override element glue",
               ("FW_Concatenator",), "FW_Concatenator=+"),
)

CAPABILITIES_BY_ID: "Mapping[str, Capability]" = {c.id: c for c in CAPABILITIES}

_BRACE_TOKEN = re.compile(r"FW_\([^)]*\)")
_NESTED_PLAIN = "FW_()"
_NESTED_GROUPED = "FW_()G"


def grammar_tokens() -> "set[str]":
    """Every ``FW_`` name the `fwgen` grammar recognizes, extracted from the
    compiled patterns themselves. The registry is checked against this, so a new
    engine verb cannot be added without the audit noticing."""
    names: "set[str]" = set()
    for pattern in (fg._VERB_RE.pattern, fg._FLAG_RE.pattern):
        names.update(re.findall(r"FW_[A-Za-z_]+", pattern))
    names.add("FW_Group")                    # recognized by is_core_verb, not by _VERB_RE
    return names


# ------------------------------------------------- spec capability detection --
def _verb_capability(verb: str) -> "str | None":
    first = (str(verb).strip().splitlines() or [""])[0].strip()
    if first.startswith("FW_Group"):
        return "operator.group"
    if first.startswith("FW_Subsets_"):
        return "operator.subsets_bounded"
    for cap in CAPABILITIES:
        for token in cap.tokens:
            # Longest-token-first ordering matters: FW_CombiR must not be read
            # as FW_Combi. The registry lists the R-variants first, and an exact
            # prefix match on the remainder settles it.
            if first.startswith(token):
                rest = first[len(token):]
                # "(" -> parameterized verb, "=" -> FW_Concatenator=<glue>,
                # "" -> bare form. Anything else is a longer sibling name
                # (FW_Combi vs FW_CombiR), which the next entry owns.
                if rest[:1] in ("", "(", "="):
                    return cap.id
    return None


def _brace_capabilities(cell: str) -> "set[str]":
    found: "set[str]" = set()
    text = str(cell)
    if not _BRACE_TOKEN.search(text):
        return found
    stripped = text.replace(_NESTED_GROUPED, "").replace(_NESTED_PLAIN, "")
    if _BRACE_TOKEN.search(stripped):
        found.add("composition.brace")
    if _NESTED_GROUPED in text:
        found.add("composition.brace_nested_grouped")
        found.add("composition.brace")
    elif _NESTED_PLAIN in text:
        found.add("composition.brace_nested")
        found.add("composition.brace")
    return found


def spec_capabilities(spec) -> "tuple[set[str], int]":
    """Capabilities a loaded spec exercises, and its maximum composition order.

    The order is derived from the brace chain: a plain brace is second order; a
    brace whose operand is ``FW_()``/``FW_()G`` consumes the previous brace
    result and is therefore one order deeper than it.
    """
    found: "set[str]" = set()
    for slot in spec.slots:
        cap = _verb_capability(slot.verb)
        if cap:
            found.add(cap)
        if getattr(slot, "group_replace", ()):
            found.add("operator.group")
        if getattr(slot, "separator", ""):
            found.add("operator.separator")
        for flag in getattr(slot, "flags", ()) or ():
            cap = _verb_capability(flag)
            if cap:
                found.add(cap)

    order = 1 if found else 0
    if "operator.group" in found:
        order = max(order, 2)
    chain_order = 0
    for row in getattr(spec, "seq_extra", ()) or ():
        for cell in row:
            caps = _brace_capabilities(cell)
            if not caps:
                cap = _verb_capability(cell)
                if cap:
                    found.add(cap)
                continue
            found |= caps
            nested = _NESTED_PLAIN in str(cell) or _NESTED_GROUPED in str(cell)
            chain_order = (chain_order + 1) if (nested and chain_order) else 2
            order = max(order, chain_order)
    return found, order


# --------------------------------------------- launcher policy restrictions --
#: Flags whose pinned value materially restricts what an application lets the
#: engine do. Read from the launcher's own source, in order, via `ast` literals.
_RESTRICTION_FLAGS = {
    "--execution-policy-profile": "execution policy pinned",
    # Phase 02 / audit F1: an unsandboxed run is now an explicit, recorded
    # decision. Surfacing both fields here means a reader of the coverage audit
    # can see WHY a launcher was entitled to trusted-local, not just that it
    # asked for it.
    "--candidate-origin": "candidate origin classification declared",
    "--acknowledge-trusted-local": "unsandboxed execution explicitly acknowledged",
    "--analysis-mode": "Analyzer mode pinned",
    "--candidate-sink": "candidate transport pinned",
    "--lang": "candidate language pinned",
    "--repeat-policy": "repeat policy pinned",
    "--repeat-scope": "repeat scope pinned",
    "--budget-final-candidates": "final-candidate budget ceiling",
    "--budget-mandatory-rows": "mandatory-row budget ceiling",
    "--budget-monetary-cost": "monetary budget ceiling",
    "--budget-requests": "external-request budget ceiling",
}
_RESTRICTION_SWITCHES = {
    "--allow-extreme": "runtime-unknown cardinality explicitly acknowledged",
    "--override-budget": "budget override recorded",
    "--sieve": "constraint sieve forced on",
    "--unleash-initial-productivity-power": "hard budget gates made advisory",
}


def _argument_sequences(tree: ast.AST, source_text: str = "") \
        -> "list[tuple[list[ast.expr], tuple[str, ...]]]":
    """Literal list/tuple sequences a command line could be built from.

    Restricted to the elements of one list/tuple so a flag is only ever paired
    with the element that actually
    follows it in the same command. Walking a flat stream of every string in
    the file instead would happily pair ``--repeat-scope`` with an unrelated
    literal from ten lines away.

    Calls themselves are deliberately *not* sequences: otherwise
    ``parser.add_argument("--budget-requests")`` is misreported as a flag the
    launcher passes to Bundle.  Conditions surrounding a list are carried with
    it so scenario-specific switches are not presented as unconditional.
    """
    sequences: "list[tuple[list[ast.expr], tuple[str, ...]]]" = []

    def visit(node: ast.AST, conditions: "tuple[str, ...]" = ()) -> None:
        if isinstance(node, ast.If):
            expression = (ast.get_source_segment(source_text, node.test)
                          or ast.dump(node.test, include_attributes=False))
            for child in node.body:
                visit(child, conditions + (expression,))
            for child in node.orelse:
                visit(child, conditions + (f"not ({expression})",))
            return
        if isinstance(node, (ast.List, ast.Tuple)):
            sequences.append((list(node.elts), conditions))
        for child in ast.iter_child_nodes(node):
            visit(child, conditions)

    visit(tree)
    return sequences


def launcher_restrictions(launcher: Path) -> "list[dict]":
    """Policy restrictions a launcher imposes, derived from its source.

    Deterministic and evidence-bearing: every entry names the flag, the pinned
    value where there is one, and the source line. When the value is computed at
    runtime rather than written as a literal, ``value`` is empty and
    ``value_kind`` is ``"dynamic"`` — the audit records that the flag is passed
    without inventing what it is set to. A launcher that pins nothing yields an
    empty list.
    """
    if not launcher.is_file():
        return []
    source_text = launcher.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(launcher))
    found: "dict[tuple[str, str, str, str], dict]" = {}
    for elements, conditions in _argument_sequences(tree, source_text):
        presence_kind = "conditional" if conditions else "always"
        condition = " and ".join(conditions)
        for index, element in enumerate(elements):
            if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
                continue
            flag = element.value
            if flag in _RESTRICTION_SWITCHES:
                found.setdefault((flag, "", presence_kind, condition), {
                    "flag": flag, "value": "", "value_kind": "switch",
                    "presence_kind": presence_kind, "condition": condition,
                    "effect": _RESTRICTION_SWITCHES[flag], "line": element.lineno})
                continue
            if flag not in _RESTRICTION_FLAGS:
                continue
            value, kind = "", "dynamic"
            if index + 1 < len(elements):
                following = elements[index + 1]
                if isinstance(following, ast.Constant) and isinstance(following.value, str):
                    value, kind = following.value, "literal"
            # A conditionally appended dynamic value (for example an optional
            # user-supplied budget) is a control the launcher exposes, not a
            # restriction it pins.  Fixed conditional switches/values remain
            # findings, explicitly marked conditional.
            if presence_kind == "conditional" and kind == "dynamic":
                continue
            found.setdefault((flag, value, presence_kind, condition), {
                "flag": flag, "value": value, "value_kind": kind,
                "presence_kind": presence_kind, "condition": condition,
                "effect": _RESTRICTION_FLAGS[flag], "line": element.lineno})
    return sorted(found.values(), key=lambda entry: (
        entry["flag"], entry["value"], entry["presence_kind"], entry["condition"]))


# ------------------------------------------------------------------ report ----
def _app_specs(app: arch.CoverageTarget) -> "list[Path]":
    root = arch.REPO_ROOT / app.root
    paths: "list[Path]" = []
    for pattern in app.spec_globs:
        paths.extend(p for p in root.glob(pattern) if p.is_file())
    return sorted(set(paths))


def application_coverage(app: arch.CoverageTarget,
                         measurement: "Mapping | None" = None) -> dict:
    """Capability coverage, composition depth and policy restrictions for one
    registered coverage target."""
    exercised: "set[str]" = set()
    max_order = 0
    scanned: "list[dict]" = []
    unreadable: "list[dict]" = []
    for path in _app_specs(app):
        try:
            spec = fg.load_spec(path)
        except Exception as exc:                        # noqa: BLE001
            # A spec the engine's own loader rejects is a finding, not something
            # to drop silently from the denominator.
            unreadable.append({"spec": arch.repo_relative(path), "error": type(exc).__name__})
            continue
        caps, order = spec_capabilities(spec)
        exercised |= caps
        max_order = max(max_order, order)
        scanned.append({"spec": arch.repo_relative(path), "capabilities": sorted(caps),
                        "composition_order": order})

    restrictions = launcher_restrictions(arch.REPO_ROOT / app.launcher)
    entry = {
        "id": app.id,
        "title": app.title,
        "role": app.role,
        "status": app.status,
        "root": app.root,
        "launcher": app.launcher,
        "summary": app.summary,
        "specs_scanned": len(scanned),
        "specs_unreadable": unreadable,
        "max_composition_order": max_order,
        "exercised_capabilities": sorted(exercised),
        "unexercised_capabilities": sorted(c.id for c in CAPABILITIES if c.id not in exercised),
        "policy_restrictions": restrictions,
        "specs": scanned,
    }
    if measurement:
        entry["measurement"] = dict(measurement)
    return entry


def measurements_from_benchmark(report: Mapping) -> "dict[str, dict]":
    """Extract per-application measurement blocks from a `bundle.benchmark/v1`
    report so the audit can carry real numbers instead of invented ones.

    Only stages that actually ran contribute: a SKIPPED overhead stage yields no
    measurement block at all, which is why an unmeasured application simply has
    no ``measurement`` key rather than a zero.
    """
    out: "dict[str, dict]" = {}
    for stage in report.get("stages", ()):
        app_id = stage.get("application")
        if not app_id or stage.get("skipped") or not stage.get("phases"):
            continue
        block = {"phases": dict(stage["phases"]),
                 "candidates": stage.get("candidates", 0),
                 "scenario": stage.get("scenario", "")}
        if stage.get("notes"):
            block["notes"] = stage["notes"]
        environment = report.get("environment")
        if environment:
            block["environment"] = {k: environment[k] for k in ("hardware", "os_kernel", "toolchain")
                                    if k in environment}
        out[app_id] = block
    return out


def reference_coverage_report(measurements: "Mapping[str, Mapping] | None" = None) -> dict:
    """The versioned audit. Deterministic for a given source revision: the same
    checkout produces byte-identical JSON."""
    measurements = measurements or {}
    if measurements.get("schema", "").startswith("bundle.benchmark/"):
        measurements = measurements_from_benchmark(measurements)
    return {
        "schema": SCHEMA,
        "engine_revision": arch.engine_revision(),
        "engine_capabilities": [c.to_dict() for c in CAPABILITIES],
        "coverage_targets": [
            application_coverage(app, measurements.get(app.id))
            for app in arch.COVERAGE_TARGETS
        ],
        "notes": [
            "A capability is EXERCISED, UNEXERCISED or RESTRICTED per target; no single "
            "aggregate score is derived, because those three states are not commensurable.",
            "UNEXERCISED means this target does not use the capability. It is not a defect "
            "in the target and not a limit of the engine.",
            "Composition order is measured from the brace chain in the specifications, not "
            "claimed by documentation.",
            "Measurement blocks are present only when a bounded benchmark actually produced "
            "them on this host.",
        ],
    }


def capability_state(entry: Mapping, capability_id: str) -> str:
    """EXERCISED or UNEXERCISED for one capability in one target entry."""
    if capability_id not in CAPABILITIES_BY_ID:
        raise KeyError(f"unknown capability {capability_id!r}")
    return (EXERCISED if capability_id in entry.get("exercised_capabilities", ())
            else UNEXERCISED)


def format_coverage_report(report: dict) -> str:
    """Concise human rendering — the same facts, no aggregate score."""
    caps = report["engine_capabilities"]
    lines = [f"reference coverage {report['schema']}  engine_revision={report['engine_revision']}",
             f"  engine capabilities: {len(caps)} "
             f"(order 1: {sum(1 for c in caps if c['order'] == 1)}, "
             f"order 2: {sum(1 for c in caps if c['order'] == 2)}, "
             f"order 3+: {sum(1 for c in caps if c['order'] >= 3)})"]
    for app in report["coverage_targets"]:
        lines.append(f"  {app['id']}  [{app['role']}; {app['status']}]  "
                     f"specs={app['specs_scanned']}  "
                     f"max_composition_order={app['max_composition_order']}")
        lines.append(f"      exercised   ({len(app['exercised_capabilities'])}): "
                     f"{', '.join(app['exercised_capabilities']) or '-'}")
        lines.append(f"      unexercised ({len(app['unexercised_capabilities'])}): "
                     f"{', '.join(app['unexercised_capabilities']) or '-'}")
        if app["policy_restrictions"]:
            lines.append("      restrictions: " + ", ".join(
                f"{r['flag']}{('=' + r['value']) if r['value'] else ''}"
                f"{' [conditional]' if r['presence_kind'] == 'conditional' else ''}"
                for r in app["policy_restrictions"]))
        if app.get("specs_unreadable"):
            lines.append(f"      ! unreadable specs: {len(app['specs_unreadable'])}")
        if app.get("measurement"):
            phases = app["measurement"].get("phases", {})
            lines.append("      measured phases: " + ", ".join(
                f"{name}={value:.3f}s" for name, value in sorted(phases.items())))
    return "\n".join(lines)
