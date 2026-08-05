#!/usr/bin/env python3
"""Tests for `bundle report` (Face 3): the results-reading surface.

The contract worth protecting is not "it renders" -- it is that the page is
honest about what a run did *not* record. A results view that quietly omits an
unset sandbox backend, an empty Analyzer front, or an interrupted stage would
let a reader mistake "not recorded" for "fine", so each of those is asserted
explicitly below (run: ``python3 -m pytest test_bundle_report.py -q``).
"""
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from bundle.errors import PreflightError
from bundle.report import collect, format_text, render_html, REPORT_SCHEMA


def _write(root: Path, name: str, payload: dict) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def full_run(root: Path) -> Path:
    """A complete, successful run directory with every artifact present."""
    _write(root, "run.json", {
        "schema": "bundle.run/v1", "run_id": "r-full", "status": "SUCCEEDED",
        "spec_path": "usecases/event_order/event_order.toml", "spec_sha256": "a" * 64,
        "db_name": "demo", "mode": "verdict", "goals": "charges:min",
        "start": "2026-08-05T11:00:46Z",
        "settings": {"lang": "py", "analysis_mode": "exploratory",
                     "execution_policy": {"profile": "trusted-local"},
                     "execution_authorization": {"origin": "reviewed-checked-in"}},
    })
    _write(root, "state.json", {"run_id": "r-full", "status": "SUCCEEDED", "stages": {
        "analyzer": {"status": "SUCCEEDED", "duration_seconds": 0.77},
        "core": {"status": "SUCCEEDED", "duration_seconds": 9.35},
        "executor": {"status": "SUCCEEDED", "duration_seconds": 2.0},
        "gen": {"status": "SUCCEEDED", "duration_seconds": 0.57},
        "reader": {"status": "SUCCEEDED", "duration_seconds": 14.25},
    }})
    _write(root, "executor-summary.json", {
        "processed": 24, "pass": 2, "fail": 22, "broken": 0, "inserted": 24,
        "duration_seconds": 1.504, "manifest_protocol": "bundle.handoff/v2",
        "candidate_count_reconciliation": {"declared": 24, "actual": 24},
        "outcomes": {"PASS": 2, "DOMAIN_FAIL": 22, "INFRA_FAIL": 0, "BROKEN": 0,
                     "TIMEOUT": 0, "CANCELLED": 0, "SKIPPED": 0},
        "sandbox_backend": None,
    })
    _write(root, "provenance.json", {
        "schema": "analyzer.provenance/v1", "mode": "exploratory", "candidates_seen": 2,
        "goals": [{"key": "charges", "mode": "MINIMIZE"}], "provenance_issues": [],
        "provenance_ok": True,
        "candidates": [{
            "candidate_id": "1_0_0", "outcome": "pass", "objectives": {"charges": 1.0},
            "dimensions": {"order": "reserve>charge>ship"},
            "reason_non_dominated": "Pareto trade-off", "provenance": "explicit",
        }],
    })
    _write(root, "stages/executor.json", {"artifacts": [
        {"kind": "output.metrics", "path": "/tmp/x/metrics.kv", "bytes": 4408, "sha256": "b" * 64}]})
    return root


class _WellFormed(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] != tag:
            self.errors.append(f"expected </{self.stack[-1]}>, got </{tag}>")
        else:
            self.stack.pop()


def _assert_well_formed(markup: str) -> None:
    parser = _WellFormed()
    parser.feed(markup)
    assert not parser.errors, parser.errors
    assert not parser.stack, f"unclosed tags: {parser.stack}"


# --- collect -------------------------------------------------------------
def test_collect_requires_a_run_directory(tmp_path):
    with pytest.raises(PreflightError):
        collect(tmp_path)


def test_collect_reports_missing_artifacts_as_none(tmp_path):
    """A run that died in Core has no executor summary; that must not raise."""
    _write(tmp_path, "run.json", {"run_id": "r-partial", "status": "FAILED"})
    data = collect(tmp_path)
    assert data["schema"] == REPORT_SCHEMA
    assert data["executor"] is None and data["provenance"] is None
    assert data["stage_records"] == {}


# --- html ----------------------------------------------------------------
def test_full_run_renders_well_formed_and_self_contained(tmp_path):
    markup = render_html(collect(full_run(tmp_path)))
    _assert_well_formed(markup)
    # a strict-CSP-safe, portable page: no external asset may be referenced
    for forbidden in ("http://", "https://", "<script", "src="):
        assert forbidden not in markup, forbidden
    assert "r-full" in markup and "charges" in markup


def test_absent_sandbox_backend_is_called_out_not_omitted(tmp_path):
    """`sandbox_backend: null` means candidates ran unsandboxed -- say so."""
    markup = render_html(collect(full_run(tmp_path)))
    assert "unsandboxed" in markup


def test_named_sandbox_backend_is_shown_verbatim(tmp_path):
    root = full_run(tmp_path)
    summary = json.loads((root / "executor-summary.json").read_text())
    summary["sandbox_backend"] = "bwrap"
    _write(root, "executor-summary.json", summary)
    markup = render_html(collect(root))
    assert "bwrap" in markup and "unsandboxed" not in markup


def test_count_mismatch_is_flagged(tmp_path):
    root = full_run(tmp_path)
    summary = json.loads((root / "executor-summary.json").read_text())
    summary["candidate_count_reconciliation"] = {"declared": 24, "actual": 23}
    _write(root, "executor-summary.json", summary)
    markup = render_html(collect(root))
    assert "class='bad'>24 / 23" in markup.replace('"', "'")


def test_missing_analyzer_says_so_rather_than_rendering_empty(tmp_path):
    root = full_run(tmp_path)
    (root / "provenance.json").unlink()
    markup = render_html(collect(root))
    _assert_well_formed(markup)
    assert "Analyzer did not run" in markup


def test_interrupted_stage_keeps_its_status(tmp_path):
    root = full_run(tmp_path)
    state = json.loads((root / "state.json").read_text())
    state["stages"]["executor"]["status"] = "INTERRUPTED"
    state["status"] = "INTERRUPTED"
    _write(root, "state.json", state)
    markup = render_html(collect(root))
    _assert_well_formed(markup)
    assert "INTERRUPTED" in markup


def test_render_escapes_untrusted_spec_text(tmp_path):
    """Spec paths and dimension values reach the page; they must be escaped."""
    root = full_run(tmp_path)
    manifest = json.loads((root / "run.json").read_text())
    manifest["spec_path"] = "<script>alert(1)</script>"
    _write(root, "run.json", manifest)
    markup = render_html(collect(root))
    assert "<script>alert(1)</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_a_run_with_no_stages_still_renders(tmp_path):
    _write(tmp_path, "run.json", {"run_id": "r-bare", "status": "FAILED"})
    markup = render_html(collect(tmp_path))
    _assert_well_formed(markup)
    assert "No stage state recorded" in markup


# --- text ----------------------------------------------------------------
def test_text_summary_covers_the_headline_facts(tmp_path):
    text = format_text(collect(full_run(tmp_path)))
    assert "r-full" in text and "SUCCEEDED" in text
    assert "PASS=2" in text and "DOMAIN_FAIL=22" in text
    assert "NONE (candidates ran unsandboxed)" in text
    assert "front=1" in text
