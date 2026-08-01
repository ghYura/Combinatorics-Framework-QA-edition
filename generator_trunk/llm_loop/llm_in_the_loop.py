#!/usr/bin/env python3
r"""LLM-in-the-loop PoC — the original 'combinatorial QA test generation' purpose of the
Bundle, with the human's per-slot value enumeration replaced by an LLM.

    LLM PROPOSES  ── edge-case values per test slot
        │
    fwgen BUILDS  ── a dispersed workbook (each slot gets the verb that fits its role)
        │
    Core EXPLORES ── the full combinatorial product of the proposed values
        │
    Reader/Executor EXECUTE ── every reassembled program is compiled + run
        │
    FW_VAR VERDICT ── empirically decides which LLM-proposed combinations BREAK the SUT

So the LLM's creativity is grounded in real execution + combinatorial coverage: nothing
it suggests is trusted blindly — the run, not the model, finds the bugs.

Usage:  python3 llm_in_the_loop.py [auto|stub|ollama] [out_spec.toml]
Then run the emitted spec through the Bundle exactly like any other fwgen spec.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # make fwgen importable
import fwgen as fg                                                  # noqa: E402
from llm_provider import get_provider                              # noqa: E402
from bundle.config import resolve_config as _resolve_bundle_config  # noqa: E402

# --- System Under Test: a price-quote engine with classic edge-case bugs ----------
SUT = ("PriceQuote engine: base = unit*qty, then a discount, a tax percent and rounding "
       "are applied (the ORDER of those three is not fixed). Optional loyalty (extra 10% "
       "off) and coupon (flat -20) may apply. Invariants that MUST hold: total >= 0 (you "
       "never pay the customer) and total stays within a sane ceiling. Edge cases: a "
       "discount larger than the price, zero/negative quantity, an order of operations "
       "that drives the running total negative.")

FRAME_HEAD = '''public class Quote {
    public static int FW_VAR = 0;
    public static int FW_CUSTOM_VAR = 0;
    static long unit = 100, qty = 1, discount = 0, taxPct = 0, base = 0;
    static long applyDiscount(long b){ return b - discount; }
    static long applyTax(long b){ return b + b * taxPct / 100; }
    static long round10(long b){ return (b / 10) * 10; }
    public static void main(String[] args){
'''

FRAME_TAIL = '''        long total = base;
        long ceiling = unit * (qty < 0 ? -qty : qty) * 2 + 1000;
        boolean negative = total < 0;
        boolean absurd = total > ceiling;
        FW_VAR = (negative || absurd) ? 1 : 0;
        FW_CUSTOM_VAR = FW_VAR;
        System.out.println("FW_VAR=" + FW_VAR + " total=" + total + " qty=" + qty
                + " discount=" + discount + " taxPct=" + taxPct);
    }
}
'''

# value slots the LLM fills: (sheet, java-variable, role/context for the prompt)
VALUE_SLOTS = [
    ("QTY",      "qty",     "order line quantity in units"),
    ("DISCOUNT", "discount", "absolute money discount taken off the line"),
    ("TAX",      "taxPct",  "tax percent applied to the base"),
]


def main() -> int:
    provider = get_provider(sys.argv[1] if len(sys.argv) > 1 else "auto")
    # STEP 14: no implicit /mnt/F default — resolved via BundleConfig
    # (default /tmp/fw_work/llm_loop/...; override via scratch_root /
    # BUNDLE_SCRATCH_ROOT / --scratch-root).
    _cfg, _ = _resolve_bundle_config()
    out = Path(sys.argv[2] if len(sys.argv) > 2 else
               str(_cfg.scratch_for("llm_loop") / "specs/llm_quote.toml"))
    out.parent.mkdir(parents=True, exist_ok=True)
    k = 3

    print(f"\nSUT: {SUT}\n\nLLM proposing {k} edge-case values per input slot:")
    slots = [{"sheet": "FRAME", "key": "frame", "verb": "FW_Combi(1)", "raw": True,
              "values": [FRAME_HEAD]}]
    for sheet, var, ctx in VALUE_SLOTS:                       # LLM-proposed value slots (Combi(1))
        vals = provider.propose(sheet, var, SUT + " " + ctx, k)
        stmts = [f"        {var} = {v};\n" for v in vals]
        slots.append({"sheet": sheet, "key": var, "verb": "FW_Combi(1)", "raw": True,
                      "values": stmts})

    slots.append({"sheet": "COMPUTE", "key": "compute", "verb": "FW_Combi(1)", "raw": True,
                  "values": ["        base = unit * qty;\n"]})
    # the combinatorial RULES (order-sensitivity, optionality) — fixed here, but an LLM
    # could just as well propose the step set / the optional features.
    slots.append({"sheet": "OPS", "key": "ops", "verb": "FW_Permut", "raw": True, "values": [
        "        base = applyDiscount(base);\n",
        "        base = applyTax(base);\n",
        "        base = round10(base);\n"]})
    slots.append({"sheet": "FLAGS", "key": "flags", "verb": "FW_Subsets", "raw": True, "values": [
        "        base = base - base / 10;\n",                 # loyalty: extra 10% off
        "        base = base - 20;\n"]})                      # coupon: flat -20
    slots.append({"sheet": "VERDICT", "key": "verdict", "verb": "FW_Combi(1)", "raw": True,
                  "values": [FRAME_TAIL]})

    spec = fg.parse_spec({"title": "LLM-in-the-loop — price-quote edge-case fuzz",
                          "note": "LLM proposes per-slot edge cases; Core×Reader×Executor "
                                  "explore+run every combination; FW_VAR validates empirically.",
                          "args": ["mode=llm_quote"], "goals": ["bugs_found"],
                          "custom_vars": [{"code": 2, "msg": "invariant broken (total<0 or absurd)"}],
                          "slots": slots}, "llm_quote")

    # write the dispersed spec + build the Core workbook in one shot
    from fwgen_cli import generate_one  # reuse the standard generator
    out.write_text(_to_toml(spec), encoding="utf-8")
    est = fg.estimate_core_combos(spec)
    print(f"\nDispersed spec → {out}")
    print(f"  slots: " + ", ".join(f"{s.sheet}({len(s.values)})·{s.verb}" for s in spec.slots))
    print(f"  predicted Core fw_final rows ≈ {est}")
    rep = fg.handshake_report(spec)
    print(f"  Results table: {rep['n_columns']} cols ({rep['n_combos']} combos) → {rep['mode']} mode; "
          f"fwVar.shift={rep['fwvar_shift']}")
    print(f"\nNext: fwgen_cli.py gen --specs {out.parent} --out <wb> ; then Core→Reader→Executor.")
    return 0


def _to_toml(spec: fg.Spec) -> str:
    """Serialise the dispersed (raw-slot) spec to a code-friendly TOML."""
    L = [f'title = "{spec.title}"', f'note  = "{spec.note}"',
         "goals = [" + ", ".join(f'"{g.key}"' for g in spec.goals) + "]",
         "args  = [" + ", ".join(f'"{a}"' for a in spec.args) + "]", ""]
    for s in spec.slots:
        L += [f'[[slots]]', f'sheet = "{s.sheet}"', f'key   = "{s.key}"',
              f'verb  = "{s.verb}"', "raw   = true", "values = ["]
        for v in s.values:
            body = v if v.startswith("\n") else "\n" + v
            if not body.endswith("\n"):
                body += "\n"
            L.append("'''" + body + "''',")
        L += ["]", ""]
    for c in spec.custom_vars:
        L += ["[[custom_vars]]", f"code = {c.code}", f'msg  = "{c.msg}"', ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
