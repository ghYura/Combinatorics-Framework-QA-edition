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

r"""sieve — the constraint-sidecar evaluator + the headless "sieve" pass for the Bundle.

WHAT THIS IS (the agreed architecture — see COLD_START_CONSTRAINTS.md):
  The Core DSL is a GENERATOR, not a constraint language: it has NO verb to forbid a
  value-combination (FW_Exclude is sheet-level + brace-tied; the brace FW_(...) is a JOIN,
  not a filter).  So allowed/forbidden "bonds" between values (the chemistry/genetics
  analogy: atoms carry params; a bond is allowed/forbidden by a FORMULA over those params,
  and proximity/order matters) are a SEPARATE, NON-INVASIVE constraint layer:

      author -> a declarative SIDECAR (params + constraints)  [authoring component]
      enforce -> this SIEVE, inserted BETWEEN Core and Reader, deletes the violating rows
                 of fw_final BEFORE the expensive Reader/Executor see them    [this file]
      fallback -> the Executor oracle (FW_VAR) for constraints that need the fully
                  assembled candidate (complex distance/order, stateful, algorithmic).
  The Core is NOT touched: the sieve filters the table the Core already produced.

This module is the LOAD-BEARING, headless core:
  * a pure in-memory sieve (testable with zero DB), and
  * a DB adapter that runs the SAME logic over fw_final (ready for a live Core run).

Sidecar holds BOTH levels the operator wanted:
  - enumerated pairs           (simple: "a11 never with c11")          -> no params needed
  - predicates over params     (compact: "forbid when A.charge*C.charge>0") -> needs params
  each with a positional GATE  ({} any co-occurrence | {"adjacent":true} | {"within":N}).

  python3 sieve.py            # self-checking demo (verified numbers) + plain-language render
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

# ----------------------------- safe predicate eval --------------------------- #
_SAFE_FUNCS = {"abs": abs, "min": min, "max": max, "round": round, "len": len, "int": int,
               "float": float, "bool": bool, "True": True, "False": False, "None": None}
_UNSAFE = re.compile(r"__|import|lambda|:=|\bexec\b|\beval\b|\bopen\b|\bglobals\b|\blocals\b")


def _eval_pred(expr: str, ns: dict) -> bool:
    """Evaluate a predicate string over per-sheet namespaces. Restricted (no builtins,
    whitelisted funcs, dunder/import banned) — same posture as the repo's difftest eval."""
    if _UNSAFE.search(expr):
        raise ValueError(f"unsafe expression rejected: {expr!r}")
    return bool(eval(expr, {"__builtins__": {}}, {**_SAFE_FUNCS, **ns}))   # noqa: S307 (restricted)


# ----------------------------- sidecar loading ------------------------------- #
def load_sidecar(path: str | Path) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".toml":
        import tomllib
        return tomllib.loads(text)
    return json.loads(text)


def _ns(sheet: str, value: str, params: dict, pos: int) -> SimpleNamespace:
    attrs = dict(params.get(sheet, {}).get(value, {}))
    attrs.setdefault("value", value)
    attrs.setdefault("pos", pos)
    return SimpleNamespace(**attrs)


def _gate_ok(gate: dict, pos_x: int, pos_y: int) -> bool:
    if not gate:
        return True                                    # any co-occurrence
    if gate.get("adjacent"):
        return abs(pos_x - pos_y) == 1
    if "within" in gate:
        return abs(pos_x - pos_y) <= int(gate["within"])
    return True


def _gate_ok_multi(gate: dict, positions: list[int]) -> bool:
    """The positional gate generalized to k>=2 placements (n-ary bonds).
      * ``{}``                => any co-occurrence;
      * ``{"adjacent":true}`` => the chosen positions form a CONTIGUOUS run
                                 (max-min == k-1) — for k=2 this is |x-y| == 1;
      * ``{"within":N}``      => they all fit inside a window of N
                                 (max-min <= N) — for k=2 this is |x-y| <= N.
    Identical to `_gate_ok` when len(positions) == 2."""
    if not gate:
        return True
    span = max(positions) - min(positions)
    if gate.get("adjacent"):
        return span == len(positions) - 1
    if "within" in gate:
        return span <= int(gate["within"])
    return True


def _pair_match(pairs: list, sx: str, vx: str, sy: str, vy: str) -> bool:
    for entry in pairs:                                # entry e.g. {"A":"a11","C":"c11"}
        if entry.get(sx) == vx and entry.get(sy) == vy:
            return True
    return False


def _tuple_match(pairs: list, sheets: list, combo: tuple) -> bool:
    """True if some enumerated entry equals this combo across ALL referenced sheets.
    Generalizes `_pair_match` to k>=2 (entry e.g. {"A":"a11","C":"c11","E":"e3"})."""
    want = {s: pl["value"] for s, pl in zip(sheets, combo)}
    for entry in pairs:
        if all(entry.get(s) == want[s] for s in sheets):
            return True
    return False


# ------------------------------- ordinal `orders` ---------------------------- #
# `orders[sheet]` declares how to RANK a sheet's values, powering the ordinal condition leaves
# (`ge/gt/le/lt` vs a constant, and `geSheet/gtSheet/leSheet/ltSheet` across sheets — date ranges,
# QualityTier/encoding tiers, pagination). Forms:
#   - a LIST of values  -> rank = index in the list  (a value not listed => SPEC ERROR, fail-closed;
#                          never a silent lexicographic guess — see the Zen's quiet-trap lesson)
#   - "numeric"         -> rank = float(value)        (epoch-int dates, integers)
#   - "date"            -> rank = ISO date ordinal     (datetime.date.fromisoformat; strict)
# The absent sentinel is NOT listed; ordinal leaves are vacuously true when a side is absent.
import datetime as _dt  # noqa: E402


def _rank(sheet: str, value, orders: dict | None):
    spec = (orders or {}).get(sheet)
    if spec is None:
        raise ValueError(f"ordinal op references sheet {sheet!r} with no declared order in `orders`")
    if isinstance(spec, (list, tuple)):
        try:
            return spec.index(value)
        except ValueError:
            raise ValueError(f"value {value!r} is not in the declared order for sheet {sheet!r}")
    if spec == "numeric":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"sheet {sheet!r} order is 'numeric' but value {value!r} is not a number")
    if spec == "date":
        try:
            return _dt.date.fromisoformat(str(value)[:10]).toordinal()
        except ValueError:
            raise ValueError(f"sheet {sheet!r} order is 'date' but value {value!r} is not ISO yyyy-mm-dd")
    raise ValueError(f"unknown order spec {spec!r} for sheet {sheet!r} (use a list, 'numeric', or 'date')")


def _ranks(sheet: str, vals, orders: dict | None) -> list:
    return [_rank(sheet, v, orders) for v in vals]


