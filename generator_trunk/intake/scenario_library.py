"""Shared verified-scenario catalog and immutable launch profiles for both Face 1 UIs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SUITE_ID = "verified_examples"
DEFAULT_SUITE_TITLE = "Verified examples"
AUTOMATION_PROFILE = "automation_scheme_studio"
AUTOMATION_SUITE_ID = "automation_scheme_studio"
AUTOMATION_SUITE_TITLE = "Automation Scheme Studio — exhaustive control-chain search"
AUTOMATION_GOALS = (
    "control_score:max,robustness_score:max,stability_score:max,"
    "settling_time_s:min,worst_error:min,overshoot_pct:min,control_effort:min"
)
AI_PROFILE = "ai_combi_testing_platform"
AI_SUITE_ID = "ai_combi_testing_platform"
AI_SUITE_TITLE = "AI Combinatorial Testing Platform — exact-oracle evaluation"
AI_GOALS = (
    "correct:max,all_constraints_pass:max,semantic_invariance_ok:max,"
    "complexity:max,latency_us:min,cost_microusd:min"
)
AI_RELEASE_GATE_PROFILE = "ai_combi_release_gate_breakpoint"
AI_SUBSUITE_SUITE_ID = "ai_combi_testing_sub_suites"
AI_SUBSUITE_SUITE_TITLE = "AI Combinatorial Testing Platform — advanced sub-suites"
AI_RELEASE_GATE_GOALS = (
    "correct:max,format_ok:max,semantic_correct:max,difficulty_units:max,"
    "construction_states:max,input_tokens:min,cost_microusd:min"
)
RELEASE_GATE_MATERIALIZER = "release_gate_breakpoint"
RELEASE_GATE_DEFAULT_DIFFICULTY_UNITS = (2, 4, 8, 16, 32)
REPOSITORY_LAUNCH_PROFILES = frozenset(
    (
        AUTOMATION_PROFILE,
        AI_PROFILE,
        AI_RELEASE_GATE_PROFILE,
    )
)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_scenarios(
    generator_root: Path,
    manifest: Path | None = None,
) -> list[dict[str, Any]]:
    """Load well-formed static or known-dynamic entries rooted in the repository."""
    root = generator_root.resolve()
    sources = (
        (manifest,)
        if manifest is not None
        else (
            root / "intake" / "automation_scenarios.json",
            root / "intake" / "verified_examples.json",
        )
    )
    raw: list[Any] = []
    for source in sources:
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(document, list):
            raw.extend(document)
    scenarios: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        materializer = str(item.get("spec_materializer") or "")
        if materializer:
            if (
                materializer != RELEASE_GATE_MATERIALIZER
                or str(item.get("run_profile") or "") != AI_RELEASE_GATE_PROFILE
            ):
                continue
            try:
                _release_gate_difficulty_units(item)
            except ValueError:
                continue
            source_value = item.get("source")
            if not source_value:
                continue
            source = (root / str(source_value)).resolve()
            if not source.is_file() or not _inside(source, root):
                continue
        else:
            if not item.get("spec"):
                continue
            spec = (root / str(item["spec"])).resolve()
            if not spec.is_file() or not _inside(spec, root):
                continue
        scenario = dict(item)
        scenario.setdefault("suite", DEFAULT_SUITE_ID)
        scenario.setdefault("suite_title", DEFAULT_SUITE_TITLE)
        scenarios.append(scenario)
    return scenarios


def suite_catalog(scenarios: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return suite id/title pairs in manifest order."""
    suites: list[tuple[str, str]] = []
    seen: set[str] = set()
    for scenario in scenarios:
        suite_id = str(scenario.get("suite") or DEFAULT_SUITE_ID)
        if suite_id in seen:
            continue
        seen.add(suite_id)
        suites.append(
            (
                suite_id,
                str(scenario.get("suite_title") or DEFAULT_SUITE_TITLE),
            )
        )
    return suites


def scenarios_in_suite(
    scenarios: list[dict[str, Any]],
    suite_id: str,
) -> list[dict[str, Any]]:
    return [
        scenario
        for scenario in scenarios
        if str(scenario.get("suite") or DEFAULT_SUITE_ID) == suite_id
    ]


