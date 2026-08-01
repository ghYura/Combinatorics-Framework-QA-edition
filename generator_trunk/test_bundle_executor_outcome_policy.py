#!/usr/bin/env python3
"""Targeted tests for the STEP 21 launcher success policy: which canonical
Executor outcomes (BROKEN/TIMEOUT/INFRA_FAIL) fail a run by default, how
`--executor-tolerate-outcomes` / `BundleConfig.executor_tolerate_outcomes`
downgrades them to recorded-but-non-blocking WARNINGs, and the persistence
invariant that must hold once `processed > pass + fail` becomes a legitimate,
tolerated state (run: `python3 test_bundle_executor_outcome_policy.py`)."""
from pathlib import Path
from unittest.mock import patch

import pytest

from bundle import invariants, stages
from bundle.config import BundleConfig
from bundle.errors import StageError
from bundle.models import InvariantSeverity
from bundle.process import CommandResult

CRITICAL = InvariantSeverity.CRITICAL
WARNING = InvariantSeverity.WARNING


@pytest.fixture(autouse=True)
def _stub_schema_capability_probe(monkeypatch):
    # Plan-1 Phase 3b pre-connect fencing runs at the start of stage_executor; these tests stub
    # stages.run (so the probe would parse a non-capability payload). Stub the probe itself -- the
    # fencing is covered directly in test_bundle_schema_capability.py.
    monkeypatch.setattr(stages, "verify_executor_schema_capability",
                        lambda cfg, language=None: {"results_v2_schema": {"version": 2}})


# --------------------- BundleConfig.tolerated_outcomes() --------------------- #
def test_tolerated_outcomes_defaults_to_empty():
    assert BundleConfig().tolerated_outcomes() == frozenset()


def test_tolerated_outcomes_parses_comma_list_case_insensitively():
    cfg = BundleConfig(executor_tolerate_outcomes=" timeout, Infra_Fail ,broken")
    assert cfg.tolerated_outcomes() == frozenset({"TIMEOUT", "INFRA_FAIL", "BROKEN"})


def test_tolerated_outcomes_ignores_blank_entries():
    assert BundleConfig(executor_tolerate_outcomes=" , ,").tolerated_outcomes() == frozenset()


# --------------- severity of the three infrastructure-outcome gates ---------- #
# Mirrors exactly how cli.py's `_severity` selects CRITICAL/WARNING from
# `cfg.tolerated_outcomes()`: untolerated -> fails the run closed (CRITICAL);
# explicitly tolerated -> recorded but non-blocking (WARNING). All three gates
# (BROKEN/TIMEOUT/INFRA_FAIL) must behave identically -- before this step
# BROKEN was hardcoded CRITICAL and the policy could not touch it.
def _severity(tolerated, name):
    return WARNING if name in tolerated else CRITICAL


def test_broken_zero_is_critical_by_default_and_warning_when_tolerated():
    untolerated = BundleConfig().tolerated_outcomes()
    tolerated = BundleConfig(executor_tolerate_outcomes="BROKEN").tolerated_outcomes()

    r = invariants.executor_broken_zero(3, severity=_severity(untolerated, "BROKEN"))
    assert r.severity == CRITICAL and r.passed is False

    r = invariants.executor_broken_zero(3, severity=_severity(tolerated, "BROKEN"))
    assert r.severity == WARNING and r.passed is False   # still recorded as failed -- just non-blocking

    # zero is always "passed" regardless of policy -- nothing to tolerate
    r = invariants.executor_broken_zero(0, severity=_severity(untolerated, "BROKEN"))
    assert r.passed is True


def test_timeout_zero_is_critical_by_default_and_warning_when_tolerated():
    untolerated = BundleConfig().tolerated_outcomes()
    tolerated = BundleConfig(executor_tolerate_outcomes="TIMEOUT").tolerated_outcomes()

    assert invariants.executor_timeout_zero(2, severity=_severity(untolerated, "TIMEOUT")).severity == CRITICAL
    assert invariants.executor_timeout_zero(2, severity=_severity(tolerated, "TIMEOUT")).severity == WARNING


def test_infra_fail_zero_is_critical_by_default_and_warning_when_tolerated():
    untolerated = BundleConfig().tolerated_outcomes()
    tolerated = BundleConfig(executor_tolerate_outcomes="INFRA_FAIL").tolerated_outcomes()

    assert invariants.executor_infra_fail_zero(1, severity=_severity(untolerated, "INFRA_FAIL")).severity == CRITICAL
    assert invariants.executor_infra_fail_zero(1, severity=_severity(tolerated, "INFRA_FAIL")).severity == WARNING