# ----------------- contextual `condition` guard + `mapping` target ----------- #
# A bond may carry a `condition`: a boolean over OTHER columns' VALUES that GATES whether the
# forbid/require fires — "this relation holds ONLY in this context". It re-expresses, on the flat
# fw_final, the way the Core interconnects values across STAGES: a later FW_(...) brace joins a PRIOR
# stage's RESULT table (BraceOperationHandler reads fw2_<k>/fw_<k>, not the raw sheet), so what is
# legal downstream depends on an upstream result. The sieve lost the stage provenance but every
# column's value survives in the row, so a declarative value-context is enough.
#
# The condition is evaluated ONCE per row over the row's full per-sheet SELECTIONS (`sel`:
# sheet -> list[value]; length 1 for an ordinary slot, >1 for a multi-select FW_Subsets slot). Leaves:
#   value:     {"sheet":S,"eq":v}      selection is exactly [v]      {"ne":v}      not exactly [v]
#              {"sheet":S,"has":v}     selection contains v          {"hasnt":v}   does not contain v
#              {"sheet":S,"in":[…]}    selection ⊆ set               {"nin":[…]}   selection ∩ set = ∅
#              {"sheet":S,"hasAny":[…]} selection ∩ set ≠ ∅
#   x-column:  {"sheet":S,"eqSheet":T} selection(S) == selection(T)  {"neSheet":T}  …!=…   (VX=VY)
#   cardinal:  {"sheet":S,"count":n} | {"countGe":n} | {"countLe":n}   |selection| tests (multi-select)
#   node:      {"all":[…]} (AND) | {"any":[…]} (OR) | {"not": cond}
def _condition_sheets(cond) -> list:
    if not cond:
        return []
    out: list = []

    def _add(seq):
        for s in seq:
            if s is not None and s not in out:
                out.append(s)
    for key in ("all", "any"):
        for c in cond.get(key, []) or []:
            _add(_condition_sheets(c))
    if cond.get("not"):
        _add(_condition_sheets(cond["not"]))
    _add([cond.get("sheet")] + [cond.get(k) for k in _COND_SHEET_OPS])
    return out


_COND_NODE_KEYS = {"all", "any", "not"}
_COND_SET_OPS = {"in", "nin", "hasAny"}            # value must be a list of values
_COND_COUNT_OPS = {"count", "countGe", "countLe"}  # value must be an integer (multi-select cardinality)
_COND_SHEET_OPS = {"eqSheet", "neSheet",           # cross-sheet: the value NAMES another sheet
                   "geSheet", "gtSheet", "leSheet", "ltSheet", "subOf", "supOf"}
_COND_ORD_CONST_OPS = {"ge", "gt", "le", "lt"}     # ordinal vs a constant (rank via `orders`)
_COND_LEAF_OPS = (
    {"eq", "ne", "has", "hasnt", "in", "nin", "hasAny", "present"}
    | _COND_SET_OPS | _COND_COUNT_OPS | _COND_SHEET_OPS | _COND_ORD_CONST_OPS
)
_COND_ALLOWED_KEYS = _COND_NODE_KEYS | _COND_LEAF_OPS | {"sheet"}


def _condition_error(cond, path: str = "condition") -> str | None:
    if cond is None or cond == {}:
        return None
    if not isinstance(cond, dict):
        return f"{path} must be an object"
    unknown = sorted(set(cond) - _COND_ALLOWED_KEYS)
    if unknown:
        return f"{path} has unknown key(s) {unknown}"
    node_keys = [k for k in _COND_NODE_KEYS if k in cond]
    leaf_ops = [k for k in _COND_LEAF_OPS if k in cond]
    if node_keys:
        if len(node_keys) != 1 or leaf_ops or "sheet" in cond:
            return f"{path} must be either one boolean node or one sheet leaf"
        key = node_keys[0]
        if key in ("all", "any"):
            children = cond.get(key)
            if not isinstance(children, list) or not children:
                return f"{path}.{key} must be a non-empty list"
            for i, child in enumerate(children):
                err = _condition_error(child, f"{path}.{key}[{i}]")
                if err:
                    return err
        else:
            err = _condition_error(cond.get("not"), f"{path}.not")
            if err:
                return err
        return None
    if "sheet" not in cond:
        return f"{path} leaf needs 'sheet'"
    if len(leaf_ops) != 1:
        return f"{path} leaf needs exactly one operator, got {leaf_ops or 'none'}"
    op = leaf_ops[0]
    val = cond.get(op)
    if op in _COND_SET_OPS and (isinstance(val, (str, bytes)) or not isinstance(val, (list, tuple, set))):
        return f"{path}.{op} must be a list of values"
    if op in _COND_COUNT_OPS and not isinstance(val, int):
        return f"{path}.{op} must be an integer"
    if op in _COND_SHEET_OPS and not (isinstance(val, str) and val):
        return f"{path}.{op} must name another sheet"
    if op == "present" and not isinstance(val, bool):
        return f"{path}.present must be true or false"
    if op in _COND_ORD_CONST_OPS and (val is None or isinstance(val, (list, tuple, set, dict))):
        return f"{path}.{op} must be a scalar constant (rank via `orders`)"
    return None


def _eval_condition(cond, sel: dict, orders: dict | None = None) -> bool:
    """True if the row's per-sheet selections `sel` satisfy `cond`. No condition ⇒ always True. A
    referenced sheet absent from the row ⇒ its selection is empty (leaves resolve against []).
    `orders` ranks values for the ordinal leaves (`ge/gt/le/lt`, `geSheet/…/ltSheet`); see `_rank`.

    Absence rules: `present` reads emptiness directly; the ordinal and subset/superset leaves are
    VACUOUSLY TRUE when a side is absent (pair with a `present` leaf when "both must be present" is
    also wanted — single-purpose, composable primitives)."""
    err = _condition_error(cond)
    if err:
        raise ValueError(f"invalid condition: {err}")
    if not cond:
        return True
    if "all" in cond:
        return all(_eval_condition(c, sel, orders) for c in cond["all"])
    if "any" in cond:
        return any(_eval_condition(c, sel, orders) for c in cond["any"])
    if "not" in cond:
        return not _eval_condition(cond["not"], sel, orders)
    s = cond.get("sheet")
    vals = sel.get(s, [])
    vset = set(vals)
    # ---- presence (is the parameter selected at all?) ----
    if "present" in cond:   return bool(vals) == bool(cond["present"])
    # ---- value membership (unchanged) ----
    if "eq" in cond:        return vals == [cond["eq"]]
    if "ne" in cond:        return vals != [cond["ne"]]
    if "has" in cond:       return cond["has"] in vset
    if "hasnt" in cond:     return cond["hasnt"] not in vset
    if "in" in cond:        return vset <= set(cond["in"])
    if "nin" in cond:       return vset.isdisjoint(cond["nin"])
    if "hasAny" in cond:    return not vset.isdisjoint(cond["hasAny"])
    # ---- cross-sheet equality / subset ----
    if "eqSheet" in cond:   return vset == set(sel.get(cond["eqSheet"], []))
    if "neSheet" in cond:   return vset != set(sel.get(cond["neSheet"], []))
    if "subOf" in cond:     return vset <= set(sel.get(cond["subOf"], []))
    if "supOf" in cond:     return vset >= set(sel.get(cond["supOf"], []))
    # ---- ordinal vs a constant (vacuous on absence) ----
    for op in _COND_ORD_CONST_OPS:
        if op in cond:
            if not vals:
                return True
            c = _rank(s, cond[op], orders)
            rs = _ranks(s, vals, orders)
            return {"ge": min(rs) >= c, "gt": min(rs) > c,
                    "le": max(rs) <= c, "lt": max(rs) < c}[op]
    # ---- ordinal cross-sheet (the whole left selection vs the whole right; vacuous on absence) ----
    for op in ("geSheet", "gtSheet", "leSheet", "ltSheet"):
        if op in cond:
            tvals = sel.get(cond[op], [])
            if not vals or not tvals:
                return True
            ls = _ranks(s, vals, orders)
            rr = _ranks(cond[op], tvals, orders)
            return {"geSheet": min(ls) >= max(rr), "gtSheet": min(ls) > max(rr),
                    "leSheet": max(ls) <= min(rr), "ltSheet": max(ls) < min(rr)}[op]
    # ---- cardinality (multi-select) ----
    if "count" in cond:     return len(vals) == cond["count"]
    if "countGe" in cond:   return len(vals) >= cond["countGe"]
    if "countLe" in cond:   return len(vals) <= cond["countLe"]
    return True


