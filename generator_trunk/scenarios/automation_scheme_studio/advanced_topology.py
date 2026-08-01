"""Recursive, executable feedback-topology programs for Bundle candidates.

The Bundle emits a token stream.  Brace and FW_Group results may coexist with
their intermediate result sheets in a final candidate, so parsing deliberately
selects the highest-order complete root and ignores incomplete helper markers.
The selected root is registered as a real SearchPlan feedback cell and compiled
by the SUT's own circuit builder, compiler, runtime, terminals, and oracle.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from automation_constructor.experiments import bundle_search as bs

BOUNDARIES = ("unit_delay", "low_pass", "integrator")
PLACEMENTS = ("feedback_only", "forward_and_feedback")
REDUCERS = ("mean", "sum", "signed")
REPEAT_MODES = ("series", "parallel")


@dataclass(frozen=True, slots=True)
class Node:
    kind: str
    children: tuple["Node", ...] = ()
    token: str = ""
    controller: str = ""
    boundary: str = ""
    placement: str = ""
    reducer: str = ""
    count: int = 1
    mode: str = ""

    @staticmethod
    def atom(token: str) -> "Node":
        if token not in bs.ALL_STAGE_TOKENS:
            raise ValueError(f"unknown SUT stage {token!r}")
        return Node("atom", token=token)

    @staticmethod
    def sequence(*children: "Node") -> "Node":
        return _container("sequence", children)

    @staticmethod
    def parallel(*children: "Node", reducer: str = "mean") -> "Node":
        if reducer not in REDUCERS:
            raise ValueError(f"unknown reducer {reducer!r}")
        return _container("parallel", children, reducer=reducer)

    @staticmethod
    def feedback(
        body: "Node",
        *,
        controller: str = "pid",
        boundary: str = "unit_delay",
        placement: str = "forward_and_feedback",
    ) -> "Node":
        if controller not in bs.CONTROLLER_TOKENS:
            raise ValueError(f"unknown feedback controller {controller!r}")
        if boundary not in BOUNDARIES:
            raise ValueError(f"unknown feedback boundary {boundary!r}")
        if placement not in PLACEMENTS:
            raise ValueError(f"unknown feedback placement {placement!r}")
        return Node(
            "feedback",
            (body,),
            controller=controller,
            boundary=boundary,
            placement=placement,
        )

    @staticmethod
    def repeat(
        body: "Node",
        *,
        count: int,
        mode: str = "series",
        reducer: str = "mean",
    ) -> "Node":
        if not 2 <= count <= 6:
            raise ValueError("repeat count must be in [2, 6]")
        if mode not in REPEAT_MODES:
            raise ValueError(f"unknown repeat mode {mode!r}")
        if reducer not in REDUCERS:
            raise ValueError(f"unknown reducer {reducer!r}")
        return Node(
            "repeat",
            (body,),
            count=count,
            mode=mode,
            reducer=reducer,
        )


def _container(
    kind: str,
    children: Iterable[Node],
    *,
    reducer: str = "",
) -> Node:
    materialized = tuple(children)
    if not materialized:
        raise ValueError(f"{kind} needs at least one child")
    if len(materialized) == 1 and kind == "sequence":
        return materialized[0]
    return Node(kind, materialized, reducer=reducer)


@dataclass(frozen=True, slots=True)
class Marker:
    action: str
    level: int
    kind: str = ""
    options: tuple[tuple[str, Any], ...] = ()


@dataclass(slots=True)
class _Frame:
    level: int
    kind: str
    options: dict[str, Any]
    children: list[Node] = field(default_factory=list)


def emit_atom(stream: list[Node | Marker], token: str) -> None:
    stream.append(Node.atom(token))


def emit_node(stream: list[Node | Marker], node: Node) -> None:
    stream.append(node)


def emit_open(
    stream: list[Node | Marker],
    level: int,
    kind: str,
    **options: Any,
) -> None:
    stream.append(Marker("open", level, kind, tuple(sorted(options.items()))))


def emit_close(stream: list[Node | Marker], level: int) -> None:
    stream.append(Marker("close", level))


def template(name: str) -> Node:
    """Reusable high-information subcircuits used as second-order atoms."""
    if name == "inverter_modulator_loop":
        return Node.feedback(
            Node.sequence(
                Node.atom("inverter"),
                Node.atom("modulator"),
                Node.atom("low_pass"),
            ),
            controller="pi",
            boundary="unit_delay",
            placement="forward_and_feedback",
        )
    if name == "parallel_conditioners":
        return Node.parallel(
            Node.sequence(Node.atom("limiter"), Node.atom("dead_zone")),
            Node.feedback(
                Node.sequence(Node.atom("comparator_gate"), Node.atom("relay")),
                controller="relay",
                boundary="low_pass",
                placement="feedback_only",
            ),
            Node.sequence(Node.atom("selector"), Node.atom("probe")),
            reducer="mean",
        )
    if name == "repeated_relay_loop":
        return Node.repeat(
            Node.feedback(
                Node.sequence(Node.atom("relay"), Node.atom("unit_delay")),
                controller="p",
                boundary="unit_delay",
                placement="forward_and_feedback",
            ),
            count=2,
            mode="series",
        )
    if name == "parallel_pid_loops":
        return Node.repeat(
            Node.feedback(
                Node.sequence(Node.atom("pid"), Node.atom("integrator")),
                controller="pid",
                boundary="low_pass",
                placement="feedback_only",
            ),
            count=3,
            mode="parallel",
            reducer="signed",
        )
    if name == "nested_selector_loop":
        inner = Node.feedback(
            Node.parallel(
                Node.atom("bumpless_selector"),
                Node.atom("manual_selector"),
                reducer="mean",
            ),
            controller="relay",
            boundary="integrator",
            placement="feedback_only",
        )
        return Node.feedback(
            Node.sequence(Node.atom("selector"), inner, Node.atom("limiter")),
            controller="pd",
            boundary="unit_delay",
            placement="forward_and_feedback",
        )
    if name == "deep_mixed":
        return Node.feedback(
            Node.sequence(
                template("parallel_conditioners"),
                Node.repeat(
                    template("inverter_modulator_loop"),
                    count=2,
                    mode="parallel",
                    reducer="mean",
                ),
            ),
            controller="pid",
            boundary="integrator",
            placement="forward_and_feedback",
        )
    raise ValueError(f"unknown topology template {name!r}")


def _frame_node(frame: _Frame) -> Node:
    children = tuple(frame.children)
    if not children:
        raise ValueError("empty frame")
    if frame.kind == "sequence":
        return Node.sequence(*children)
    if frame.kind == "parallel":
        return Node.parallel(
            *children,
            reducer=str(frame.options.get("reducer", "mean")),
        )
    body = Node.sequence(*children)
    if frame.kind == "feedback":
        return Node.feedback(
            body,
            controller=str(frame.options.get("controller", "pid")),
            boundary=str(frame.options.get("boundary", "unit_delay")),
            placement=str(
                frame.options.get("placement", "forward_and_feedback")
            ),
        )
    if frame.kind == "repeat":
        return Node.repeat(
            body,
            count=int(frame.options.get("count", 2)),
            mode=str(frame.options.get("mode", "series")),
            reducer=str(frame.options.get("reducer", "mean")),
        )
    raise ValueError(f"unknown frame kind {frame.kind!r}")


def parse_topology(stream: Iterable[Node | Marker]) -> Node:
    """Recover the deepest complete composition from Bundle-generated code."""
    frames: list[_Frame] = []
    roots: list[tuple[int, Node]] = []
    for item in stream:
        if isinstance(item, Node):
            if frames:
                frames[-1].children.append(item)
            else:
                roots.append((0, item))
            continue
        if item.action == "open":
            frames.append(
                _Frame(item.level, item.kind, dict(item.options))
            )
            continue
        if not frames or frames[-1].level != item.level:
            continue
        frame = frames.pop()
        if not frame.children:
            continue
        node = _frame_node(frame)
        if frames:
            frames[-1].children.append(node)
        else:
            roots.append((frame.level, node))
    if not roots:
        raise ValueError("no complete topology root was emitted")
    return max(
        roots,
        key=lambda candidate: (
            candidate[0],
            topology_stats(candidate[1])["topology_nodes"],
            topology_stats(candidate[1])["topology_depth"],
            topology_signature(candidate[1]),
        ),
    )[1]


def _as_dict(node: Node) -> dict[str, Any]:
    return {
        "kind": node.kind,
        "token": node.token,
        "controller": node.controller,
        "boundary": node.boundary,
        "placement": node.placement,
        "reducer": node.reducer,
        "count": node.count,
        "mode": node.mode,
        "children": [_as_dict(child) for child in node.children],
    }


def topology_signature(node: Node) -> str:
    if node.kind == "atom":
        return node.token
    children = ",".join(topology_signature(child) for child in node.children)
    if node.kind == "feedback":
        return (
            f"fb[{node.controller}/{node.boundary}/{node.placement}]"
            f"({children})"
        )
    if node.kind == "parallel":
        return f"par[{node.reducer}]({children})"
    if node.kind == "repeat":
        return f"repeat[{node.mode}x{node.count}/{node.reducer}]({children})"
    return f"seq({children})"


def topology_id(node: Node) -> str:
    payload = json.dumps(_as_dict(node), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def topology_stats(node: Node) -> dict[str, int]:
    child_stats = [topology_stats(child) for child in node.children]
    totals = {
        key: sum(stats[key] for stats in child_stats)
        for key in (
            "topology_nodes",
            "topology_atoms",
            "topology_feedbacks",
            "topology_parallels",
            "topology_repeats",
        )
    }
    totals["topology_nodes"] += 1
    totals["topology_atoms"] += int(node.kind == "atom")
    totals["topology_feedbacks"] += int(node.kind == "feedback")
    totals["topology_parallels"] += int(node.kind == "parallel")
    totals["topology_repeats"] += int(node.kind == "repeat")
    totals["topology_depth"] = 1 + max(
        (stats["topology_depth"] for stats in child_stats),
        default=0,
    )
    totals["topology_expanded_atoms"] = (
        node.count * child_stats[0]["topology_expanded_atoms"]
        if node.kind == "repeat"
        else sum(
            stats["topology_expanded_atoms"] for stats in child_stats
        ) + int(node.kind == "atom")
    )
    return totals


_RECIPES: dict[str, Node] = {}
_ORIGINAL_FEEDBACK_CELL = getattr(
    bs._CircuitBuilder,
    "_advanced_original_feedback_cell",
    bs._CircuitBuilder._feedback_cell,
)
bs._CircuitBuilder._advanced_original_feedback_cell = _ORIGINAL_FEEDBACK_CELL


def _reduce(self, refs: list[str], reducer: str, stem: str) -> str:
    if not refs:
        raise ValueError("parallel topology has no branches")
    if len(refs) == 1:
        return refs[0]
    partials: list[str] = []
    for offset in range(0, len(refs), 4):
        group = refs[offset : offset + 4]
        if reducer == "mean":
            partials.append(self._blend(group, f"{stem}_mean_{offset // 4}"))
        else:
            weights = (
                tuple(1.0 for _ in group)
                if reducer == "sum"
                else tuple(
                    1.0 if (offset + index) % 2 == 0 else -1.0
                    for index in range(len(group))
                )
            )
            partials.append(
                self._sum(tuple(group), weights, f"{stem}_{reducer}_{offset // 4}")
            )
    if len(partials) == 1:
        return partials[0]
    return _reduce(self, partials, "mean" if reducer == "mean" else "sum", f"{stem}_fold")


def _compile_node(self, node: Node, source_ref: str, stem: str) -> str:
    if node.kind == "atom":
        return self._stage(node.token, source_ref, f"{stem}_{node.token}")
    if node.kind == "sequence":
        ref = source_ref
        for index, child in enumerate(node.children, 1):
            ref = _compile_node(self, child, ref, f"{stem}_s{index}")
        return ref
    if node.kind == "parallel":
        refs = [
            _compile_node(self, child, source_ref, f"{stem}_p{index}")
            for index, child in enumerate(node.children, 1)
        ]
        return _reduce(self, refs, node.reducer, f"{stem}_reduce")
    if node.kind == "repeat":
        body = node.children[0]
        if node.mode == "series":
            ref = source_ref
            for index in range(1, node.count + 1):
                ref = _compile_node(self, body, ref, f"{stem}_r{index}")
            return ref
        refs = [
            _compile_node(self, body, source_ref, f"{stem}_r{index}")
            for index in range(1, node.count + 1)
        ]
        return _reduce(self, refs, node.reducer, f"{stem}_repeat_reduce")
    if node.kind == "feedback":
        error = self._add(
            "core.weighted_sum",
            f"{stem}_error",
            {
                "weight_a": 1.0,
                "weight_b": -1.0,
                "weight_c": 0.0,
                "weight_d": 0.0,
                "offset": 0.0,
            },
        )
        self._wire(source_ref, error, "a")
        controller_ref = self._controller(
            node.controller,
            f"{error}.out",
            f"{stem}_controller",
            inner=True,
        )
        body_ref = _compile_node(
            self,
            node.children[0],
            controller_ref,
            f"{stem}_body",
        )
        boundary_ref = self._stage(
            node.boundary,
            body_ref,
            f"{stem}_boundary_{node.boundary}",
        )
        self._wire(boundary_ref, error, "b")
        return (
            body_ref
            if node.placement == "forward_and_feedback"
            else controller_ref
        )
    raise ValueError(f"unknown node kind {node.kind!r}")


def _advanced_feedback_cell(
    self,
    token: str,
    source_ref: str,
    stem: str,
) -> str:
    node = _RECIPES.get(token)
    if node is None:
        return _ORIGINAL_FEEDBACK_CELL(self, token, source_ref, stem)
    return _compile_node(self, node, source_ref, stem)


bs._CircuitBuilder._feedback_cell = _advanced_feedback_cell


def attach_topology(plan: bs.SearchPlan, stream: Iterable[Node | Marker]) -> Node:
    node = parse_topology(stream)
    token = f"advanced_{topology_id(node)}"
    _RECIPES[token] = node
    # SearchPlan validates keys; the patched builder consumes the recursive body.
    bs.LOOP_CELL_TOKENS[token] = ("p", "unit_delay")
    plan.add_loop(token)
    return node


def annotate_result(result: bs.EvaluationResult, node: Node) -> None:
    result.metrics.update(topology_stats(node))
    result.metrics["topology_id"] = topology_id(node)
    result.metrics["topology_signature"] = topology_signature(node)
