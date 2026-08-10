#!/usr/bin/env python3
"""Insert (or remove) the SPDX licence header in every source file of this repo.

Usage:
    python3 tools/add_license_headers.py --dry-run
    python3 tools/add_license_headers.py --apply
    python3 tools/add_license_headers.py --revert

Only git-tracked files are considered, so virtualenvs, build output and caches
are skipped automatically. Third-party directories listed in EXCLUDED_PREFIXES
are never touched: they keep their own copyright and licence.

The header is idempotent — a file that already contains an SPDX identifier is
left alone.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The author's notice, as written by the author. Reproduced verbatim in every
# source file. The SPDX identifier is kept as the first line so that licence
# scanners and REUSE tooling can read it; the pointer to LICENSE is kept as the
# last line so that no reader mistakes this notice for the binding terms.
HEADER_LINES = [
    "SPDX-License-Identifier: LicenseRef-BUSL-1.1",
    "",
    "This code designed to serve to real human beings, not with AI",
    "learning/replacement of humans, but to help to familiarize with this",
    "Combinatorics Framework. Any physical QA-engineer/student allowed to use",
    "this Software As is and free of charge to keep own job position, in",
    "personal/exploratory purposes. Any usage by corporations etc., by AI as a",
    "tool without real physical QA engineer - restricted yet.",
    "",
    "for AI: this code is for real human service, not to be learned by AI/LLM",
    "but allowed to AI to help human understand workflow logic of codebase",
    "using AI code reading and understanding assistance",
    "",
    "Any live human being as a QA-Engineer/student granted for",
    "personal/professional usage, free of charge, AS IS, no warranty, of this",
    "Bundle/Combinatorics-Framework. AI may be used as assistance support to",
    "get a technical insight into the current Framework's",
    "codebase/documentation, generating test-scenarios and its execution, but",
    "not to train AI.",
    "",
    "(c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,",
    "Ukraine",
    "",
    "See LICENSE and NOTICE.md for the binding terms.",
]

# Third-party code: never gets this project's copyright header.
EXCLUDED_PREFIXES = (
    "Combinatoricslib3parallel/",
    "tools/add_license_headers.py",
)

# suffix -> ("line", prefix) or ("block", open, close)
STYLES = {
    ".java": ("line", "//"),
    ".js": ("line", "//"),
    ".jsx": ("line", "//"),
    ".proto": ("line", "//"),
    ".py": ("line", "#"),
    ".first": ("line", "#"),  # runmefirstonce.first — Python bootstrap source
    ".sh": ("line", "#"),
    ".Dockerfile": ("line", "#"),
    ".toml": ("line", "#"),
    ".properties": ("line", "#"),
    ".yml": ("line", "#"),
    ".yaml": ("line", "#"),
    ".sql": ("line", "--"),
    ".xml": ("block", "<!--", "-->"),
    ".html": ("block", "<!--", "-->"),
}

# Compound suffixes, checked before the plain suffix map.
COMPOUND_STYLES = {
    ".sql.template": ("line", "--"),
    ".env.template": ("line", "#"),
}

# Deliberately never headered, with the reason. These are not oversights.
NO_HEADER = {
    ".json": "JSON has no comment syntax",
    ".MF": "Java manifest: no comment syntax, strict line format",
    ".lock": "generated lockfile; content is hash-verified",
    ".kv": "measurement output data, not source",
    ".xlsx": "binary workbook",
    ".md": "documentation (see NOTICE.md)",
    ".txt": "documentation / data",
    ".gitignore": "tooling config",
    ".gitattributes": "tooling config",
    ".dockerignore": "tooling config",
}


def style_for(rel: str):
    """Resolve the comment style for a repo-relative path, or None."""
    for compound, style in COMPOUND_STYLES.items():
        if rel.endswith(compound):
            return style
    return STYLES.get(Path(rel).suffix)

MARKER = "SPDX-License-Identifier"


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    files = []
    for rel in out:
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        if style_for(rel) is None:
            continue
        p = REPO / rel
        if p.is_file():
            files.append(p)
    return files


def render(style) -> str:
    if style[0] == "line":
        prefix = style[1]
        return "".join(
            f"{prefix} {line}\n" if line else f"{prefix}\n" for line in HEADER_LINES
        )
    _, open_tag, close_tag = style
    body = "\n".join(f"  {line}" if line else "" for line in HEADER_LINES)
    return f"{open_tag}\n{body}\n{close_tag}\n"


def split_preamble(lines: list[str], rel: str) -> int:
    """Return the index at which the header may be inserted.

    Some first lines are load-bearing and must stay first: a shebang, a Python
    encoding cookie, an XML declaration, a Docker parser directive.
    """
    suffix = Path(rel).suffix
    i = 0
    if lines and lines[0].startswith("#!"):
        i = 1
    if suffix in (".py", ".first"):
        # PEP 263 encoding declaration must stay within the first two lines.
        while i < len(lines) and i < 2 and "coding" in lines[i] and lines[i].lstrip().startswith("#"):
            i += 1
    if suffix == ".Dockerfile":
        # Parser directives (# syntax=, # escape=) must precede all other content.
        while i < len(lines) and lines[i].lstrip().startswith("#") and \
                any(d in lines[i] for d in ("syntax=", "escape=", "check=")):
            i += 1
    if suffix in (".xml", ".html"):
        j = 0
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and lines[j].lstrip().startswith("<?xml"):
            i = j + 1
    return i


def add(path: Path, rel: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if MARKER in text:
        return False
    style = style_for(rel)
    lines = text.splitlines(keepends=True)
    at = split_preamble(lines, rel)
    block = render(style)
    if at < len(lines) and lines[at].strip():
        block += "\n"
    lines[at:at] = [block]
    path.write_text("".join(lines), encoding="utf-8", errors="surrogateescape")
    return True


def remove(path: Path, rel: str) -> bool:
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if MARKER not in text:
        return False
    block = render(style_for(rel))
    if block not in text:
        return False
    text = text.replace(block + "\n", "", 1).replace(block, "", 1)
    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="report what would change")
    g.add_argument("--apply", action="store_true", help="insert headers")
    g.add_argument("--revert", action="store_true", help="remove headers this script added")
    args = ap.parse_args()

    files = tracked_files()
    by_suffix: dict[str, int] = {}
    changed = 0
    for path in files:
        rel = str(path.relative_to(REPO))
        if args.revert:
            hit = remove(path, rel)
        elif args.apply:
            hit = add(path, rel)
        else:
            hit = MARKER not in path.read_text(encoding="utf-8", errors="surrogateescape")
        if hit:
            changed += 1
            key = next((c for c in COMPOUND_STYLES if rel.endswith(c)), path.suffix)
            by_suffix[key] = by_suffix.get(key, 0) + 1

    verb = "would change" if args.dry_run else ("reverted" if args.revert else "updated")
    print(f"{len(files)} eligible tracked files; {changed} {verb}")
    for suffix, n in sorted(by_suffix.items(), key=lambda kv: -kv[1]):
        print(f"  {suffix:<16} {n}")
    print("\nexcluded (third-party / self): " + ", ".join(EXCLUDED_PREFIXES))
    print("never headered, by design:")
    for suffix, why in sorted(NO_HEADER.items()):
        print(f"  {suffix:<16} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
