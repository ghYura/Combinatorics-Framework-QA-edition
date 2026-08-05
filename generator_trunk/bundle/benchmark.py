"""STEP 40 — stage-specific benchmark harness.

Confirms scale claims SEPARATELY, per stage — never as one fused "end-to-end at
scale" number. Each stage (Generator / Core / sieve / Reader loose|shard /
Executor local|sandbox|workers / Analyzer) is timed independently at a chosen
size profile; the report captures the environment (hardware / OS / toolchain /
component hashes / DB settings) and per-stage wall/CPU/peak-memory/disk/WAL/
throughput, and is emitted as versioned JSON + a concise table.

Hard guard: the standard profiles top out at 10M candidates. Anything larger
(100M / 1B) is NEVER run automatically — it requires an explicit ``allow_huge``
opt-in, and even then the harness only resolves the size, it makes no
"billion executions" claim. The infra-free stages (generator, sieve) run for
real; the infra-heavy stages (core, reader*, executor*, analyzer) are measured
when their backend is available and otherwise recorded as SKIPPED with a reason,
so the report never overstates what was actually measured.
"""
from __future__ import annotations

import dataclasses
import itertools
import math
import os
import platform
import resource
import subprocess
import sys
import time
import tracemalloc
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent.parent          # generator_trunk/
SRC = HERE.parent
sys.path.insert(0, str(HERE))
import fwgen as fg                                       # noqa: E402
sys.path.insert(0, str(HERE / "constraints"))
import sieve as sv                                       # noqa: E402

from .runs import file_sha256                            # noqa: E402
from .config import BundleConfig                         # noqa: E402
from .database import psql                               # noqa: E402
from . import stages                                     # noqa: E402

SCHEMA = "bundle.benchmark/v1"

# Standard size profiles. Anything above MAX_AUTO_CANDIDATES is opt-in only.
PROFILES = {"10K": 10_000, "1M": 1_000_000, "10M": 10_000_000}
MAX_AUTO_CANDIDATES = 10_000_000

# The infra-free stages this harness runs for real; the rest are measured only
# when their backend is supplied (else recorded SKIPPED).
INFRA_FREE_STAGES = ("generator", "sieve")
HEAVY_STAGES = ("core", "reader_loose", "reader_shard",
                "executor_local", "executor_sandbox", "executor_workers", "analyzer")


def _overhead_stage_names() -> "tuple[str, ...]":
    """One reference-overhead stage per registered coverage target.

    Derived from the architecture registry rather than hardcoded, so registering
    an application makes it measurable without touching this module.
    """
    from . import architecture as _arch
    return tuple(f"reference_overhead[{app.id}]" for app in _arch.COVERAGE_TARGETS)


OVERHEAD_STAGES = _overhead_stage_names()
ALL_STAGES = INFRA_FREE_STAGES + HEAVY_STAGES + OVERHEAD_STAGES


class BenchmarkError(Exception):
    """A benchmark misconfiguration (unknown profile/stage, or a refused huge size)."""


@dataclass
class StageResult:
    stage: str
    candidates: int
    rows: int = 0
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    peak_memory_bytes: int = 0
    disk_bytes: int = 0
    wal_bytes: int = 0
    throughput_per_s: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    notes: str = ""
    # Reference-overhead stages report a per-phase breakdown rather than one
    # fused number, so an application's wrapper cost is never mistaken for
    # engine cost (or the reverse).
    phases: dict = field(default_factory=dict)
    scenario: str = ""
    application: str = ""

    def to_dict(self) -> dict:
        out = {
            "stage": self.stage, "candidates": self.candidates, "rows": self.rows,
            "wall_seconds": round(self.wall_seconds, 6), "cpu_seconds": round(self.cpu_seconds, 6),
            "peak_memory_bytes": self.peak_memory_bytes, "disk_bytes": self.disk_bytes,
            "wal_bytes": self.wal_bytes, "throughput_per_s": round(self.throughput_per_s, 2),
            "skipped": self.skipped, "skip_reason": self.skip_reason, "notes": self.notes,
        }
        if self.phases:
            out["phases"] = {k: round(v, 6) for k, v in sorted(self.phases.items())}
        if self.scenario:
            out["scenario"] = self.scenario
        if self.application:
            out["application"] = self.application
        return out


# --------------------------------------------------------------------------- #
def resolve_profile(profile: str, *, allow_huge: bool = False) -> int:
    """Resolve a profile name (``10K``/``1M``/``10M``) or a raw integer to a
    candidate count. Sizes above :data:`MAX_AUTO_CANDIDATES` are refused unless
    ``allow_huge`` — the harness never auto-runs 100M/1B."""
    n = PROFILES.get(profile)
    if n is None:
        try:
            n = int(str(profile).replace("_", "").replace(",", ""))
        except ValueError:
            raise BenchmarkError(f"unknown profile {profile!r} (known: {', '.join(PROFILES)} or an integer)")
    if n <= 0:
        raise BenchmarkError(f"profile size must be positive, got {n}")
    if n > MAX_AUTO_CANDIDATES and not allow_huge:
        raise BenchmarkError(
            f"profile size {n:,} exceeds the {MAX_AUTO_CANDIDATES:,} auto-run ceiling — "
            f"100M/1B-class runs are never started automatically; pass allow_huge=True "
            f"(CLI --allow-huge) to explicitly opt in")
    return n


