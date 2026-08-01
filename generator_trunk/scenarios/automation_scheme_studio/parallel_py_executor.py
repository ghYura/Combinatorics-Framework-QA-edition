#!/usr/bin/env python3
"""Forward to Python Executor's worker pool with launcher-safe aggregation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
EXECUTOR = FRAMEWORK_ROOT / "Executor_trunk" / "py_executor.py"
_COMPLETION_PREFIXES = (
    "py_executor DONE:",
    "py_executor OUTCOMES:",
    "py_executor RESULTS_V2:",
)


def filter_completion_lines(output: str) -> str:
    """Keep diagnostics, but expose only the dispatcher's last count triplet.

    Worker subprocesses print the same canonical lines as their dispatcher. The
    current Bundle launcher uses first-match parsing, so forwarding every worker
    line makes it compare one partition with the aggregate Results DB. The last
    occurrence of each prefix is the dispatcher's documented aggregate.
    """
    retained: list[str] = []
    final: dict[str, str] = {}
    for line in output.splitlines():
        prefix = next((p for p in _COMPLETION_PREFIXES if line.startswith(p)), None)
        if prefix is None:
            retained.append(line)
        else:
            final[prefix] = line
    retained.extend(final[prefix] for prefix in _COMPLETION_PREFIXES if prefix in final)
    return "\n".join(retained) + ("\n" if retained else "")


def main() -> None:
    workers = int(os.environ.get("AUTOMATION_BUNDLE_EXECUTOR_WORKERS", "8"))
    if workers < 1:
        raise SystemExit("AUTOMATION_BUNDLE_EXECUTOR_WORKERS must be at least 1")
    arguments = list(sys.argv[1:])
    if not any(arg.lstrip("-") == "workers" for arg in arguments):
        arguments.extend(("--workers", str(workers)))
    environment = os.environ.copy()
    python_paths = [
        item for item in environment.get("PYTHONPATH", "").split(os.pathsep) if item
    ]
    if str(FRAMEWORK_ROOT) not in python_paths:
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(FRAMEWORK_ROOT), *python_paths)
        )
    configured_sut = Path(environment.get("BUNDLE_SUT_ROOT", ""))
    if not (configured_sut / "automation-scheme-studio" / "src").is_dir():
        for sibling_name in ("SUT", "SUT-main"):
            sibling_sut = FRAMEWORK_ROOT.parent / sibling_name
            if (sibling_sut / "automation-scheme-studio" / "src").is_dir():
                environment["BUNDLE_SUT_ROOT"] = str(sibling_sut)
                break
    completed = subprocess.run(
        [sys.executable, str(EXECUTOR), *arguments],
        cwd=FRAMEWORK_ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sys.stdout.write(filter_completion_lines(completed.stdout or ""))
    sys.stderr.write(completed.stderr or "")
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
