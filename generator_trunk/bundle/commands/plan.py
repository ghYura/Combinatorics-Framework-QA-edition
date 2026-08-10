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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""`bundle plan` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
import fwseq_graph as _seq_graph
from pathlib import Path
from ..budgets import blocking_checks, budget_check_to_dict, evaluate_budgets
from ..cliargs import _add_budget_ceiling_args, _add_repeat_args
from ..cliutil import _budget_limits_from_config, _load_one_spec, _resolve_bundle_config
from ..counts import count_plan
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic
from ..optional_contract import OptionalContractError, contract_from_spec
from ..resources import (
    DEFAULT_PER_CANDIDATE_SECONDS,
    ResourceThresholds,
    estimate_resources,
    format_resource_plan,
    resource_plan_to_dict,
)
from ..runs import file_sha256
from ..stages import fg


PLAN_SCHEMA = "bundle.plan/v1"


def _slot_summary(s) -> dict:
    return {"sheet": s.sheet, "verb": str(s.verb).splitlines()[0].strip(),
            "flags": list(s.flags), "n": len(s.values)}


def _plan_warnings(spec, plan) -> list:
    """Risks the operator should see before committing to a run (STEP 10 action 2:
    plan output must include `warnings`). Each is actionable and tied to a
    concrete plan/spec fact — never a vague "be careful"."""
    M = fg.CardinalityMode
    warnings = []
    if spec.spec_version == "legacy":
        warnings.append("spec has no 'spec_version' — interpreted as legacy (bundle-spec-v1 not declared)")
    brace_rows = sum(1 for cells in spec.seq_extra for c in cells
                     if fg._BRACE_RE.fullmatch(str(c).strip().splitlines()[0].strip()))
    if brace_rows:
        warnings.append(f"{brace_rows} seq_extra brace joiner row(s): their joined-result-table row "
                        f"count is UNKNOWN until Core runs (see cardinality.mandatory.reasons)")
    if plan.mandatory.mode != M.EXACT:
        warnings.append(f"mandatory Core product is {plan.mandatory.mode.value}, not EXACT — "
                        f"{plan.mandatory.formula}")
    if spec.constraints:
        warnings.append(f"{len(spec.constraints)} constraint(s) declared — post-sieve count is only "
                        f"bounded [{plan.post_sieve.lower}, {plan.post_sieve.upper}], not predicted exactly "
                        f"(sieve selectivity is not evaluated without running it)")
    n_opt = sum(1 for s in spec.slots if "FW_Optional" in s.flags)
    if n_opt:
        warnings.append(f"{n_opt} FW_Optional slot(s) — optional multiplier ×{plan.optional_multiplier.value} "
                        f"expands the post-sieve space into the final candidate count")
    if plan.final.mode == M.UNKNOWN:
        warnings.append("final candidate count is UNKNOWN — it cannot be sized statically (no "
                        "upper bound); its true size is known only once Core runs (Automation #31 cleanup)")
    elif plan.final.mode != M.EXACT:
        warnings.append(f"final candidate count is {plan.final.mode.value} "
                        f"[{plan.final.lower}, {plan.final.upper}], not an exact prediction — "
                        f"treat {plan.final.value} as an upper-bound planning figure")
    return warnings