def _factor_pair(n: int) -> tuple[int, int]:
    """Factor n into two slot sizes ``(a, b)`` with ``a * b == n`` EXACTLY (a is
    the largest divisor ≤ √n), so a 2-slot fwgen spec produces exactly n Cartesian
    candidates — not ``(isqrt(n)+1)²``. The standard profiles factor cleanly
    (10K=100×100, 1M=1000×1000, 10M=3125×3200); a prime n degrades to 1×n."""
    n = max(1, int(n))
    a = math.isqrt(n)
    while a > 1 and n % a != 0:
        a -= 1
    return a, n // a


def _dir_size(p: Optional[Path]) -> int:
    if p is None or not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _measure(stage: str, candidates: int, work: Callable[[], tuple[int, str]],
             *, scratch: Optional[Path] = None, child: bool = False) -> StageResult:
    """Time ``work()`` (returns (rows, notes)) capturing wall/CPU/peak-memory/disk.

    ``child=True`` measures a SUBPROCESS stage (Core/Reader/Executor/Analyzer):
    CPU is the children's user+sys delta and peak memory is the max child RSS
    (``getrusage(RUSAGE_CHILDREN)``), since tracemalloc only sees this process'
    heap. ``child=False`` uses tracemalloc + process_time for in-process stages."""
    disk0 = _dir_size(scratch)
    if child:
        ru0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        t0 = time.perf_counter()
        rows, notes = work()
        wall = time.perf_counter() - t0
        ru1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (ru1.ru_utime + ru1.ru_stime) - (ru0.ru_utime + ru0.ru_stime)
        peak = ru1.ru_maxrss * 1024            # Linux ru_maxrss is in KiB; max child RSS so far
    else:
        tracemalloc.start()
        t0, c0 = time.perf_counter(), time.process_time()
        rows, notes = work()
        wall = time.perf_counter() - t0
        cpu = time.process_time() - c0
        _cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    disk = max(0, _dir_size(scratch) - disk0)
    # throughput is computed against the ACTUAL rows the stage processed, never the
    # requested profile size — so a stage that produced fewer/more than requested
    # reports an honest rate (the input is sized to exactly n, but this stays sound
    # even if a stage drops/dedups rows).
    return StageResult(stage=stage, candidates=candidates, rows=rows,
                       wall_seconds=wall, cpu_seconds=cpu, peak_memory_bytes=peak,
                       disk_bytes=disk, wal_bytes=0,
                       throughput_per_s=(rows / wall if (wall > 0 and rows) else 0.0), notes=notes)


def _skipped(stage: str, n: int, reason: str) -> StageResult:
    return StageResult(stage=stage, candidates=n, skipped=True, skip_reason=reason)


# ---- infra-free stage runners (run for real, in-process) ------------------- #
def bench_generator(n: int, scratch: Path, ctx: "PipelineContext") -> StageResult:
    """Materialize EXACTLY n assembled candidate rows from a real fwgen spec."""
    a, b = _factor_pair(n)                               # a×b == n exactly
    spec = fg.parse_spec({"runme": "class R{}", "slots": [
        {"sheet": "A", "values": [f"a{i}" for i in range(a)]},
        {"sheet": "B", "values": [f"b{i}" for i in range(b)]}]}, "bench")

    def work():
        rows = [fg.assemble(spec, c) for c in itertools.islice(fg.cartesian(spec), n)]
        (scratch / "generator_rows.txt").write_text("\n".join(rows), encoding="utf-8")
        return len(rows), f"materialized {len(rows)} assembled rows from a {a}×{b} fwgen spec (= exactly n)"

    return _measure("generator", n, work, scratch=scratch)


_S_MODE = {'MODE = "strict"': {"tier": 2}, 'MODE = "legacy"': {"tier": 1}}
_S_PAY = {'PAYLOAD = "ascii"': {"unicode": 0}, 'PAYLOAD = "unicode"': {"unicode": 1}}
_S_SIDECAR = {"version": 1, "params": {"MODE": _S_MODE, "PAYLOAD": _S_PAY},
              "constraints": [{"id": "strict_ascii_ingress_policy", "sheets": ["MODE", "PAYLOAD"],
                               "when": "MODE.tier == 2 and PAYLOAD.unicode == 1", "gate": {}}]}


def bench_sieve(n: int, scratch: Path, ctx: "PipelineContext") -> StageResult:
    """Run the constraint sieve over n synthetic decoded rows (in-memory)."""
    base = [[{"sheet": "MODE", "value": m, "pos": 1}, {"sheet": "PAYLOAD", "value": p, "pos": 4}]
            for m in _S_MODE for p in _S_PAY]
    rows = [base[i % len(base)] for i in range(n)]

    def work():
        rep = sv.sieve(rows, _S_SIDECAR)
        return rep["scanned"], f"sieved {rep['scanned']} rows; {rep['unique_removals']} removed"

    return _measure("sieve", n, work)


