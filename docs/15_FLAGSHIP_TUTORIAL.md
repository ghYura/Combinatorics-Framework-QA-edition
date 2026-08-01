# 15 — Flagship Tutorial: a bounded end-to-end secure run

> **Verification status (2026-07-21):** this tutorial preserves the bounded 2026-06-11 flagship
> run and its recorded counts; it was not re-executed during the current documentation audit.
> Re-run `doctor` and `plan` on the target host before treating the expected output as current.

A new expert user can complete this in ~15 minutes on a prepared Linux host. It runs the
secure-document-pipeline spec end-to-end (288 candidates) in a rootless-Docker sandbox against a
local SUT, inspects the results and the formal Analyzer report, does a no-op resume, and cleans up.
Every command here is copied from a verified invocation. **Linux-specific.**

> Placeholders: `$PGPW` = your PostgreSQL password (do not write it into a file);
> `$BUNDLE_ROOT` = this repository's checkout directory; `$BUNDLE_SUT_ROOT` = the directory
> containing the separately checked-out SUT projects. Ports are the canonical host ports
> (main `5433`, results `5432`).

## 0. Prerequisites (once)

```bash
export BUNDLE_ROOT="<path-to-bundle-checkout>"
export BUNDLE_SUT_ROOT="<path-to-sut-checkouts>"
cd "$BUNDLE_ROOT/generator_trunk"
export PATH="$HOME/bin:$PATH"
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
export BUNDLE_MAIN_DB_PASSWORD=$PGPW
export BUNDLE_RESULTS_DB_PASSWORD=$PGPW
python3 bundle_run.py doctor          # expect overall: OK
```

If `doctor` is green, both PostgreSQL clusters are up, the jars/analyzer are built, and Docker +
a sandbox backend are available. (To build jars: see [03](03_INSTALLATION_AND_LOCAL_DEPLOYMENT.md).)

## 1. Plan first (no DB side effects)

```bash
python3 bundle_run.py plan tryout_own/spec --out /tmp/sp_plan
```

Expect: mandatory **96** (EXACT), post-sieve BOUNDED `[0,96]`, optional **×4** (EXACT), final **384**
BOUNDED, **run class S**. (With the sieve applied at run time the realized final is 288.)

## 2. Launch the local SUT in a sandbox-reachable container

The example SUT is a small FastAPI app. Build a purpose-specific image so the container does not
inherit host executables or libraries. Run it on a local-only internal network with a read-only
root filesystem and **no published host ports**:

```bash
SUT="$BUNDLE_SUT_ROOT/bundle_secure_pipeline_tryout"
docker build -t bundle-secure-app -f - "$SUT" <<'DOCKERFILE'
FROM python:3.12-slim
WORKDIR /app
RUN python -m pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29"
COPY app.py /app/app.py
USER 65532:65532
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8025"]
DOCKERFILE
docker network create --internal fwsut-net 2>/dev/null || true
docker rm -f secure-app 2>/dev/null || true
docker run -d --name secure-app --network fwsut-net --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m bundle-secure-app
sleep 4
docker exec secure-app python -c \
  "import urllib.request; print('SUT', urllib.request.urlopen('http://127.0.0.1:8025/docs',timeout=5).status)"
# expect: SUT 200
```

## 3. Run the full secure chain (Generator → … → Analyzer)

```bash
python3 bundle_run.py tryout_own/spec \
  --db sp_demo --sieve \
  --analyzer "security_failures:max,latency_ms:min,correct:max" --analysis-mode formal \
  --execution-policy-profile networked-api-probe \
  --sandbox-network-allowlist secure-app \
  --sandbox-candidate-env TRYOUT_URL=http://secure-app:8025 \
  --run-id sp-demo-001
```

Watch the stages: `fw_final = 96` → `sieve … → fw_final now 72` → `candidates = 288` → executor
(each candidate in its own container) → `Results DB: 288 / pass 150 / fail 138` → Analyzer formal
front. Final line: `✓ DONE — sp_demo: full Bundle chain green.` (~5–6 min; the slow part is one
container per candidate.)

## 4. Inspect manifests, results, Analyzer

```bash
R=/tmp/fw_work/sp_demo/runs/sp-demo-001
python3 -m json.tool "$R/executor-summary.json"      # outcomes + sandbox_backend
python3 -c "import json;d=json.load(open('$R/provenance.json'));print('mode',d['mode'],'seen',d['candidates_seen'],'ok',d['provenance_ok'],'front',len(d['candidates']))"
PGPASSWORD=$PGPW psql -h 127.0.0.1 -p 5432 -U postgres -d sp_demo -Atc \
  "select outcome,count(*) from results_v2 where run_id='sp-demo-001' group by outcome order by 1;"
```

Expect outcomes `PASS=150, DOMAIN_FAIL=138`, `provenance_ok=true`, a small Pareto front (3 in the
verified run). Open one failing candidate in `$R/src/<id>.py` and trace it to its metric line in
`$R/metrics.kv` — counts plus traceability, the whole point.

## 5. Resume (no-op) — proves idempotency

```bash
python3 bundle_run.py resume "$R"
```

Expect every stage `resuming: reusing 'gen'/'core'/'sieve'/'reader'/'executor'/'analyzer'` and
`✓ DONE … resumed run green`. The `results_v2` row count stays **288** (no new attempt, no
duplicates).

## 6. Cleanup (dry-run, then real)

```bash
python3 bundle_run.py cleanup "$R" --dry-run          # lists files/DB rows; deletes nothing
python3 bundle_run.py cleanup "$R" --yes              # removes the run dir + this run's results_v2 rows
```

Tear down the SUT (it published no host ports and lived only on the internal net):

```bash
docker rm -f secure-app
docker network rm fwsut-net
```

You have now planned, run, inspected, resumed, and cleaned a bounded secure experiment with exact
count planning, constraint pruning, optional sudden actions, an independent oracle, a sandbox with no
external egress, and a traceable formal Pareto front.
