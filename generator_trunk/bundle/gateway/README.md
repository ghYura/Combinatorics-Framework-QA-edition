# Bundle Evaluation Gateway

`bundle_gateway.py --transport auto` selects the normative gRPC contract from
`proto/evaluation_gateway.proto` when both `grpcio` and `grpcio-tools` are
installed. Otherwise it falls back to the stdlib HTTP/JSON mapping. Use
`--transport grpc` or `--transport http-json` to require one transport.

Run locally:

```bash
# Create this file outside source control with an operator-generated token:
# {"<bearer-token>": "<tenant-id>"}
chmod 600 .bundle-gateway-tokens.json

: "${BUNDLE_MAIN_DB_PASSWORD:?set the main DB password in the environment}"
: "${BUNDLE_RESULTS_DB_PASSWORD:?set the results DB password in the environment}"
# Optional when java/javac are not already on PATH:
# export BUNDLE_JAVA_CMD=/path/to/java
# export BUNDLE_JAVAC_CMD=/path/to/javac
python3 bundle_gateway.py --runs-root /tmp/fw_gateway_runs
```

Do not commit the token file or database credentials. The example deliberately
uses placeholders; inject secrets through the deployment environment or secret
manager.

Plaintext binds are refused on non-loopback hosts. For `0.0.0.0`, pass
`--tls-cert` and `--tls-key`.

Regenerate stubs after proto edits:

```bash
python3 -m bundle.gateway.codegen
```

The gRPC service is `fw.eval.v1.EvaluationGateway`:

- `Submit(EvaluationJob) -> JobHandle`
- `GetStatus(JobRef) -> JobStatus`
- `WatchStatus(JobRef) -> stream JobStatus`
- `GetResults(JobRef) -> EvaluationResults`
- `Cancel(JobRef) -> JobStatus`
- `ListJobs(ListFilter) -> JobList`
- `Capabilities(Empty) -> CapabilitiesDoc`
- `Health(Empty) -> HealthDoc`

## Two different gRPC boundaries

The gateway RPCs above are the external job-control API. They submit, observe,
cancel, and collect whole Bundle jobs.

The Reader-to-Executor candidate stream is a separate internal boundary:
`LooseFileSink` is the default handoff, while the candidate gRPC sink targets
the Java Executor's `-grpcPort`. That candidate transport does not expose the
gateway service. In the current launcher it is a Java, trusted-local path:
Executor is started before Reader so the sink has a live receiver, and Reader
streams each candidate once. It does not produce a reusable loose-file corpus,
cannot be resumed as an already-materialized Reader/Executor pair, and is not
compatible with `--executor-pool`.

HTTP/JSON fallback endpoints:

- `POST /v1/submit` with an `EvaluationJob` JSON body returns `{job_id,state}`.
- `GET /v1/jobs/<job_id>/status`
- `GET /v1/jobs/<job_id>/watch` streams newline-delimited status JSON.
- `GET /v1/jobs/<job_id>/results` is terminal-only and fails closed before then.
- `POST /v1/jobs/<job_id>/cancel`
- `POST /v1/jobs/<job_id>/cleanup` removes terminal run artifacts via `bundle_run.py cleanup` and drops the per-job DBs.
- `GET /v1/jobs`
- `GET /v1/capabilities`
- `GET /v1/health`

All endpoints/RPCs except `Health` require `Authorization: Bearer <token>`.
Tokens map to tenants, and each tenant is confined to `runs_root/<tenant>/`.
`config_overrides` are allow-listed; path, DB, password, sandbox-network, and
artifact overrides are rejected before the launcher sees them.

Packaging overlay:

```bash
# after deploy/.env, deploy/gateway-tokens.json, and deploy/certs/* exist
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.gateway.yml up -d
```

The gateway image uses JDK 25 and serves gRPC over TLS when bound inside the container.