# ---- infra detection -------------------------------------------------------- #
def _java_ok(cfg: BundleConfig) -> bool:
    try:
        subprocess.run([cfg.java_cmd, "-version"], capture_output=True, timeout=15)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _pg_ok(port: int, cfg: BundleConfig, *, results: bool = False) -> bool:
    host = cfg.results_db_host if results else cfg.main_db_host
    user = cfg.results_db_user if results else cfg.main_db_user
    pw = cfg.results_db_password if results else cfg.main_db_password
    try:
        _out, rc = psql(port, "postgres", "select 1;", host=host, user=user, password=pw)
        return rc == 0
    except Exception:  # noqa: BLE001
        return False


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _create_db(port: int, name: str, cfg: BundleConfig, *, results: bool = False) -> None:
    host = cfg.results_db_host if results else cfg.main_db_host
    user = cfg.results_db_user if results else cfg.main_db_user
    pw = cfg.results_db_password if results else cfg.main_db_password
    psql(port, "postgres", f'DROP DATABASE IF EXISTS "{name}";', host=host, user=user, password=pw)
    psql(port, "postgres", f'CREATE DATABASE "{name}";', host=host, user=user, password=pw)


def _drop_db(port: int, name: str, cfg: BundleConfig, *, results: bool = False) -> None:
    host = cfg.results_db_host if results else cfg.main_db_host
    user = cfg.results_db_user if results else cfg.main_db_user
    pw = cfg.results_db_password if results else cfg.main_db_password
    psql(port, "postgres", f'DROP DATABASE IF EXISTS "{name}";', host=host, user=user, password=pw)


# ---- pipeline context: lazily prepares (untimed) the upstream artifacts ----- #
class PipelineContext:
    """Lazily prepares the (UNTIMED) inputs each pipeline stage needs — a fwgen
    workbook, a Core-filled main DB, the Reader-reassembled candidates, a results
    DB — so each stage can be measured INDEPENDENTLY while reusing one upstream
    setup. Temp DBs are dropped by :meth:`cleanup`."""

    def __init__(self, n: int, scratch: Path, cfg: BundleConfig, main_port: int, results_port: int):
        self.n = n
        self.scratch = Path(scratch)
        self.cfg = cfg
        self.main_port = main_port
        self.results_port = results_port
        self._spec = None
        self._xlsx = None
        self._core = None                       # (db_name, fw_final_count)
        self._cands: dict = {}                  # transport -> (src, hs, n_cands, manifest)
        self._results_db = None
        self._dbs: list = []                    # (port, name, results?) to drop

    def spec_and_workbook(self):
        if self._xlsx is None:
            a, b = _factor_pair(self.n)                  # a×b == n exactly → Core fills exactly n
            spec_dir = self.scratch / "spec"
            spec_dir.mkdir(parents=True, exist_ok=True)
            toml = ('title = "bench"\nrunme = "class R{}"\n\n'
                    + '[[slots]]\nsheet = "A"\nvalues = [' + ", ".join(f'"a{i}"' for i in range(a)) + ']\n\n'
                    + '[[slots]]\nsheet = "B"\nvalues = [' + ", ".join(f'"b{i}"' for i in range(b)) + ']\n')
            (spec_dir / "bench.toml").write_text(toml, encoding="utf-8")
            self._spec = fg.load_spec(spec_dir / "bench.toml")
            self._xlsx = stages.stage_gen(spec_dir, self.scratch / "gen")
        return self._spec, self._xlsx

    def core_db(self):
        if self._core is None:
            spec, xlsx = self.spec_and_workbook()
            db = f"fwbench_{uuid.uuid4().hex[:12]}"
            _create_db(self.main_port, db, self.cfg)
            self._dbs.append((self.main_port, db, False))
            prep = self.scratch / "core_prep"
            prep.mkdir(parents=True, exist_ok=True)
            cnt = stages.stage_core(spec, xlsx, prep, db, self.main_port, cfg=self.cfg)
            self._core = (db, cnt)
        return self._core

    def candidates(self, transport: str):
        if transport not in self._cands:
            db, cnt = self.core_db()
            cfg2 = dataclasses.replace(self.cfg,
                                       candidate_sink=("sharded" if transport == "shard" else "loose-files"))
            sc = self.scratch / f"reader_{transport}"
            sc.mkdir(parents=True, exist_ok=True)
            src, hs, n_cands, _empty, manifest = stages.stage_reader(
                sc, db, "py", self.main_port, self.results_port, cnt, cfg=cfg2)
            self._cands[transport] = (src, hs, n_cands, manifest)
        return self._cands[transport]

    def results_db(self):
        # Executor reads results at (results_port, SAME db name as the main DB).
        # RESET it (drop+recreate) on every call so each Executor variant does the
        # FULL work instead of hitting results_v2 idempotency from a prior variant.
        db, _ = self.core_db()
        if self._results_db is None:
            self._dbs.append((self.results_port, db, True))
            self._results_db = db
        _create_db(self.results_port, db, self.cfg, results=True)   # DROP IF EXISTS + CREATE → fresh
        return self._results_db

    def note_results_db(self, name):
        """Track a results-cluster DB of *name* for cleanup. The Reader provisions a
        results-side DB (same name as the main DB) even when no Executor stage runs, so
        a reader-only benchmark would otherwise leak it (DROP is idempotent / IF EXISTS)."""
        entry = (self.results_port, name, True)
        if entry not in self._dbs:
            self._dbs.append(entry)

    def cleanup(self):
        for port, name, results in self._dbs:
            try:
                _drop_db(port, name, self.cfg, results=results)
            except Exception:  # noqa: BLE001
                pass
        self._dbs.clear()


