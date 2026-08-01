// blocks.js — custom Blockly blocks + Python-generator hooks for `when`-predicate constraints,
// plus the workspace-code → sidecar compiler. Pure helpers (fwParamCode/gateOf/toSidecar) are
// unit-tested headlessly; standard math/logic blocks use Blockly's stock Python generator, so a
// formula like  A.charge * C.charge > 0  comes out as a sieve-evaluable `when` string. The sheet
// dropdowns are populated from a REAL spec at runtime (sheets.json) — see main.js.

export const DEFAULT_SHEETS = ["A", "B", "C"]; // fallback if sheets.json is absent

export function fwParamCode(block) {
  return block.getFieldValue("SHEET") + "." + block.getFieldValue("PARAM");
}

export function gateOf(g) {
  return g === "adjacent" ? { adjacent: true } : g === "within2" ? { within: 2 } : {};
}

export function defineFwBlocks(Blockly, gen, Order, sheetNames = DEFAULT_SHEETS) {
  const opts = sheetNames.map((s) => [s, s]);
  Blockly.common.defineBlocksWithJsonArray([
    {
      type: "fw_param",
      message0: "%1 . %2",
      args0: [
        { type: "field_dropdown", name: "SHEET", options: opts },
        { type: "field_input", name: "PARAM", text: "charge" },
      ],
      output: "Number",
      colour: 230,
      tooltip: "a value's parameter, e.g. A.charge",
    },
    {
      type: "fw_when",
      message0: "forbid %1 x %2 , gate %3 , when %4",
      args0: [
        { type: "field_dropdown", name: "SHEETA", options: opts },
        { type: "field_dropdown", name: "SHEETB", options: opts },
        {
          type: "field_dropdown",
          name: "GATE",
          options: [["any", "any"], ["adjacent", "adjacent"], ["within 2", "within2"]],
        },
        { type: "input_value", name: "EXPR", check: "Boolean" },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: 20,
      tooltip: "forbid this sheet-pair when the formula holds",
    },
  ]);

  gen.forBlock["fw_param"] = (block) => [fwParamCode(block), Order.MEMBER];
  gen.forBlock["fw_when"] = (block) => {
    const expr = gen.valueToCode(block, "EXPR", Order.NONE) || "True";
    return (
      JSON.stringify({
        sheets: [block.getFieldValue("SHEETA"), block.getFieldValue("SHEETB")],
        when: expr,
        gate: gateOf(block.getFieldValue("GATE")),
        polarity: "forbid",
      }) + "\n"
    );
  };
}

// workspace code (one JSON object per fw_when, newline-separated) → constraint sidecar
export function toSidecar(code) {
  const cons = [];
  let i = 0;
  for (const line of String(code).split("\n")) {
    const s = line.trim();
    if (!s) continue;
    try {
      const c = JSON.parse(s);
      if (!Array.isArray(c.sheets) || new Set(c.sheets).size < 2) continue;
      cons.push({
        id: "when" + i++ + "_" + c.sheets.join("_"),
        polarity: c.polarity,
        sheets: c.sheets,
        when: c.when,
        gate: c.gate,
        desc: c.polarity + " " + c.sheets.join("/") + " when " + c.when,
      });
    } catch (e) {
      /* skip non-JSON lines */
    }
  }
  return { version: 1, params: {}, constraints: cons };
}
