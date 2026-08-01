# Executed campaign evidence

## Complete six-tier campaign

On 2026-07-24 all 155,712 candidates reconciled: 25,292 PASS, 130,420 DOMAIN_FAIL, zero infrastructure/provenance outcomes, and a 370-candidate exact global Pareto front. Balanced winner `18006_0_0` used first-order `parallel_sum`, PID, P+relay branches, prefilter, and identity loop slots (control 91.817337; robustness 92.118710; stability 96.149969; settling 1.08 s; worst error 0.213506811; zero overshoot; effort 2.024234737).

## Full-battery smoke

Run `automation-00_smoke-20260723T212601Z` completed the entire Bundle chain:
48 generated = 48 executed = 48 Results rows, with 12 PASS and 36 DOMAIN_FAIL,
zero BROKEN/TIMEOUT/INFRA_FAIL, and a provenance-clean seven-point formal Pareto
front.

The strongest smoke class was balanced `cascade_velocity` with parallel PI/PID
branches and either gain or limiter post-processing: control score 79.876749,
robustness 78.634536, stability 88.799862, worst error 0.556632224, and effort
1.025851502. The short-grid nested delay variants exposed internal-terminal
blow-up and were correctly rejected.

Evidence: `/tmp/fw_work/automation-00_smoke-20260723T212601Z`.

## Brace-joined deep composition

Run `automation-04_brace_join-20260723T213217Z` proved the runtime-unknown brace
count: Core materialized 1,152 rows, Reader emitted exactly 1,152 candidates in
two shards, and the deterministic eight-worker Executor processed all 1,152 in
117.427 seconds. Results were 96 PASS / 1,056 DOMAIN_FAIL with zero infrastructure
outcomes. Analyzer produced a provenance-clean 24-point front.

The best stability/error variant was balanced first-order `parallel_sum` with a
`pi_filter` inner loop: stability 94.398020, worst error 0.307939311, and effort
1.474208235. The alternative front point traded stability/error for effort
1.570621867.

Evidence: `/tmp/fw_work/automation-04_brace_join-20260723T213217Z`.
