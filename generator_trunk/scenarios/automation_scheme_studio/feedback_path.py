"""Deep feedback-path recipes used by the covering campaign."""

from __future__ import annotations

from typing import Any

from automation_constructor.experiments import bundle_search as bs

_RECIPES: dict[str, tuple[str, str, tuple[str, ...], str]] = {}
_ORIGINAL_FEEDBACK_CELL = bs._CircuitBuilder._feedback_cell


def _deep_feedback_cell(self, token: str, source_ref: str, stem: str) -> str:
    recipe = _RECIPES.get(token)
    if recipe is None:
        return _ORIGINAL_FEEDBACK_CELL(self, token, source_ref, stem)
    controller, boundary, stages, placement = recipe
    local_error = self._add(
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
    self._wire(source_ref, local_error, "a")
    controller_ref = self._controller(
        controller,
        f"{local_error}.out",
        f"{stem}_controller",
        inner=True,
    )
    path_ref = controller_ref
    for index, stage in enumerate(stages, 1):
        path_ref = self._stage(stage, path_ref, f"{stem}_path_{index}_{stage}")
    feedback_ref = self._stage(
        boundary,
        path_ref,
        f"{stem}_state_boundary",
    )
    self._wire(feedback_ref, local_error, "b")
    return path_ref if placement == "forward_and_feedback" else controller_ref


if bs._CircuitBuilder._feedback_cell is not _deep_feedback_cell:
    bs._CircuitBuilder._feedback_cell = _deep_feedback_cell


def covering_feedback_recipe(
    front_index: int,
    row: int,
) -> tuple[str, str, tuple[str, ...], str]:
    """Return one deterministic row of the 370x16 covering design."""
    if not 0 <= front_index < 370 or not 0 <= row < 16:
        raise ValueError("covering coordinates are outside 370x16")
    stages = bs.ALL_STAGE_TOKENS
    count = len(stages)
    stage_path = (
        stages[row],
        stages[(row + front_index) % count],
        stages[(5 * row + 3 + front_index // count) % count],
    )
    controller = bs.CONTROLLER_TOKENS[row % len(bs.CONTROLLER_TOKENS)]
    boundary = ("unit_delay", "low_pass", "integrator")[
        row // len(bs.CONTROLLER_TOKENS)
        if row < 15
        else front_index % 3
    ]
    placement = (
        "forward_and_feedback"
        if (front_index + row) % 2 == 0
        else "feedback_only"
    )
    return controller, boundary, stage_path, placement


def append_covering_feedback_path(plan, front_index: int, row: int) -> dict[str, Any]:
    """Append one deterministic row of the 370x16 pairwise/deep covering design."""
    controller, boundary, stage_path, placement = covering_feedback_recipe(
        front_index,
        row,
    )
    token = f"covering_path_{front_index}_{row}"
    _RECIPES[token] = (controller, boundary, stage_path, placement)
    # The value is a validation sentinel; the patched builder uses _RECIPES.
    bs.LOOP_CELL_TOKENS[token] = (controller, boundary)
    plan.add_loop(token)
    return {
        "front_index": front_index,
        "feedback_row": row,
        "feedback_controller": controller,
        "feedback_boundary": boundary,
        "feedback_path": ">".join(stage_path),
        "feedback_placement": placement,
    }
