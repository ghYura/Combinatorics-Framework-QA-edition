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

"""D4 fixture checks: legality, envelope transformation, the three policies, atom discipline,
oracle blindness, and agreement with the frozen cases and verify.py's own model on all 84 cases.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import gzip
import importlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import oracle   # noqa: E402
import runtime  # noqa: E402
import sut      # noqa: E402

GOOD = {"env": "dev", "mode": "batch", "transport": "https", "features": ["cache", "gzip"], "workers": 1, "debug": False}


def run(phase, policy, c):
    importlib.reload(runtime)
    runtime.impl(policy); runtime.env(c["env"]); runtime.mode(c["mode"]); runtime.transport(c["transport"])
    for f in c["features"]:
        runtime.feature(f)
    runtime.workers(c["workers"])
    if c["debug"]:
        runtime.debug()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        runtime.finish(phase)
    return json.loads(base64.urlsafe_b64decode(dict(t.split("=", 1) for t in out.getvalue().split())["rec"]))


class Adapter(unittest.TestCase):
    def test_correct_envelope_and_gzip_payload(self):
        r = sut.adapt(GOOD, "correct")
        env = r["envelope"]
        self.assertEqual((env["url"], env["workers"]), ("https://telemetry.invalid/batch", 1))
        self.assertEqual(env["headers"], {"Cache-Control": "max-age=60", "Content-Encoding": "gzip"})
        self.assertEqual(gzip.decompress(base64.b64decode(env["body_b64"])), sut.BODY)

    def test_drops_gzip_sends_identity_and_is_a_header_failure_only(self):
        rec = run("main", "drops_gzip", GOOD)
        self.assertEqual(rec["result"]["envelope"]["headers"]["Content-Encoding"], "identity")
        self.assertEqual((rec["failure_classes"], rec["acceptance_ok"], rec["transformation"]["payload"]), (["wrong_headers"], True, True))

    def test_rejections_carry_sorted_rule_ids(self):
        c = dict(GOOD, env="prod", transport="http", debug=True)            # R1, R4 (cache), R6
        self.assertEqual(sut.adapt(c, "correct")["violations"], ["R1", "R4", "R6"])
        self.assertEqual(sut.adapt(c, "ignores_debug_rule")["violations"], ["R1", "R4"])

    def test_ignores_debug_rule_accepts_the_r6_control(self):
        c = {"env": "prod", "mode": "batch", "transport": "https", "features": ["audit", "gzip"], "workers": 2, "debug": True}
        rec = run("controls", "ignores_debug_rule", c)
        self.assertEqual((rec["result"]["accepted"], rec["failure_classes"], rec["verdict"]), (True, ["wrong_acceptance"], "DOMAIN_FAIL"))
        self.assertEqual(run("controls", "correct", c)["verdict"], "PASS")          # a legitimate rejection passes


class Atoms(unittest.TestCase):
    def test_repeated_or_incomplete_atoms_are_setup_errors(self):
        importlib.reload(runtime)
        runtime.env("dev")
        with self.assertRaises(ValueError):
            runtime.env("prod")
        importlib.reload(runtime)
        runtime.impl("correct"); runtime.env("dev"); runtime.mode("batch"); runtime.transport("https"); runtime.workers(2)
        runtime.feature("audit")
        with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
            runtime.finish("main")                                               # one feature only

    def test_oracle_is_policy_blind(self):
        src = (HERE / "oracle.py").read_text()
        imports = {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {"sut", "runtime"})
        literals = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertFalse(literals & set(sut.POLICIES))


class Agreement(unittest.TestCase):
    def test_all_84_cases_match_frozen_predictions_and_verifier_model(self):
        import verify
        for c in json.loads((HERE / "architect-derived.json").read_text())["cases"]:
            rec = run(c["phase"], c["policy"], c["config"])
            self.assertEqual((rec["case_id"], rec["verdict"], rec["result"]["accepted"], rec["expected_violations"]),
                             (c["id"], c["predicted_outcome"], c["predicted_acceptance"], c["violations"]), c["id"])
            self.assertEqual(sorted(rec["failure_classes"]), sorted(verify.verdict(c["config"], c["policy"])), c["id"])
            self.assertEqual(rec["expected_violations"], verify.rules(c["config"]), c["id"])


if __name__ == "__main__":
    unittest.main()
