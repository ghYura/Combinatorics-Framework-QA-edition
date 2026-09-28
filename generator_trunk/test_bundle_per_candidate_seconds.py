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

"""The per-candidate execution-cost range behind the wall-time estimate: one setting for plan and run.

`bundle plan` always accepted --per-candidate-seconds-min/max, but the run's budget gate used the
generic default (0.05-2 s) regardless, so a measured range could clear `plan` and still be refused
by the run. Both now read `BundleConfig.per_candidate_seconds_min/max` (CLI flag or
BUNDLE_PER_CANDIDATE_SECONDS_*), with the historical defaults, and the run records the range it
used in its budget intent.

Run: `python3 -m pytest test_bundle_per_candidate_seconds.py -q` (no DB / no Bundle run).
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fwgen as fg                                            # noqa: E402
from bundle.cli import _check_budgets                         # noqa: E402
from bundle.cliutil import _per_candidate_seconds, _resolve_bundle_config   # noqa: E402
from bundle.config import BundleConfig                        # noqa: E402
from bundle.errors import BudgetError, PreflightError         # noqa: E402
from bundle.resources import DEFAULT_PER_CANDIDATE_SECONDS    # noqa: E402

# 40 x 36 = 1440 mandatory rows = 1440 final candidates (no optional sheets, no sieve)
SPEC = {"slots": [{"sheet": "A", "key": "a", "values": [f"a{i}" for i in range(40)]},
                  {"sheet": "B", "key": "b", "values": [f"b{i}" for i in range(36)]}]}


def _args():
    return SimpleNamespace(override_budget=None, allow_extreme=False, cost_per_candidate=None)


def _cfg(**kw):
    return BundleConfig(budget_mandatory_rows=1600, budget_final_candidates=1600,
                        budget_wall_time_seconds=1800, **kw)


def test_defaults_are_the_historical_range():
    cfg = BundleConfig()
    assert (cfg.per_candidate_seconds_min, cfg.per_candidate_seconds_max) == DEFAULT_PER_CANDIDATE_SECONDS
    assert _per_candidate_seconds(cfg) == DEFAULT_PER_CANDIDATE_SECONDS


def test_the_run_gate_uses_the_configured_range_and_records_it():
    spec = fg.parse_spec(SPEC, "per-candidate")
    with pytest.raises(BudgetError, match="wall time"):          # default: 1440 x 2 s = 2880 > 1800
        _check_budgets(_args(), spec, _cfg())
    intent = _check_budgets(_args(), spec, _cfg(per_candidate_seconds_min=0.3, per_candidate_seconds_max=1.2))
    assert intent["exceeded"] == [] and intent["override"] is False      # 1440 x 1.2 = 1728 <= 1800
    assert intent["per_candidate_seconds"] == [0.3, 1.2]
    with pytest.raises(BudgetError, match="wall time"):          # a range that still exceeds is refused
        _check_budgets(_args(), spec, _cfg(per_candidate_seconds_min=0.3, per_candidate_seconds_max=1.3))


INF, NAN = float("inf"), float("nan")
INVALID = [(0, 1), (-0.1, 1), (2, 1),                              # non-positive or reversed
           (0.05, INF), (INF, INF), (INF, 2.0), (-INF, 1.0),      # infinite at either endpoint
           (0.05, NAN), (NAN, 1.0), (NAN, NAN)]                    # NaN


@pytest.mark.parametrize("lo, hi", INVALID)
def test_an_invalid_range_fails_before_any_stage(lo, hi):
    with pytest.raises(PreflightError, match="finite with 0 < min <= max"):
        _per_candidate_seconds(BundleConfig(per_candidate_seconds_min=lo, per_candidate_seconds_max=hi))


@pytest.mark.parametrize("lo, hi", INVALID)
def test_the_run_gate_refuses_non_finite_or_invalid_ranges_cleanly(lo, hi):
    """Review R-v3: an infinite endpoint reached the integer estimates as OverflowError."""
    one = fg.parse_spec({"slots": [{"sheet": "A", "key": "a", "values": ["a1"]}]}, "one")
    with pytest.raises(PreflightError):
        _check_budgets(_args(), one, BundleConfig(per_candidate_seconds_min=lo, per_candidate_seconds_max=hi))


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "0", "-1"])
def test_layered_config_rejects_invalid_values(monkeypatch, value):
    from bundle.config import ConfigError
    with pytest.raises(ConfigError, match="finite with 0 < min <= max"):
        _resolve_bundle_config(SimpleNamespace(per_candidate_seconds_max=float(value), config_file=""))
    monkeypatch.setenv("BUNDLE_PER_CANDIDATE_SECONDS_MIN", value)
    with pytest.raises(ConfigError, match="finite with 0 < min <= max"):
        _resolve_bundle_config(SimpleNamespace(config_file=""))


@pytest.mark.parametrize("flags", [["--per-candidate-seconds-max=inf"], ["--per-candidate-seconds-min=-inf"],
                                   ["--per-candidate-seconds-max=nan"], ["--per-candidate-seconds-min=inf"]])
def test_plan_and_run_cli_refuse_without_a_traceback_or_any_stage(tmp_path, flags):
    spec_path = tmp_path / "one.toml"
    spec_path.write_text('[[slots]]\nsheet = "A"\nkey = "a"\nvalues = ["a1"]\n', encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "BUNDLE_SCRATCH_ROOT": str(tmp_path / "scratch")}
    plan = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "plan", str(spec_path), "--out",
                           str(tmp_path / "plan"), *flags], capture_output=True, text=True, cwd=HERE.parent, env=env)
    run = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), str(spec_path), "--db", "as0927_never_created",
                          "--execution-policy-profile", "generated-default", *flags],
                         capture_output=True, text=True, cwd=HERE.parent, env=env)
    for r in (plan, run):
        out = r.stdout + r.stderr
        assert r.returncode != 0 and "Traceback" not in out and "finite with 0 < min <= max" in out, out
    assert not (tmp_path / "plan" / "plan.json").exists()          # nothing planned
    assert not (tmp_path / "scratch").exists()                      # the run never reached preflight


def test_cli_and_environment_layers(monkeypatch):
    cfg, sources = _resolve_bundle_config(SimpleNamespace(per_candidate_seconds_min=0.3, per_candidate_seconds_max=1.2,
                                                          config_file=""))
    assert (cfg.per_candidate_seconds_min, cfg.per_candidate_seconds_max) == (0.3, 1.2)
    monkeypatch.setenv("BUNDLE_PER_CANDIDATE_SECONDS_MAX", "0.9")
    cfg, _ = _resolve_bundle_config(SimpleNamespace(config_file=""))
    assert (cfg.per_candidate_seconds_min, cfg.per_candidate_seconds_max) == (0.05, 0.9)


def test_plan_and_run_agree(tmp_path):
    spec_path = tmp_path / "pc.toml"
    spec_path.write_text("".join(f'[[slots]]\nsheet = "{s["sheet"]}"\nkey = "{s["key"]}"\nvalues = {json.dumps(s["values"])}\n'
                                 for s in SPEC["slots"]), encoding="utf-8")
    env = {"BUNDLE_BUDGET_WALL_TIME_SECONDS": "1800", "BUNDLE_BUDGET_MANDATORY_ROWS": "1600",
           "BUNDLE_BUDGET_FINAL_CANDIDATES": "1600", "PATH": "/usr/bin:/bin"}
    def plan(*flags):
        out = tmp_path / ("p" + "_".join(flags).replace("-", "").replace(".", ""))
        r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "plan", str(spec_path), "--out", str(out), *flags],
                           capture_output=True, text=True, cwd=HERE.parent, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        return json.loads((out / "plan.json").read_text())["budget_blocking"]
    assert plan() == ["wall_time_seconds"]                     # the same verdict as the run gate's default
    assert plan("--per-candidate-seconds-min", "0.3", "--per-candidate-seconds-max", "1.2") == []
