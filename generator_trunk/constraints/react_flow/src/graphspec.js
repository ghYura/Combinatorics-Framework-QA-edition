// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

// graphspec.js — the graph→sidecar compile model, mirroring the VERIFIED Python
// constraints/graphspec.py. Node id encodes [sheet, value] as compact JSON; an edge between two
// value-nodes = a forbidden bond. Edges are grouped by unordered sheet-pair into one constraint
// each — the exact sidecar that constraints/sieve.py + `bundle_run --sieve` consume.

export const nid = (sheet, value) => JSON.stringify([sheet, value]);

export function parseNodeId(id) {
  try {
    const parsed = JSON.parse(id);
    return Array.isArray(parsed) && parsed.length === 2 ? parsed : null;
  } catch (_) {
    return null;
  }
}

export function graphToSidecar(edges) {
  const groups = {};
  for (const e of edges) {
    const a = parseNodeId(e.source);
    const b = parseNodeId(e.target);
    if (!a || !b) continue;
    const [s1, v1] = a;
    const [s2, v2] = b;
    if (s1 === s2) continue; // a bond is between two DIFFERENT sheets
    const ps = [s1, s2].sort();
    const gk = ps.join("");
    if (!groups[gk]) groups[gk] = { sheets: ps, pairs: [] };
    const o = {};
    o[s1] = v1;
    o[s2] = v2;
    groups[gk].pairs.push(o);
  }
  const constraints = Object.values(groups).map((g, i) => ({
    id: "bond" + i + "_" + g.sheets[0] + "_" + g.sheets[1],
    polarity: "forbid",
    sheets: g.sheets,
    pairs: g.pairs,
    gate: {},
    desc: g.pairs.length + " forbid " + g.sheets[0] + "x" + g.sheets[1] + " bond(s)",
  }));
  return { version: 1, params: {}, constraints };
}
