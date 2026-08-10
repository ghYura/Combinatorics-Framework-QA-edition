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

from __future__ import annotations

import calendar
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .database import psql, sql_literal
from .errors import BundleError
from .jsonio import write_json_atomic
from .models import RunManifest
from .runs import RunLayout

CLEANUP_LOG_SCHEMA = "bundle.cleanup-log/v1"

# Mirrors `jsonio._SECRET_KEY_FRAGMENTS`: a `key=value`/`key: value` line whose
# key contains one of these (case-insensitive) is "temporary credentials" --
# exactly the run-private `fw.properties`/`resultsDbURL.properties` STEP 14
# action 7 says may carry a secret and must be removable by policy after the
# run. Bounded to small text-ish files so a stray multi-GB candidate/log isn't
# read whole into memory.
_CREDENTIAL_KEY_FRAGMENTS = ("password", "secret", "token", "credential", "api_key")
_PROPERTY_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*[=:]\s*(\S.*?)\s*$")
_SCAN_MAX_BYTES = 1_000_000


class CleanupError(BundleError):
    """Cleanup cannot proceed safely: path escape, DB-name mismatch, missing run, ..."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_ts(ts: "str | None") -> "Optional[float]":
    if not ts:
        return None
    try:
        return float(calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


# ------------------------------- dry-run scan --------------------------------- #
@dataclass(frozen=True)
class CredentialHit:
    path: str
    key: str


@dataclass(frozen=True)
class CleanupReport:
    """Everything action 2 says a dry-run must show, plus the safety facts
    (`db_name_matches_manifest`) action 5/6 hinge on -- read-only, never
    mutates a byte of run state (acceptance: "Dry-run не меняет state")."""

    run_id: str
    root: str
    file_count: int
    total_bytes: int
    skipped_symlinks: tuple
    credential_files: tuple
    db_name: str
    db_name_matches_manifest: bool
    results_v2_rows: "Optional[int]"
    age_seconds: "Optional[float]"
    retention_seconds: "Optional[float]"
    retention_eligible: "Optional[bool]"


def _scan_credentials(path: Path) -> "Optional[CredentialHit]":
    try:
        if path.is_symlink() or path.stat().st_size > _SCAN_MAX_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        m = _PROPERTY_LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value and any(frag in key.lower() for frag in _CREDENTIAL_KEY_FRAGMENTS):
            return CredentialHit(path=str(path), key=key)
    return None


def _walk_files(root: Path):
    """Yield every regular file under *root*, depth-first, never following a
    symlinked directory (`followlinks=False`) -- the walk itself cannot step
    outside *root* through a symlink. Symlinks (file or dir) are reported
    separately and otherwise skipped untouched."""
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            yield Path(dirpath) / name


def scan_run(layout: RunLayout, manifest: RunManifest, cfg, *,
             db: "str | None" = None, retention_seconds: "float | None" = None) -> CleanupReport:
    """Read-only inventory of what a real cleanup would touch (action 2):
    files/bytes, DB identity + scoped row counts, credential-shaped files,
    and the run's age relative to an optional retention threshold."""
    root = Path(layout.root)
    file_count = 0
    total_bytes = 0
    skipped_symlinks = []
    credential_files = []
    for p in _walk_files(root):
        if p.is_symlink():
            skipped_symlinks.append(str(p))
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        file_count += 1
        total_bytes += size
        hit = _scan_credentials(p)
        if hit is not None:
            credential_files.append(hit)

    db_name = db or manifest.db_name
    db_matches = (db_name == manifest.db_name)
    rows = _results_v2_row_count(cfg, db_name, layout.run_id) if db_matches else None

    age = None
    started = _parse_ts(manifest.start)
    if started is not None:
        age = max(0.0, time.time() - started)
    eligible = None if (retention_seconds is None or age is None) else (age >= retention_seconds)

    return CleanupReport(
        run_id=layout.run_id, root=str(root), file_count=file_count, total_bytes=total_bytes,
        skipped_symlinks=tuple(skipped_symlinks), credential_files=tuple(credential_files),
        db_name=db_name, db_name_matches_manifest=db_matches, results_v2_rows=rows,
        age_seconds=age, retention_seconds=retention_seconds, retention_eligible=eligible)


