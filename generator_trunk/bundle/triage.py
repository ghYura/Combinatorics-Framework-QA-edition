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

"""Result triage: turn a campaign's verdicts into a report.

A large campaign does not fail in many ways. It fails in a few ways, many times
over -- 2,304 failing candidates from a single defect is a pile, not a finding.
This module reduces that pile to the shape a person can act on:

  * **findings** -- failures grouped by what actually distinguishes them, so one
    defect is one row however many candidates carry it;
  * **a minimal witness** per finding -- the simplest candidate that still
    exhibits it, which is what someone will paste into a debugger;
  * **axis enrichment** -- which declared values are over-represented among the
    failures, with the lift that says whether that is signal or just the design's
    own balance.

It reads only what the run already persisted. It never re-executes a candidate:
re-running generated code outside the recorded execution policy would be a
sandbox bypass, and re-firing a stateful candidate produces a different verdict
anyway (the Executor makes the same argument where it harvests metrics).

Inputs, in order of preference:

  ``metrics.kv``      the Executor's own K=V corpus -- one line per candidate,
                      carrying ``candidate_id``/``source_ref``/``run_id``
                      provenance plus whatever the candidate itself reported.
                      This is the rich path, and the only one that can group
                      failures by what the candidate SAYS went wrong.
  ``executor-summary.json``
                      outcome totals, always present. Enough to report counts,
                      not enough to group them.

A candidate contributes a metrics line only when it prints one starting with
``app=`` and containing ``FW_VAR=`` -- the Executor's documented selection rule.
A run whose specs do not follow it yields an empty corpus, and triage says so
plainly rather than reporting "no findings" over no data.
"""
from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "bundle.triage/v1"

#: Keys the Executor prepends for provenance. They identify a candidate; they
#: never describe one, so they take no part in grouping or enrichment.
PROVENANCE_KEYS = frozenset({"candidate_id", "source_ref", "run_id", "repeat_idx", "env_id"})

#: The verdict token every candidate must emit. Non-zero == the oracle fired.
VERDICT_KEY = "FW_VAR"

_KV = re.compile(r"(\w+)=(\S*)")


@dataclass(frozen=True)
class Record:
    """One candidate's reported metrics."""
    candidate_id: str
    source_ref: str
    failed: bool
    fields: "dict[str, str]"


@dataclass
class Finding:
    """One distinct way the campaign failed."""
    signature: "tuple[tuple[str, str], ...]"
    count: int
    members: "list[str]" = field(default_factory=list)
    witness: "Record | None" = None
    witness_bytes: "int | None" = None

    def label(self) -> str:
        return " ".join(f"{k}={v}" for k, v in self.signature) or "(undifferentiated)"


def parse_metrics(path: "str | Path") -> "list[Record]":
    """Parse ``metrics.kv``. Returns [] when the corpus is absent or empty."""
    p = Path(path)
    if not p.is_file():
        return []
    out: "list[Record]" = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        fields = dict(_KV.findall(line))
        cid = fields.get("candidate_id", "")
        if not cid:
            continue
        verdict = fields.get(VERDICT_KEY, "0")
        try:
            failed = int(verdict) != 0
        except ValueError:
            failed = bool(verdict)
        out.append(Record(candidate_id=cid, source_ref=fields.get("source_ref", ""),
                          failed=failed, fields=fields))
    return out


