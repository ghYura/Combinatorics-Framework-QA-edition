from __future__ import annotations

import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

from .config import BundleConfig
from .database import psql
from .process import run
from .runs import file_sha256
from .stages import CORE_JAR, CORE_PROPS, READER_JAR, SRC

DOCTOR_SCHEMA = "bundle.doctor/v1"


class Severity(str, Enum):
    """STEP 15 action 3 — three levels, ordered worst-last for `max()`-style
    aggregation. OK = nothing to act on; WARNING = degraded but runnable;
    BLOCKING = `bundle run` would fail preflight (or worse) on this environment."""

    OK = "OK"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"

    @property
    def rank(self) -> int:
        return (Severity.OK, Severity.WARNING, Severity.BLOCKING).index(self)


@dataclass(frozen=True)
class DoctorCheck:
    """One diagnosed environment fact: a name, its severity, a human-readable
    summary, and optional structured details. Doctor performs read-only probes —
    it never creates/modifies anything in a production DB or installs
    dependencies (action 4/5); this is purely an observation record."""

    name: str
    severity: Severity
    message: str
    details: "Sequence[str]" = field(default_factory=tuple)


def _check(name, severity, message, *details) -> DoctorCheck:
    return DoctorCheck(name=name, severity=severity, message=message, details=tuple(details))


# ------------------------------- individual probes -------------------------- #
def _check_python(cfg: BundleConfig) -> DoctorCheck:
    v = sys.version_info
    name = "python"
    if v < (3, 8):
        return _check(name, Severity.BLOCKING, f"Python {v.major}.{v.minor}.{v.micro} too old (need >= 3.8)")
    try:
        import pg8000  # noqa: F401
    except Exception:
        return _check(name, Severity.BLOCKING, f"Python {v.major}.{v.minor}.{v.micro}, but pg8000 missing",
                      "install: pip install --break-system-packages pg8000")
    return _check(name, Severity.OK, f"Python {v.major}.{v.minor}.{v.micro}, pg8000 present")


