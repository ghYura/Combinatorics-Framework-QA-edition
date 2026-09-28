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

"""D2 fixture checks: real decoder behaviour, the oracle's literal gate and blindness, emission,
and agreement of verify.py's independent checker with the fixture on all 480 cases.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import hashlib
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

EURO = bytes.fromhex("41e282ac42")          # "A€B"; a cut after byte 2 splits the euro sign


class Adapters(unittest.TestCase):
    def test_incremental_carries_a_split_multibyte_character(self):
        self.assertEqual(sut.incremental([EURO[:2], EURO[2:]], "utf-8", "strict"), "A€B")

    def test_per_chunk_breaks_a_split_character(self):
        with self.assertRaises(UnicodeDecodeError):
            sut.per_chunk([EURO[:2], EURO[2:]], "utf-8", "strict")
        self.assertIn("�", sut.per_chunk([EURO[:2], EURO[2:]], "utf-8", "replace"))

    def test_no_final_silently_drops_an_incomplete_tail(self):
        trunc = bytes.fromhex("41e282")
        self.assertEqual(sut.no_final([trunc], "utf-8", "strict"), "A")          # no error raised
        self.assertEqual(sut.no_final([trunc], "utf-8", "replace"), "A")         # no replacement char
        with self.assertRaises(UnicodeDecodeError):
            sut.incremental([trunc], "utf-8", "strict")                          # the flush reports it

    def test_unknown_adapter_is_a_setup_error(self):
        with self.assertRaises(ValueError):
            sut.decode("buffered", [EURO], "utf-8", "strict")


class Oracle(unittest.TestCase):
    def test_reference_is_gated_by_the_frozen_literal(self):
        good = dict(runtime.PAYLOADS["euro"])
        self.assertEqual(oracle.reference(good, "strict")["text"], "A€B")
        forged = dict(good, literal_text="AB")
        with self.assertRaises(RuntimeError):
            oracle.reference(forged, "strict")
        self.assertFalse(oracle.reference(runtime.PAYLOADS["truncated_utf16"], "strict")["accepted"])

    def test_classification_matrix(self):
        acc = lambda t: {"accepted": True, "text": t, "error": None}   # noqa: E731
        rej = {"accepted": False, "text": None, "error": "UnicodeDecodeError"}
        self.assertEqual(oracle.classify(acc("x"), acc("x")), "none")
        self.assertEqual(oracle.classify(acc("x"), acc("y")), "wrong_text")
        self.assertEqual(oracle.classify(acc("x"), rej), "unexpected_rejection")
        self.assertEqual(oracle.classify(rej, acc("x")), "unexpected_acceptance")
        self.assertEqual(oracle.classify(rej, rej), "none")

    def test_oracle_is_adapter_blind(self):
        src = (HERE / "oracle.py").read_text()
        imports = {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {"sut", "runtime"})
        for name in sut.ADAPTERS:
            self.assertNotIn(name, src)


class Runtime(unittest.TestCase):
    def test_payload_table_equals_the_frozen_derivation(self):
        derived = json.loads((HERE / "architect-derived.json").read_text())["payloads"]
        for pid, p in derived.items():
            mine = runtime.PAYLOADS[pid]
            self.assertEqual((mine["encoding"], mine["hex"], mine["literal_text"]), (p["encoding"], p["hex"], p["literal_text"]))
            self.assertEqual(mine["truncated"], pid.startswith("truncated"))
        self.assertEqual(set(runtime.PAYLOADS), set(derived))

    def test_segmentation_reproduces_the_payload_and_refuses_phantom_cuts(self):
        self.assertEqual(runtime.segment(EURO, [0, 1, 0, 1, 0]), [EURO[:2], EURO[2:4], EURO[4:]])
        with self.assertRaises(ValueError):
            runtime.segment(bytes.fromhex("414243"), [0, 0, 1, 0, 0])          # cut after byte 3 of 3
        with self.assertRaises(ValueError):
            runtime.run_case("incremental", "ascii", "strict", [0, 0, 0, 1, 0])

    def test_record_line_round_trips(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = runtime.emit("per_chunk", "euro", "strict", [0, 1, 0, 0, 0])
        tokens = dict(t.split("=", 1) for t in out.getvalue().split())
        raw = base64.urlsafe_b64decode(tokens["rec"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), tokens["rec_sha256"])
        rec = json.loads(raw)
        self.assertEqual((code, rec["case_id"], rec["failure_class"]), (2, "per_chunk|P=euro|E=strict|M=02", "unexpected_rejection"))
        self.assertEqual(rec["chunks_hex"], ["41e2", "82ac42"])


class VerifierAgreement(unittest.TestCase):
    """Pre-run self-check: verify.py's own decoding agrees with the fixture on all 480 cases."""

    def test_independent_checker_matches_fixture(self):
        import verify
        derived = json.loads((HERE / "architect-derived.json").read_text())["payloads"]
        ids = verify.expected_identities(derived)
        self.assertEqual(len(ids), 480)
        for case in ids:
            adapter, p, e, m = case.split("|")
            pid, errors, mask = p[2:], e[2:], int(m[2:], 16)
            rec = runtime.run_case(adapter, pid, errors, [mask >> i & 1 for i in range(5)])
            data = bytes.fromhex(derived[pid]["hex"])
            ok, val = verify.adapter_outcome(adapter, verify.split(data, mask), derived[pid]["encoding"], errors)
            self.assertEqual((rec["observed"]["accepted"], rec["observed"]["text"] if ok else rec["observed"]["error"]), (ok, val), case)
            self.assertEqual(rec["case_id"], case)


if __name__ == "__main__":
    unittest.main()