def classify_keys(records: "list[Record]") -> "tuple[list[str], list[str]]":
    """Split reported keys into *classifying* and *descriptive*.

    A combinatorial design is balanced by construction: a declared axis takes
    every one of its values across the corpus, on passing and failing candidates
    alike. A key that describes an OUTCOME does not behave that way -- on the
    passing candidates it is constant (``inv=none``) or absent entirely.

    So: a key whose value never varies among the PASSING candidates is
    classifying (it says what went wrong); everything else is descriptive (it
    says under what conditions). This needs no per-spec configuration and no
    naming convention beyond the verdict itself.

    Returns ``(classifying, descriptive)``, both sorted.
    """
    passing = [r for r in records if not r.failed]
    keys = {k for r in records for k in r.fields} - PROVENANCE_KEYS - {VERDICT_KEY}
    # When EVERY candidate failed there is no passing set to compare against, and
    # the rule below would make every key classifying -- giving one finding per
    # candidate, which is no reduction at all and happens exactly when a campaign
    # is saturated and reduction matters most. Fall back to constancy across the
    # WHOLE corpus: a key that never varies describes the outcome all these
    # candidates share, and one that varies is an axis the design was balancing.
    classifying, descriptive = [], []
    for k in sorted(keys):
        if _is_measurement(k, records):
            descriptive.append(k)
            continue
        if passing:
            is_outcome = len({r.fields.get(k) for r in passing}) <= 1
        else:
            is_outcome = _looks_like_outcome_without_passes(k, records)
        (classifying if is_outcome else descriptive).append(k)
    return classifying, descriptive


def _looks_like_outcome_without_passes(key: str, records: "list[Record]") -> bool:
    """Outcome or axis, when every candidate failed and there is nothing to
    compare against.

    A combinatorial design is BALANCED: an axis takes each of its values in
    roughly the same number of candidates, because that is what the product
    construction does. An outcome is not built that way -- it is either the one
    thing they all share, or it is lopsided, with one failure mode dominating
    and the interesting one carried by a handful.

    So: constant, or unbalanced, means outcome. Balanced means axis. Both halves
    are load-bearing -- constancy alone would bury a rare finding among 399 of
    its dominant sibling, and skew alone would not recognise the single shared
    outcome of a fully saturated run.
    """
    counts = collections.Counter(r.fields.get(key) for r in records
                                 if r.fields.get(key) is not None)
    if len(counts) <= 1:
        return True                                   # the one thing they share
    lo, hi = min(counts.values()), max(counts.values())
    return hi >= lo * _OUTCOME_SKEW                   # lopsided -> outcome


#: How far from balanced a key must be, with no passing candidates to compare
#: against, before it is read as an outcome rather than a declared axis. A clean
#: product is perfectly balanced; a sieve or an uneven slot can tilt it a little,
#: so the threshold is generous.
_OUTCOME_SKEW = 4


def _is_measurement(key: str, records: "list[Record]") -> bool:
    """Is this key a numeric measurement rather than a failure category?

    A balance, a count of shipments, a queue depth: these are constant across the
    passing candidates (the clean run always lands on the same number), so the
    passing-set test alone reads them as part of a failure's identity. They are
    not. Splitting one defect into four findings because the money it lost
    differed is exactly the pile this module exists to remove -- observed on a
    real run, where `inv=J4+J5` fractured into four rows by `bal`.

    A category (`inv=I4+I8`, `trans=none`) is not numeric, so requiring every
    observed value to parse as a number separates the two without naming either.
    """
    values = {r.fields.get(key) for r in records} - {None, ""}
    if not values:
        return False
    for v in values:
        try:
            float(v)
        except ValueError:
            return False
    return True


def group_findings(records: "list[Record]", classifying: "list[str]") -> "list[Finding]":
    """Group failures by their classifying values, most frequent first."""
    buckets: "dict[tuple, list[Record]]" = collections.OrderedDict()
    for r in records:
        if not r.failed:
            continue
        sig = tuple((k, r.fields.get(k, "")) for k in classifying if r.fields.get(k, ""))
        buckets.setdefault(sig, []).append(r)
    findings = [Finding(signature=sig, count=len(rs), members=[x.candidate_id for x in rs])
                for sig, rs in buckets.items()]
    findings.sort(key=lambda f: (-f.count, f.label()))
    return findings


