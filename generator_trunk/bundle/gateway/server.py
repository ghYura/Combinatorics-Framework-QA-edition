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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

from __future__ import annotations

import argparse
import http.server
import importlib.util
import json
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .auth import AuthError, TokenAuth
from .engine import GatewayConfig, GatewayEngine, GatewayError, GatewayLimits


def _json_bytes(body) -> bytes:
    return json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def make_handler(engine: GatewayEngine, auth: TokenAuth):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
            if isinstance(body, (dict, list)):
                body = _json_bytes(body)
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _send_error(self, code: int, status: str, message: str) -> None:
            self._send(code, {"error": {"code": status, "message": message}})

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except Exception as exc:
                raise GatewayError("INVALID_ARGUMENT", f"request body is not valid JSON: {exc}")
            if not isinstance(data, dict):
                raise GatewayError("INVALID_ARGUMENT", "request body must be a JSON object")
            return data

        def _tenant(self) -> str:
            try:
                return auth.authenticate(self.headers.get("Authorization"))
            except AuthError as exc:
                raise GatewayError(exc.code, exc.message, http_status=401) from exc

        def _dispatch(self, func):
            try:
                func()
            except GatewayError as exc:
                self._send_error(exc.http_status, exc.code, exc.message)
            except BrokenPipeError:
                pass
            except Exception as exc:
                self._send_error(500, "INTERNAL", str(exc))

        def do_GET(self):
            self._dispatch(self._get)

        def do_POST(self):
            self._dispatch(self._post)

        def _get(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            q = parse_qs(parsed.query)
            if path == "/v1/health":
                self._send(200, engine.health())
                return
            if path == "/v1/capabilities":
                self._tenant()
                self._send(200, engine.capabilities())
                return
            if path == "/v1/jobs":
                tenant = self._tenant()
                state = (q.get("state") or [""])[0] or None
                self._send(200, engine.list_jobs(tenant, state))
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[:3] == ["", "v1", "jobs"]:
                tenant = self._tenant()
                job_id, action = parts[3], parts[4]
                if action == "status":
                    self._send(200, engine.status(tenant, job_id))
                    return
                if action == "results":
                    self._send(200, engine.results(tenant, job_id))
                    return
                if action == "log":
                    cursor = int((q.get("cursor") or ["0"])[0] or 0)
                    self._send(200, engine.tail_log(tenant, job_id, cursor))
                    return
                if action == "watch":
                    self._watch(tenant, job_id)
                    return
            self._send_error(404, "NOT_FOUND", "not found")

        def _post(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            if path == "/v1/submit":
                tenant = self._tenant()
                health = engine.health()
                if not health.get("ready"):
                    raise GatewayError("FAILED_PRECONDITION", "gateway is not ready: " + ", ".join(health.get("reasons") or []), http_status=503)
                body = self._body()
                handle = engine.submit(tenant, body)
                engine.write_access_log(tenant, "submit", {"job_id": handle["job_id"], "state": handle["state"]})
                self._send(200, {"job_id": handle["job_id"], "state": handle["state"]})
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[:3] == ["", "v1", "jobs"]:
                tenant = self._tenant()
                if parts[4] == "cancel":
                    status = engine.cancel(tenant, parts[3])
                    engine.write_access_log(tenant, "cancel", {"job_id": parts[3], "state": status["state"]})
                    self._send(200, status)
                    return
                if parts[4] == "cleanup":
                    report = engine.cleanup_job(tenant, parts[3])
                    engine.write_access_log(tenant, "cleanup", {"job_id": parts[3]})
                    self._send(200, report)
                    return
            self._send_error(404, "NOT_FOUND", "not found")

        def _watch(self, tenant: str, job_id: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = None
            while True:
                status = engine.status(tenant, job_id)
                encoded = json.dumps(status, sort_keys=True, ensure_ascii=False)
                if encoded != last:
                    self.wfile.write(encoded.encode("utf-8") + b"\n")
                    self.wfile.flush()
                    last = encoded
                if status.get("state") in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    return
                time.sleep(0.5)

    return Handler


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bundle_gateway", description="Bundle Evaluation Gateway")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--runs-root", default="/tmp/fw_gateway_runs")
    ap.add_argument("--tokens-file", default=".bundle-gateway-tokens.json")
    ap.add_argument("--max-concurrent-jobs", type=int, default=1)
    ap.add_argument("--max-worker-units", type=int, default=4)
    ap.add_argument("--max-executor-pool", type=int, default=4)
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--timeout-seconds", type=float, default=24 * 3600)
    ap.add_argument("--retention-seconds", type=float, default=0.0,
                    help="on startup, clean terminal jobs older than this many seconds; 0 disables")
    ap.add_argument("--tls-cert", default="")
    ap.add_argument("--tls-key", default="")
    ap.add_argument("--transport", choices=["auto", "grpc", "http-json"], default="auto",
                    help="wire transport: auto picks grpc when grpcio is importable, else http-json")
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_arg_parser().parse_args(argv)
    grpc_available = bool(importlib.util.find_spec("grpc") and importlib.util.find_spec("grpc_tools"))
    transport = args.transport
    if transport == "auto":
        transport = "grpc" if grpc_available else "http-json"
    if transport == "grpc" and not grpc_available:
        print("error: --transport grpc requested but grpcio/grpc_tools are not importable", file=sys.stderr)
        return 2
    if not _loopback(args.host) and not (args.tls_cert and args.tls_key):
        print("error: refusing plaintext gateway bind on non-loopback interface; provide --tls-cert and --tls-key", file=sys.stderr)
        return 2
    gen_dir = Path(__file__).resolve().parents[2]
    limits = GatewayLimits(
        max_concurrent_jobs=args.max_concurrent_jobs,
        max_worker_units=args.max_worker_units,
        max_executor_pool=args.max_executor_pool,
        max_iterations=args.max_iterations,
        default_timeout_seconds=args.timeout_seconds,
    )
    try:
        auth = TokenAuth(Path(args.tokens_file))
    except AuthError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2
    engine = GatewayEngine(GatewayConfig(gen_dir=gen_dir, runs_root=Path(args.runs_root), limits=limits,
                                         transport=transport, retention_seconds=args.retention_seconds))
    if transport == "grpc":
        from .grpc_service import serve_grpc
        server = serve_grpc(engine, auth, host=args.host, port=args.port,
                            tls_cert=args.tls_cert, tls_key=args.tls_key)
        scheme = "grpcs" if args.tls_cert else "grpc"
        print(f"Bundle Evaluation Gateway at {scheme}://{args.host}:{args.port}/")
        print("  transport: grpc")
        print(f"  runs_root: {Path(args.runs_root).resolve()}")
        try:
            server.wait_for_termination()
        except KeyboardInterrupt:
            print("\nstopping...")
            server.stop(grace=3).wait()
        return 0

    httpd = http.server.ThreadingHTTPServer((args.host, args.port), make_handler(engine, auth))
    if args.tls_cert and args.tls_key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(args.tls_cert, args.tls_key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    scheme = "https" if args.tls_cert else "http"
    print(f"Bundle Evaluation Gateway at {scheme}://{args.host}:{args.port}/")
    print("  transport: http-json")
    print(f"  runs_root: {Path(args.runs_root).resolve()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
