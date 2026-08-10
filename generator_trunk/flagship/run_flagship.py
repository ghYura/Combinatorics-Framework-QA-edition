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

"""Launcher for the Bundle-native flagship levels.

Each level is one scenario directory; each *run* is that level executed against
one of the three SUT versions. Nothing but ``FLAGSHIP_SUT_VERSION`` differs
between the three runs of a level, which is what makes their outcomes
comparable — same spec, same budgets, same policy, same corpus, same oracle.

Like the engine-demo launcher this is deliberately thin: it invokes the canonical
``bundle_run.py`` entry point as a subprocess rather than re-implementing
lifecycle, budget, policy or evidence logic. A second orchestrator would be a
second source of truth.

Planning always precedes execution. The brace chain's cardinality is genuinely
runtime-known — five links, each joining the previous result table — so the plan
reports UNKNOWN and the run carries an explicit, recorded bounded materialization
gate instead of pretending to a count nobody can compute in advance.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parent.parent
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"

GOALS = "stages:max,retained:max,ops:min"
VERSIONS = ("correct", "single_fault", "interaction_only")


class Level:
    """One rung of the scaling ladder.

    `expected_final` is the count the engine must actually produce. It is derived
    by hand from the spec (see each level's `derivation`) and asserted against the
    run, so a structural regression that multiplies or collapses the space fails
    loudly instead of quietly producing a different experiment.
    """

    def __init__(self, name: str, spec_dir: str, expected_mandatory: int,
                 optional_multiplier: int, derivation: str, sieve: bool = False,
                 db: str = ""):
        self.name = name
        self.spec_dir = HERE / spec_dir
        self.expected_mandatory = expected_mandatory
        self.optional_multiplier = optional_multiplier
        self.derivation = derivation
        self.sieve = sieve
        self.db = db or f"flagship_{name}"

    @property
    def expected_final(self) -> int:
        return self.expected_mandatory * self.optional_multiplier

    @property
    def budget_final(self) -> int:
        # Just above the expected count: a structural regression (typically a
        # missing FW_Exclude on an intermediate brace target) multiplies the space,
        # and the gate must stop it rather than execute the surplus.
        return self.expected_final * 2

    @property
    def budget_mandatory(self) -> int:
        return self.expected_mandatory * 2


LEVELS = {
    "l2": Level(
        "l2", "bundle_native_l2", expected_mandatory=128, optional_multiplier=2,
        derivation=("SEQ=2(module)x4(FW_PermutR(2)) -> 8; BRANCH=8x2(side) -> 16; "
                    "PAR=2(reducer)x16 -> 32; NEST=2(nesting)x32 -> 64; "
                    "ROOT=64x2(finalizer) -> 128 mandatory; FW_Optional x2 -> 256 final"),
    ),
    # --- SUT 2: the transactional store ------------------------------------
    # Same chain shape and same expected count as l2, a different domain adapter
    # underneath. That equality is the experiment: the engine's half does not
    # change when the system under test does.
    "s2": Level(
        "s2", "bundle_native_s2", expected_mandatory=128, optional_multiplier=2,
        derivation=("SEQ=2(group)x4(FW_PermutR(2)) -> 8; TXN=2(outcome)x8 -> 16; "
                    "BRANCH=16x2(side) -> 32; NEST=2(nesting)x32 -> 64; "
                    "ROOT=64x2(final) -> 128 mandatory; FW_Optional x2 -> 256 final"),
    ),
    "l3": Level(
        "l3", "bundle_native_l3", expected_mandatory=648, optional_multiplier=4,
        sieve=True,
        derivation=("SEQ=3(module)x9(FW_PermutR(2) over 3) -> 27; BRANCH=27x2(side) -> 54; "
                    "PAR=2(reducer)x54 -> 108; NEST=2(nesting)x108 -> 216; ROOT=216x1 -> 216; "
                    "x2(CLIP_LOW)x2(CLIP_HIGH) -> 864 mandatory, minus 216 invalid clamp "
                    "pairs removed by the sieve -> 648; two FW_Optional slots x4 -> 2592 final"),
    ),
    "l4": Level(
        "l4", "bundle_native_l4", expected_mandatory=1944, optional_multiplier=4,
        sieve=True,
        derivation=("L3 with FW_PermutR(3) instead of FW_PermutR(2): SEQ=3x27 -> 81; "
                    "BRANCH=81x2 -> 162; PAR=2x162 -> 324; NEST=2x324 -> 648; ROOT=648x1 -> 648; "
                    "x2x2 -> 2592 mandatory, minus 648 sieved -> 1944; x4 optional -> 7776 final"),
    ),
}

#: What a release gate is willing to spend on one level, one SUT version. The
#: breakpoint is not a property of the engine — it is the point where a level
#: stops fitting inside a budget somebody declared in advance. Declaring it here,
#: before the runs, is what stops it becoming whatever the last run happened to cost.
GATE_BUDGET_SECONDS = 600


def _plan_command(level: Level, out_dir: Path) -> "list[str]":
    return [sys.executable, str(BUNDLE), "plan", str(level.spec_dir), "--out", str(out_dir)]


def _run_command(level: Level, args: argparse.Namespace, version: str) -> "list[str]":
    return ([
        sys.executable, str(BUNDLE), str(level.spec_dir),
        "--db", args.db or level.db,
        "--run-id", f"{args.run_id}-{level.name}-{version}",
        "--runs-root", str(args.runs_root.resolve()),
        "--main-port", str(args.main_port),
        "--results-port", str(args.results_port),
        "--lang", "py",
        # Checked-in, reviewed candidate source in this repository: the reviewed
        # trusted-local origin class. Generated or imported candidates must not
        # reuse this profile.
        "--execution-policy-profile", "trusted-local",
        "--candidate-origin", "reviewed-checked-in",
        "--acknowledge-trusted-local",
        "reviewed checked-in flagship scenario fragments in this repository",
        "--analyzer", GOALS,
        "--analysis-mode", "formal",
        "--allow-extreme",
        "--override-budget",
        f"bounded flagship {level.name}: brace cardinality is runtime-known and capped "
        f"by explicit budgets ({level.derivation})",
        "--budget-final-candidates", str(level.budget_final),
        "--budget-mandatory-rows", str(level.budget_mandatory),
    ] + (["--sieve"] if level.sieve else []))


def _checked(command: "list[str]", env: "dict | None" = None) -> None:
    completed = subprocess.run(command, cwd=FRAMEWORK_ROOT, check=False, env=env)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("list", "plan", "run"))
    parser.add_argument("--level", default="l2", choices=sorted(LEVELS))
    parser.add_argument("--version", default="all", choices=("all",) + VERSIONS,
                        help="SUT version(s) to execute; 'all' runs the three in order")
    parser.add_argument("--db", default="", help="override the level's own database name")
    parser.add_argument("--run-id", default="flagship")
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--plan-out", type=Path, default=Path("/tmp/flagship-plan"))
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    args = parser.parse_args(argv)

    level = LEVELS[args.level]
    if args.command == "list":
        for name, lvl in LEVELS.items():
            print(f"{name}\t{lvl.spec_dir}")
            print(f"  expected: {lvl.expected_mandatory} mandatory x{lvl.optional_multiplier} "
                  f"optional = {lvl.expected_final} final")
            print(f"  gate:     final<={lvl.budget_final}, mandatory<={lvl.budget_mandatory}")
            print(f"  derived:  {lvl.derivation}")
        return 0

    _checked(_plan_command(level, args.plan_out / level.name))
    if args.command == "plan":
        return 0

    for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD"):
        if not os.environ.get(key):
            raise SystemExit(f"{key} is not set; the run stage needs both database passwords")

    versions = VERSIONS if args.version == "all" else (args.version,)
    for version in versions:
        # The version reaches the candidate through the environment, which the
        # Executor inherits. Everything else about the three runs is identical.
        env = dict(os.environ, FLAGSHIP_SUT_VERSION=version)
        print(f"\n=== {level.name} / {version} ===", flush=True)
        started = time.monotonic()
        _checked(_run_command(level, args, version), env=env)
        elapsed = time.monotonic() - started
        verdict = "WITHIN" if elapsed <= GATE_BUDGET_SECONDS else "OVER"
        print(f"=== {level.name} / {version}: {elapsed:.1f}s wall, "
              f"{elapsed / level.expected_final * 1000:.1f} ms/candidate — "
              f"{verdict} the {GATE_BUDGET_SECONDS}s gate budget", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
