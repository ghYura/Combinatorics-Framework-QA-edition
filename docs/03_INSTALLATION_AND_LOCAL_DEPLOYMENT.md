# 03 — Installation and Local Deployment

> **Linux-specific.** The sandbox backends and the deploy stack assume Linux. Verified on Ubuntu
> 24.04 (kernel 6.17), 2026-06-11.

## Prerequisites (verified versions)

| Tool | Verified | Used by |
|---|---|---|
| Python | 3.12.3 | control plane, Generator, Executor, sieve |
| `pg8000` (pure-Python driver) | present | control plane / Executor DB access |
| Java | **25** — JDK 25 is required to build the reactor at all | Core/Analyzer/shared libraries target release 21, Reader/Executor target release 25, so a JDK 21 host builds the first half and fails the second. The dated evidence host ran 21 against a tree whose Reader/Executor still targeted 21. |
| Maven | 3.9.15 | offline component builds |
| PostgreSQL | 18.4 host (16.9 deploy containers) | **two clean instances required** — main `:5433` + results `:5432`, see below |
| Docker | 29.5.3 (rootless) | secure sandbox + deploy stack |
| bubblewrap (`bwrap`) | present | alternative daemonless sandbox |

### Required: two clean PostgreSQL instances

This is a hard prerequisite for any full chain run and for the complete test suite. The two
endpoints are separate instances, not two databases in one cluster:

| Role | Endpoint | Written by |
|---|---|---|
| **main** | `127.0.0.1:5433` | Core materializes the combinatorial space into `fw_final`; the sieve deletes invalid rows here |
| **results** | `127.0.0.1:5432` | Executor writes candidate results, which the Analyzer then reads |

The connecting role needs `CREATEDB`; `bundle doctor` reports this as BLOCKING when it is missing.
Create them with Option A or Option B below, then verify:

```bash
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5432
```

**Why "clean" matters.** Leftover Bundle databases, tables or `fwbundle-main-db` /
`fwbundle-results-db` deploy containers rarely cause a visible failure. Instead they cause tests to
*skip*, or a run to reuse rows from an earlier session — both of which look like success in a
summary line. Before a verification run, clear any prior deploy stack:

```bash
python generator_trunk/bundle_run.py deploy down
```

**What the two instances change in the test suite.** With both databases running and no leftover
deploy containers, the full suite reports:

```
1375 passed, 2 skipped, 12 subtests passed
```

Only two skips remain, and both are opt-in by design: the ML extra is not installed
(`pip install -e '.[ml]'`), and `FACE1_E2E_LIVE` is unset.

Without the databases, roughly thirty tests skip instead of running — the constraints/sieve paths,
the GUI end-to-end flows, the telemetry catalog, the evaluation gateway, the benchmarks, and the
`results_v2` schema and policy columns. Those are precisely the parts of the chain that cannot be
verified without a real database, so a green summary from a run without them proves considerably
less than the same line with them.

Two further skips appear when a previous deploy stack is still up: the deploy acceptance tests
decline to run rather than act on containers whose ownership they cannot prove. Run
`python generator_trunk/bundle_run.py deploy down` first if you want them to execute.

Absent infrastructure is reported as a **skip**, never as an error or a failure — a reachable but
misbehaving server is what counts as a failure.

The dated verification host used system Python packages directly. For a fresh checkout, use the
repository-local virtual environment and extras shown in the root `README.md`; this avoids changing
the host interpreter. `pg8000` is the core runtime driver, while optional gateway, UI, and example
SUT dependencies are supplied by the corresponding `pyproject.toml` extras or SUT manifests.

Docker is reached via:

```bash
export PATH="$HOME/bin:$PATH"
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
```

