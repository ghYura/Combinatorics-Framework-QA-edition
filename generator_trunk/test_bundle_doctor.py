#!/usr/bin/env python3
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


def test_usable_backends_are_only_ones_the_executor_implements():
    """`unshare`/`nsjail` being installed does not make them selectable.

    Doctor used to list every isolation executable on PATH as an available
    backend, which overstated what a secure policy can actually name: the Python
    Executor implements `container` and `bubblewrap` only.
    """
    import shutil

    from bundle.doctor import IMPLEMENTED_SANDBOX_BACKENDS, usable_sandbox_backends

    usable = usable_sandbox_backends()
    assert isinstance(usable, tuple)
    assert set(usable) <= set(IMPLEMENTED_SANDBOX_BACKENDS)
    for backend in usable:
        exes = IMPLEMENTED_SANDBOX_BACKENDS[backend]
        assert any(shutil.which(e) for e in exes), f"{backend} reported usable with no host exe"


def _executor_sandbox_or_skip():
    """The Executor's sandbox module, or an EXPECTED_OPTIONAL skip."""
    import pytest

    from bundle.doctor import _executor_sandbox_module

    module = _executor_sandbox_module()
    if module is None:
        pytest.skip("EXPECTED_OPTIONAL: Executor_trunk/sandbox.py not present in this checkout")
    return module


def test_doctor_never_reports_a_backend_the_executor_would_refuse():
    """Anti-rot: doctor's answer must agree with the production selection path.

    A host executable being installed is not the same as the backend working --
    `bwrap` on PATH with user namespaces unavailable is precisely the case where
    a PATH probe says yes and the run says no. Doctor exists to predict the run,
    so it must never be the more optimistic of the two.
    """
    import sys

    from bundle.doctor import usable_sandbox_backends

    sandbox = _executor_sandbox_or_skip()
    for backend in usable_sandbox_backends():
        probe = {"profile": "doctor-probe", "backend": backend, "trusted": False}
        built = sandbox.build_sandbox(probe, runner="py", host_python=sys.executable)
        assert built is not None, (
            f"doctor reports {backend!r} usable, but build_sandbox returned no backend")


def test_every_advertised_backend_is_one_the_executor_implements():
    """Anti-rot: `IMPLEMENTED_SANDBOX_BACKENDS` must not name a backend the
    Executor does not dispatch on. This is the check that would have caught
    `unshare`/`nsjail` being advertised when no profile could ever select them."""
    import sys

    from bundle.doctor import IMPLEMENTED_SANDBOX_BACKENDS

    sandbox = _executor_sandbox_or_skip()
    for backend in IMPLEMENTED_SANDBOX_BACKENDS:
        probe = {"profile": "doctor-probe", "backend": backend, "trusted": False}
        try:
            sandbox.build_sandbox(probe, runner="py", host_python=sys.executable)
        except Exception as exc:
            # "not usable on this host" is fine; "does not implement" is the bug
            assert "does not implement" not in str(exc), (
                f"doctor advertises backend {backend!r}, which the Executor does not implement")


def test_sandbox_check_does_not_claim_backends_are_unwired(monkeypatch):
    """Regression: the check reported "none is wired up as an active backend yet"
    long after `build_sandbox` was driving container/bubblewrap for real."""
    from bundle.config import BundleConfig

    monkeypatch.setattr(doctor_module, "usable_sandbox_backends", lambda: ("container",))
    check = doctor_module._check_sandbox(BundleConfig())
    blob = " ".join((check.message,) + tuple(check.details)).lower()
    assert check.severity is Severity.OK
    assert "container" in blob
    assert "not wired" not in blob and "none is wired" not in blob
    # the fail-closed guarantee is the point of the check, so it must be stated
    assert "fails closed" in blob


def test_sandbox_check_warns_when_no_implemented_backend_is_usable(monkeypatch):
    from bundle.config import BundleConfig

    monkeypatch.setattr(doctor_module, "usable_sandbox_backends", lambda: ())
    check = doctor_module._check_sandbox(BundleConfig())
    assert check.severity is Severity.WARNING
    assert "no implemented backend is usable" in check.message


def test_sandbox_check_stays_ok_when_isolation_is_opted_out(monkeypatch):
    from bundle.config import BundleConfig

    monkeypatch.setattr(doctor_module, "usable_sandbox_backends", lambda: ())
    check = doctor_module._check_sandbox(BundleConfig(sandbox_policy="none"))
    assert check.severity is Severity.OK
    assert "explicitly disabled" in check.message


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
