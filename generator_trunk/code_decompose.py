#!/usr/bin/env python3
r"""code_decompose — split source code into logically-whole PIECES and emit a
code-friendly fwgen TOML spec, ready to run through the Bundle.

THE WORKFLOW THIS SERVES (a future cold-start "quick start"):
  "Split your own generated code into separate logically-whole pieces and rewrite
   each piece several times. Account for how some pieces would interact with others,
   even indirectly."

How it maps onto the Bundle (Core → Reader → Executor):
  • each PIECE  → one `[[slots]]` (a data sheet), `raw=true`, values[0] = the ORIGINAL piece.
  • REWRITES    → you (the LLM) add more `'''...'''` entries to that slot's `values`.
  • COMBINING   → default verb FW_Combi(1): the Core takes the CARTESIAN of every
                  piece's chosen rewrite ⇒ every combination of rewrites. THIS is what
                  surfaces indirect interactions (rewrite-of-A meets rewrite-of-B).
  • INTERACTIONS are also detected statically (shared identifiers) and written as
                  comments, so a piece that *uses* a name another piece *defines* is flagged.
  • REASSEMBLY  : pieces are byte-preserving contiguous spans (concat == original), so
                  the Reader concatenates them back into a runnable program. Run the
                  Reader with `reader.core.concatenator=''` (pieces keep their own newlines).

Verb choice (the rule each piece gets — deliberately conservative):
  default = FW_Combi(1) for every piece (cartesian leaf). Order-sensitivity and
  optionality are SEMANTIC judgments, so they are SUGGESTED in comments (FW_Permut for
  an order-sensitive step sequence; FW_Subsets for an optional piece) rather than guessed.

CLI:  python3 code_decompose.py <src> [--lang auto|py|generic] [--name N] [--out spec.toml]
      python3 code_decompose.py fwgen.py --name fwgen --out landing/fwgen_decomposed.toml
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Piece:
    kind: str                       # "imports" | "function" | "class" | "block"
    name: str                       # logical name (for the sheet); may be ""
    code: str                       # the VERBATIM source span (byte-preserving)
    defines: set = field(default_factory=set)
    uses: set = field(default_factory=set)
    verb: str = "FW_Combi(1)"       # cartesian leaf — pick one rewrite per piece
    note: str = ""                  # role + interaction commentary (→ TOML comments)


# --------------------------------------------------------------------------- #
# 1. Splitters — both BYTE-PRESERVING (concatenating the pieces == the source) #
# --------------------------------------------------------------------------- #

def _py_names(code: str) -> tuple[set, set]:
    """(defined, used) top-level identifiers of a parseable Python piece."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set(), set()
    defined, used = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Assign):
            for tgt in n.targets:
                defined.update(m.id for m in ast.walk(tgt) if isinstance(m, ast.Name))
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            used.add(n.id)
    return defined, used


def decompose_python(src: str) -> list[Piece]:
    """ast-based: one piece per top-level def/class; consecutive simple statements
    (imports, constants) merge into one piece. Leading blanks/comments/decorators
    attach to the following piece; trailing lines attach to the last."""
    lines = src.splitlines(keepends=True)
    body = ast.parse(src).body
    raw: list[list] = []                     # [kind, name, code]
    prev = 0                                 # 0-based: lines consumed
    for node in body:
        end = node.end_lineno                # 1-based inclusive == 0-based exclusive slice end
        code = "".join(lines[prev:end])
        prev = end
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raw.append(["function", node.name, code])
        elif isinstance(node, ast.ClassDef):
            raw.append(["class", node.name, code])
        else:
            raw.append(["stmt", "", code])
    if prev < len(lines):                    # trailing bytes → last piece (preserve all)
        tail = "".join(lines[prev:])
        if raw:
            raw[-1][2] += tail
        else:
            raw.append(["stmt", "", tail])
    merged: list[list] = []                  # fuse consecutive simple-statement runs
    for kind, name, code in raw:
        if kind == "stmt" and merged and merged[-1][0] == "stmt":
            merged[-1][2] += code
        else:
            merged.append([kind, name, code])
    pieces = []
    for kind, name, code in merged:
        d, u = _py_names(code)
        pieces.append(Piece(kind=("statements" if kind == "stmt" else kind),
                            name=name, code=code, defines=d, uses=u))
    return pieces


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def decompose_generic(src: str) -> list[Piece]:
    """Language-agnostic fallback: split on blank-line gaps (byte-preserving).
    Identifiers are harvested by regex for best-effort interaction detection."""
    chunks = re.split(r"(\n[ \t]*\n)", src)          # keep the blank-line separators
    pieces: list[Piece] = []
    i = 0
    while i < len(chunks):
        code = chunks[i] + (chunks[i + 1] if i + 1 < len(chunks) else "")
        if code.strip():
            pieces.append(Piece(kind="block", name="", code=code,
                                uses=set(_IDENT.findall(code))))
        elif pieces:                                  # whitespace-only → keep with previous
            pieces[-1].code += code
        elif code:
            pieces.append(Piece(kind="block", name="", code=code))
        i += 2
    return pieces