def test_tolerating_one_outcome_does_not_tolerate_the_others():
    # --executor-tolerate-outcomes=TIMEOUT must not silently waive BROKEN/INFRA_FAIL
    tolerated = BundleConfig(executor_tolerate_outcomes="TIMEOUT").tolerated_outcomes()
    assert invariants.executor_timeout_zero(1, severity=_severity(tolerated, "TIMEOUT")).severity == WARNING
    assert invariants.executor_broken_zero(1, severity=_severity(tolerated, "BROKEN")).severity == CRITICAL
    assert invariants.executor_infra_fail_zero(1, severity=_severity(tolerated, "INFRA_FAIL")).severity == CRITICAL


def test_enforce_only_raises_on_critical_failures():
    # WARNING-severity failures (a tolerated outcome that actually occurred)
    # must be recorded but must NOT raise -- that is the entire point of
    # downgrading severity rather than skipping the check.
    results = [
        invariants.executor_broken_zero(2, severity=WARNING),
        invariants.executor_timeout_zero(0, severity=CRITICAL),
    ]
    invariants.enforce(results)   # must not raise

    results = [invariants.executor_infra_fail_zero(1, severity=CRITICAL)]
    try:
        invariants.enforce(results)
        assert False, "expected InvariantError for a failed CRITICAL invariant"
    except Exception as exc:
        assert "executor.infra_fail_zero" in str(exc)


# ------------------- persistence invariant under tolerated outcomes ---------- #
# STEP 21 review finding: TIMEOUT/INFRA_FAIL (and BROKEN, now tolerable too)
# produce no domain verdict and so cannot be inserted -- `processed > pass +
# fail` is a legitimate state once the policy tolerates any of them. The
# invariant must compare against `pass + fail`, not `processed`.
def test_inserted_matches_policy_compares_against_pass_plus_fail_not_processed():
    # 10 processed: 6 pass, 2 domain_fail, 1 broken, 1 infra_fail (tolerated) --
    # only the 8 verdict-producing candidates can have been inserted.
    r = invariants.executor_inserted_matches_policy(inserted=8, passed_n=6, failed=2)
    assert r.passed is True and r.expected == 8

    # the pre-STEP-21 expectation (inserted == processed == 10) must NOT be
    # what this invariant checks anymore -- that would fail a run the policy
    # just chose to allow through.
    r = invariants.executor_inserted_matches_policy(inserted=10, passed_n=6, failed=2)
    assert r.passed is False


def test_inserted_matches_policy_still_catches_a_genuine_persistence_gap():
    # 6 pass + 2 fail = 8 should have been inserted; only 7 were -- a real bug
    # (e.g. one verdict silently dropped), not a tolerated-outcome artifact.
    r = invariants.executor_inserted_matches_policy(inserted=7, passed_n=6, failed=2)
    assert r.passed is False and r.expected == 8 and r.actual == 7


def test_processed_eq_sum_accounts_for_every_canonical_infrastructure_outcome():
    # processed = pass + fail + broken + timeout + infra_fail (skipped/cancelled
    # are never produced by the cold-start/watch executor path, so they are not
    # parameters here -- see py_executor's Outcome.ALL vs. what it actually emits).
    r = invariants.executor_processed_eq_sum(processed=10, passed_n=6, failed=2, broken=1, timeout=0, infra_fail=1)
    assert r.passed is True

    r = invariants.executor_processed_eq_sum(processed=10, passed_n=6, failed=2, broken=1, timeout=1, infra_fail=1)
    assert r.passed is False and r.expected == 11


# --------- stage_executor: non-zero exit must defer to outcome policy -------- #
# STEP 21 review finding (c): py_executor now exits non-zero on a *classified*
# infrastructure failure (DB connect/commit -> INFRA_FAIL) while still emitting
# a complete completion summary. The launcher must NOT raise a bare StageError
# in that case -- doing so would short-circuit the success policy and make
# --executor-tolerate-outcomes=INFRA_FAIL/TIMEOUT/BROKEN impossible to honour.
# Only a genuinely unclassified crash (no summary at all) stays a hard StageError.
def _cmd_result(returncode, stdout):
    return CommandResult(argv=(), display="", returncode=returncode, stdout=stdout,
                         stderr="", start=0.0, end=0.0, duration=0.0, timed_out=False)


def _fake_psql(port, db, sql, **kw):
    return "1 / pass 0 / fail 0", 0


def _run_stage_executor(fake_run):
    src, hs = Path("/nonexistent-src"), Path("/nonexistent-hs")
    cfg = BundleConfig()
    with patch.object(stages, "run", fake_run), patch.object(stages, "psql", _fake_psql):
        return stages.stage_executor(src, hs, "cfgtestdb", 5432, cfg=cfg)


