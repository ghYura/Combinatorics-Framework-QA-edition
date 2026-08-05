"""`bundle release` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_release(a) -> None:
    """Generate the release manifest and/or SBOM. Side-effect-free apart from
    the files it is asked to write.

    Instances are release ARTIFACTS, not source: write them to /tmp or a CI
    artifact store. Only the generator, its schema and its tests are committed.
    """
    from .. import release as rel
    skips: "list[str]" = []
    test_summary: dict = {}
    if a.pytest_output:
        raw = Path(a.pytest_output).read_text(encoding="utf-8", errors="replace")
        parsed = rel.parse_pytest_skips(raw)
        skips = [entry["reason"] for entry in parsed for _ in range(entry["count"])]
        test_summary = {"source": a.pytest_output, **rel.parse_pytest_summary(raw)}
        # Cross-check pytest's aggregate with the grouped -ra evidence. A
        # mismatch means the log is incomplete or the parser no longer matches
        # pytest's format; either case is release-blocking.
        test_summary["classified_skip_count"] = sum(entry["count"] for entry in parsed)
    if a.sbom:
        sbom = rel.generate_sbom()
        write_json_atomic(Path(a.sbom), sbom)
        ok(f"SBOM ({len(sbom['components'])} components) -> {a.sbom}")
    manifest = rel.release_manifest(skips=skips, test_summary=test_summary)
    rel.validate_release_manifest(manifest)
    print(rel.format_release_report(manifest))
    if a.out:
        write_json_atomic(Path(a.out), manifest)
        ok(f"release manifest -> {a.out}")
    blocking = manifest["skips"]["release_blocking"]
    tests = manifest.get("tests") or {}
    # Review item A.3: the summary line can read green while the process still
    # exited non-zero (an internal error after the summary, a plugin failure, a
    # non-zero exit with no failed tests). When the runner recorded its real
    # exit code, that code is authoritative over the parsed text.
    recorded_exit = tests.get("exit_code")
    if a.pytest_output and recorded_exit is not None and int(recorded_exit) != 0:
        raise PreflightError(
            f"the supplied pytest run recorded BUNDLE_PYTEST_EXIT_CODE={recorded_exit}; a non-zero "
            f"exit is release-blocking regardless of what the summary line says. The manifest was "
            f"emitted as evidence, but the release gate is refused.")
    if a.pytest_output and (
            not tests.get("complete")
            or int(tests.get("failed") or 0) > 0
            or int(tests.get("errors") or 0) > 0):
        raise PreflightError(
            "the supplied pytest run is not release-green: "
            f"complete={tests.get('complete')}, failed={tests.get('failed')}, "
            f"errors={tests.get('errors')}. The manifest was emitted as evidence, but the "
            "release gate is refused.")
    if a.pytest_output and int(tests.get("skipped") or 0) != int(
            tests.get("classified_skip_count") or 0):
        raise PreflightError(
            "pytest skip evidence is incomplete: terminal summary reports "
            f"{tests.get('skipped')} skip(s), but classified -ra entries account for "
            f"{tests.get('classified_skip_count')}. Refusing a partially classified release.")
    if blocking and not a.allow_blocking_skips:
        raise PreflightError(
            f"{len(blocking)} release-blocking skip(s): "
            + "; ".join(f"{e['class']}: {e['reason']}" for e in blocking)
            + ". Unclassified skips must be classified; a MISSING_AUTHORIZED_BACKEND "
              "must be supplied because absence is not release evidence.")


def _main_release(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run release",
        description="Generate the release manifest (source revision + dirty state, toolchain, "
                    "hashed release inputs, capability matrix identity, canonical SUT inventory, "
                    "classified skips) and optionally a CycloneDX SBOM. Fails when a skip on the "
                    "release path is unclassified. Instances are artifacts, never source.")
    ap.add_argument("--out", default="", metavar="PATH", help="write the release manifest JSON")
    ap.add_argument("--sbom", default="", metavar="PATH", help="write the CycloneDX SBOM JSON")
    ap.add_argument("--pytest-output", default="", metavar="PATH",
                    help="a saved `pytest -ra` output to classify skips from")
    ap.add_argument("--allow-blocking-skips", action="store_true",
                    help="report unclassified skips without failing (never use on a release gate)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_release(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
