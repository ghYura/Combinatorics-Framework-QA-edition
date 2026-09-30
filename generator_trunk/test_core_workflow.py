# SPDX-License-Identifier: LicenseRef-BUSL-1.1
# (c) Yurii Baranov, Kyiv, Ukraine. See LICENSE and NOTICE.md for binding terms.
# AI assistance supports a real human QA engineer; no AI training is authorized.

"""Executable Core regressions: worker failures, grouped rendering, and process exit status."""
from pathlib import Path
import shutil
import subprocess

import pytest

CORE_JAR = Path(__file__).resolve().parents[1] / "Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar"
pytestmark = pytest.mark.skipif(
    not CORE_JAR.is_file() or not shutil.which("java"),
    reason="MISSING_AUTHORIZED_BACKEND: build the Core jar with JDK 25 and install java first")


def test_worker_failure_propagation_and_grouped_rendering():
    result = subprocess.run(
        ["java", "-cp", str(CORE_JAR), "com.company.excel.SheetWorkerWorkflowVerify"],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL SHEET-WORKER WORKFLOW CHECKS PASSED" in result.stdout


def test_core_main_configuration_failure_exits_nonzero(tmp_path):
    result = subprocess.run(
        ["java", "-cp", str(CORE_JAR), "com.company.MainRefactored"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, "Core must expose a fatal failure to its caller"
    assert "Cannot load fw.properties" in result.stdout + result.stderr