# A `mapping` is a dependent allowed-set (the `key11={val11:val21,val11:val22}` shape): for the chosen
# SOURCE value(s), the TARGET selection must stay WITHIN that source's allowed set — else the row is
# removed (a require-style relation). `allow` maps source value -> [allowed target values]; a source
# value not in `allow` is unconstrained.
def _mapping_sheets(m) -> list:
    return [m["source"], m["target"]] if m else []


def _mapping_error(m, path: str = "mapping") -> str | None:
    if m is None:
        return None
    if not isinstance(m, dict):
        return f"{path} must be an object"
    unknown = sorted(set(m) - {"source", "target", "allow"})
    if unknown:
        return f"{path} has unknown key(s) {unknown}"
    if not m.get("source") or not m.get("target"):
        return f"{path} needs non-empty source and target"
    allow = m.get("allow", {})
    if not isinstance(allow, dict):
        return f"{path}.allow must be an object"
    for key, vals in allow.items():
        if isinstance(vals, (str, bytes)) or not isinstance(vals, (list, tuple, set)):
            return f"{path}.allow[{key!r}] must be a list of values"
    return None


def _mapping_violated(m: dict, sel: dict) -> bool:
    tvals = set(sel.get(m["target"], []))
    allow = m.get("allow", {})
    for sv in sel.get(m["source"], []):
        if sv in allow and not tvals <= set(allow[sv]):
            return True
    return False


# ---------------------------- the core sieve logic --------------------------- #
# A "row" = an ORDERED list of placements: [{"sheet","value","pos"}, ...].  pos = index in
# the assembled output sequence (slot order; or the FW_Permut order for an ordered sheet).
def _rule_id(c: dict) -> str:
    return c.get("id", "<unnamed>")


def _constraint_sheets(c: dict) -> list:
    """The sheets the forbid/require TARGET ranges over (assert/pairs/sets/when/mapping)."""
    if c.get("assert") is not None:
        return _condition_sheets(c["assert"])
    if c.get("mapping"):
        return _mapping_sheets(c["mapping"])
    return c.get("sheets") or list(c.get("sets", {}).keys()) or _sheets_of_pairs(c.get("pairs", []))


def _referenced_sheets(c: dict) -> list:
    """ALL sheets a constraint touches = its target sheets ∪ its `condition` sheets. This is the
    arity that matters: a 1-target bond gated by a `condition` over another sheet IS a bond (it
    relates the two), e.g. forbid SignalClass∈{Radar} WHEN DatasetFamily=Mobility."""
    out = list(_constraint_sheets(c))
    for s in _condition_sheets(c.get("condition")):
        if s not in out:
            out.append(s)
    return out


def validate_sidecar(sidecar: dict, *, strict: bool = False) -> dict:
    """Preflight the sidecar against this sieve engine's supported constraint shape.

    The sieve evaluates n-ary bonds: a constraint may reference TWO OR MORE sheets (a
    forbidden/required tuple of values, or a `when`-predicate over those sheets' params).
    A constraint that names fewer than two sheets is not a bond and is skipped — silently
    ignoring it could make a scenario look tested while an authored rule never ran, so every
    such rule is reported; callers can opt into fail-closed validation with ``strict=True``.
    """
    unsupported = []
    invalid = []
    for c in sidecar.get("constraints", []):
        cond_err = _condition_error(c.get("condition"))
        map_err = _mapping_error(c.get("mapping")) if c.get("mapping") is not None else None
        asrt_err = _condition_error(c.get("assert"), "assert") if c.get("assert") is not None else None
        if cond_err or map_err or asrt_err:
            invalid.append({"id": _rule_id(c), "reason": cond_err or map_err or asrt_err})
            continue
        sheets = _referenced_sheets(c)            # arity counts the condition's sheets too
        if c.get("assert") is not None:           # deliberate-rule family — exempt from the >=2 floor
            if not sheets:
                invalid.append({"id": _rule_id(c), "reason": "assert references no sheet"})
            continue
        if len(sheets) >= 2:
            continue
        unsupported.append({
            "id": _rule_id(c),
            "arity": len(sheets),
            "sheets": sheets,
            "reason": "a bond needs at least two referenced sheets",
        })
    warnings = [
        "skipped unsupported constraint "
        f"{u['id']} (arity={u['arity']}, sheets={u['sheets']})"
        for u in unsupported
    ] + [
        f"invalid constraint {u['id']}: {u['reason']}"
        for u in invalid
    ]
    if strict and (unsupported or invalid):
        raise ValueError("; ".join(warnings))
    return {
        "unsupported_constraints": unsupported,
        "unsupported_constraint_count": len(unsupported),
        "invalid_constraints": invalid,
        "invalid_constraint_count": len(invalid),
        "warnings": warnings,
        # Compatibility aliases for the non-binary bug report wording.
        "skipped_nonbinary_constraints": unsupported,
        "skipped_nonbinary_count": len(unsupported),
    }


def row_violations(row: list[dict], sidecar: dict) -> list[str]:
    """Return the ids of ALL constraints this row violates (in spec order). Used for the STEP 35
    per-rule + overlap statistics: a row removed by two rules appears in both rules' counts but is
    a SINGLE unique removal."""
    params = sidecar.get("params", {})
    orders = sidecar.get("orders", {})
    placed: dict[str, list] = {}
    sel: dict[str, list] = {}
    for p in row:
        placed.setdefault(p["sheet"], []).append(p)
        sel.setdefault(p["sheet"], []).append(p["value"])   # per-sheet selection — the `condition` context
    hits: list[str] = []
    for c in sidecar.get("constraints", []):
        is_assert = c.get("assert") is not None
        # `assert` is the deliberate-rule family (a condition-AST as the bond body) and is EXEMPT from
        # the >=2-sheet floor that catches accidentally-underspecified pairs/sets bonds.
        if not is_assert and len(_referenced_sheets(c)) < 2:
            continue                                   # a bond needs >=2 sheets (see validate_sidecar)
        cond = c.get("condition")
        if cond is not None and not _eval_condition(cond, sel, orders):
            continue                                   # out of context — the bond is inert on this row
        if is_assert:                                  # require/forbid a condition-AST over `sel`
            holds = _eval_condition(c["assert"], sel, orders)
            forbid = c.get("polarity", "require") == "forbid"
            if (forbid and holds) or ((not forbid) and (not holds)):
                hits.append(_rule_id(c))
            continue
        mapping = c.get("mapping")
        if mapping is not None:                        # dependent allowed-set (require-style relation)
            if _mapping_violated(mapping, sel):
                hits.append(_rule_id(c))
            continue
        sheets = _constraint_sheets(c)
        plists = [placed.get(s, []) for s in sheets]
        if any(not pl for pl in plists):
            continue                                   # a referenced sheet is absent from this row
        gate = c.get("gate", {})
        forbid = c.get("polarity", "forbid") == "forbid"
        when = c.get("when")
        sets = c.get("sets")
        setmap = {s: set(v) for s, v in sets.items()} if sets else None
        pairs = c.get("pairs", [])
        violated = False
        for combo in itertools.product(*plists):       # one placement per referenced sheet
            positions = [pl["pos"] for pl in combo]
            if len(set(positions)) != len(positions):
                continue                               # two chosen placements share a position
            if not _gate_ok_multi(gate, positions):
                continue
            if when is not None:
                ns = {s: _ns(s, pl["value"], params, pl["pos"]) for s, pl in zip(sheets, combo)}
                holds = _eval_pred(when, ns)
            elif setmap is not None:                   # Many:Many — the CROSS PRODUCT of per-sheet sets
                holds = all(pl["value"] in setmap.get(s, ()) for s, pl in zip(sheets, combo))
            else:
                holds = _tuple_match(pairs, sheets, combo)
            # forbid: a holding (gated) tuple kills the row.
            # require: a gated tuple that does NOT hold kills the row.
            if (forbid and holds) or ((not forbid) and (not holds)):
                violated = True
                break
        if violated:
            hits.append(_rule_id(c))
    return hits


