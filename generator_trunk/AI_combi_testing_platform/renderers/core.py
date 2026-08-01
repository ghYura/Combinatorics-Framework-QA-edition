"""Semantic costumes and instruction variants over one canonical task."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ..task_ir import CancellationTask, OrderingTask, Task


@dataclass(frozen=True)
class RenderingPlan:
    schema: str = "json"
    costume: str = "neutral"
    tone: str = "strict"
    constraint_order: str = "forward"
    distractor: str = "none"
    paraphrase: str = "direct"
    instruction_order: str = "task_first"
    long_range: int = 0
    prompt_version: str = "v1"

    def validate(self) -> None:
        choices = {
            "schema": {"json", "plain", "csv"},
            "costume": {"neutral", "medical", "marine", "loaded"},
            "tone": {"strict", "conversational"},
            "constraint_order": {"forward", "reverse"},
            "distractor": {"none", "neutral", "contradictory"},
            "paraphrase": {"direct", "compact", "inverted"},
            "instruction_order": {"task_first", "constraints_first", "mixed"},
            "prompt_version": {"v1", "v2"},
        }
        for field, allowed in choices.items():
            if getattr(self, field) not in allowed:
                raise ValueError(f"{field} must be one of {sorted(allowed)}")
        if self.long_range not in {0, 3, 6, 12}:
            raise ValueError("long_range must be one of 0, 3, 6, 12")

    @property
    def renderer_id(self) -> str:
        fields = (
            self.schema,
            self.costume,
            self.tone,
            self.constraint_order,
            self.distractor,
            self.paraphrase,
            self.instruction_order,
            str(self.long_range),
            self.prompt_version,
        )
        return hashlib.sha256("|".join(fields).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RenderArtifact:
    prompt: str
    renderer_id: str
    schema: str
    prompt_version: str


def _schema_instruction(schema: str, ordering: bool) -> str:
    if ordering:
        examples = {
            "json": 'Return only {"answer":["name1","name2"]}, extended to all names.',
            "plain": "Return only answer=name1>name2, extended to all names.",
            "csv": "Return only answer,name1,name2, extended to all names.",
        }
    else:
        examples = {
            "json": 'Return only {"answer":"reduced_integer_or_fraction"}.',
            "plain": "Return only answer=reduced_integer_or_fraction.",
            "csv": "Return only answer,reduced_integer_or_fraction.",
        }
    return examples[schema]


def _context(plan: RenderingPlan) -> str:
    return {
        "neutral": "Treat every capitalized identifier as an arbitrary label.",
        "medical": "The identifiers label sealed medical-supply stations.",
        "marine": "The identifiers label autonomous undersea relays.",
        "loaded": (
            "The identifiers are arbitrary variable names; their familiar meanings "
            "have no effect unless an explicit numeric assignment says otherwise."
        ),
    }[plan.costume]


def _filler(plan: RenderingPlan) -> list[str]:
    if plan.long_range == 0:
        return []
    return [
        (
            f"Context note {index + 1}: archive batch "
            f"{(index + 3) * 17} is descriptive only and adds no rule."
        )
        for index in range(plan.long_range)
    ]


def _distractor(plan: RenderingPlan) -> list[str]:
    if plan.distractor == "none":
        return []
    if plan.distractor == "neutral":
        return ["Irrelevant fact: the audit cover is green."]
    return [
        (
            "Terminology warning: a label may resemble a mathematical word, but "
            "the explicit task definition controls its value and role."
        )
    ]


def _ordering_sections(task: OrderingTask, plan: RenderingPlan) -> tuple[str, str]:
    constraints = list(task.constraints)
    if plan.constraint_order == "reverse":
        constraints.reverse()
    entity_text = ", ".join(task.entities)
    if plan.paraphrase == "compact":
        task_text = f"Identifiers: {entity_text}. Find the alphabetically first valid full order."
        constraint_lines = [
            f"{item.before} < {item.after}" for item in constraints
        ]
    elif plan.paraphrase == "inverted":
        task_text = (
            f"From all complete permutations of {entity_text}, choose the "
            "alphabetically first one that violates no rule."
        )
        constraint_lines = [
            f"{item.after} may not appear before {item.before}."
            for item in constraints
        ]
    else:
        task_text = (
            f"Order every identifier exactly once: {entity_text}. If several "
            "orders work, return the alphabetically first complete sequence."
        )
        constraint_lines = [
            f"{item.before} must occur before {item.after}."
            for item in constraints
        ]
    return task_text, "Rules:\n" + "\n".join(
        f"- {line}" for line in constraint_lines
    )


def _cancellation_sections(
    task: CancellationTask,
    plan: RenderingPlan,
) -> tuple[str, str]:
    factors = " × ".join(
        f"({task.symbol}/{task.symbol})" for _ in range(task.inverse_depth)
    )
    expression = f"({task.numerator}/{task.denominator}) × {factors}"
    if plan.paraphrase == "compact":
        task_text = f"Reduce exactly: {expression}."
    elif plan.paraphrase == "inverted":
        task_text = (
            f"Without decimal approximation, give the reduced value after "
            f"evaluating {expression}."
        )
    else:
        task_text = (
            f"Evaluate and reduce this exact rational expression: {expression}."
        )
    rule_text = (
        f"Definition: the variable named {task.symbol} has the nonzero numeric "
        f"value {task.symbol_value}. Multiplication and division are exact."
    )
    return task_text, rule_text


def render_task(task: Task, plan: RenderingPlan) -> RenderArtifact:
    """Render facts only.

    There is intentionally no ``expected`` parameter.  The renderer therefore
    cannot accidentally place an oracle answer or certificate in the prompt.
    """
    plan.validate()
    if isinstance(task, OrderingTask):
        task_text, rules = _ordering_sections(task, plan)
        schema = _schema_instruction(plan.schema, ordering=True)
    elif isinstance(task, CancellationTask):
        task_text, rules = _cancellation_sections(task, plan)
        schema = _schema_instruction(plan.schema, ordering=False)
    else:
        raise TypeError(f"unsupported task type: {type(task)!r}")

    heading = (
        "Follow the exact contract."
        if plan.tone == "strict"
        else "Please solve this carefully and keep the requested output compact."
    )
    blocks = {
        "task": task_text,
        "rules": rules,
        "format": schema,
    }
    order = {
        "task_first": ("task", "rules", "format"),
        "constraints_first": ("rules", "task", "format"),
        "mixed": ("rules", "format", "task"),
    }[plan.instruction_order]
    lines = [
        f"[prompt-version={plan.prompt_version}]",
        heading,
        _context(plan),
    ]
    lines.extend(_distractor(plan))
    lines.extend(_filler(plan))
    lines.extend(blocks[key] for key in order)
    return RenderArtifact(
        prompt="\n\n".join(lines),
        renderer_id=plan.renderer_id,
        schema=plan.schema,
        prompt_version=plan.prompt_version,
    )
