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

"""Engine-first architecture model — the machine-readable product boundary.

The Bundle is an executable combinatorial design-space and evidence engine. AI
response testing is *one reference application* built on it. That sentence is a
requirement, not marketing: this module encodes it as data so a test can enforce
it and a report can be generated from it, instead of the boundary living only in
prose that drifts.

Two things are declared here:

1. **Layers.** Every source tree in the repository belongs to exactly one layer
   (:data:`LAYERS`), classified by *responsibility and dependency direction* —
   never by who or what wrote the code. ``classify_path`` maps any repository
   path to its layer by longest-prefix match.

2. **Allowed dependency direction.** Each layer declares which layers it may
   import (``may_import``). The engine must never import a reference
   application, so:

   ``reference application -> documented Bundle entry points/contracts``
   ``Bundle engine/control plane -X-> reference application``

   :func:`scan_imports` resolves real ``import``/``from`` statements with the
   ``ast`` module (not a grep) and :func:`dependency_violations` reports every
   edge that the declaration forbids. One narrow exception exists — the shared
   Face 1 scenario catalog legitimately *launches* reference applications — so
   it is enumerated explicitly in :data:`DECLARED_CROSS_LAYER_EDGES` rather than
   being waved through by a blanket rule: an undeclared edge still fails.

The migration rule this model exists to serve: **characterize before moving or
splitting code.** Reclassifying a tree here is cheap and reviewable; moving
Core/Reader/Executor source is not, and must be preceded by characterization
tests (docs/30_ENGINE_FIRST_ARCHITECTURE.md).
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

SCHEMA = "bundle.architecture/v1"

# generator_trunk/bundle/architecture.py -> generator_trunk/bundle -> generator_trunk -> <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]

# Import roots a repository module name can be resolved against. These mirror the
# real runtime/pytest search path (`pyproject.toml [tool.pytest.ini_options]
# pythonpath`) plus the repository root used by candidate code
# (`from generator_trunk...`), so a dotted name is classified the same way the
# interpreter would resolve it.
IMPORT_ROOTS = ("", "generator_trunk", "Executor_trunk")

# ----------------------------------------------------------------- layer ids --
ENGINE_CORE = "engine-core"
ENGINE_CONTROL_PLANE = "engine-control-plane"
ENGINE_DEMONSTRATION = "engine-demonstration"
DOMAIN_APPLICATION = "domain-application"
PRESENTATION = "presentation"
REFERENCE_APPLICATION = "reference-application"
TESTS = "tests"
UNCLASSIFIED = "unclassified"

#: Layers that implement the engine itself.  The demonstration consumes these
#: layers; it is deliberately *not* part of the engine revision or product
#: boundary it exists to prove.
ENGINE_LAYERS = (ENGINE_CORE, ENGINE_CONTROL_PLANE)

#: Every non-test product layer whose dependency direction the CLI gate audits.
#: Keeping this separate from ``ENGINE_LAYERS`` prevents the architecture report
#: from silently omitting a forbidden edge originating in a demonstration,
#: presentation surface, or reference application.
AUDITED_LAYERS = (
    ENGINE_CORE,
    ENGINE_CONTROL_PLANE,
    ENGINE_DEMONSTRATION,
    DOMAIN_APPLICATION,
    PRESENTATION,
    REFERENCE_APPLICATION,
)


@dataclass(frozen=True)
class LayerSpec:
    """One architectural layer: what it is responsible for, how stable its
    surface is, which layers it may import, and which paths belong to it."""

    id: str
    title: str
    responsibility: str
    stability: str                    # stable | experimental | replaceable
    may_import: Sequence[str]
    roots: Sequence[str]              # repository-relative POSIX path prefixes

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "responsibility": self.responsibility,
            "stability": self.stability, "may_import": list(self.may_import),
            "roots": list(self.roots),
        }


# The declaration order is irrelevant: classification is longest-prefix, so a
# nested tree (generator_trunk/engine_demo) wins over its parent regardless.
LAYERS: "tuple[LayerSpec, ...]" = (
    LayerSpec(
        id=ENGINE_CORE,
        title="Bundle Engine — Core, Reader, Executor, Analyzer",
        responsibility=(
            "engine semantics: enumerate the declared design space, assemble each surviving "
            "row into an executable candidate, execute it under a policy, and select "
            "non-dominated outcomes. Knows nothing about any domain."),
        stability="stable",
        may_import=(ENGINE_CORE,),
        roots=(
            "Core_trunk", "Reader_trunk", "Executor_trunk", "Analyzer_trunk",
            "Combinatoricslib3parallel",
        ),
    ),
    LayerSpec(
        id=ENGINE_CONTROL_PLANE,
        title="Engine control plane — specification, planning, lifecycle, contracts",
        responsibility=(
            "orchestration required to operate the engine: spec parsing, workbook "
            "generation, cardinality planning and budgets, the constraint sieve, the run/stage "
            "contracts, execution policy, invariants, lifecycle and diagnostics. Supporting "
            "engine infrastructure, not a domain."),
        stability="stable",
        may_import=(ENGINE_CORE, ENGINE_CONTROL_PLANE),
        roots=(
            "generator_trunk/bundle", "generator_trunk/constraints", "generator_trunk/proto",
            "generator_trunk/bundle-biasplan-v1.schema.json",
            "generator_trunk/bundle-handoff-v2.schema.json",
            "generator_trunk/bundle-iterate-v1.schema.json",
            "generator_trunk/bundle-reference-coverage-v1.schema.json",
            "generator_trunk/bundle-sut-manifest-v1.schema.json",
            "generator_trunk/bundle-spec-v1.schema.json",
            # Canonical SUT adapter manifests are release-contract DECLARATIONS
            # owned by the control plane, not domain code: they state how a SUT is
            # gated, and the control plane validates them.
            "generator_trunk/sut_manifests",
            "generator_trunk/fwgen.py", "generator_trunk/fwgen_cli.py",
            "generator_trunk/fwseq_graph.py", "generator_trunk/bundle_run.py",
            "generator_trunk/bundle_gateway.py", "generator_trunk/sut_paths.py",
            "generator_trunk/xlsx_autofit.py", "generator_trunk/code_decompose.py",
        ),
    ),
    LayerSpec(
        id=ENGINE_DEMONSTRATION,
        title="Direct engine demonstration",
        responsibility=(
            "the minimal, self-contained proof that advanced first/second/third-order "
            "composition is an engine capability: a domain adapter, an exact oracle and one "
            "bounded scenario that reach Core/Reader/Executor/Analyzer without any reference "
            "application on the path."),
        stability="stable",
        may_import=(ENGINE_CORE, ENGINE_CONTROL_PLANE, ENGINE_DEMONSTRATION),
        roots=("generator_trunk/engine_demo",
               # The flagship extends the demonstration SUT with versioned
               # defects and baseline constructions. Same layer: it proves an
               # engine property and imports no reference application.
               "generator_trunk/flagship",
               # Controlled comparative studies: a hash-frozen SUT, a classic
               # baseline (including its parameter model run to exhaustion) and
               # the campaigns that answer what the verbs reach and the model
               # cannot. Same layer as the other demonstrations -- they prove an
               # engine property end to end and import no reference application.
               "generator_trunk/proof_billing",
               "generator_trunk/proof_fulfilment",
               "generator_trunk/proof_authz"),
    ),
    LayerSpec(
        id=PRESENTATION,
        title="Replaceable control and presentation",
        responsibility=(
            "user interfaces, intake catalogs, wizards and gateways. Replaceable: removing "
            "any of these must not remove an engine capability."),
        stability="replaceable",
        may_import=(ENGINE_CORE, ENGINE_CONTROL_PLANE, ENGINE_DEMONSTRATION, PRESENTATION),
        roots=(
            "generator_trunk/intake", "generator_trunk/face1_new", "generator_trunk/landing",
            "generator_trunk/invitation_wizard", "generator_trunk/fwgen_gui.py",
        ),
    ),
    LayerSpec(
        id=DOMAIN_APPLICATION,
        title="Domain applications — a subject matter modelled on top of the engine",
        responsibility=(
            "one subject matter, modelled as data and executable candidates: the domain's "
            "objects, the operations over them, an oracle that decides them, and the "
            "scenario specifications that enumerate them. A domain application may "
            "restrict its own search space; it may not restrict the engine, and it may "
            "not reach sideways into another application's domain."),
        stability="experimental",
        # DELIBERATELY NARROWER than `reference-application`. The engine and its
        # control plane are available; nothing else is. In particular this layer
        # may NOT import:
        #   * `reference-application` — so a domain application cannot grow into,
        #     or quietly depend on, the AI testing platform;
        #   * `engine-demonstration` — so it cannot borrow the flagship SUTs. Those
        #     are worked examples of the method, not a framework, and copying one
        #     reproduces its assumptions along with its structure.
        # The shared comparison harness lives in `bundle/study.py`, i.e. in the
        # control plane, precisely so this layer can use it without either edge.
        may_import=(ENGINE_CORE, ENGINE_CONTROL_PLANE, DOMAIN_APPLICATION),
        roots=(
            # Declared before the directory exists, on purpose: an absent root is
            # skipped, so the boundary is in force from the FIRST commit of the
            # application rather than retrofitted around code already written.
            "generator_trunk/genetics_model_testing",
        ),
    ),
    LayerSpec(
        id=REFERENCE_APPLICATION,
        title="Reference applications, domain adapters and scenario libraries",
        responsibility=(
            "domain meaning: task/prompt construction, SUT adapters, oracles, scenario "
            "specifications and campaign launchers. Each may restrict its own search space; "
            "none may restrict the engine."),
        stability="experimental",
        may_import=(
            ENGINE_CORE, ENGINE_CONTROL_PLANE, ENGINE_DEMONSTRATION, REFERENCE_APPLICATION),
        roots=(
            "generator_trunk/AI_combi_testing_platform", "generator_trunk/scenarios",
            "generator_trunk/usecases", "generator_trunk/combinatorial_tests",
            "generator_trunk/model_usecases", "generator_trunk/examples",
            "generator_trunk/specs", "generator_trunk/java_e2e", "generator_trunk/qa_checkout",
            "generator_trunk/qa_testgen", "generator_trunk/api_probe",
            "generator_trunk/brace_demo", "generator_trunk/brace_full_demo",
            "generator_trunk/group_sep_demo", "generator_trunk/fintech_oot",
            "generator_trunk/llm_arch_search", "generator_trunk/llm_loop",
            "generator_trunk/llm_selfposed_bundle_tasks", "generator_trunk/llm_transformer_campaign",
            "generator_trunk/transformers_sweep_288", "generator_trunk/tryout_own",
            "generator_trunk/generated_tests", "generator_trunk/generated_tests_fintech",
            "generator_trunk/testgen_api.py", "generator_trunk/testgen_fintech.py",
            "generator_trunk/run_4instance_bundle.py", "generator_trunk/run_full_pairwise_bundle.py",
        ),
    ),
    LayerSpec(
        id=TESTS,
        title="Test suites",
        responsibility=(
            "verification. Tests may import any layer by design — a test that exercises a "
            "reference application is not a product dependency."),
        stability="stable",
        # Tests may reach every layer -- including `domain-application`, which a
        # domain's own test module has to import. Adding a layer without adding it
        # here is invisible to the CLI gate (it audits only AUDITED_LAYERS, which
        # excludes tests) and shows up as a violation only when something actually
        # imports the new layer from a test.
        may_import=(
            ENGINE_CORE, ENGINE_CONTROL_PLANE, ENGINE_DEMONSTRATION, DOMAIN_APPLICATION,
            PRESENTATION, REFERENCE_APPLICATION, TESTS),
        roots=(),                      # matched by filename convention, see classify_path
    ),
)

LAYERS_BY_ID: "Mapping[str, LayerSpec]" = {layer.id: layer for layer in LAYERS}


@dataclass(frozen=True)
class DeclaredEdge:
    """One reviewed, deliberately allowed import that the layer declaration would
    otherwise forbid. Enumerated so a *new* violation still fails the gate."""

    importer: str                     # repository-relative path of the importing module
    imported_prefix: str              # repository-relative path prefix of the imported tree
    reason: str

    def to_dict(self) -> dict:
        return {"importer": self.importer, "imported_prefix": self.imported_prefix,
                "reason": self.reason}


#: Reviewed exceptions. Presentation code may *launch* a reference application;
#: it must still be listed here, one edge at a time, with a reason.
DECLARED_CROSS_LAYER_EDGES: "tuple[DeclaredEdge, ...]" = (
    DeclaredEdge(
        importer="generator_trunk/intake/scenario_library.py",
        imported_prefix="generator_trunk/AI_combi_testing_platform",
        reason=(
            "The shared Face 1 catalog materializes the AI release-gate sub-suite's dynamic "
            "spec at inspection/launch time. Presentation launching a reference application "
            "is the allowed direction; the engine and control plane still never import it."),
    ),
)


# ------------------------------------------------------------- classification --
def _normalized_roots() -> "list[tuple[str, str]]":
    """(root, layer_id) pairs, longest root first, so nested trees win."""
    pairs = [(root, layer.id) for layer in LAYERS for root in layer.roots]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


_ROOTS = _normalized_roots()


def repo_relative(path) -> str:
    """Repository-relative POSIX path for *path* (absolute or already relative)."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.relative_to(REPO_ROOT)
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def classify_path(path) -> str:
    """Layer id for a repository path, by longest-prefix match.

    A file named ``test_*.py`` (or living under a ``tests/`` directory) is
    classified as :data:`TESTS` regardless of where it sits: a test beside the
    module it verifies is still a test, not a product dependency. Anything the
    declaration does not cover returns :data:`UNCLASSIFIED` — a signal to extend
    :data:`LAYERS`, never something to silently ignore.
    """
    rel = repo_relative(path)
    parts = rel.split("/")
    name = parts[-1]
    if ((name.startswith("test_") or name.endswith("_test.py")) and name.endswith(".py")):
        return TESTS
    if name.endswith(("Test.java", "Tests.java")):
        return TESTS
    if "tests" in parts[:-1] or "test" in parts[:-1]:
        return TESTS
    for root, layer_id in _ROOTS:
        if rel == root or rel.startswith(root + "/"):
            return layer_id
    return UNCLASSIFIED


