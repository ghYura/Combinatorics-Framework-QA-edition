#!/usr/bin/env python3
"""Manual preflight. Python Bundle candidates import bootstrap.py themselves."""

from __future__ import annotations

import json
import sys
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from generator_trunk.scenarios.automation_scheme_studio.bootstrap import preflight


if __name__ == "__main__":
    print(json.dumps(preflight(), indent=2, sort_keys=True))