# ---- infra-gated REAL stage runners ---------------------------------------- #
def bench_core(n: int, scratch: Path, ctx: PipelineContext) -> StageResult:
    cfg = ctx.cfg
    core_jar = Path(cfg.core_jar) if cfg.core_jar else stages.CORE_JAR
    if not _java_ok(cfg):
        return _skipped("core", n, "java not available")
    if not core_jar.exists():
        return _skipped("core", n, f"Core jar missing ({core_jar})")
    if not _pg_ok(ctx.main_port, cfg):
        return _skipped("core", n, f"main PostgreSQL :{ctx.main_port} not reachable")
    spec, xlsx = ctx.spec_and_workbook()        # untimed setup
    db = f"fwbench_{uuid.uuid4().hex[:12]}"
    _create_db(ctx.main_port, db, cfg)
    ctx._dbs.append((ctx.main_port, db, False))
    cwd = scratch / "core_bench"
    cwd.mkdir(parents=True, exist_ok=True)

    def work():
        cnt = stages.stage_core(spec, xlsx, cwd, db, ctx.main_port, cfg=cfg)
        return cnt, f"Core JAR filled fw_final={cnt}"

    return _measure("core", n, work, scratch=cwd, child=True)


def _bench_reader(transport: str, n: int, scratch: Path, ctx: PipelineContext) -> StageResult:
    name = "reader_shard" if transport == "shard" else "reader_loose"
    cfg = ctx.cfg
    reader_jar = Path(cfg.reader_jar) if cfg.reader_jar else stages.READER_JAR
    if not _java_ok(cfg):
        return _skipped(name, n, "java not available")
    if not reader_jar.exists():
        return _skipped(name, n, f"Reader jar missing ({reader_jar})")
    if not _pg_ok(ctx.main_port, cfg):
        return _skipped(name, n, f"main PostgreSQL :{ctx.main_port} not reachable")
    db, cnt = ctx.core_db()                     # untimed setup (Core fills the main DB)
    ctx.note_results_db(db)                      # the Reader provisions a results-side DB of the same name -> track it for cleanup
    cfg2 = dataclasses.replace(cfg, candidate_sink=("sharded" if transport == "shard" else "loose-files"))
    sc = scratch / f"{name}_bench"
    sc.mkdir(parents=True, exist_ok=True)

    def work():
        src, _hs, n_cands, _empty, _m = stages.stage_reader(
            sc, db, "py", ctx.main_port, ctx.results_port, cnt, cfg=cfg2)
        return n_cands, f"Reader reassembled {n_cands} candidates ({transport})"

    return _measure(name, n, work, scratch=sc, child=True)


def _bench_executor(variant: str, n: int, scratch: Path, ctx: PipelineContext) -> StageResult:
    name = f"executor_{variant}"
    cfg = ctx.cfg
    py_exec = Path(cfg.py_executor) if cfg.py_executor else stages.PY_EXECUTOR
    if not py_exec.exists():
        return _skipped(name, n, f"py_executor missing ({py_exec})")
    if not (_java_ok(cfg) and (Path(cfg.reader_jar) if cfg.reader_jar else stages.READER_JAR).exists()):
        return _skipped(name, n, "java/Reader jar needed to prepare candidates not available")
    if not (_pg_ok(ctx.main_port, cfg) and _pg_ok(ctx.results_port, cfg, results=True)):
        return _skipped(name, n, f"main :{ctx.main_port} / results :{ctx.results_port} PostgreSQL not reachable")
    if variant == "sandbox" and not _docker_ok():
        return _skipped(name, n, "rootless Docker container backend not reachable (docker info failed)")
    src, hs, n_cands, manifest = ctx.candidates("loose")     # untimed setup
    rdb = ctx.results_db()                                    # untimed setup

    cmd = [cfg.resolved_python_cmd(), str(py_exec), "-srcDirList", str(src),
           "-dirResultsDbURL", str(hs / "resultsDbURL"), "-dirSqlTemplate", str(hs / "sqlTemplate"),
           "-dirArguments", str(hs / "arguments"), "-dirRunFirstOnce", str(hs / "runFirstOnce"),
           "--failOnly", "false", "--writeToDB", "true"]
    if variant == "workers":
        cmd += ["--workers", str(os.cpu_count() or 2)]
    if variant == "sandbox":
        # Engage STEP 28's container backend for real: drop a container execution
        # policy next to the handoff manifest (exactly where py_executor's
        # _load_execution_policy reads it) and run via --manifest. Each candidate
        # then executes inside a rootless Docker container.
        import json as _json
        from .policy import resolve_policy, effective_policy_view, policy_id
        pol = resolve_policy("generated-default")            # backend = "container"
        mpath = Path(manifest)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        (mpath.parent / "execution_policy.json").write_text(
            _json.dumps(effective_policy_view(pol)), encoding="utf-8")
        if mpath.is_file():
            raw = _json.loads(mpath.read_text(encoding="utf-8"))
            raw["execution_policy_ref"] = policy_id(pol)
            mpath.write_text(_json.dumps(raw), encoding="utf-8")
        # the manifest's own run_id is authoritative — do NOT override it with --runId
        cmd += ["--manifest", str(mpath)]

    # manifest mode (sandbox) reads the Results DB password from the environment —
    # the v2 manifest never carries a secret. Harmless for the legacy local/workers path.
    env = {**os.environ, "BUNDLE_RESULTS_DB_PASSWORD": cfg.results_db_password}

    def work():
        stages.run(cmd, env=env)
        return n_cands, f"Executor ({variant}) processed {n_cands} candidates -> results :{ctx.results_port}/{rdb}"

    return _measure(name, n, work, scratch=scratch, child=True)