# ------------------------------------------------------------- import walking --
@dataclass(frozen=True)
class ImportEdge:
    """One resolved repository-internal import."""

    importer: str                     # repository-relative path
    importer_layer: str
    imported_module: str              # dotted name as written
    imported_path: str                # repository-relative path it resolves to
    imported_layer: str
    lineno: int

    def to_dict(self) -> dict:
        return {
            "importer": self.importer, "importer_layer": self.importer_layer,
            "imported_module": self.imported_module, "imported_path": self.imported_path,
            "imported_layer": self.imported_layer, "lineno": self.lineno,
        }


def _module_targets(node: ast.AST) -> "Iterator[tuple[str, int, int]]":
    """Yield ``(dotted_name, relative_level, lineno)`` for every import statement."""
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                yield alias.name, 0, stmt.lineno
        elif isinstance(stmt, ast.ImportFrom):
            base = stmt.module or ""
            level = stmt.level or 0
            if base:
                yield base, level, stmt.lineno
            # `from . import x` / `from .pkg import x`: each name may itself be a module.
            for alias in stmt.names:
                dotted = f"{base}.{alias.name}" if base else alias.name
                yield dotted, level, stmt.lineno


def _resolve_absolute(dotted: str) -> "str | None":
    """Repository-relative path a top-level dotted name resolves to, else None
    (stdlib / third-party / unknown)."""
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return None
    for root in IMPORT_ROOTS:
        base = REPO_ROOT / root if root else REPO_ROOT
        candidate = base.joinpath(*parts)
        if candidate.is_dir() and (candidate / "__init__.py").is_file():
            return repo_relative(candidate)
        if candidate.with_suffix(".py").is_file():
            return repo_relative(candidate.with_suffix(".py"))
        # Namespace package (no __init__.py) — the repository uses these for
        # `generator_trunk.scenarios...` imports from candidate code.
        if candidate.is_dir():
            return repo_relative(candidate)
    return None


