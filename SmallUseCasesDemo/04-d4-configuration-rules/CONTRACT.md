<!-- SPDX-License-Identifier: BUSL-1.1 -->
# D4 contract v1 — configuration legality and optional assembly

Implement under this folder using Framework v4 accepted in D3. Follow the shared
protocol and author decisions. Preserve prior examples; do not import their
runtime. This is a deterministic local telemetry-request adapter, with no network.

## Population and rules

Mandatory factors: env={dev,prod}, mode={batch,live}, transport={http,https},
features=exactly two distinct members of {audit,cache,gzip}, workers={1,2}.
Optional DEBUG has one enabling fragment; absence means false. This deliberately
excludes other feature cardinalities. Three separate policies: correct,
drops_gzip, ignores_debug_rule. Uniform weight per structural case, K=1; do not
infer production frequencies or collapse different configurations by equal output.

Freeze these independent legality rules, in this order:

| ID | Invalid configuration | Required bond form |
|---|---|---|
| R1 | prod with http | forbid pairs over ENV, TRANSPORT |
| R2 | live with cache selected | forbid sets over MODE, FEATURES |
| R3 | live with workers<2 | require when over MODE.live and WORKERS.n |
| R4 | prod with any feature outside {audit,gzip} | mapping ENV -> FEATURES allowed set |
| R5 | batch with audit selected and workers<2 | require ordinal assert on WORKERS, contextual MODE/FEATURES condition |
| R6 | prod with DEBUG present | forbid pairs over ENV, DEBUG; deferred to Reader |

R4 leaves dev unconstrained. R5 declares WORKERS ranks [workers(1);,workers(2);],
requires >= the second value, and uses an all-condition: MODE=batch AND FEATURES
has audit. This is an ordinal dependency, not an execution-order bond. R3's
predicate is MODE.live == 0 or WORKERS.n >= 2. Do not encode SUT outcomes as bonds.

## Adapter and oracle

Input is one configuration. First validate it; if invalid, reject with the sorted
violated-rule IDs and no request envelope. Otherwise emit a request envelope:
URL = transport + "://telemetry.invalid/" + mode, workers unchanged, headers and
body as below. The fixed original body is UTF-8 bytes `{"sensor":7}\n`.

- audit: X-Audit="1"; cache: Cache-Control="max-age=60".
- gzip: Content-Encoding="gzip", body gzip-compressed with mtime=0.
- Without gzip: Content-Encoding="identity", original body.
- DEBUG present: X-Debug="1"; otherwise that header is absent.

The host name is illustrative; never send the envelope. Record binary body as
base64. No extra headers are part of this finite adapter contract.
The reference validates all six rules independently of the sidecar and SUT.
For accepted configurations check exact URL/workers/header map and that decoding
according to the required encoding yields the original bytes; do not compare
gzip container bytes across Python versions. Wrong acceptance, rejection, header
or payload is DOMAIN_FAIL. Unexpected exceptions/setup failures are BROKEN.

drops_gzip keeps correct validation but emits identity encoding and raw body even
when gzip is selected. ignores_debug_rule omits R6 from validation and otherwise
behaves correctly. The reference must not read the policy. Check all outputs,
retaining acceptance failures separately from transformation failures.

## Framework construction and campaigns

Main sheet order: HEAD, IMPL, ENV, MODE, TRANSPORT, FEATURES, WORKERS, DEBUG, TAIL.
IMPL is position 2 for the legacy verdict carrier. Use self-contained atoms such
as env("dev");, mode("live");, feature("audit");, workers(1); and debug();.
All atom strings must be whitespace-free and consistent in workbook, params and
bonds; use FW_SheetNames endings for final newlines. FEATURES must use
FW_Combi(2) -> FW_Combi(size), producing three unordered pairs without empty-row
semantics. Other factors use explicit identity-controlled selection. DEBUG is
FW_Optional, one row. HEAD initializes debug=false and an empty feature set.
Never enumerate the main complete configurations as a catalogue.

Build matching TOML and primary XLSX+native companion inputs. Freeze both plans,
effective chains and sidecar provenance. Explain the rules before the
main run; retain live per-rule effects and compare with independent enumeration. A bounded
planner result is acceptable if honestly labelled and within the budget.

Derived main counts: raw fw_final=144, fw_opt1=1; unconstrained assembled support
288. R1–R5 sequential mandatory survivors: 144,108,72,63,51,36. Standalone raw
matches: 36,48,36,48,24; do not sum overlapping removals. DEBUG/R6 must not remove
mandatory rows. Reader expands 36x2=72 assemblies and rejects exactly six under
R6, leaving 66 unique rendered/executed cases. There are 22 legal configurations
per policy. Expected outcomes: 48 PASS / 18 DOMAIN_FAIL, all failures drops_gzip.

Then run one separate unsieved controls campaign, with six preregistered invalid
configurations, each violating exactly one different rule, crossed with the same
three policies: 18 cases. An explicit CONFIG catalogue is appropriate for these
six controls only. Predicted outcomes: 17 PASS / one DOMAIN_FAIL, from
ignores_debug_rule accepting the R6 control. These are a separate population;
their legitimate rejection is PASS. Do not sieve them away.

Exact IDs, all 84 cases, configurations and predictions are frozen in
architect-derived.json. Do not change predictions to fit results.

## Coverage and demonstration

Independently certify the frozen nine-configuration greedy pairwise suite against
all 60 feasible pair obligations in the 22-configuration legal population. The
six axes are env, mode, transport, features, workers, debug; features is one
categorical unordered-pair level. Do not claim individual-feature t-wise coverage
or minimum suite size. Measure its detection by intersecting with main results;
no additional campaign is needed. Preserve feasibility and selection evidence.

Also evaluate an intentionally wrong extra bond OFFLINE: forbid gzip with either
mode (sets over FEATURES, MODE). It removes 54 legal main candidates and retains
12, hiding every observed drops_gzip failure. Report this changed denominator
and that the rule is wrong; do not alter the live campaign or its evidence.
Contrast this with the necessary separate invalid-input controls for R6.

Replay four cases only: correct and drops_gzip at dev/batch/https/cache+gzip/
workers1/debug0; and correct and ignores_debug_rule at the frozen R6 control.
Log replays as extra attempts. Show that a prod configuration without DEBUG
survives while the same mandatory row with DEBUG is filtered at Reader assembly.

## Evidence and limits

Provide independent SUT, reference, runtime, builder, runner, offline verifier and
replay tools. The verifier must not import the SUT/reference/runtime or execute
candidate sources. Check every record, sidecar rule truth table, rule overlap,
mandatory/optional supports, deferred removals, all rendered/executed identity
sets, pairwise certificate, and wrong-bond intersection. Archive source/input/
build hashes, commands, plans, logs, database exports and complete observations.
Keep illegal-input rejection distinct from broken infrastructure.

Run main then controls once each, fresh as0927_d4main_* and as0927_d4ctrl_* on both
ports; main uses --sieve, controls does not. Use generated-default, one worker,
K=1, JVM <=2 GB. Per-run budgets: mandatory rows 200, final candidates 300,
disk 100000000 bytes, wall 600 seconds. Preflight disk and database ownership.
Keep live tests opted out; focused DB-free tests only. No broad suite, full
canonical fixture, cleanup, commit, push or external request. Preserve databases.

Apply G1–G7 and send a concise EEST-named Markdown delivery. Supported optional
pairs must execute at the Reader boundary; do not weaken a bond to make it run.
Necessary Framework fixes remain authorized with minimal reproducer and scope.
No further approval is needed for this contract. Await review before starting D5.
