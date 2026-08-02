#!/usr/bin/env bash
#
# QUICK_INSTALL_ALL.sh — one command from nothing to a verified Bundle install.
#
# Does everything QUICKSTART.md and SUT/QUICKSTART.md describe: clones both private
# repositories side by side, builds the Python and Java components, provisions the
# per-SUT virtualenvs, and runs the documented smoke tests, checking each published
# count rather than merely reporting success.
#
#   ./QUICK_INSTALL_ALL.sh                  # install + smoke tests (no database)
#   ./QUICK_INSTALL_ALL.sh --with-db        # also start PostgreSQL and run a full pipeline
#   ./QUICK_INSTALL_ALL.sh --dir ~/bundle   # choose where the checkouts go
#   ./QUICK_INSTALL_ALL.sh --ref <branch>   # check out a branch or tag instead of the default
#   ./QUICK_INSTALL_ALL.sh --help
#
# Run it from anywhere: inside an existing checkout (it will find the sibling, or
# clone it), or in an empty directory (it will clone both).
#
# Requirements: git, gh (authenticated), python3 >= 3.11, JDK 25, maven.
# --with-db additionally needs docker, psql and pg_isready.
#
# The script is idempotent: re-running it reuses what already exists. It never
# writes outside the target directory, never installs anything system-wide, and
# never touches another checkout's containers.

set -Eeuo pipefail

readonly FW_REPO="ghYura/Combinatorics-Framework-QA-edition"
readonly SUT_REPO="ghYura/SUT"
readonly FW_DIR_NAME="Combinatorics-Framework-QA-edition"
readonly SUT_DIR_NAME="SUT"

WITH_DB=0
TARGET_DIR=""
SKIP_SMOKE=0
# Branch or tag to check out in both repositories. Empty means each repository's
# default branch. Both are checked out at the same ref, so a cross-repository
# change stays consistent.
REF=""

# Database endpoints used by --with-db. Deliberately NOT the managed `deploy`
# profile's 15433/15432: those are fixed host-wide, so a second checkout on the
# same machine collides with the first. These are private to this installation.
DB_MAIN_PORT="${BUNDLE_QUICK_MAIN_PORT:-25433}"
DB_RESULTS_PORT="${BUNDLE_QUICK_RESULTS_PORT:-25432}"
DB_MAIN_NAME="bundle-quick-main-db"
DB_RESULTS_NAME="bundle-quick-results-db"
# Same pinned digest the repository's own deploy profile uses.
readonly PG_IMAGE="postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7"

# ---------------------------------------------------------------- presentation --

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'
    C_DIM=$'\033[2m'; C_B=$'\033[1m'; C_0=$'\033[0m'
else
    C_OK=""; C_BAD=""; C_WARN=""; C_DIM=""; C_B=""; C_0=""
fi

STEP_NO=0
step()  { STEP_NO=$((STEP_NO + 1)); printf '\n%s[%d/%d] %s%s\n' "$C_B" "$STEP_NO" "$TOTAL_STEPS" "$*" "$C_0"; }
ok()    { printf '  %s✓%s %s\n' "$C_OK"  "$C_0" "$*"; }
warn()  { printf '  %s!%s %s\n' "$C_WARN" "$C_0" "$*"; }
info()  { printf '  %s%s%s\n'   "$C_DIM" "$*" "$C_0"; }
die()   { printf '\n  %s✗ %s%s\n\n' "$C_BAD" "$*" "$C_0" >&2; exit 1; }

on_error() {
    local rc=$? line=$1
    printf '\n  %s✗ failed at line %s (exit %s)%s\n' "$C_BAD" "$line" "$rc" "$C_0" >&2
    printf '  %sre-run with:  bash -x %s%s\n\n' "$C_DIM" "$0" "$C_0" >&2
    exit "$rc"
}
trap 'on_error $LINENO' ERR

usage() {
    sed -n '3,26p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

# Compare dotted versions: have_version <have> <min>  → 0 when have >= min.
have_version() {
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

# --------------------------------------------------------------------- arguments --

while [ $# -gt 0 ]; do
    case "$1" in
        --with-db)    WITH_DB=1 ;;
        --no-smoke)   SKIP_SMOKE=1 ;;
        --dir)        TARGET_DIR="${2:-}"; [ -n "$TARGET_DIR" ] || die "--dir needs a path"; shift ;;
        --dir=*)      TARGET_DIR="${1#--dir=}" ;;
        --ref)        REF="${2:-}"; [ -n "$REF" ] || die "--ref needs a branch or tag"; shift ;;
        --ref=*)      REF="${1#--ref=}" ;;
        -h|--help)    usage ;;
        *)            die "unknown option '$1' (try --help)" ;;
    esac
    shift