def _resolve_relative(source: Path, dotted: str, level: int) -> "str | None":
    """Resolve ``from ..pkg import x`` against the importing module's package."""
    package = source.parent
    for _ in range(level - 1):
        package = package.parent
    parts = [p for p in dotted.split(".") if p]
    candidate = package.joinpath(*parts) if parts else package
    if candidate.with_suffix(".py").is_file():
        return repo_relative(candidate.with_suffix(".py"))
    if candidate.is_dir():
        return repo_relative(candidate)
    return None


def iter_python_sources(layers: "Sequence[str] | None" = None) -> "Iterator[Path]":
    """Every ``.py`` file under the declared roots of *layers* (all layers when
    None), skipping build/cache directories."""
    wanted = set(layers) if layers is not None else None
    seen: set = set()
    for layer in LAYERS:
        if wanted is not None and layer.id not in wanted:
            continue
        for root in layer.roots:
            base = REPO_ROOT / root
            if base.is_file() and base.suffix == ".py":
                candidates: Iterable[Path] = [base]
            elif base.is_dir():
                candidates = base.rglob("*.py")
            else:
                continue
            for path in candidates:
                rel = repo_relative(path)
                if any(part in ("__pycache__", "target", "build", "dist", "node_modules",
                                ".venv", "campaign_results", "runs")
                       for part in rel.split("/")):
                    continue
                if rel in seen:
                    continue
                # A test colocated with an implementation root belongs to the
                # test layer, not to the product layer whose directory contains
                # it.  This also keeps engine_revision independent of tests.
                if wanted is not None and classify_path(path) not in wanted:
                    continue
                seen.add(rel)
                yield path