def scenario_source_label(scenario: Mapping[str, Any]) -> str:
    """Describe a static source or an explicitly dynamic spec in either GUI."""
    materializer = str(scenario.get("spec_materializer") or "")
    if materializer:
        return f"fresh {materializer} from {scenario.get('source') or '?'}"
    return str(scenario.get("spec") or "?")


def _release_gate_difficulty_units(
    scenario: Mapping[str, Any],
) -> tuple[int, ...]:
    raw = scenario.get("difficulty_units", RELEASE_GATE_DEFAULT_DIFFICULTY_UNITS)
    if not isinstance(raw, (list, tuple)):
        raise ValueError("release-gate difficulty_units must be an array")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in raw):
        raise ValueError("release-gate difficulty_units must be integers")
    units = tuple(raw)
    if not units or len(units) > 6:
        raise ValueError("release-gate profile requires one through six levels")
    if any(value < 2 or value > 64 or value & (value - 1) for value in units):
        raise ValueError("release-gate levels must be powers of two from 2 through 64")
    if any(right != left * 2 for left, right in zip(units, units[1:])):
        raise ValueError("release-gate levels must form a strictly doubling ladder")
    return units


def release_gate_candidate_count(scenario: Mapping[str, Any]) -> int:
    return len(_release_gate_difficulty_units(scenario)) * 512


