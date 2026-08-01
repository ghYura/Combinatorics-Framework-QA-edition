from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import fwgen as fg

from .jsonio import write_json_atomic


BIASPLAN_SCHEMA = "bundle.biasplan/v1"

_CANDIDATE_ID_RE = re.compile(r"^(?P<final>\d+)_(?P<opt>\d+)_(?P<suffix>\d+)$")
_TOKEN_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>\S+)")


class SeedBiasError(ValueError):
    """A seed could not be converted into a safe pruning plan."""


class DegenerateBiasPlan(SeedBiasError):
    """The seed was valid but carried no useful narrowing signal."""


@dataclass(frozen=True)
class ValueBias:
    value: str
    winner_count: int
    decision: str
    reason: str = ""


@dataclass(frozen=True)
class SheetBias:
    sheet: str
    domain_values: list[str]
    winner_observations: int
    winner_values: list[str]
    kept_values: list[str]
    excluded_values: list[str]
    min_keep: int
    coverage: float
    values: list[ValueBias] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class WinnerRow:
    candidate_id: str
    line_no: int | None
    role: str
    values: dict[str, tuple[str, ...]]
    score: float | None = None
    crowding_distance: float | None = None


@dataclass(frozen=True)
class BiasPlan:
    schema: str
    source_run_id: str
    source_seed_sha256: str
    per_sheet: dict[str, SheetBias]
    derived_constraints: list[dict]
    exploration_floor: float
    est_keep_fraction: float
    full_space_estimate: int
    est_post_bias_candidates: int
    winner_count: int
    decoded_winner_count: int
    skipped_winner_count: int
    min_winner_support: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_dict(value: Any) -> dict:
    if not isinstance(value, dict):
        raise SeedBiasError(f"seed schemaVersion=1 expected a JSON object, got {type(value).__name__}")
    return value


