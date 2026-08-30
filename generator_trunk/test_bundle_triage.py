# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev, Ukraine
# See LICENSE and NOTICE.md for the binding terms.

"""Tests for `bundle triage` — the result-analysis stage.

The property under test throughout: a campaign that fails 300 times in 6 ways
must be reported as 6 findings, not 300 failures, and each must carry the
smallest candidate that still shows it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bundle import triage as tri


def _corpus(lines, tmp_path: Path, *, sources=None) -> Path:
    """Materialise a run directory holding a K=V corpus (and optional sources)."""
    run = tmp_path / "runs" / "r1"
    (run / "src").mkdir(parents=True)
    (run / "metrics.kv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name, body in (sources or {}).items():
        (run / "src" / name).write_text(body, encoding="utf-8")
    (run / "executor-summary.json").write_text(
        json.dumps({"processed": len(lines), "outcomes": {"PASS": 0, "DOMAIN_FAIL": 0}}),
        encoding="utf-8")
    return run


def _line(cid, **kv):
    parts = [f"candidate_id={cid}", f"source_ref={cid}.py", "run_id=RUN", "app=t"]
    parts += [f"{k}={v}" for k, v in kv.items()]
    return " ".join(parts)


# ------------------------------------------------------------------ parsing --

def test_parse_reads_provenance_and_verdict(tmp_path):
    run = _corpus([_line("1_0_0", inv="none", FW_VAR=0),
                   _line("2_0_0", inv="I4", FW_VAR=1)], tmp_path)
    recs = tri.parse_metrics(run / "metrics.kv")
    assert [r.candidate_id for r in recs] == ["1_0_0", "2_0_0"]
    assert [r.failed for r in recs] == [False, True]
    assert recs[1].source_ref == "2_0_0.py"


def test_absent_corpus_is_reported_not_silently_clean(tmp_path):
    """An empty corpus must never read as 'no findings'."""
    run = tmp_path / "runs" / "r1"
    (run / "src").mkdir(parents=True)
    data = tri.triage_run(run)
    assert data["findings"] == []
    assert data["corpus"]["records"] == 0
    assert any("metrics.kv" in n and "app=" in n for n in data["notes"]), data["notes"]


# ------------------------------------------------------------ key splitting --

def test_outcome_keys_are_separated_from_declared_axes(tmp_path):
    """A key constant across the PASSING candidates describes an outcome; one
    that varies among them is an input axis the design was balancing."""
    run = _corpus([_line("1_0_0", inv="none", mode="a", FW_VAR=0),
                   _line("2_0_0", inv="none", mode="b", FW_VAR=0),
                   _line("3_0_0", inv="I4", mode="a", FW_VAR=1),
                   _line("4_0_0", inv="I8", mode="b", FW_VAR=1)], tmp_path)
    recs = tri.parse_metrics(run / "metrics.kv")
    classifying, descriptive = tri.classify_keys(recs)
    assert "inv" in classifying and "inv" not in descriptive
    assert "mode" in descriptive and "mode" not in classifying
    assert "app" in classifying          # constant everywhere


# ---------------------------------------------------------------- grouping --

def test_many_failures_collapse_to_few_findings_with_minimal_witnesses(tmp_path):
    """300 failures in 2 ways is 2 findings, and each witness is the smallest
    candidate carrying it."""
    lines, sources = [], {}
    for i in range(150):
        cid = f"a{i}_0_0"
        lines.append(_line(cid, inv="I4", FW_VAR=1))
        sources[f"{cid}.py"] = "x" * (500 + i)          # a0 is the smallest
    for i in range(150):
        cid = f"b{i}_0_0"
        lines.append(_line(cid, inv="I8", FW_VAR=1))
        sources[f"{cid}.py"] = "y" * (900 - i)          # b149 is the smallest
    lines.append(_line("ok_0_0", inv="none", FW_VAR=0))
    sources["ok_0_0.py"] = "z"
    run = _corpus(lines, tmp_path, sources=sources)

    data = tri.triage_run(run)
    assert data["corpus"]["failing"] == 300
    assert len(data["findings"]) == 2, data["findings"]
    assert [f["count"] for f in data["findings"]] == [150, 150]
    by_label = {f["label"]: f for f in data["findings"]}
    assert by_label["app=t inv=I4"]["witness"]["source_ref"] == "a0_0_0.py"
    assert by_label["app=t inv=I8"]["witness"]["source_ref"] == "b149_0_0.py"
    assert sum(f["share"] for f in data["findings"]) == pytest.approx(1.0)


def test_a_rare_finding_survives_a_dominant_one(tmp_path):
    """The needle is the point: one failure in 400 must still get its own row."""
    lines = [_line(f"d{i}_0_0", inv="I8", FW_VAR=1) for i in range(399)]
    lines.append(_line("rare_0_0", inv="I5", FW_VAR=1))
    data = tri.triage_run(_corpus(lines, tmp_path))
    labels = [f["label"] for f in data["findings"]]
    assert "app=t inv=I5" in labels
    rare = next(f for f in data["findings"] if f["label"] == "app=t inv=I5")
    assert rare["count"] == 1 and rare["witness"]["candidate_id"] == "rare_0_0"


# -------------------------------------------------------------- enrichment --

def test_enrichment_lift_points_at_the_responsible_axis(tmp_path):
    """An axis that raises the failure rate must show a lift above 1, and one
    that lowers it below 1. `mode` varies among the passing candidates here, as
    a balanced design's axis does."""
    lines = []
    for i in range(60):
        # mode=bad fails 2/3 of the time, mode=good 1/3 -> base rate 1/2
        bad_fails = i % 3 != 0
        good_fails = i % 3 == 0
        lines.append(_line(f"b{i}_0_0", inv="I4" if bad_fails else "none",
                           mode="bad", FW_VAR=int(bad_fails)))
        lines.append(_line(f"g{i}_0_0", inv="I4" if good_fails else "none",
                           mode="good", FW_VAR=int(good_fails)))
    data = tri.triage_run(_corpus(lines, tmp_path))
    rows = {(r["key"], r["value"]): r for r in data["enrichment"]}
    assert rows[("mode", "bad")]["lift"] > 1.3
    assert rows[("mode", "good")]["lift"] < 0.7
    assert data["enrichment"][0]["key"] == "mode"


