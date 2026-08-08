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

"""STEP 42 — normalized builds + component version inventory.

Each component has a canonical build command and an identifiable artifact; the
inventory is a versioned, machine-readable matrix recording declared version +
actual sha256. A baseline compare provides a warn/block mismatch policy. SBOM
generation is optional and never blocks. A canonical build of a changed component
(the Analyzer) is exercised when Maven is available — no full bundle workflow.

Run: `python3 -m pytest test_bundle_inventory.py -q`.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle import inventory as inv

_NAMES = {"generator", "core", "reader", "executor", "analyzer"}


# ---- inventory / matrix ---------------------------------------------------- #
def test_every_component_has_canonical_build_and_identifiable_artifact():
    invd = inv.build_inventory()
    inv.validate_inventory(invd)
    comps = {c["name"]: c for c in invd["components"]}
    assert set(comps) == _NAMES
    for name, c in comps.items():
        assert c["build_command"]                              # a canonical build command
        assert c["declared_version"]
        if c["kind"] == "maven":
            assert "mvn" in c["build_command"] and "package" in c["build_command"]
            assert c["artifact"].endswith(".jar")                 # identifiable output path
            if c["exists"]:                                      # built checkout: hash real output
                assert c.get("sha256") and c.get("size_bytes", 0) > 0
            else:                                                # fresh source checkout: no prebuilt JAR
                assert "sha256" not in c and "size_bytes" not in c
        else:
            assert c["build_command"].startswith("(interpreted")
    assert inv.canonical_build_command("analyzer").startswith("mvn")


def test_version_matrix_is_machine_readable_and_validates():
    invd = inv.build_inventory()
    assert invd["schema"] == inv.SCHEMA
    for k in ("python", "java", "maven", "postgresql"):
        assert k in invd["toolchain"]
    assert "generated_at" in invd
    text = inv.format_matrix(invd)
    assert "component version matrix" in text and "core" in text and "1.0.0" in text
    # JSON round-trips
    assert json.loads(json.dumps(invd))["components"]


def test_validate_rejects_defects():
    with pytest.raises(inv.InventoryError):
        inv.validate_inventory({"schema": "wrong"})
    good = inv.build_inventory()
    good["components"][0].pop("name")
    with pytest.raises(inv.InventoryError):
        inv.validate_inventory(good)


# ---- version-mismatch policy ---------------------------------------------- #
def test_compare_and_warn_block_policy():
    cur = inv.build_inventory()
    # Exercise hash policy independently of Maven outputs left by another test.
    for index, component in enumerate(cur["components"], start=1):
        component["exists"] = True
        component["sha256"] = f"{index:064x}"
        component["size_bytes"] = index
    same = inv.compare(cur, cur)
    assert all(d["status"] == "ok" for d in same)
    assert inv.enforce_policy(same, policy="block") == []      # no mismatch -> never blocks

    changed = json.loads(json.dumps(cur))
    core = next(c for c in changed["components"] if c["name"] == "core")
    core["sha256"] = "0" * 64                                  # baseline had a different hash
    diffs = inv.compare(cur, changed)
    assert any(d["component"] == "core" and d["status"] == "changed" for d in diffs)
    # warn: surfaces the mismatch but does not raise
    assert inv.enforce_policy(diffs, policy="warn")
    # block: raises
    with pytest.raises(inv.InventoryError, match="version mismatch.*core changed"):
        inv.enforce_policy(diffs, policy="block")


def test_missing_artifact_is_a_mismatch():
    cur = inv.build_inventory()
    cur2 = json.loads(json.dumps(cur))
    rdr = next(c for c in cur2["components"] if c["name"] == "reader")
    rdr["exists"] = False
    rdr.pop("sha256", None)
    diffs = inv.compare(cur2, cur)
    assert any(d["component"] == "reader" and d["status"] == "missing" for d in diffs)
    with pytest.raises(inv.InventoryError):
        inv.enforce_policy(diffs, policy="block")


# ---- SBOM (optional, non-blocking) ---------------------------------------- #
def test_sbom_is_optional_and_never_blocks():
    sb = inv.generate_sbom()
    assert "available" in sb
    if not sb["available"]:
        assert "skipped" in sb["reason"].lower() and ("syft" in sb["reason"] or "cyclonedx" in sb["reason"])


# ---- doctor records versions ---------------------------------------------- #
def test_doctor_records_component_versions():
    from bundle.doctor import run_doctor, Severity
    from bundle.config import BundleConfig
    checks = {c.name: c for c in run_doctor(BundleConfig())}
    assert "component_inventory" in checks
    chk = checks["component_inventory"]
    blob = chk.message + " " + " ".join(chk.details)
    for name in _NAMES:
        assert name in blob
    assert chk.severity in (Severity.OK, Severity.WARNING)     # OK when artifacts present


# ---- run manifest records the inventory ----------------------------------- #
def test_create_run_writes_component_inventory_to_manifest(tmp_path):
    from bundle.runs import create_run, file_sha256
    from bundle.jsonio import read_json
    from bundle.models import run_manifest_from_dict
    spec = tmp_path / "s.toml"
    spec.write_text("title='x'\n", encoding="utf-8")
    ci = inv.build_inventory()
    layout = create_run(runs_root=tmp_path / "runs", db_name="db", spec_path=spec,
                        spec_sha256=file_sha256(spec), mode="verdict", goals="",
                        scratch_root=tmp_path / "scratch", settings={}, run_id="ci-rec",
                        component_inventory=ci)
    rj = read_json(layout.manifest_path)
    assert rj["component_inventory"]["schema"] == inv.SCHEMA
    assert {c["name"] for c in rj["component_inventory"]["components"]} == _NAMES
    assert run_manifest_from_dict(rj).component_inventory["schema"] == inv.SCHEMA   # typed round-trip


def test_new_run_directory_auto_records_inventory_state(tmp_path):
    """The real run-creation path records versions and the current artifact
    state. A clean source checkout legitimately records an absent Maven JAR;
    once built, the same record includes its actual sha256."""
    import fwgen as fg
    from types import SimpleNamespace
    from bundle import cli
    from bundle.jsonio import read_json
    toml = tmp_path / "spec" / "s.toml"
    toml.parent.mkdir()
    toml.write_text('title = "t"\n[[slots]]\nsheet = "A"\nvalues = ["a1", "a2"]\n', encoding="utf-8")
    spec = fg.load_spec(toml)
    a = SimpleNamespace(runs_root=str(tmp_path / "runs"), db="bench", lang="py", mode="verdict",
                        analyzer="", main_port=5433, results_port=5432, sieve=False,
                        analysis_mode="exploratory", run_id="inv-rec")
    layout = cli._create_run_directory(a, spec, toml, tmp_path / "scratch")
    ci = read_json(layout.manifest_path)["component_inventory"]
    assert ci["schema"] == inv.SCHEMA
    names = {c["name"] for c in ci["components"]}
    assert _NAMES <= names
    core = next(c for c in ci["components"] if c["name"] == "core")
    assert core["declared_version"] == "1.0-SNAPSHOT"
    if core["exists"]:
        assert core.get("sha256") and core.get("size_bytes", 0) > 0
    else:
        assert "sha256" not in core and "size_bytes" not in core
    assert "toolchain" in ci                                    # versions recorded too


def test_source_only_checkout_records_missing_maven_artifacts(tmp_path):
    """Inventorying a fresh checkout must not require committed build outputs."""
    for comp in inv.COMPONENTS:
        rec = inv.artifact_record(comp, root=tmp_path)
        assert rec["exists"] is False
        assert "sha256" not in rec and "size_bytes" not in rec


# ---- CLI ------------------------------------------------------------------- #
def test_cli_inventory_writes_matrix(tmp_path):
    out = tmp_path / "matrix.json"
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "inventory", "--out", str(out)],
                       cwd=str(HERE), capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr
    m = json.loads(out.read_text(encoding="utf-8"))
    assert m["schema"] == inv.SCHEMA and {c["name"] for c in m["components"]} == _NAMES


def test_cli_inventory_blocks_on_baseline_mismatch(tmp_path):
    baseline = inv.build_inventory()
    next(c for c in baseline["components"] if c["name"] == "core")["sha256"] = "f" * 64
    bpath = tmp_path / "baseline.json"
    bpath.write_text(json.dumps(baseline), encoding="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "inventory",
                        "--baseline", str(bpath), "--policy", "block"],
                       cwd=str(HERE), capture_output=True, text=True, timeout=90)
    assert r.returncode != 0
    assert "version mismatch" in (r.stdout + r.stderr)


# ---- canonical build of a changed component (Maven) ------------------------ #
@pytest.mark.skipif(shutil.which("mvn") is None or not (inv.SRC / "Analyzer_trunk/pom.xml").exists(),
                    reason="Maven / Analyzer trunk not available")
def test_canonical_build_of_changed_component_produces_identifiable_artifact():
    """Run the Analyzer's canonical build (it was changed this effort) and confirm
    it produces the identifiable artifact the inventory records — no full workflow."""
    az = inv.SRC / "Analyzer_trunk"
    cmd = inv.canonical_build_command("analyzer")
    r = subprocess.run(cmd, shell=True, cwd=str(az), capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout + r.stderr)[-800:]
    rec = inv.artifact_record(next(c for c in inv.COMPONENTS if c.name == "analyzer"))
    assert rec["exists"] and rec["declared_version"] == "1.0.0"
    art = inv.SRC / rec["trunk"] / rec["artifact"]
    import hashlib
    assert rec["sha256"] == hashlib.sha256(art.read_bytes()).hexdigest()   # inventory hash == on-disk artifact


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
