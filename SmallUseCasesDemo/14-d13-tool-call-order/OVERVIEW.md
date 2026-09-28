<!-- SPDX-License-Identifier: BUSL-1.1 -->
# Agent tool-call policy traces

**What it is.** A local agent-orchestrator simulation using inert tool calls.

**Problem shown.** A tool-using agent may perform a state-changing action before approval or after a policy-relevant event.

**How the Combinatorics Framework helps.** Generates call orders, repetitions, failures and optional approval events. Mechanical checks on the resulting traces expose actions performed at forbidden times.

**How correctness is checked.** Mechanical temporal predicates over recorded tool events and local canaries, independently of an agent's explanation.

**What this establishes.** The tools are stubs. These results validate the bounded orchestration example, not the safety of a live AI agent.

**Status.** Accepted demonstration; implementation and evidence reviewed. Verified: 480 traces, 454 PASS / 26 DOMAIN_FAIL; five replays and 16 tests passed.

[Detailed explanation](README.md) · [Contract](CONTRACT.md) · [Results](evidence/results.md)
