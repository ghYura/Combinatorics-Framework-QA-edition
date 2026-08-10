# Technical-preview quick start

This is the authoritative clean-checkout path for the Framework Bundle and its companion SUT
portfolio. **Both are needed**: the canonical gates test the two repositories together, and every
path below assumes the SUT tree is present.

> **Access.** While either repository is private, your GitHub account must have access to it before
> cloning, and §2 covers authenticating. If both are public, skip the authentication step — a plain
> `git clone` is enough. GitHub reports a private repository you cannot see as
> `404 Repository not found`, which reads like a wrong URL rather than a permission problem; if you
> hit that, check access before checking the address.

> **In a hurry?** [`QUICK_INSTALL_ALL.sh`](QUICK_INSTALL_ALL.sh) performs every step on this page —
> clone, build, per-SUT environments, self-audits and smoke tests — in one command, asserting the
> counts stated below rather than just exit status. `--with-db` adds §6's database run.
> Read on to do it by hand, or to understand what each step proves.

## Before your first run — two notes from the author

**The explosion is yours to govern.** Bundle generates exactly the space you declare, and a declared
space can outgrow any machine. Deciding which units combine with which, and under which rules, is
the engineer's judgement — not the tool's. Every scenario here shows its count before it runs; read
that number. `bundle plan` is side-effect-free and exists precisely so you can look before you leap.

**The creative freedom belongs to living people.** Designing the test — imagining the situation,
choosing which interactions matter, judging what a result means — is the work of human QA engineers
and students. AI may assist you: read the code with you, explain a stage, help draft and run a
scenario. The initiative and the final decisions are **by Humans only — or blocker Above**. A
machine may hold the lamp; it does not choose the road.

## 1. Prerequisites

- Linux or another POSIX-like environment
- GitHub CLI (`gh`) and Git
- Python 3.11 or newer
- JDK 25 and Maven
- Docker plus PostgreSQL client tools (`psql` and `pg_isready`)
- **Two clean PostgreSQL instances, installed and running before you begin** — see below

### Two clean PostgreSQL instances

The Bundle uses two separate local endpoints. Both must be up before §6's database run or the full
test suite:

| Role | Endpoint | Written by |
|---|---|---|
| **main** | `127.0.0.1:5433` | Core materializes the combinatorial space into `fw_final` |
| **results** | `127.0.0.1:5432` | Executor writes candidate results |

The role you connect as needs `CREATEDB` (`bundle doctor` checks this).

Confirm both are accepting connections before continuing:

```bash
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5432
```

**"Clean" means no leftover state from an earlier run** — no Bundle databases or tables from a
previous session, and no pre-existing `fwbundle-main-db` / `fwbundle-results-db` deploy containers.
Stale state rarely produces an error; it makes tests *skip* or silently reuse old data, which reads
like success. If deploy containers already exist, run
`python generator_trunk/bundle_run.py deploy down` first.

See [`docs/03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md`](docs/03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md)
for how to create the two instances, including the route that needs no `sudo`.

The optional UI and editor prerequisites are documented in the root [README](README.md).

## 2. Authenticate and clone both repositories

**If both repositories are public, authentication is unnecessary** — jump straight to the clone
commands below, substituting `git clone https://github.com/ghYura/<repo>.git <dir>` for the
`gh repo clone` lines. The rest of this section applies while either repository is private.

Check the active GitHub identity:

```bash
gh auth status --hostname github.com
```

If it is not authenticated, use GitHub CLI's interactive browser flow. Do not paste a token into a
command, script, or repository file:

```bash
gh auth login --hostname github.com --web
```

That leaves `gh` on its default HTTPS transport, which works with the token `gh` itself stores and
needs no key management. **Choose SSH only if you already have a key registered with GitHub** — add
`--git-protocol ssh` in that case. An unregistered key is the most common way to fail at this step,
because `gh` will then use a transport that cannot authenticate; check before you switch:

```bash
ssh -T git@github.com     # expect "Hi <user>! You've successfully authenticated"
```

Create a new parent directory and clone both repositories as siblings:

```bash
mkdir -p downloaded-repos
cd downloaded-repos
gh repo clone ghYura/Combinatorics-Framework-QA-edition Combinatorics-Framework-QA-edition
gh repo clone ghYura/SUT SUT
export BUNDLE_SUT_ROOT="$(cd SUT && pwd -P)"
cd Combinatorics-Framework-QA-edition
```

The target directory is given explicitly so the result does not depend on `gh`'s default naming, and
`pwd -P` resolves symlinks so the value is stable wherever it is later read. `SUT/QUICKSTART.md` uses
the identical commands; if the two pages ever disagree, that is a documentation bug.

This edition is `ghYura/Combinatorics-Framework-QA-edition`. `ghYura/Combinatorics-Framework` is a
different repository — cloning it instead gives you a different tree, and every path below assumes
the QA edition.

Keep the two directory names unchanged for these commands; no symlink or copied SUT tree is required.

`BUNDLE_SUT_ROOT` is the supported portable connection between the repositories, and the only one
that works when they are *not* siblings. In the sibling layout above it is in fact optional —
`generator_trunk/sut_paths.py` falls back to a directory named `SUT` or `SUT-main` beside the
Framework checkout — but export it anyway: it costs nothing, it keeps working if the directories are
ever moved apart, and it removes any doubt about which SUT tree a run used.

## 3. Create the Python environment and build Java components

Run from the Framework repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,science]'
mvn -q clean package
```

The first pip or Maven invocation may download dependencies. Build products remain local and are
ignored by Git.

## 4. Run the self-contained 24-case plan

```bash
python generator_trunk/bundle_run.py plan \
  generator_trunk/usecases/event_order \
  --out /tmp/framework-plan

python -c 'import json, pathlib; p=json.loads(pathlib.Path("/tmp/framework-plan/plan.json").read_text()); c=p["cardinality"]["final"]; assert c["mode"] == "EXACT" and c["value"] == 24, c; print("verified exact final cardinality: 24")'
```

This is the first smoke test because it needs no database, container, network service, or SUT.

## 5. Run the deterministic companion-SUT smoke

The combination-thinking tutor is standard-library-only and never contacts an external service:

```bash
(
  cd "$BUNDLE_SUT_ROOT/combination_thinking_tutor"
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
  PYTHONDONTWRITEBYTECODE=1 python3 tutor_sut.py --summary
)
```

The expected exhaustive oracle covers 144 cases and reports 18 `PASS`, 120
`ORDER_VIOLATION`, 2 `DOUBLE_CHARGE`, and 4 `DISPATCH_LOST`.

The telemetry catalog is also standard-library-only:

```bash
(
  cd "$BUNDLE_SUT_ROOT/telemetry_catalog_service"
  PYTHONDONTWRITEBYTECODE=1 python3 selftest.py
)
```

Its expected signal is `OK — 20 case(s), 0 failure(s)`.

## 6. Optional local database deployment and full run

Everything up to this point was database-free. From here on every command needs **two reachable
PostgreSQL endpoints and their credentials**: one main database for Core/Reader and one results
database for the Executor. Bundle never guesses them — a run refuses to start until they are
configured, and it will not mix ports from one source with credentials from another.

The two supported ways to supply them:

- **the local deploy stack** — `deploy up` starts the containers and writes ports, user and a
  generated password into `generator_trunk/deploy/.env`, which is then the single source for both;
- **your own cluster** — export `BUNDLE_MAIN_DB_*`/`BUNDLE_RESULTS_DB_*` yourself, including both
  passwords.

Note that a process environment left over from another cluster keeps normal precedence over most
settings, so prefer a clean shell for the commands below, or select the deploy stack explicitly
where a command offers that choice (`doctor --deploy`, the engine demo's `--db-endpoint deploy`).

The managed deploy profile is local-only: its published ports bind to `127.0.0.1`. Install the
deployment extra, validate the profile, and start the two PostgreSQL containers:

```bash
python -m pip install -e '.[deploy]'
python generator_trunk/bundle_run.py deploy validate
python generator_trunk/bundle_run.py deploy up
python generator_trunk/bundle_run.py doctor --deploy
```

> **One checkout per machine.** The profile uses fixed, host-wide container names and ports, so only
> one checkout's stack can run at a time. On a machine that accumulates checkouts this is the most
> likely reason `deploy up` refuses:
>
> ```
> ✗ refusing to replace/remove fixed-name container(s) not owned by the selected deploy env …:
>   fwbundle-main-db, fwbundle-results-db. Stop them from their owning checkout or choose
>   another host; no container was changed.
> ```
>
> That refusal is deliberate and it changed nothing — it will not adopt or delete another checkout's
> databases. Three ways forward, in order of least surprise:
>
> 1. run `deploy down` **from the checkout that owns them** (it preserves the data volumes);
> 2. use the *your own cluster* route below — export the `BUNDLE_*` variables at any free ports. This
>    is a first-class path, not a workaround;
> 3. run `./QUICK_INSTALL_ALL.sh --with-db`, which starts its own pair on automatically-chosen free
>    ports and cannot collide with anything already running.
>
> `docker ps --filter name=fwbundle` shows what currently holds the names.

`deploy up` starts exactly the two database containers. `deploy validate` additionally validates the
optional Adminer monitoring service that is declared in the same compose profile but is **not**
started by default — add it explicitly when you want the web UI on `127.0.0.1:18080`:

```bash
python generator_trunk/bundle_run.py deploy up --monitoring
```

`deploy up` creates `generator_trunk/deploy/.env` with a generated local password, a pair of
checkout-scoped Docker volume names, and mode `0600`. The file is ignored by Git. The scoped names
prevent an older checkout's volumes from being silently reused when a new checkout generates a new
password. The command reports success only after authenticated SQL probes pass. Do not replace the
template with a real credential and do not print, commit, or paste the generated values.

An older `.env` without scoped volume names remains compatible with its legacy volumes. If its
credentials no longer match those volumes, `deploy up` stops the containers without deleting data
and explains the two recovery choices: restore the original `.env`, or, only for explicitly
disposable data, run `deploy down --volumes` before retrying.

Load the generated settings into the current shell and map them to the Bundle runtime variables:

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

Run the complete event-order pipeline:

```bash
python generator_trunk/bundle_run.py \
  generator_trunk/usecases/event_order \
  --db event_order_demo \
  --lang py \
  --execution-policy-profile trusted-local \
  --candidate-origin reviewed-checked-in \
  --acknowledge-trusted-local 'reviewed checked-in event_order fixture' \
  --analyzer 'charges:min'