def test_nonzero_exit_with_summary_defers_to_policy_instead_of_raising():
    stdout = ("py_executor DONE: processed=1 pass=0 fail=0 broken=0 inserted=0\n"
              "py_executor OUTCOMES: pass=0 domain_fail=0 broken=0 timeout=0 "
              "infra_fail=1 skipped=0 cancelled=0")
    result = _run_stage_executor(lambda cmd, **kw: _cmd_result(1, stdout))
    processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = result
    assert (processed, passed, failed, broken, inserted) == (1, 0, 0, 0, 0)
    assert (timeout, infra_fail) == (0, 1)


def test_nonzero_exit_without_summary_raises_unclassified_stage_error():
    try:
        _run_stage_executor(lambda cmd, **kw: _cmd_result(1, "Traceback (most recent call last): boom"))
        assert False, "expected StageError for an unclassified crash"
    except StageError as exc:
        assert "unclassified failure" in str(exc)


def test_connect_failure_summary_skips_db_crosscheck_instead_of_bypassing_policy():
    # py_executor: a connect failure leaves processed=0, inserted=0, and every
    # outcome bucket at 0 (it is FATAL/untolerable via processed_positive, not
    # a per-candidate INFRA_FAIL -- see py_executor.py's connect-failure branch).
    # stage_executor must not then call `psql` against a DB that may itself be
    # unreachable: a raw StageError("could not read Results DB ...") from that
    # probe would short-circuit the launcher's invariant/policy evaluation --
    # the same "bypasses tolerance" failure mode as issue (c), just one line
    # later. `processed == 0` is the narrow, structural signal that py_executor
    # never reached the DB at all (see stages.py's comment on the skip condition
    # -- review finding round 2: `inserted == 0` alone was too broad, see the
    # companion test below for the case that must still probe).
    stdout = ("py_executor DONE: processed=0 pass=0 fail=0 broken=0 inserted=0\n"
              "py_executor OUTCOMES: pass=0 domain_fail=0 broken=0 timeout=0 "
              "infra_fail=0 skipped=0 cancelled=0")

    def _psql_must_not_be_called(port, db, sql, **kw):
        raise AssertionError("stage_executor must not query the Results DB when processed == 0")

    src, hs = Path("/nonexistent-src"), Path("/nonexistent-hs")
    cfg = BundleConfig()
    with patch.object(stages, "run", lambda cmd, **kw: _cmd_result(1, stdout)), \
         patch.object(stages, "psql", _psql_must_not_be_called):
        result = stages.stage_executor(src, hs, "cfgtestdb", 5432, cfg=cfg)
    processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = result
    assert (processed, inserted, db_total) == (0, 0, 0)
    # processed == sum(outcomes) == 0 -- the FATAL signal is processed_positive,
    # which is always CRITICAL/untolerable, not a per-candidate outcome count.
    r = invariants.executor_processed_eq_sum(processed, passed, failed, broken, timeout, infra_fail)
    assert r.passed is True
    assert invariants.executor_processed_positive(processed).passed is False


def test_zero_inserted_with_candidates_processed_still_probes_results_db():
    # STEP 21 review finding (round 2): `inserted == 0` is NOT, by itself, a
    # signal that the DB is unreachable -- a perfectly normal run where every
    # candidate was tolerated as e.g. BROKEN (--executor-tolerate-outcomes
    # =BROKEN, DB connection healthy, nothing to insert) legitimately ends with
    # `inserted == 0` too. That run still benefits from confirming the Results
    # DB table is actually empty/consistent -- skipping the probe here would
    # silently widen the earlier "skip when DB might be down" carve-out into
    # "never check an empty insert set", masking a real persistence bug (e.g.
    # stale rows left over from a previous run).
    stdout = ("py_executor DONE: processed=3 pass=0 fail=0 broken=3 inserted=0\n"
              "py_executor OUTCOMES: pass=0 domain_fail=0 broken=3 timeout=0 "
              "infra_fail=0 skipped=0 cancelled=0")
    probed = []

    def _fake_psql(port, db, sql, **kw):
        probed.append((port, db))
        return "0 / pass 0 / fail 0", 0

    src, hs = Path("/nonexistent-src"), Path("/nonexistent-hs")
    cfg = BundleConfig()
    with patch.object(stages, "run", lambda cmd, **kw: _cmd_result(0, stdout)), \
         patch.object(stages, "psql", _fake_psql):
        result = stages.stage_executor(src, hs, "cfgtestdb", 5432, cfg=cfg)
    processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts = result
    assert (processed, inserted, db_total) == (3, 0, 0)
    assert probed == [(5432, "cfgtestdb")], "expected stage_executor to probe the Results DB exactly once"


def test_zero_exit_without_summary_still_raises_stage_error():
    try:
        _run_stage_executor(lambda cmd, **kw: _cmd_result(0, "nothing useful here"))
        assert False, "expected StageError when no completion summary is emitted"
    except StageError as exc:
        assert "did not emit a completion summary" in str(exc)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} tests passed")
