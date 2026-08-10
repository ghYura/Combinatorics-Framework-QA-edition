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

from __future__ import annotations

from typing import Any, Sequence
from pathlib import Path

from .errors import InvariantError
from .runs import file_sha256
from .models import InvariantResult, InvariantSeverity

CRITICAL = InvariantSeverity.CRITICAL
WARNING = InvariantSeverity.WARNING


def _r(id, description, expected, actual, passed, severity=CRITICAL) -> InvariantResult:
    return InvariantResult(id=id, description=description, expected=expected, actual=actual,
                           passed=bool(passed), severity=severity)


# ------------------------------ individual checks ---------------------------- #
# Each mirrors one bullet of the execution-plan's STEP-6 invariant list, against
# whichever counts the launcher already has in hand from the stage it just ran
# (see cli.py). None of these replace a stage's own fail-fast checks — they make
# the cross-stage expectations explicit, structured, and recorded in stage JSON.
def core_count_positive(actual: Any) -> InvariantResult:
    return _r("core.count_positive", "Core actual count is an integer > 0",
              expected=">0", actual=actual, passed=isinstance(actual, int) and actual > 0)


def post_sieve_le_core(post_sieve: Any, core: Any) -> InvariantResult:
    ok = isinstance(post_sieve, int) and isinstance(core, int) and post_sieve <= core
    return _r("sieve.post_le_core", "post-sieve count <= Core count",
              expected=f"<= {core}", actual=post_sieve, passed=ok)


def reader_emitted_eq_expected(emitted: Any, expected: Any) -> InvariantResult:
    return _r("reader.emitted_eq_expected", "Reader emitted count equals expected count",
              expected=expected, actual=emitted, passed=emitted == expected)


def reader_empty_zero(empty: Any) -> InvariantResult:
    return _r("reader.empty_zero", "empty candidate count = 0",
              expected=0, actual=empty, passed=empty == 0)


def handoff_run_id_matches(manifest_run_id: Any, expected_run_id: Any) -> InvariantResult:
    return _r("handoff.run_id_matches", "Handoff v2 manifest run_id matches the bundle run",
              expected=expected_run_id, actual=manifest_run_id, passed=manifest_run_id == expected_run_id)


def handoff_candidate_count_matches(manifest_count: Any, emitted: Any) -> InvariantResult:
    return _r("handoff.candidate_count_matches", "Handoff v2 manifest candidate_count matches Reader emission",
              expected=emitted, actual=manifest_count, passed=manifest_count == emitted)


def handoff_manifest_used(used: Any, expected: Any) -> InvariantResult:
    return _r("handoff.manifest_used", "Executor received the Handoff v2 manifest per the active mode "
                                       "(normal: required; --legacy-handoff: explicit fallback)",
              expected=expected, actual=used, passed=used == expected)


def executor_processed_positive(processed: Any) -> InvariantResult:
    return _r("executor.processed_positive", "Executor processed count is an integer > 0",
              expected=">0", actual=processed, passed=isinstance(processed, int) and processed > 0)


def executor_processed_eq_sum(processed: Any, passed_n: Any, failed: Any, broken: Any,
                              timeout: Any = 0, infra_fail: Any = 0) -> InvariantResult:
    """processed = pass + fail + broken + timeout + infra_fail (STEP 21 outcome split).

    `passed_n`/`failed` are the legacy boolean-status projections (PASS/
    DOMAIN_FAIL); `broken`/`timeout`/`infra_fail` are the canonical
    infrastructure-outcome counts py_executor now reports separately instead
    of folding TIMEOUT and INFRA_FAIL into BROKEN.
    """
    total = passed_n + failed + broken + timeout + infra_fail
    return _r("executor.processed_eq_sum",
              "Executor processed = pass + fail + broken + timeout + infra_fail",
              expected=total, actual=processed, passed=processed == total)


def executor_broken_zero(broken: Any, *, severity: InvariantSeverity = CRITICAL) -> InvariantResult:
    """Per the STEP 21 launcher success policy: BROKEN candidates fail the run
    by default (domain failures are an accepted outcome; infrastructure
    outcomes — including BROKEN — are not). `severity` lets the launcher
    downgrade to WARNING when its configured success policy explicitly
    tolerates BROKEN (mirrors executor_timeout_zero/executor_infra_fail_zero —
    before STEP 21 this was hardcoded CRITICAL and --executor-tolerate-outcomes
    could not honour BROKEN)."""
    return _r("executor.broken_zero", "Executor broken count = 0",
              expected=0, actual=broken, passed=broken == 0, severity=severity)


def executor_timeout_zero(timeout: Any, *, severity: InvariantSeverity = CRITICAL) -> InvariantResult:
    """Per the STEP 21 launcher success policy: timeouts fail the run by default
    (domain failures are an accepted outcome; infrastructure outcomes are not).
    `severity` lets the launcher downgrade to WARNING when its configured
    success policy explicitly tolerates timeouts."""
    return _r("executor.timeout_zero", "Executor timeout count = 0",
              expected=0, actual=timeout, passed=timeout == 0, severity=severity)