def format_cleanup_report(report: CleanupReport) -> str:
    lines = [
        f"cleanup dry-run -- run '{report.run_id}' ({report.root})",
        f"  files: {report.file_count}  bytes: {report.total_bytes}",
    ]
    if report.skipped_symlinks:
        lines.append(f"  symlinks (left alone, not counted): {len(report.skipped_symlinks)}")
        for s in report.skipped_symlinks[:10]:
            lines.append(f"    - {s}")
        if len(report.skipped_symlinks) > 10:
            lines.append(f"    ... and {len(report.skipped_symlinks) - 10} more")
    lines.append(f"  DB: {report.db_name!r} "
                 f"({'matches' if report.db_name_matches_manifest else 'DOES NOT MATCH'} run manifest)")
    if report.results_v2_rows is not None:
        lines.append(f"    results_v2 rows for this run_id: {report.results_v2_rows}")
    elif not report.db_name_matches_manifest:
        lines.append("    results_v2 row count skipped -- DB-name mismatch (see above)")
    if report.credential_files:
        lines.append(f"  temporary credentials found in {len(report.credential_files)} file(s):")
        for hit in report.credential_files:
            lines.append(f"    - {hit.path}  (key {hit.key!r})")
    else:
        lines.append("  temporary credentials: none found")
    if report.age_seconds is not None:
        age_txt = f"  age: {report.age_seconds:.0f}s"
        if report.retention_seconds is not None:
            verdict = "eligible for cleanup" if report.retention_eligible else "younger than retention -- not yet eligible"
            age_txt += f"  (retention {report.retention_seconds:.0f}s -- {verdict})"
        lines.append(age_txt)
    return "\n".join(lines)


# ----------------------------------- DB helpers ------------------------------- #
def _results_v2_row_count(cfg, db: str, run_id: str) -> "Optional[int]":
    sql = "select count(*) from public.results_v2 where run_id=" + sql_literal(run_id) + ";"
    out, rc = psql(cfg.results_db_port, db, sql, host=cfg.results_db_host,
                   user=cfg.results_db_user, password=cfg.results_db_password)
    return int(out) if rc == 0 and out.isdigit() else None


def _delete_results_v2_rows(cfg, db: str, run_id: str) -> "Optional[int]":
    """Delete (and count, in one round trip via a CTE so nothing can race
    between "count what we'd remove" and "remove it") only the rows this run
    itself wrote -- `results_v2` is additive and keyed by run ID (STEP 22),
    so this is the one DB-side cleanup that is safely scoped to *this* run
    without risking another run's evidence (unlike the legacy results table,
    which has no run_id column and is therefore never touched here)."""
    sql = ("with doomed as (delete from public.results_v2 where run_id=" + sql_literal(run_id)
           + " returning 1) select count(*) from doomed;")
    out, rc = psql(cfg.results_db_port, db, sql, host=cfg.results_db_host,
                   user=cfg.results_db_user, password=cfg.results_db_password)
    if rc != 0:
        raise CleanupError(f"failed to delete results_v2 rows for run {run_id!r} from DB {db!r} (psql exit {rc})")
    return int(out) if out.isdigit() else None


# ----------------------------------- real cleanup ------------------------------ #
@dataclass(frozen=True)
class CleanupActionLog:
    schema: str
    run_id: str
    root: str
    db_name: str
    performed_at: str
    removed_files: int
    removed_bytes: int
    deleted_results_v2_rows: "Optional[int]"
    skipped_symlinks: tuple


