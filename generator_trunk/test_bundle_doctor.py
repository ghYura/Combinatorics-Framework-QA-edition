#!/usr/bin/env python3
"""Targeted tests for bundle.doctor: severity ranking/aggregation, jar-version
extraction (manifest + filename fallback), sandbox-backend probing, report
formatting/redaction, and the "non-zero only on BLOCKING" exit-code rule
(run: `python3 test_bundle_doctor.py`)."""
import io
import tempfile
import zipfile
from pathlib import Path

import bundle.doctor as doctor_module

from bundle.doctor import (
    available_sandbox_backends,
    DoctorCheck,
    doctor_exit_code,
    doctor_report_to_dict,
    DOCTOR_SCHEMA,
    format_doctor_report,
    jar_version,
    Severity,
)


def _jar_with_manifest(path: Path, manifest_text: "str | None"):
    with zipfile.ZipFile(path, "w") as zf:
        if manifest_text is not None:
            zf.writestr("META-INF/MANIFEST.MF", manifest_text)
        zf.writestr("dummy.txt", "x")


def test_severity_rank_orders_ok_warning_blocking():
    assert Severity.OK.rank < Severity.WARNING.rank < Severity.BLOCKING.rank
    assert max(Severity.OK, Severity.BLOCKING, Severity.WARNING, key=lambda s: s.rank) is Severity.BLOCKING


def test_jar_version_prefers_manifest_implementation_version():
    with tempfile.TemporaryDirectory() as d:
        jar = Path(d) / "thing-1.0-SNAPSHOT-shaded.jar"
        _jar_with_manifest(jar, "Manifest-Version: 1.0\nImplementation-Version: 7.3.1\n")
        assert jar_version(jar) == "7.3.1"


def test_jar_version_falls_back_to_filename_when_manifest_lacks_version():
    with tempfile.TemporaryDirectory() as d:
        jar = Path(d) / "migrated-project-1.0-SNAPSHOT.jar"
        _jar_with_manifest(jar, "Manifest-Version: 1.0\n")          # no *-Version key
        assert jar_version(jar) == "1.0-SNAPSHOT"


def test_jar_version_falls_back_to_filename_when_manifest_absent():
    with tempfile.TemporaryDirectory() as d:
        jar = Path(d) / "CombinatoricsReader-1.0-SNAPSHOT-shaded.jar"
        _jar_with_manifest(jar, None)
        assert jar_version(jar) == "1.0-SNAPSHOT"


def test_jar_version_returns_none_for_unversioned_name_and_bad_zip():
    with tempfile.TemporaryDirectory() as d:
        not_a_jar = Path(d) / "plainname.jar"
        not_a_jar.write_bytes(b"not a zip at all")
        assert jar_version(not_a_jar) is None

        no_version_name = Path(d) / "thing.jar"
        _jar_with_manifest(no_version_name, "Manifest-Version: 1.0\n")
        assert jar_version(no_version_name) is None


def test_available_sandbox_backends_only_returns_present_executables():
    backends = available_sandbox_backends()
    assert isinstance(backends, tuple)
    # whatever is actually on this machine's PATH must round-trip through `which`
    import shutil
    for exe in backends:
        assert shutil.which(exe), f"{exe} reported available but not on PATH"


def test_analyzer_canonical_jar_is_ready_without_legacy_persisted_files():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        analyzer = root / "Analyzer_trunk"
        (analyzer / "target").mkdir(parents=True)
        (analyzer / "target/heuristic-analyzer-flatlaf-1.0.0.jar").touch()
        (analyzer / "AnalyzeKv.java").touch()
        previous_src = doctor_module.SRC
        doctor_module.SRC = root
        try:
            check = doctor_module._check_analyzer(None)
        finally:
            doctor_module.SRC = previous_src
        assert check.severity is Severity.OK
        assert "lazy driver build" in check.message


def test_doctor_exit_code_nonzero_only_on_blocking():
    ok_and_warn = (
        DoctorCheck("a", Severity.OK, "fine"),
        DoctorCheck("b", Severity.WARNING, "meh"),
    )
    assert doctor_exit_code(ok_and_warn) == 0

    with_blocking = ok_and_warn + (DoctorCheck("c", Severity.BLOCKING, "nope"),)
    assert doctor_exit_code(with_blocking) == 1

    assert doctor_exit_code(()) == 0


def test_doctor_report_to_dict_overall_is_worst_severity_and_schema_versioned():
    checks = (
        DoctorCheck("a", Severity.OK, "fine"),
        DoctorCheck("b", Severity.WARNING, "meh", details=("note",)),
    )
    report = doctor_report_to_dict(checks)
    assert report["schema"] == DOCTOR_SCHEMA
    assert report["overall"] == Severity.WARNING.value
    assert [c["name"] for c in report["checks"]] == ["a", "b"]
    assert report["checks"][1]["details"] == ["note"]

    assert doctor_report_to_dict(())["overall"] == Severity.OK.value
    assert doctor_report_to_dict(checks + (DoctorCheck("c", Severity.BLOCKING, "x"),))["overall"] == Severity.BLOCKING.value


def test_format_doctor_report_never_prints_secret_looking_values():
    checks = (
        DoctorCheck("main_db", Severity.OK, "main DB 127.0.0.1:5433 reachable as 'postgres'",
                    details=("PostgreSQL 18.4",)),
        DoctorCheck("scratch", Severity.WARNING, "scratch root low on space", details=("free=2.0 GiB",)),
    )
    text = format_doctor_report(checks)
    assert "main_db" in text and "scratch" in text
    assert "✓" in text and "!" in text
    for leaked in ("password", "PGPASSWORD", "hunter2"):
        assert leaked not in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
