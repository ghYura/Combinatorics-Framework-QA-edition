# Combinatorics Framework — QA Edition

**Bundle is an executable combinatorial design-space and evidence engine. AI response testing is a
reference application.**

The engine — `Core -> optional Sieve -> Reader -> Executor -> Analyzer` — compiles a declarative
specification of a problem's degrees of freedom into executable candidates, runs each under an
explicit execution policy, and selects the non-dominated outcomes against declared objectives. It is
domain-neutral: it knows nothing about LLMs, control systems, or any other subject matter.

## QA-edition scope

This edition is a clean, history-free source snapshot focused on human-led QA engineering:
the engine, Control Plane, Analyzer, GUIs, QA/LLM test applications, exact oracles, scenarios, and
operational documentation remain. Historical handoffs, legal-option collections, provenance media,
and generated candidate corpora are deliberately omitted. Generators remain source; their bulk
runtime products — candidate corpora, workbooks, model weights — stay local and are git-ignored.

The one exception worth knowing before you run a generator: the small **run specs** some of them
emit under `generator_trunk/model_usecases/run/` *are* tracked, deliberately, so the exact spec a
result came from is reviewable. Re-running such a generator therefore rewrites a tracked file and
leaves the checkout dirty — `git diff` will show it, and `git checkout --` discards it. That is
expected, not a sign that something broke.