def _check_java(cfg: BundleConfig) -> DoctorCheck:
    name = "java"
    r = run([cfg.java_cmd, "-version"])
    if not r.ok:
        return _check(name, Severity.BLOCKING, f"'{cfg.java_cmd} -version' failed",
                      f"rc={r.returncode}: {(r.stderr or r.stdout).strip().splitlines()[:1]}")
    line = (r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else cfg.java_cmd
    return _check(name, Severity.OK, line)


_MANIFEST_VERSION_RE = re.compile(
    r"^(?:Implementation-Version|Specification-Version|Bundle-Version):\s*(.+?)\s*$", re.MULTILINE)
_FILENAME_VERSION_RE = re.compile(r"-(\d[\w.\-]*?)(?:-shaded)?\.jar$")


def jar_version(jar: Path) -> "Optional[str]":
    """Best-effort jar version: prefer `META-INF/MANIFEST.MF`'s
    Implementation-/Specification-/Bundle-Version (what `java -jar ... --version`
    would itself report on a well-built artifact), falling back to the
    `-<version>[-shaded].jar` filename convention these jars are built with.
    `None` if neither source yields anything — never raises on a malformed jar."""
    try:
        with zipfile.ZipFile(jar) as zf:
            try:
                manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
            except KeyError:
                manifest = ""
        m = _MANIFEST_VERSION_RE.search(manifest)
        if m:
            return m.group(1)
    except (OSError, zipfile.BadZipFile):
        pass
    m = _FILENAME_VERSION_RE.search(jar.name)
    return m.group(1) if m else None


def _jar_check(name, jar: Path, label: str) -> DoctorCheck:
    if not jar.exists():
        return _check(name, Severity.BLOCKING, f"{label} missing: {jar}",
                      "build it or point BundleConfig at an existing build (core_jar/reader_jar)")
    try:
        sha = file_sha256(jar)
        size = jar.stat().st_size
    except OSError as exc:
        return _check(name, Severity.WARNING, f"{label} present but unreadable: {jar}", str(exc))
    version = jar_version(jar)
    version_desc = version if version else "(unknown — no MANIFEST.MF/filename version found)"
    return _check(name, Severity.OK, f"{label} present, version={version_desc} ({size} bytes)",
                  f"path={jar}", f"sha256={sha}")


def _check_core_jar(cfg: BundleConfig) -> DoctorCheck:
    jar = Path(cfg.core_jar) if cfg.core_jar else CORE_JAR
    return _jar_check("core_jar", jar, "Core jar")


def _check_reader_jar(cfg: BundleConfig) -> DoctorCheck:
    jar = Path(cfg.reader_jar) if cfg.reader_jar else READER_JAR
    return _jar_check("reader_jar", jar, "Reader jar")


def _check_analyzer(cfg: BundleConfig) -> DoctorCheck:
    name = "analyzer"
    az = SRC / "Analyzer_trunk"
    jar = az / "target/heuristic-analyzer-flatlaf-1.0.0.jar"
    src = az / "AnalyzeKv.java"
    if not (jar.exists() and src.exists()):
        return _check(name, Severity.WARNING, f"Analyzer artifact/source not found under {az}",
                      "Bundle runs without it ('--analyzer' becomes a no-op corpus collection)")
    real_cls, real_cp = az / "target/analyzekv/AnalyzeKv.class", az / "analyzer_cp.txt"
    if real_cls.exists() and real_cp.exists():
        return _check(name, Severity.OK, "Analyzer build + classpath present",
                      f"classes={real_cls}", f"classpath={real_cp}")
    return _check(name, Severity.OK, "Analyzer artifact/source present; lazy driver build available",
                  f"jar={jar}",
                  "no persisted driver/classpath; first '--analyzer' run prepares them under /tmp")


def _db_check(name, label, host, port, user, password, want_db) -> DoctorCheck:
    if run(["pg_isready", "-h", host, "-p", str(port)]).returncode != 0:
        return _check(name, Severity.BLOCKING, f"{label} PostgreSQL not accepting on {host}:{port}",
                      "start it, e.g.: sudo pg_ctlcluster <ver> main start")
    if not password:
        return _check(name, Severity.BLOCKING, f"{label} DB up on {host}:{port}, but no password configured",
                      "set BUNDLE_MAIN_DB_PASSWORD/BUNDLE_RESULTS_DB_PASSWORD (or --*-db-password / config file)")
    out, rc = psql(port, want_db, "select version();", host=host, user=user, password=password)
    if rc != 0:
        return _check(name, Severity.BLOCKING, f"{label} DB up on {host}:{port} but auth/connect to '{want_db}' failed",
                      f"psql rc={rc}")
    version_line = out.splitlines()[0] if out else "(no version string)"
    return _check(name, Severity.OK, f"{label} DB {host}:{port} reachable as '{user}'", version_line)


def _check_main_db(cfg: BundleConfig) -> DoctorCheck:
    return _db_check("main_db", "main", cfg.main_db_host, cfg.main_db_port,
                     cfg.main_db_user, cfg.main_db_password, "postgres")


def _check_results_db(cfg: BundleConfig) -> DoctorCheck:
    return _db_check("results_db", "results", cfg.results_db_host, cfg.results_db_port,
                     cfg.results_db_user, cfg.results_db_password, "postgres")


def _check_db_privileges(cfg: BundleConfig) -> DoctorCheck:
    """STEP 15 action 1: 'required DB privileges' — read-only probe, never
    creates anything (action 4: doctor touches no production DB state). Asks
    Postgres whether the configured role *could* create databases/roles, the
    privilege every Bundle run actually exercises (`stage_core` provisions a
    fresh per-run database)."""
    name = "db_privileges"
    if not cfg.main_db_password:
        return _check(name, Severity.BLOCKING, "cannot probe privileges — main DB password not configured")
    out, rc = psql(cfg.main_db_port, "postgres",
                   "select rolcreatedb, rolcreaterole from pg_roles where rolname = current_user;",
                   host=cfg.main_db_host, user=cfg.main_db_user, password=cfg.main_db_password)
    if rc != 0:
        return _check(name, Severity.BLOCKING, "could not query pg_roles for current user", f"psql rc={rc}")
    parts = [p.strip() for p in out.split("|")]
    createdb = len(parts) > 0 and parts[0] == "t"
    if not createdb:
        return _check(name, Severity.BLOCKING,
                      f"role '{cfg.main_db_user}' lacks CREATEDB — Bundle provisions a fresh DB per run",
                      "grant: ALTER ROLE <user> CREATEDB;")
    return _check(name, Severity.OK, f"role '{cfg.main_db_user}' has CREATEDB")


def _parse_properties_kv_csv(raw: str) -> "dict[str, str]":
    """Mirror of Core's AppConfig.parseKvMap: comma-separated `key ; value`
    pairs (whitespace-tolerant); entries without a `;` are ignored."""
    out: "dict[str, str]" = {}
    for pair in raw.split(","):
        if ";" in pair:
            k, _, v = pair.partition(";")
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def _check_tablespace_provisioning(cfg: BundleConfig) -> DoctorCheck:
    """States whether Core-side named-tablespace provisioning is active for the
    properties this Bundle ships to a run. Nothing requested (the canonical
    default) → provisioning is inert and tables land on the database's default
    tablespace. Requests present → Core provisions them only when the
    PostgreSQL server can see the configured directories, and FAILS the run
    closed otherwise — there is no silent fall-through to pg_default."""
    name = "tablespace_provisioning"
    props = Path(cfg.core_props) if getattr(cfg, "core_props", None) else CORE_PROPS
    if not props.exists():
        return _check(name, Severity.WARNING, f"core properties not found: {props}",
                      "cannot determine whether tablespace provisioning is requested")
    # .properties line-continuations: join backslash-terminated lines first.
    text = re.sub(r"\\\s*\n", " ", props.read_text(encoding="utf-8"))
    tablespaces: "dict[str, str]" = {}
    databases: "dict[str, str]" = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key == "db.tablespace2pathMappingCSVList":
            tablespaces = _parse_properties_kv_csv(value)
        elif key == "db.database2tablespaceMappingCSVList":
            databases = _parse_properties_kv_csv(value)
    if not tablespaces and not databases:
        return _check(name, Severity.OK,
                      "inactive — no named tablespaces requested; tables use the database default tablespace",
                      f"source={props}")
    details = [f"source={props}"]
    details += [f"tablespace {k} -> {v}" for k, v in tablespaces.items()]
    details += [f"database {k} -> tablespace {v}" for k, v in databases.items()]
    return _check(name, Severity.WARNING,
                  f"ACTIVE — {len(tablespaces)} tablespace(s), {len(databases)} database(s) requested; "
                  "Core fails the run closed unless the PostgreSQL server can see the configured directories",
                  *details)


def _check_scratch(cfg: BundleConfig) -> DoctorCheck:
    name = "scratch"
    root = Path(cfg.scratch_root) if cfg.scratch_root else Path("/tmp/fw_work")
    probe_dir = root / ".doctor-probe"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file = probe_dir / "write-test"
        probe_file.write_text("doctor\n", encoding="utf-8")
        probe_file.unlink()
        probe_dir.rmdir()
    except OSError as exc:
        return _check(name, Severity.BLOCKING, f"scratch root not writable: {root}", str(exc))
    try:
        usage = shutil.disk_usage(root)
        st = os.statvfs(root)
        free_inodes = st.f_favail
    except OSError as exc:
        return _check(name, Severity.WARNING, f"scratch root writable but stat failed: {root}", str(exc))
    free_gb = usage.free / (1024 ** 3)
    details = [f"path={root}", f"free={free_gb:.1f} GiB", f"free_inodes={free_inodes}"]
    if free_gb < 1.0:
        return _check(name, Severity.BLOCKING, f"scratch root nearly full: {free_gb:.2f} GiB free", *details)
    if free_gb < 5.0 or free_inodes < 100_000:
        return _check(name, Severity.WARNING, f"scratch root low on space/inodes: {free_gb:.1f} GiB, {free_inodes} inodes",
                      *details)
    return _check(name, Severity.OK, f"scratch root writable, {free_gb:.1f} GiB free", *details)


# OS-level isolation mechanisms a future STEP-28 backend could realistically
# drive (checked by executable presence, cheapest real signal short of actually
# wiring a backend selector that doesn't exist yet).
_SANDBOX_BACKEND_EXES = ("bwrap", "firejail", "nsjail", "unshare")

#: Backends the Python Executor actually implements (``Executor_trunk/sandbox.py``),
#: mapped to the host executable each one drives. Kept deliberately narrow: an
#: isolation tool being installed is not the same as this project being able to
#: drive it, and reporting `unshare`/`nsjail` as "available backends" overstated
#: what a secure run can actually select.
IMPLEMENTED_SANDBOX_BACKENDS = {
    "container": ("docker", "podman"),
    "bubblewrap": ("bwrap",),
}


def available_sandbox_backends() -> "tuple[str, ...]":
    """Which of `_SANDBOX_BACKEND_EXES` are on PATH, in priority order.

    Retained for callers that want the raw OS-level probe; `_check_sandbox`
    reports against `IMPLEMENTED_SANDBOX_BACKENDS` instead, because that is the
    set a policy can actually name.
    """
    return tuple(exe for exe in _SANDBOX_BACKEND_EXES if shutil.which(exe))


def _executor_sandbox_module():
    """The Python Executor's `sandbox` module, or None if it cannot be imported.

    It lives in a sibling trunk rather than this package, so a partial checkout
    (or a docs-only clone) legitimately has no copy of it.
    """
    path = SRC / "Executor_trunk"
    if not (path / "sandbox.py").is_file():
        return None
    try:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        import sandbox                                    # noqa: PLC0415
        return sandbox
    except Exception:                                     # pragma: no cover - defensive
        return None


def usable_sandbox_backends() -> "tuple[str, ...]":
    """Backends a secure run could actually select on this host, in policy order.

    Asks the Executor through the *production* selection path (`build_sandbox`),
    so the answer is the one a real run would get, including each backend's
    functional self-test. A host executable being installed is not the same as
    the backend working: `bwrap` on PATH with user namespaces unavailable is
    exactly the case where a PATH probe says yes and the run says no. Doctor
    exists to predict the run, so it must not be the more optimistic of the two.

    Falls back to the PATH heuristic only when the Executor cannot be imported,
    and that fallback is reported as such by `_check_sandbox`.
    """
    sandbox = _executor_sandbox_module()
    if sandbox is None:
        return tuple(backend for backend, exes in IMPLEMENTED_SANDBOX_BACKENDS.items()
                     if any(shutil.which(exe) for exe in exes))
    usable = []
    for backend in IMPLEMENTED_SANDBOX_BACKENDS:
        probe = {"profile": "doctor-probe", "backend": backend, "trusted": False}
        try:
            if sandbox.build_sandbox(probe, runner="py", host_python=sys.executable) is not None:
                usable.append(backend)
        except Exception:
            continue                                      # unusable, or not implemented
    return tuple(usable)


def _check_sandbox(cfg: BundleConfig) -> DoctorCheck:
    """STEP 15 action 1 'sandbox backend availability', reporting what a secure
    run can actually select today.

    `cfg.sandbox_policy` remains a legacy free-form label; the operative choice
    is the execution-policy profile's `backend`, and the Python Executor
    implements `container` (rootless Docker/Podman) and `bubblewrap`. Both are
    live: `build_sandbox` constructs the backend, self-tests it, and raises
    `SandboxUnavailable` rather than falling back to unsandboxed execution, so a
    secure profile on a host without its backend refuses to run instead of
    quietly degrading.

    policy='none' means isolation is explicitly opted out, so absence of a
    backend is not a finding.
    """
    name = "sandbox"
    policy = cfg.sandbox_policy
    if policy == "none":
        return _check(name, Severity.OK, "sandbox_policy='none' — isolation explicitly disabled")
    usable = usable_sandbox_backends()
    known = ", ".join(IMPLEMENTED_SANDBOX_BACKENDS)
    if usable:
        return _check(name, Severity.OK,
                      f"sandbox_policy='{policy}', usable backend(s): {', '.join(usable)}",
                      "profiles 'generated-default'/'networked-api-probe' select backend "
                      "'container'; 'trusted-local' is the explicit unsandboxed opt-in",
                      "a secure profile whose backend is unusable fails closed "
                      "(SandboxUnavailable) — it never falls back to running candidates "
                      "unsandboxed")
    return _check(name, Severity.WARNING,
                  f"sandbox_policy='{policy}', but no implemented backend is usable "
                  f"(need one of: {known})",
                  "install a container runtime (docker/podman) or bubblewrap; without one, "
                  "every sandboxed profile refuses to start",
                  "not blocking on its own — 'trusted-local' still runs, unsandboxed by design")


def _check_container_runtime(cfg: BundleConfig) -> DoctorCheck:
    """A container runtime is what the `container` sandbox backend drives, so it
    is a live dependency of every sandboxed profile — not a future one."""
    name = "container_runtime"
    for exe in ("docker", "podman"):
        path = shutil.which(exe)
        if path:
            r = run([exe, "--version"])
            ver = (r.stdout or r.stderr).strip().splitlines()[0] if r.ok else exe
            return _check(name, Severity.OK, f"{ver}", f"path={path}",
                          "drives the 'container' sandbox backend used by "
                          "'generated-default' and 'networked-api-probe'")
    return _check(name, Severity.WARNING, "no container runtime found (docker/podman)",
                  "required by the 'container' sandbox backend: without it "
                  "'generated-default' and 'networked-api-probe' refuse to start",
                  "not blocking on its own — 'trusted-local' still runs, unsandboxed by design")


# Order matters for the human table; it is also the canonical check-name list.
def _check_component_inventory(cfg: BundleConfig) -> DoctorCheck:
    """STEP 42: record each component's canonical build + declared version +
    actual artifact hash. WARNING if a build artifact is missing (the canonical
    build hasn't been run); the full machine-readable matrix is `bundle inventory`."""
    from . import inventory
    inv = inventory.build_inventory()
    details = tuple(
        f"{c['name']}: {c['declared_version']} "
        + (f"sha256={c['sha256'][:12]}…" if c.get("sha256") else "(artifact MISSING)")
        + f"  [{c['build_command']}]"
        for c in inv["components"]
    )
    missing = [c["name"] for c in inv["components"] if c["kind"] == "maven" and not c["exists"]]
    if missing:
        return _check("component_inventory", Severity.WARNING,
                      f"{len(missing)} build artifact(s) missing: {', '.join(missing)} — run the canonical build",
                      *details)
    versions = ", ".join(f"{c['name']}={c['declared_version']}" for c in inv["components"])
    return _check("component_inventory", Severity.OK,
                  f"{len(inv['components'])} components inventoried ({versions})", *details)


def _check_capability_matrix(cfg: BundleConfig) -> DoctorCheck:
    """Report what THIS configuration resolves to in the capability registry.

    Diagnostic, not a gate: `preflight` is the enforcement point. Doctor's job is
    to tell an operator, before they build a command line, whether the run they
    intend is supported — and if not, which stable reason code to look up.
    """
    from . import capabilities as caps
    selection = {
        "candidate_sink": getattr(cfg, "candidate_sink", "loose-files"),
        "execution_policy": (getattr(cfg, "execution_policy_profile", "") or "").strip(),
        "executor_pool": "multi" if int(getattr(cfg, "executor_pool_size", 1) or 1) > 1 else "single",
        "repeat": "k_gt_1" if int(getattr(cfg, "repeat_each_candidate", 1) or 1) > 1 else "k1",
        "analyzer": "formal" if getattr(cfg, "analyzer_goals", "") else "none",
    }
    matrix = caps.capability_matrix()
    counts = matrix["counts"]
    summary = (f"{len(matrix['rules'])} rules; {counts[caps.SUPPORTED]} supported / "
               f"{counts[caps.EXPERIMENTAL]} experimental / {counts[caps.UNSUPPORTED]} unsupported "
               f"of {sum(counts.values())} combinations")
    try:
        verdict = caps.classify(selection)
    except caps.UnknownDimensionValue as exc:
        return _check("capability_matrix", Severity.BLOCKING,
                      f"configuration names an unknown capability value: {exc}", summary)
    details = [summary, f"resolved selection: {verdict.selection}"]
    if not selection["execution_policy"]:
        details.append("execution policy not configured — the run path will refuse until one is "
                       "chosen (plan does not need one)")
    for code in verdict.codes:
        rule = caps.RULES_BY_CODE[code]
        details.append(f"{rule.level} {code}: {rule.title}")
    if verdict.blocking_code:
        return _check("capability_matrix", Severity.BLOCKING,
                      f"this configuration is UNSUPPORTED ({verdict.blocking_code})", *details)
    if verdict.level == caps.EXPERIMENTAL:
        return _check("capability_matrix", Severity.WARNING,
                      "this configuration is EXPERIMENTAL", *details)
    return _check("capability_matrix", Severity.OK,
                  "this configuration is SUPPORTED", *details)


_PROBES = (
    _check_python,
    _check_java,
    _check_core_jar,
    _check_reader_jar,
    _check_analyzer,
    _check_main_db,
    _check_results_db,
    _check_db_privileges,
    _check_tablespace_provisioning,
    _check_scratch,
    _check_container_runtime,
    _check_sandbox,
    _check_component_inventory,
    _check_capability_matrix,
)


def run_doctor(cfg: BundleConfig) -> "tuple[DoctorCheck, ...]":
    """Run every probe and return its `DoctorCheck`, in canonical order.

    Read-only: no production-DB writes, no dependency installation (action 4/5
    — Doctor *diagnoses*, `bundle run`'s preflight is what gates an actual run)."""
    return tuple(probe(cfg) for probe in _PROBES)


_SEVERITY_GLYPH = {Severity.OK: "✓", Severity.WARNING: "!", Severity.BLOCKING: "✗"}


def format_doctor_report(checks: "Sequence[DoctorCheck]") -> str:
    """Human-readable table: one line per check, glyph + severity + name + message,
    followed by any details indented underneath. Secret values never reach here —
    every probe reports connectivity/role facts, never a password (action 3:
    'Secret values не печатаются')."""
    lines = []
    width = max((len(c.name) for c in checks), default=0)
    for c in checks:
        glyph = _SEVERITY_GLYPH[c.severity]
        lines.append(f"  {glyph} [{c.severity.value:<8}] {c.name:<{width}}  {c.message}")
        for d in c.details:
            lines.append(f"      {d}")
    return "\n".join(lines)


def doctor_report_to_dict(checks: "Sequence[DoctorCheck]") -> dict:
    worst = max((c.severity for c in checks), default=Severity.OK, key=lambda s: s.rank)
    return {
        "schema": DOCTOR_SCHEMA,
        "overall": worst.value,
        "checks": [
            {"name": c.name, "severity": c.severity.value, "message": c.message, "details": list(c.details)}
            for c in checks
        ],
    }


def doctor_exit_code(checks: "Sequence[DoctorCheck]") -> int:
    """Action 'Exit non-zero только при blocking checks' — WARNING alone keeps
    exit 0 so e.g. CI can run `bundle doctor` informationally without a missing
    optional component (analyzer, container runtime, ...) failing the job."""
    return 1 if any(c.severity is Severity.BLOCKING for c in checks) else 0