def test_a_perfectly_predictive_axis_surfaces_in_the_signature(tmp_path):
    """Known limitation, asserted so it stays known.

    The split between "what went wrong" and "under what conditions" keys on a
    key being constant among the PASSING candidates. An axis that predicts the
    outcome perfectly is also constant there, so it is read as part of the
    failure's identity rather than as enrichment. Nothing is lost -- it appears
    in the finding's label, which is where someone reading the report will see
    it -- but it will not carry a lift number.
    """
    lines = []
    for i in range(30):
        lines.append(_line(f"g{i}_0_0", inv="none", mode="good", FW_VAR=0))
        lines.append(_line(f"b{i}_0_0", inv="I4", mode="bad", FW_VAR=1))
    data = tri.triage_run(_corpus(lines, tmp_path))
    assert "mode" not in {r["key"] for r in data["enrichment"]}
    assert len(data["findings"]) == 1
    assert "mode=bad" in data["findings"][0]["label"]


def test_high_cardinality_detail_is_not_mistaken_for_an_axis(tmp_path):
    """A per-candidate trace takes a new value every time. Every one of its
    values would then show 100% failure on a support of one, which outranks the
    axis that actually explains the run. It must be excluded."""
    lines = []
    for i in range(120):
        failed = i % 3 != 0                       # mode varies among passes
        lines.append(_line(f"c{i}_0_0", inv="I4" if failed else "none",
                           mode="bad" if i % 2 else "good",
                           trace=f"step{i}", FW_VAR=int(failed)))
    data = tri.triage_run(_corpus(lines, tmp_path))
    keys = {r["key"] for r in data["enrichment"]}
    assert "trace" not in keys, "a 120-valued key is witness detail, not an axis"
    assert "mode" in keys


def test_enrichment_ranks_by_explained_share_not_effect_size(tmp_path):
    """A big effect over 4% of the corpus must not outrank a smaller one that
    explains half of it."""
    lines = []
    for i in range(100):
        lines.append(_line(f"w{i}_0_0", inv="I4" if i < 40 else "none",
                           broad="yes" if i < 50 else "no", FW_VAR=1 if i < 40 else 0))
    for i in range(6):                                   # narrow, always fails
        lines.append(_line(f"n{i}_0_0", inv="I9", broad="no", narrow="hit", FW_VAR=1))
    data = tri.triage_run(_corpus(lines, tmp_path))
    top = data["enrichment"][0]
    assert top["key"] == "broad", data["enrichment"][:3]
    assert top["coverage"] > 0.4


