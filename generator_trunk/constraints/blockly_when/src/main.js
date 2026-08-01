import * as Blockly from "blockly";
import { pythonGenerator, Order } from "blockly/python";
import { defineFwBlocks, toSidecar, DEFAULT_SHEETS } from "./blocks.js";

// load sheet names from a REAL spec at runtime (sheets.json), else fall back to the demo sheets
function loadSheetNames() {
  return fetch("sheets.json")
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no sheets.json"))))
    .then((sheets) => sheets.map((s) => s[0]))
    .catch(() => DEFAULT_SHEETS);
}

const toolbox = {
  kind: "categoryToolbox",
  contents: [
    { kind: "category", name: "Constraint", colour: "20", contents: [{ kind: "block", type: "fw_when" }] },
    { kind: "category", name: "Param", colour: "230", contents: [{ kind: "block", type: "fw_param" }] },
    {
      kind: "category", name: "Math", colour: "230",
      contents: [
        { kind: "block", type: "math_number" },
        { kind: "block", type: "math_arithmetic" },
        { kind: "block", type: "math_single" },
      ],
    },
    {
      kind: "category", name: "Logic", colour: "210",
      contents: [
        { kind: "block", type: "logic_compare" },
        { kind: "block", type: "logic_operation" },
        { kind: "block", type: "logic_negate" },
        { kind: "block", type: "logic_boolean" },
      ],
    },
  ],
};

loadSheetNames().then((sheetNames) => {
  defineFwBlocks(Blockly, pythonGenerator, Order, sheetNames);
  const ws = Blockly.inject("ws", { toolbox });
  document.getElementById("sheets").textContent = "sheets: " + sheetNames.join(", ");
  let last = { version: 1, params: {}, constraints: [] };

  document.getElementById("gen").onclick = () => {
    const code = pythonGenerator.workspaceToCode(ws);
    last = toSidecar(code);
    document.getElementById("out").textContent = JSON.stringify(last, null, 2);
    document.getElementById("dl").disabled = last.constraints.length === 0;
  };

  document.getElementById("dl").onclick = () => {
    const b = new Blob([JSON.stringify(last, null, 2)], { type: "application/json" });
    const u = URL.createObjectURL(b);
    const a = document.createElement("a");
    a.href = u;
    a.download = "sidecar.json";
    a.click();
    URL.revokeObjectURL(u);
  };
});