def executor_infra_fail_zero(infra_fail: Any, *, severity: InvariantSeverity = CRITICAL) -> InvariantResult:
    """Per the STEP 21 launcher success policy: infrastructure failures fail the
    run by default. `severity` lets the launcher downgrade to WARNING when its
    configured success policy explicitly tolerates infra failures."""
    return _r("executor.infra_fail_zero", "Executor infra_fail count = 0",
              expected=0, actual=infra_fail, passed=infra_fail == 0, severity=severity)


def executor_inserted_matches_policy(inserted: Any, passed_n: Any, failed: Any) -> InvariantResult:
    """Current persistence policy: every candidate that produced a domain verdict
    (PASS or DOMAIN_FAIL) is inserted -- BROKEN/TIMEOUT/INFRA_FAIL/SKIPPED/
    CANCELLED candidates produce no verdict and so cannot be inserted (STEP 21:
    `inserted == processed` only happened to hold while BROKEN was forced to 0
    by a hardcoded CRITICAL invariant; expressing the expectation as `pass +
    fail` makes it correct under a tolerated-outcomes policy too, where
    `processed > pass + fail` is now a legitimate, accepted state)."""
    expected = passed_n + failed
    return _r("executor.inserted_matches_policy",
              "inserted count matches persistence policy (= pass + fail, i.e. candidates with a domain verdict)",
              expected=expected, actual=inserted, passed=inserted == expected)


def results_v2_write_counts_consistent(attempted: Any, inserted: Any, already_present: Any,
                                       updated_selected: Any) -> InvariantResult:
    """STEP 23 idempotent-write policy, expressed as a launcher-checkable
    invariant (action item 4: "Launcher invariant учитывает policy").

    The additive results_v2 writer (ResultsV2Writer / write_results_v2_batch,
    schema from STEP 22's ResultsV2SchemaMigrator) reports four buckets per
    batch: every attempted row lands in EXACTLY ONE of inserted /
    already_present / updated_selected -- "DB write: ... conflict handling
    explicit; no silent overwrite" means a row is never counted twice (e.g.
    both inserted and already-present) nor dropped on the floor (attempted
    higher than the sum). `updated_selected` is always 0 for the current
    writer (immutable attempts -- "one selected/final result" is a read-time
    concern, never a write-time UPDATE -- see ResultsV2Writer's class-level
    policy note) but is carried in the sum so the invariant keeps holding
    unchanged if a future, still-immutable selection mechanism ever populates
    it from a separate, additive write path.

    This is independent of (and additive to) results_db_eq_inserted: that one
    is the legacy positional table's count contract (every PASS/DOMAIN_FAIL
    becomes exactly one row, because the legacy schema has no idempotency key
    and so cannot distinguish a fresh insert from a replay); this one is
    results_v2's, where replays are expected and must be visible as
    already_present rather than as duplicate rows or inflated inserted counts."""
    expected = inserted + already_present + updated_selected
    return _r("results_v2.write_counts_consistent",
              "results_v2 write counts satisfy attempted == inserted + already_present + updated_selected "
              "(idempotent-write policy: every attempted row lands in exactly one bucket)",
              expected=expected, actual=attempted, passed=attempted == expected)


def results_v2_attempted_matches_processed(attempted: Any, processed: Any) -> InvariantResult:
    """A Handoff-v2 executor persists one canonical row for every attempted
    candidate, including BROKEN/TIMEOUT/INFRA_FAIL outcomes that have no legacy
    positional-table row. Replays remain one attempted write per candidate and
    move from `inserted` to `already_present` through the unique key."""
    return _r("results_v2.attempted_matches_processed",
              "results_v2 attempted writes match processed candidates",
              expected=processed, actual=attempted, passed=attempted == processed)


def results_db_eq_inserted(db_total: Any, inserted: Any) -> InvariantResult:
    return _r("results_db.count_eq_inserted", "Results DB count matches inserted count",
              expected=inserted, actual=db_total, passed=db_total == inserted)


# --------- Plan-1 repeat (repeatScope=metrics) runtime count invariants ------- #
# docs/24 §2-§3 + Automation handoff #37 step 4. Active only for the verified Python local/metrics
# K>1 path; for that mode the count plan gives V = C (one canonical verdict per candidate) and
# I = C·K (measurement opportunities). These tie the executor's runtime tallies to the plan.
def repeat_processed_eq_verdicts(processed: Any, verdicts_v: Any) -> InvariantResult:
    """processed == V: the executor reaches a verdict for each candidate exactly once even when
    it re-measures the metric K times (repeatScope=metrics runs the verdict once, sample 0)."""
    return _r("repeat.processed_eq_verdicts", "Executor processed == V (full-verdict invocations)",
              expected=verdicts_v, actual=processed, passed=processed == verdicts_v)


def repeat_results_v2_attempted_eq_verdicts(attempted: Any, verdicts_v: Any) -> InvariantResult:
    """results_v2 attempted == V: one canonical results_v2 row per candidate (the verdict),
    NOT one per measurement opportunity — so repeatScope=metrics needs no 5-column sample index."""
    return _r("repeat.results_v2_attempted_eq_verdicts", "results_v2 attempted writes == V (verdicts)",
              expected=verdicts_v, actual=attempted, passed=attempted == verdicts_v)