def row_violates(row: list[dict], sidecar: dict) -> str | None:
    """Return the id of the FIRST violated constraint, or None if the row survives."""
    hits = row_violations(row, sidecar)
    return hits[0] if hits else None


def _sheets_of_pairs(pairs: list) -> list:
    seen = []
    for e in pairs:
        for k in e:
            if k not in seen:
                seen.append(k)
    return seen


def sieve(rows: list[list[dict]], sidecar: dict, *, sample: int = 5, strict: bool = False) -> dict:
    """STEP 35 impact report (the dry-run / preview — DELETES NOTHING). Reports, per the plan:
    `scanned`, `matched` (per-rule count of rows each rule would remove), `overlap` (rows removed
    by MORE THAN ONE rule), `unique_removals` (distinct rows removed — a row counted once even if
    several rules hit it), and `retained`. ``sample`` bounds the example lists (action 5).

    Overlap semantics (made explicit): ``sum(matched.values())`` counts a row once PER rule it
    violates, so it equals ``unique_removals`` plus one extra for each additional rule a removed
    row trips; ``overlap`` is the number of rows tripped by ≥2 rules. (For ≤2 rules,
    ``total_rule_matches - unique_removals == overlap``.)"""
    validation = validate_sidecar(sidecar, strict=strict)
    rule_ids = [_rule_id(c) for c in sidecar.get("constraints", [])]
    matched = {rid: 0 for rid in rule_ids}
    kept, removed, overlap = [], [], 0
    for r in rows:
        hits = row_violations(r, sidecar)
        for rid in hits:
            matched[rid] = matched.get(rid, 0) + 1
        if hits:
            removed.append((r, hits))
            if len(hits) > 1:
                overlap += 1
        else:
            kept.append(r)
    scanned = len(rows)
    report = {
        "scanned": scanned,
        "matched": matched,
        "overlap": overlap,
        "unique_removals": len(removed),
        "retained": scanned - len(removed),
        "total_rule_matches": sum(matched.values()),
        # legacy keys (existing callers/tests rely on these):
        "total": scanned, "kept": len(kept), "removed": len(removed),
        "kept_rows": kept,
        "removed_examples": [(_render_row(r), hits) for r, hits in removed[:sample]],
        "kept_examples": [_render_row(r) for r in kept[:sample]],
    }
    report.update(validation)
    return report


def referenced(c: dict) -> dict:
    """The sheets and param attributes a constraint references (for `constraints explain`)."""
    sheets = _referenced_sheets(c)
    params = sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)", c.get("when", ""))))
    return {"sheets": sheets, "params": params, "gate": c.get("gate", {}),
            "condition": c.get("condition"), "mapping": bool(c.get("mapping")),
            "assert": bool(c.get("assert"))}


def format_explain(sidecar: dict, report: dict | None = None, *, sample: int = 5) -> str:
    """Render `bundle constraints explain`: each rule's plain text + referenced sheets/params, and
    — when a scan `report` is supplied — its quantitative effect plus BOUNDED sample rejected
    combinations and retained boundary cases (action 2 & 5)."""
    out = ["constraints explain:"]
    constraints = sidecar.get("constraints", [])
    matched = (report or {}).get("matched", {})
    unsupported = {u["id"]: u for u in (report or validate_sidecar(sidecar)).get("unsupported_constraints", [])}
    for c in constraints:
        rid = _rule_id(c)
        ref = referenced(c)
        out.append(f"  • {rid}: {describe(c)}")
        out.append(f"      sheets={ref['sheets']}  params={ref['params'] or '—'}  gate={ref['gate'] or '{}'}")
        if rid in unsupported:
            u = unsupported[rid]
            out.append(f"      WARNING: skipped — not a bond (arity={u['arity']}, reason={u['reason']})")
        if rid in matched:
            out.append(f"      would remove {matched[rid]} row(s)")
    if report is not None:
        for w in report.get("warnings", []):
            out.append(f"  WARNING: {w}")
        out.append(f"  impact: scanned {report['scanned']}  unique_removals {report['unique_removals']}  "
                   f"overlap {report['overlap']}  retained {report['retained']}")
        out.append("  sample rejected combinations:")
        for rendered, hits in report.get("removed_examples", [])[:sample]:
            out.append(f"      ✗  {rendered}   [{', '.join(hits)}]")
        out.append("  sample retained (boundary) cases:")
        for rendered in report.get("kept_examples", [])[:sample]:
            out.append(f"      ✓  {rendered}")
    return "\n".join(out)


def _render_row(row: list[dict]) -> str:
    return " + ".join(f"{p['sheet']}:{p['value']}" for p in sorted(row, key=lambda p: p["pos"]))


# ------------------------------- UX: plain language -------------------------- #
def describe_condition(cond) -> str:
    """A short human phrase for a `condition` AST (used in `explain` and the GUI link text)."""
    if not cond:
        return ""
    if "all" in cond:
        return " and ".join(f"({describe_condition(c)})" for c in cond["all"])
    if "any" in cond:
        return " or ".join(f"({describe_condition(c)})" for c in cond["any"])
    if "not" in cond:
        return f"not ({describe_condition(cond['not'])})"
    s = cond.get("sheet")
    if "present" in cond:
        return f"{s} present" if cond["present"] else f"{s} absent"
    for op, sym in (("eq", "="), ("ne", "≠"), ("has", "∋"), ("hasnt", "∌"),
                    ("eqSheet", "="), ("neSheet", "≠"),
                    ("ge", "≥"), ("gt", ">"), ("le", "≤"), ("lt", "<"),
                    ("geSheet", "≥"), ("gtSheet", ">"), ("leSheet", "≤"), ("ltSheet", "<"),
                    ("subOf", "⊆"), ("supOf", "⊇")):
        if op in cond:
            return f"{s}{sym}{cond[op]}"
    for op, sym in (("in", "∈"), ("nin", "∉"), ("hasAny", "∩")):
        if op in cond:
            return f"{s}{sym}{{{', '.join(map(str, cond[op]))}}}"
    for op, sym in (("count", "="), ("countGe", "≥"), ("countLe", "≤")):
        if op in cond:
            return f"|{s}|{sym}{cond[op]}"
    return ""


