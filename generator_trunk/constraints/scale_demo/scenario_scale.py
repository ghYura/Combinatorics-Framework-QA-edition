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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

r"""scenario_scale — a SCALE demo for the Combinatorics Framework that (1) exercises the engine's
VERB VOCABULARY the Zen way (each verb dictated by the shape of the freedom, not chosen to pad a
count) and (2) stresses the constraint SIEVE at 10^4 -> 10^6 rows, proving the constraint layer does
not fall apart (Core + Reader are already proven to 1e9 by the author).

THE ZEN — the modeled space is "API test-scenario synthesis". Each degree of freedom picks its verb:
  OPS      — the ORDER of API operations is the variable, no repeats        -> FW_Permut    (n!)
  HEADERS  — independent optional request modifiers, each on/off            -> FW_Subsets   (2^n)
  RES      — choose k resources to touch, order irrelevant                  -> FW_Combi(2)  (C(n,2))
  REGION   — exactly one region                                             -> FW_Combi(1)  (n)
  TIER     — exactly one service tier                                       -> FW_Combi(1)  (n)
The count FALLS OUT of honest modeling: n_ops! * 2^n_h * C(n_res,2) * n_reg * n_tier.

THE BONDS (sieve) — a forbidden bond by a FORMULA over params (the chemistry analogy):
  forbid when  REGION.cost + TIER.cost > THRESHOLD     (a budget bond; gate {} = any co-occurrence)
The sieve deletes the violating fw_final rows BETWEEN Core and Reader. Because the bond depends only
on REGION x TIER (each FW_Combi(1) => exactly one per row), the removed count is CLOSED-FORM exact:
  removed = total * |{(r,t): cost_r+cost_t > THR}| / (n_reg*n_tier)
— so every scale is integrity-checked against ground truth.

THE MEANING (verdict) — TAIL marks FW_VAR=2 for an invalid op order (a destructive op before its
create); the full chain (Part 1) shows the pass/fail split. (Sieve = bonds; verdict = meaning.)

Usage:
  scenario_scale.py emit  <dir> <preset>     # write the mixed-verb spec (for bundle_run --sieve)
  scenario_scale.py scale <preset> [...]     # drive fwgen -> Core -> sieve at each preset; integrity+throughput
  presets: chain (~2.6k, full chain) | s1e4 | s1e5 | s1e6
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
GEN = HERE.parent.parent.parent          # generator_trunk/
sys.path.insert(0, str(GEN))
import fwgen as fg                        # noqa: E402
from bundle.config import resolve_config as _resolve_bundle_config  # noqa: E402

OPS_POOL = ["create", "delete", "read", "update", "list", "patch"]   # create+delete early => oracle bites
HDR_POOL = ["auth", "idem", "gzip", "cond", "trace", "etag"]
RES_POOL = ["u1", "u2", "u3", "u4", "u5"]

# preset = (n_ops, n_h, n_res, n_reg, n_tier, thr)
PRESETS = {
    "chain": (4, 2, 3, 3, 3, 2),     # 24 * 4 * 3 * 3 * 3      = 2,592   (full chain incl. Reader/Executor)
    "s1e4":  (4, 3, 4, 4, 4, 3),     # 24 * 8 * 6 * 4 * 4      = 18,432
    "s1e5":  (5, 3, 4, 4, 4, 3),     # 120 * 8 * 6 * 4 * 4     = 92,160
    "s1e6":  (6, 4, 4, 4, 4, 3),     # 720 * 16 * 6 * 4 * 4    = 1,105,920
}


def total_combos(sz) -> int:
    n_ops, n_h, n_res, n_reg, n_tier, _ = sz
    return math.factorial(n_ops) * (2 ** n_h) * math.comb(n_res, 2) * n_reg * n_tier


def removed_groundtruth(sz) -> int:
    """Closed-form: rows whose (REGION.cost + TIER.cost) > thr. cost = index."""
    n_ops, n_h, n_res, n_reg, n_tier, thr = sz
    bad_pairs = sum(1 for r in range(n_reg) for t in range(n_tier) if r + t > thr)
    multiplier = math.factorial(n_ops) * (2 ** n_h) * math.comb(n_res, 2)
    return bad_pairs * multiplier


# ------------------------------- spec emission ------------------------------- #
def _raw_slot(sheet, key, verb, frags):
    L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{key}"',
         f'verb  = "{verb}"', 'raw   = true', 'values = [']
    for f in frags:
        body = "\n" + f.strip("\n") + "\n"
        L.append("'''" + body + "''',")
    return L + [']', '']


def build_toml(sz) -> str:
    n_ops, n_h, n_res, n_reg, n_tier, thr = sz
    ops, hdrs, ress = OPS_POOL[:n_ops], HDR_POOL[:n_h], RES_POOL[:n_res]

    head = ('seq = []        # operation order  (FW_Permut)\n'
            'hdr = set()     # optional headers  (FW_Subsets)\n'
            'res = []        # chosen resources  (FW_Combi(2))\n'
            'region = None   # exactly one       (FW_Combi(1))\n'
            'tier = None     # exactly one       (FW_Combi(1))')
    tail = ('_ok = not ("delete" in seq and "create" in seq and seq.index("delete") < seq.index("create"))\n'
            'FW_VAR = 0 if _ok else 2\n'
            'print("app=scenario ops=%d headers=%d resources=%d region=%s tier=%s valid=%d FW_VAR=%d"\n'
            '      % (len(seq), len(hdr), len(res), region, tier, 1 if _ok else 0, FW_VAR))')

    L = ['title = "Scenario synthesis (SCALE) — verbs the Zen way + sieve at scale"',
         f'note  = "OPS=FW_Permut, HEADERS=FW_Subsets, RES=FW_Combi(2), REGION/TIER=FW_Combi(1); '
         f'sieve forbids REGION.cost+TIER.cost>{thr}. total={total_combos(sz)}."',
         'args = ["mode=scenario_scale"]',
         '[[goals]]', 'key = "valid"', 'dir = "max"', '']
    L += _raw_slot("HEAD", "head", "FW_Combi(1)", [head])
    L += _raw_slot("OPS", "ops", "FW_Permut", [f'seq.append("{o}")' for o in ops])
    L += _raw_slot("HEADERS", "headers", "FW_Subsets", [f'hdr.add("{h}")' for h in hdrs])
    L += _raw_slot("RES", "res", "FW_Combi(2)", [f'res.append("{r}")' for r in ress])
    L += _raw_slot("REGION", "region", "FW_Combi(1)", [f'region = "r{i}"' for i in range(n_reg)])
    L += _raw_slot("TIER", "tier", "FW_Combi(1)", [f'tier = "t{i}"' for i in range(n_tier)])
    L += _raw_slot("TAIL", "tail", "FW_Combi(1)", [tail])

    # params: REGION/TIER values carry a numeric cost (= index). Key = the STRIPPED value string.
    for i in range(n_reg):
        L += ['[[params]]', 'sheet = "REGION"', f"value = 'region = \"r{i}\"'", f'cost = {i}']
    for i in range(n_tier):
        L += ['[[params]]', 'sheet = "TIER"', f"value = 'tier = \"t{i}\"'", f'cost = {i}']
    L += ['']
    # the forbidden bond (sieve): a formula over params
    L += ['[[constraints]]', 'id = "budget_bond"', 'sheets = ["REGION", "TIER"]',
          f'when = "REGION.cost + TIER.cost > {thr}"', 'gate = {}',
          f'desc = "forbid a region+tier whose combined cost exceeds {thr}"', '']
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "invalid operation order (destructive op before create)"', '']
    return "\n".join(L) + "\n"


def emit(dirpath: Path, preset: str):
    sz = PRESETS[preset]
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / f"scenario_{preset}.toml"
    p.write_text(build_toml(sz), encoding="utf-8")
    print(f"  spec -> {p}")
    print(f"  preset {preset}: total={total_combos(sz):,}  sieve removes={removed_groundtruth(sz):,} "
          f"(ground truth)  kept={total_combos(sz)-removed_groundtruth(sz):,}")
    # validate through the real generator
    spec = fg.load_spec(p)
    est = fg.estimate_core_combos(spec)
    ok = "MATCH" if est == total_combos(sz) else f"MISMATCH (est {est})"
    print(f"  fwgen estimate_core_combos = {est:,}  [{ok}]  | constraints parsed = {len(spec.constraints)}")
    return p


# ------------------------------- scale driver ------------------------------- #
def scale(presets: list[str]):
    import bundle_run as br
    _cfg, _ = _resolve_bundle_config()

    def psql_size(port, db, rel):
        out, _ = br.psql(port, db, f"select pg_size_pretty(pg_total_relation_size('\"{rel}\"'));")
        return out

    print("=== SIEVE SCALE DEMO — verbs the Zen way, sieve stressed 10^4 → 10^6 ===\n")
    rows = []
    for preset in presets:
        sz = PRESETS[preset]
        total, exp_removed = total_combos(sz), removed_groundtruth(sz)
        db = f"scaledemo_{total}"
        # STEP 14: no implicit /mnt/F auto-probe — scratch root comes from
        # BundleConfig (default /tmp/fw_work/<db>; override via scratch_root /
        # BUNDLE_SCRATCH_ROOT / --scratch-root, e.g. scratch_root=/mnt/F/fw_work).
        scratch = _cfg.scratch_for(db)
        scratch.mkdir(parents=True, exist_ok=True)
        spec_dir = scratch / "spec"
        emit(spec_dir, preset)
        spec = fg.load_spec(spec_dir / f"scenario_{preset}.toml")

        print(f"\n----- preset {preset}: {total:,} combos -----")
        t0 = time.time()
        xlsx = br.stage_gen(spec_dir, scratch)
        fw_final = br.stage_core(spec, xlsx, scratch, db, 5433, n_opt=0)
        t_core = time.time() - t0
        size_before = psql_size(5433, db, "fw_final")

        t1 = time.time()
        kept = br.stage_sieve(spec, scratch, db, 5433, fw_final)
        t_sieve = time.time() - t1

        removed = fw_final - kept
        integrity = "✓ EXACT" if (fw_final == total and removed == exp_removed and kept == total - exp_removed) \
            else f"✗ (fw_final={fw_final} removed={removed} exp_removed={exp_removed})"
        rows.append((preset, total, fw_final, removed, kept, t_core, t_sieve,
                     total / t_core if t_core else 0, fw_final / t_sieve if t_sieve else 0,
                     size_before, integrity))
        print(f"  integrity: {integrity}")
        print(f"  timing: Core {t_core:.1f}s ({total/max(t_core,1e-9):,.0f} rows/s) | "
              f"sieve {t_sieve:.1f}s ({fw_final/max(t_sieve,1e-9):,.0f} rows/s) | fw_final size {size_before}")

    print("\n" + "=" * 110)
    print(f"  {'preset':<7}{'total':>12}{'fw_final':>11}{'removed':>11}{'kept':>11}"
          f"{'Core s':>9}{'sieve s':>9}{'sieve rows/s':>14}{'fw_size':>10}  integrity")
    for r in rows:
        print(f"  {r[0]:<7}{r[1]:>12,}{r[2]:>11,}{r[3]:>11,}{r[4]:>11,}"
              f"{r[5]:>9.1f}{r[6]:>9.1f}{r[8]:>14,.0f}{r[9]:>10}  {r[10]}")
    print("=" * 110)
    print("  Core+Reader are author-proven to 1e9; this isolates the NEW layer — the constraint sieve —")
    print("  and shows it scans/deletes correctly and linearly into the 10^6 range. Bonds: REGION+TIER budget.")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "emit":
        emit(Path(sys.argv[2]), sys.argv[3])
    elif cmd == "scale":
        scale(sys.argv[2:] or ["s1e4", "s1e5", "s1e6"])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
