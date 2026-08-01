from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Iterable, Mapping

from ..jsonio import read_json, write_json_atomic
from ..runs import generate_run_id

JOB_REGISTRY_SCHEMA = "bundle.gateway.job/v1"
IDEMPOTENCY_SCHEMA = "bundle.gateway.idempotency/v1"

_TENANT_RE = re.compile(r"[^A-Za-z0-9_.-]")


class RegistryError(Exception):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slug_tenant(value: str) -> str:
    tenant = _TENANT_RE.sub("-", (value or "").strip()).strip("-.")
    if not tenant:
        raise RegistryError("tenant must not be empty")
    if not re.match(r"^[A-Za-z0-9]", tenant):
        tenant = "t-" + tenant
    return tenant[:80]


def new_job_id() -> str:
    return generate_run_id(f"gw-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}")


def _idem_name(tenant: str, key: str) -> str:
    digest = hashlib.sha256((tenant + "\0" + key).encode("utf-8")).hexdigest()
    return f"{digest}.json"


class JobRegistry:
    """Durable per-tenant job registry.

    Records are deliberately plain JSON files, written atomically through the
    existing bundle jsonio helper. This keeps the gateway aligned with the run
    journal's persistence posture and avoids introducing SQLite just for v1.
    """

    def __init__(self, runs_root: "Path | str"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def tenant_root(self, tenant: str) -> Path:
        root = self.runs_root / slug_tenant(tenant)
        root.mkdir(parents=True, exist_ok=True)
        (root / "_registry").mkdir(parents=True, exist_ok=True)
        (root / "_jobs").mkdir(parents=True, exist_ok=True)
        return root

    def registry_dir(self, tenant: str) -> Path:
        return self.tenant_root(tenant) / "_registry"

    def job_path(self, tenant: str, job_id: str) -> Path:
        return self.registry_dir(tenant) / f"{job_id}.json"

    def idempotency_dir(self, tenant: str) -> Path:
        d = self.registry_dir(tenant) / "idempotency"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def idempotency_path(self, tenant: str, key: str) -> Path:
        return self.idempotency_dir(tenant) / _idem_name(tenant, key)

    def write(self, record: Mapping[str, object]) -> None:
        tenant = str(record["tenant"])
        job_id = str(record["job_id"])
        data = dict(record)
        data["schema"] = JOB_REGISTRY_SCHEMA
        with self._lock:
            write_json_atomic(self.job_path(tenant, job_id), data)

    def create(self, tenant: str, fields: Mapping[str, object]) -> tuple[dict, bool]:
        tenant = slug_tenant(tenant)
        idem = str(fields.get("idempotency_key") or "")
        with self._lock:
            if idem:
                p = self.idempotency_path(tenant, idem)
                if p.exists():
                    idx = read_json(p)
                    existing = self.get(tenant, str(idx["job_id"]))
                    return existing, False
            job_id = str(fields.get("job_id") or new_job_id())
            if self.job_path(tenant, job_id).exists():
                raise RegistryError(f"job_id={job_id!r} already exists for tenant={tenant!r}")
            record = {
                "schema": JOB_REGISTRY_SCHEMA,
                "job_id": job_id,
                "tenant": tenant,
                "state": "QUEUED",
                "submitted_at": now_iso(),
                "terminal_at": "",
                "error": "",
                "pid": None,
                "pgid": None,
                "cmd": [],
                **dict(fields),
                "job_id": job_id,
                "tenant": tenant,
            }
            self.write(record)
            if idem:
                write_json_atomic(self.idempotency_path(tenant, idem), {
                    "schema": IDEMPOTENCY_SCHEMA,
                    "tenant": tenant,
                    "idempotency_key_sha256": hashlib.sha256(idem.encode("utf-8")).hexdigest(),
                    "job_id": job_id,
                    "created_at": record["submitted_at"],
                })
            return record, True

    def get(self, tenant: str, job_id: str) -> dict:
        tenant = slug_tenant(tenant)
        path = self.job_path(tenant, job_id)
        if not path.exists():
            raise RegistryError(f"unknown job_id={job_id!r} for tenant={tenant!r}")
        data = read_json(path)
        if data.get("schema") != JOB_REGISTRY_SCHEMA:
            raise RegistryError(f"job registry record {path} has unsupported schema {data.get('schema')!r}")
        if data.get("tenant") != tenant:
            raise RegistryError(f"job_id={job_id!r} belongs to a different tenant")
        return dict(data)

    def update(self, tenant: str, job_id: str, **fields: object) -> dict:
        with self._lock:
            record = self.get(tenant, job_id)
            record.update(fields)
            self.write(record)
            return record

    def mark_state(self, tenant: str, job_id: str, state: str, *, error: str = "") -> dict:
        fields: dict[str, object] = {"state": state}
        if error:
            fields["error"] = error
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            fields["terminal_at"] = now_iso()
        return self.update(tenant, job_id, **fields)

    def list(self, tenant: str, state: "str | None" = None) -> list[dict]:
        tenant = slug_tenant(tenant)
        d = self.registry_dir(tenant)
        jobs = []
        for path in sorted(d.glob("*.json")):
            try:
                data = read_json(path)
            except Exception:
                continue
            if data.get("schema") != JOB_REGISTRY_SCHEMA:
                continue
            if state and data.get("state") != state:
                continue
            jobs.append(dict(data))
        return jobs

    def tenants(self) -> Iterable[str]:
        for p in self.runs_root.iterdir():
            if p.is_dir() and (p / "_registry").is_dir():
                yield p.name

    def all_jobs(self) -> list[dict]:
        out = []
        for tenant in self.tenants():
            out.extend(self.list(tenant))
        return out