def scenario_spec_document(
    scenario: Mapping[str, Any],
    generator_root: Path,
) -> tuple[str, str]:
    """Return one runnable TOML document and safe filename for a catalog entry."""
    root = generator_root.resolve()
    materializer = str(scenario.get("spec_materializer") or "")
    if not materializer:
        source = (root / str(scenario.get("spec") or "")).resolve()
        if not source.is_file() or not _inside(source, root):
            raise ValueError("scenario spec path is missing or outside the repository")
        return source.read_text(encoding="utf-8"), source.name
    if materializer != RELEASE_GATE_MATERIALIZER:
        raise ValueError(f"unsupported scenario spec materializer: {materializer}")
    if str(scenario.get("run_profile") or "") != AI_RELEASE_GATE_PROFILE:
        raise ValueError("release-gate materializer requires its immutable run profile")
    difficulty_units = _release_gate_difficulty_units(scenario)
    reference = (root / str(scenario.get("source") or "")).resolve()
    if not reference.is_file() or not _inside(reference, root):
        raise ValueError("dynamic scenario source is missing or outside the repository")

    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.exchange import (
        build_release_gate_spec_text,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.runtime import (
        rg_solve,
    )
    from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.task_factory import (
        generate_release_gate_ladder,
        new_release_holdout_seed,
    )

    generated = generate_release_gate_ladder(
        new_release_holdout_seed(),
        difficulty_units,
    )
    if any(rg_solve(row.task) != row.planted_answer for row in generated):
        raise RuntimeError("release-gate materializer oracle cross-check failed")
    return (
        build_release_gate_spec_text(row.task for row in generated),
        "release_gate_breakpoint.toml",
    )


def _run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def scenario_run_config(
    scenario: Mapping[str, Any],
    generator_root: Path,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the run config, isolating special profiles from workbook controls."""
    profile = str(scenario.get("run_profile") or "")
    if profile not in REPOSITORY_LAUNCH_PROFILES:
        config = dict(base or {})
        if not config.get("analyzer") and scenario.get("analyzer"):
            config["analyzer"] = str(scenario["analyzer"])
            config["mode"] = "formal"
        return config

    scenario_id = str(scenario["id"])
    run_stem = str(scenario.get("run_stem") or scenario_id)
    database = str(scenario.get("database") or scenario_id)
    # Repository launch profiles deliberately replace ordinary workbook knobs,
    # but they must not replace the operator's authorization evidence. Before
    # Phase 02 these two fields were absent; after F1 the special-profile return
    # paths still discarded them from `base`, making every trusted example fail.
    trusted_authorization = {
        "candidateOrigin": str((base or {}).get("candidateOrigin") or ""),
        "trustedLocalAcknowledgement": str(
            (base or {}).get("trustedLocalAcknowledgement") or ""),
    }
    if profile == AI_RELEASE_GATE_PROFILE:
        candidate_count = release_gate_candidate_count(scenario)
        return {
            "backend": "local",
            "db": database,
            "runId": f"{run_stem}-ui-{_run_stamp()}",
            "lang": "py",
            "runMode": "verdict",
            "profile": "generated-default",
            "transport": "sharded",
            "executorPool": 1,
            "iterations": 1,
            "repeat": 1,
            "repeatPolicy": "local",
            "repeatScope": "all",
            "mainPort": 5433,
            "resultsPort": 5432,
            "analyzer": AI_RELEASE_GATE_GOALS,
            "mode": "formal",
            "budgetMandatoryRows": candidate_count // 16,
            "budgetFinalCandidates": candidate_count,
            "budgetRequests": candidate_count,
            "budgetMonetaryCost": 0,
            "costPerCandidate": 0,
            "allowExtreme": True,
            "overrideBudget": str(
                scenario.get("override_budget")
                or "reviewed bounded release-gate breakpoint apparatus"
            ),
        }
    if profile == AI_PROFILE:
        return {
            "backend": "local",
            "db": database,
            "runId": f"{run_stem}-ui-{_run_stamp()}",
            "lang": "py",
            "runMode": "verdict",
            "profile": "trusted-local",
            "transport": "sharded",
            "executorPool": 1,
            "iterations": 1,
            "repeat": 1,
            "mainPort": 5433,
            "resultsPort": 5432,
            "analyzer": AI_GOALS,
            "mode": "formal",
        } | trusted_authorization | (
            {
                "allowExtreme": True,
                "overrideBudget": str(
                    scenario.get("override_budget")
                    or "reviewed Bundle-native AI higher-order composition"
                ),
            }
            if scenario.get("allow_extreme")
            else {}
        )
    return {
        "backend": "local",
        "db": database,
        "runId": f"{run_stem}-ui-{_run_stamp()}",
        "lang": "py",
        "runMode": "verdict",
        "profile": "trusted-local",
        "transport": "sharded",
        "iterations": 1,
        "repeat": 1,
        "mainPort": 5433,
        "resultsPort": 5432,
        "pyExecutor": str(
            (
                generator_root
                / "scenarios"
                / "automation_scheme_studio"
                / "parallel_py_executor.py"
            ).resolve()
        ),
        "analyzer": AUTOMATION_GOALS,
        "mode": "formal",
        "unleash": True,
    } | trusted_authorization | (
        {
            "allowExtreme": True,
            "overrideBudget": str(
                scenario.get("override_budget")
                or "explicit advanced recursive control-topology search"
            ),
        }
        if scenario.get("allow_extreme")
        else {}
    )


def discover_sut_root(framework_root: Path) -> Path | None:
    """Find the documented sibling checkout without overriding explicit config."""
    candidates = (
        framework_root.parent / "SUT",
        framework_root.parent / "SUT-main",
        framework_root / "suts",
    )
    for candidate in candidates:
        if (candidate / "automation-scheme-studio" / "src").is_dir():
            return candidate.resolve()
    return None


def scenario_environment(
    scenario: Mapping[str, Any],
    framework_root: Path,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a child environment with only profile-required portable defaults."""
    env = dict(os.environ if environ is None else environ)
    profile = str(scenario.get("run_profile") or "")
    if profile not in REPOSITORY_LAUNCH_PROFILES:
        return env
    resolved_framework = str(framework_root.resolve())
    env.setdefault("BUNDLE_FRAMEWORK_ROOT", resolved_framework)
    python_paths = [
        item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item
    ]
    if resolved_framework not in python_paths:
        env["PYTHONPATH"] = os.pathsep.join((resolved_framework, *python_paths))
    if profile in (AI_PROFILE, AI_RELEASE_GATE_PROFILE):
        for key in (
            "AI_COMBI_ALLOW_EXTERNAL",
            "AI_COMBI_CONFIG",
            "AI_COMBI_EXPORT_PROMPT",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
        ):
            env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["AI_COMBI_ENVIRONMENT_ID"] = (
            "face1-release-gate-control"
            if profile == AI_RELEASE_GATE_PROFILE
            else "face1-local-control"
        )
        return env
    if not env.get("BUNDLE_SUT_ROOT"):
        sut_root = discover_sut_root(framework_root)
        if sut_root is not None:
            env["BUNDLE_SUT_ROOT"] = str(sut_root)
    env.setdefault(
        "AUTOMATION_BUNDLE_EXECUTOR_WORKERS",
        str(min(8, os.cpu_count() or 1)),
    )
    return env
