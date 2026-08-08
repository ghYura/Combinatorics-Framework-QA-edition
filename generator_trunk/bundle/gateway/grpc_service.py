# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

from __future__ import annotations

import sys
import time
from concurrent import futures
from pathlib import Path
from typing import Mapping

import grpc

from .auth import AuthError, TokenAuth
from .engine import GatewayEngine, GatewayError, JobState

_GENERATED = Path(__file__).resolve().parent / "generated"
if str(_GENERATED) not in sys.path:
    sys.path.insert(0, str(_GENERATED))

import evaluation_gateway_pb2 as pb2  # noqa: E402
import evaluation_gateway_pb2_grpc as pb2_grpc  # noqa: E402


_STATE_TO_PROTO = {
    JobState.QUEUED: pb2.QUEUED,
    JobState.RUNNING: pb2.RUNNING,
    JobState.SUCCEEDED: pb2.SUCCEEDED,
    JobState.FAILED: pb2.FAILED,
    JobState.CANCELLED: pb2.CANCELLED,
}

_STATUS = {
    "INVALID_ARGUMENT": grpc.StatusCode.INVALID_ARGUMENT,
    "UNAUTHENTICATED": grpc.StatusCode.UNAUTHENTICATED,
    "PERMISSION_DENIED": grpc.StatusCode.PERMISSION_DENIED,
    "NOT_FOUND": grpc.StatusCode.NOT_FOUND,
    "FAILED_PRECONDITION": grpc.StatusCode.FAILED_PRECONDITION,
    "RESOURCE_EXHAUSTED": grpc.StatusCode.RESOURCE_EXHAUSTED,
    "INTERNAL": grpc.StatusCode.INTERNAL,
}


def _abort(context, code: str, message: str):
    context.abort(_STATUS.get(code, grpc.StatusCode.UNKNOWN), message)


def _tenant(auth: TokenAuth, context) -> str:
    meta = dict(context.invocation_metadata())
    try:
        return auth.authenticate(meta.get("authorization"))
    except AuthError as exc:
        return _abort(context, exc.code, exc.message)


def _handle_error(context, exc: Exception):
    if isinstance(exc, GatewayError):
        return _abort(context, exc.code, exc.message)
    return _abort(context, "INTERNAL", str(exc))


def _state(value: str) -> int:
    return _STATE_TO_PROTO.get(str(value), pb2.FAILED)


