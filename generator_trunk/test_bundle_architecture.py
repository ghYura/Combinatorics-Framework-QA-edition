"""Engine-first architecture gate.

Enforces the boundary declared in `bundle/architecture.py`:

    reference application -> documented Bundle entry point/contracts
    Bundle engine/control plane -X-> reference application

The gate resolves real ``import``/``from`` statements with :mod:`ast`, so it is
not a grep pattern that a rename, an alias, or an import nested inside a
function can slip past. It also proves the *negative* acceptance criterion:
with the AI reference application unimportable, the direct engine path still
plans and the control plane still loads.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from bundle import architecture as arch

REPO_ROOT = arch.REPO_ROOT


# --------------------------------------------------------- direction gate ----
def test_engine_layers_do_not_import_a_reference_application() -> None:
    violations = arch.dependency_violations(arch.ENGINE_LAYERS)
    assert violations == [], "\n".join(
        f"{v.importer}:{v.lineno} [{v.importer_layer}] imports "
        f"{v.imported_module} -> {v.imported_path} [{v.imported_layer}]"
        for v in violations)


def test_no_layer_violates_its_declared_dependency_direction() -> None:
    violations = arch.dependency_violations(arch.AUDITED_LAYERS)
    assert violations == [], "\n".join(
        f"{v.importer}:{v.lineno} [{v.importer_layer}] imports "
        f"{v.imported_module} -> {v.imported_path} [{v.imported_layer}]"
        for v in violations)


def test_every_repository_tree_is_classified() -> None:
    """A new top-level tree must declare its layer. Without this, code could
    acquire an undeclared architectural position simply by being added."""
    assert arch.unclassified_paths() == []


def test_engine_layers_never_reach_the_ai_platform_specifically() -> None:
    ai_root = "generator_trunk/AI_combi_testing_platform"
    reaching = [e for e in arch.scan_imports(arch.ENGINE_LAYERS)
                if e.imported_path == ai_root or e.imported_path.startswith(ai_root + "/")]
    assert reaching == []


# ------------------------------------------------- the reviewed exceptions ----
def test_declared_cross_layer_edges_are_all_still_real() -> None:
    """A stale exception is as dangerous as a missing one: it silently
    pre-authorizes an edge nobody re-reviewed."""
    edges = arch.scan_imports((arch.PRESENTATION,))
    for declared in arch.DECLARED_CROSS_LAYER_EDGES:
        matching = [e for e in edges
                    if e.importer == declared.importer
                    and (e.imported_path == declared.imported_prefix
                         or e.imported_path.startswith(declared.imported_prefix + "/"))]
        assert matching, (
            f"declared exception {declared.importer} -> {declared.imported_prefix} "
            f"no longer corresponds to any real import; remove it")
        assert declared.reason.strip()


def test_the_scanner_sees_imports_nested_inside_functions() -> None:
    """The one real presentation -> reference-application edge is a lazy import
    inside a function body. Detecting it is what distinguishes an AST gate from
    a top-of-file grep."""
    edges = [e for e in arch.scan_imports((arch.PRESENTATION,))
             if e.importer == "generator_trunk/intake/scenario_library.py"
             and e.imported_layer == arch.REFERENCE_APPLICATION]
    assert edges, "expected the lazy release-gate materializer import to be detected"
    source = (REPO_ROOT / "generator_trunk/intake/scenario_library.py").read_text(encoding="utf-8")
    line = source.splitlines()[edges[0].lineno - 1]
    assert line.startswith(" "), "the detected import should be indented (nested), not top-level"


# ---------------------------------------------------------- classification ----
@pytest.mark.parametrize("path,expected", [
    ("generator_trunk/bundle/cli.py", arch.ENGINE_CONTROL_PLANE),
    ("generator_trunk/fwgen.py", arch.ENGINE_CONTROL_PLANE),
    ("Core_trunk/AI_QUICK_CORE_UNDERSTANDING.md", arch.ENGINE_CORE),
    ("Executor_trunk/py_executor.py", arch.ENGINE_CORE),
    ("generator_trunk/engine_demo/record_pipeline.py", arch.ENGINE_DEMONSTRATION),
    ("generator_trunk/intake/scenario_library.py", arch.PRESENTATION),
    ("generator_trunk/AI_combi_testing_platform/engine.py", arch.REFERENCE_APPLICATION),
    ("generator_trunk/scenarios/automation_scheme_studio/bootstrap.py", arch.REFERENCE_APPLICATION),
    ("generator_trunk/test_bundle_architecture.py", arch.TESTS),
    ("generator_trunk/AI_combi_testing_platform/tests/test_engine_and_rendering.py", arch.TESTS),
])
def test_classification_is_by_responsibility(path: str, expected: str) -> None:
    assert arch.classify_path(path) == expected


def test_engine_revision_is_deterministic_and_content_addressed() -> None:
    first = arch.engine_revision()
    assert first == arch.engine_revision()
    assert first.startswith("sha256:") and len(first) == len("sha256:") + 64


def test_engine_revision_covers_real_java_engine_source_not_demo_or_tests() -> None:
    paths = {arch.repo_relative(path) for path in arch.engine_source_files()}
    assert "Core_trunk/src/main/java/com/company/MainRefactored.java" in paths
    assert "Reader_trunk/src/main/java/com/company/Main.java" in paths
    assert "generator_trunk/bundle-handoff-v2.schema.json" in paths
    assert not any(path.startswith("generator_trunk/engine_demo/") for path in paths)
    assert not any(path.endswith("/test_bundle_architecture.py") for path in paths)


def test_architecture_report_is_serializable_and_declares_the_engine_first_model() -> None:
    report = arch.architecture_report()
    json.dumps(report)                                  # must be a machine-readable contract
    assert report["schema"] == arch.SCHEMA
    assert report["violations"] == []
    ids = {layer["id"] for layer in report["layers"]}
    assert {arch.ENGINE_CORE, arch.ENGINE_CONTROL_PLANE, arch.REFERENCE_APPLICATION} <= ids
    ai = next(a for a in report["reference_applications"] if a["id"] == "ai-combi")
    assert ai["status"] == "experimental"
    assert ai["role"] == arch.REFERENCE_APPLICATION
    assert {a["id"] for a in report["reference_applications"]} == {
        "ai-combi", "automation-scheme-studio"}
    assert {a["id"] for a in report["engine_demonstrations"]} == {"engine-demo"}


def _violates(importer_layer: str, imported_layer: str) -> bool:
    """Would the declaration reject this edge? Mirrors `dependency_violations`'
    decision for one edge, without needing the files to exist."""
    spec = arch.LAYERS_BY_ID[importer_layer]
    return imported_layer not in spec.may_import


def test_a_domain_application_may_use_the_engine_and_its_control_plane() -> None:
    """The whole point of the layer: `bundle/study.py` and the run entry points
    must be reachable, or a domain application would have to duplicate them."""
    for allowed in (arch.ENGINE_CORE, arch.ENGINE_CONTROL_PLANE, arch.DOMAIN_APPLICATION):
        assert not _violates(arch.DOMAIN_APPLICATION, allowed), allowed


def test_a_domain_application_may_not_import_a_reference_application() -> None:
    """This is the boundary the layer exists to enforce, and it is why
    `reference-application` was NOT reused: that layer may import itself, so
    nothing there would stop a domain application growing into the AI platform."""
    assert _violates(arch.DOMAIN_APPLICATION, arch.REFERENCE_APPLICATION)
    assert arch.REFERENCE_APPLICATION not in arch.LAYERS_BY_ID[arch.DOMAIN_APPLICATION].may_import


def test_a_domain_application_may_not_import_an_engine_demonstration() -> None:
    """The flagship SUTs are worked examples, not a framework. Copying one
    reproduces its assumptions along with its structure, which is exactly what a
    second domain is supposed to avoid."""
    assert _violates(arch.DOMAIN_APPLICATION, arch.ENGINE_DEMONSTRATION)


def test_the_engine_never_depends_on_a_domain_application() -> None:
    for engine_layer in (arch.ENGINE_CORE, arch.ENGINE_CONTROL_PLANE):
        assert _violates(engine_layer, arch.DOMAIN_APPLICATION), engine_layer


def test_the_domain_application_layer_is_audited() -> None:
    """A declared layer that the gate does not audit is decoration."""
    assert arch.DOMAIN_APPLICATION in arch.AUDITED_LAYERS


def test_tests_may_import_every_layer() -> None:
    """A layer added without being added here is invisible to the CLI gate, which
    audits only AUDITED_LAYERS, and surfaces only when a test module imports the
    new layer. That is exactly how the omission for `domain-application` was
    found -- by this file's own assertion, not by the gate."""
    allowed = set(arch.LAYERS_BY_ID[arch.TESTS].may_import)
    for spec in arch.LAYERS:
        assert spec.id in allowed, f"tests may not import {spec.id}"