def load_seed(path) -> dict:
    """Parse and validate a BundleSeed v1 JSON document.

    Unknown keys remain available to future versions, but the v1 fields the
    launcher consumes are fail-closed: schemaVersion must be 1 and winners must
    be a list.
    """
    p = Path(path)
    try:
        seed = _as_dict(json.loads(p.read_text(encoding="utf-8")))
    except OSError as exc:
        raise SeedBiasError(f"seed-from {p}: cannot read BundleSeed ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise SeedBiasError(f"seed-from {p}: invalid JSON ({exc})") from exc
    if seed.get("schemaVersion") != 1:
        raise SeedBiasError(f"seed-from {p}: unsupported BundleSeed schemaVersion={seed.get('schemaVersion')!r} (expected 1)")
    winners = seed.get("winners")
    if not isinstance(winners, list):
        raise SeedBiasError(f"seed-from {p}: BundleSeed winners must be a list")
    return seed


def _candidate_id_from_winner(winner: Mapping[str, Any]) -> str | None:
    def valid(value) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            if _CANDIDATE_ID_RE.match(value):
                return value
        return None

    kv = winner.get("kvPairs") or {}
    if isinstance(kv, Mapping):
        for key in ("candidate_id", "combi_id", "id"):
            candidate_id = valid(kv.get(key))
            if candidate_id:
                return candidate_id
    line = winner.get("originalLine") or ""
    if isinstance(line, str):
        tokens = {m.group("key"): m.group("value") for m in _TOKEN_RE.finditer(line)}
        for key in ("candidate_id", "combi_id", "id"):
            candidate_id = valid(tokens.get(key))
            if candidate_id:
                return candidate_id
    return None


def _candidate_parts(candidate_id: str) -> tuple[int, int, int]:
    m = _CANDIDATE_ID_RE.match(candidate_id or "")
    if not m:
        raise SeedBiasError(
            f"winner candidate_id={candidate_id!r} is not the Bundle composite '<fw_final>_<fw_opt>_<opt_suffix>'; "
            "the seed cannot be joined back to Core rows")
    return int(m.group("final")), int(m.group("opt")), int(m.group("suffix"))


def _score(winner: Mapping[str, Any]) -> float | None:
    try:
        value = float(winner.get("score"))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _crowding(winner: Mapping[str, Any]) -> float | None:
    raw = winner.get("crowdingDistance")
    if raw == "Infinity":
        return math.inf
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _select_rows(conn, table: str, ids: Iterable[int], combos_col: Mapping[str, str], sheet_order: list[str]) -> dict[int, tuple]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    cols = [combos_col[s] for s in sheet_order if s in combos_col]
    if not cols:
        raise SeedBiasError(f"table {table}: no combos columns discovered; cannot decode winner rows")
    placeholders = ",".join(["%s"] * len(ids))
    select_cols = ", ".join(['"combi_id"'] + [f'"{c}"' for c in cols])
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT {select_cols} FROM "{table}" WHERE "combi_id" IN ({placeholders});', tuple(ids))
        return {int(row[0]): tuple(row[1:]) for row in cur.fetchall()}
    finally:
        cur.close()


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("select 1 from information_schema.tables where table_name=%s;", (table,))
        return cur.fetchone() is not None
    finally:
        cur.close()


def _decode_arrays(arrays: tuple, *, want_optional: bool, code2val: dict, sheet_order: list[str],
                   baseline: Mapping[str, str], optional_sheets: set[str]) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for pos, (sheet, arr) in enumerate(zip(sheet_order, arrays)):
        is_optional = sheet in optional_sheets
        if is_optional != want_optional:
            continue
        values: list[str] = []
        if arr:
            for code in arr:
                value = code2val.get(sheet, {}).get(int(code))
                if value is not None:
                    values.append(str(value).strip())
        elif (not is_optional) and sheet in baseline:
            values.append(str(baseline[sheet]).strip())
        if values:
            out[sheet] = tuple(values)
    return out


def decode_winner_rows(conn, spec, winners) -> list[WinnerRow]:
    """Decode seed winners into the exact sheet values selected by their DB rows.

    This intentionally reads only the winner row ids. It reuses the sieve's
    Core-aware decode maps so base-row inheritance and FW_Optional absence have
    the same semantics as the existing constraint path.
    """
    import sys
    sys.path.insert(0, str(Path(fg.__file__).resolve().parent / "constraints"))
    import sieve as sv

    code2val, baseline, combos_col, sheet_order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
    optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}

    parsed: list[tuple[Mapping[str, Any], str, int, int, int]] = []
    skipped_missing_id = 0
    for winner in winners:
        if not isinstance(winner, Mapping):
            skipped_missing_id += 1
            continue
        candidate_id = _candidate_id_from_winner(winner)
        if not candidate_id:
            skipped_missing_id += 1
            continue
        final_id, opt_id, suffix = _candidate_parts(candidate_id)
        if opt_id > 0 and suffix <= 0:
            raise SeedBiasError(f"winner candidate_id={candidate_id!r} has optional row {opt_id} but opt suffix {suffix}")
        parsed.append((winner, candidate_id, final_id, opt_id, suffix))
    if not parsed:
        raise SeedBiasError(
            f"BundleSeed winners did not contain any joinable candidate_id values (skipped {skipped_missing_id}); "
            "ensure the Executor metrics corpus prefixes candidate_id=<F>_<O>_<J>")

    final_rows = _select_rows(conn, "fw_final", (p[2] for p in parsed), combos_col, sheet_order)
    missing_final = sorted({p[2] for p in parsed} - set(final_rows))
    if missing_final:
        raise SeedBiasError(f"BundleSeed references fw_final combi_id(s) not present after Core: {missing_final[:10]}")

    opt_rows: dict[int, dict[int, tuple]] = {}
    for suffix in sorted({p[4] for p in parsed if p[3] > 0}):
        table = f"fw_opt{suffix}"
        if not _table_exists(conn, table):
            raise SeedBiasError(f"BundleSeed references optional table {table}, but that table is absent")
        ids = [p[3] for p in parsed if p[3] > 0 and p[4] == suffix]
        opt_rows[suffix] = _select_rows(conn, table, ids, combos_col, sheet_order)
        missing = sorted(set(ids) - set(opt_rows[suffix]))
        if missing:
            raise SeedBiasError(f"BundleSeed references {table} combi_id(s) not present after Core: {missing[:10]}")

    decoded: list[WinnerRow] = []
    for winner, candidate_id, final_id, opt_id, suffix in parsed:
        values = _decode_arrays(final_rows[final_id], want_optional=False, code2val=code2val,
                                sheet_order=sheet_order, baseline=baseline,
                                optional_sheets=optional_sheets)
        if opt_id > 0:
            values.update(_decode_arrays(opt_rows[suffix][opt_id], want_optional=True, code2val=code2val,
                                         sheet_order=sheet_order, baseline=baseline,
                                         optional_sheets=optional_sheets))
        line_no = winner.get("lineNo")
        decoded.append(WinnerRow(candidate_id=candidate_id,
                                 line_no=int(line_no) if isinstance(line_no, int) else None,
                                 role=str(winner.get("role") or ""),
                                 values=values,
                                 score=_score(winner),
                                 crowding_distance=_crowding(winner)))
    return decoded


