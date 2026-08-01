"""STEP 42 — normalized builds + machine-readable component version inventory.

Each component (Generator / Core / Reader / Executor / Analyzer) has a CANONICAL
build command and an identifiable artifact; this module exports a versioned,
machine-readable inventory (the compatibility matrix) recording each artifact's
declared version + actual sha256 + the build command that produces it. A
mismatch policy (`compare` + `enforce_policy`) warns or blocks when an artifact's
hash drifts from a recorded baseline. SBOM generation is attempted only when a
toolchain (syft / cyclonedx) is already present — a missing optional tool is
reported, never a build blocker.

It does NOT mass-align dependencies or rebuild anything itself: it inventories
what the canonical builds produce.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .runs import file_sha256

HERE = Path(__file__).resolve().parent.parent          # generator_trunk/
SRC = HERE.parent                                       # repo root (the *_trunk parent)

SCHEMA = "bundle.inventory/v1"

# A repeatable online-first reactor build (no tests/verifiers).  `-am` includes
# source dependencies from the repository (the Analyzer for Reader, and the
# restored combinatorics library for Core), so this command also works with an
# empty Maven cache. `-Dexec.skip` is a no-op for trunks without the exec plugin.
def _maven_artifact(trunk: str) -> str:
    return (f"mvn -q -f ../pom.xml -pl {trunk} -am "
            "-DskipTests -Dexec.skip=true package")


@dataclass(frozen=True)
class Component:
    name: str
    kind: str            # "maven" | "python"
    trunk: str           # dir under the repo root
    build_command: str   # canonical, repeatable artifact build
    artifact: str        # path under the trunk (jar) or the entry source file
    declared_version: str


COMPONENTS = (
    Component("generator", "python", "generator_trunk",
              "(interpreted — no build step; run with python3)", "fwgen.py", "interpreted"),
    Component("core", "maven", "Core_trunk", _maven_artifact("Core_trunk"),
              "target/migrated-project-1.0-SNAPSHOT.jar", "1.0-SNAPSHOT"),
    Component("reader", "maven", "Reader_trunk", _maven_artifact("Reader_trunk"),
              "target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar", "1.0-SNAPSHOT"),
    Component("executor", "maven", "Executor_trunk", _maven_artifact("Executor_trunk"),
              "target/Executor-1.0-jar-with-dependencies.jar", "1.0"),
    Component("analyzer", "maven", "Analyzer_trunk", _maven_artifact("Analyzer_trunk"),
              "target/heuristic-analyzer-flatlaf-1.0.0.jar", "1.0.0"),
)


class InventoryError(Exception):
    """An inventory defect, or a blocked version mismatch (policy=block)."""


# --------------------------------------------------------------------------- #
def _probe(cmd, *, stderr: bool = False) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (r.stderr if stderr else r.stdout) or r.stdout or r.stderr
        return (out.strip().splitlines() or ["unknown"])[0]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def toolchain_versions() -> dict:
    import platform
    return {
        "python": platform.python_version(),
        "java": _probe(["java", "-version"], stderr=True),
        "maven": _probe(["mvn", "-v"]),
        "postgresql": _probe(["psql", "--version"]),
    }


def canonical_build_command(name: str) -> str:
    for c in COMPONENTS:
        if c.name == name:
            return c.build_command
    raise InventoryError(f"unknown component {name!r}")


def artifact_record(comp: Component, root: Path = SRC) -> dict:
    """Identifiable-artifact record for one component: build command + declared
    version + actual sha256/size (when the artifact exists)."""
    art = root / comp.trunk / comp.artifact
    rec = {
        "name": comp.name, "kind": comp.kind, "trunk": comp.trunk,
        "build_command": comp.build_command, "declared_version": comp.declared_version,
        "artifact": comp.artifact, "exists": art.is_file(),
    }
    if art.is_file():
        rec["sha256"] = file_sha256(art)
        rec["size_bytes"] = art.stat().st_size
    return rec


def build_inventory(root: Path = SRC) -> dict:
    """The full machine-readable version matrix (versioned)."""
    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "toolchain": toolchain_versions(),
        "components": [artifact_record(c, root) for c in COMPONENTS],
    }


def validate_inventory(inv: dict) -> None:
    if inv.get("schema") != SCHEMA:
        raise InventoryError(f"bad schema {inv.get('schema')!r} (want {SCHEMA!r})")
    for key in ("generated_at", "toolchain", "components"):
        if key not in inv:
            raise InventoryError(f"inventory missing {key!r}")
    if not inv["components"]:
        raise InventoryError("inventory has no components")
    for c in inv["components"]:
        for f in ("name", "kind", "build_command", "declared_version", "exists"):
            if f not in c:
                raise InventoryError(f"component {c.get('name')!r} missing field {f!r}")
        if c["exists"] and "sha256" not in c:
            raise InventoryError(f"component {c['name']!r} exists but has no sha256")


# --------------------------------------------------------------------------- #
def compare(current: dict, baseline: dict) -> list:
    """Diff a current inventory against a baseline. Per component:
    ``ok`` | ``changed`` (hash drift) | ``missing`` (artifact absent now) |
    ``new`` (not in baseline)."""
    base = {c["name"]: c for c in baseline.get("components", [])}
    out = []
    for c in current.get("components", []):
        b = base.get(c["name"])
        if b is None:
            out.append({"component": c["name"], "status": "new", "detail": "not present in baseline"})
        elif not c.get("exists"):
            out.append({"component": c["name"], "status": "missing", "detail": "artifact absent"})
        elif c.get("sha256") != b.get("sha256"):
            out.append({"component": c["name"], "status": "changed",
                        "detail": f"sha256 {str(b.get('sha256'))[:12]}… → {str(c.get('sha256'))[:12]}…"})
        else:
            out.append({"component": c["name"], "status": "ok", "detail": "hash matches baseline"})
    return out


def enforce_policy(diffs: list, *, policy: str = "warn") -> list:
    """Apply the version-mismatch policy. ``warn`` returns the offending diffs;
    ``block`` raises :class:`InventoryError` if any artifact CHANGED or is MISSING
    (``new`` is informational and never blocks)."""
    blocking = [d for d in diffs if d["status"] in ("changed", "missing")]
    if policy == "block" and blocking:
        raise InventoryError("version mismatch (policy=block): "
                             + "; ".join(f"{d['component']} {d['status']}" for d in blocking))
    return [d for d in diffs if d["status"] != "ok"]


# --------------------------------------------------------------------------- #
def sbom_tool() -> "Optional[str]":
    for tool in ("syft", "cyclonedx", "cyclonedx-py"):
        try:
            if subprocess.run([tool, "--version"], capture_output=True, timeout=10).returncode == 0:
                return tool
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def generate_sbom(out_dir: "Optional[Path]" = None) -> dict:
    """Generate an SBOM IF a toolchain (syft/cyclonedx) is already available.
    A missing tool is reported, never raised — the main build is never blocked
    by an absent optional plugin."""
    tool = sbom_tool()
    if tool is None:
        return {"available": False, "tool": None,
                "reason": "no SBOM tool (syft / cyclonedx) on PATH — skipped (optional, non-blocking)"}
    out_dir = Path(out_dir) if out_dir else SRC
    out_path = out_dir / "sbom.json"
    try:
        if tool == "syft":
            r = subprocess.run([tool, f"dir:{SRC}", "-o", "cyclonedx-json"],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                out_path.write_text(r.stdout, encoding="utf-8")
                return {"available": True, "tool": tool, "path": str(out_path)}
        return {"available": True, "tool": tool, "error": "SBOM generation failed (non-blocking)"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "tool": tool, "error": f"{exc} (non-blocking)"}


# --------------------------------------------------------------------------- #
def format_matrix(inv: dict) -> str:
    lines = [f"component version matrix ({inv['schema']}, {inv['generated_at']})"]
    tc = inv["toolchain"]
    lines.append(f"  toolchain: python {tc['python']} | {tc['java']} | {tc['maven']} | {tc['postgresql']}")
    lines.append(f"  {'component':<11}{'kind':<8}{'version':<16}{'artifact sha256':<20}{'build'}")
    for c in inv["components"]:
        sha = (c.get("sha256", "")[:16] or "(missing)") if c["exists"] else "(MISSING)"
        lines.append(f"  {c['name']:<11}{c['kind']:<8}{c['declared_version']:<16}{sha:<20}{c['build_command']}")
    return "\n".join(lines)
