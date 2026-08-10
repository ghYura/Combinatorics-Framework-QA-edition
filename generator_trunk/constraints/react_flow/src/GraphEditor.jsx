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

import React, { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nid, graphToSidecar, parseNodeId } from "./graphspec.js";

// Default sheets (used if sheets.json is absent). Real sheets come from a spec via:
//   python3 ../graphspec.py --spec <spec> --sheets-json public/sheets.json
const DEFAULT_SHEETS = [
  ["A", ["a1", "a2"]],
  ["B", ["b1", "b2"]],
  ["C", ["c1", "c2", "c3"]],
];

function buildNodes(sheets) {
  const nodes = [];
  sheets.forEach(([sheet, vals], si) => {
    nodes.push({
      id: "col_" + sheet,
      position: { x: si * 220, y: -50 },
      data: { label: sheet },
      selectable: false,
      draggable: false,
      connectable: false,
      style: { border: "none", background: "transparent", fontWeight: 600 },
    });
    vals.forEach((v, vi) =>
      nodes.push({
        id: nid(sheet, v),
        position: { x: si * 220, y: vi * 70 },
        data: { label: v },
        style: { background: "#eef3ff", border: "1px solid #88a", borderRadius: 14, padding: 6 },
      }),
    );
  });
  return nodes;
}

export default function GraphEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState(buildNodes(DEFAULT_SHEETS));
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [src, setSrc] = useState("default demo sheets");

  // load sheets from a real spec at runtime (sheets.json), if present
  useEffect(() => {
    fetch("sheets.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no sheets.json"))))
      .then((sheets) => {
        setNodes(buildNodes(sheets));
        setSrc("sheets.json (" + sheets.length + " sheets from a real spec)");
      })
      .catch(() => {});
  }, [setNodes]);

  const onConnect = useCallback(
    (c) => {
      const a = parseNodeId(c.source);
      const b = parseNodeId(c.target);
      if (!a || !b) return;
      const [s1] = a;
      const [s2] = b;
      if (s1 === s2) return; // bonds are cross-sheet only
      setEdges((es) => addEdge({ ...c, label: "forbid", style: { stroke: "#d33", strokeWidth: 2.5 } }, es));
    },
    [setEdges],
  );

  const download = useCallback(() => {
    const sc = graphToSidecar(edges);
    const blob = new Blob([JSON.stringify(sc, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sidecar.json";
    a.click();
    URL.revokeObjectURL(url);
  }, [edges]);

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <div style={{ position: "absolute", zIndex: 5, padding: 8 }}>
        <button onClick={download}>Download sidecar.json</button>
        <span style={{ marginLeft: 10, color: "#666" }}>
          {edges.length} forbidden thread(s) · sheets: {src} — drag between nodes in different sheets
        </span>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