def cmd_plan(a) -> None:
    """`bundle plan <spec-dir>` (STEP 10): estimate a run's shape WITHOUT any
    PostgreSQL/JAR/application/candidate side effects — load the spec, build its
    STEP-9 confidence-tagged cardinality plan, print spec identity/operator
    table/counts/exactness, and write a versioned `plan.json`."""
    spec, toml_path = _load_one_spec(a.spec_dir)
    # STEP 37: the FW_Seq dependency graph is a preflight GATE — a cycle / missing
    # operand / consumed-result ambiguity must reject the spec BEFORE any plan.json
    # is written (a plan for an unbuildable graph would be misleading). Build once
    # here, gate error-level issues, then reuse the graph for the artifact block.
    graph = _seq_graph.build_graph(spec)
    graph_errors = graph.errors()
    if graph_errors:
        msg = "; ".join(f"[{e.code}] {e.message}" for e in graph_errors)
        raise PreflightError(f"FW_Seq dependency graph has {len(graph_errors)} error(s) — "
                             f"refusing to write plan.json: {msg}")
    # CLI overrides the spec: the flag is how an operator re-plans the same spec
    # against a different budget without editing it.
    if getattr(a, "coverage_strength", 0):
        spec.coverage_strength = int(a.coverage_strength)
    if getattr(a, "coverage_optimal", False):
        spec.coverage_optimal = True
    if getattr(a, "coverage_budget", 0):
        spec.coverage_budget = int(a.coverage_budget)
    plan = fg.spec_cardinality_plan(spec)
    try:
        plan_contract = contract_from_spec(spec)
    except OptionalContractError as exc:
        raise PreflightError(f"optional-table contract is unsatisfiable: {exc}")
    sha = file_sha256(toml_path)
    slots = [_slot_summary(s) for s in spec.slots]
    warnings = _plan_warnings(spec, plan)
    # Plan-1 Phase 2 (docs/24 §3): the repeat count plan — plan-only here (no gate; a K>1 run
    # is refused later by `_check_budgets`). `validate_repeat` raises a named ConfigError on an
    # invalid combination (e.g. nested K>1 without --repeat-environments).
    cfg, cfg_sources = _resolve_bundle_config(a)
    repeat_policy, repeat_scope, repeat_k, repeat_e = cfg.validate_repeat()
    cplan = count_plan(repeat_policy, repeat_scope, plan.final, repeat_k, repeat_e)
    res_plan = estimate_resources(
        plan,
        thresholds=ResourceThresholds(smoke_max=a.class_smoke_max, bounded_max=a.class_bounded_max,
                                       large_max=a.class_large_max),
        template_sample_bytes=a.template_sample_bytes if a.template_sample_bytes else None,
        per_candidate_seconds=(a.per_candidate_seconds_min, a.per_candidate_seconds_max),
        cost_per_candidate=a.cost_per_candidate if a.cost_per_candidate is not None else None,
        count_plan=cplan,
    )
    # Plan-1 Phase 2 (Automation #29 finding 1): evaluate the SAME budget contract against the
    # repeat-aware ResourcePlan, so `bundle plan` actually answers whether a K>1 campaign violates
    # a hard ceiling (the run path refuses K>1 *before* budget evaluation). Plan mode is
    # analysis-only: a BLOCKING projection is printed prominently and persisted in plan.json, but
    # the artifact is still written and the process exits 0 — the report is the deliverable; the
    # run path is the enforcement point.
    budget_checks = evaluate_budgets(plan, res_plan, _budget_limits_from_config(cfg))
    budget_blocking = blocking_checks(budget_checks)

    print(f"spec '{spec.name}'  ({toml_path})")
    print(f"  spec_version={spec.spec_version}  sha256={sha}")
    print(f"  slots: {len(spec.slots)}   seq_extra rows: {len(spec.seq_extra)}")
    print("operator table:")
    for s in slots:
        flags = f" flags={s['flags']}" if s["flags"] else ""
        print(f"  {s['sheet']}: {s['verb']}  n={s['n']}{flags}")
    print(f"constraints present: {len(spec.constraints)}")
    if plan_contract.active:
        print(f"optional table contract: {plan_contract.optional_sheet_count} FW_Optional sheet(s), "
              f"Core produces [{plan_contract.core_property_value()}], "
              f"Reader consumes [{plan_contract.reader_property_value()}] "
              f"({plan_contract.mode}) -> ×{plan_contract.expected_multiplier()} per fw_final row")
    print()
    print(fg.format_cardinality_plan(plan))
    print()
    # the human output must distinguish "before sieve" (mandatory) from "after
    # sieve estimate" (post_sieve) — STEP 10 action 6.
    print(f"summary: mandatory={plan.mandatory.value} ({plan.mandatory.mode.value}, before sieve)  "
          f"post-sieve={plan.post_sieve.value} ({plan.post_sieve.mode.value}, after-sieve estimate)  "
          f"optional×{plan.optional_multiplier.value} ({plan.optional_multiplier.mode.value})  "
          f"final={plan.final.value} ({plan.final.mode.value})")
    print()
    print(format_resource_plan(res_plan))
    print()
    if cplan.topology_inactive:
        print("repeat plan: K=1 — repeat topology inactive (A=V=I=C); legacy single-run path")
    else:
        def _cv(est):
            return "UNKNOWN" if est.value is None else est.value
        print(f"repeat plan: policy={cplan.policy} scope={cplan.scope} K={cplan.k} "
              f"E={cplan.e_effective} (E source: {cfg_sources.get('repeat_environments', 'default')})")
        print(f"  assignments A={_cv(cplan.A)}  verdicts V={_cv(cplan.V)}  "
              f"opportunities I={_cv(cplan.I)}  metric_only={_cv(cplan.metric_only_invocations)}")
        print("  NOTE: local/metrics K>1 is EXECUTABLE on both Executors (Python & Java); "
              "scope=all / disperse / nested remain PLAN-ONLY — refused with "
              "REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY (docs/24 §4)")
    print()
    print("budget evaluation (analysis-only; the run path is the enforcement point):")
    for c in budget_checks:
        print(f"  [{c.severity.value}] {c.message}")
    if budget_blocking:
        print(f"  ⛔ BUDGET BLOCKING: {len(budget_blocking)} dimension(s) over a hard ceiling "
              f"({', '.join(c.dimension for c in budget_blocking)})")
    print()
    if warnings:
        print(f"warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("warnings: none")

    out_dir = Path(a.out) if a.out else Path(a.spec_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "plan.json"
    write_json_atomic(plan_path, {
        "schema": PLAN_SCHEMA,
        "spec_name": spec.name,
        "spec_path": str(toml_path),
        "spec_sha256": sha,
        "spec_version": spec.spec_version,
        "slots": slots,
        "seq_extra_rows": len(spec.seq_extra),
        "constraints_present": len(spec.constraints),
        "cardinality": fg.cardinality_plan_to_dict(plan),
        "resources": resource_plan_to_dict(res_plan),
        "repeat_plan": cplan.to_dict(),                            # Plan-1 Phase 2 (docs/24 §3)
        "repeat_environments_source": cfg_sources.get("repeat_environments", "default"),
        "budget_checks": [budget_check_to_dict(c) for c in budget_checks],   # Automation #29 finding 1
        "budget_blocking": [c.dimension for c in budget_blocking],
        # Audit F4: the optional-table contract is validated during side-effect-free
        # planning, so an unsatisfiable R ⊆ P is rejected before Core and Reader do
        # any expensive work rather than after.
        "optional_table_contract": plan_contract.to_dict(),
        "dependency_graph": _seq_graph.graph_plan_block(graph),    # STEP 37: graph + graph_hash (gated above)
        "warnings": warnings,
    })
    ok(f"plan -> {plan_path}  (FW_Seq graph {graph.graph_hash()})")


def _main_plan(argv):
    ap = argparse.ArgumentParser(prog="bundle_run plan",
                                 description="Estimate a spec's run shape (cardinality/exactness) "
                                             "without creating a DB, running Core/Reader/Executor, "
                                             "or producing any candidates.")
    ap.add_argument("spec_dir")
    ap.add_argument("--out", default="", help="directory to write plan.json into (default: spec_dir)")
    _add_repeat_args(ap)
    ap.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON object of BundleConfig overrides (incl. budget ceilings); lowest-"
                         "precedence layer above defaults (Automation #29 finding 1: layered budgets in plan)")
    _add_budget_ceiling_args(ap)
    # STEP 11: run-class thresholds and resource-estimate inputs are
    # configurable rather than hardcoded — defaults are conservative
    # placeholders pending real measurement (see ResourceThresholds docstring).
    ap.add_argument("--class-smoke-max", type=int, default=ResourceThresholds().smoke_max,
                    help="final-candidate-count ceiling for run class S (smoke)")
    ap.add_argument("--class-bounded-max", type=int, default=ResourceThresholds().bounded_max,
                    help="final-candidate-count ceiling for run class B (bounded)")
    ap.add_argument("--class-large-max", type=int, default=ResourceThresholds().large_max,
                    help="final-candidate-count ceiling for run class L (large); above this is X (extreme)")
    ap.add_argument("--template-sample-bytes", type=int, default=0,
                    help="size in bytes of a real candidate-source template sample, "
                         "for a sound 'candidate source bytes' estimate (default: generic placeholder range)")
    ap.add_argument("--per-candidate-seconds-min", type=float, default=DEFAULT_PER_CANDIDATE_SECONDS[0],
                    help="lower bound of the assumed per-candidate execution cost in seconds "
                         "(single worker; drives the execution-duration estimate)")
    ap.add_argument("--per-candidate-seconds-max", type=float, default=DEFAULT_PER_CANDIDATE_SECONDS[1],
                    help="upper bound of the assumed per-candidate execution cost in seconds "
                         "(single worker; drives the execution-duration estimate)")
    ap.add_argument("--cost-per-candidate", type=float, default=None,
                    help="optional flat monetary cost per candidate; enables the monetary-cost estimate")
    ap.add_argument("--coverage-strength", type=int, default=0, metavar="T",
                    help="opt into t-wise covering-array reduction before Core (0 = off): "
                         "keep the smallest suite that still covers every T-tuple of "
                         "(slot, value). Overrides the spec's coverage_strength.")
    ap.add_argument("--coverage-optimal", action="store_true",
                    help="use minimum set-cover instead of streaming greedy — a markedly "
                         "smaller suite (measured 18 vs 144 rows at t=2) at the cost of "
                         "holding the tuple universe in RAM. Do NOT combine with "
                         "--coverage-budget on a wide spec: that search starts at the "
                         "highest strength, where set-cover does not finish in useful time")
    ap.add_argument("--coverage-budget", type=int, default=0, metavar="N",
                    help="ignore --coverage-strength and pick the most thorough strength "
                         "whose suite fits N candidates")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_plan(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
