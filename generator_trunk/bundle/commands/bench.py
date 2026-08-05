"""`bundle bench` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..config import resolve_config
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_bench(a) -> None:
    """STEP 40: run the per-stage benchmark harness, validate + print the report,
    and write the versioned JSON. 100M/1B sizes are refused unless --allow-huge."""
    import tempfile
    from .. import benchmark
    stages = [s.strip() for s in a.stages.split(",") if s.strip()] if a.stages \
        else list(benchmark.INFRA_FREE_STAGES)
    scratch = Path(a.scratch) if a.scratch else Path(tempfile.mkdtemp(prefix="fwbench-"))
    # Resolve the config (CLI > env > file > dev-defaults) so the harness gets the
    # real DB credentials/ports the infra-heavy stages need to connect.
    cfg, _sources = resolve_config(cli={})
    try:
        report = benchmark.run_benchmark(a.profile, stages, allow_huge=a.allow_huge,
                                         scratch=scratch, cfg=cfg,
                                         main_port=(a.main_port if a.main_port is not None else None),
                                         results_port=(a.results_port if a.results_port is not None else None))
        benchmark.validate_report(report)
    except benchmark.BenchmarkError as exc:
        raise PreflightError(str(exc))
    print(benchmark.format_table(report))
    out = Path(a.out) if a.out else (scratch / "benchmark.json")
    write_json_atomic(out, report)
    ok(f"benchmark -> {out}")


def _main_bench(argv):
    ap = argparse.ArgumentParser(prog="bundle_run bench",
                                 description="STEP 40: per-stage benchmark harness — each stage is "
                                             "measured INDEPENDENTLY at a size profile. 100M/1B are "
                                             "never run automatically (need --allow-huge).")
    ap.add_argument("--profile", default="10K", help="10K | 1M | 10M | <int>  (default: 10K)")
    from ..benchmark import ALL_STAGES as _BENCH_STAGES
    ap.add_argument("--stages", default="",
                    help="comma list (default: generator,sieve). A reference_overhead[...] stage "
                         "measures what one registered target's wrapper adds around an "
                         "identical canonical Bundle run. known: " + ",".join(_BENCH_STAGES))
    ap.add_argument("--allow-huge", action="store_true",
                    help="explicitly permit profile sizes above 10M (100M/1B) — never the default")
    ap.add_argument("--main-port", type=int, default=None, help="main DB port for Core/Reader stages (optional)")
    ap.add_argument("--results-port", type=int, default=None, help="results DB port for the Executor stage (optional)")
    ap.add_argument("--scratch", default="", help="scratch dir for stage artifacts (default: a tempdir)")
    ap.add_argument("--out", default="", help="write the JSON report here (default: <scratch>/benchmark.json)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_bench(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