def test_declaring_a_root_before_it_exists_is_harmless() -> None:
    """The layer names `genetics_model_testing` before any such directory exists,
    so the boundary is in force from that application's first commit rather than
    retrofitted. An absent root must therefore be skipped, not fatal."""
    spec = arch.LAYERS_BY_ID[arch.DOMAIN_APPLICATION]
    assert spec.roots, "the layer must claim at least one root"
    assert arch.dependency_violations() == []


def test_architecture_report_audits_every_non_test_product_layer(monkeypatch) -> None:
    observed = []

    def capture(layers):
        observed.append(tuple(layers))
        return []

    monkeypatch.setattr(arch, "dependency_violations", capture)
    arch.architecture_report()
    assert observed == [arch.AUDITED_LAYERS]


# ---------------------------- the engine works without the reference layer ----
_BLOCKER = textwrap.dedent(
    '''
    import sys
    class _Blocked:
        def find_module(self, name, path=None):
            return self.find_spec(name, path)
        def find_spec(self, name, path=None, target=None):
            blocked = ("AI_combi_testing_platform", "generator_trunk.AI_combi_testing_platform")
            if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked):
                raise ImportError("AI_combi_testing_platform is unavailable in this environment")
            return None
    sys.meta_path.insert(0, _Blocked())
    '''
).strip()