def attach_witnesses(findings: "list[Finding]", records: "list[Record]",
                     src_dir: "str | Path | None") -> None:
    """Pick each finding's minimal witness: the smallest candidate that shows it.

    Smallest means fewest source bytes. The Reader assembles a candidate by
    concatenating the chosen slot values, so a shorter candidate is one that
    selected shorter fragments and fewer optional pieces -- the closest
    generic proxy for "simplest reproduction" without re-parsing the spec.
    Falls back to the first member when the sources are unavailable.
    """
    by_id = {r.candidate_id: r for r in records}
    src = Path(src_dir) if src_dir else None
    for f in findings:
        best, best_size = None, None
        for cid in f.members:
            rec = by_id.get(cid)
            if rec is None:
                continue
            size = None
            if src is not None and rec.source_ref:
                fp = src / rec.source_ref
                if fp.is_file():
                    size = fp.stat().st_size
            if best is None or (size is not None and (best_size is None or size < best_size)):
                best, best_size = rec, size
        f.witness = best
        f.witness_bytes = best_size


#: A declared axis is a slot with a small value list. A key carrying a per-candidate
#: detail -- an operation trace, a running total -- takes a new value almost every
#: time, and every one of its values then has a support of one or two candidates,
#: which cannot evidence anything. Keys above this many distinct values are treated
#: as witness detail and excluded from enrichment (they still appear on witnesses).
MAX_AXIS_VALUES = 24


def axis_enrichment(records: "list[Record]", descriptive: "list[str]",
                    *, max_axis_values: int = MAX_AXIS_VALUES,
                    min_support_fraction: float = 0.01) -> "list[dict]":
    """Per declared value: how often it fails, and the lift over the base rate.

    ``lift`` is P(fail | value) / P(fail). A balanced design puts every value in
    the same number of candidates, so lift is exactly the factor by which
    choosing that value changes the odds of failing: 1.0 is noise, and the
    distance from 1.0 is the signal that points at a responsible axis.

    Only keys that behave like axes are reported -- see ``MAX_AXIS_VALUES``. A
    value also needs enough candidates behind it to mean anything, so rows below
    ``min_support_fraction`` of the corpus are dropped: without that, a trace
    string seen three times at 100% failure outranks the config axis that
    actually explains the campaign.
    """
    total = len(records)
    failures = sum(1 for r in records if r.failed)
    if not total or not failures:
        return []
    base = failures / total
    min_support = max(2, int(total * min_support_fraction))
    rows = []
    for key in descriptive:
        counts: "dict[str, list[int]]" = collections.defaultdict(lambda: [0, 0])
        for r in records:
            v = r.fields.get(key)
            if v is None:
                continue
            counts[v][1] += 1
            if r.failed:
                counts[v][0] += 1
        if len(counts) > max_axis_values:
            continue                       # witness detail, not an axis
        # A key whose every value sits at 0% or 100% restates the verdict rather
        # than explaining it -- a violation COUNT is non-zero exactly when the
        # candidate failed. Reporting it as the strongest signal in the run is
        # true and useless, and it crowds out the axis that does explain things.
        if all(seen and (bad == 0 or bad == seen) for bad, seen in counts.values()):
            continue
        for value, (bad, seen) in sorted(counts.items()):
            if seen < min_support:
                continue
            rate = bad / seen
            lift = rate / base
            # Rank by how much of the corpus an effect explains, not by effect
            # size alone: a value covering a third of the candidates at lift 1.9
            # tells you where to look, while one covering nine candidates at
            # lift 2.5 is a coincidence with a big number attached.
            rows.append({"key": key, "value": value, "failing": bad, "total": seen,
                         "rate": round(rate, 4), "lift": round(lift, 3),
                         "coverage": round(seen / total, 4),
                         "score": round(abs(lift - 1.0) * (seen / total), 4)})
    rows.sort(key=lambda r: (-r["score"], r["key"], r["value"]))
    return rows


