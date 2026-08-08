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

r"""LLM-in-the-loop + MULTIPLE FW_Optional — the "Птичка" scenario.

System Under Test: a tiny command/intent parser. A command is ACTION TARGET AMOUNT.
Real life sprinkles OPTIONAL, valid-but-unexpected tokens (interjections / slang /
"птичка") at arbitrary positions; a robust parser must skip them. This parser filters a
small known-filler set, then reads positionally — so an UNKNOWN surprise shifts the
positions and the command is mis-parsed.

The LLM proposes BOTH the command tokens AND the surprise tokens. Each surprise is a
separate FW_Optional slot at a different position, so the Core manufactures the WHOLE
space: clean · surprise-after-action · surprise-after-target · surprise-at-end · and
every combination of those. Execution (FW_VAR) then maps exactly which surprise × which
position breaks the parser — not the model's guess, the run.

Output: a dispersed fwgen spec ready for Core→Reader(opt)→Executor.
Usage:  python3 cmd_parser_scenario.py [auto|stub|ollama] [out_spec.toml]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fwgen as fg                       # noqa: E402
from llm_provider import get_provider    # noqa: E402
from bundle.config import resolve_config as _resolve_bundle_config  # noqa: E402

SUT = ("A command parser: input is a token stream meant to be ACTION TARGET AMOUNT. "
       "Known filler words {please, pls, kindly} are skipped; everything else is read "
       "positionally. Unexpected interjections/slang inserted between the real tokens "
       "shift the positions and corrupt the parse.")

FRAME = '''public class Cmd {
    public static int FW_VAR = 0;
    public static int FW_CUSTOM_VAR = 0;
    static java.util.List<String> toks = new java.util.ArrayList<>();
    static java.util.Set<String> FILLERS = new java.util.HashSet<>(java.util.Arrays.asList("please", "pls", "kindly"));
    static String wantAction = "", wantTarget = "", wantAmount = "";
    static String[] parse(){
        java.util.List<String> clean = new java.util.ArrayList<>();
        for (String t : toks) if (!FILLERS.contains(t)) clean.add(t);
        String a  = clean.size() > 0 ? clean.get(0) : "";
        String tg = clean.size() > 1 ? clean.get(1) : "";
        String am = clean.size() > 2 ? clean.get(2) : "";
        return new String[]{a, tg, am};
    }
    public static void main(String[] args){
'''

VERDICT = '''        String[] got = parse();
        boolean ok = got[0].equals(wantAction) && got[1].equals(wantTarget) && got[2].equals(wantAmount);
        FW_VAR = ok ? 0 : 1;
        FW_CUSTOM_VAR = FW_VAR;
        System.out.println("FW_VAR=" + FW_VAR + " want=[" + wantAction + "|" + wantTarget + "|" + wantAmount
                + "] got=" + java.util.Arrays.toString(got) + " toks=" + toks);
    }
}
'''


def q(v: str) -> str:
    return '"' + v.strip().strip('"') + '"'


def main() -> int:
    prov = get_provider(sys.argv[1] if len(sys.argv) > 1 else "auto")
    # STEP 14: no implicit /mnt/F default — resolved via BundleConfig
    # (default /tmp/fw_work/llm_loop/...; override via scratch_root /
    # BUNDLE_SCRATCH_ROOT / --scratch-root).
    _cfg, _ = _resolve_bundle_config()
    out = Path(sys.argv[2] if len(sys.argv) > 2 else
               str(_cfg.scratch_for("llm_loop") / "specs_parser/cmd_parser.toml"))
    out.parent.mkdir(parents=True, exist_ok=True)
    k = 2

    print(f"\nSUT: command parser robust to optional surprises.\nLLM proposing tokens:")
    av = prov.propose("ACTION", "action verb", SUT, k)
    tv = prov.propose("TARGET", "target object", SUT, k)
    mv = prov.propose("AMOUNT", "amount value", SUT, k)
    s1 = prov.propose("SURPRISE1", "surprise interjection slang", SUT, k)
    s2 = prov.propose("SURPRISE2", "surprise interjection slang", SUT, k)
    s3 = prov.propose("SURPRISE3", "surprise interjection slang", SUT, k)

    def val_slot(sheet, var, vals):
        return {"sheet": sheet, "key": sheet.lower(), "verb": "FW_Combi(1)", "raw": True,
                "values": [f"        {var} = {q(v)}; toks.add({q(v)});\n" for v in vals]}

    def opt_slot(sheet, vals):              # an FW_Optional 'surprise' at this position
        return {"sheet": sheet, "key": sheet.lower(), "verb": "FW_Combi(1)",
                "flags": ["FW_Optional"], "raw": True,
                "values": [f"        toks.add({q(v)});\n" for v in vals]}

    slots = [
        {"sheet": "FRAME", "key": "frame", "verb": "FW_Combi(1)", "raw": True, "values": [FRAME]},
        val_slot("ACTION", "wantAction", av),
        opt_slot("SURPRISE1", s1),          # after ACTION
        val_slot("TARGET", "wantTarget", tv),
        opt_slot("SURPRISE2", s2),          # after TARGET
        val_slot("AMOUNT", "wantAmount", mv),
        opt_slot("SURPRISE3", s3),          # at the end
        {"sheet": "VERDICT", "key": "verdict", "verb": "FW_Combi(1)", "raw": True, "values": [VERDICT]},
    ]
    spec = fg.parse_spec({"title": "LLM-in-the-loop — command parser vs multiple optional surprises",
                          "note": "3 FW_Optional surprises at different positions; LLM proposes tokens; "
                                  "FW_VAR=1 when an unexpected token shifts the parse.",
                          "args": ["mode=cmd_parser"], "goals": ["bugs_found"],
                          "custom_vars": [{"code": 2, "msg": "parse corrupted by an optional surprise"}],
                          "slots": slots}, "cmd_parser")
    out.write_text(_to_toml(spec), encoding="utf-8")

    n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
    print(f"\nDispersed spec → {out}")
    print(f"  slots: " + ", ".join(f"{s.sheet}({len(s.values)})"
                                   + ("·OPT" if "FW_Optional" in s.flags else "") for s in spec.slots))
    print(f"  mandatory fw_final ≈ {fg.estimate_core_combos(spec)} ; {n_opt} FW_Optional surprise dimensions")
    print(f"  → Core builds fw_final + fw_opt1..fw_opt{n_opt} (clean / 1-surprise / 2 / all); "
          f"Reader needs isOptCSVList=1..{n_opt}, processIsOpt=true, processBothFinalAndOpt=true.")
    return 0


def _to_toml(spec: fg.Spec) -> str:
    L = [f'title = "{spec.title}"', f'note  = "{spec.note}"',
         "goals = [" + ", ".join(f'"{g.key}"' for g in spec.goals) + "]",
         "args  = [" + ", ".join(f'"{a}"' for a in spec.args) + "]", ""]
    for s in spec.slots:
        L += ["[[slots]]", f'sheet = "{s.sheet}"', f'key   = "{s.key}"', f'verb  = "{s.verb}"']
        if s.flags:
            L.append("flags = [" + ", ".join(f'"{f}"' for f in s.flags) + "]")
        L += ["raw   = true", "values = ["]
        for v in s.values:
            body = v if v.startswith("\n") else "\n" + v
            L.append("'''" + (body if body.endswith("\n") else body + "\n") + "''',")
        L += ["]", ""]
    for c in spec.custom_vars:
        L += ["[[custom_vars]]", f"code = {c.code}", f'msg  = "{c.msg}"', ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
