#!/usr/bin/env python3
"""Dogfood adapter for the legacy Python Executor.

The legacy executor deliberately gives ordinary candidates 20 seconds. A real
browser journey needs longer, so Face 1 E2E lanes replace only that exact
per-candidate timeout in this adapter process. The adjacent executor source is
loaded unchanged; all handshake, DB, outcome, policy and capability behavior
remains the real Bundle implementation.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

# Direct script execution prepends this directory, whose semantic selectors.py
# would otherwise shadow the Python standard library selectors module.
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path[:] = [
    item for item in sys.path
    if not item or Path(item).resolve() != _SCRIPT_DIR
]

import subprocess


LEGACY_EXECUTOR = Path(__file__).resolve().parents[3] / "Executor_trunk" / "py_executor.py"
LEGACY_CANDIDATE_TIMEOUT = 20


def candidate_timeout() -> float:
    value = float(os.environ.get("FACE1_E2E_CANDIDATE_TIMEOUT", "360"))
    if not 30 <= value <= 1800:
        raise ValueError("FACE1_E2E_CANDIDATE_TIMEOUT must be between 30 and 1800 seconds")
    return value


def main() -> None:
    if not LEGACY_EXECUTOR.is_file():
        raise SystemExit(f"legacy Python Executor is missing: {LEGACY_EXECUTOR}")
    spec = importlib.util.spec_from_file_location("face1_legacy_py_executor", LEGACY_EXECUTOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load legacy Python Executor: {LEGACY_EXECUTOR}")
    executor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(executor)

    original_run = subprocess.run
    e2e_timeout = candidate_timeout()

    def run_with_browser_timeout(*args, **kwargs):
        if kwargs.get("timeout") == LEGACY_CANDIDATE_TIMEOUT:
            kwargs["timeout"] = e2e_timeout
        return original_run(*args, **kwargs)

    executor.subprocess.run = run_with_browser_timeout
    executor.main()


if __name__ == "__main__":
    main()
