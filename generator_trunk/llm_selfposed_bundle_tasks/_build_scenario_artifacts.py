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

"""Build evidence-backed scenario artifacts (zen_mapping/result_card/run_report/problem)
from the REAL Bundle run directories. Faithful: reads metrics.kv / provenance.json /
plan.json from each run, snapshots the numbers into the scenario dir so the evidence is
durable in the repo. Run from generator_trunk/."""
from __future__ import annotations
import hashlib, json, re, sys
from collections import Counter
from pathlib import Path

LAB = Path("llm_selfposed_bundle_tasks")
FWWORK = Path("/tmp/fw_work")

# Per-scenario authored metadata + run mapping. category, user_problem, bundle_offer,
# hypothesis, zen_mapping, entities, verdict_codes, run(db,run_id,sieve), pattern.
S = {
 "01_order_record_clean": {
   "category": "order-sensitive pipeline",
   "user_problem": "I have a customer list with messy duplicates (same person, different case/spacing) and some missing emails. I want to normalize, apply a null-email policy, and de-duplicate — but does the ORDER of those steps change correctness?",
   "bundle_offer": "Bundle enumerates every order of the three cleaning steps (a permutation), crosses it with the null-policy and dedupe-key, runs each pipeline on a fixed dataset, and a data-quality oracle reports which orders silently leak duplicates or nulls.",
   "hypothesis": "Orders that run dedupe before normalize fail to collapse case/spacing variants -> a duplicate id survives (DOMAIN_FAIL).",
   "zen_mapping": [
     {"freedom": "cleaning-step order", "shape": "an ordering", "verb": "FW_Permut", "cardinality": "3! = 6"},
     {"freedom": "null-email policy", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "dedupe key", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"}],
   "goals": [{"key": "rows_out", "dir": "max"}],
   "oracle": "FW_VAR=2 duplicate id survived; FW_VAR=3 null email leaked under non-keep policy; FW_VAR=0 clean",
   "verdict_codes": {"0": "PASS (clean, deduped, policy-consistent)", "2": "duplicate id survived (dedupe ran before normalize)", "3": "null email leaked despite a non-keep policy"},
   "pattern": "usecases/etl_pipeline",
   "run": ("llm_selfposed_01_order", "llm-selfposed-01-order-001", False)},
 "02_optional_queue_saga": {
   "category": "optional sudden actions",
   "user_problem": "My message-queue consumer does fetch -> process -> ack. I also worry about a redelivery (the same message arriving twice) and a crash before ack. Which orderings and which fault combinations break correctness?",
   "bundle_offer": "Bundle runs the consumer steps in every order and bolts on two optional 'sudden actions' (redelivery, crash-before-ack) as a separate dimension, then a saga oracle checks ordering, idempotency, and liveness across all combinations.",
   "hypothesis": "Only fetch<process<ack is valid; a redelivery without an idempotency key double-processes; a crash before ack loses liveness.",
   "zen_mapping": [
     {"freedom": "consumer step order", "shape": "an ordering", "verb": "FW_Permut", "cardinality": "3! = 6"},
     {"freedom": "redelivery may or may not fire", "shape": "may-or-may-not (sudden action)", "verb": "FW_Optional", "cardinality": "x2"},
     {"freedom": "crash-before-ack may or may not fire", "shape": "may-or-may-not (sudden action)", "verb": "FW_Optional", "cardinality": "x2"}],
   "goals": [{"key": "process_count", "dir": "min"}],
   "oracle": "FW_VAR=3 process before fetch; 2 ack before process; 4 double-process; 5 not-acked without crash cause; 0 PASS",
   "verdict_codes": {"0": "PASS", "2": "ack before process (order violation)", "3": "process before fetch (order violation)", "4": "double process (idempotency violation on redelivery)", "5": "not acknowledged without a crash cause (liveness violation)"},
   "pattern": "usecases/event_order",
   "run": ("llm_selfposed_02_saga", "llm-selfposed-02-saga-001", False)},
 "03_pareto_cache_design": {
   "category": "design-space / Pareto",
   "user_problem": "I'm choosing a cache layer: eviction policy, size, TTL, and whether to prefetch. Every choice is valid; I want the best trade-offs of hit-rate, memory, and tail latency.",
   "bundle_offer": "Bundle enumerates the full design space (one choice per axis), evaluates each with a deterministic surrogate cost model, and the Analyzer returns the non-dominated (Pareto) configs over three conflicting objectives.",
   "hypothesis": "No single config wins all three objectives; a Pareto front of trade-offs exists.",
   "zen_mapping": [
     {"freedom": "eviction policy", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "cache size", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "entry TTL", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "prefetch toggle", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"}],
   "goals": [{"key": "hit_rate", "dir": "max"}, {"key": "memory_mb", "dir": "min"}, {"key": "p99_latency_ms", "dir": "min"}],
   "oracle": "FW_VAR=0 for every config (optimization, not pass/fail); the Analyzer selects, it does not reject",
   "verdict_codes": {"0": "valid configuration (optimization selects among them)"},
   "pattern": "usecases/perf_opt",
   "run": ("llm_selfposed_03_cache", "llm-selfposed-03-cache-001", False)},
 "04_ml_rerank_eval": {
   "category": "ML/LLM outer-structure evaluation",
   "user_problem": "For a text classifier I can vary the preprocessing order, the retrieval chunk size, and whether to use a reranker. Which outer structures clear my quality bar, and what do they cost?",
   "bundle_offer": "Bundle treats the discrete OUTER structure as the freedom (preprocessing order is a permutation; chunk and reranker are exactly-one choices), evaluates each with a LOCAL deterministic surrogate, applies a quality-gate oracle, and Pareto-ranks accuracy vs latency vs cost.",
   "hypothesis": "Some preprocessing orders and the smallest chunk without a reranker fall below the 0.75 accuracy gate (DOMAIN_FAIL).",
   "zen_mapping": [
     {"freedom": "preprocessing order", "shape": "an ordering", "verb": "FW_Permut", "cardinality": "3! = 6"},
     {"freedom": "retrieval chunk size", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "reranker on/off", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"}],
   "goals": [{"key": "accuracy", "dir": "max"}, {"key": "latency_ms", "dir": "min"}, {"key": "cost_usd", "dir": "min"}],
   "oracle": "FW_VAR=4 below the 0.75 quality gate (DOMAIN_FAIL); FW_VAR=0 passes",
   "verdict_codes": {"0": "PASS (>= quality gate)", "4": "below quality gate (accuracy < 0.75)"},
   "pattern": "usecases/ml_eval",
   "run": ("llm_selfposed_04_rerank", "llm-selfposed-04-rerank-001", False)},
 "05_sieve_deploy_matrix": {
   "category": "constraint / sieve",
   "user_problem": "I deploy across regions, plan tiers, and replica counts, but some combinations are illegal before I even run them (the free tier isn't allowed in data-residency-restricted regions). I also want a runtime check that enterprise tiers are sufficiently replicated.",
   "bundle_offer": "Bundle declares value attributes ([[params]]) and a binary when-rule ([[constraints]]); the SIEVE deletes the illegal region/tier combinations from the space BEFORE any execution, then the oracle catches the remaining runtime policy (enterprise under-replication).",
   "hypothesis": "The sieve removes free-tier x restricted-region rows pre-execution; the oracle flags enterprise tier with < 3 replicas at runtime.",
   "zen_mapping": [
     {"freedom": "region", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "4"},
     {"freedom": "plan tier", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "replica count", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "free-tier-in-restricted-region is FORBIDDEN", "shape": "a bond (pre-execution invalidity)", "verb": "[[constraints]] sieve (NOT a verb)", "cardinality": "removes 6 rows"}],
   "goals": [{"key": "replicas", "dir": "max"}],
   "oracle": "sieve removes structurally-invalid combos pre-exec; FW_VAR=2 enterprise under-replicated (replicas<3) at runtime; FW_VAR=0 valid",
   "verdict_codes": {"0": "PASS (valid deployment)", "2": "enterprise tier under-replicated (replicas < 3)"},
   "pattern": "constraints/diff_fuzz_when",
   "run": ("llm_selfposed_05_deploy", "llm-selfposed-05-deploy-001", True)},
 "06_secondorder_release_join": {
   "category": "second-order composition (brace)",
   "user_problem": "I want to build candidate pairs of migration steps (choose 2 of 3) and then JOIN each pair with a target region to get composed release plans.",
   "bundle_offer": "Bundle's brace FW_(...) is a second-order JOIN of two PRIOR result tables: operand A = choose-2-of-3 steps (its result table is 3 pairs), operand B = choose-1-of-2 regions (2 rows); the M:N brace joins those result tables into 6 composed plans.",
   "hypothesis": "The brace consumes the combination-RESULTS of earlier rows (not raw sheets); the join yields 3 x 2 = 6 plans.",
   "zen_mapping": [
     {"freedom": "choose 2 of 3 migration steps", "shape": "k of n, order irrelevant", "verb": "FW_Combi(2) (FW_Exclude'd operand)", "cardinality": "C(3,2)=3 pairs"},
     {"freedom": "choose 1 of 2 regions", "shape": "exactly one of a set", "verb": "FW_Combi(1) (FW_Exclude'd operand)", "cardinality": "2"},
     {"freedom": "join the two prior result tables", "shape": "join two prior results", "verb": "brace FW_(,,A,,B,,,,M:N)", "cardinality": "3 x 2 = 6 (UNKNOWN to planner -> class X)"}],
   "goals": [{"key": "steps", "dir": "max"}],
   "oracle": "FW_VAR=0 (this scenario demonstrates the second-order join shape, not a pass/fail oracle)",
   "verdict_codes": {"0": "composed plan"},
   "pattern": "brace_demo",
   "plan_only_summary": "Plan + graph only (second-order brace; effective class X because cardinality is UNKNOWN). ",
   "run": None},  # plan + graph only: UNKNOWN cardinality -> class X; running needs --allow-extreme (prohibited here)
 "07_constraint_arity": {
   "category": "constraint arity (binary vs ternary)",
   "user_problem": "I deploy across region, tier, and replicas. One forbidden rule is binary (free tier in a restricted region), but another is a true 3-way rule (enterprise tier in a restricted region with a single replica). What can Bundle enforce before execution, and what can't it?",
   "bundle_offer": "Bundle's sieve v1 executes BINARY [[constraints]] (two sheets) and prunes them before execution; a true ternary (3-sheet) bond is REPORTED as unsupported (never silently skipped) and must be decomposed into binary rules or enforced by the TAIL oracle at runtime.",
   "hypothesis": "The binary free-tier rule removes 6 rows in the sieve; the ternary rule is reported unsupported, and the oracle catches the enterprise+restricted+single-replica candidates as DOMAIN_FAIL.",
   "zen_mapping": [
     {"freedom": "region", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "4"},
     {"freedom": "tier", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "replicas", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "binary bond (free x restricted)", "shape": "a bond, arity 2", "verb": "[[constraints]] sieve v1 (executable)", "cardinality": "removes 6"},
     {"freedom": "ternary bond (ent x restricted x single replica)", "shape": "a bond, arity 3", "verb": "reported unsupported -> decompose or oracle", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "replicas", "dir": "max"}],
   "oracle": "sieve v1 applies the binary bond (36->30); the ternary bond is reported unsupported and the TAIL oracle sets FW_VAR=2 for enterprise+restricted+single-replica; else 0",
   "verdict_codes": {"0": "PASS (valid deployment)", "2": "ternary bond violated (enterprise tier in a restricted region with a single replica) - caught by the oracle because sieve v1 cannot express a 3-sheet rule"},
   "pattern": "constraints/diff_fuzz_when",
   "run": ("llm_selfposed_07_arity", "llm-selfposed-07-arity-001", True)},
 "08_ci_release_matrix": {
   "category": "CI/CD release matrix",
   "user_problem": "I run releases across services. I can vary deployment strategy, database migration kind, test scope, and feature flag state. Which combinations are structurally unsafe before execution, and which risky release plans should the oracle catch?",
   "bundle_offer": "Bundle enumerates the release matrix, applies a binary sieve rule to remove direct deploys with breaking database migrations before execution, runs each surviving release plan through a deterministic safety oracle, and returns a Pareto front over risk, duration, and rollback strength.",
   "hypothesis": "The sieve removes 12 direct+breaking-migration rows from 108 raw combinations; the oracle catches smoke-tested breaking migrations and smoke-tested canary+feature-flag releases; Analyzer exposes the risk/duration/rollback tradeoff.",
   "zen_mapping": [
     {"freedom": "service", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "release strategy", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "database migration kind", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "test scope", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "feature flag state", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "direct deploy with breaking migration is forbidden", "shape": "a binary pre-execution bond", "verb": "[[constraints]] sieve v1", "cardinality": "removes 12"}],
   "goals": [{"key": "risk_score", "dir": "min"}, {"key": "duration_min", "dir": "min"}, {"key": "rollback_score", "dir": "max"}],
   "oracle": "sieve removes direct+breaking migration pre-execution; FW_VAR=2 for breaking migration with smoke tests only; FW_VAR=3 for canary+feature-flag with smoke tests only; FW_VAR=0 accepted release plan",
   "verdict_codes": {"0": "PASS (release plan accepted)", "2": "breaking migration released with smoke tests only", "3": "canary with enabled feature flag released with smoke tests only"},
   "pattern": "release-engineering safety matrix",
   "run": ("llm_selfposed_08_ci_release", "llm-selfposed-08-ci-release-001", True)},
 "09_api_compat_matrix": {
   "category": "API compatibility matrix",
   "user_problem": "I maintain an API with v1/v2/v3 versions and several client SDK generations. I need to test which client/auth/payload combinations are compatible, which pairs are structurally unsupported, and which trade-offs are best for compatibility, latency, and migration effort.",
   "bundle_offer": "Bundle enumerates API version, client SDK, auth scheme, and payload shape; the binary sieve removes unsupported legacy-SDK/v3 pairs before execution; the TAIL oracle catches executable but incompatible payload/auth cases; the Analyzer returns a compatibility/latency/migration-effort Pareto front.",
   "hypothesis": "The sieve removes 9 legacy-SDK/v3 rows from 81 raw combinations; the oracle catches v1+bulk payloads and beta-SDK JWT legacy payloads; Analyzer exposes the compatibility/latency/migration trade-off.",
   "zen_mapping": [
     {"freedom": "API version", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "client SDK generation", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "auth scheme", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "payload shape", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "legacy SDK against v3 API is forbidden", "shape": "a binary pre-execution contract bond", "verb": "[[constraints]] sieve v1", "cardinality": "removes 9"}],
   "goals": [{"key": "compat_score", "dir": "max"}, {"key": "latency_ms", "dir": "min"}, {"key": "migration_effort", "dir": "min"}],
   "oracle": "sieve removes legacy_sdk+v3 API pre-execution; FW_VAR=2 for v1 API with bulk_json payload; FW_VAR=3 for beta_sdk+jwt+legacy_json; FW_VAR=0 compatible combination",
   "verdict_codes": {"0": "PASS (compatible API/client/auth/payload combination)", "2": "v1 API cannot accept bulk_json payloads", "3": "beta SDK JWT path requires modern/bulk payload claims"},
   "pattern": "API/client/payload contract matrix",
   "run": ("llm_selfposed_09_api_compat", "llm-selfposed-09-api-compat-001", True)},
 "10_feature_flag_interaction": {
   "category": "feature-flag interaction (FW_Subsets)",
   "user_problem": "My service has several feature flags; ANY subset can be enabled, and some flag combinations interact badly. I also roll out in stages. Which flag sets are safe, and which interactions break?",
   "bundle_offer": "Bundle models WHICH flags are enabled as FW_Subsets (any subset, 2^n) crossed with the rollout stage; the TAIL oracle catches flag interactions (a dependency, a conflicting pair) because a within-subset bond is not a binary 2-sheet sieve rule; the Analyzer returns a capability-vs-risk Pareto front.",
   "hypothesis": "Subsets enabling experimental_ui without new_router fail a dependency; audit+cache in canary conflict; the rest pass.",
   "zen_mapping": [
     {"freedom": "which feature flags are enabled", "shape": "any subset (incl. none)", "verb": "FW_Subsets", "cardinality": "2^4 = 16"},
     {"freedom": "rollout stage", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "flag dependency / conflicting pair", "shape": "a within-subset bond (not a binary sieve rule)", "verb": "TAIL oracle (FW_VAR)", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "enabled_flags", "dir": "max"}, {"key": "risk_score", "dir": "min"}],
   "oracle": "FW_VAR=2 experimental_ui without new_router (dependency); FW_VAR=3 audit+cache in canary (conflict); FW_VAR=0 safe",
   "verdict_codes": {"0": "PASS (safe flag set)", "2": "feature dependency violated (experimental_ui without new_router)", "3": "canary resource conflict (audit + cache in canary)"},
   "pattern": "secure_pipeline FW_Subsets features",
   "run": ("llm_selfposed_10_flags", "llm-selfposed-10-flags-001", False)},
 "11_db_config_cartes": {
   "category": "DB-config tuning / FW_Cartes workload matrix",
   "user_problem": "I tune PostgreSQL-like database configs across workload classes and data sizes. I need to cross config profiles with OLTP/analytics/mixed workloads, catch under-provisioned combinations, and compare p95 latency, cost, and stability.",
   "bundle_offer": "Bundle models DB config profile as FW_Cartes(WORKLOAD), crossing each config profile with each workload class, then crosses that matrix with data size. The TAIL oracle catches workload-specific under-provisioning and the Analyzer exposes p95/cost/stability trade-offs.",
   "hypothesis": "The 3 config profiles x 3 workload classes x 2 data sizes produce 18 candidates; analytics workloads fail when work_mem is below 64 MB, OLTP workloads fail when pool_size is below 32, and the remaining candidates form a p95/cost/stability trade-off set.",
   "zen_mapping": [
     {"freedom": "DB config profile crossed with workload class", "shape": "cross another sheet", "verb": "FW_Cartes(WORKLOAD)", "cardinality": "3 x 3 = 9 matrix cells"},
     {"freedom": "workload class operand", "shape": "exactly one of a set, set aside as the Cartes operand", "verb": "FW_Combi(1) + FW_Exclude", "cardinality": "3 operand values"},
     {"freedom": "data size", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "workload/config compatibility", "shape": "runtime domain policy", "verb": "TAIL oracle (FW_VAR)", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "p95_ms", "dir": "min"}, {"key": "cost_units", "dir": "min"}, {"key": "stability_score", "dir": "max"}],
   "oracle": "FW_VAR=2 analytics workload under-provisioned when work_mem < 64 MB; FW_VAR=3 OLTP workload under-provisioned when pool_size < 32; FW_VAR=0 acceptable",
   "verdict_codes": {"0": "PASS (config/workload/data-size combination accepted)", "2": "analytics workload under-provisioned: work_mem below 64 MB", "3": "OLTP workload under-provisioned: pool_size below 32"},
   "pattern": "database config workload matrix",
   "run": ("llm_selfposed_11_db_cartes", "llm-selfposed-11-db-cartes-001", False)},
 "12_fallback_sequence_permutr": {
   "category": "service fallback sequence (FW_PermutR)",
   "user_problem": "I design a service fallback strategy with three ordered probe slots. Each slot can probe cache, replica, or primary, and repeats are allowed. I need to know which repeated sequences are deployable for interactive and critical traffic, and compare availability, latency, and cost.",
   "bundle_offer": "Bundle models the fallback probe sequence as FW_PermutR(3): an ordered length-3 sequence where the same probe may repeat. It crosses the repeated sequence with request class, runs a TAIL oracle for deployability, and returns an availability/latency/cost Pareto front with PASS-aware front annotations.",
   "hypothesis": "Three probes over three positions produce 3^3 = 27 ordered sequences with repetition; crossing two request classes produces 54 candidates. Critical traffic fails without a primary probe, interactive traffic fails when it starts with primary, and all-identical or over-budget sequences fail policy.",
   "zen_mapping": [
     {"freedom": "three-step fallback probe sequence", "shape": "a sequence with repetition", "verb": "FW_PermutR(3)", "cardinality": "3^3 = 27"},
     {"freedom": "request class", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "fallback deployability policy", "shape": "runtime domain policy", "verb": "TAIL oracle (FW_VAR)", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "availability_score", "dir": "max"}, {"key": "latency_ms", "dir": "min"}, {"key": "cost_units", "dir": "min"}],
   "oracle": "FW_VAR=2 critical sequence never probes primary; FW_VAR=3 interactive sequence starts with expensive primary; FW_VAR=4 sequence has no diversity or exceeds latency budget; FW_VAR=0 deployable",
   "verdict_codes": {"0": "PASS (deployable fallback sequence)", "2": "critical request sequence never probes primary", "3": "interactive request sequence starts with expensive primary probe", "4": "fallback sequence policy violation: no diversity or latency budget exceeded"},
   "pattern": "service fallback repeated sequence",
   "run": ("llm_selfposed_12_permutr_v2", "llm-selfposed-12-permutr-002", False)},
 "13_resource_multiset_combir": {
   "category": "resource allocation multiset (FW_CombiR)",
   "user_problem": "I allocate 3 worker slots from instance types {cpu, gpu, mem}, and I can pick the same type more than once. Which allocation mixes are safe for batch vs serving, and how do diversity and cost trade off?",
   "bundle_offer": "Bundle models the allocation as FW_CombiR(3): a size-3 MULTISET over the instance types (repetition allowed) crossed with the workload class; a resource-mix oracle flags zero-diversity (single point of failure) and serving-without-gpu; the Analyzer returns a diversity-vs-cost Pareto front.",
   "hypothesis": "All-identical allocations are single points of failure (DOMAIN_FAIL); serving with no gpu slot fails; the rest pass; cost rises with gpu slots.",
   "zen_mapping": [
     {"freedom": "3 worker slots from 3 instance types, repetition allowed", "shape": "k of n WITH repetition", "verb": "FW_CombiR(3)", "cardinality": "C(5,3) = 10"},
     {"freedom": "workload class", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "resource-mix policy", "shape": "runtime domain policy", "verb": "TAIL oracle (FW_VAR)", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "diversity", "dir": "max"}, {"key": "cost_units", "dir": "min"}],
   "oracle": "FW_VAR=2 zero diversity (all slots same type); FW_VAR=3 serving without a gpu slot; FW_VAR=0 safe (codes kept small to fit combo-column capacity)",
   "verdict_codes": {"0": "PASS (safe allocation)", "2": "zero diversity: all 3 slots same type (single point of failure)", "3": "serving workload allocated no gpu slot"},
   "pattern": "resource multiset allocation",
   "run": ("llm_selfposed_13_combir", "llm-selfposed-13-combir-001", False)},
 "14_control_pair_combi2": {
   "category": "security control pair selection (FW_Combi(2))",
   "user_problem": "I need to choose exactly two security controls from rate_limit, captcha, waf, and review_queue. Order does not matter and repeats are not allowed. Which pairs are safe for public API and admin API traffic, and how do coverage, friction, and cost trade off?",
   "bundle_offer": "Bundle models the control pair as FW_Combi(2): choose exactly two distinct controls, order irrelevant. It crosses the pair with traffic profile, uses a TAIL oracle for admin-without-WAF and public excessive-friction policies, and returns a coverage/friction/cost Pareto front with PASS-aware annotations.",
   "hypothesis": "Four controls choose two gives C(4,2)=6 pairs; crossing public/admin traffic gives 12 candidates. Admin traffic fails without WAF, public traffic fails for captcha+review_queue, and the remaining pairs form a coverage/friction/cost trade-off.",
   "zen_mapping": [
     {"freedom": "choose exactly two security controls", "shape": "k of n, order irrelevant, no repetition", "verb": "FW_Combi(2)", "cardinality": "C(4,2) = 6"},
     {"freedom": "traffic profile", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "2"},
     {"freedom": "control-pair policy", "shape": "runtime domain policy", "verb": "TAIL oracle (FW_VAR)", "cardinality": "oracle DOMAIN_FAIL"}],
   "goals": [{"key": "coverage_score", "dir": "max"}, {"key": "friction_score", "dir": "min"}, {"key": "cost_units", "dir": "min"}],
   "oracle": "FW_VAR=2 admin traffic pair is missing WAF; FW_VAR=3 public traffic pair has excessive friction; FW_VAR=0 safe",
   "verdict_codes": {"0": "PASS (safe control pair)", "2": "admin traffic control pair is missing WAF", "3": "public traffic control pair has excessive user friction"},
   "pattern": "security control choose-k pair",
   "run": ("llm_selfposed_14_combi2", "llm-selfposed-14-combi2-001", False)},
 "15_secondorder_group_rewrite": {
   "category": "second-order recombination (FW_Group + FW_ReplaceRE + FW_Separator)",
   "user_problem": "I want to take audit-tag subsets and RE-COMBINE those results into groups, rewriting the codes and gluing tokens between elements -- combinations of combinations. What does Bundle do, and can I run it safely?",
   "bundle_offer": "Bundle's UNARY second-order operator: FW_Group re-combines a sheet's PRIOR result rows (combinations of combinations), FW_ReplaceRE rewrites the Core code-string, and FW_Separator weaves a glue token. Authored with fwgen first-class group_replace= and separator= fields. Like the brace, it is a second-order verb the planner cannot estimate, so it is PLAN + GRAPH only in the safe path.",
   "hypothesis": "FW_Subsets over 3 tags -> 8 result rows; FW_Group recombines them into the second-order space (the planner under-estimates this), so a forced full run trips the reader_emitted_eq_expected invariant.",
   "zen_mapping": [
     {"freedom": "tag subsets (prior result rows)", "shape": "any subset", "verb": "FW_Subsets", "cardinality": "2^3 = 8 rows"},
     {"freedom": "re-combine + rewrite those prior rows", "shape": "re-combine + rewrite a prior result", "verb": "FW_Group + FW_ReplaceRE", "cardinality": "second-order (UNKNOWN to planner)"},
     {"freedom": "glue token between elements", "shape": "weave a glue token", "verb": "FW_Separator(GLUE)", "cardinality": "row-preserving modifier"}],
   "goals": [{"key": "groups", "dir": "max"}],
   "oracle": "FW_VAR=0 (this scenario demonstrates the second-order recombination shape, not a pass/fail oracle)",
   "verdict_codes": {"0": "recombined tag group"},
   "pattern": "group_sep_demo + ZEN canonical FW_Group",
   "plan_only_reason": "Second-order FW_Group: the planner estimates only the base verb (FW_Subsets=8) and cannot fold in FW_Group's recombination, so it under-counts. A forced full run materialized fw_final=206 in Core (vs estimate 8) and tripped the CRITICAL reader_emitted_eq_expected invariant (expected 8, got 206). Hence PLAN + GRAPH only in the safe path (like the brace, scenario 06); a real second-order run needs explicit handling, not the default invariant chain.",
   "plan_only_summary": "Plan + graph only (planner reports S from the base FW_Subsets=8, but safe policy treats FW_Group as effective class X because Core materializes the second-order space). ",
   "run": None},
 "16_security_redteam_matrix": {
   "category": "security red-team (order + sudden attacks)",
   "user_problem": "A request passes security checks (authn, authz, ratelimit) in some order, and an attacker may fire sudden steps (token replay, privilege escalation). Which check orders and which attacks cause a breach?",
   "bundle_offer": "Bundle runs the security checks in every order (FW_Permut) and bolts on optional sudden attacks (FW_Optional: token replay, privilege escalation); a breach oracle reports which order+attack combinations slip through -- the engine's strongest story (interactions, order, sudden state-changes).",
   "hypothesis": "Authorizing before authenticating is broken access control; a replay slips through when authn is not bound first; escalation slips through when ratelimit precedes authz.",
   "zen_mapping": [
     {"freedom": "security check order", "shape": "an ordering", "verb": "FW_Permut", "cardinality": "3! = 6"},
     {"freedom": "token-replay attack may or may not fire", "shape": "may-or-may-not (sudden action)", "verb": "FW_Optional", "cardinality": "x2"},
     {"freedom": "privilege-escalation attack may or may not fire", "shape": "may-or-may-not (sudden action)", "verb": "FW_Optional", "cardinality": "x2"}],
   "goals": [{"key": "breach", "dir": "max"}],
   "oracle": "FW_VAR=2 authz before authn; FW_VAR=3 token replay (authn not first); FW_VAR=4 privilege escalation (ratelimit before authz); FW_VAR=0 secure",
   "verdict_codes": {"0": "PASS (secure: checks in order, attacks blocked)", "2": "broken access control: authorize before authenticate", "3": "token replay accepted: authn not bound first", "4": "privilege escalation: rate limiting before the authorization check"},
   "pareto_front_note": "red-team run: the formal front intentionally maximizes breach, so DOMAIN_FAIL front members are the desired security findings; PASS candidates are secure baselines, not the optimization target",
   "pattern": "tryout_own/spec (secure pipeline) + event_order",
   "run": ("llm_selfposed_16_redteam", "llm-selfposed-16-redteam-001", False)},
 "17_qa_pub_joke_promo": {
   "category": "promo/demo (QA tester walks into a pub)",
   "user_problem": "Turn the classic 'a QA tester walks into a pub and orders 1, 0, -1, 999999999, abcd beers, a lizard...' joke into a real Bundle test: different entries, weird quantities, weird targets, and permuted action order; the bar must never crash.",
   "bundle_offer": "Bundle makes boundary/type/domain abuse FIRST-CLASS values and generates invalid action orders ON PURPOSE (FW_Permut), not by chance; the oracle separates clean rejection from a crash or silent accept. A one-minute Bundle explainer. Motto: 'Bundle walks into the pub before your users do.'",
   "hypothesis": "Acting before entering is an order bug; non-numeric/negative/huge quantities must be rejected cleanly (never crash/overflow); a lizard is an invalid target; normal and zero-no-op orders pass.",
   "zen_mapping": [
     {"freedom": "entry mode", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"},
     {"freedom": "action order", "shape": "an ordering", "verb": "FW_Permut", "cardinality": "3! = 6"},
     {"freedom": "order quantity (boundary/type/domain)", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "5"},
     {"freedom": "order target", "shape": "exactly one of a set", "verb": "FW_Combi(1)", "cardinality": "3"}],
   "goals": [{"key": "accepted", "dir": "max"}],
   "oracle": "FW_VAR=2 acted before entering; FW_VAR=3 invalid quantity rejected cleanly (type/domain/huge); FW_VAR=4 invalid target (lizard); FW_VAR=0 accepted (normal or zero no-op)",
   "verdict_codes": {"0": "PASS (normal or zero-no-op order accepted)", "2": "invalid action order (acted before entering)", "3": "invalid quantity rejected cleanly (type/domain/over-capacity)", "4": "invalid order target rejected cleanly (a lizard)"},
   "pattern": "boundary/type/domain + order abuse demo",
   "run": ("llm_selfposed_17_pubjoke", "llm-selfposed-17-pubjoke-001", False)},
}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def parse_metrics(run_dir: Path):
    """Return (verdict_dist by FW_VAR, [exemplar lines per FW_VAR], corpus_count)."""
    mk = run_dir / "metrics.kv"
    if not mk.exists():
        return {}, {}, 0
    dist, exemplar = Counter(), {}
    n = 0
    for line in mk.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.search(r"FW_VAR=(\d+)", line)
        if not m:
            continue
        n += 1
        code = m.group(1)
        dist[code] += 1
        if code not in exemplar:
            app = re.search(r"(app=.*?FW_VAR=\d+)", line)
            exemplar[code] = (app.group(1) if app else line.strip())[:240]
    return dict(dist), exemplar, n


def best_candidates(run_dir: Path, limit=3):
    """Return (front[:limit] tagged with PASS/DOMAIN_FAIL outcome, total front size, PASS-only count).
    The formal Pareto front is computed over ALL executed candidates, so a DOMAIN_FAIL candidate can be
    non-dominated (e.g. lowest latency yet failing an invariant) — we surface its outcome so a reader does
    not mistake a finding for a deployable recommendation (Automation caveat 2026-06-18)."""
    pv = run_dir / "provenance.json"
    if not pv.exists():
        return [], 0, 0
    d = json.loads(pv.read_text(encoding="utf-8"))
    cands = d.get("candidates", [])
    fw = {}  # candidate_id -> FW_VAR (outcome), from the harvested metrics corpus
    mk = run_dir / "metrics.kv"
    if mk.exists():
        for line in mk.read_text(encoding="utf-8", errors="ignore").splitlines():
            cid = re.search(r"candidate_id=(\S+)", line)
            m = re.search(r"FW_VAR=(\d+)", line)
            if cid and m:
                fw[cid.group(1)] = int(m.group(1))
    out, pass_front = [], 0
    for c in cands:
        cid = c.get("candidate_id")
        v = fw.get(cid)
        outcome = "PASS" if v == 0 else ("DOMAIN_FAIL" if v is not None else "unknown")
        pass_front += int(outcome == "PASS")
        if len(out) < limit:
            out.append({"candidate_id": cid, "outcome": outcome, "fw_var": v,
                        "objectives": c.get("objectives"),
                        "reason_non_dominated": (c.get("reason_non_dominated") or "")[:140]})
    return out, len(cands), pass_front


def write_json(p: Path, obj):
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    made = []
    for sid, meta in S.items():
        sdir = LAB / sid
        spec = sdir / "scenario.toml"
        spec_sha = sha256_file(spec)
        plan = {}
        if (sdir / "plan.json").exists():
            plan = json.loads((sdir / "plan.json").read_text(encoding="utf-8"))
        card_evidence = {}
        verdict_dist, exemplars, corpus = {}, {}, 0
        front, front_n, pass_front = [], 0, 0
        ran = meta["run"] is not None
        if ran:
            db, rid, sieve = meta["run"]
            run_dir = FWWORK / db / "runs" / rid
            if not (run_dir / "metrics.kv").exists():
                # Run dir absent (e.g. /tmp wiped by a reboot): do NOT clobber an existing evidence-backed
                # card with zeros. Skip this scenario and keep its artifacts; re-run the scenario, then rebuild.
                print(f"  SKIP {sid}: run dir/metrics missing ({run_dir}); keeping existing artifacts (re-run the scenario first)")
                continue
            verdict_dist, exemplars, corpus = parse_metrics(run_dir)
            front, front_n, pass_front = best_candidates(run_dir)
            card_evidence = {"db": db, "run_id": rid, "sieve": sieve,
                             "run_dir": str(run_dir),
                             "evidence_files": [f for f in ["run.json", "state.json", "executor-summary.json",
                                                "metrics.kv", "provenance.json"] if (run_dir / f).exists()]}

        # ----- zen_mapping.json (schema-stamped so the spec loader skips it) -----
        zen = {"schema": "bundle.selfposed-zen-mapping/v1", "scenario_id": "selfposed_" + sid,
               "category": meta["category"], "user_problem": meta["user_problem"],
               "bundle_offer": meta["bundle_offer"], "hypothesis": meta["hypothesis"],
               "zen_mapping": meta["zen_mapping"],
               "entities": {"sheets": ["HEAD"] + [m["verb"].split("(")[0] for m in meta["zen_mapping"]] + ["TAIL"],
                            "goals": meta["goals"], "oracle": meta["oracle"]},
               "pattern": meta["pattern"],
               "evidence": [{"kind": "zen", "path": "ZEN_OF_COMBINATORICS.md"},
                            {"kind": "pattern", "path": "generator_trunk/" + meta["pattern"]}]}
        # keep the hand-written scenario 01 zen_mapping/problem; generate for the rest
        if sid != "01_order_record_clean":
            write_json(sdir / "zen_mapping.json", zen)

        # ----- result_card.json (schema-stamped) -----
        card = {"schema": "bundle.selfposed-result-card/v1", "scenario_id": "selfposed_" + sid,
                "category": meta["category"], "user_problem": meta["user_problem"],
                "bundle_offer": meta["bundle_offer"], "zen_mapping": meta["zen_mapping"],
                "oracle": meta["oracle"],
                "spec_path": str(spec), "spec_sha256": spec_sha,
                "plan_cardinality": (plan.get("cardinality", {}).get("final") if plan else None),
                "run_class": (plan.get("resources", {}).get("run_class") if plan else None),
                "ran": ran, "candidate_count": corpus,
                "verdict_distribution": {meta["verdict_codes"].get(k, "FW_VAR=" + k): v for k, v in sorted(verdict_dist.items())},
                "goals": meta["goals"], "best_candidates": front, "pareto_front_size": front_n,
                "pareto_front_pass_count": pass_front,
                "pareto_front_note": meta.get(
                    "pareto_front_note",
                    "the formal front is over ALL executed candidates; DOMAIN_FAIL members are "
                    "findings, not deployable — pick the best PASS candidate to deploy"),
                "domain_fail_examples": [exemplars[k] for k in exemplars if k != "0"][:3],
                "pass_example": exemplars.get("0"),
                "teaching_summary": "",
                **card_evidence}
        if not ran:
            card["plan_only_reason"] = meta.get(
                "plan_only_reason",
                "Brace -> UNKNOWN cardinality -> run class X; a full run needs --allow-extreme, which this assignment prohibits. Verified by plan + FW_Seq graph (6 nodes, 3 edges).")
        ts = (f"User problem ({meta['category']}). " +
              (f"Ran {corpus} candidates: " + ", ".join(f"{v}x {k}" for k, v in card['verdict_distribution'].items()) +
               f". Formal Pareto front of {front_n}. " if ran else meta.get("plan_only_summary", "Plan + graph only (second-order, effective class X). ")) +
              "Verbs: " + "; ".join(f"{m['freedom']} -> {m['verb']}" for m in meta["zen_mapping"]) + ".")
        if ran and (front_n - pass_front) > 0:
            ts += (f" NOTE: {front_n - pass_front} of {front_n} Pareto-front candidates are DOMAIN_FAIL "
                   f"(findings, not deployable): {card['pareto_front_note']}.")
        card["teaching_summary"] = ts
        write_json(sdir / "result_card.json", card)

        # ----- problem.md (generate for 02..06; keep hand-written 01) -----
        if sid != "01_order_record_clean":
            md = [f"# Scenario {sid} — {meta['category']}", "",
                  f"**Category:** {meta['category']} (pattern like `generator_trunk/{meta['pattern']}`).", "",
                  "## Simple-language user problem", f"\"{meta['user_problem']}\"", "",
                  "## What Bundle can offer", meta["bundle_offer"], "",
                  "## Hypothesis", meta["hypothesis"], "",
                  "## Freedoms -> ZEN verbs"]
            for m in meta["zen_mapping"]:
                md.append(f"- **{m['freedom']}** -> shape *{m['shape']}* -> `{m['verb']}` ({m['cardinality']}).")
            md += ["", "## Oracle (meaning)", meta["oracle"],
                   "", f"**Goals:** " + ", ".join(f"`{g['key']}:{g['dir']}`" for g in meta["goals"]) + "."]
            (sdir / "problem.md").write_text("\n".join(md) + "\n", encoding="utf-8")

        # ----- run_report.md -----
        rr = [f"# Run report — {sid}", "", f"- spec: `{spec}`  sha256 `{spec_sha[:16]}...`",
              f"- category: {meta['category']}  | pattern: {meta['pattern']}"]
        if plan:
            fin = plan.get("cardinality", {}).get("final", {})
            rr.append(f"- plan: final={fin.get('value')} mode={fin.get('mode')} run_class={plan.get('resources',{}).get('run_class')}")
        if ran:
            db, rid, sieve = meta["run"]
            rr += [f"- run_id: `{rid}`  db: `{db}`  sieve: {sieve}",
                   f"- candidates executed: {corpus}",
                   f"- verdict distribution: " + ", ".join(f"{v}x {k}" for k, v in card['verdict_distribution'].items()),
                   f"- formal Pareto front: {front_n} non-dominated (PASS on front: {pass_front}/{front_n}; provenance_ok)",
                   f"- Pareto note: {card['pareto_front_note']}",
                   f"- evidence: {', '.join(card_evidence.get('evidence_files', []))}"]
            if card["pass_example"]:
                rr.append(f"- PASS exemplar: `{card['pass_example']}`")
            for ex in card["domain_fail_examples"]:
                rr.append(f"- DOMAIN_FAIL exemplar: `{ex}`")
        else:
            rr += ["- PLAN + GRAPH ONLY: " + card["plan_only_reason"]]
        (sdir / "run_report.md").write_text("\n".join(rr) + "\n", encoding="utf-8")
        made.append(sid)
        print(f"  {sid}: ran={ran} corpus={corpus} verdicts={card['verdict_distribution']} front={front_n}")
    print(f"built artifacts for {len(made)} scenarios")


if __name__ == "__main__":
    main()
