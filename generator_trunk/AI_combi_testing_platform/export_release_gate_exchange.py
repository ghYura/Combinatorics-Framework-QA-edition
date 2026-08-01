#!/usr/bin/env python3
"""Compatibility launcher for the configurable release-gate sub-suite."""

from __future__ import annotations

from pathlib import Path
import sys

if __package__:
    from .sub_suites.release_gate_breakpoint.cli import main
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