An individual QA engineer or student may use one complete personal installation, **AS IS** and free
of charge, for their own learning, exploration, research and professional practice. Inference-only
AI may help that user understand Bundle or author their scenarios; training a machine to reproduce
Bundle's Core → Reader → Executor capabilities is outside the grant. These terms are now operative
under the root [LICENSE](LICENSE); see [Licence](#licence) below.

Its distinguishing property is that a *result table*, not a value, is the unit of composition. A
brace `FW_(…)` joins two prior result tables and `FW_Group` re-combines one, so first-, second-,
third- and higher-order composition are engine capabilities available to any specification.

Everything around the engine — the Face 1 UIs, the gateway, campaign launchers, the AI testing
platform, and every SUT adapter — is replaceable control, presentation, or a reference application.
An application may restrict its own search space; it must never restrict the engine. The boundary is
declared as data, enforced by a test, and audited:

```bash
python generator_trunk/bundle_run.py architecture   # the layer model + dependency-direction gate
python generator_trunk/bundle_run.py coverage       # engine capability vs. what each app exercises
```

See [docs/30_ENGINE_FIRST_ARCHITECTURE.md](docs/30_ENGINE_FIRST_ARCHITECTURE.md).

The workspace supports Python and Java systems under test (SUTs), planning without a database, full
PostgreSQL-backed runs, optional visual constraint editors, and an optional HTTP/gRPC evaluation
gateway.

## See the engine directly

The smallest complete proof of advanced composition — no reference application, no LLM adapter, no
external SUT, standard library only:

```bash
python generator_trunk/engine_demo/run_direct_engine_smoke.py plan   # no database needed
```

`plan` is side-effect-free. It prints `⛔ BUDGET BLOCKING` for this scenario and still exits 0 —
that is expected: the brace chain's cardinality is genuinely `UNKNOWN` until Core runs, and budget
evaluation on the plan path is analysis-only, with `run` as the enforcement point.

The bounded full chain additionally needs **two PostgreSQL endpoints and their credentials**.
`--db-endpoint` is required and has no default; it selects ports *and* credentials from one source:

```bash
python generator_trunk/bundle_run.py deploy up                        # local stack
python generator_trunk/engine_demo/run_direct_engine_smoke.py run --db-endpoint deploy
```

Use `--db-endpoint manual --main-port PORT --results-port PORT` to target your own cluster, with
`BUNDLE_MAIN_DB_PASSWORD`/`BUNDLE_RESULTS_DB_PASSWORD` in the environment. The launcher prints the
resolved endpoint and the *source* of each setting (never a credential value) before it starts.

`FW_Group`, `FW_PermutR(2)` and a three-link nested-brace chain compose a fourth-order executable
record pipeline; an exact differential oracle judges it. See
[generator_trunk/engine_demo/README.md](generator_trunk/engine_demo/README.md).

## Quick start

One command, from nothing to a verified installation — clones both repositories side by
side, builds the Python and Java components, provisions the per-SUT environments, runs the
self-audits, and checks the documented smoke-test counts rather than merely exit status:

```bash
./QUICK_INSTALL_ALL.sh              # install + smoke tests (no database)
./QUICK_INSTALL_ALL.sh --with-db    # also start PostgreSQL and run the full pipeline
./QUICK_INSTALL_ALL.sh --help
```

It is idempotent, installs nothing system-wide, and picks free database ports so it cannot collide
with another checkout's stack.

To do the same steps by hand, or to understand what each one proves, follow
[QUICKSTART.md](QUICKSTART.md): a clean clone of both repositories, the
24-case no-database smoke, deterministic companion-SUT verification, and the optional local
database run.

## Repository map

| Path | Purpose |
| --- | --- |
| `Combinatoricslib3parallel/` | Shared combinatorial generation library |
| `Core_trunk/` | Expands workbook schedules into test cases |
| `Reader_trunk/` | Reads and materializes generated candidates |
| `Executor_trunk/` | Executes Python or Java candidates and records outcomes |
| `Analyzer_trunk/` | Ranks harvested metrics and builds Pareto fronts |
| `generator_trunk/bundle/` | Engine control plane: planning, budgets, contracts, policy, lifecycle |
| `generator_trunk/engine_demo/` | Direct engine demonstration — self-contained, no application on the path |
| `generator_trunk/AI_combi_testing_platform/` | Reference application (experimental): AI response testing |
| `generator_trunk/` (rest) | Specifications, CLIs, orchestration, gateway, tests, and optional UIs |

Build products and downloaded dependencies are intentionally not committed. Maven and pip resolve
from checked-in manifests; the optional npm editors additionally use checked-in lockfiles.

## Prerequisites

- Linux or another POSIX-like environment
- JDK 25 and Maven (some modules target Java 21; Reader and Executor target Java 25)
- Python 3.11 or newer
- PostgreSQL client tools (`psql` and `pg_isready`)
- **Two clean PostgreSQL instances, up and running**, for full runs and the full test suite — see below
- Node.js 18 or newer and npm only for the optional React/Blockly editors
- Docker with Compose only for the optional local database stack
- A usable rootless Docker or Podman runtime for generated-code sandbox profiles

The first Maven, pip, or npm build may download dependencies.

### The two PostgreSQL instances

| Role | Endpoint | Written by |
|---|---|---|
| **main** | `127.0.0.1:5433` | Core materializes the combinatorial space into `fw_final` |
| **results** | `127.0.0.1:5432` | Executor writes candidate results |

The connecting role needs `CREATEDB` (`bundle doctor` verifies this). Confirm both endpoints before
a full run:

```bash
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5432
```

**Start from clean instances.** No Bundle databases or tables from an earlier session, and no
pre-existing `fwbundle-main-db` / `fwbundle-results-db` deploy containers. Leftover state seldom
raises an error — it makes tests skip or reuse stale data, which is easily mistaken for success.
Clear deploy containers with `python generator_trunk/bundle_run.py deploy down`.

Setup instructions for both instances, including a route that needs no `sudo`, are in
[`docs/03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md`](docs/03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md).

## Start with the invitation wizard

New users can begin with a guided combination-thinking coach instead of authoring syntax. It proposes editable factors and interactions, flags missing relationships, estimates raw growth, explains optional stress actions, and routes to real use cases.

```bash
python -m pip install -e '.[ui]'
cd generator_trunk
python3 intake/serve_face1.py          # original guided composer
python3 -m face1_new.app               # workbook-first interface with Guided start tab
```

Both interfaces require confirmation before applying suggestions and keep constraints honest: relationship questions must still be encoded in Face 2. The companion SUT repository contains `combination_thinking_tutor` as the deterministic introductory lesson.

## Build and no-database smoke test

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,science]'
mvn -q clean package

python generator_trunk/bundle_run.py plan \
  generator_trunk/usecases/event_order \
  --out /tmp/framework-plan