def scan_imports(layers: "Sequence[str] | None" = None) -> "list[ImportEdge]":
    """Every repository-internal import edge originating in *layers*.

    Uses :mod:`ast`, so a string that merely *mentions* a module name is not an
    edge, and an import that a grep pattern would miss (aliased, nested inside a
    function, relative) still is. A file that cannot be parsed raises — a control
    plane that does not parse is a defect, not something to skip.
    """
    edges: "list[ImportEdge]" = []
    for source in iter_python_sources(layers):
        rel = repo_relative(source)
        importer_layer = classify_path(source)
        if layers is not None and importer_layer not in layers:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"), filename=str(source))
        for dotted, level, lineno in _module_targets(tree):
            target = (_resolve_relative(source, dotted, level) if level
                      else _resolve_absolute(dotted))
            if target is None or target == rel:
                continue
            edges.append(ImportEdge(
                importer=rel, importer_layer=importer_layer, imported_module=dotted,
                imported_path=target, imported_layer=classify_path(target), lineno=lineno))
    return edges


def _edge_is_declared(edge: ImportEdge) -> bool:
    for declared in DECLARED_CROSS_LAYER_EDGES:
        if edge.importer == declared.importer and (
                edge.imported_path == declared.imported_prefix
                or edge.imported_path.startswith(declared.imported_prefix + "/")):
            return True
    return False


