"""STEP 43 — repository hygiene WITHOUT deleting history.

Separates production sources from historical backups. This module INVENTORIES
backup/obsolete files in the production trunks (with checksums), lists each
component's production COMPILE source set, and VERIFIES the compile source set
does not capture any backup. It PROPOSES an archival move (to a dir outside the
compiler source roots) but never moves or deletes anything on its own —
`apply_archival` runs only with an explicit ``approved=True`` (an operator's
reasoned, traceable approval). Forbidden paths (anything containing 'claude')
and build output (`target/`, `.git/`, `__pycache__`) are never scanned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .runs import file_sha256

HERE = Path(__file__).resolve().parent.parent          # generator_trunk/
SRC = HERE.parent                                       # repo root

# the PRODUCTION trunks (the historical *RC* / Opus* sibling dirs are themselves
# directory-level historical copies — out of scope for the production build).
PRODUCTION_TRUNKS = ("Core_trunk", "Reader_trunk", "Executor_trunk", "Analyzer_trunk", "generator_trunk")

# backup/obsolete file markers (extension- or suffix-based; conservative).
_BACKUP_EXTS = {".bak", ".djava", ".orig", ".old", ".rej", ".save", ".swp", ".swo"}
_BACKUP_RE = re.compile(r"(~$|\.bak\b|\.may\d+\.bak$|bkup|bckup|backup)", re.IGNORECASE)

# directories never scanned
_SKIP_DIRS = ("/target/", "/.git/", "/__pycache__/", "/node_modules/", "/.m2/")


def _forbidden(path: str) -> bool:
    low = str(path).lower()
    return "claude" in low or any(s in str(path) for s in _SKIP_DIRS)


def is_backup(path: Path) -> bool:
    name = path.name
    if path.suffix.lower() in _BACKUP_EXTS:
        return True
    return bool(_BACKUP_RE.search(name)) and path.suffix.lower() not in (".py",)


@dataclass(frozen=True)
class BackupFile:
    trunk: str
    relpath: str          # relative to the repo root
    size_bytes: int
    sha256: str
    captured_by_compile: bool   # True if the production compile would pick it up


# --------------------------------------------------------------------------- #
def _compile_extension(trunk: str) -> str:
    """The extension the production compiler picks up for this trunk."""
    return ".py" if trunk == "generator_trunk" or trunk == "Executor_trunk" else ".java"


def compile_source_set(trunk: str, root: Path = SRC) -> list:
    """The production COMPILE source set for a trunk — the files the canonical
    build actually compiles. Maven: ``src/main/java/**/*.java``; Python: package
    ``*.py``. Backups (``.djava``/``.bak``/…) are NOT in it (wrong extension)."""
    base = root / trunk
    ext = _compile_extension(trunk)
    if ext == ".java":
        src = base / "src/main/java"
        if not src.is_dir():
            return []
        return sorted(str(p.relative_to(root)) for p in src.rglob("*.java") if not _forbidden(p))
    # python: top-level package sources (exclude tests/backups/pycache)
    return sorted(str(p.relative_to(root)) for p in base.rglob("*.py")
                  if not _forbidden(p) and "test" not in p.name.lower())


def scan_backups(root: Path = SRC) -> list:
    """Inventory backup/obsolete files across the production trunks, each with a
    sha256 (checksums retained) and whether the compile source set captures it."""
    out: list = []
    for trunk in PRODUCTION_TRUNKS:
        base = root / trunk
        if not base.is_dir():
            continue
        compile_set = set(compile_source_set(trunk, root))
        for p in sorted(base.rglob("*")):
            if not p.is_file() or _forbidden(p) or not is_backup(p):
                continue
            rel = str(p.relative_to(root))
            out.append(BackupFile(
                trunk=trunk, relpath=rel, size_bytes=p.stat().st_size,
                sha256=file_sha256(p), captured_by_compile=(rel in compile_set)))
    return out


def verify_clean(root: Path = SRC) -> "tuple[bool, list]":
    """Acceptance check: the production compile source set must not capture any
    backup. Returns ``(clean, captured)`` — ``captured`` lists any offending file."""
    captured = [b for b in scan_backups(root) if b.captured_by_compile]
    return (not captured, captured)


# --------------------------------------------------------------------------- #
def archival_proposal(root: Path = SRC, *, archive_dir: str = "_archive") -> dict:
    """Propose moving each inventoried backup to an archival directory OUTSIDE the
    compiler source roots, retaining its checksum. Machine-readable; NOT executed.
    `<archive_dir>/<trunk>/<path-under-trunk>` keeps provenance without touching
    the production source set."""
    backups = scan_backups(root)
    moves = []
    for b in backups:
        under_trunk = b.relpath[len(b.trunk) + 1:]      # path within the trunk
        dest = f"{archive_dir}/{b.trunk}/{under_trunk}"
        moves.append({"from": b.relpath, "to": dest, "sha256": b.sha256, "size_bytes": b.size_bytes})
    return {
        "schema": "bundle.hygiene/v1",
        "archive_dir": archive_dir,
        "backup_count": len(backups),
        "captured_by_compile": [b.relpath for b in backups if b.captured_by_compile],
        "moves": moves,
        "note": "PROPOSAL ONLY — no file is moved or deleted without explicit approval "
                "(apply_archival(approved=True)). Checksums are retained for every file.",
    }


def apply_archival(proposal: dict, *, root: Path = SRC, approved: bool = False) -> dict:
    """Execute the proposed archival moves — ONLY with explicit ``approved=True``.
    Verifies each file's checksum before moving (no silent corruption) and never
    deletes (it MOVES into the archive dir, preserving history). Returns a report."""
    if not approved:
        raise PermissionError("apply_archival refused: explicit approval required (approved=True) — "
                              "STEP 43 never moves/deletes without the operator's reasoned approval")
    import shutil
    moved, skipped = [], []
    for m in proposal.get("moves", []):
        src_p = root / m["from"]
        if not src_p.is_file():
            skipped.append({"from": m["from"], "reason": "source missing"})
            continue
        if file_sha256(src_p) != m["sha256"]:
            skipped.append({"from": m["from"], "reason": "checksum mismatch — not moved"})
            continue
        dest_p = root / m["to"]
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dest_p))            # MOVE (history preserved), never delete
        moved.append({"from": m["from"], "to": m["to"], "sha256": m["sha256"]})
    return {"moved": moved, "skipped": skipped, "approved": True}


def format_report(root: Path = SRC) -> str:
    backups = scan_backups(root)
    clean, captured = verify_clean(root)
    lines = ["repository hygiene (bundle.hygiene/v1) — production trunks"]
    for trunk in PRODUCTION_TRUNKS:
        n_src = len(compile_source_set(trunk, root))
        n_bak = sum(1 for b in backups if b.trunk == trunk)
        lines.append(f"  {trunk:<16} compile-source files: {n_src:<5} backup/obsolete files: {n_bak}")
    lines.append(f"  total backups inventoried: {len(backups)} (checksums retained)")
    lines.append("  compile source set captures a backup: "
                 + ("NO ✓ (production build is clean)" if clean else f"YES ✗ ({len(captured)} file(s)!)"))
    for b in captured:
        lines.append(f"    ✗ {b.relpath}")
    lines.append("  proposal: archive backups under _archive/<trunk>/… (move, not delete; approval required)")
    return "\n".join(lines)
