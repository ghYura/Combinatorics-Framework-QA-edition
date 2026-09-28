<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D10 contract v1 — sensor selection and fault diagnosis

Frozen before implementation; apply ../README.md, G1–G7. Questions:
detect a fault, identify its observable class, minimize fixed acquisition cost,
or identify adaptively. These are distinct objectives. The fixture models four
binary status flags and eight direct/parity probes, with synthetic fault modes.
All costs are one unit per queried sensor. No field calibration is claimed.

## Faults, sensors and equivalence

Let flags (a,b,c,d) be bits 0,1,2,3 of an integer code, least significant bit
first. The 12 fault labels map to six states:

| Class | Fault labels | Code |
|---|---|---:|
| 1 | F01, F02 | 1 |
| 2 | F03, F04 | 2 |
| 3 | F05, F06 | 4 |
| 4 | F07, F08 | 8 |
| 5 | F09, F10 | 7 |
| 6 | F11, F12 | 15 |

Class 0 is healthy H0, code 0. H0 is a declared reference/control, not a thirteenth
campaign hypothesis. Exercise it in a focused DB-free control and label its
all-zero signature separately from Framework observations.

Sensors in bit-mask order S0..S7 return respectively:
`a, b, c, d, a XOR b XOR d, a XOR c XOR d, b XOR c XOR d, a XOR b XOR c`.
Each fault injection initializes a fresh flag state. Query only selected sensors,
once each in index order. Preserve both labels of every pair even though they
produce identical signals. Full eight-sensor equality defines observational
equivalence; identification can return the class and BOTH member labels, never
claim to distinguish its two causes. Subsets can merge further classes.

Population: every subset of eight sensors × all 12 fault labels = **3072** cases,
K=1. Identity `S=eight_bits|H=Fxx`. Empty subset produces zero cost, [] readings
and an empty signature string. All cases predict PASS when the sensor computation
matches its oracle. An uninformative selection is a diagnostic design limitation,
not a faulty sensor calculation or a DOMAIN_FAIL.

Record mask, selected indices, sensor_cost, fault, latent_bits, readings,
signature (selected readings concatenated), oracle agreement, verdict and source/
candidate identity. Follow architect-derived.json's ordering and field meanings.
Separate SUT flag injection and probe functions from an independent literal
7×8 reference signature table. Neither reads frozen case results. Unexpected
exceptions/missing data are infrastructure/setup failures. Incorrect readings
against the declared sensor model are DOMAIN_FAIL.

## Framework and measurement matrix

Primary demo.xlsx with equivalent spec.toml: mandatory HEAD, SENSORS (position 2),
FAULT, TAIL. HEAD initializes an empty selection; SENSORS contains select(0)..select(7).
Use explicit `FW_Subsets -> FW_Subsets` for SENSORS; other sheets use
`Combi(1)->Combi(size)`. FAULT has twelve distinct fault("Fxx") fragments;
do not collapse equal latent states into one fragment. No optional/sieve/scenario
axis is needed. The later Subsets pass regenerates the empty subset.

Derived work: 256 first-pass subsets, 3^8-1=6560 second-pass emissions before
DISTINCT, then 256 distinct subsets. Record measured support and label unmeasured
emission counts Derived. Both actual-input plans must be EXACT 3072. Raw Core,
post-Core, Reader/rendered and Executor original attempts must all be 3072,
optional multiplier 1. Confirm 12 empty-subset cases and all 12 full-subset cases.
Use SENSORS position 2 only as the legacy verdict carrier, not causal attribution.

Archive a complete observed subset/fault matrix. Before analysis reject missing,
duplicate, unknown or non-PASS observations; require each subset's readings to
equal the projection of that fault's observed full signature. Infer full-signature
equivalence classes from observations and confirm the frozen pairs. The healthy
reference extends the six measured classes to seven diagnosis classes.

## Fixed suites, adaptive queries and noise