def _domain_by_sheet(spec) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for slot in spec.slots:
        vals: list[str] = []
        seen: set[str] = set()
        for raw in slot.values:
            value = str(raw).strip()
            if value not in seen:
                seen.add(value)
                vals.append(value)
        out[slot.sheet] = vals
    return out


def _optional_factor(spec) -> int:
    factor = 1
    for slot in spec.slots:
        if "FW_Optional" in slot.flags:
            factor *= len(slot.values) + 1
    return factor


def _full_space_estimate(spec) -> int:
    try:
        return int(fg.estimate_core_combos(spec)) * _optional_factor(spec)
    except Exception:
        n = 1
        for slot in spec.slots:
            n *= max(1, len(slot.values))
        return n


def _adjacent_keep(domain: list[str], kept: set[str]) -> set[str]:
    out = set(kept)
    for value in list(kept):
        try:
            i = domain.index(value)
        except ValueError:
            continue
        if i > 0:
            out.add(domain[i - 1])
        if i + 1 < len(domain):
            out.add(domain[i + 1])
    return out


def _constraint_for(sheet: str, value: str) -> dict:
    # Assert-form keeps the existing strict sidecar validator intact: ordinary
    # pairs/sets still need arity >= 2, while deliberate one-sheet exclusions are
    # represented as a condition body the sieve already knows how to evaluate and
    # defer for FW_Optional assembly when needed.
    return {
        "id": f"seedbias.forbid.{sheet}.{hashlib.sha1(value.encode('utf-8')).hexdigest()[:10]}",
        "polarity": "forbid",
        "assert": {"sheet": sheet, "has": value},
        "desc": f"BundleSeed bias: exclude {sheet}={value!r} (not observed among winners)",
    }


def _rows_relevant_to_declared_goals(rows: list[WinnerRow], seed: Mapping[str, Any], spec=None) -> list[WinnerRow]:
    declared = {str(k) for k in (seed.get("declaredMetrics") or [])}
    goal_dirs = {getattr(g, "key", ""): getattr(g, "direction", "") for g in getattr(spec, "goals", [])}
    relevant: list[WinnerRow] = []
    for row in rows:
        role = row.role or ""
        if role == "pareto" or role.startswith("balanced:"):
            relevant.append(row)
            continue
        if role.startswith("champion-min:") or role.startswith("champion-max:"):
            prefix, key = role.split(":", 1)
            if key not in declared:
                continue
            direction = goal_dirs.get(key)
            if not direction or (prefix == "champion-min" and direction == "min") or (prefix == "champion-max" and direction == "max"):
                relevant.append(row)
    return relevant or rows