def describe(c: dict) -> str:
    """Render a constraint as a human sentence (the always-show-words UX)."""
    if c.get("desc"):
        return ("❌ " if c.get("polarity", "forbid") == "forbid" else "✅ ") + c["desc"]
    gate = c.get("gate", {})
    where = (" when adjacent" if gate.get("adjacent")
             else f" when within {gate['within']}" if "within" in gate else " together")
    ctx = describe_condition(c.get("condition"))
    cond_txt = f"  [only when {ctx}]" if ctx else ""
    if c.get("assert") is not None:                    # condition-AST as the bond body (deliberate rule)
        pol = "Require" if c.get("polarity", "require") == "require" else "Forbid"
        return f"{pol}: {describe_condition(c['assert'])}{cond_txt}"
    pol = "Forbid" if c.get("polarity", "forbid") == "forbid" else "Require"
    if c.get("mapping"):                               # dependent allowed-set (key→{values})
        m = c["mapping"]
        body = "; ".join(f"{m['source']}={k}→{m['target']}∈{{{', '.join(map(str, v))}}}"
                         for k, v in m.get("allow", {}).items())
        return f"Map {body}{cond_txt}"
    if "when" in c:
        sheets = "/".join(c.get("sheets", []))
        return f"{pol} {sheets}{where}: {c['when']}{cond_txt}"
    if c.get("sets"):                                  # Many:Many — cross product of per-sheet value sets
        body = " × ".join(f"{s}∈{{{', '.join(map(str, vals))}}}" for s, vals in c["sets"].items())
        return f"{pol}{where}: {body}{cond_txt}"
    pairs = ", ".join("+".join(f"{k}:{v}" for k, v in e.items()) for e in c.get("pairs", []))
    return f"{pol}{where}: {pairs}{cond_txt}"


# ----------------------------- DB adapter (fw_final) ------------------------- #
def sieve_fw_final(conn, table: str, sidecar: dict,
                   code2val: dict[str, dict[int, str]], sheet_order: list[str],
                   combos_col: dict[str, str], id_col: str = "combi_id",
                   baseline: dict[str, str] | None = None, dry_run: bool = True,
                   strict: bool = False, optional_sheets=None) -> dict:
    r"""Run the SAME sieve over a Core-filled fw_final, BETWEEN Core and Reader.

    fw_final rows carry per-sheet `combos<key>_<sheet>` smallint[] columns. CRUCIAL ENCODING
    (verified live on diff_fuzz_run): it is a DELTA-AGAINST-BASELINE form —
      * an EMPTY/NULL cell  => the slot's BASELINE value (the slot's FIRST value), and
      * a non-empty cell    => the deviating value's code (decode via `NumberToValue1`).
    (HEAD with one value is always baseline => always empty; a 3-value slot deviates 2/3 of
    the rows => 162/243 non-empty.)  So you MUST pass `baseline` {sheet -> baseline value} or
    baseline-valued combinations are silently missed.

    We decode each row -> ordered placements (sheet_order = FW_Seq slot order; an ordered
    FW_Permut sheet's array order IS the sequence), reuse row_violates, and DELETE violators
    by id. `dry_run=True` only counts (run it first). Main-DB fw_final id col = `combi_id`.

    code2val:   {sheet: {code:int -> value:str}}  (from NumberToValue1, split per sheet)
    combos_col: {sheet -> column name}            (case-sensitive, e.g. {"O1":"combos2_O1"})
    baseline:   {sheet -> baseline value:str}     (the slot's FIRST value; empty cell => this)
    Returns {"scanned","violating","deleted"}.
    """
    baseline = baseline or {}
    optional_sheets = set(optional_sheets or ())
    # FW_Optional sheets are factored into fw_optX and ASSEMBLED in the Reader — they are NOT
    # materialized in the compact fw_final rows. A bond touching an optional sheet cannot be
    # enforced here (deleting a fw_final row would wrongly drop the mandatory combo for EVERY
    # optional choice), so it is DEFERRED to the candidate-assembly stage and only reported.
    deferred = [c for c in sidecar.get("constraints", [])
                if optional_sheets & set(_referenced_sheets(c))]
    deferred_ids = {id(c) for c in deferred}
    active = {"version": sidecar.get("version", 1), "params": sidecar.get("params", {}),
              "orders": sidecar.get("orders", {}),
              "constraints": [c for c in sidecar.get("constraints", []) if id(c) not in deferred_ids]}
    validation = validate_sidecar(active, strict=strict)
    sample = 5
    rule_ids = [_rule_id(c) for c in active.get("constraints", [])]
    matched = {rid: 0 for rid in rule_ids}
    # FW_Exclude'd slots (brace operands, intermediate brace targets, headings) are
    # moved out of the mandatory Cartesian, so fw_final has NO combos column for
    # them: they exist only inside the joined result the brace produced. Decoding
    # must therefore walk the sheets that are actually materialized, in slot order.
    # `pos` counts materialized columns, which is what the row genuinely is — a
    # positional gate must not count axes the row does not contain.
    # A rule naming a non-materialized sheet can never fire here. Silently keeping
    # every row would look exactly like "the constraint allowed everything", so it
    # fails instead, before any query runs: an unenforceable bond has to be visible.
    unreachable = {s for c in active.get("constraints", [])
                   for s in _referenced_sheets(c)} - set(combos_col)
    if unreachable:
        raise ValueError(
            f"constraint(s) reference sheet(s) {sorted(unreachable)} that have no fw_final "
            f"column — they are FW_Exclude'd (or FW_Heading) and so are not independent axes "
            f"of the mandatory product. Bond a materialized sheet instead, or enforce the rule "
            f"in the candidate oracle.")
    sheet_order = [s for s in sheet_order if s in combos_col]
    cur = conn.cursor()
    cols = [combos_col[s] for s in sheet_order]
    cur.execute(f'SELECT {id_col}, ' + ", ".join(f'"{c}"' for c in cols) + f' FROM "{table}";')
    violating_ids, scanned, overlap = [], 0, 0
    removed_examples, kept_examples = [], []
    for rec in cur.fetchall():
        scanned += 1
        rid, arrays = rec[0], rec[1:]
        row, pos = [], 0
        for s, arr in zip(sheet_order, arrays):
            if arr:                                       # deviating value(s)
                for code in arr:
                    val = code2val.get(s, {}).get(int(code))
                    if val is not None:
                        row.append({"sheet": s, "value": val, "pos": pos})
            elif s in baseline:                           # EMPTY => slot baseline (first value)
                row.append({"sheet": s, "value": baseline[s], "pos": pos})
            pos += 1
        hits = row_violations(row, active)
        for h in hits:
            matched[h] = matched.get(h, 0) + 1
        if hits:
            violating_ids.append(rid)
            if len(hits) > 1:
                overlap += 1
            if len(removed_examples) < sample:
                removed_examples.append((_render_row(row), hits))
        elif len(kept_examples) < sample:
            kept_examples.append(_render_row(row))
    deleted = 0
    if not dry_run and violating_ids:                     # dry_run=True NEVER deletes (action 3)
        cur.execute(f'DELETE FROM "{table}" WHERE {id_col} = ANY(%s);', (violating_ids,))
        conn.commit()
        deleted = len(violating_ids)
    cur.close()
    # STEP 35: identical stats whether dry-run or actual (action 4). `deleted` is 0 on a dry-run.
    report = {"scanned": scanned, "matched": matched, "overlap": overlap,
              "unique_removals": len(violating_ids), "retained": scanned - len(violating_ids),
              "total_rule_matches": sum(matched.values()),
              "removed_examples": removed_examples, "kept_examples": kept_examples,
              "violating": len(violating_ids), "deleted": deleted}   # back-compat keys
    report.update(validation)
    report["deferred"] = [{"id": _rule_id(c), "sheets": _referenced_sheets(c),
                           "optional_sheets": sorted(optional_sheets & set(_referenced_sheets(c)))}
                          for c in deferred]
    report["deferred_count"] = len(deferred)
    if deferred:
        extra = []
        for c in deferred:
            opt_ref = sorted(optional_sheets & set(_referenced_sheets(c)))
            if c.get("condition") is not None or c.get("mapping") is not None:
                extra.append(
                    f"deferred bond {_rule_id(c)} — references optional sheet(s) {opt_ref}; "
                    "not enforceable by the fw_final sieve; stage_sieve compiles it for Reader "
                    "optional assembly when the contextual domain can be enumerated, otherwise fails closed")
            else:
                extra.append(
                    f"deferred bond {_rule_id(c)} — references optional sheet(s) {opt_ref}; "
                    "enforced at candidate assembly (Reader), not the fw_final sieve")
        report["warnings"] = list(report.get("warnings", [])) + extra
    return report