def dependency_violations(layers: "Sequence[str] | None" = None) -> "list[ImportEdge]":
    """Import edges that the layer declaration forbids and no reviewed exception
    covers. An empty list is the architecture gate's pass condition."""
    bad: "list[ImportEdge]" = []
    for edge in scan_imports(layers):
        spec = LAYERS_BY_ID.get(edge.importer_layer)
        if spec is None:                       # unclassified importer: reported separately
            continue
        if edge.imported_layer in spec.may_import:
            continue
        if edge.imported_layer == UNCLASSIFIED:
            continue                            # reported by unclassified_paths(), not here
        if _edge_is_declared(edge):
            continue
        bad.append(edge)
    return bad


def unclassified_paths() -> "list[str]":
    """Top-level repository trees and ``generator_trunk`` entries that no layer
    claims. Keeping this empty is what stops a new tree from quietly acquiring
    an undeclared position in the architecture."""
    # Not part of the architecture: documentation, legal/deploy/config assets,
    # repository maintenance tooling, build output, and the `generator_trunk`
    # container itself (its children are classified one level down).
    skip_names = {"__pycache__", "target", "build", "dist", "node_modules", "docs",
                  "LEGAL_LICENSE_KIT", "deploy", "config", "tools", "generator_trunk"}
    missing: "list[str]" = []
    for parent in (REPO_ROOT, REPO_ROOT / "generator_trunk"):
        if not parent.is_dir():
            continue
        for entry in sorted(parent.iterdir()):
            rel = repo_relative(entry)
            if entry.name.startswith(".") or entry.name in skip_names:
                continue
            if entry.name.endswith(".egg-info"):
                continue
            # Python modules and published JSON schemas are architectural
            # source/contracts.  Documentation, build metadata and binary
            # examples are intentionally outside this source-tree gate.
            if entry.is_file() and not (
                    entry.suffix == ".py" or entry.name.endswith(".schema.json")):
                continue
            if classify_path(entry) == UNCLASSIFIED:
                missing.append(rel)
    return missing


