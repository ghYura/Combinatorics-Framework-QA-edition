<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D13b — Composed untrusted-content boundaries

**Status:** implemented and verified by one recorded campaign (see Results).

[Contract](CONTRACT.md) · [Frozen predictions](architect-derived.json)

A structured-content processor must preserve untrusted leaf origins when data is
wrapped, reordered or decoded. Native FW_Group and two brace levels construct
four contexts, crossed with three policies, three encodings and three marker
classes. Trusted work must complete while untrusted commands remain inert data.

Verified: 108 cases, 80 PASS / 28 DOMAIN_FAIL. The architecture
[plan](planning/plan/plan.json) conservatively reports BOUNDED [27,108]. The completed campaign
matches the frozen predictions. Local stubs expose trust
promotion through a wrapper or decoder, with no external model or outbound action.

## Results (the AI implementer, 2026-09-28)

[Results](evidence/results.md). Run `d13b_20260928T094930Z` on Framework v6 (no change).
- **Construction:** FW_Group and two M:N braces composed CHUNKS 2 × 4 codes, INNER 4 × 7 and ROOT 4 × 11; all
  four context expressions are intact in `fw_final`. The plan stays BOUNDED [27, 108], as recorded.
- **Counts:** Core, Reader and Executor each had 108 cases. **80 PASS / 28 DOMAIN_FAIL** (verify 29/29).
- **Failures by policy:** preserve_origin 36/0; wrapper_trust 12 (tool_result envelope promotes leaf
  commands); decode_trust 16 (json/base64 decoding promotes them). The 14 benign REF promotions pass.
- Five replays were byte-identical. All effects were local stubs.