# --------------------------------------------------------------------- CLI --

def test_cli_resolves_a_scratch_root_to_its_latest_run(tmp_path):
    from bundle.commands.triage import _resolve_run
    run = _corpus([_line("1_0_0", inv="none", FW_VAR=0)], tmp_path)
    assert _resolve_run(str(run)) == run                  # the run itself
    assert _resolve_run(str(tmp_path)) == run             # a container


def test_cli_rejects_a_path_with_no_run(tmp_path):
    from bundle.commands.triage import _resolve_run
    from bundle.errors import PreflightError
    with pytest.raises(PreflightError):
        _resolve_run(str(tmp_path / "nothing-here"))

def test_a_measurement_does_not_fracture_one_defect_into_many(tmp_path):
    """Regression from a real run: 572 failures of ONE defect were reported as
    four findings because the money lost differed between them.

    A balance or a count is constant across the passing candidates -- the clean
    run always lands on the same number -- so the passing-set test alone reads it
    as part of the failure's identity. It is not. Numeric keys are measurements
    and stay out of the signature; they remain visible on the witness.
    """
    lines = []
    for i in range(20):
        lines.append(_line(f"p{i}_0_0", inv="none", bal=350, shipped=1, FW_VAR=0))
    for i, bal in enumerate((450, 600, 550, 850) * 5):
        lines.append(_line(f"f{i}_0_0", inv="J4+J5", bal=bal, shipped=3, FW_VAR=1))
    data = tri.triage_run(_corpus(lines, tmp_path))

    assert len(data["findings"]) == 1, [f["label"] for f in data["findings"]]
    only = data["findings"][0]
    assert only["count"] == 20
    assert "inv=J4+J5" in only["label"]
    assert "bal" not in only["label"] and "shipped" not in only["label"]
    # the numbers are not lost -- they stay on the witness
    assert "bal" in only["witness"]["detail"]

def test_a_key_that_restates_the_verdict_is_not_reported_as_a_cause(tmp_path):
    """A violation COUNT is non-zero exactly when the candidate failed, so every
    one of its values sits at 0% or 100%. Reporting that as the strongest signal
    in the run is true and useless, and it outranks the axis that does explain
    something. Observed on a real run, where `viol` displaced `pror`.
    """
    lines = []
    for i in range(60):
        fails = i % 3 != 0
        lines.append(_line(f"c{i}_0_0", inv="I4" if fails else "none",
                           viol=1 if fails else 0,                  # restates the verdict
                           mode="bad" if i % 2 else "good",         # a real axis
                           FW_VAR=int(fails)))
    data = tri.triage_run(_corpus(lines, tmp_path))
    keys = {r["key"] for r in data["enrichment"]}
    assert "viol" not in keys, "a key that partitions exactly on pass/fail explains nothing"
    assert "mode" in keys

def test_a_campaign_where_everything_failed_still_reduces(tmp_path):
    """Regression from a real run: 6 failures became 6 findings.

    With no passing candidates there is no set to compare against, and the
    passing-set rule makes every key classifying -- one finding per candidate,
    which is no reduction at all. It happens precisely when a campaign is
    saturated, which is when reduction matters most. The fallback compares
    against the whole corpus instead: a key that never varies describes the
    outcome they share; one that varies is an axis.
    """
    lines = []
    for i, subject in enumerate(("alice", "bob") * 3):
        lines.append(_line(f"f{i}_0_0", inv="A6+A7",          # constant: the shared outcome
                           subject=subject,                    # varies: an axis
                           clauses="mfa|AND|vpn" if i % 3 else "mfa|AND|office",
                           FW_VAR=1))
    data = tri.triage_run(_corpus(lines, tmp_path))
    assert data["corpus"]["failing"] == 6
    assert len(data["findings"]) == 1, [f["label"] for f in data["findings"]]
    only = data["findings"][0]
    assert "inv=A6+A7" in only["label"]
    assert "subject" not in only["label"] and "clauses" not in only["label"]
    assert only["count"] == 6 and only["share"] == 1.0