Read the repository's canonical
[Docker and internal-networking policy](10_SECURITY_AND_SANDBOXING.md#docker--internal-networking-local-only)
first: bind published ports to `127.0.0.1` only, use internal/user-defined networks, and never expose
containers to the LAN/Internet. This policy preserves the applicable restrictions from the historical
Docker notice, which is not shipped as a separate source file.

## Credentials (no secrets in source)

The Bundle never defaults a password in code. Load host-database credentials from an approved
shell secret source, then export these names; values are deliberately omitted here.
`bundle doctor`/preflight fail closed with a precise message if they are missing:

```bash
export BUNDLE_MAIN_DB_PASSWORD
export BUNDLE_RESULTS_DB_PASSWORD
```

(Also settable via `--main-db-password`/`--results-db-password` or a config file; precedence is
CLI > environment > config file > defaults.)

## Component builds (offline after dependency warm-up)

The first root build may download Maven dependencies. Once the local Maven cache is populated,
the component commands below can be repeated offline.

From `bundle inventory` — each component's canonical build and the artifact it produces:

```bash
# Java modules (offline only after Maven dependencies have been warmed):
(cd Core_trunk     && mvn -o -q -DskipTests -Dexec.skip=true package) # → target/migrated-project-1.0-SNAPSHOT.jar
(cd Reader_trunk   && mvn -o -q -DskipTests -Dexec.skip=true package) # → target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar
(cd Analyzer_trunk && mvn -o -q -DskipTests -Dexec.skip=true package) # → target/heuristic-analyzer-flatlaf-1.0.0.jar
(cd Executor_trunk && mvn -o -q -DskipTests package)
# Generator and the Python Executor are interpreted Python; Executor also has the Java build above.
```

Confirm artifact identity any time with:

```bash
python3 generator_trunk/bundle_run.py inventory --out /tmp/inventory.json
```

This prints a `bundle.inventory/v1` matrix (component, kind, version, artifact sha256, build cmd)
and the toolchain versions. `--baseline <file> --policy {warn,block}` compares against a known-good
inventory; `--sbom` adds an SBOM if the toolchain supports it.

## Option A — host PostgreSQL (the canonical setup)

Two local clusters, localhost-only:

- **main** DB on `127.0.0.1:5433` (Core fills `fw_final` here)
- **results** DB on `127.0.0.1:5432` (Executor writes results here)

```bash
sudo pg_ctlcluster 18 main start
sudo pg_ctlcluster 18 my_second_instance start   # or your results cluster
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5432
```

The role needs `CREATEDB` (doctor checks this).

**Option A needs root.** `pg_ctlcluster` will not start a cluster as an unprivileged user, so on a
host where you have no `sudo` — a shared machine, a locked-down CI image, an unattended session —
this route is unavailable no matter how correctly PostgreSQL is installed. `pg_lsclusters` will still
list the clusters, and `doctor` will still report the ports as BLOCKING, which reads like a
configuration error rather than a permission one. Use Option B, or the "your own cluster" route in
[QUICKSTART.md](../QUICKSTART.md) §6, when that is the case.

## Option B — local Docker deploy profile (one command)

`generator_trunk/deploy/docker-compose.yml` uses readable version tags plus immutable registry
digests for PostgreSQL and Adminer. It provides two DBs (+ optional monitoring) on
**127.0.0.1-only** ports `15433`/`15432`/`18080` that do **not** clash with a host PostgreSQL.
Secrets and checkout-scoped engine volume names come from `deploy/.env` (rendered from
`.env.template`; never commit a real `.env` — it is git-ignored). Scoped volumes prevent a new
password from being attached to an older PostgreSQL cluster. Container names and ports remain
host-wide, so only one checkout's stack can run at once; ownership preflight refuses to replace or
remove another checkout's resources.

```bash
python3 generator_trunk/bundle_run.py deploy validate    # checks loopback binding, pinned images, healthchecks
python3 generator_trunk/bundle_run.py deploy up          # start DBs; require port + authenticated SQL health
python3 generator_trunk/bundle_run.py deploy status
```

`deploy up` creates the ignored `generator_trunk/deploy/.env` on first use, writes it with mode
`0600`, and generates its local password and volume names internally. It reports success only when
both databases accept an authenticated `SELECT 1`; a listening port alone is not sufficient. Do
not put a real password in `.env.template` or expect a pre-exported `POSTGRES_PASSWORD` to
replace the generated file. Load the generated settings before a pipeline run:

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
```

`deploy up --monitoring` adds Adminer at `127.0.0.1:18080`. **`down` preserves data by default**
(verified: "data PRESERVED (volumes kept)").

Stop the containers while preserving data with
`python3 generator_trunk/bundle_run.py deploy down`. An older `.env` without scoped names keeps
using the legacy fixed volumes. If those credentials do not match, `deploy up` stops its
containers, preserves the volumes, and tells you to restore the original `.env`. Only use
`python3 generator_trunk/bundle_run.py deploy down --volumes` when those local databases are
explicitly throwaway; the deletion is permanent.

The environment mapping above points pipeline runs at the deploy ports. The equivalent explicit
flags are `--main-port 15433 --results-port 15432`.

## doctor & troubleshooting

```bash
python3 generator_trunk/bundle_run.py doctor                 # host config
python3 generator_trunk/bundle_run.py doctor --deploy         # deploy stack ports
python3 generator_trunk/bundle_run.py doctor --json /tmp/doctor.json
```

`doctor` reports OK / WARNING / BLOCKING for: Python+pg8000, Java, Core/Reader jars (path, version,
sha256), Analyzer build+classpath, **both** DB roles (host:port, version), `CREATEDB` privilege,
scratch writability/free space/inodes, container runtime, sandbox backend availability, and the
component inventory. It creates nothing in any production DB and never prints secret values; exit is
non-zero only on a BLOCKING check. A verified-good host run shows `overall: OK` with all checks
green. See [12_OPERATIONS_AND_TROUBLESHOOTING.md](12_OPERATIONS_AND_TROUBLESHOOTING.md) for failure
playbooks.

## Live gRPC transport prerequisite

No external gRPC service is required: the launcher starts the Java Executor receiver before the
Reader streams candidates. The current path requires JDK 25, `--lang java`, verdict mode, Handoff
v2, and the explicit `--execution-policy-profile trusted-local` plus its required
`--candidate-origin` and `--acknowledge-trusted-local`; Reader targets `127.0.0.1:50061` by default.
The receiver separately binds the explicit `grpc_bind_host` (default `127.0.0.1`) and refuses a
wildcard or non-loopback address. The channel still has no TLS or application authentication, so
keep it local and treat host firewall/interface isolation as defense in depth.
