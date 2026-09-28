<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D2 contract v1 — streaming boundaries and EOF

Architecture: declarative payload/error/adapter/cut slots → Core → sieve → Reader →
Executor → complete observation export → independent offline verification.
Question: detect integration failures caused by byte boundaries and missing EOF.
The obligation is all declared segmentations; no suite reduction or repeats.

## Frozen inputs and expected results

Use exactly the six payloads, encodings and literal outputs in
[architect-derived.json](architect-derived.json). This freezes bytes as hex, not
platform-dependent encodings. Truncated payloads reject under strict policy and
produce the listed replacement text under replace; all other payloads produce
listed text under both policies. Check whole-stream decoding against those literal
expectations before using it as the relational reference.

Adapters:
- incremental: one decoder per case, decode every chunk with final=False, then
  decode an empty byte string with final=True; concatenate all returned text.
- per_chunk: independently decode each chunk with bytes.decode and concatenate.
- no_final: one incremental decoder, final=False for every chunk, omit final flush.

Normalize UnicodeError as rejection. Other exceptions are implementation/setup
errors. Compare completed text or rejection; partial emitted text and exception
offsets are outside this contract. Preserve actual error class for diagnosis.

Expected outcomes, independently calculated before the campaign:

| Adapter | PASS | DOMAIN_FAIL | Failure classification |
|---|---:|---:|---|
| incremental | 160 | 0 | none |
| per_chunk | 52 | 108 | 47 unexpected rejection; 61 wrong text |
| no_final | 120 | 40 | 20 unexpected acceptance; 20 wrong text |
| Total | 332 | 148 | 480 cases |

These are predictions, not execution evidence. Investigate disagreements; do not
change the oracle to force the totals. Record host and container Python versions.

## Framework input

Sheet order: HEAD, IMPL, PAYLOAD, ERRORS, CUT1…CUT5, TAIL. All use FW_Combi(1).
HEAD/TAIL are singleton fragments. IMPL has the three adapters; PAYLOAD has six
IDs; ERRORS is strict/replace; each CUT has 0/1. Bonded assignment strings have no
surrounding whitespace; put newlines in FW_SheetNames endings.

CUTi=1 cuts after byte i. Nonempty chunks only. A payload of length n must have
CUTi=0 for i>=n. Declare payload length n and cut bit as params. Five require
bonds, real_boundary_1…5, assert `CUTi.bit == 0 or PAYLOAD.n > i`, each explicitly
naming PAYLOAD and CUTi. No optional sheets. Raw product: 6×2×3×32=1152. Valid
segmentations: 4+16+8+4+32+16=80; final cases 80×2×3=480. Sequential survivor counts
are in architect-derived.json; count overlapping matches explicitly.

Deliver primary spec/demo.xlsx with native spec/demo.constraints.json and its
TOML authoring source. Both plans must preserve params, five rules and 1152→480.
Framework must construct/sieve cases; no prebuilt catalogue of complete programs.
Use self-contained candidates. IMPL is position 2: FW_VAR=0/2 is a verdict carrier,
not a cause. Begin TAIL with an ordinary runtime call before assigning FW_VAR.

## Implementation and evidence

Independent files in this folder: sut.py, oracle.py, runtime.py, build_spec.py,
run_demo.py, verify.py, replay.py, tests/, spec/, evidence/. Equivalent compact
organization is fine. Do not import D1's runtime or another AI's workspace.
Existing Framework code and generic integration patterns may be reused.

Emit case ID, payload hex/encoding, five bits/mask, actual chunk hex sequence,
error policy, adapter, reference and observed acceptance/text, failure class,
legacy verdict, and execution/source identities. Case ID format is frozen in
architect-derived.json: adapter|P=payload|E=errors|M=two-digit-lowercase-hex-mask.
Bit zero means CUT1. Concatenated nonempty chunks must reproduce the input.

The offline verifier must not import SUT/runtime/oracle or execute candidate
sources. Independently enumerate real cut subsets, pad phantom bits with zero,
parse candidate assignments, and reconcile decoded Core, Reader and Executor
identity sets. Check literal reference results and observed adapter outcomes via
an independently written checker. Verify all records, not just 332/148 totals.
Archive source/input/companion/build hashes and copies before any later changes.

Run one XLSX campaign: fresh as0927_d2_* on both ports, --sieve, generated-default,
K=1, one worker, JVM heaps <=2 GB. Limits: mandatory rows 2000, final candidates
600, disk 200000000 bytes, wall 1200 seconds. Zero unexpected infrastructure
outcomes. Keep live integration tests opted out; select DB-free tests only.

Show four witnesses: valid multibyte split with correct incremental output;
per-chunk failure on that split; truncated input with mask=00 showing missing EOF
under strict; the same boundary-free truncation under replace. Replay only these
and a relevant positive control, logging extra attempts separately. Explain why
covering internal cuts alone misses EOF. No stdlib defect or broader streaming
correctness claim is supported. Empty chunks, cancellation, concurrency and
cross-stream reuse are outside this finite contract.

Use ../README.md gates G1–G7. Deliver concise results.md, exact commands,
complete observations, case-set and stage reconciliation, focused tests and
witness evidence. No broad test sweep, commit, push or DB cleanup. Necessary
Framework changes remain authorized but require a recorded reproducer and scope.
