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

"""STEP 37 — FW_Seq dependency graph artifact.

The Core's FW_Seq is a dataflow: each slot produces a combination-RESULT table,
and the second-order joiners (brace ``FW_(...)``, ``FW_Cartes``, ``FW_Separator``,
``FW_Group``) consume/rewrite those prior results. That flow is invisible in the
flat slot list, so this module makes it explicit for an author/reviewer:

  * a graph model — slot nodes + brace nodes, with excluded/optional/heading/group
    annotations and brace/group/cartes/separator dependency edges;
  * two serializations — JSON (`to_json`) and Graphviz DOT text (`to_dot`);
  * structural detection — missing operand, dependency cycle, consumed-result
    ambiguity, and unreachable/unused advanced (excluded-but-never-joined) nodes;
  * a stable `graph_hash` recorded in `plan.json`.

No visual GUI — DOT text is the rendering contract.

Edges are oriented dependent -> dependency ("X is computed FROM Y"):
  - cartes/separator: a slot depends on the operand sheet it weaves in;
  - brace_operand:   a brace depends on the prior RESULT table of E1/E2 (the join);
  - brace_ref:       a brace references start/rel/end/sep sheets;
  - produces:        the target sheet's result is produced BY the brace.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import fwgen as fg


# severity levels for a detected issue
ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str                       # "slot" | "brace"
    attrs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    src: str
    dst: str
    kind: str                       # cartes | separator | brace_operand | brace_ref | produces | seq_operand


@dataclass(frozen=True)
class GraphIssue:
    level: str                      # ERROR | WARNING
    code: str                       # missing_operand | cycle | consumed_result_ambiguity | unused_advanced_node
    message: str
    nodes: tuple = ()               # the node id(s) the issue concerns


@dataclass
class FwSeqGraph:
    nodes: dict
    edges: list

    # -- serializations ----------------------------------------------------- #
    def to_json(self) -> dict:
        """Canonical (sorted) JSON projection — the basis of `graph_hash`."""
        return {
            "nodes": [
                {"id": n.id, "kind": n.kind, "attrs": n.attrs}
                for n in sorted(self.nodes.values(), key=lambda n: n.id)
            ],
            "edges": [
                {"src": e.src, "dst": e.dst, "kind": e.kind}
                for e in sorted(self.edges, key=lambda e: (e.src, e.dst, e.kind))
            ],
        }

    def to_dot(self) -> str:
        """Graphviz DOT text (deterministic node/edge order)."""
        lines = ["digraph fwseq {", "  rankdir=LR;"]
        for n in sorted(self.nodes.values(), key=lambda n: n.id):
            tags = []
            if n.attrs.get("excluded"):
                tags.append("excluded")
            if n.attrs.get("optional"):
                tags.append("optional")
            if n.attrs.get("heading"):
                tags.append("heading")
            if n.attrs.get("group"):
                tags.append("group")
            if n.attrs.get("is_join_result"):
                tags.append("join-result")
            shape = "box" if n.kind == "brace" else "ellipse"
            label = n.id + (("\\n[" + ",".join(tags) + "]") if tags else "")
            lines.append(f'  "{n.id}" [shape={shape}, label="{label}"];')
        for e in sorted(self.edges, key=lambda e: (e.src, e.dst, e.kind)):
            lines.append(f'  "{e.src}" -> "{e.dst}" [label="{e.kind}"];')
        lines.append("}")
        return "\n".join(lines) + "\n"

    def graph_hash(self) -> str:
        """Stable sha256 over the canonical JSON — recorded in plan.json."""
        blob = json.dumps(self.to_json(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- detection ---------------------------------------------------------- #
    def validate(self) -> list:
        """Return all structural issues (errors + warnings), in a stable order."""
        issues: list = []
        issues += self._missing_operands()
        issues += self._cycles()
        issues += self._consumed_result_ambiguity()
        issues += self._unused_advanced_nodes()
        return issues

    def errors(self) -> list:
        return [i for i in self.validate() if i.level == ERROR]

    def _missing_operands(self) -> list:
        out = []
        for e in sorted(self.edges, key=lambda e: (e.src, e.dst, e.kind)):
            if e.dst not in self.nodes:
                out.append(GraphIssue(ERROR, "missing_operand",
                                      f"edge {e.src} --{e.kind}--> {e.dst!r}: operand sheet "
                                      f"{e.dst!r} is not a declared node", (e.src, e.dst)))
            if e.src not in self.nodes:
                out.append(GraphIssue(ERROR, "missing_operand",
                                      f"edge source {e.src!r} (--{e.kind}--> {e.dst}) is not a "
                                      f"declared node", (e.src, e.dst)))
        return out

    def _cycles(self) -> list:
        adj: dict = {nid: [] for nid in self.nodes}
        for e in self.edges:
            if e.src in adj and e.dst in self.nodes:
                adj[e.src].append(e.dst)
        WHITE, GREY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in self.nodes}
        found: list = []

        def dfs(u: str, stack: list) -> None:
            color[u] = GREY
            stack.append(u)
            for v in sorted(adj[u]):
                if color[v] == GREY:                      # back-edge -> cycle
                    cyc = stack[stack.index(v):] + [v]
                    found.append(tuple(cyc))
                elif color[v] == WHITE:
                    dfs(v, stack)
            stack.pop()
            color[u] = BLACK

        for nid in sorted(self.nodes):
            if color[nid] == WHITE:
                dfs(nid, [])
        # de-dup cycles by their normalized node set
        seen = set()
        out = []
        for cyc in found:
            key = frozenset(cyc)
            if key in seen:
                continue
            seen.add(key)
            out.append(GraphIssue(ERROR, "cycle",
                                  f"dependency cycle: {' -> '.join(cyc)}", tuple(dict.fromkeys(cyc))))
        return out

    def _consumed_result_ambiguity(self) -> list:
        out = []
        # how many braces consume each slot's RESULT table as an operand
        consumers: dict = {}
        for e in self.edges:
            if e.kind in {"brace_operand", "brace_nested_operand"}:
                consumers.setdefault(e.dst, []).append(e.src)
        for slot, braces in sorted(consumers.items()):
            if len(braces) > 1:
                out.append(GraphIssue(ERROR, "consumed_result_ambiguity",
                                      f"result of {slot!r} is consumed by {len(braces)} braces "
                                      f"({', '.join(sorted(braces))}); a brace operand result is "
                                      f"consumed-and-cleaned, so it cannot feed two joins", (slot,)))
            node = self.nodes.get(slot)
            nested = any(
                edge.dst == slot and edge.kind == "brace_nested_operand"
                for edge in self.edges
            )
            if node is not None and not nested and not node.attrs.get("excluded"):
                out.append(GraphIssue(ERROR, "consumed_result_ambiguity",
                                      f"brace operand {slot!r} is consumed as a prior result but is "
                                      f"not FW_Exclude'd — it stays an independent axis AND is joined, "
                                      f"so which table feeds the brace is ambiguous", (slot,)))
        return out

    def _unused_advanced_nodes(self) -> list:
        out = []
        consumed = {
            e.dst
            for e in self.edges
            if e.kind in {"brace_operand", "brace_nested_operand"}
        }
        for nid, node in sorted(self.nodes.items()):
            if node.kind == "slot" and node.attrs.get("excluded") and nid not in consumed:
                out.append(GraphIssue(WARNING, "unused_advanced_node",
                                      f"slot {nid!r} is FW_Exclude'd (set aside from the cartesian) "
                                      f"but never consumed by a brace operand — it is unreachable "
                                      f"and contributes nothing", (nid,)))
        return out


# --------------------------------------------------------------------------- #
def _brace_fields(expr: str) -> Optional[list]:
    """Split a brace ``FW_(...)`` into its 9 fields, or None if not a brace."""
    first = fg._first_line(expr)
    if not fg._BRACE_RE.fullmatch(first):
        return None
    inner = first[first.index("(") + 1:first.rindex(")")]
    return inner.split(",")


def build_graph(spec: "fg.Spec") -> FwSeqGraph:
    """Build the FW_Seq dependency graph for a parsed `spec`."""
    nodes: dict = {}
    edges: list = []

    def slot_node(s) -> None:
        nodes[s.sheet] = GraphNode(s.sheet, "slot", {
            "verb": s.verb,
            "n": len(s.values),
            "optional": "FW_Optional" in s.flags,
            "excluded": "FW_Exclude" in s.flags,
            "heading": "FW_Heading" in s.flags,
            "group": bool(s.group_replace),
            "separator": s.separator or None,
        })

    for s in spec.slots:
        slot_node(s)

    # cartes / separator dependencies declared on the slot verb + separator field
    for s in spec.slots:
        for op in re.findall(r"FW_Cartes(?:_first)?\(([A-Za-z0-9_]+)\)", fg._first_line(s.verb)):
            edges.append(GraphEdge(s.sheet, op, "cartes"))
        for op in re.findall(r"FW_Separator\(([A-Za-z0-9_]+)\)", fg._first_line(s.verb)):
            edges.append(GraphEdge(s.sheet, op, "separator"))
        if s.separator:
            edges.append(GraphEdge(s.sheet, s.separator, "separator"))

    # seq_extra brace joiners: a brace consumes prior RESULT tables. Core's
    # FW_()/FW_()G markers resolve from a stack of the most-recent brace targets.
    prior_brace_targets: list[str] = []
    for ri, row in enumerate(spec.seq_extra):
        target = row[0] if row else ""
        for ci, cell in enumerate(row):
            fields = _brace_fields(cell)
            if fields is None:
                continue
            bid = f"brace#{ri}.{ci}"
            mult = fields[8] if len(fields) > 8 else ""
            nodes[bid] = GraphNode(bid, "brace", {"expr": fg._first_line(cell), "mult": mult,
                                                  "target": target})
            # the target sheet's result is produced BY the brace
            if target:
                edges.append(GraphEdge(target, bid, "produces"))
                if target in nodes and nodes[target].kind == "slot":
                    a = dict(nodes[target].attrs); a["is_join_result"] = True
                    nodes[target] = GraphNode(target, "slot", a)
            # E1 (idx 2) and E2 (idx 4) are consumed prior-result operands.
            # Nested markers pop from the same newest-first stack as SeqParser.
            prior_index = len(prior_brace_targets) - 1
            for idx in (2, 4):
                op = fields[idx] if idx < len(fields) else ""
                if op in {"FW_()", "FW_()G"}:
                    if prior_index >= 0:
                        op = prior_brace_targets[prior_index]
                        prior_index -= 1
                    else:
                        op = f"@missing_nested_prior:{ri}:{idx}"
                    edges.append(GraphEdge(bid, op, "brace_nested_operand"))
                elif op:
                    edges.append(GraphEdge(bid, op, "brace_operand"))
            # start(0)/rel(3)/end(6)/sep(7) are referenced sheets
            for idx in (0, 3, 6, 7):
                op = fields[idx] if idx < len(fields) else ""
                if op:
                    edges.append(GraphEdge(bid, op, "brace_ref"))
            if target:
                prior_brace_targets.append(target)

    return FwSeqGraph(nodes=nodes, edges=edges)


def validate_spec_graph(spec: "fg.Spec") -> FwSeqGraph:
    """Build the graph and RAISE ``ValueError`` if it has any error-level issue
    (missing operand / cycle / consumed-result ambiguity). Returns the graph so a
    caller can still emit/inspect it. Warnings (unused advanced nodes) do not
    raise. This is the gate run before workbook emission."""
    g = build_graph(spec)
    errs = g.errors()
    if errs:
        msg = "; ".join(f"[{e.code}] {e.message}" for e in errs)
        raise ValueError(f"FW_Seq dependency graph rejected before workbook: {msg}")
    return g


def graph_plan_block(g: FwSeqGraph) -> dict:
    """The graph block recorded in `plan.json` for an ALREADY-VALIDATED graph:
    the graph + its hash + any WARNING-level issues. The caller MUST have gated
    error-level issues first (see `validate_spec_graph`) — this does not re-gate,
    so it never silently records a graph the plan should have rejected."""
    return {
        "graph_hash": g.graph_hash(),
        "graph": g.to_json(),
        "warnings": [{"code": i.code, "message": i.message, "nodes": list(i.nodes)}
                     for i in g.validate() if i.level == WARNING],
    }


def graph_to_plan_dict(spec: "fg.Spec") -> dict:
    """Convenience: build + GATE (raise on error-level issues) + return the
    plan.json graph block. Use when you don't already hold a validated graph."""
    return graph_plan_block(validate_spec_graph(spec))