def _assert_safe_run_root(layout: RunLayout) -> Path:
    """Defense in depth ahead of `shutil.rmtree` (acceptance: "Path
    traversal/symlink escape blocked", "Никогда не удалять path вне run
    root"): refuse unless *layout.root* both names this run ID and looks like
    a run directory (has `run.json`) -- a layout-construction bug must never
    be able to point this at, say, `runs_root` itself or an arbitrary path."""
    root = Path(layout.root)
    if root.is_symlink():
        raise CleanupError(f"run root {root} is a symlink -- refusing to delete")
    resolved = root.resolve()
    if root.name != layout.run_id:
        raise CleanupError(f"run root {root} does not end in run ID {layout.run_id!r} "
                           f"-- refusing to delete (safety check failed)")
    if not (root / "run.json").is_file():
        raise CleanupError(f"{root} has no run.json -- refusing to delete "
                           f"what does not look like a run directory")
    if len(resolved.parts) < 3:
        raise CleanupError(f"refusing to delete suspiciously shallow path {resolved}")
    return resolved


def _remove_tree(root: Path) -> "tuple[int, int, tuple]":
    """Count files/bytes/symlinks first (the manifest may live inside what
    we're about to remove), then remove the tree.

    `shutil.rmtree` never *recurses* through a symlinked directory -- it
    `lstat`s each entry and unlinks symlinks as themselves, so a crafted link
    inside the run root pointing at, say, `$HOME` only ever removes the link,
    never the target (the "symlink escape blocked" half of the acceptance
    criterion; `_walk_files`'s `followlinks=False` covers the counting half).
    """
    file_count = 0
    total_bytes = 0
    symlinks = []
    for p in _walk_files(root):
        if p.is_symlink():
            symlinks.append(str(p))
            continue
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass
        file_count += 1
    shutil.rmtree(root)
    return file_count, total_bytes, tuple(symlinks)


def _write_cleanup_log(layout: RunLayout, log: CleanupActionLog) -> Path:
    """Write the action log *outside* the run root -- action 6 ("Cleanup
    action log записывается") would be self-defeating if its only copy lived
    inside the directory the same operation just deleted."""
    path = Path(layout.root).parent / f"{layout.run_id}.cleanup.json"
    write_json_atomic(path, log)
    return path


def delete_run(layout: RunLayout, manifest: RunManifest, cfg, *,
               db: "str | None" = None, delete_db_rows: bool = True) -> "tuple[CleanupActionLog, Path]":
    """Real cleanup (action 3, only ever reached behind an explicit operator
    flag -- see `cli.cmd_cleanup`'s `--yes`):

    1. validate the DB name against the run manifest (action 5) *before*
       touching the database -- a stale `--db`/config override must never
       cause this to operate on the wrong database;
    2. delete this run's `results_v2` rows (scoped by run_id, see
       `_delete_results_v2_rows`) while the manifest is still readable;
    3. remove the run directory tree itself;
    4. write the action log where it survives step 3.

    DB rows are removed before files specifically so a failure partway
    through never leaves the run directory gone with no manifest left to
    re-derive `db_name` from for a retry.
    """
    root = _assert_safe_run_root(layout)
    db_name = db or manifest.db_name
    if db_name != manifest.db_name:
        raise CleanupError(f"DB name {db_name!r} does not match run manifest's db_name "
                           f"{manifest.db_name!r} -- refusing DB-side cleanup (action 5)")
    deleted_rows = _delete_results_v2_rows(cfg, db_name, layout.run_id) if delete_db_rows else None
    removed_files, removed_bytes, symlinks = _remove_tree(root)
    log = CleanupActionLog(
        schema=CLEANUP_LOG_SCHEMA, run_id=layout.run_id, root=str(root), db_name=db_name,
        performed_at=_now(), removed_files=removed_files, removed_bytes=removed_bytes,
        deleted_results_v2_rows=deleted_rows, skipped_symlinks=symlinks)
    log_path = _write_cleanup_log(layout, log)
    return log, log_path
