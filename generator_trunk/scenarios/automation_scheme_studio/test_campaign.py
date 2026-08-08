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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[2]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))
if not os.environ.get("BUNDLE_SUT_ROOT"):
    for sibling_name in ("SUT", "SUT-main"):
        sibling_sut_root = FRAMEWORK_ROOT.parent / sibling_name
        if (sibling_sut_root / "automation-scheme-studio" / "src").is_dir():
            os.environ["BUNDLE_SUT_ROOT"] = str(sibling_sut_root)
            break

from generator_trunk.scenarios.automation_scheme_studio.bootstrap import preflight
from generator_trunk.scenarios.automation_scheme_studio.run_campaign import SPECS
from generator_trunk.sut_paths import PROJECT_DIRS, project_path


class CampaignTests(unittest.TestCase):
    def test_sut_path_is_canonical(self) -> None:
        self.assertEqual("automation-scheme-studio", PROJECT_DIRS["automation_scheme_studio"])
        self.assertTrue((project_path("automation_scheme_studio") / "src").is_dir())

    def test_all_specs_exist_and_exercise_deep_rules(self) -> None:
        text = "\n".join((HERE / name / "scenario.toml").read_text() for name in SPECS)
        self.assertTrue(all((HERE / name / "scenario.toml").is_file() for name in SPECS))
        for verb in ("FW_PermutR(3)", "FW_Subsets_RANGE(1,2)", "FW_CombiR(3)", "FW_Cartes(PLANT_PROFILE)", "FW_(,,SUBCHAIN,,ARCH_PROFILE,,,,M:N)"):
            self.assertIn(verb, text)

    def test_preflight_reaches_real_sut(self) -> None:
        report = preflight()
        self.assertEqual(25, report["component_types"])
        self.assertEqual("OK", report["status"])


if __name__ == "__main__":
    unittest.main()
