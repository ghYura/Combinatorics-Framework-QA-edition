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

"""`bundle inventory` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import read_json, write_json_atomic


def cmd_inventory(a) -> None:
    """STEP 42: print + (optionally) write the machine-readable component version
    matrix; optionally compare to a baseline under a warn/block policy; optionally
    emit an SBOM if the toolchain is present (never blocks on a missing tool)."""
    from .. import inventory
    try:
        inv = inventory.build_inventory()
        inventory.validate_inventory(inv)
        print(inventory.format_matrix(inv))
        if a.baseline:
            baseline = read_json(Path(a.baseline))
            diffs = inventory.compare(inv, baseline)
            for d in diffs:
                print(f"  {'=' if d['status'] == 'ok' else '≠'} {d['component']}: {d['status']} — {d['detail']}")
            inventory.enforce_policy(diffs, policy=a.policy)     # raises on block + mismatch
        if a.sbom:
            sb = inventory.generate_sbom()
            print(f"  SBOM: {'generated via ' + sb['tool'] if sb.get('available') and 'path' in sb else sb.get('reason') or sb.get('error') or 'unavailable'}")
        if a.out:
            write_json_atomic(Path(a.out), inv)
            ok(f"inventory -> {a.out}")
    except inventory.InventoryError as exc:
        raise PreflightError(str(exc))


def _main_inventory(argv):
    ap = argparse.ArgumentParser(prog="bundle_run inventory",
                                 description="STEP 42: machine-readable component version/hash matrix. "
                                             "Each component's canonical build + declared version + actual "
                                             "artifact sha256. Optional baseline compare (warn/block).")
    ap.add_argument("--out", default="", help="write the matrix JSON to PATH")
    ap.add_argument("--baseline", default="", help="compare artifact hashes against this saved inventory JSON")
    ap.add_argument("--policy", default="warn", choices=["warn", "block"],
                    help="version-mismatch policy when --baseline is given (default: warn)")
    ap.add_argument("--sbom", action="store_true", help="also emit an SBOM if a toolchain (syft/cyclonedx) is present")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_inventory(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