# --------------------------------------------------------- reference registry --
@dataclass(frozen=True)
class CoverageTarget:
    """A registered subject of capability/launcher-overhead measurement.

    ``role`` preserves the engine-first boundary in the data model: the direct
    engine demonstration is a stable proof fixture, while a reference
    application is a replaceable consumer.  Both are useful comparison targets,
    but they are not the same architectural thing.
    """

    id: str
    title: str
    role: str                         # engine-demonstration | reference-application
    status: str                       # stable | reference | experimental
    root: str                         # repository-relative directory
    spec_globs: Sequence[str]         # scenario specs, relative to `root`
    launcher: str                     # repository-relative launcher module
    summary: str
    # --- overhead-comparison declaration (bundle bench --stages reference_overhead) ---
    # The ONE bounded scenario this application is measured on, the launcher
    # arguments that run exactly that scenario, and the canonical `bundle_run.py`
    # flags that reproduce the same work directly. Declaring the direct flags
    # explicitly is what makes the comparison honest: identical scenario,
    # identical policy, identical candidate count, identical oracle — the only
    # difference is the wrapper.
    benchmark_spec: str = ""
    benchmark_launcher_args: Sequence[str] = ()
    benchmark_direct_args: Sequence[str] = ()
    # A launcher benchmark must be able to use a fresh, uniquely named DB.  The
    # option is declared here rather than guessed from source; the harness adds
    # the generated name to both-cluster cleanup before the launcher starts.
    benchmark_launcher_database_arg: str = ""
    benchmark_launcher_run_id_arg: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "role": self.role,
                "status": self.status, "root": self.root,
                "spec_globs": list(self.spec_globs), "launcher": self.launcher,
                "summary": self.summary, "benchmark_spec": self.benchmark_spec,
                "benchmark_launcher_args": list(self.benchmark_launcher_args),
                "benchmark_direct_args": list(self.benchmark_direct_args),
                "benchmark_launcher_database_arg": self.benchmark_launcher_database_arg,
                "benchmark_launcher_run_id_arg": self.benchmark_launcher_run_id_arg}


