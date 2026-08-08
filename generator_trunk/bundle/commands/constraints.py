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

"""`bundle constraints` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from ..cliutil import _UNSET, _load_one_spec, _resolve_bundle_config
from ..config import BundleConfig
from ..errors import BundleError, PreflightError, StageError, report_and_exit
from ..stages import fg


def _table_count(conn, table: str) -> int:
    cur = conn.cursor()
    cur.execute(f'SELECT count(*) FROM "{table}";')
    n = cur.fetchone()[0]
    cur.close()
    return int(n)


def cmd_constraints(a) -> None:
    """STEP 35: `bundle constraints explain|dry-run <spec-dir>` — the quantitative effect of every
    constraint BEFORE the destructive sieve. Both are NON-destructive: the dry-run scans a
    Core-filled fw_final and reports scanned / matched-per-rule / overlap / unique-removals /
    retained (action 1) and BOUNDED sample rejected+retained combinations, deleting NOTHING
    (action 3). The actual sieve stage records the SAME statistics (action 4)."""
    sys.path.insert(0, str(Path(fg.__file__).resolve().parent / "constraints"))
    import sieve as sv
    spec, toml_path = _load_one_spec(a.spec_dir)
    if not getattr(spec, "constraints", None):
        print(f"constraints: spec {toml_path.name} declares no constraints — nothing to explain.")
        return
    sidecar = {"version": 1, "params": spec.params, "constraints": spec.constraints}
    try:
        sv.validate_sidecar(sidecar, strict=getattr(a, "strict", False))
    except ValueError as exc:
        raise PreflightError(str(exc)) from exc

    report = None
    if getattr(a, "db", ""):
        cfg, _sources = _resolve_bundle_config(a)
        import pg8000.dbapi
        port = cfg.main_db_port if getattr(a, "main_port", _UNSET) is _UNSET else a.main_port
        conn = pg8000.dbapi.connect(host=cfg.main_db_host, port=port, user=cfg.main_db_user,
                                    password=cfg.main_db_password, database=a.db)
        try:
            before = _table_count(conn, "fw_final")
            code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
            optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
            report = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                                       id_col="combi_id", baseline=baseline, dry_run=True,
                                       strict=getattr(a, "strict", False),
                                       optional_sheets=optional_sheets)   # NEVER deletes
            after = _table_count(conn, "fw_final")
        finally:
            conn.close()
        if before != after:
            raise StageError(f"[STEP 35] dry-run MUST NOT delete: fw_final {before} -> {after} rows")
        print(f"dry-run: fw_final unchanged ({before} rows on disk — deletes nothing)")
    elif a.command == "dry-run":
        raise PreflightError("`bundle constraints dry-run` needs --db <name> (a Core-filled fw_final to scan)")

    print(sv.format_explain(sidecar, report))   # report None → rules only; with --db → + stats/samples


def _main_constraints(argv):
    ap = argparse.ArgumentParser(prog="bundle_run constraints",
                                 description="STEP 35: show each constraint's quantitative effect "
                                             "(non-destructive). `explain` lists the rules (+ a dry-run "
                                             "report when --db is given); `dry-run` requires --db and "
                                             "reports what the sieve WOULD remove without deleting anything.")
    ap.add_argument("command", choices=["explain", "dry-run"])
    ap.add_argument("spec_dir")
    ap.add_argument("--db", default="",
                    help="Core-filled main DB name to scan for the quantitative report "
                         "(explain works without it — rules only)")
    ap.add_argument("--main-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"main DB port (default: {BundleConfig().main_db_port})")
    ap.add_argument("--strict", action="store_true",
                    help="fail if any declared constraint is unsupported by sieve v1")
    ap.add_argument("--config-file", default="")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_constraints(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