def bench_analyzer(n: int, scratch: Path, ctx: PipelineContext) -> StageResult:
    cfg = ctx.cfg
    az = SRC / "Analyzer_trunk"
    # Resolve the driver exactly as the run path does. Checking only the
    # persisted build made this stage permanently unmeasurable on a normal
    # checkout, because the runtime self-builds under /tmp instead -- a skip
    # nobody reads is indistinguishable from a stage that has no cost.
    driver = stages.resolve_analyzer_driver(az)
    if not (_java_ok(cfg) and driver):
        return _skipped("analyzer", n,
                        "Analyzer driver unavailable (no compiled AnalyzeKv in "
                        "Analyzer_trunk/target/analyzekv or the /tmp self-build; "
                        "run any '--analyzer' pipeline once to produce it)")
    clsdir, cp = driver
    corpus = scratch / "analyzer_corpus.kv"
    lines = [f"candidate_id=c{i} run_id=bench app=svc mode=m{i % 5} "
             f"latency_ms={1.0 + (i % 17)} severity={i % 4} FW_VAR={i % 2}" for i in range(n)]
    corpus.write_text("\n".join(lines), encoding="utf-8")
    goals = "latency_ms:min,severity:min"

    def work():
        stages.run(f'{cfg.java_cmd} -cp "{clsdir}:{az}/target/classes:$(cat {cp})" AnalyzeKv "{corpus}" 10 "{goals}" --mode exploratory')
        return n, f"AnalyzeKv ingested {n} K=V candidate lines"

    return _measure("analyzer", n, work, scratch=scratch, child=True)


# ---- reference-application overhead around the canonical Bundle run --------- #
def _stage_durations(run_dir: Path) -> "dict[str, float]":
    """Per-stage wall seconds from a run's OWN stage records.

    Reuses the engine's existing measurement contract (`bundle.stage-result/v1`)
    instead of re-timing the pipeline from outside — the stage record is what the
    run already had to write to be considered green.
    """
    import json as _json
    out: "dict[str, float]" = {}
    stages_dir = Path(run_dir) / "stages"
    if not stages_dir.is_dir():
        return out
    for path in sorted(stages_dir.glob("*.json")):
        try:
            rec = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        duration = rec.get("duration_seconds", rec.get("duration"))
        if isinstance(duration, (int, float)):
            out[f"engine.{rec.get('stage', path.stem)}"] = float(duration)
    return out


def _run_wall(cmd: "list[str]", env: dict) -> "tuple[float, int]":
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(SRC), env=env, capture_output=True, text=True)
    return time.perf_counter() - t0, proc.returncode