```

The plan command is self-contained: it needs no database or external SUT and should produce a bounded 24-candidate plan.

Useful discovery commands:

```bash
python generator_trunk/fwgen_cli.py --help
python generator_trunk/fwgen_cli.py list --specs generator_trunk/specs
python generator_trunk/bundle_run.py --help
python generator_trunk/bundle_run.py inventory
python generator_trunk/bundle_run.py hygiene
python generator_trunk/bundle_run.py iterate --help
```

Current execution controls are discoverable from `bundle_run.py --help`: `--repeat K` with
`--repeat-policy`/`--repeat-scope`, `--candidate-sink`, `--executor-pool`, and the
`--seed-output`/`--seed-from` feedback loop. `bundle iterate` runs that feedback loop for a bounded
number of iterations and requires explicit Analyzer goals.

## Local PostgreSQL stack and a full run

Install the deployment extra, validate the checked-in local-only configuration, and start the two database containers:

```bash
python -m pip install -e '.[deploy]'
python generator_trunk/bundle_run.py deploy validate
python generator_trunk/bundle_run.py deploy up
python generator_trunk/bundle_run.py doctor --deploy
```

`deploy up` starts exactly the two database containers. The compose profile also declares an
optional Adminer monitoring service — `deploy validate` validates it, but it is opt-in and is only
started by `deploy up --monitoring` (web UI on `127.0.0.1:18080`).

`deploy up` creates the ignored `generator_trunk/deploy/.env` on first use. It stores both a
generated local password and checkout-scoped volume names, so a re-downloaded checkout does not
silently attach older clusters initialized with another password. Success includes authenticated
SQL probes; on a legacy credential mismatch, containers are stopped and all data is preserved. The
doctor command consumes that file automatically. Pipeline runs do not, so export its values before
running:

```bash
set -a
source generator_trunk/deploy/.env
set +a

export BUNDLE_MAIN_DB_HOST=127.0.0.1
export BUNDLE_RESULTS_DB_HOST=127.0.0.1
export BUNDLE_MAIN_DB_PORT="$BUNDLE_MAIN_DB_HOST_PORT"
export BUNDLE_RESULTS_DB_PORT="$BUNDLE_RESULTS_DB_HOST_PORT"
export BUNDLE_MAIN_DB_USER="$POSTGRES_USER"
export BUNDLE_RESULTS_DB_USER="$POSTGRES_USER"
export BUNDLE_MAIN_DB_PASSWORD="$POSTGRES_PASSWORD"
export BUNDLE_RESULTS_DB_PASSWORD="$POSTGRES_PASSWORD"

python generator_trunk/bundle_run.py \
  generator_trunk/usecases/event_order \
  --db event_order_demo \
  --lang py \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in event_order fixture' \
  --run-id event-order-001 \
  --analyzer 'charges:min'
```

There is no default execution profile, so the three policy flags are not optional: `event_order` is a
reviewed, checked-in fixture, which is what `trusted-local` is for. For generated or otherwise
untrusted candidates use `--execution-policy-profile generated-default` instead — it is sandboxed and
needs no acknowledgement. `--run-id` is optional (one is minted automatically) but makes the run easy
to name afterwards:

```bash
python generator_trunk/bundle_run.py report event-order-001
```

That renders the run as a single self-contained HTML page — verdicts, stage timeline, the Analyzer's
non-dominated front and provenance — reading only what the run already recorded, so it also works on
a run that failed.

The main database role must have `CREATEDB`. Stop the local stack while preserving its data with
`python generator_trunk/bundle_run.py deploy down`. If a legacy `.env` no longer matches its
volumes, restore the original `.env`; use `deploy down --volumes` only when that local data is
explicitly disposable. See `bundle_run.py doctor --help` and `bundle_run.py deploy --help` for
additional configuration.

## Systems under test

Portable SUT mappings live in `generator_trunk/sut_paths.py`. The default SUT root is `suts/` inside this repository. To keep SUT checkouts elsewhere:

```bash
export BUNDLE_SUT_ROOT=/absolute/path/to/systems-under-test
```

Relative values are resolved from the repository root. `SIEVE3D_ROOT` and `SIM_DIR` remain available as narrower overrides for their respective integrations. The `event_order` smoke plan does not require an external SUT.

## Security profiles

**There is no default execution profile.** A run refuses to start until one is chosen; `bundle_run.py plan` needs none. Choose `generated-default` for generated, imported or otherwise untrusted candidates — it is sandboxed and fails closed if its container backend is unavailable.

`trusted-local` is intentionally unsandboxed: it inherits the host environment, filesystem and network. Selecting it requires an explicit origin classification and a recorded reason, both persisted in the run manifest and re-verified on resume:

```bash
python generator_trunk/bundle_run.py SPEC_DIR \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'why this code is reviewed and trusted'
```

Origins `generated`, `imported-untrusted` and `network-facing` are refused `trusted-local` outright — an acknowledgement records a decision, it does not grant a permission.

For untrusted generated Python or Java candidates, use:

```bash
python generator_trunk/bundle_run.py SPEC_DIR \
  --execution-policy-profile generated-default \
  [other options]
