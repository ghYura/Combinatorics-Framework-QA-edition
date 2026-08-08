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

r"""esoteric_life — materialises Model proposition #5 (Academic & Esoteric Software
Research) as a Combinatorics-Framework use-case.

> "people are constantly looking for minimal programs for Turing machines, exploring
>  cellular automata, or writing Quines ... a ready-made digital playground for simulating
>  the artificial life of code."   — Model AI

Cellular automata are the cleanest fit: a Conway's-Game-of-Life SEED *is* a combinatorial
object — a subset of the cells of a bounding box.  The combinatorics breeds every seed; the
harness runs the automaton and the Analyzer optimises the dynamics.

Decomposition -> FW_ rule:
  | piece     | variants                  | rule        | what it breeds
  | SEED cells| each of the 9 cells of a  | FW_Subsets  | the full 2^9 = 512 powerset of
  |           | 3x3 box: live / dead      |             | starting patterns
  (FW_Combi(5) would breed exactly the 126 five-cell "pentomino" seeds instead.)

Each seed is run on a toroidal grid; cycle detection (translation-invariant state hashing)
classifies it and measures:
  lifespan (gens to stabilise -> METHUSELAHS), period, displacement (-> SPACESHIPS/gliders),
  max_population, final_population.
Verdict FW_VAR=0 = "interesting" (survives / moves / oscillates).  Analyzer goals
lifespan:max + displacement:max => the engine DISCOVERS the glider and the longest-lived
methuselah by exhaustive search — no human seeded them.

Fully offline, stdlib-only, deterministic.  `emit_toml()` writes the equivalent fwgen spec.

  python3 esoteric_life.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

N = 64           # toroidal grid size
T = 250          # generation cap
BOX = [(r, c) for r in range(3) for c in range(3)]   # the 3x3 seed bounding box


def step(live: frozenset, n: int = N) -> frozenset:
    """One Conway B3/S23 generation on an n x n torus."""
    from collections import Counter
    nb = Counter()
    for (r, c) in live:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    nb[((r + dr) % n, (c + dc) % n)] += 1
    return frozenset(cell for cell, k in nb.items()
                     if k == 3 or (k == 2 and cell in live))


def normalize(live: frozenset):
    """Translate the pattern so its bounding-box corner sits at (0,0).
    Returns (normalised_frozenset, origin_offset) — equal normalised sets at different
    origins == the SAME shape translated (a moving spaceship)."""
    if not live:
        return frozenset(), (0, 0)
    mr = min(r for r, _ in live)
    mc = min(c for _, c in live)
    return frozenset((r - mr, c - mc) for r, c in live), (mr, mc)


def _min_image(d: int, n: int = N) -> int:
    d %= n
    return d - n if d > n // 2 else d


def simulate(seed: frozenset):
    """Run until a (translation-invariant) cycle is found or T gens elapse.
    Returns metrics dict."""
    live = seed
    history = {}                                       # normhash -> (gen, origin)
    max_pop = len(live)
    for gen in range(T + 1):
        max_pop = max(max_pop, len(live))
        if not live:
            return dict(klass="extinct", lifespan=gen, period=0, displacement=0,
                        max_pop=max_pop, final_pop=0)
        norm, origin = normalize(live)
        if norm in history:
            t0, o0 = history[norm]
            period = gen - t0
            dr, dc = _min_image(origin[0] - o0[0]), _min_image(origin[1] - o0[1])
            disp = max(abs(dr), abs(dc))
            if disp > 0:
                klass = "spaceship"
            elif period == 1:
                klass = "still_life"
            else:
                klass = "oscillator"
            return dict(klass=klass, lifespan=t0, period=period, displacement=disp,
                        max_pop=max_pop, final_pop=len(live))
        history[norm] = (gen, origin)
        live = step(live)
    return dict(klass="methuselah", lifespan=T, period=0, displacement=0,
                max_pop=max_pop, final_pop=len(live))   # no cycle within T (censored)


def seeds():
    """FW_Subsets over the 9 box cells = every starting pattern, centred on the grid."""
    off = N // 2 - 1
    for r in range(len(BOX) + 1):
        for subset in itertools.combinations(BOX, r):
            yield subset, frozenset((rr + off, cc + off) for rr, cc in subset)


# ------------------------------- emit fwgen spec ------------------------------ #
def _to_toml() -> str:
    L = ['title = "Esoteric #5 — Game of Life seed search (discover gliders & methuselahs)"',
         'note  = "Each of the 3 ROWS of the 3x3 box is an FW_Subsets slot over its 3 cells, so the '
         'product 2^3 x 2^3 x 2^3 = 512 breeds every seed (3 combos columns keep the positional '
         'FW_VAR encoding clean). Each seed is run on a torus and classified (still/oscillator/'
         'spaceship/methuselah/extinct); Analyzer lifespan:max + displacement:max discovers the '
         'glider and the longest-lived seed. FW_Combi(5) would breed the 126 pentominoes instead."',
         f'args  = ["grid={N}x{N}_torus", "generations={T}", "rule=B3/S23"]',
         '[[goals]]', 'key = "lifespan"', 'dir = "max"',
         '[[goals]]', 'key = "displacement"', 'dir = "max"',
         '[[goals]]', 'key = "max_population"', 'dir = "max"', ""]
    for r in range(3):                                  # one FW_Subsets slot per box row
        cells = ", ".join(f'"({r},{c})"' for c in range(3))
        L += ['[[slots]]', f'sheet = "ROW{r}"', f'key   = "row{r}"', 'verb  = "FW_Subsets"',
              f'values = [{cells}]', ""]
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "seed went extinct"',
          '[[custom_vars]]', 'code = 3', 'msg  = "seed froze into a boring still-life"', ""]
    return "\n".join(L) + "\n"


def emit_toml(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(), encoding="utf-8")
    print(f"  fwgen spec -> {path}  (full Core product = {2 ** len(BOX)} seeds)")


# ---- run-ready spec (materialized): 512 self-classifying seeds for the full Bundle ---- #
# HEAD embeds the Life engine; the SEED slot carries 512 explicit `S = frozenset({...})` seeds;
# TAIL simulates, sets FW_VAR (0 = survives), prints the K=V the Analyzer mines for the glider
# (displacement:max) and the methuselah (lifespan:max).
RUN_TAIL = '''
m = simulate(S)
FW_VAR = 0 if m["final_pop"] > 0 else 2
print("app=life klass=%s lifespan=%d period=%d displacement=%d max_population=%d FW_VAR=%d"
      % (m["klass"], m["lifespan"], m["period"], m["displacement"], m["max_pop"], FW_VAR))
'''


def _run_head(run_T: int) -> str:
    import inspect as _i
    return (f"N = {N}\nT = {run_T}\n"
            + _i.getsource(step) + _i.getsource(normalize)
            + _i.getsource(_min_image) + _i.getsource(simulate))


def emit_run_toml(path: Path, run_T: int = 150):
    def raw_slot(sheet, frags):
        L = ['[[slots]]', f'sheet = "{sheet}"', f'key   = "{sheet.lower()}"',
             'verb  = "FW_Combi(1)"', 'raw   = true', 'values = [']
        for f in frags:
            body = f if f.startswith("\n") else "\n" + f
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        return L + [']', '']
    off = N // 2 - 1
    seeds_src = []
    for r in range(len(BOX) + 1):
        for subset in itertools.combinations(BOX, r):
            cells = ", ".join(f"({rr + off}, {cc + off})" for rr, cc in subset)
            seeds_src.append(f"S = frozenset({{{cells}}})\n" if subset else "S = frozenset()\n")
    L = ['title = "Esoteric #5 (RUN) — Game of Life seed search, full Bundle"',
         'note  = "512 self-classifying seeds; Analyzer displacement:max finds the glider, '
         'lifespan:max finds the methuselah."',
         'args = ["mode=life_run"]',
         '[[goals]]', 'key = "displacement"', 'dir = "max"',
         '[[goals]]', 'key = "lifespan"', 'dir = "max"',
         '[[goals]]', 'key = "max_population"', 'dir = "max"', '']
    L += raw_slot("HEAD", [_run_head(run_T)])
    L += raw_slot("SEED", seeds_src)
    L += raw_slot("TAIL", [RUN_TAIL])
    L += ['[[custom_vars]]', 'code = 2', 'msg  = "seed went extinct"', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  RUN spec -> {path}  ({len(seeds_src)} self-classifying seeds for bundle_run.py)")


def main():
    if "--run" in sys.argv[1:]:
        a = [x for x in sys.argv[1:] if not x.startswith("--")]
        emit_run_toml(Path(a[0]) if a else
                      Path(__file__).resolve().parent / "run" / "esoteric_life" / "esoteric_life_run.toml")
        return
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               str(Path(__file__).resolve().parent / "specs" / "esoteric_life.toml"))
    print("=== Esoteric research (Model #5): exhaustive Game-of-Life seed search ===")
    print(f"    all 2^9 = 512 seeds in a 3x3 box, on a {N}x{N} torus, {T} generations\n")

    classes = {}
    ships, methus = [], []
    for subset, seed in seeds():
        m = simulate(seed)
        classes[m["klass"]] = classes.get(m["klass"], 0) + 1
        if m["klass"] == "spaceship":
            ships.append((subset, m))
        if m["klass"] == "methuselah" or (m["lifespan"] >= 20 and m["klass"] != "spaceship"):
            methus.append((subset, m))

    print("  classification of all 512 seeds:")
    for k in ("extinct", "still_life", "oscillator", "spaceship", "methuselah"):
        print(f"    {k:<12}: {classes.get(k, 0)}")

    if ships:
        s = min(ships, key=lambda x: len(x[0]))        # the smallest spaceship = the glider
        sub, m = s
        print(f"\n  *** DISCOVERED A SPACESHIP (the glider) — {len(sub)} live cells ***")
        print(f"      seed cells (in 3x3 box) = {list(sub)}")
        print(f"      period={m['period']} displacement={m['displacement']} (moves across the grid)")
        print(f"      K=V -> klass=spaceship lifespan={m['lifespan']} period={m['period']} "
              f"displacement={m['displacement']} max_population={m['max_pop']}")

    if methus:
        sub, m = max(methus, key=lambda x: (x[1]["lifespan"], x[1]["max_pop"]))
        tag = "(censored at T)" if m["klass"] == "methuselah" else ""
        print(f"\n  *** LONGEST-LIVED seed (methuselah) — {len(sub)} cells ***  {tag}")
        print(f"      seed cells = {list(sub)}   lifespan={m['lifespan']} gens, peaked at "
              f"{m['max_pop']} cells")
        print(f"      K=V -> klass={m['klass']} lifespan={m['lifespan']} max_population={m['max_pop']}")

    print("\n  -> the engine BRED 512 universes and the verdict found the glider & the methuselah —")
    print("     'artificial life of code' by exhaustive combinatorial search, not by hand.\n")
    emit_toml(out)


if __name__ == "__main__":
    main()