def triage_run(run_dir: "str | Path") -> dict:
    """Build the triage report for one run directory."""
    run = Path(run_dir)
    metrics = run / "metrics.kv"
    records = parse_metrics(metrics)

    summary = {}
    sp = run / "executor-summary.json"
    if sp.is_file():
        try:
            summary = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError:
            summary = {}

    notes: "list[str]" = []
    if not records:
        notes.append(
            "no K=V corpus: metrics.kv is absent or empty, so failures cannot be grouped. "
            "A candidate contributes a line only when it prints one starting with 'app=' and "
            "containing 'FW_VAR=' -- check the spec's TAIL slot against that rule.")

    classifying, descriptive = classify_keys(records)
    findings = group_findings(records, classifying)
    attach_witnesses(findings, records, run / "src")
    enrichment = axis_enrichment(records, descriptive)

    failing = sum(1 for r in records if r.failed)
    if records and findings and len(findings) == 1 and not classifying:
        notes.append(
            "every failure shares one signature because the candidates reported nothing that "
            "varies between them; the campaign may be saturated by a single defect, or the "
            "oracle may not be reporting what distinguishes one failure from another.")

    return {
        "schema": SCHEMA,
        "run_id": (records[0].fields.get("run_id") if records else summary.get("run_id", "")) or "",
        "corpus": {"path": str(metrics), "records": len(records),
                   "failing": failing,
                   "outcomes": summary.get("outcomes", {}),
                   "processed": summary.get("processed", len(records))},
        "keys": {"classifying": classifying, "descriptive": descriptive},
        "findings": [
            {"signature": [list(kv) for kv in f.signature],
             "label": f.label(),
             "count": f.count,
             "share": round(f.count / failing, 4) if failing else 0.0,
             "witness": ({"candidate_id": f.witness.candidate_id,
                          "source_ref": f.witness.source_ref,
                          "source_bytes": f.witness_bytes,
                          "detail": {k: v for k, v in f.witness.fields.items()
                                     if k not in PROVENANCE_KEYS}}
                         if f.witness else None)}
            for f in findings],
        "enrichment": enrichment,
        "notes": notes,
    }


def format_report(data: dict, *, top_axes: int = 12) -> str:
    """Human-readable triage report."""
    c = data["corpus"]
    out: "list[str]" = []
    out.append("triage %s" % (data.get("run_id") or "(run id unknown)"))
    out.append("  candidates %s   failing %s   distinct findings %s"
               % (c["records"], c["failing"], len(data["findings"])))
    if c.get("outcomes"):
        out.append("  outcomes   " + "  ".join(f"{k}={v}" for k, v in sorted(c["outcomes"].items()) if v))

    for note in data.get("notes", []):
        out.append("  ! " + note)

    if data["findings"]:
        out.append("")
        out.append("FINDINGS  (one row per distinct failure, most frequent first)")
        for i, f in enumerate(data["findings"], 1):
            out.append("  %d. %-46s %5d candidates  %5.1f%%"
                       % (i, f["label"], f["count"], 100.0 * f["share"]))
            w = f.get("witness")
            if w:
                size = f"{w['source_bytes']}B" if w.get("source_bytes") is not None else "?"
                out.append("     minimal witness  %s  (%s)" % (w["source_ref"] or w["candidate_id"], size))
                detail = {k: v for k, v in (w.get("detail") or {}).items() if k != "FW_VAR"}
                if detail:
                    out.append("     " + "  ".join(f"{k}={v}" for k, v in detail.items())[:200])

    if data["enrichment"]:
        out.append("")
        out.append("AXIS ENRICHMENT  (lift = how much this value changes the odds of failing; "
                   "1.0 = noise. Ranked by how much of the corpus the effect explains.)")
        for row in data["enrichment"][:top_axes]:
            out.append("  %-14s %-24s %4d/%-5d  %5.1f%%  lift %5.2f  covers %4.1f%%"
                       % (row["key"], row["value"][:24], row["failing"], row["total"],
                          100.0 * row["rate"], row["lift"], 100.0 * row["coverage"]))
    return "\n".join(out)