```

`generated-default` requires a usable rootless container runtime and a local `python:3-slim` image; it disables candidate networking and fails closed if isolation is unavailable. The `networked-api-probe` profile additionally requires an explicit network allowlist.

The live `grpc` candidate transport is deliberately narrower than the file transports: it is
currently Java-only, verdict-mode-only, Handoff-v2-only, and restricted to `trusted-local`. The
Reader targets `127.0.0.1:50061` by default, while the current receiver is constructed from a port
rather than a loopback-only bind address. This channel is plaintext and unauthenticated, so enforce
host firewall/interface isolation and never route it onto an untrusted network. Java executor
pooling is likewise a specialized
path: `--executor-pool N` requires Java, `loose-files`, Handoff v2, verdict mode, and `--repeat 1`.

## Optional interfaces

Face 1 serves the real local pipeline on loopback. `--no-browser` prevents automatic browser launch:

```bash
python -m pip install -e '.[ui]'
bash generator_trunk/intake/run_face1.sh --no-browser
(cd generator_trunk && python -m face1_new.app)  # workbook-first interface
```

Build the optional constraint editors without committing downloaded packages or output:

```bash
npm --prefix generator_trunk/constraints/react_flow ci
npm --prefix generator_trunk/constraints/react_flow run build
npm --prefix generator_trunk/constraints/blockly_when ci
npm --prefix generator_trunk/constraints/blockly_when run build
```

Install and inspect the optional gateway:

```bash
python -m pip install -e '.[gateway]'
python generator_trunk/bundle_gateway.py --help
```

The checked-in gateway stubs are generated by `generator_trunk/bundle/gateway/codegen.py`, which enforces the exact `grpcio-tools` version declared in `pyproject.toml`.

## Verification

```bash
python -m pytest -q \
  generator_trunk/test_bundle_inventory.py \
  generator_trunk/test_bundle_hygiene.py \
  generator_trunk/test_bundle_doctor.py

bash Analyzer_trunk/run-tests.sh
```

`generator_trunk/test_bundle_deploy.py` includes a live Docker acceptance test whose teardown removes its named test volumes. Run that file only in an isolated development environment.

For the comprehensive (and intentionally heavy) Python suite:

```bash
python -m pip install -e '.[test-full]'
python -m pytest
```

`test-full` installs UI, browser, container, and ML integrations. When those services are available, the comprehensive suite may exercise them; use an isolated test host.

## Licence

This edition is licensed under the **[Business Source License 1.1](LICENSE)**.

| | |
|---|---|
| Licensor | Yurii Baranov, Kyiv, Ukraine |
| Change Date | **2030-08-08** |
| Change Licence | **GNU AGPL v3.0-only** |

**Free for an individual.** A QA engineer, tester or student may run one concurrently active
installation, AS IS and free of charge, for their own learning, exploration, research and
professional practice — including work in the course of their own employment or studies. Copying,
modification, redistribution and any non-production use are permitted to anyone holding a copy.

**A separate licence is required** to deploy Bundle as shared infrastructure of a company or
institution, embed it in a product or service, use it to serve third parties, or operate it by an
AI system without a real human QA engineer directing it. See
[COMMERCIAL_LICENSING.md](COMMERCIAL_LICENSING.md).

**On the Change Date** — or the fourth anniversary of a version's first public distribution,
whichever comes first — that version becomes available under the AGPL-3.0-only and these
restrictions cease to apply to it. [SUCCESSION.md](SUCCESSION.md) explains why that guarantee
exists.

The author's statement of intent, the third-party scope and the trademark position are in
[NOTICE.md](NOTICE.md). The earlier personal-use and output drafts in
[docs/qa_edition/](docs/qa_edition/README.md) are retained as a record of intent; where they differ
from `LICENSE`, `LICENSE` governs. The licence text has not yet had qualified legal review.