# --------------------- build decode maps from a live DB ---------------------- #
def build_maps_from_db(conn, table: str, slots) -> tuple:
    r"""Derive (code2val, baseline, combos_col, sheet_order) from a Core-filled DB.

    fw_final is storage-economical RELATIVE TO `<table>_base` / `<table>_base_copy` (the base
    row): an empty `combos*` cell INHERITS the base value. So the baseline is read from that base
    row (source of truth — `fw_final_base` if present, else `fw_final_base_copy`, which the Reader
    keeps for column shape), NOT guessed from the spec. `code2val` comes from `NumberToValue1`,
    whitespace-stripped to match authored values. `slots` = spec slots (for sheet order + fallback).

    FW_Optional slots are EXCLUDED from the baseline: their value lives in fw_optX and is assembled
    in the Reader, so an empty optional cell in fw_final means the action is ABSENT — NOT that the
    slot's first value is present. Inheriting a baseline there would make the sieve hallucinate an
    optional value on every mandatory row (see sieve_fw_final's deferral of optional bonds).
    """
    optional = {s.sheet for s in slots if "FW_Optional" in getattr(s, "flags", ())}
    cur = conn.cursor()
    cur.execute("select column_name from information_schema.columns "
                "where table_name=%s and column_name like 'combos%%';", (table,))
    combos_col = {}
    for (col,) in cur.fetchall():
        combos_col[col.split("_", 1)[1] if "_" in col else col] = col
    cur.execute('select bigint, value from "NumberToValue1";')
    gmap = {int(code): (val or "").strip() for code, val in cur.fetchall()}
    sheet_order = [s.sheet for s in slots]
    code2val = {s.sheet: gmap for s in slots}                 # codes are globally unique
    # baseline ← the base row (what empty fw_final cells inherit)
    base_tbl = None
    for cand in (table + "_base", table + "_base_copy"):
        cur.execute("select 1 from information_schema.tables where table_name=%s;", (cand,))
        if cur.fetchone():
            base_tbl = cand
            break
    baseline = {}
    if base_tbl:
        names = [s.sheet for s in slots if s.sheet in combos_col and s.sheet not in optional]
        cols = ", ".join(f'"{combos_col[n]}"' for n in names)
        cur.execute(f'select {cols} from "{base_tbl}" limit 1;')
        rec = cur.fetchone()
        if rec:
            for n, arr in zip(names, rec):
                if arr:
                    baseline[n] = gmap.get(int(arr[0]), "")
    for s in slots:                                           # fallback: spec first value
        if s.sheet in optional:                               # optional cell empty => ABSENT, not baseline
            continue
        baseline.setdefault(s.sheet, (s.values[0] or "").strip())
    cur.close()
    return code2val, baseline, combos_col, sheet_order


# ---- enforce DEFERRED optional bonds at Reader assembly (the scalable, non-invasive path) ---- #
def _holding_value_tuples(c: dict, sheets: list, params: dict):
    """The value-tuples (each a dict sheet→value) over `sheets` for which a bond 'holds' — its own
    small combinatorial space. Enumerated `pairs`, the `sets` cross product, and `when`-true tuples
    (evaluated over the referenced sheets' param values) all collapse to one tuple set. Returns None
    when it cannot be enumerated (a `when` with no param values, or an unsafe expr)."""
    if c.get("when") is not None:
        spaces = []
        for s in sheets:
            vals = list((params.get(s) or {}).keys())
            if not vals:
                return None
            spaces.append(vals)
        out = []
        for combo in itertools.product(*spaces):
            ns = {s: _ns(s, v, params, 0) for s, v in zip(sheets, combo)}
            try:
                if _eval_pred(c["when"], ns):
                    out.append(dict(zip(sheets, combo)))
            except Exception:
                return None
        return out
    if c.get("sets") is not None:
        spaces = [c["sets"].get(s, []) for s in sheets]
        return [dict(zip(sheets, combo)) for combo in itertools.product(*spaces)]
    return [dict(e) for e in c.get("pairs", [])]


def _condition_optional_absence_blocker(cond, optional_sheets: set, path: str = "condition") -> str | None:
    """Return a reason when a condition cannot be compiled to the Reader's present-only
    OptionalBondFilter.

    The Reader filter only evaluates assembled candidates that contain every referenced optional
    sheet. Conditions such as ``hasnt``/``ne``/``countLe`` can become true when an optional sheet is
    absent, so compiling them to present-only code tuples would under-enforce. Equality/membership
    predicates that are false on absence are safe for optional URL-parameter constraints.
    """
    if not cond:
        return None
    if "all" in cond or "any" in cond:
        key = "all" if "all" in cond else "any"
        for i, child in enumerate(cond[key]):
            err = _condition_optional_absence_blocker(child, optional_sheets, f"{path}.{key}[{i}]")
            if err:
                return err
        return None
    if "not" in cond:
        if optional_sheets & set(_condition_sheets(cond["not"])):
            return f"{path}.not references optional sheet(s), which may be true when absent"
        return None
    op = next((k for k in _COND_LEAF_OPS if k in cond), None)
    leaf_sheets = {cond.get("sheet")}
    if op in _COND_SHEET_OPS:
        leaf_sheets.add(cond.get(op))                 # cross-sheet: the named RIGHT sheet counts too
    if not (optional_sheets & {s for s in leaf_sheets if s}):
        return None
    # safe-on-absence: ops that are FALSE when the optional sheet is absent (so present-only
    # compilation does not under-enforce). Everything else (presence, ne/hasnt, ordinal, subset,
    # countLe, …) can flip on absence → fail closed.
    if op in ("eq", "has", "hasAny"):
        return None
    if op == "countGe" and int(cond.get(op, 0)) >= 1:
        return None
    return f"{path} uses absence-sensitive operator {op!r} on optional sheet(s)"


def _domain_values(sheet: str, domain_values: dict | None, params: dict) -> list:
    vals = list((domain_values or {}).get(sheet) or (params.get(sheet) or {}).keys())
    return [str(v).strip() for v in vals]


def _uses_ordinal(cond) -> bool:
    """True if a condition AST uses any ordinal leaf (which needs `orders` to rank)."""
    if not cond:
        return False
    for k in ("all", "any"):
        if any(_uses_ordinal(c) for c in cond.get(k, []) or []):
            return True
    if cond.get("not") and _uses_ordinal(cond["not"]):
        return True
    return any(op in cond for op in (_COND_ORD_CONST_OPS | {"geSheet", "gtSheet", "leSheet", "ltSheet"}))