COVERAGE_TARGETS: "tuple[CoverageTarget, ...]" = (
    CoverageTarget(
        id="ai-combi",
        title="AI combinatorial testing platform",
        role=REFERENCE_APPLICATION,
        status="experimental",
        root="generator_trunk/AI_combi_testing_platform",
        spec_globs=("scenarios/*/*.toml",),
        launcher="generator_trunk/AI_combi_testing_platform/run_campaign.py",
        summary=(
            "Bundle-native AI evaluation derivative: canonical task IR, exact oracles, "
            "renderings and prompt programs. A valuable proof of concept and reference "
            "application — not the definition of the Bundle."),
        benchmark_spec="generator_trunk/AI_combi_testing_platform/scenarios/00_smoke",
        benchmark_launcher_args=("run", "--scenario", "00_smoke"),
        benchmark_launcher_database_arg="--db",
        benchmark_launcher_run_id_arg="--run-id",
        benchmark_direct_args=(
            "--lang", "py", "--candidate-sink", "sharded",
            "--execution-policy-profile", "trusted-local",
            "--candidate-origin", "reviewed-checked-in",
            "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
            "--analyzer", "correct:max,all_constraints_pass:max,semantic_invariance_ok:max,"
                          "complexity:max,latency_us:min,cost_microusd:min",
            "--analysis-mode", "formal",
            "--repeat", "1", "--repeat-policy", "local", "--repeat-scope", "all"),
    ),
    CoverageTarget(
        id="automation-scheme-studio",
        title="Automation Scheme Studio control-circuit search",
        role=REFERENCE_APPLICATION,
        status="reference",
        root="generator_trunk/scenarios/automation_scheme_studio",
        spec_globs=("*/*.toml", "advanced_feedback/*/*.toml"),
        launcher="generator_trunk/scenarios/automation_scheme_studio/advanced_feedback/"
                 "run_advanced_campaign.py",
        summary=(
            "Higher-order composition against an external control-system SUT: recursive "
            "topologies built from braces, FW_Group and repetition verbs."),
        # Its campaign launcher runs the whole advanced suite rather than one
        # scenario, so there is no single-scenario wrapper leg to time. The
        # engine leg is still measurable; the wrapper leg records a reason.
        benchmark_spec="generator_trunk/scenarios/automation_scheme_studio/"
                       "advanced_feedback/01_operator_smoke",
        benchmark_launcher_args=(),
        benchmark_direct_args=(
            "--lang", "py", "--candidate-sink", "sharded",
            "--execution-policy-profile", "trusted-local",
            "--candidate-origin", "reviewed-checked-in",
            "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
            "--analyzer", "control_score:max,robustness_score:max,stability_score:max,"
                          "settling_time_s:min,worst_error:min,overshoot_pct:min,"
                          "control_effort:min",
            "--analysis-mode", "formal", "--allow-extreme",
            "--override-budget", "reference-overhead measurement of a bounded operator smoke"),
    ),
    CoverageTarget(
        id="engine-demo",
        title="Direct engine demonstration (record pipeline)",
        role=ENGINE_DEMONSTRATION,
        status="stable",
        root="generator_trunk/engine_demo",
        spec_globs=("*/*.toml",),
        launcher="generator_trunk/engine_demo/run_direct_engine_smoke.py",
        summary=(
            "The minimal direct engine path: self-contained domain adapter and exact "
            "differential oracle, no reference application and no external SUT on the path."),
        benchmark_spec="generator_trunk/engine_demo/direct_engine_smoke",
        benchmark_launcher_args=("run",),
        benchmark_launcher_database_arg="--db",
        benchmark_launcher_run_id_arg="--run-id",
        benchmark_direct_args=(
            "--lang", "py", "--execution-policy-profile", "trusted-local",
            "--candidate-origin", "reviewed-checked-in",
            "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
            "--analyzer", "stages:max,retained:max,ops:min", "--analysis-mode", "formal",
            "--allow-extreme",
            "--override-budget", "bounded direct engine smoke: higher-order brace cardinality "
                                 "is runtime-known and capped by explicit budgets",
            "--budget-final-candidates", "64", "--budget-mandatory-rows", "64"),
    ),
)


REFERENCE_APPLICATIONS: "tuple[CoverageTarget, ...]" = tuple(
    target for target in COVERAGE_TARGETS if target.role == REFERENCE_APPLICATION)
ENGINE_DEMONSTRATIONS: "tuple[CoverageTarget, ...]" = tuple(
    target for target in COVERAGE_TARGETS if target.role == ENGINE_DEMONSTRATION)


def coverage_target(target_id: str) -> CoverageTarget:
    for target in COVERAGE_TARGETS:
        if target.id == target_id:
            return target
    raise KeyError(f"unknown coverage target {target_id!r}; known: "
                   f"{[target.id for target in COVERAGE_TARGETS]}")