def bench_reference_overhead(app_id: str, n: int, scratch: Path,
                             ctx: PipelineContext) -> StageResult:
    """Measure what a registered target's wrapper ADDS around one identical
    canonical Bundle run.

    When a single-scenario launcher leg is declared, both legs execute the
    *same* scenario, policy, candidate count and oracle; the only intended
    difference is whether the canonical `bundle_run.py` entry point is invoked
    directly or through the target's launcher. A target without such an entry
    reports the direct leg and a reason, not a fabricated comparison.

    What this does NOT claim: the wrapper's preparation and post-processing are
    reported as one aggregate, because separating them from outside requires
    instrumenting the wrapper. Reporting an invented split would be worse than
    reporting the honest aggregate.
    """
    from . import architecture as arch

    name = f"reference_overhead[{app_id}]"
    cfg = ctx.cfg
    try:
        app = arch.coverage_target(app_id)
    except KeyError as exc:
        return _skipped(name, n, str(exc))
    if not app.benchmark_spec:
        return _skipped(name, n, f"{app_id} declares no benchmark_spec")
    spec_dir = arch.REPO_ROOT / app.benchmark_spec
    if not spec_dir.is_dir():
        return _skipped(name, n, f"benchmark spec missing ({app.benchmark_spec})")
    if not _java_ok(cfg):
        return _skipped(name, n, "java not available")
    for jar, label in ((Path(cfg.core_jar) if cfg.core_jar else stages.CORE_JAR, "Core jar"),
                       (Path(cfg.reader_jar) if cfg.reader_jar else stages.READER_JAR, "Reader jar")):
        if not jar.exists():
            return _skipped(name, n, f"{label} missing ({jar})")
    if not (_pg_ok(ctx.main_port, cfg) and _pg_ok(ctx.results_port, cfg, results=True)):
        return _skipped(name, n, f"main :{ctx.main_port} / results :{ctx.results_port} "
                                 f"PostgreSQL not reachable")
    if not (cfg.main_db_password and cfg.results_db_password):
        return _skipped(name, n, "database passwords not configured")

    stamp = uuid.uuid4().hex[:10]
    runs_root = scratch / "overhead_runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "BUNDLE_MAIN_DB_PASSWORD": cfg.main_db_password,
        "BUNDLE_RESULTS_DB_PASSWORD": cfg.results_db_password,
        "BUNDLE_MAIN_DB_PORT": str(ctx.main_port),
        "BUNDLE_RESULTS_DB_PORT": str(ctx.results_port),
        "PYTHONPATH": os.pathsep.join(
            [str(SRC)] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]),
    }
    python = cfg.resolved_python_cmd()
    bundle_cli = SRC / "generator_trunk" / "bundle_run.py"
    safe_id = "".join(ch if ch.isalnum() else "_" for ch in app_id).strip("_") or "target"
    # PostgreSQL identifiers are at most 63 bytes.  Keep the random stamp in the
    # suffix so even a long future target id still receives a unique database.
    direct_db = f"refovh_direct_{safe_id[:31]}_{stamp}"[:63]
    ctx._dbs.append((ctx.main_port, direct_db, False))
    ctx._dbs.append((ctx.results_port, direct_db, True))

    phases: "dict[str, float]" = {}
    notes: "list[str]" = []

    # Leg 0 — the side-effect-free plan the launcher always performs first.
    plan_out = scratch / f"overhead_plan_{stamp}"
    plan_wall, rc = _run_wall(
        [python, str(bundle_cli), "plan", str(spec_dir), "--out", str(plan_out)], env)
    if rc != 0:
        return _skipped(name, n, f"canonical plan failed for {app.benchmark_spec} (rc={rc})")
    phases["bundle_plan"] = plan_wall

    # Leg 1 — the canonical engine path, invoked directly.
    direct_run_id = f"refovh-direct-{stamp}"
    direct_cmd = [python, str(bundle_cli), str(spec_dir),
                  "--db", direct_db, "--run-id", direct_run_id,
                  "--runs-root", str(runs_root),
                  "--main-port", str(ctx.main_port), "--results-port", str(ctx.results_port),
                  *app.benchmark_direct_args]
    direct_wall, rc = _run_wall(direct_cmd, env)
    if rc != 0:
        return _skipped(name, n, f"direct canonical run failed for {app_id} (rc={rc})")
    phases["bundle_direct_total"] = direct_wall
    # With an explicit --runs-root the launcher places the run directly under it
    # (the <db>/runs/<id> nesting is only the default scratch layout).
    direct_dir = runs_root / direct_run_id
    stage_phases = _stage_durations(direct_dir)
    phases.update(stage_phases)
    engine_sum = sum(stage_phases.values())
    if engine_sum:
        phases["bundle_cli_overhead"] = max(0.0, direct_wall - engine_sum)

    candidates = _candidate_count(direct_dir)

    # Leg 2 — the same scenario through the target's own launcher.
    if app.benchmark_launcher_args:
        launcher = arch.REPO_ROOT / app.launcher
        if not app.benchmark_launcher_database_arg:
            notes.append("application launcher leg not run: no unique temporary-database "
                         "override is declared; a benchmark must not overwrite a fixed user DB")
        elif not app.benchmark_launcher_run_id_arg:
            notes.append("application launcher leg not run: no unique run-id override is "
                         "declared; repeated benchmarks must not collide with prior run evidence")
        elif launcher.is_file():
            app_db = f"refovh_app_{safe_id[:34]}_{stamp}"[:63]
            app_run_id = f"refovh-app-{safe_id[:31]}-{stamp}"
            # Register cleanup before launch: a partial/failed application run
            # may create only one of the two databases, and DROP IF EXISTS is
            # deliberately idempotent for the other.
            ctx._dbs.append((ctx.main_port, app_db, False))
            ctx._dbs.append((ctx.results_port, app_db, True))
            app_cmd = [python, str(launcher), *app.benchmark_launcher_args,
                       app.benchmark_launcher_database_arg, app_db,
                       "--runs-root", str(runs_root),
                       "--main-port", str(ctx.main_port),
                       "--results-port", str(ctx.results_port)]
            app_cmd += [app.benchmark_launcher_run_id_arg, app_run_id]
            if app_id == "ai-combi":
                app_cmd += ["--output-dir", str(scratch / "app_reports")]
            app_wall, rc = _run_wall(app_cmd, env)
            if rc == 0:
                phases["application_total"] = app_wall
                observed_delta = app_wall - direct_wall
                if observed_delta >= 0:
                    phases["application_overhead"] = observed_delta
                    notes.append("application_overhead is the observed one-run wall delta and "
                                 "aggregates wrapper preparation/post-processing; separating "
                                 "them requires instrumentation")
                else:
                    notes.append(f"application_total was {-observed_delta:.6f}s lower than the "
                                 "direct leg; no nonnegative overhead was inferred from noise")
            else:
                notes.append(f"application launcher leg failed (rc={rc}); engine leg reported alone")
        else:
            notes.append(f"application launcher missing ({app.launcher})")
    else:
        notes.append("application declares no single-scenario launcher entry; "
                     "engine leg reported alone")

    result = StageResult(stage=name, candidates=candidates, rows=candidates,
                         wall_seconds=phases.get("application_total", direct_wall),
                         cpu_seconds=0.0, peak_memory_bytes=0,
                         notes="; ".join(notes) if notes else "")
    result.throughput_per_s = (candidates / direct_wall) if (direct_wall > 0 and candidates) else 0.0
    result.phases = phases            # carried into the report and the coverage audit
    result.scenario = app.benchmark_spec
    result.application = app_id
    return result


