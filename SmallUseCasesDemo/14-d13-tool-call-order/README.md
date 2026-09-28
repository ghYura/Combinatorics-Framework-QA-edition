<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13a — Agent tool-call policy traces

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

Six approve/read/send orders, one or two adjacent send requests, read success or
partial failure, optional revocation and four local orchestrators produce 480
traces. Plan: 96 mandatory rows x 5 optional choices. Derived: 454 PASS / 26
DOMAIN_FAIL. The guarded controller passes every configuration.

Inert stubs demonstrate stale approval, sensitive output delivered before a tool
error, and duplicate effects. The oracle checks event prefixes and required
responses. There are no external model calls or real outbound actions.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d13a_20260928T091033Z` on Framework v6 (no change): mandatory Core 96 ×
optional revocation (absent + 4) = 480 at Reader/Executor. **454 PASS / 26 DOMAIN_FAIL** (verify 22/22).
- Failures by policy: guarded 120/0, sticky_approval 4 (unapproved_emit), success_only_taint 14 (tainted_emit),
  no_dedup 8 (duplicate_emit).
- Checks are prefix-based and policy-blind. The guarded reference responses rule out a deny-all pass.
- Five replays were byte-identical. All tools were inert local stubs.