def _run_without_ai_platform(tmp_path: Path, code: str) -> subprocess.CompletedProcess:
    """Run `code` in a subprocess where importing the AI reference application
    raises, simulating its removal without mutating the source tree."""
    (tmp_path / "sitecustomize.py").write_text(_BLOCKER + "\n", encoding="utf-8")
    script = tmp_path / "probe.py"
    script.write_text(code, encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHONPATH": f"{tmp_path}:{REPO_ROOT / 'generator_trunk'}:{REPO_ROOT}",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("module_name", [
    "AI_combi_testing_platform",
    "generator_trunk.AI_combi_testing_platform",
])
def test_the_blocker_actually_blocks(tmp_path: Path, module_name: str) -> None:
    """Guards the two tests below: if the blocker silently stopped working they
    would pass for the wrong reason."""
    proc = _run_without_ai_platform(tmp_path, textwrap.dedent(f'''
        try:
            __import__({module_name!r})
        except ImportError:
            print("BLOCKED")
        else:
            print("NOT_BLOCKED")
    '''))
    assert proc.stdout.strip() == "BLOCKED", proc.stderr


def test_control_plane_imports_without_the_ai_platform(tmp_path: Path) -> None:
    proc = _run_without_ai_platform(tmp_path, textwrap.dedent('''
        from bundle import cli, stages, coverage, architecture  # noqa: F401
        print("CONTROL_PLANE_OK")
    '''))
    assert "CONTROL_PLANE_OK" in proc.stdout, proc.stderr


def test_direct_engine_smoke_plans_without_the_ai_platform(tmp_path: Path) -> None:
    """The acceptance criterion: removing the AI reference application must not
    prevent the direct engine demonstration from planning."""
    out = tmp_path / "plan"
    proc = _run_without_ai_platform(tmp_path, textwrap.dedent(f'''
        import sys
        sys.argv = ["bundle", "plan",
                    "generator_trunk/engine_demo/direct_engine_smoke",
                    "--out", {str(out)!r}]
        from bundle.cli import main
        raise SystemExit(main())
    '''))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert plan["seq_extra_rows"] == 3
    # The higher-order count is genuinely runtime-known; the plan must say so
    # rather than inventing an exact number.
    assert plan["cardinality"]["final"]["mode"] == "UNKNOWN"