def _candidate_count(run_dir: Path) -> int:
    """Candidates the reader stage actually emitted for this run (0 when unknown)."""
    import json as _json
    path = Path(run_dir) / "stages" / "reader.json"
    if not path.is_file():
        return 0
    try:
        rec = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    for count in rec.get("counts", ()):
        if count.get("name") == "candidates" and isinstance(count.get("actual"), int):
            return int(count["actual"])
    return 0


def _reference_overhead_stages() -> dict:
    from . import architecture as arch
    return {f"reference_overhead[{app.id}]":
            (lambda app_id: (lambda n, s, c: bench_reference_overhead(app_id, n, s, c)))(app.id)
            for app in arch.COVERAGE_TARGETS}


_RUNNERS: dict = {
    "generator": bench_generator,
    "sieve": bench_sieve,
    "core": bench_core,
    "reader_loose": lambda n, s, c: _bench_reader("loose", n, s, c),
    "reader_shard": lambda n, s, c: _bench_reader("shard", n, s, c),
    "executor_local": lambda n, s, c: _bench_executor("local", n, s, c),
    "executor_workers": lambda n, s, c: _bench_executor("workers", n, s, c),
    "executor_sandbox": lambda n, s, c: _bench_executor("sandbox", n, s, c),
    "analyzer": bench_analyzer,
    **_reference_overhead_stages(),
}


# --------------------------------------------------------------------------- #
def capture_environment(*, main_port: Optional[int] = None) -> dict:
    """Hardware / OS / toolchain / component hashes / DB settings — everything
    needed to make a benchmark reproducible and comparable. Each probe is
    best-effort; an unavailable probe records ``"unknown"`` rather than failing."""
    env: dict = {}
    # hardware
    mem_total = "unknown"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total = line.split()[1] + " kB"
                break
    except OSError:
        pass
    import os
    env["hardware"] = {"cpu_count": os.cpu_count(), "machine": platform.machine(),
                       "processor": platform.processor() or "unknown", "mem_total": mem_total}
    # OS / kernel
    env["os_kernel"] = {"platform": platform.platform(), "system": platform.system(),
                        "release": platform.release(), "version": platform.version()}
    # toolchain
    env["toolchain"] = {
        "python": platform.python_version(),
        "java": _probe(["java", "-version"], stderr=True),
        "postgresql": _probe(["psql", "--version"]),
    }
    # component hashes (only those present)
    comps = {
        "fwgen.py": Path(fg.__file__).resolve(),
        "sieve.py": HERE / "constraints" / "sieve.py",
        "core_jar": SRC / "Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar",
        "reader_jar": SRC / "Reader_trunk/target/classes",
        "py_executor.py": SRC / "Executor_trunk/py_executor.py",
        "AnalyzeKv.java": SRC / "Analyzer_trunk/AnalyzeKv.java",
    }
    hashes = {}
    for name, p in comps.items():
        try:
            if p.is_file():
                hashes[name] = file_sha256(p)
        except OSError:
            pass
    env["component_hashes"] = hashes
    # DB settings (best-effort; only if a port is given)
    env["db_settings"] = _db_settings(main_port) if main_port else {"note": "no DB probed (no main_port)"}
    return env


