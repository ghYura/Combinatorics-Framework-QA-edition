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

"""End-to-end test for the two combinable Java specs under java_e2e/.

Assembles every candidate of each spec exactly as the Reader concatenates the
Core-combined chunks (concatenator=''), then compiles + runs each through the REAL
Executor compiler backends (com.company.compiler.AdaptiveJavaCompiler via the
CompileProbe harness) resolving the external dependency from Executor_trunk/lib-src/target --
the same -dirJars pass-through MainWatch uses. Asserts:

  janino_max : every combo compiles+runs on JANINO (lightweight Java subset);
  ecj_modern : every combo FAILS on JANINO and compiles+runs on ECJ (modern Java),
               and ADAPTIVE routes every combo to ECJ.

This is the compiler-routing/combinability layer (no DB). The full Generator->Core->
Reader->Java-Executor->Results-DB run is documented + verified in java_e2e/README.md.

Run: `python3 -m pytest test_java_e2e_specs.py -q` (skips cleanly if the Java
Executor fat jar / dep jar / a JDK are unavailable)."""
import itertools
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
FAT_JAR = SRC / "Executor_trunk/target/Executor-1.0-jar-with-dependencies.jar"
DEP_DIR = SRC / "Executor_trunk/lib-src/target"
PROBE = HERE / "java_e2e" / "CompileProbe.java"
JANINO_SPEC = HERE / "java_e2e/janino_max/janino_max.toml"
ECJ_SPEC = HERE / "java_e2e/ecj_modern/ecj_modern.toml"

_needs = pytest.mark.skipif(
    not (FAT_JAR.is_file() and DEP_DIR.is_dir() and shutil.which("javac") and shutil.which("java")),
    reason="Java Executor fat jar / dep dir / JDK not available",
)


def _assemble(spec_path: Path, out_dir: Path) -> int:
    """Replicate the Reader's concatenation: HEAD + BASE + permuted(OPS) +
    subset(FLAGS) + TAIL for every Core combination. Returns the candidate count."""
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    s = {slot["sheet"]: slot["values"] for slot in spec["slots"]}
    head, tail = s["HEAD"][0], s["TAIL"][0]
    n = 0
    for base in s["BASE"]:
        for perm in itertools.permutations(range(len(s["OPS"]))):
            for r in range(len(s["FLAGS"]) + 1):
                for subset in itertools.combinations(range(len(s["FLAGS"])), r):
                    body = head + base + "".join(s["OPS"][i] for i in perm) \
                        + "".join(s["FLAGS"][i] for i in subset) + tail
                    (out_dir / f"{n}_0_0.java").write_text(body, encoding="utf-8")
                    n += 1
    return n


def _probe(mode: str, files):
    """Compile+run each assembled candidate through `mode`; return (rc, stdout)."""
    cp = subprocess.run(
        ["java", "-cp", f"{_PROBE_OUT}:{FAT_JAR}", "CompileProbe", mode, str(DEP_DIR), *map(str, files)],
        capture_output=True, text=True, timeout=600)
    return cp.returncode, cp.stdout + cp.stderr


_PROBE_OUT = None  # set by the fixture


@pytest.fixture(scope="module")
def _probe_built(tmp_path_factory):
    global _PROBE_OUT
    out = tmp_path_factory.mktemp("probe")
    rc = subprocess.run(["javac", "-cp", str(FAT_JAR), "-d", str(out), str(PROBE)],
                        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    _PROBE_OUT = str(out)
    return out


@_needs
def test_janino_max_every_combo_compiles_and_runs_on_janino(_probe_built, tmp_path):
    cand = tmp_path / "janino"; cand.mkdir()
    n = _assemble(JANINO_SPEC, cand)
    assert n == 48, n
    files = sorted(cand.glob("*.java"))
    rc, out = _probe("janino", files)
    assert rc == 0, out
    assert f"PROBE mode=JANINO ok={n} fail=0" in out, out
    assert out.count("backend=janino") == n, out          # every combo used Janino
    # the external -dirJars dependency (Scorer) was importable/usable under Janino
    assert "FAILED" not in out, out


@_needs
def test_ecj_modern_every_combo_needs_ecj(_probe_built, tmp_path):
    cand = tmp_path / "ecj"; cand.mkdir()
    n = _assemble(ECJ_SPEC, cand)
    assert n == 48, n
    files = sorted(cand.glob("*.java"))
    # Janino cannot compile any of them (modern Java) -> proves ECJ is REQUIRED
    rc_j, out_j = _probe("janino", files)
    assert rc_j != 0 and f"PROBE mode=JANINO ok=0 fail={n}" in out_j, out_j
    # ECJ compiles + runs every one (modern Java) using the -dirJars dependency
    rc_e, out_e = _probe("ecj", files)
    assert rc_e == 0 and f"PROBE mode=ECJ ok={n} fail=0" in out_e, out_e
    # adaptive routes every candidate to ECJ
    rc_a, out_a = _probe("adaptive", files)
    assert rc_a == 0 and out_a.count("backend=ecj") == n, out_a


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