done

TOTAL_STEPS=7
[ "$WITH_DB" -eq 1 ] && TOTAL_STEPS=8

printf '%s' "$C_B"
cat <<'BANNER'
Combinatorics Framework (QA edition) + SUT — quick install
BANNER
printf '%s' "$C_0"

# ------------------------------------------------------- 1. prerequisite check --

step "Checking prerequisites"

missing=()
for tool in git gh python3 java mvn; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ "$WITH_DB" -eq 1 ]; then
    for tool in docker psql pg_isready; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
fi
[ ${#missing[@]} -eq 0 ] || die "missing required tool(s): ${missing[*]}"

PY_VER="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
have_version "$PY_VER" "3.11" || die "Python >= 3.11 required (found $PY_VER); the Framework's pyproject declares requires-python >= 3.11"
ok "python $PY_VER"

python3 -c 'import venv' 2>/dev/null || die "python3-venv is not available; install it (e.g. apt install python3-venv)"

# Reader_trunk and Executor_trunk target release 25, so a JDK 21 host builds half
# the reactor and then fails. Check up front rather than 200 lines into a build.
JAVA_MAJOR="$(java -version 2>&1 | sed -n '1s/.*version "\([0-9]*\).*/\1/p')"
[ -n "$JAVA_MAJOR" ] || die "could not determine the Java version from 'java -version'"
if [ "$JAVA_MAJOR" -lt 25 ]; then
    die "JDK 25 required (found $JAVA_MAJOR). Reader_trunk and Executor_trunk target release 25; an older JDK builds Core/Analyzer and then fails."
fi
ok "java $JAVA_MAJOR"
ok "maven $(mvn --version 2>/dev/null | sed -n '1s/Apache Maven \([^ ]*\).*/\1/p')"

# gh must be authenticated: both repositories are private.
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
    die "gh is not authenticated. Run:  gh auth login --hostname github.com --web
       Both repositories are private, so an anonymous clone returns 404 rather than a permission error."
fi
ok "gh authenticated as $(gh api user --jq .login 2>/dev/null || echo '<unknown>')"

# If gh is set to SSH, make sure that transport actually works before we rely on it.
if [ "$(gh config get git_protocol 2>/dev/null || echo https)" = "ssh" ]; then
    if ! ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T git@github.com 2>&1 | grep -qi "successfully authenticated"; then
        die "gh is configured for SSH but 'ssh -T git@github.com' does not authenticate.
       Either register your key with GitHub, or switch back:  gh config set git_protocol https --host github.com"
    fi
    ok "ssh transport verified"
fi

if [ "$WITH_DB" -eq 1 ]; then
    export DOCKER_HOST="${DOCKER_HOST:-unix:///run/user/$(id -u)/docker.sock}"
    docker info >/dev/null 2>&1 || die "docker is installed but its daemon is not reachable (DOCKER_HOST=$DOCKER_HOST)"
    ok "docker reachable"
fi

# ------------------------------------------------------------ 2. locate/clone --

step "Locating the two checkouts"

# Resolve where the checkouts should live. Precedence: --dir, then an enclosing
# checkout's parent (so running this from inside a clone does the expected thing),
# then the current directory.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ -n "$TARGET_DIR" ]; then
    mkdir -p "$TARGET_DIR"
    ROOT="$(cd "$TARGET_DIR" && pwd -P)"
elif [ -f "$script_dir/generator_trunk/bundle_run.py" ]; then
    ROOT="$(dirname "$script_dir")"        # we are inside the Framework checkout
else
    ROOT="$(pwd -P)"
fi
info "workspace: $ROOT"

FW_ROOT="$ROOT/$FW_DIR_NAME"
SUT_ROOT="$ROOT/$SUT_DIR_NAME"

clone_or_keep() {
    local repo="$1" dest="$2" label="$3"
    if [ -d "$dest/.git" ]; then
        ok "$label already present — reusing $dest"
    elif [ -e "$dest" ]; then
        die "$dest exists but is not a git checkout; move it aside or use --dir"
    else
        info "cloning $repo …"
        gh repo clone "$repo" "$dest" -- --quiet \
            || die "clone of $repo failed. Both repositories are private — confirm your account can read them:  gh repo view $repo"
        ok "$label cloned"
    fi
    if [ -n "$REF" ]; then
        # Fetch explicitly: a fresh clone only has the default branch, and a reused
        # checkout may predate the ref entirely.
        (cd "$dest" && git fetch --quiet origin "$REF" && git checkout --quiet FETCH_HEAD) \
            || die "$label: could not check out ref '$REF'"
        ok "$label at $REF ($(cd "$dest" && git rev-parse --short HEAD))"
    fi
}

clone_or_keep "$FW_REPO"  "$FW_ROOT"  "Framework"
clone_or_keep "$SUT_REPO" "$SUT_ROOT" "SUT collection"

# The supported link between the two checkouts. The Framework also discovers a
# sibling named SUT on its own, but being explicit keeps this working if the
# directories are ever moved apart.
export BUNDLE_SUT_ROOT="$SUT_ROOT"
export PYTHONDONTWRITEBYTECODE=1
ok "BUNDLE_SUT_ROOT=$BUNDLE_SUT_ROOT"

# ------------------------------------------------------------ 3. python setup --

step "Building the Python environment"

VENV="$FW_ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
    ok "virtualenv created"
else
    ok "virtualenv already present"
fi
PY="$VENV/bin/python"

"$PY" -m pip install --quiet --upgrade pip
info "installing framework-bundle-workspace[test,science,deploy] (first run downloads packages)"
(cd "$FW_ROOT" && "$PY" -m pip install --quiet -e '.[test,science,deploy]')
ok "python components installed"

# ------------------------------------------------------------- 4. java build --

step "Building the Java components"

if [ -f "$FW_ROOT/Reader_trunk/target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar" ]; then
    ok "jars already built — skipping (delete */target to force a rebuild)"
else
    info "mvn clean package — the first run downloads dependencies and takes a few minutes"
    (cd "$FW_ROOT" && mvn -q clean package) || die "the Maven build failed"
    ok "reactor built"
fi
for jar in \
    "Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar" \
    "Reader_trunk/target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar" \
    "Analyzer_trunk/target/heuristic-analyzer-flatlaf-1.0.0.jar" \
    "Executor_trunk/target/Executor-1.0.jar"; do
    [ -f "$FW_ROOT/$jar" ] || die "expected artifact missing after the build: $jar"
done
ok "all four artifacts present"

# --------------------------------------------------------- 5. SUT virtualenvs --

step "Provisioning the per-SUT environments"

# Kept beside the checkouts, never inside them, so neither repository is dirtied.
SUT_VENV_ROOT="$ROOT/.venvs"
mkdir -p "$SUT_VENV_ROOT"

make_sut_venv() {
    local name="$1" reqs="$2"
    if [ ! -f "$reqs" ]; then
        warn "$name: no requirements manifest — skipped"
        return 0
    fi
    if [ ! -x "$SUT_VENV_ROOT/$name/bin/python" ]; then
        python3 -m venv "$SUT_VENV_ROOT/$name"
    fi
    "$SUT_VENV_ROOT/$name/bin/python" -m pip install --quiet --upgrade pip
    "$SUT_VENV_ROOT/$name/bin/python" -m pip install --quiet -r "$reqs" \
        || die "$name: dependency install failed ($reqs)"
    ok "$name environment ready"
}

make_sut_venv fintech "$SUT_ROOT/fin_tech_to_test/requirements.txt"
make_sut_venv sieve3d "$SUT_ROOT/3Dprofile-VS-2Dsieve/requirements.txt"
info "llm_transformer_testme (PyTorch) is optional and not installed here; see its requirements.txt"

# ---------------------------------------------------------------- 6. self-check --

step "Framework self-audits"

run_verb() {
    local verb="$1"
    if (cd "$FW_ROOT" && "$PY" generator_trunk/bundle_run.py "$verb" >/tmp/qi_$$.log 2>&1); then
        ok "$verb"
    else
        cat /tmp/qi_$$.log >&2; rm -f /tmp/qi_$$.log
        die "'$verb' reported a problem"
    fi
    rm -f /tmp/qi_$$.log
}
run_verb architecture
run_verb coverage
run_verb sut-manifests

# ---------------------------------------------------------------- 7. smoke tests --

step "Smoke tests"

if [ "$SKIP_SMOKE" -eq 1 ]; then
    warn "skipped (--no-smoke)"
else
    # Each check asserts the count the documentation publishes, so a silent
    # behaviour change fails here instead of looking like success.

    # (a) 24-case plan — no database, no SUT, no network.
    (cd "$FW_ROOT" && "$PY" generator_trunk/bundle_run.py plan \
        generator_trunk/usecases/event_order --out /tmp/qi_plan_$$ >/dev/null 2>&1) \
        || die "the event_order plan failed"
    "$PY" - "/tmp/qi_plan_$$/plan.json" <<'PY' || die "plan cardinality is not the documented EXACT 24"
import json, pathlib, sys
c = json.loads(pathlib.Path(sys.argv[1]).read_text())["cardinality"]["final"]
assert c["mode"] == "EXACT" and c["value"] == 24, c
PY
    rm -rf "/tmp/qi_plan_$$"
    ok "event_order plan: EXACT 24"

    # (b) tutor — 9 tests, then the 144-case exhaustive oracle.
    (cd "$SUT_ROOT/combination_thinking_tutor" && python3 -m unittest discover -s tests >/dev/null 2>&1) \
        || die "the combination_thinking_tutor unit tests failed"
    tutor_out="$(cd "$SUT_ROOT/combination_thinking_tutor" && python3 tutor_sut.py --summary)"
    "$PY" - <<PY || die "tutor outcome distribution does not match the documented fixture contract"
import json
d = json.loads('''$tutor_out''')["outcomes"]
expected = {"PASS": 18, "ORDER_VIOLATION": 120, "DOUBLE_CHARGE": 2, "DISPATCH_LOST": 4}
assert d == expected, (d, expected)
PY
    ok "tutor: 9 tests; 144 cases = 18 PASS / 120 ORDER_VIOLATION / 2 DOUBLE_CHARGE / 4 DISPATCH_LOST"

    # (c) telemetry catalog — standard library only, 20 rule cases over HTTP.
    telemetry_out="$(cd "$SUT_ROOT/telemetry_catalog_service" && python3 selftest.py 2>&1 | tail -1)"
    case "$telemetry_out" in
        *"OK — 20 case(s), 0 failure(s)"*) ok "telemetry catalog: $telemetry_out" ;;
        *) die "telemetry selftest expected 'OK — 20 case(s), 0 failure(s)', got: $telemetry_out" ;;
    esac

    # (d) fintech SUT in its own environment.
    if [ -x "$SUT_VENV_ROOT/fintech/bin/python" ]; then
        (cd "$SUT_ROOT/fin_tech_to_test" && "$SUT_VENV_ROOT/fintech/bin/python" -m pytest -q -p no:cacheprovider >/dev/null 2>&1) \
            || die "the fintech SUT test suite failed"
        ok "fintech SUT suite"
    fi

    # (e) the Framework's own focused suite.
    (cd "$FW_ROOT" && "$PY" -m pytest -q -p no:cacheprovider \
        generator_trunk/test_bundle_doctor.py \
        generator_trunk/test_bundle_counts.py \
        generator_trunk/test_fwgen_aliases.py >/dev/null 2>&1) \
        || die "the focused Framework suite failed"
    ok "focused Framework suite"