def _probe(cmd, *, stderr: bool = False) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (r.stderr if stderr else r.stdout) or r.stdout or r.stderr
        return (out.strip().splitlines() or ["unknown"])[0]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _db_settings(port: int) -> dict:
    try:
        from .database import psql
        out, rc = psql(port, "postgres",
                       "show server_version; show shared_buffers; show work_mem; show max_wal_size;")
        if rc == 0:
            vals = [v.strip() for v in out.split() if v.strip()]
            return {"raw": vals[:8]}
    except Exception:  # noqa: BLE001 — best-effort probe, never fail the benchmark
        pass
    return {"note": "DB settings probe failed/unavailable"}


# --------------------------------------------------------------------------- #
def run_benchmark(profile: str, stages_requested, *, allow_huge: bool = False,
                  scratch: Optional[Path] = None, cfg: Optional[BundleConfig] = None,
                  main_port: Optional[int] = None, results_port: Optional[int] = None) -> dict:
    """Run the requested stages at ``profile`` and return the versioned report.

    Each stage runs for REAL when its backend is available; otherwise it records
    SKIPPED with a precise infra reason (never a hardcoded skip). Infra-heavy
    stages share one untimed upstream setup via :class:`PipelineContext`."""
    n = resolve_profile(profile, allow_huge=allow_huge)
    requested = list(stages_requested) if stages_requested else list(INFRA_FREE_STAGES)
    unknown = [s for s in requested if s not in ALL_STAGES]
    if unknown:
        raise BenchmarkError(f"unknown stage(s) {unknown}; known: {', '.join(ALL_STAGES)}")
    scratch = Path(scratch) if scratch else Path(".")
    scratch.mkdir(parents=True, exist_ok=True)
    cfg = cfg or BundleConfig()
    ctx = PipelineContext(n, scratch, cfg,
                          main_port=main_port or cfg.main_db_port,
                          results_port=results_port or cfg.results_db_port)

    results: list[StageResult] = []
    try:
        for s in requested:
            results.append(_RUNNERS[s](n, scratch, ctx))
    finally:
        ctx.cleanup()

    measured = [r.stage for r in results if not r.skipped]
    skipped = [{"stage": r.stage, "reason": r.skip_reason} for r in results if r.skipped]
    return {
        "schema": SCHEMA,
        "profile": profile,
        "candidates": n,
        "environment": capture_environment(main_port=ctx.main_port),
        "stages": [r.to_dict() for r in results],
        "claims": {
            "measured_stages": measured,
            "skipped_stages": skipped,
            "scope": "per-stage micro-benchmark, NOT a fused end-to-end pipeline. Size-profile "
                     "stages use the requested profile; reference_overhead stages use each "
                     "target's declared fixed bounded scenario and report their actual candidates",
            "disclaimer": "No end-to-end 'billion executions' throughput is claimed or measured. "
                          f"Sizes above {MAX_AUTO_CANDIDATES:,} (100M/1B) are never run automatically.",
        },
    }


def validate_report(report: dict) -> None:
    """Structurally validate a benchmark report; raise BenchmarkError on a defect."""
    if report.get("schema") != SCHEMA:
        raise BenchmarkError(f"bad schema {report.get('schema')!r} (want {SCHEMA!r})")
    for key in ("profile", "candidates", "environment", "stages", "claims"):
        if key not in report:
            raise BenchmarkError(f"report missing required key {key!r}")
    env = report["environment"]
    for key in ("hardware", "os_kernel", "toolchain", "component_hashes", "db_settings"):
        if key not in env:
            raise BenchmarkError(f"environment missing {key!r}")
    if not report["stages"]:
        raise BenchmarkError("report has no stages")
    for st in report["stages"]:
        for f in ("stage", "candidates", "wall_seconds", "cpu_seconds",
                  "peak_memory_bytes", "throughput_per_s", "skipped"):
            if f not in st:
                raise BenchmarkError(f"stage {st.get('stage')!r} missing field {f!r}")
    if "billion" not in report["claims"]["disclaimer"].lower():
        raise BenchmarkError("claims.disclaimer must explicitly disclaim a billion-execution claim")


def format_table(report: dict) -> str:
    """Concise human table for the report."""
    lines = [f"benchmark {report['schema']}  profile={report['profile']}  candidates={report['candidates']:,}"]
    tc = report["environment"]["toolchain"]
    hw = report["environment"]["hardware"]
    lines.append(f"  host: {hw['cpu_count']} CPU, {hw['mem_total']}, {report['environment']['os_kernel']['platform']}")
    lines.append(f"  toolchain: python {tc['python']} | {tc['java']} | {tc['postgresql']}")
    lines.append(f"  {'stage':<18}{'cand':>10}{'wall_s':>10}{'cpu_s':>9}{'peakMB':>9}{'thru/s':>12}")
    for st in report["stages"]:
        if st["skipped"]:
            lines.append(f"  {st['stage']:<18}{'(skipped: ' + st['skip_reason'][:40] + ')'}")
            continue
        lines.append(f"  {st['stage']:<18}{st['candidates']:>10,}{st['wall_seconds']:>10.3f}"
                     f"{st['cpu_seconds']:>9.3f}{st['peak_memory_bytes']/1e6:>9.1f}{st['throughput_per_s']:>12,.0f}")
    lines.append("  " + report["claims"]["disclaimer"])
    return "\n".join(lines)
