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

"""NiceGUI invitation and combination-thinking coach."""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from invitation_wizard import assessment, domains, propose

from .invitation_adapter import project_from_invitation
from .runtime_model import format_estimate, plan_project


WIZARD_CSS = """
.invite-shell{padding:14px;gap:12px}.invite-hero{border:1px solid #a8c7b4;background:linear-gradient(135deg,#edf8f1,#fff);
border-radius:12px;padding:14px}.invite-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;width:100%}
.invite-card{border:1px solid var(--line);background:#fff;border-radius:10px;padding:11px;min-width:0}
.invite-card h3{font-size:12px;font-weight:800;margin:0 0 6px}.invite-card p{font-size:11px;color:var(--muted);margin:3px 0}
.growth-strip{display:grid;grid-template-columns:repeat(4,minmax(110px,1fr));gap:7px;width:100%}
.growth-cell{border:1px solid #bdd2c4;background:#f2faf5;border-radius:8px;padding:8px}
.growth-cell b{display:block;font-size:16px;color:#17633a}.growth-cell span{font-size:9px;color:var(--muted);text-transform:uppercase}
.coach-warning{border-left:4px solid #d97706;background:#fff7ed;color:#7c2d12;border-radius:6px;padding:8px 10px;font-size:11px}
.coach-lesson{border-left:4px solid #3159c6;background:#eef3ff;color:#243f8f;border-radius:6px;padding:9px 11px;font-size:11px}
@media(max-width:760px){.growth-strip{grid-template-columns:repeat(2,1fr)}}
"""


def render_invitation_center(state: dict[str, Any], on_apply: Callable[[Any], None]) -> None:
    wizard = state.setdefault(
        "invitation",
        {"domain": "learn", "goal": "", "risks": set(), "stress": set(), "constraints": set()},
    )
    for key in ("risks", "stress", "constraints"):
        if not isinstance(wizard.get(key), set):
            wizard[key] = set(wizard.get(key) or ())
    host = ui.column().classes("invite-shell w-full")

    def update(key: str, value: Any) -> None:
        wizard[key] = value
        repaint()

    def toggle(key: str, value: str, enabled: bool) -> None:
        values: set[str] = wizard[key]
        values.add(value) if enabled else values.discard(value)
        repaint()

    def repaint() -> None:
        host.clear()
        draft = propose(wizard["domain"], wizard["goal"], wizard["risks"])
        selected_stress = tuple(item for item in draft.stress_actions if item.key in wizard["stress"])
        growth = assessment(draft.factors, selected_stress, wizard["constraints"])
        project = project_from_invitation(draft, wizard["stress"])
        exact = plan_project(project)

        with host:
            with ui.element("div").classes("invite-hero w-full"):
                ui.label("Start with the issue, not with syntax").classes("eyebrow")
                ui.label("Invitation to think in combinations").classes("text-xl font-bold")
                ui.label(
                    "Answer three small questions. The coach proposes an editable model, explains risky interactions, "
                    "and shows how every optional disturbance changes the search space."
                ).classes("text-xs muted leading-relaxed")

            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                ui.select(
                    {item["id"]: item["title"] for item in domains()},
                    value=wizard["domain"],
                    label="What kind of issue is this?",
                    on_change=lambda event: update("domain", event.value),
                ).classes("min-w-[260px]")
                ui.input(
                    "What outcome should improve or never fail?",
                    value=wizard["goal"],
                    on_change=lambda event: update("goal", event.value),
                ).classes("grow min-w-[280px]")

            ui.label("Which risks worry you most? This only prioritizes suggestions.").classes("text-xs font-semibold")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                for key, label in (
                    ("integrity", "duplicate or inconsistent state"),
                    ("timing", "delay, order, or timeout"),
                    ("resource", "interruption or resource pressure"),
                ):
                    ui.checkbox(
                        label,
                        value=key in wizard["risks"],
                        on_change=lambda event, item=key: toggle("risks", item, event.value),
                    ).props("dense")

            with ui.element("div").classes("growth-strip"):
                for label, value in (
                    ("mandatory crossings", f"{growth.mandatory:,}"),
                    ("optional multiplier", f"×{growth.optional_multiplier:,}"),
                    ("raw final space", format_estimate(exact.final)),
                    ("value-pair interactions", f"{growth.interaction_pairs:,}"),
                ):
                    with ui.element("div").classes("growth-cell"):
                        ui.label(value).classes("font-bold")
                        ui.label(label)

            ui.label("Proposed factors — editable after confirmation").classes("text-sm font-bold")
            with ui.element("div").classes("invite-grid"):
                for factor in draft.factors:
                    with ui.element("div").classes("invite-card"):
                        ui.label(factor.name).classes("text-xs font-bold")
                        ui.label(" · ".join(factor.values)).classes("text-[11px]")
                        ui.label(factor.why).classes("text-[10px] muted")

            with ui.element("div").classes("invite-grid"):
                with ui.element("div").classes("invite-card"):
                    ui.label("Interactions worth investigating").classes("text-xs font-bold")
                    for item in draft.interactions:
                        ui.label("↔ " + item).classes("text-[11px]")
                with ui.element("div").classes("invite-card"):
                    ui.label("Relationships still missing").classes("text-xs font-bold")
                    ui.label("Raw counts assume every crossing is valid. Mark only questions for which you can state a rule.").classes("text-[10px] muted")
                    for item in draft.missing_constraints:
                        ui.checkbox(
                            item,
                            value=item in wizard["constraints"],
                            on_change=lambda event, text=item: toggle("constraints", text, event.value),
                        ).props("dense")

            ui.label("Optional stress actions — deliberately unchecked").classes("text-sm font-bold")
            ui.label(
                "An optional row tries absence plus each listed action. Add one because it represents a plausible failure hypothesis, "
                "not merely to make the run larger."
            ).classes("text-[11px] muted")
            with ui.element("div").classes("invite-grid"):
                for item in draft.stress_actions:
                    with ui.element("div").classes("invite-card"):
                        ui.checkbox(
                            item.name,
                            value=item.key in wizard["stress"],
                            on_change=lambda event, key=item.key: toggle("stress", key, event.value),
                        ).props("dense")
                        ui.label(" · ".join(item.values)).classes("text-[11px]")
                        ui.label(item.why).classes("text-[10px] muted")

            for warning in growth.warnings:
                ui.label(warning).classes("coach-warning w-full")
            ui.label(draft.lesson).classes("coach-lesson w-full")

            with ui.element("div").classes("invite-card w-full"):
                ui.label("Good next examples").classes("text-xs font-bold")
                ui.label("These are existing use cases, not invented demonstrations.").classes("text-[10px] muted")
                with ui.row().classes("gap-2 flex-wrap"):
                    for path in draft.use_cases:
                        ui.label(path).classes("pill")

            def apply() -> None:
                errors = [issue.message for issue in project.validate() if issue.severity == "error"]
                if errors:
                    ui.notify("; ".join(errors), type="negative", multi_line=True)
                    return
                ui.notify("Starter uses raw combinations. Record actual relationship rules in Face 2 before claiming constrained coverage.", type="warning")
                on_apply(project)

            with ui.row().classes("w-full justify-between items-center flex-wrap gap-2"):
                ui.label("Nothing is applied silently. You can edit every proposed cell after confirmation.").classes("text-[10px] muted")
                ui.button("Use this editable starter", on_click=apply).props("color=green-8 no-caps")

    repaint()