# ------------------------------------------------------------------ reporting --
_ENGINE_SOURCE_SUFFIXES = {
    ".cfg", ".ini", ".java", ".json", ".properties", ".proto", ".py",
    ".sh", ".sql", ".toml", ".txt", ".xml", ".yaml", ".yml",
}
_SOURCE_SKIP_DIRS = {
    "__pycache__", "target", "build", "dist", "node_modules", ".venv",
    "campaign_results", "runs",
}


def engine_source_files() -> "list[Path]":
    """Every implementation/configuration source file in the engine layers.

    Core, Reader and most of Analyzer are Java, so hashing only Python would
    produce the same alleged engine revision after a real engine change.  This
    walk is Git-independent (it also works in an extracted source tree), skips
    generated output, excludes colocated test-layer files, and includes the
    source/config formats that can affect engine behaviour.
    """
    seen: "set[str]" = set()
    paths: "list[Path]" = []
    wanted = set(ENGINE_LAYERS)
    for layer in LAYERS:
        if layer.id not in wanted:
            continue
        for root in layer.roots:
            base = REPO_ROOT / root
            candidates: Iterable[Path]
            if base.is_file():
                candidates = [base]
            elif base.is_dir():
                candidates = base.rglob("*")
            else:
                continue
            for path in candidates:
                if not path.is_file() or path.suffix.lower() not in _ENGINE_SOURCE_SUFFIXES:
                    continue
                rel = repo_relative(path)
                if any(part in _SOURCE_SKIP_DIRS for part in rel.split("/")):
                    continue
                if classify_path(path) not in wanted or rel in seen:
                    continue
                seen.add(rel)
                paths.append(path)
    return sorted(paths, key=repo_relative)


def engine_revision() -> str:
    """Deterministic identity of the engine implementation at this revision.

    Same source revision -> same value, on any host and in any checkout
    location, so a coverage/overhead report can be compared across runs without
    depending on Git metadata (an extracted tree may have none).
    """
    digest = hashlib.sha256()
    for path in engine_source_files():
        digest.update(repo_relative(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def architecture_report() -> dict:
    """The versioned architecture document: layers, allowed direction, reviewed
    exceptions, registered reference applications, and the current violations."""
    violations = dependency_violations(AUDITED_LAYERS)
    return {
        "schema": SCHEMA,
        "engine_revision": engine_revision(),
        "layers": [layer.to_dict() for layer in LAYERS],
        "engine_layers": list(ENGINE_LAYERS),
        "declared_cross_layer_edges": [e.to_dict() for e in DECLARED_CROSS_LAYER_EDGES],
        "reference_applications": [app.to_dict() for app in REFERENCE_APPLICATIONS],
        "engine_demonstrations": [demo.to_dict() for demo in ENGINE_DEMONSTRATIONS],
        "unclassified_paths": unclassified_paths(),
        "violations": [v.to_dict() for v in violations],
    }


def format_architecture_report(report: dict) -> str:
    """Concise human rendering of :func:`architecture_report`."""
    lines = [f"architecture {report['schema']}  engine_revision={report['engine_revision']}"]
    for layer in report["layers"]:
        lines.append(f"  {layer['id']:<22} [{layer['stability']}] "
                     f"may_import={','.join(layer['may_import']) or '-'}")
    lines.append(f"  reference applications: "
                 f"{', '.join(a['id'] for a in report['reference_applications']) or '-'}")
    lines.append(f"  engine demonstrations: "
                 f"{', '.join(a['id'] for a in report['engine_demonstrations']) or '-'}")
    if report["unclassified_paths"]:
        lines.append(f"  ! unclassified paths ({len(report['unclassified_paths'])}): "
                     f"{', '.join(report['unclassified_paths'])}")
    if report["violations"]:
        lines.append(f"  ⛔ dependency-direction violations ({len(report['violations'])}):")
        for v in report["violations"]:
            lines.append(f"      {v['importer']}:{v['lineno']} [{v['importer_layer']}] "
                         f"-> {v['imported_path']} [{v['imported_layer']}]")
    else:
        lines.append("  ✓ no dependency-direction violations")
    return "\n".join(lines)