def _status_msg(status: Mapping[str, object]) -> pb2.JobStatus:
    msg = pb2.JobStatus(
        job_id=str(status.get("job_id") or ""),
        state=_state(str(status.get("state") or JobState.FAILED)),
        current_iteration=str(status.get("current_iteration") or ""),
        error=str(status.get("error") or ""),
    )
    for stage in status.get("stages") or []:
        st = msg.stages.add()
        st.name = str(stage.get("name") or "")
        st.status = str(stage.get("status") or "")
        for key, value in (stage.get("counts") or {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                st.counts[str(key)] = int(value)
    return msg


def _results_msg(results: Mapping[str, object]) -> pb2.EvaluationResults:
    msg = pb2.EvaluationResults(
        job_id=str(results.get("job_id") or ""),
        state=_state(str(results.get("state") or JobState.FAILED)),
        provenance_ok=bool(results.get("provenance_ok")),
        seed_json=str(results.get("seed_json") or ""),
    )
    outcomes = results.get("outcomes") or {}
    setattr(msg.outcomes, "pass", int(outcomes.get("PASS", results.get("pass") or 0) or 0))
    msg.outcomes.domain_fail = int(outcomes.get("DOMAIN_FAIL", results.get("fail") or 0) or 0)
    msg.outcomes.broken = int(outcomes.get("BROKEN", 0) or 0)
    msg.outcomes.timeout = int(outcomes.get("TIMEOUT", 0) or 0)
    msg.outcomes.infra_fail = int(outcomes.get("INFRA_FAIL", 0) or 0)
    for key, value in outcomes.items():
        if isinstance(value, int) and not isinstance(value, bool):
            msg.outcomes.raw[str(key)] = int(value)

    for cand in results.get("front") or []:
        c = msg.front.add()
        c.id = str(cand.get("id") or "")
        c.source_ref = str(cand.get("source_ref") or "")
        c.outcome = str(cand.get("outcome") or "")
        c.reason = str(cand.get("reason") or "")
        for key, value in (cand.get("objectives") or {}).items():
            try:
                c.objectives[str(key)] = float(value)
            except (TypeError, ValueError):
                pass
        for key, value in (cand.get("dimensions") or {}).items():
            c.dimensions[str(key)] = str(value)

    for point in results.get("points") or []:
        p = msg.points.add()
        for key, value in (point.get("objectives") or {}).items():
            try:
                p.objectives[str(key)] = float(value)
            except (TypeError, ValueError):
                pass

    counts = results.get("counts") or {}
    msg.counts.mandatory = int(counts.get("mandatory") or 0)
    msg.counts.post_sieve = int(counts.get("post_sieve") or 0)
    msg.counts.candidates = int(counts.get("candidates") or 0)
    msg.counts.processed = int(counts.get("processed") or 0)
    msg.counts.inserted = int(counts.get("inserted") or 0)

    iterate = results.get("iterate") or {}
    if iterate:
        msg.iterate.status = str(iterate.get("status") or "")
        msg.iterate.requested = int(iterate.get("requested") or 0)
        msg.iterate.completed = int(iterate.get("completed") or 0)
        msg.iterate.candidates.extend(int(x or 0) for x in (iterate.get("candidates") or []))
        msg.iterate.front_sizes.extend(int(x or 0) for x in (iterate.get("front_sizes") or []))
        msg.iterate.plan_statuses.extend(str(x or "") for x in (iterate.get("plan_statuses") or []))
    return msg


def _caps_msg(caps: Mapping[str, object]) -> pb2.CapabilitiesDoc:
    msg = pb2.CapabilitiesDoc(
        transport=str(caps.get("transport") or ""),
        grpc_python_available=bool(caps.get("grpc_python_available")),
    )
    msg.supported_languages.extend(str(x) for x in caps.get("supported_languages") or [])
    msg.supported_candidate_sinks.extend(str(x) for x in caps.get("supported_candidate_sinks") or [])
    msg.supported_execution_policy_profiles.extend(str(x) for x in caps.get("supported_execution_policy_profiles") or [])
    for key, value in (caps.get("limits") or {}).items():
        if isinstance(value, int) and not isinstance(value, bool):
            msg.limits[str(key)] = int(value)
    for key, value in (caps.get("components") or {}).items():
        msg.components[str(key)] = str(value)
    return msg


def _health_msg(health: Mapping[str, object]) -> pb2.HealthDoc:
    msg = pb2.HealthDoc(live=bool(health.get("live")), ready=bool(health.get("ready")))
    msg.reasons.extend(str(x) for x in health.get("reasons") or [])
    for key, value in (health.get("deps") or {}).items():
        msg.deps[str(key)] = str(value)
    return msg


class EvaluationGatewayServicer(pb2_grpc.EvaluationGatewayServicer):
    def __init__(self, engine: GatewayEngine, auth: TokenAuth):
        self.engine = engine
        self.auth = auth

    def Submit(self, request, context):
        tenant = _tenant(self.auth, context)
        try:
            health = self.engine.health()
            if not health.get("ready"):
                raise GatewayError(
                    "FAILED_PRECONDITION",
                    "gateway is not ready: " + ", ".join(health.get("reasons") or []),
                )
            handle = self.engine.submit(tenant, {
                "spec_toml": request.spec_toml,
                "language": request.language,
                "analyzer_goals": request.analyzer_goals,
                "iterations": request.iterations,
                "executor_pool": request.executor_pool,
                "candidate_sink": request.candidate_sink,
                "analysis_mode": request.analysis_mode,
                "execution_policy_profile": request.execution_policy_profile,
                "config_overrides": dict(request.config_overrides),
                "idempotency_key": request.idempotency_key,
            })
            self.engine.write_access_log(tenant, "submit", {"job_id": handle["job_id"], "state": handle["state"]})
            return pb2.JobHandle(job_id=str(handle["job_id"]), state=_state(str(handle["state"])))
        except Exception as exc:
            return _handle_error(context, exc)

    def GetStatus(self, request, context):
        tenant = _tenant(self.auth, context)
        try:
            return _status_msg(self.engine.status(tenant, request.job_id))
        except Exception as exc:
            return _handle_error(context, exc)

    def WatchStatus(self, request, context):
        tenant = _tenant(self.auth, context)
        last = None
        while context.is_active():
            try:
                status = self.engine.status(tenant, request.job_id)
            except Exception as exc:
                _handle_error(context, exc)
                return
            key = repr(status)
            if key != last:
                yield _status_msg(status)
                last = key
            if status.get("state") in JobState.TERMINAL:
                return
            time.sleep(0.5)

    def GetResults(self, request, context):
        tenant = _tenant(self.auth, context)
        try:
            return _results_msg(self.engine.results(tenant, request.job_id))
        except Exception as exc:
            return _handle_error(context, exc)

    def Cancel(self, request, context):
        tenant = _tenant(self.auth, context)
        try:
            status = self.engine.cancel(tenant, request.job_id)
            self.engine.write_access_log(tenant, "cancel", {"job_id": request.job_id, "state": status["state"]})
            return _status_msg(status)
        except Exception as exc:
            return _handle_error(context, exc)

    def ListJobs(self, request, context):
        tenant = _tenant(self.auth, context)
        try:
            jobs = self.engine.list_jobs(tenant, request.state or None).get("jobs") or []
            out = pb2.JobList()
            for job in jobs:
                item = out.jobs.add()
                item.job_id = str(job.get("job_id") or "")
                item.state = _state(str(job.get("state") or JobState.FAILED))
                item.submitted_at = str(job.get("submitted_at") or "")
                item.terminal_at = str(job.get("terminal_at") or "")
            return out
        except Exception as exc:
            return _handle_error(context, exc)

    def Capabilities(self, request, context):
        _tenant(self.auth, context)
        try:
            caps = dict(self.engine.capabilities())
            caps["transport"] = "grpc"
            return _caps_msg(caps)
        except Exception as exc:
            return _handle_error(context, exc)

    def Health(self, request, context):
        return _health_msg(self.engine.health())


def serve_grpc(engine: GatewayEngine, auth: TokenAuth, *, host: str, port: int,
               tls_cert: str = "", tls_key: str = "") -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pb2_grpc.add_EvaluationGatewayServicer_to_server(EvaluationGatewayServicer(engine, auth), server)
    addr = f"{host}:{port}"
    if tls_cert and tls_key:
        cert = Path(tls_cert).read_bytes()
        key = Path(tls_key).read_bytes()
        server.add_secure_port(addr, grpc.ssl_server_credentials(((key, cert),)))
    else:
        server.add_insecure_port(addr)
    server.start()
    return server