fi

# ------------------------------------------------------------ 8. optional DBs --

if [ "$WITH_DB" -eq 1 ]; then
    step "PostgreSQL and a full pipeline"

    # A generated password, kept in the process environment only: never written to
    # a file by this script, never echoed.
    DB_PASSWORD="$("$PY" -c 'import secrets; print("quickinstall_" + secrets.token_hex(12))')"

    start_db() {
        local name="$1" port="$2"
        if [ -n "$(docker ps -q --filter "name=^${name}$" 2>/dev/null)" ]; then
            ok "$name already running"
            return 0
        fi
        if [ -n "$(docker ps -aq --filter "name=^${name}$" 2>/dev/null)" ]; then
            # A stopped container from an earlier run holds an older password.
            docker rm -f "$name" >/dev/null 2>&1 || true
        fi
        docker run -d --name "$name" \
            -p "127.0.0.1:${port}:5432" \
            -e POSTGRES_USER=postgres \
            -e POSTGRES_PASSWORD="$DB_PASSWORD" \
            "$PG_IMAGE" >/dev/null \
            || die "could not start $name on 127.0.0.1:$port (is the port already taken?)"
        ok "$name started on 127.0.0.1:$port"
    }

    start_db "$DB_MAIN_NAME"    "$DB_MAIN_PORT"
    start_db "$DB_RESULTS_NAME" "$DB_RESULTS_PORT"

    info "waiting for both databases to accept authenticated connections"
    for _ in $(seq 1 60); do
        if PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p "$DB_MAIN_PORT"    -U postgres -d postgres -tAc 'select 1' >/dev/null 2>&1 &&
           PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p "$DB_RESULTS_PORT" -U postgres -d postgres -tAc 'select 1' >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p "$DB_MAIN_PORT" -U postgres -d postgres -tAc 'select 1' >/dev/null 2>&1 \
        || die "the databases never accepted an authenticated connection"
    ok "both databases authenticated"

    export BUNDLE_MAIN_DB_HOST=127.0.0.1    BUNDLE_MAIN_DB_PORT="$DB_MAIN_PORT"
    export BUNDLE_RESULTS_DB_HOST=127.0.0.1 BUNDLE_RESULTS_DB_PORT="$DB_RESULTS_PORT"
    export BUNDLE_MAIN_DB_USER=postgres     BUNDLE_RESULTS_DB_USER=postgres
    export BUNDLE_MAIN_DB_PASSWORD="$DB_PASSWORD" BUNDLE_RESULTS_DB_PASSWORD="$DB_PASSWORD"

    (cd "$FW_ROOT" && "$PY" generator_trunk/bundle_run.py doctor >/tmp/qi_doc_$$.log 2>&1) \
        || { cat /tmp/qi_doc_$$.log >&2; rm -f /tmp/qi_doc_$$.log; die "doctor reported a BLOCKING problem"; }
    rm -f /tmp/qi_doc_$$.log
    ok "doctor: overall OK"

    info "running the full event_order pipeline (Core → Reader → Executor → Analyzer)"
    if (cd "$FW_ROOT" && "$PY" generator_trunk/bundle_run.py \
            generator_trunk/usecases/event_order \
            --db quickinstall_event_order --lang py \
            --execution-policy-profile trusted-local \
            --candidate-origin reviewed-checked-in \
            --acknowledge-trusted-local 'QUICK_INSTALL_ALL smoke: checked-in event_order fixture' \
            --analyzer 'charges:min' >/tmp/qi_run_$$.log 2>&1); then
        grep -E 'candidates =|Results DB|Pareto' /tmp/qi_run_$$.log | sed 's/^ *//' | while read -r l; do info "$l"; done
        ok "full Bundle chain green"
    else
        tail -30 /tmp/qi_run_$$.log >&2
        rm -f /tmp/qi_run_$$.log
        die "the full pipeline failed"
    fi
    rm -f /tmp/qi_run_$$.log