_JAVA_KW = {"if", "else", "for", "while", "do", "switch", "case", "return", "new", "try",
            "catch", "finally", "throw", "throws", "public", "private", "protected", "static",
            "final", "void", "int", "long", "double", "float", "boolean", "char", "byte",
            "short", "class", "interface", "enum", "record", "extends", "implements", "import",
            "package", "this", "super", "true", "false", "null", "instanceof", "synchronized",
            "volatile", "transient", "abstract", "native", "default", "break", "continue"}


def _eol(src: str, idx: int) -> int:
    j = src.find("\n", idx)
    return (j + 1) if j != -1 else len(src)


def _java_member_name(code: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", re.sub(r"//[^\n]*", "", code), flags=re.S)
    # method: name before '(', but NOT a call like `System.getenv(` (preceded by '.')
    m = re.search(r"(?<![.\w])([A-Za-z_]\w*)\s*\(", s)
    if m and m.group(1) not in ("if", "for", "while", "switch", "catch", "return", "new"):
        return m.group(1)
    m = re.search(r"\b([A-Za-z_]\w*)\s*[=;]", s)                # field: name before '='/';'
    return m.group(1) if m else ""


def decompose_java(src: str) -> list[Piece] | None:
    """Method-level, BYTE-PRESERVING split of the first top-level type: HEAD (package /
    imports / type decl + '{'), each field/method member, TAIL (closing '}'). Comment /
    string / char-aware; distinguishes a method body from an array initializer / annotation
    so fields like `int[] x = {1,2};` are not mis-split. Spans are contiguous, so byte-
    preservation holds even if a member boundary heuristic is imperfect."""
    n, i, depth = len(src), 0, 0
    lc = bc = dq = sq = False
    body_open = head_end = member_start = -1
    depth1_is_member = False
    spans: list[tuple[int, int]] = []
    tail_start = n
    while i < n:
        c = src[i]
        d = src[i + 1] if i + 1 < n else ""
        if lc:
            if c == "\n":
                lc = False
        elif bc:
            if c == "*" and d == "/":
                bc = False; i += 2; continue
        elif dq:
            if c == "\\":
                i += 2; continue
            if c == '"':
                dq = False
        elif sq:
            if c == "\\":
                i += 2; continue
            if c == "'":
                sq = False
        else:
            if c == "/" and d == "/":
                lc = True; i += 2; continue
            if c == "/" and d == "*":
                bc = True; i += 2; continue
            if c == '"':
                dq = True
            elif c == "'":
                sq = True
            elif c == "{":
                depth += 1
                if depth == 1 and body_open < 0:
                    body_open = i; head_end = _eol(src, i); member_start = head_end
                elif depth == 2 and body_open >= 0:        # member body vs array-init/annotation?
                    pre = src[member_start:i]
                    depth1_is_member = (")" in pre
                                        or bool(re.search(r"\b(class|interface|enum|record)\b", pre))
                                        or pre.rstrip().endswith("static"))
            elif c == "}":
                depth -= 1
                if body_open >= 0 and depth == 0:
                    tail_start = member_start; break       # type closed → remainder is TAIL
                if body_open >= 0 and depth == 1 and depth1_is_member:
                    end = _eol(src, i); spans.append((member_start, end)); member_start = end
            elif c == ";" and depth == 1 and body_open >= 0:
                end = _eol(src, i); spans.append((member_start, end)); member_start = end
        i += 1
    if body_open < 0:
        return None
    pieces = [Piece(kind="header", name="", code=src[:head_end])]
    for s, e in spans:
        code = src[s:e]
        nm = _java_member_name(code)
        is_method = bool(nm and re.search(r"\b" + re.escape(nm) + r"\s*\(", code))
        uses = set(_IDENT.findall(re.sub(r"/\*.*?\*/", "", re.sub(r"//[^\n]*", "", code), flags=re.S))) - _JAVA_KW
        pieces.append(Piece(kind=("method" if is_method else "field" if nm else "member"),
                            name=nm, code=code, defines=({nm} if nm else set()), uses=uses))
    pieces.append(Piece(kind="footer", name="", code=src[tail_start:]))
    return pieces


def decompose(src: str, lang: str = "auto") -> list[Piece]:
    if lang == "auto":
        lang = "py" if _looks_python(src) else "java" if _looks_java(src) else "generic"
    if lang == "py":
        pieces = decompose_python(src)
    elif lang == "java":
        pieces = decompose_java(src) or decompose_generic(src)
    else:
        pieces = decompose_generic(src)
    _annotate(pieces)
    assert "".join(p.code for p in pieces) == src, "decomposition is not byte-preserving"
    return pieces


# --------------------------------------------------------------------------- #
# 1b. Sub-split over-limit pieces — the XLSX/POI 32,767-char-per-cell ceiling. #
# --------------------------------------------------------------------------- #
# A single decomposed piece (notably a giant `main()`) can exceed the spreadsheet
# CELL limit (32,767 chars; enforced by Apache POI's XSSFWorkbook at setCellValue,
# which the Core's XLSX **and** JSON/TOML parsers both funnel through). A cell value
# of any size is fine in the TOML/JSON spec FILE, and fine in Postgres downstream —
# the bottleneck is purely the POI cell. So split an over-limit piece into ≤limit
# SUB-PIECES; each becomes its own single-value data sheet (slot), and the Reader
# concatenates the sheets back in order (run it with reader.core.concatenator=''),
# exactly the proven multi-piece reassembly path. The split is BYTE-PRESERVING and
# does NOT change the Core combo count (each single-value FW_Combi(1) slot is ×1).

XLSX_CELL_LIMIT = 32767


def _split_text_on_newlines(code: str, limit: int) -> list[str]:
    """Byte-preserving chunking: each chunk ≤ limit, cut at the last newline that
    fits (so chunks stay whole-line); fall back to a hard cut for a single line
    longer than the limit. ''.join(result) == code."""
    chunks: list[str] = []
    i, n = 0, len(code)
    while n - i > limit:
        window_end = i + limit
        nl = code.rfind("\n", i, window_end)
        cut = (nl + 1) if nl > i else window_end       # include the newline; else hard-cut
        chunks.append(code[i:cut])
        i = cut
    chunks.append(code[i:])
    return chunks


def subsplit_oversize(pieces: list[Piece], limit: int = XLSX_CELL_LIMIT) -> list[Piece]:
    """Return a new piece list in which any piece longer than `limit` is replaced by
    consecutive byte-preserving sub-pieces (`<name>__partK`), each ≤ limit. Identifier
    coupling is kept on part 1 only (parts are not independent code). Concatenation of
    all pieces still equals the original source."""
    out: list[Piece] = []
    for p in pieces:
        if len(p.code) <= limit:
            out.append(p)
            continue
        parts = _split_text_on_newlines(p.code, limit)
        base = p.name or p.kind
        for j, part in enumerate(parts, start=1):
            note = (f"role: sub-piece {j}/{len(parts)} of OVERSIZE {p.kind} `{p.name}` "
                    f"({len(p.code)} chars > {limit} cell limit).\n"
                    f"# byte-preserving split; reassembles via the Reader's concatenator='' "
                    f"in sheet order — keep these consecutive and single-valued.")
            out.append(Piece(kind=p.kind, name=f"{base}__part{j}", code=part,
                             defines=(set(p.defines) if j == 1 else set()),
                             uses=(set(p.uses) if j == 1 else set()),
                             verb=p.verb, note=note))
    assert "".join(q.code for q in out) == "".join(p.code for p in pieces), \
        "sub-split is not byte-preserving"
    return out


def _looks_python(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _looks_java(src: str) -> bool:
    return bool(re.search(r"\b(class|interface|enum|record)\s+\w+", src)) and "{" in src


# --------------------------------------------------------------------------- #
# 2. Annotate: role + indirect-interaction notes (the "account for it" part)   #
# --------------------------------------------------------------------------- #

def _annotate(pieces: list[Piece]) -> None:
    for i, p in enumerate(pieces):
        # which EARLIER pieces define names this piece uses → indirect coupling
        links = []
        for j, q in enumerate(pieces):
            if j == i or not q.defines:
                continue
            shared = sorted(p.uses & q.defines)
            if shared:
                links.append(f"P{j + 1:02d}({', '.join(shared[:4])})")
        role = {"statements": "module-level statements (imports / constants / __main__ block)",
                "function": f"function `{p.name}`",
                "class": f"class `{p.name}`",
                "block": "code block",
                "header": "type header (package / imports / class decl + open brace)",
                "method": f"method `{p.name}`",
                "field": f"field `{p.name}`",
                "footer": "type footer (closing brace(s) / trailing)",
                "member": "type member"}.get(p.kind, p.kind)
        hint = ""
        if p.kind in ("header", "footer") or (i == 0 and p.kind == "statements"):
            hint = "  · structural frame — usually kept as a single CONSTANT value (FW_Combi(1))."
        note = f"role: {role}.{hint}"
        if links:
            note += (f"\n# interacts (uses names defined in): {', '.join(links)} "
                     f"→ indirect coupling; the FW_Combi(1) cartesian covers every "
                     f"rewrite-pair, so a rewrite here is tried against each rewrite there.")
        else:
            note += "\n# no static identifier coupling detected (still combined via the cartesian)."
        p.note = note


# --------------------------------------------------------------------------- #
# 3. Emit a code-friendly TOML spec (triple-quoted literals + comments)        #
# --------------------------------------------------------------------------- #

def _slug(s: str, idx: int) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_") or "piece"
    return f"P{idx:02d}_{base}"[:40]


def _toml_value(code: str) -> str:
    """Render code as a TOML multi-line string. Prefer a literal '''…''' (verbatim,
    zero escaping); fall back to a basic \"\"\"…\"\"\" with escaping if the code itself
    contains '''."""
    if "'''" not in code:
        body = code if code.startswith("\n") else "\n" + code
        if not body.endswith("\n"):
            body += "\n"
        return "'''" + body + "'''"
    esc = code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    body = esc if esc.startswith("\n") else "\n" + esc
    if not body.endswith("\n"):
        body += "\n"
    return '"""' + body + '"""'


_HEADER = """\
# ============================================================================
# fwgen DECOMPOSITION spec  —  QUICK START (auto-generated by code_decompose.py)
# ----------------------------------------------------------------------------
# Each [[slots]] below is ONE logical PIECE of the source. values[0] is the
# ORIGINAL piece. To explore the space, ADD REWRITES as more '''...''' entries
# to a piece's `values`. The Core then takes the CARTESIAN of every piece's
# chosen rewrite (verb FW_Combi(1)) — i.e. every combination of rewrites — which
# is what surfaces INDIRECT cross-piece interactions (see the per-piece notes).
#
# Run it through the Bundle:
#   python3 fwgen_cli.py list --specs <this-dir>      # predicts the Core row count
#   python3 fwgen_cli.py gen  --specs <this-dir> --out out
#   # → Core fills the DB, Reader reassembles each combination into a program.
#   # raw=true ⇒ pieces emitted VERBATIM; run the Reader with
#   #   reader.core.concatenator=''  so the pieces concatenate back cleanly.
#
# Tuning the rule per piece (the verb): FW_Combi(1)=cartesian leaf (default);
#   FW_Permut if a piece is an ORDER-sensitive step sequence; FW_Subsets if a
#   piece is OPTIONAL (present/absent). Keep value sets small to avoid explosion.
# ============================================================================
"""


def dump_toml(pieces: list[Piece], name: str, *,
              goals=("correctness", "latency_ms"),
              args=("mode=decompose_rewrite",)) -> str:
    out = [_HEADER,
           f'title = "decomposition of {name} — {len(pieces)} pieces, rewrite & combine"',
           'note  = "Each slot = one code piece; add rewrites to values; the cartesian of '
           'rewrites surfaces indirect interactions. raw=true → verbatim; Reader concatenator='
           "''" + '."',
           "goals = [" + ", ".join(f'"{g}"' for g in goals) + "]",
           "args  = [" + ", ".join(f'"{a}"' for a in args) + "]",
           ""]
    for i, p in enumerate(pieces, start=1):
        sheet = _slug(p.name or p.kind, i)
        out.append(f"# --- PIECE {i}/{len(pieces)}: {p.kind} {p.name} ".rstrip() + " ---")
        for line in p.note.splitlines():
            out.append(line if line.startswith("#") else f"# {line}")
        out.append("[[slots]]")
        out.append(f'sheet  = "{sheet}"')
        out.append(f'key    = "p{i:02d}"')
        out.append(f'verb   = "{p.verb}"   # cartesian leaf; alt: FW_Permut (order) / FW_Subsets (optional)')
        out.append("raw    = true")
        out.append("values = [")
        out.append(_toml_value(p.code) + ",")
        out.append("  # ↑ baseline (original). Add rewrites of THIS piece as more '''...''' entries.")
        out.append("]")
        out.append("")
    return "\n".join(out) + "\n"


def to_spec_dict(pieces: list[Piece], name: str, *,
                 goals=("correctness", "latency_ms"),
                 args=("mode=decompose_rewrite",)) -> dict:
    """Raw spec dict (same shape as the TOML) — pass to fwgen.parse_spec to validate
    or build directly without a file round-trip."""
    return {"title": f"decomposition of {name}", "goals": list(goals), "args": list(args),
            "slots": [{"sheet": _slug(p.name or p.kind, i), "key": f"p{i:02d}",
                       "verb": p.verb, "raw": True, "values": [p.code]}
                      for i, p in enumerate(pieces, start=1)]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="code_decompose",
                                 description="Split code into pieces → fwgen TOML (rewrite & combine).")
    ap.add_argument("src", help="source file to decompose")
    ap.add_argument("--lang", choices=["auto", "py", "java", "generic"], default="auto")
    ap.add_argument("--name", default="", help="logical name (default: file stem)")
    ap.add_argument("--out", default="", help="write TOML here (default: stdout)")
    ap.add_argument("--max-cell", type=int, default=0,
                    help="byte-preservingly sub-split any piece longer than this many chars "
                         f"(spreadsheet/POI cell ceiling = {XLSX_CELL_LIMIT}; 0 = off)")
    a = ap.parse_args(argv)
    src = Path(a.src).read_text(encoding="utf-8")
    name = a.name or Path(a.src).stem
    pieces = decompose(src, a.lang)
    if a.max_cell:
        pieces = subsplit_oversize(pieces, a.max_cell)
    toml = dump_toml(pieces, name)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(toml, encoding="utf-8")
        print(f"{len(pieces)} pieces → {a.out}")
        for i, p in enumerate(pieces, start=1):
            link = " ⇄" if "interacts" in p.note else ""
            print(f"  P{i:02d} {p.kind:<9} {p.name or '(anon)':<24} {len(p.code):>5}B{link}")
    else:
        sys.stdout.write(toml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