def _violating_value_tuples(c: dict, params: dict, sheet_order: list, optional_sheets: set,
                            domain_values: dict | None) -> tuple[list, list, str | None]:
    """Enumerate concrete value-tuples that violate a contextual optional bond.

    This bridges the expressive sieve tier (`condition`/`mapping`) to the Reader's compact
    OptionalBondFilter format. We enumerate the bond's own small referenced-domain product,
    evaluate the real row_violations semantics over each tuple, then emit those violating tuples as
    a FORBID line. Missing optional sheets stay naturally inert in the Reader because a candidate
    without every referenced column is not applicable.
    """
    # Ordinal leaves (ge/le/…, geSheet/…) rank values via `orders`, which the Reader's pure short-set
    # OptionalBondFilter cannot express — a bond using them anywhere can't be compiled, fail closed.
    if _uses_ordinal(c.get("condition")) or _uses_ordinal(c.get("assert")):
        return _referenced_sheets(c), [], "uses an ordinal leaf (ge/le/geSheet/…) — not expressible by the Reader filter"
    err = _condition_optional_absence_blocker(c.get("condition"), optional_sheets)
    if not err and c.get("assert") is not None:
        # An `assert` body is the bond itself; over an optional sheet it is absence-sensitive by
        # nature (presence/ordinal/subset) and cannot be expressed by the Reader's pure short-set
        # OptionalBondFilter — fail closed rather than under-enforce.
        err = _condition_optional_absence_blocker(c.get("assert"), optional_sheets, "assert")
    if err:
        return [], [], err
    sheets = _referenced_sheets(c)
    pos = {s: i for i, s in enumerate(sheet_order)}
    missing_pos = [s for s in sheets if s not in pos]
    if missing_pos:
        return sheets, [], f"sheet(s) not present in Reader order: {missing_pos}"
    domains = []
    missing_domains = []
    for s in sheets:
        vals = _domain_values(s, domain_values, params)
        if not vals:
            missing_domains.append(s)
        domains.append(vals)
    if missing_domains:
        return sheets, [], f"missing domain values for sheet(s) {missing_domains}"
    sidecar = {"version": 1, "params": params, "constraints": [c]}
    out = []
    for combo in itertools.product(*domains):
        row = [{"sheet": s, "value": v, "pos": pos[s]} for s, v in zip(sheets, combo)]
        if row_violations(row, sidecar):
            out.append(dict(zip(sheets, combo)))
    return sheets, out, None


def _code_tuple_line(c: dict, sheets: list, tuples: list, *, forbid: bool, code2val: dict,
                     combos_col: dict, sheet_order: list) -> tuple[str | None, str | None]:
    gmap = next(iter(code2val.values()), {})
    val2codes: dict = {}
    for code, val in gmap.items():
        val2codes.setdefault(val, []).append(int(code))
    pos = {s: i for i, s in enumerate(sheet_order)}
    if any(s not in combos_col or s not in pos for s in sheets):
        missing = [s for s in sheets if s not in combos_col or s not in pos]
        return None, f"sheet(s) not present in Reader columns: {missing}"
    gate_ok = _gate_ok_multi(c.get("gate", {}), [pos[s] for s in sheets])
    code_tuples, ok = [], True
    for t in tuples:
        per_sheet = []
        for s in sheets:
            cs = val2codes.get(t.get(s))
            if not cs:
                ok = False
                break
            per_sheet.append(cs)
        if not ok:
            break
        for combo in itertools.product(*per_sheet):
            code_tuples.append(combo)
    if not ok:
        return None, "one or more constraint values were not interned in NumberToValue1"
    if not code_tuples and forbid:
        return None, None
    cols = ",".join(sheets)
    tuplepart = ";".join(",".join(str(x) for x in tup) for tup in code_tuples)
    return f"{'F' if forbid else 'R'}|{'1' if gate_ok else '0'}|{cols}|{tuplepart}", None


def decode_assembly(conn, table: str, code2val: dict, sheet_order: list, combos_col: dict,
                    baseline: dict, optional_sheets, opt_tables: list) -> tuple:
    r"""Decode `fw_final` → mandatory placement-rows and all `fw_optX` → optional placement-rows,
    ONCE. The editor's live exact preview caches these so each `/impact` call doesn't re-read the DB
    (the tables don't change during a draw session). Returns ``(finals, opts)`` (lists of placement
    lists), ready for `impact_over_rows`."""
    optional_sheets = set(optional_sheets or ())
    cur = conn.cursor()
    cols = ", ".join(f'"{combos_col[s]}"' for s in sheet_order)

    def decode(arrays, want_optional):
        place = []
        for pos, (s, arr) in enumerate(zip(sheet_order, arrays)):
            is_opt = s in optional_sheets
            if is_opt != want_optional:
                continue
            if arr:
                for code in arr:
                    v = code2val.get(s, {}).get(int(code))
                    if v is not None:
                        place.append({"sheet": s, "value": v, "pos": pos})
            elif (not is_opt) and (s in baseline):
                place.append({"sheet": s, "value": baseline[s], "pos": pos})
        return place

    cur.execute(f'SELECT {cols} FROM "{table}";')
    finals = [decode(rec, False) for rec in cur.fetchall()]
    opts = []
    for t in opt_tables:
        cur.execute(f'SELECT {cols} FROM "{t}";')
        opts.extend(decode(rec, True) for rec in cur.fetchall())
    cur.close()
    return finals, opts


def impact_over_rows(finals: list, opts: list, sidecar: dict, optional_sheets, cap: int = 300_000) -> dict:
    r"""EXACT removed/kept over PRE-DECODED rows (see `decode_assembly`) — DB-free, so the editor's
    live preview reuses cached rows. Same semantics as `exact_impact`:

      * a MANDATORY bond (references only non-optional sheets) deletes a fw_final row → kills ALL of
        that row's assembled forms (× the optional multiplier);
      * an OPTIONAL bond (touches an optional sheet) deletes the ASSEMBLED candidate (a surviving
        fw_final row ∪ one fw_optX combo) — never a fw_final row, never the optional-absent form.

    No double counting (a mandatory-removed row is not re-checked). The optional pass is
    `surviving × Σ|fw_optX|`; above ``cap`` it returns ``exact=False`` so the caller shows the
    offline estimate. Reuses `row_violations`."""
    optional_sheets = set(optional_sheets or ())
    cons = sidecar.get("constraints", [])
    params = sidecar.get("params", {})
    orders = sidecar.get("orders", {})
    mand = [c for c in cons if not (optional_sheets & set(_referenced_sheets(c)))]
    opt = {"version": 1, "params": params, "orders": orders,
           "constraints": [c for c in cons if optional_sheets & set(_referenced_sheets(c))]}
    mand_sc = {"version": 1, "params": params, "orders": orders, "constraints": mand}
    nfin, nopt = len(finals), len(opts)
    mult = 1 + nopt
    total = nfin * mult
    removed, surviving = 0, []
    for f in finals:
        if mand and row_violations(f, mand_sc):
            removed += mult                                    # the whole row (all its candidates) dies
        else:
            surviving.append(f)
    exact = True
    if opt["constraints"] and nopt:
        if len(surviving) * nopt > cap:
            exact = False                                      # too large to count the assembled space exactly
        else:
            for f in surviving:
                for o in opts:
                    if row_violations(f + o, opt):
                        removed += 1
    return {"exact": exact, "total": total, "removed": removed if exact else None,
            "kept": (total - removed) if exact else None,
            "mandatory_rows": nfin, "optional_multiplier": mult}