```

`trusted-local` is intentionally unsandboxed. Use it only for the checked-in candidate fixture or
other code you trust.

Stop the containers while preserving their named data volumes:

```bash
python generator_trunk/bundle_run.py deploy down
unset POSTGRES_PASSWORD BUNDLE_MAIN_DB_PASSWORD BUNDLE_RESULTS_DB_PASSWORD
```

`deploy down --volumes` also deletes the local database volumes and is therefore reserved for an
explicitly throwaway environment.

## 7. Focused verification

```bash
python -m pytest -q \
  generator_trunk/test_bundle_doctor.py \
  generator_trunk/test_bundle_counts.py \
  generator_trunk/test_fwgen_aliases.py

bash Analyzer_trunk/run-tests.sh
```

For full live-deploy coverage, first use `deploy down`: the profile keeps fixed host-wide container
names, so its acceptance test self-skips `EXPECTED_OPTIONAL` whenever any canonical name already
exists. Production `deploy up`/`down` now proves ownership from labels and the selected `.env`
before touching such a name; a foreign or ambiguous container is refused, never force-replaced.
Persistent volume identity always comes from the selected `.env`, not ambient exports. A clean shell
is still recommended for the full suite because ports, credentials and other non-identity settings
retain normal process-environment precedence.

For heavier suites, optional interfaces, security profiles, and troubleshooting, continue with the
[README](README.md) and [installation guide](docs/03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md).

---

**Upgrading from a checkout older than Phases 01–05?** Two things changed behaviour on purpose — `--execution-policy-profile` is now required for any run, and the gRPC candidate channel is loopback-only. The one-line fix for each, and how to revert them, is in [docs/38_MIGRATION_PHASE_01_05.md](docs/38_MIGRATION_PHASE_01_05.md).

---

P.S.: Quick workaround to use the Bundle freely: wear a role of QA-Engineer/student (or hire them for real - preferably) and Godspeed! =Ъ
