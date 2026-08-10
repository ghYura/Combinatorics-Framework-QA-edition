#!/usr/bin/env python3
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

"""Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6): `verify_executor_schema_capability`
fences genuinely-old executor artifacts BEFORE they connect, so they never resurrect the retired
3-column results_v2 index. Pure-unit (no DB, no real run): the real Python/Java probe is exercised
once for the accept path; the reject paths drive a fake `run` (old binary / probe failure / wrong
version). Run: python3 -m pytest test_bundle_schema_capability.py -q
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bundle.stages as stages
from bundle.config import BundleConfig
from bundle.errors import StageError

TOKEN = stages.RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def _good_doc():
    return json.dumps({
        "schema": "py_executor.capabilities/v1",
        "results_v2_schema": {"version": stages.RESULTS_V2_SCHEMA_VERSION,
                              "unique_index": stages.RESULTS_V2_SAMPLE_INDEX_NAME,
                              "sample_identity_writer": True},
    })


def test_accepts_real_python_executor():
    # the actual configured py_executor advertises the 5-col sample-identity writer.
    doc = stages.verify_executor_schema_capability(BundleConfig(), "python")
    assert doc["results_v2_schema"]["version"] == stages.RESULTS_V2_SCHEMA_VERSION
    assert doc["results_v2_schema"]["unique_index"] == stages.RESULTS_V2_SAMPLE_INDEX_NAME


def test_accepts_when_probe_reports_5col_writer(monkeypatch):
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result(_good_doc()))
    assert stages.verify_executor_schema_capability(BundleConfig(), "java")["results_v2_schema"][
        "sample_identity_writer"] is True


def test_rejects_old_binary_without_schema_block(monkeypatch):
    # a pre-Plan-1 binary emits a capability doc with no results_v2_schema block -> reject.
    old = json.dumps({"schema": "py_executor.capabilities/v1", "repeat": {"local_metrics": True}})
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result(old))
    with pytest.raises(StageError) as ei:
        stages.verify_executor_schema_capability(BundleConfig(), "python")
    assert TOKEN in str(ei.value)


def test_rejects_when_probe_exits_nonzero(monkeypatch):
    # a genuinely-old binary invoked with --capabilities does not recognize it and exits non-zero.
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result("boom", returncode=2))
    with pytest.raises(StageError) as ei:
        stages.verify_executor_schema_capability(BundleConfig(), "python")
    assert TOKEN in str(ei.value)


def test_rejects_wrong_schema_version(monkeypatch):
    doc = json.dumps({"results_v2_schema": {"version": 1, "unique_index": "results_v2_sample_uk",
                                            "sample_identity_writer": True}})
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result(doc))
    with pytest.raises(StageError) as ei:
        stages.verify_executor_schema_capability(BundleConfig(), "python")
    assert TOKEN in str(ei.value)


def test_rejects_non_json_probe_output(monkeypatch):
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result("not json at all"))
    with pytest.raises(StageError) as ei:
        stages.verify_executor_schema_capability(BundleConfig(), "python")
    assert TOKEN in str(ei.value)


# ── Plan-1 3c: the Java repeat-capability probe (gate-opening) ──────────────────────────
def test_accepts_real_java_executor_repeat_capability():
    # the actual configured Java Executor jar advertises the local/metrics repeat block.
    cfg = BundleConfig()
    jar = Path(cfg.java_executor_jar) if cfg.java_executor_jar else stages.JAVA_EXECUTOR_JAR
    if not jar.is_file():
        pytest.skip(f"generated Java Executor build artifact absent: {jar}")
    doc = stages.probe_java_executor_repeat_capability(cfg)
    assert doc["schema"] == "java_executor.capabilities/v1"
    assert doc["repeat"]["local_metrics"] is True
    assert doc["repeat"]["local_all"] is True          # Plan-1 local/all (every sample a full verdict)
    assert doc["repeat"]["raw_sample_identity"] is True
    assert doc["repeat"]["runtime_accounting"] is True
    assert int(doc["repeat"]["max_k"]) >= 1


def test_java_repeat_probe_rejects_doc_without_repeat_block(monkeypatch):
    # an artifact that reports a schema doc but no repeat block (e.g. a pre-3c Java jar) is refused.
    doc = json.dumps({"schema": "java_executor.capabilities/v1",
                      "results_v2_schema": {"version": stages.RESULTS_V2_SCHEMA_VERSION,
                                            "unique_index": stages.RESULTS_V2_SAMPLE_INDEX_NAME,
                                            "sample_identity_writer": True}})
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result(doc))
    with pytest.raises(StageError) as ei:
        stages.probe_java_executor_repeat_capability(BundleConfig())
    assert "capability" in str(ei.value).lower()


def test_java_repeat_probe_rejects_probe_failure(monkeypatch):
    monkeypatch.setattr(stages, "run", lambda *a, **k: _result("", returncode=3))
    with pytest.raises(StageError) as ei:
        stages.probe_java_executor_repeat_capability(BundleConfig())
    assert "capability probe failed" in str(ei.value).lower()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