def exact_impact(conn, table: str, sidecar: dict, code2val: dict, sheet_order: list,
                 combos_col: dict, baseline: dict, optional_sheets, opt_tables: list,
                 cap: int = 300_000) -> dict:
    r"""One-shot EXACT impact over the whole assembled space (`decode_assembly` + `impact_over_rows`)
    — see those. For a live editor, decode once with `decode_assembly` and reuse `impact_over_rows`."""
    finals, opts = decode_assembly(conn, table, code2val, sheet_order, combos_col, baseline,
                                   optional_sheets, opt_tables)
    return impact_over_rows(finals, opts, sidecar, optional_sheets, cap)


def optional_bond_compile_report(deferred: list, params: dict, code2val: dict, combos_col: dict,
                                 sheet_order: list, optional_sheets, domain_values: dict | None = None) -> dict:
    r"""Compile deferred optional bonds into Reader OptionalBondFilter lines, or report blockers.

    Plain `pairs`/`sets`/`when` constraints keep the legacy compact representation. Contextual
    `condition`/`mapping` constraints are compiled by enumerating the small referenced-domain product
    and emitting the value tuples that violate the real sieve semantics as FORBID tuples. This lets
    optional URL parameters participate in the same constraint layer without silently bypassing the
    Reader assembly stage. Unsupported absence-sensitive optional conditions fail closed via
    `blockers`.
    """
    optional_sheets = set(optional_sheets or ())
    lines, blockers = [], []
    for c in deferred:
        contextual = (c.get("condition") is not None or c.get("mapping") is not None
                      or c.get("assert") is not None)
        if contextual:
            sheets, tuples, err = _violating_value_tuples(c, params, sheet_order, optional_sheets, domain_values)
            if err:
                blockers.append({"id": _rule_id(c), "reason": err,
                                 "features": [k for k in ("condition", "mapping", "assert") if c.get(k) is not None],
                                 "sheets": sheets or _referenced_sheets(c),
                                 "optional_sheets": sorted(optional_sheets & set(_referenced_sheets(c)))})
                continue
            if not tuples:
                continue
            line, err = _code_tuple_line(c, sheets, tuples, forbid=True, code2val=code2val,
                                         combos_col=combos_col, sheet_order=sheet_order)
            if err:
                blockers.append({"id": _rule_id(c), "reason": err,
                                 "features": [k for k in ("condition", "mapping", "assert") if c.get(k) is not None],
                                 "sheets": sheets, "optional_sheets": sorted(optional_sheets & set(sheets))})
            elif line:
                lines.append(line)
            continue

        sheets = _constraint_sheets(c)
        tuples = _holding_value_tuples(c, sheets, params)
        if tuples is None:
            blockers.append({"id": _rule_id(c), "reason": "constraint tuples could not be enumerated",
                             "features": [], "sheets": sheets,
                             "optional_sheets": sorted(optional_sheets & set(sheets))})
            continue
        forbid = c.get("polarity", "forbid") != "require"
        line, err = _code_tuple_line(c, sheets, tuples, forbid=forbid, code2val=code2val,
                                     combos_col=combos_col, sheet_order=sheet_order)
        if err:
            blockers.append({"id": _rule_id(c), "reason": err, "features": [], "sheets": sheets,
                             "optional_sheets": sorted(optional_sheets & set(sheets))})
        elif line:
            lines.append(line)
    return {"lines": lines, "blockers": blockers}


def optional_bond_specs(deferred: list, params: dict, code2val: dict, combos_col: dict,
                        sheet_order: list, optional_sheets, domain_values: dict | None = None) -> list:
    r"""Backward-compatible wrapper returning only compiled Reader bond lines.

    Call `optional_bond_compile_report` when the caller must fail closed on uncompiled deferred
    bonds. The line format is ``<F|R>|<gateOk 1/0>|<col,col,...>|<code,code,...;...>``.
    """
    return optional_bond_compile_report(deferred, params, code2val, combos_col, sheet_order,
                                        optional_sheets, domain_values).get("lines", [])


def optional_bond_compile_blockers(deferred: list, optional_sheets=None) -> list[dict]:
    """Legacy shape-only warning helper.

    Contextual optional bonds may now compile when the caller supplies domains to
    `optional_bond_compile_report`. This helper is intentionally conservative and remains useful for
    callers that only have a sidecar shape, not the Core/Reader code maps.
    """
    optional_sheets = set(optional_sheets or ())
    blockers = []
    for c in deferred:
        features = []
        if c.get("condition") is not None:
            features.append("condition")
        if c.get("mapping") is not None:
            features.append("mapping")
        if c.get("assert") is not None:
            features.append("assert")
        if features:
            refs = _referenced_sheets(c)
            blockers.append({
                "id": _rule_id(c),
                "features": features,
                "sheets": refs,
                "optional_sheets": sorted(optional_sheets & set(refs)),
                "reason": "needs optional_bond_compile_report with domain values",
            })
    return blockers


# ----------------------------------- demo ----------------------------------- #
def _demo_sidecar() -> dict:
    # chemistry: atoms with a 'charge'; A and C are ADJACENT in the output (pos 0,1).
    return {
        "version": 1,
        "params": {
            "A": {"a11": {"charge": 2}, "a12": {"charge": -1}},
            "C": {"c11": {"charge": -2}, "c12": {"charge": 3}},
        },
        "constraints": [
            {"id": "ban_a11_c11", "polarity": "forbid",
             "pairs": [{"A": "a11", "C": "c11"}], "gate": {},
             "desc": "a11 never together with c11"},
            {"id": "no_like_charge_adjacency", "polarity": "forbid",
             "sheets": ["A", "C"], "when": "A.charge * C.charge > 0", "gate": {"adjacent": True},
             "desc": "A next to C is forbidden when their charges share a sign"},
        ],
    }


def _demo_rows() -> list[list[dict]]:
    A, C = ["a11", "a12"], ["c11", "c12"]
    rows = []
    for a in A:
        for c in C:
            rows.append([{"sheet": "A", "value": a, "pos": 0},
                         {"sheet": "C", "value": c, "pos": 1}])
    return rows


def main():
    if len(sys.argv) > 1:                              # sieve.py <sidecar> [rows.json]
        sc = load_sidecar(sys.argv[1])
        rows = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else _demo_rows()
    else:
        sc, rows = _demo_sidecar(), _demo_rows()
    print("=== constraint sieve — demo (chemistry bonds) ===\n")
    print("rules (plain language, the UX surface):")
    for c in sc["constraints"]:
        print("   ", describe(c))
    rep = sieve(rows, sc)
    print(f"\nimpact: {rep['total']} combinations -> kept {rep['kept']}, removed {rep['removed']}")
    print("  removed (with the rule that killed each):")
    for r, vid in rep["removed_examples"]:
        print(f"    x   {r}   [{vid}]")
    print("  kept:")
    for r in rep["kept_examples"]:
        print(f"    ✓   {r}")
    print("\n(DB mode: sieve_fw_final(conn, ...) runs this exact logic over a Core-filled "
          "fw_final, deleting violators between Core and Reader — Core untouched.)")


if __name__ == "__main__":
    main()