For each of 256 masks, derive all seven projected class signatures, all 21
pairwise Hamming distances, cost and these obligations:

- Detection: every fault class differs from H0 (a killing suite).
- Separation: all seven class signatures are distinct, minimum distance >=1.
- One known erasure: minimum distance >=2.
- One wrong binary reading at an unknown position: minimum distance >=3.

Minimize (cost, mask lexicographically), retaining all minimum-cost ties. Frozen
predictions: detection cost 2, mask 00000011, 201 feasible masks; separation cost
4, mask 00001111, 149 feasible; erasure cost 6, mask 00111111, 37 feasible;
wrong-reading cost 7, mask 01111111, 9 feasible. Certify minimality by all 256
masks, not just a successful witness. On unquotiented fault labels the full
minimum distance remains zero because each alias pair is inseparable.

For noiseless adaptive diagnosis, a belief B is a nonempty subset of the seven
classes. T(singleton)=0; otherwise minimize over sensors that split B:
`T(B) = min_s [1 + max(T(B_s=0), T(B_s=1))]`. Break ties by smallest sensor index.
Save all 127 belief-state optima, the resulting tree and traces for all seven
classes. Every leaf must name the entire equivalence class. A sensor already
queried cannot split a descendant belief. The optimum worst-case query cost is
3, between detection's 2 and fixed separation's 4. This is an offline certified
policy using observed signatures, not additional Framework runs or a measured
interactive service. No class probabilities or expected-cost objective apply.

For the chosen erasure suite, decode every class word unchanged and with each
one position replaced by '?': 49 controls. For the chosen wrong-reading suite,
decode every class word unchanged and with each one bit flipped: 56 controls.
Erasure decoding retains words agreeing at known positions; error decoding
retains words at Hamming distance <=1. Every retained set must contain exactly
the true CLASS. Store these finite proofs, separate from campaign attempts.
Do not claim the adaptive tree handles noise or that one-erasure and one-error
tolerance combine into a joint guarantee.

## Independent review and demonstration

Separate runtime, builder, bounded runner, diagnosis analysis, verifier and replay;
no imports from another example. Generated candidates are self-contained.
The verifier must not import SUT/oracle/runtime/analysis/derive.py or execute
candidate sources. Independently recompute all identities and readings, fixed
suite certificates, all DP choices and noise controls from observed data; compare
to frozen predictions. Verify source inlining and hashes, workbook/TOML/Core
input equivalence, stage counts and one original attempt per identity. Analysis
input guards need focused missing/duplicate/corrupted-reading tests. Also test
the healthy control, empty selection and refusal to identify within an alias pair.

Explain with actual observations: detection mask 00000011 gives signature 01 for
both F01 and F09, distinguishing them from health but not each other. Separation
mask 00001111 gives 1101 versus 0001. Even all eight sensors cannot distinguish
F01 from F02. Show the adaptive tree and its seven paths; connect extra probes
to erasure/error tolerance. No universal optimum beyond this model is implied.

Replay exactly five cases, separately from the original attempts:

- S=00000011|H=F01
- S=00000011|H=F09
- S=00001111|H=F09
- S=11111111|H=F02
- S=00000000|H=F01

Archive commands, input/source/build hashes, both plans, Core tables/dictionary,
all sources/records, observed-matrix diagnosis certificates, verifier output and
concise results.md. Run once on fresh as0927_d10_* databases on both ports,
generated-default, one worker, K=1, JVM <=2 GB. Budgets: mandatory rows 3200,
final candidates 3200, disk 150000000 bytes, wall 7200 seconds. Preflight current
disk/ownership and record retained sizes. Preserve databases and prior artifacts.
Focused DB-free tests only; no broad/live-test sweep, full fixture, external calls,
cleanup, commit or push. Necessary evidenced Framework fixes remain authorized;
otherwise preserve v6. Send EEST-named Markdown here. **Do not start D11.**