def build_bias_plan(spec, winner_rows, seed, *, exploration_floor, min_winner_support) -> BiasPlan:
    if not (0 < float(exploration_floor) <= 1):
        raise SeedBiasError(f"exploration_floor must satisfy 0 < value <= 1, got {exploration_floor!r}")
    if int(min_winner_support) < 1:
        raise SeedBiasError(f"min_winner_support must be >= 1, got {min_winner_support!r}")
    decoded_rows = list(winner_rows or [])
    if not decoded_rows:
        raise SeedBiasError("BundleSeed decoded to zero winner rows; refusing to build an empty bias plan")
    rows = _rows_relevant_to_declared_goals(decoded_rows, seed, spec)

    domains = _domain_by_sheet(spec)
    per_sheet: dict[str, SheetBias] = {}
    constraints: list[dict] = []
    keep_fraction = 1.0
    floor_limited: list[bool] = []

    for sheet, domain in domains.items():
        if not domain:
            per_sheet[sheet] = SheetBias(sheet, [], 0, [], [], [], 0, 0.0, [], "empty domain")
            continue
        counts = {v: 0 for v in domain}
        observations = 0
        for row in rows:
            selected = [v for v in row.values.get(sheet, ()) if v in counts]
            if not selected:
                continue
            observations += 1
            for value in set(selected):
                counts[value] += 1
        winner_values = [v for v in domain if counts[v] > 0]
        coverage = len(winner_values) / len(domain) if domain else 0.0
        min_keep = min(len(domain), max(2, math.ceil(float(exploration_floor) * len(domain))))
        reason = ""
        kept = set(domain)
        excluded: list[str] = []
        if observations < int(min_winner_support):
            reason = f"support {observations} < min_winner_support {int(min_winner_support)}"
        elif coverage >= 0.80:
            reason = f"winner coverage {coverage:.3f} >= 0.800; no narrowing signal"
        elif len(domain) <= min_keep:
            reason = f"domain size {len(domain)} <= exploration minimum {min_keep}"
        else:
            kept = _adjacent_keep(domain, set(winner_values))
            if len(kept) < min_keep:
                for value in domain:
                    kept.add(value)
                    if len(kept) >= min_keep:
                        break
            kept = set(v for v in domain if v in kept)
            excluded = [v for v in domain if v not in kept]
            if not excluded:
                reason = "adjacency/floor retention kept the full domain"
                kept = set(domain)
            else:
                reason = "excluded values absent from winners; immediate declared-order neighbors retained"
                keep_fraction *= len(kept) / len(domain)
                floor_limited.append(len(kept) <= min_keep)
                constraints.extend(_constraint_for(sheet, value) for value in excluded)

        values = [ValueBias(value=v, winner_count=counts.get(v, 0),
                            decision=("drop" if v in excluded else "keep"),
                            reason=("not seen in winners" if v in excluded else "retained"))
                  for v in domain]
        per_sheet[sheet] = SheetBias(sheet=sheet,
                                     domain_values=list(domain),
                                     winner_observations=observations,
                                     winner_values=winner_values,
                                     kept_values=[v for v in domain if v in kept],
                                     excluded_values=excluded,
                                     min_keep=min_keep,
                                     coverage=coverage,
                                     values=values,
                                     reason=reason)

    if not constraints:
        raise DegenerateBiasPlan("seed bias produced no exclusions: every sheet lacked support, already covered >=80%, or was protected by the exploration floor")
    if floor_limited and all(floor_limited):
        raise DegenerateBiasPlan("seed bias would push every narrowed sheet to its exploration floor; refusing to prune noise")
    full = _full_space_estimate(spec)
    post = int(math.floor(full * keep_fraction))
    if post < 1:
        raise SeedBiasError(f"seed bias would keep <1 candidate: full_space_estimate={full}, est_keep_fraction={keep_fraction:.8f}")
    return BiasPlan(schema=BIASPLAN_SCHEMA,
                    source_run_id=str(seed.get("sourceRunId") or ""),
                    source_seed_sha256=str(seed.get("_source_seed_sha256") or ""),
                    per_sheet=per_sheet,
                    derived_constraints=constraints,
                    exploration_floor=float(exploration_floor),
                    est_keep_fraction=float(keep_fraction),
                    full_space_estimate=full,
                    est_post_bias_candidates=max(1, post),
                    winner_count=len(seed.get("winners") or []),
                    decoded_winner_count=len(rows),
                    skipped_winner_count=max(0, len(seed.get("winners") or []) - len(rows)),
                    min_winner_support=int(min_winner_support))


def plan_to_sidecar(plan) -> dict:
    constraints = plan.derived_constraints if isinstance(plan, BiasPlan) else plan.get("derived_constraints", [])
    return {"version": 1, "constraints": list(constraints)}


def write_plan(plan, path) -> None:
    if not isinstance(plan, BiasPlan):
        raise SeedBiasError("write_plan expected a BiasPlan")
    write_json_atomic(Path(path), plan)


def load_seed_with_sha(path) -> dict:
    p = Path(path)
    seed = load_seed(p)
    seed["_source_seed_sha256"] = _sha256(p)
    return seed