fi

# --------------------------------------------------------------------- summary --

cat <<EOF

${C_OK}${C_B}Installation complete.${C_0}

  Framework   $FW_ROOT
  SUT         $SUT_ROOT
  virtualenv  $VENV
  SUT venvs   $SUT_VENV_ROOT

Start a working shell:

  cd $FW_ROOT
  source .venv/bin/activate
  export BUNDLE_SUT_ROOT=$SUT_ROOT

Then try:

  python generator_trunk/bundle_run.py --help              # all subcommands
  python generator_trunk/bundle_run.py doctor              # what this host still needs
  python generator_trunk/bundle_run.py sut-manifests       # which SUTs are gated, and why
  python generator_trunk/bundle_run.py plan generator_trunk/usecases/event_order --out /tmp/plan
EOF

if [ "$WITH_DB" -eq 1 ]; then
    cat <<EOF

The two PostgreSQL containers are still running and hold your run data:

  docker stop $DB_MAIN_NAME $DB_RESULTS_NAME      # stop, keep data
  docker rm -f $DB_MAIN_NAME $DB_RESULTS_NAME     # remove entirely

Their password was generated for this run and not saved anywhere. Re-run with
--with-db to start a fresh pair, or use QUICKSTART.md §6 to point the Bundle at a
cluster of your own.
EOF
else
    cat <<EOF

Everything above is database-free. For the full pipeline, re-run with --with-db,
or follow QUICKSTART.md §6 to use a PostgreSQL cluster you already have.
EOF
fi
echo