def repeat_metric_rows_plus_missing_eq_opportunities(metric_rows: Any, missing: Any,
                                                     opportunities_i: Any) -> InvariantResult:
    """metric_rows + missing_measurements == I: every measurement opportunity is accounted for as
    an emitted metric row or an explicit missing measurement (docs/24 §2.2), so a noisy/missing
    sample is never silently dropped."""
    total = (metric_rows or 0) + (missing or 0)
    return _r("repeat.metric_rows_plus_missing_eq_opportunities",
              "metric_rows + missing_measurements == I (measurement opportunities)",
              expected=opportunities_i, actual=total, passed=total == opportunities_i)


def analyzer_input_matches_metrics(candidates: Any, metrics_lines: Any) -> InvariantResult:
    """Best-effort: corpus line count vs. candidate count.

    Marked WARNING (not CRITICAL): "eligible" metrics is a domain notion the
    launcher cannot authoritatively compute without the Analyzer-mode rework
    scheduled for STEP 38/39 — this is a visibility cross-check, not a gate.
    """
    return _r("analyzer.input_matches_metrics", "Analyzer input count corresponds to collected metrics",
              expected=candidates, actual=metrics_lines, passed=metrics_lines == candidates,
              severity=WARNING)


def bias_plan_schema_valid(applied: Any) -> InvariantResult:
    return _r("seed_bias.plan_schema_valid", "seed bias plan schema is valid when bias is applied",
              expected=True, actual=applied, passed=applied is True)


def bias_keeps_minimum_space(post_bias_estimate: Any, degenerate: Any = False) -> InvariantResult:
    ok = bool(degenerate) or (isinstance(post_bias_estimate, int) and post_bias_estimate >= 1)
    return _r("seed_bias.keeps_minimum_space",
              "seed bias keeps at least one estimated candidate or reports no-signal convergence",
              expected=">=1 or CONVERGED_NO_SIGNAL", actual=post_bias_estimate, passed=ok)


def seed_sha_matches_source(seed_path: Any, recorded_sha: Any) -> InvariantResult:
    actual = None
    try:
        actual = file_sha256(Path(seed_path)) if seed_path else None
    except OSError:
        actual = None
    return _r("seed_bias.seed_sha_matches_source",
              "consumed BundleSeed sha256 equals the bias plan lineage hash",
              expected=actual, actual=recorded_sha, passed=bool(actual) and actual == recorded_sha)


# --------------------- coverage / silent-exclusion guards --------------------- #
# Added for BUNDLE_TODO #4 (axis-coverage) and #2 (loud exclusion): a reduced/subset run can leave a
# whole axis-value un-exercised, and only code==0 candidates reach the corpus — so a systematically
# broken axis-value can vanish from the Analyzer with no alarm. These make both visible.
def subset_axis_coverage(declared: dict, exercised: dict) -> list[InvariantResult]:
    """WARN if a run (e.g. --limit/subset) leaves any declared axis-value un-exercised.

    declared:  {axis_name: [all declared values]}
    exercised: {axis_name: set/iterable of values actually run}
    """
    out = []
    for axis, values in declared.items():
        seen = set(exercised.get(axis, ()))
        missing = [v for v in values if v not in seen]
        out.append(_r(f"coverage.{axis}", f"every '{axis}' value is exercised by this run",
                      expected=list(values), actual=f"missing={missing}",
                      passed=not missing, severity=WARNING))
    return out


def no_axis_value_fully_excluded(axis_valid_counts: dict) -> list[InvariantResult]:
    """CRITICAL if some axis-value has candidates but 0 reach the corpus (valid==0) — a likely
    systematic defect (or too-tight oracle), not bad luck; don't let the class vanish silently.

    axis_valid_counts: {axis_name: {value: (valid_count, total_count)}}
    """
    out = []
    for axis, vmap in axis_valid_counts.items():
        excluded = [v for v, (valid, total) in vmap.items() if total > 0 and valid == 0]
        out.append(_r(f"exclusion.{axis}", f"no '{axis}' value is 100% excluded (0 valid of >0)",
                      expected="each value has >=1 valid candidate",
                      actual=f"fully-excluded={excluded}", passed=not excluded, severity=CRITICAL))
    return out


def verdict_histogram(codes: Sequence[Any]) -> dict:
    """Convenience: {code: count} over a run's verdict codes (for the loud executor/Analyzer summary)."""
    hist: dict = {}
    for c in codes:
        hist[c] = hist.get(c, 0) + 1
    return hist


# --------------------------------- enforcement -------------------------------- #
def enforce(results: Sequence[InvariantResult]) -> None:
    """Fail closed on the first failed CRITICAL invariant (STEP 6).

    WARNING-severity failures are left in the recorded list for the human/JSON
    output to surface, but do not stop the stage/run by themselves.
    """
    for r in results:
        if not r.passed and r.severity == CRITICAL:
            raise InvariantError(
                f"invariant {r.id} failed: expected {r.expected}, got {r.actual} ({r.description})")
