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

"""Release manifest, SBOM and skip classification (Prompt 03 Parts C and D).

Three things a release needs to be answerable about, and one rule they share:
**nothing is asserted that was not observed on the machine that produced it.**

* :func:`release_manifest` — what this release *is*: source revision and dirty
  state, toolchain versions, hashes of the release inputs, the generated
  capability matrix, the canonical SUT inventory, and the test/skip summary.
* :func:`generate_sbom` — a CycloneDX software bill of materials over the Python
  distributions, Maven modules and container images actually declared here.
* :func:`classify_skip` — every skipped test lands in one of four classes, and
  one of them fails the gate.

Reproducibility is claimed narrowly and the boundary is stated in the artifact
itself: Maven jars are not byte-reproducible (zip entry timestamps), so a
component's artifact hash changes across rebuilds even from identical source.
"Reproducible" here means *same source revision -> same declared versions and
the same set of inputs*, with each artifact freshly hashed — not byte equality.

Generated instances are release artifacts, not source. Only this generator, its
schema, its golden fixtures and its tests are committed.
"""
from __future__ import annotations

import collections
import hashlib
import json
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import quote

from . import architecture as arch
from . import capabilities as caps

RELEASE_SCHEMA = "bundle.release-manifest/v1"
SBOM_SCHEMA = "CycloneDX/1.5"

REPO_ROOT = arch.REPO_ROOT

# --------------------------------------------------------- skip classes ------
EXPECTED_OPTIONAL = "EXPECTED_OPTIONAL"
UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
MISSING_AUTHORIZED_BACKEND = "MISSING_AUTHORIZED_BACKEND"
BLOCKING_UNEXPECTED = "BLOCKING_UNEXPECTED"
SKIP_CLASSES = (EXPECTED_OPTIONAL, UNSUPPORTED_PLATFORM,
                MISSING_AUTHORIZED_BACKEND, BLOCKING_UNEXPECTED)

#: Reason patterns -> class. Ordered: the first match wins. Anything unmatched is
#: BLOCKING_UNEXPECTED, because an unclassified skip on a release path is exactly
#: the thing that quietly turns a gate green.
_SKIP_PATTERNS: "tuple[tuple[str, str], ...]" = (
    (r"EXPECTED_OPTIONAL", EXPECTED_OPTIONAL),
    (r"UNSUPPORTED_PLATFORM", UNSUPPORTED_PLATFORM),
    (r"MISSING_AUTHORIZED_BACKEND", MISSING_AUTHORIZED_BACKEND),
    (r"could not import ['\"]?grpc", EXPECTED_OPTIONAL),
    # The Analyzer driver classes are built lazily on first --analyzer use, so a
    # publish-clean checkout legitimately lacks them. Several suites word this
    # differently ("Analyzer jar/AnalyzeKv build not present", "Analyzer build
    # (BundleControlPlane.class + analyzer_cp.txt) not present").
    (r"analyzer\b.*not present", EXPECTED_OPTIONAL),
    (r"opt-in|explicitly enabled|live e2e|set [a-z0-9_]+=1", EXPECTED_OPTIONAL),
    (r"refus\w+ to delete|would delete a real", EXPECTED_OPTIONAL),
    (r"requires? linux|not supported on (macos|windows)|platform", UNSUPPORTED_PLATFORM),
    (r"docker|podman|container runtime|bubblewrap|rootless", MISSING_AUTHORIZED_BACKEND),
    (r"postgres|database not reachable|no database", MISSING_AUTHORIZED_BACKEND),
    (r"jdk|java (not )?available|maven|jar (missing|not present)", MISSING_AUTHORIZED_BACKEND),
    (r"BUNDLE_SUT_ROOT|sibling (sut )?checkout|automation_constructor", MISSING_AUTHORIZED_BACKEND),
)


def classify_skip(reason: str) -> str:
    """Classify one skip reason. Unrecognized reasons are BLOCKING_UNEXPECTED.

    Fail-closed by construction: a new skip nobody has thought about must stop a
    release gate rather than be silently tolerated.
    """
    text = (reason or "").strip()
    if not text:
        return BLOCKING_UNEXPECTED
    lowered = text.lower()
    for pattern, klass in _SKIP_PATTERNS:
        if re.search(pattern, text if pattern.isupper() else lowered,
                     0 if pattern.isupper() else re.IGNORECASE):
            return klass
    return BLOCKING_UNEXPECTED


@dataclass(frozen=True)
class SkipReport:
    """The classified skip summary for one test run."""

    total: int
    by_class: "Mapping[str, int]"
    entries: "tuple[Mapping[str, str], ...]"

    @property
    def blocking(self) -> "list[Mapping[str, str]]":
        return [e for e in self.entries if e["class"] == BLOCKING_UNEXPECTED]

    @property
    def release_blocking(self) -> "list[Mapping[str, str]]":
        """Skips that invalidate release evidence.

        A missing authorized backend is a useful classification, but it is not
        successful execution.  Treating it as non-blocking allowed a release job
        with no database or sibling SUT to remain green.
        """
        return [e for e in self.entries
                if e["class"] in (BLOCKING_UNEXPECTED, MISSING_AUTHORIZED_BACKEND)]

    def to_dict(self) -> dict:
        return {"total": self.total, "by_class": dict(self.by_class),
                "entries": [dict(e) for e in self.entries],
                "blocking": [dict(e) for e in self.blocking],
                "release_blocking": [dict(e) for e in self.release_blocking]}


def classify_skips(reasons: "Sequence[str]") -> SkipReport:
    entries = []
    counts = {k: 0 for k in SKIP_CLASSES}
    for reason in reasons:
        klass = classify_skip(reason)
        counts[klass] += 1
        entries.append({"reason": reason.strip(), "class": klass})
    return SkipReport(total=len(entries), by_class=counts, entries=tuple(entries))


#: pytest's short summary line: ``SKIPPED [1] path:line: reason``. The count is
#: evidence: parametrized skips are often grouped into one line, so counting
#: lines under-reports how much of the suite did not execute.
_PYTEST_SKIP_RE = re.compile(
    r"^SKIPPED\s*\[(?P<count>\d+)\]\s*(?P<where>.+:\d+):\s*(?P<reason>.*)$")


def parse_pytest_skips(output: str) -> "list[dict]":
    """Extract grouped ``(count, location, reason)`` entries from ``pytest -ra``."""
    found = []
    for line in (output or "").splitlines():
        match = _PYTEST_SKIP_RE.match(line.strip())
        if match:
            found.append({"count": int(match.group("count")),
                          "where": match.group("where").strip(),
                          "reason": match.group("reason").strip()})
    return found


_PYTEST_RESULT_RE = re.compile(
    r"(?P<count>\d+)\s+(?P<kind>passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b",
    re.IGNORECASE,
)
_PYTEST_EXIT_RE = re.compile(r"^BUNDLE_PYTEST_EXIT_CODE=(?P<code>\d+)$", re.MULTILINE)


def parse_pytest_summary(output: str) -> dict:
    """Parse pytest's final terminal-summary count line, failing closed on absence.

    The release gate must never infer success merely because a log contains a
    ``passed`` token. We scan from the end for the final duration-bearing summary
    (for example ``2 failed, 10 passed in 3.2s``) and record failures/errors
    explicitly. A truncated/interrupted log has ``complete=false`` and blocks the
    release path just like a failed test.
    """
    text = output or ""
    exit_matches = list(_PYTEST_EXIT_RE.finditer(text))
    exit_code = int(exit_matches[-1].group("code")) if exit_matches else None
    interrupted = bool(re.search(
        r"(^|\n)(?:INTERNALERROR>|!+\s*(?:KeyboardInterrupt|Interrupted)|"
        r"=+\s*KeyboardInterrupt)", text, re.IGNORECASE))
    for raw_line in reversed(text.splitlines()):
        line = raw_line.strip()
        if not re.search(r"\bin\s+\d+(?:\.\d+)?s(?:\s|$)", line):
            continue
        matches = list(_PYTEST_RESULT_RE.finditer(line))
        if not matches:
            continue
        counts = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "xfailed": 0,
            "xpassed": 0,
            "deselected": 0,
        }
        for match in matches:
            kind = match.group("kind").lower()
            if kind in ("error", "errors"):
                kind = "errors"
            counts[kind] = int(match.group("count"))
        return {"complete": not interrupted, "summary_line": line,
                "exit_code": exit_code, "interrupted": interrupted, **counts}
    return {
        "complete": False,
        "summary_line": "",
        "exit_code": exit_code,
        "interrupted": interrupted,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }


# ------------------------------------------------------------- provenance ----
def _run(cmd: "Sequence[str]", *, cwd: "Path | None" = None) -> str:
    try:
        proc = subprocess.run(list(cmd), cwd=str(cwd or REPO_ROOT), capture_output=True,
                              text=True, timeout=120)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _repository_files(pathspecs: "Sequence[str]", fallback_name: str) -> "list[Path]":
    """Files belonging to this repository, never a nested/ignored checkout.

    Tier 2/3 check the private sibling SUT out at ``SUT/`` inside the GitHub
    workspace and hide it with ``.git/info/exclude``. A raw ``rglob`` crossed
    that boundary and made the Framework SBOM depend on whichever private files
    happened to be present. In a Git checkout, Git's tracked set is the source
    boundary. Extracted source trees have no Git metadata, so they use a
    conservative filesystem fallback with generated/nested directories excluded.
    """
    if _run(["git", "rev-parse", "--is-inside-work-tree"]) == "true":
        listed = _run(["git", "ls-files", "--", *pathspecs])
        return [REPO_ROOT / line for line in listed.splitlines()
                if line.strip() and (REPO_ROOT / line).is_file()]
    excluded = {".git", ".venv", "node_modules", "target", "SUT", "__pycache__"}
    return [path for path in sorted(REPO_ROOT.rglob(fallback_name))
            if path.is_file() and not (set(path.relative_to(REPO_ROOT).parts) & excluded)]


def source_revision() -> dict:
    """Source identity, including whether the tree was dirty.

    An extracted tree may have no Git metadata at all; that is recorded as
    ``available: false`` rather than invented. The content-addressed engine
    revision is always present, so two manifests remain comparable either way.
    """
    head = _run(["git", "rev-parse", "HEAD"])
    if not head:
        return {"available": False, "engine_revision": arch.engine_revision(),
                "note": "no Git metadata in this tree; the engine revision identifies the source"}
    status = _run(["git", "status", "--porcelain"])
    return {
        "available": True,
        "commit": head,
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": bool(status),
        "dirty_paths": sorted(line[3:] for line in status.splitlines())[:200] if status else [],
        "engine_revision": arch.engine_revision(),
    }


def toolchain() -> dict:
    def first_line(cmd, stderr=False):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            out = (proc.stderr if stderr else proc.stdout) or proc.stdout or proc.stderr
            return (out.strip().splitlines() or ["unknown"])[0]
        except (OSError, subprocess.SubprocessError):
            return "unknown"
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "java": first_line(["java", "-version"], stderr=True),
        "maven": first_line(["mvn", "-v"]),
        "postgresql_client": first_line(["psql", "--version"]),
        "docker": first_line(["docker", "--version"]),
        "platform": platform.platform(),
    }


#: Files whose content defines what a release IS. Hashed individually so a
#: reviewer can see exactly which input changed between two manifests.
RELEASE_INPUT_GLOBS = (
    "pyproject.toml", "requirements-release.lock", "pom.xml",
    "*/pom.xml",
    "generator_trunk/bundle/*.py",
    "generator_trunk/bundle_run.py",
    "generator_trunk/bundle-*.schema.json",
    "generator_trunk/sut_manifests/*.json",
    "generator_trunk/deploy/docker-compose.yml",
    ".github/workflows/*.yml",
    "docs/33_CAPABILITY_MATRIX.md",
    "docs/34_RELEASE_REPRODUCIBILITY.md",
)


def release_inputs() -> "list[dict]":
    seen: "dict[str, dict]" = {}
    for pattern in RELEASE_INPUT_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = arch.repo_relative(path)
            seen[rel] = {"path": rel, "bytes": path.stat().st_size,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return [seen[k] for k in sorted(seen)]


# ------------------------------------------------------------------ SBOM -----
_LOCK_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)==(?P<version>[^\s;]+)$")


def locked_python_requirements() -> "list[tuple[str, str]]":
    """Return the exact Python versions declared by the release lock.

    This parser is intentionally narrow: a range, editable requirement, URL or
    marker is not silently treated as an exact release pin.
    """
    lock = REPO_ROOT / "requirements-release.lock"
    if not lock.is_file():
        raise ValueError("requirements-release.lock is missing")
    out = []
    for number, raw in enumerate(lock.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LOCK_REQUIREMENT_RE.fullmatch(line)
        if not match:
            raise ValueError(
                f"requirements-release.lock:{number}: not an exact name==version pin: {line!r}")
        out.append((match.group("name"), match.group("version")))
    if not out:
        raise ValueError("requirements-release.lock contains no requirements")
    return out


_DECLARED_REQUIREMENT_NAME_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^]]+\])?")


def _canonical_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_python_requirements() -> "list[dict]":
    """Every checked-in Python dependency declaration, including optional UI.

    The Tier-3 lock intentionally covers only ``test,science,deploy``. Treating
    that as if it also locked the GUI, gateway, ML and browser extras concealed
    real release surfaces. This inventory makes the omissions explicit without
    resolving anything from the network.
    """
    import tomllib

    declarations = []

    def add(raw: str, source: str, role: str) -> None:
        requirement = raw.strip()
        if not requirement or requirement.startswith(("#", "-")):
            return
        match = _DECLARED_REQUIREMENT_NAME_RE.match(requirement)
        if not match:
            declarations.append({"name": "(unparsed)", "requirement": requirement,
                                 "source": source, "role": role})
            return
        declarations.append({
            "name": _canonical_python_name(match.group("name")),
            "requirement": requirement, "source": source, "role": role,
        })

    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        for requirement in data.get("build-system", {}).get("requires", ()):
            add(requirement, "pyproject.toml#build-system.requires", "build")
        project = data.get("project", {})
        for requirement in project.get("dependencies", ()):
            add(requirement, "pyproject.toml#project.dependencies", "runtime")
        for extra, requirements in project.get("optional-dependencies", {}).items():
            for requirement in requirements:
                add(requirement, f"pyproject.toml#project.optional-dependencies.{extra}",
                    f"optional:{extra}")

    for path in _repository_files(("*requirements*.txt",), "requirements*.txt"):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            add(raw, arch.repo_relative(path), "requirements-file")
    return declarations

def _declared_license_names(metadata) -> "list[str]":
    values = []
    expression = (metadata.get("License-Expression") or "").strip()
    legacy = (metadata.get("License") or "").strip()
    for value in (expression, legacy):
        if value and len(value) < 120 and value not in values:
            values.append(value)
    for classifier in metadata.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            value = classifier.split("::")[-1].strip()
            if value and value not in values:
                values.append(value)
    return values


def _python_components() -> "list[dict]":
    """Only distributions in the checked-in release lock.

    The old implementation enumerated the executing host's entire site-packages
    (219 packages on one reviewer machine), so the SBOM changed with unrelated
    tools installed beside the project.  The lock is the release boundary;
    local metadata is consulted only to enrich those locked entries.
    """
    components = []
    from importlib import metadata
    for name, version in locked_python_requirements():
        licenses, installed = [], "not-installed"
        try:
            dist = metadata.distribution(name)
            installed = dist.version or "unknown"
            # Metadata from a different installed version is not evidence about
            # the exact locked release. Keep the mismatch visible, but never
            # borrow its licence declaration.
            if installed == version:
                licenses = _declared_license_names(dist.metadata)
        except metadata.PackageNotFoundError:
            pass
        components.append({
            "type": "library", "name": name, "version": version,
            "purl": (f"pkg:pypi/{quote(name.lower().replace('_', '-'), safe='-.')}@"
                     f"{quote(version, safe='.-+')}"),
            "licenses": [{"license": {"name": value}} for value in licenses],
            "properties": [
                {"name": "bundle:source", "value": "requirements-release.lock"},
                {"name": "bundle:installed_metadata_version", "value": installed},
                {"name": "bundle:installed_version_matches_lock",
                 "value": str(installed == version).lower()},
            ],
        })
    return components


def _local_name(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _direct_text(element, name: str) -> str:
    for child in list(element):
        if _local_name(child) == name:
            return (child.text or "").strip()
    return ""


def _resolve_maven_value(value: str, properties: Mapping[str, str]) -> str:
    for _ in range(8):
        match = re.search(r"\$\{([^}]+)\}", value)
        if not match or match.group(1) not in properties:
            break
        value = value[:match.start()] + properties[match.group(1)] + value[match.end():]
    return value or "(managed/unresolved)"


def _maven_declarations() -> "list[dict]":
    """Reactor modules plus direct dependencies, plugins and extensions.

    This is a declaration inventory, not a resolved transitive dependency tree.
    It nevertheless includes the third-party code/build tools the former SBOM
    omitted entirely.
    """
    seen: "dict[tuple[str, str, str, str], dict]" = {}
    for pom in _repository_files(("*pom.xml",), "pom.xml"):
        rel = arch.repo_relative(pom)
        try:
            root = ET.fromstring(pom.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ET.ParseError):
            continue
        properties = {}
        for child in list(root):
            if _local_name(child) == "properties":
                properties.update({_local_name(p): (p.text or "").strip() for p in list(child)})
        parent = next((c for c in list(root) if _local_name(c) == "parent"), None)
        project_group = _direct_text(root, "groupId") or (_direct_text(parent, "groupId") if parent is not None else "")
        project_version = _direct_text(root, "version") or (_direct_text(parent, "version") if parent is not None else "")
        project_artifact = _direct_text(root, "artifactId")
        properties.update({
            "project.groupId": project_group, "pom.groupId": project_group,
            "project.version": project_version, "pom.version": project_version,
            "project.artifactId": project_artifact, "pom.artifactId": project_artifact,
        })

        def add(node, role: str, default_group: str = "") -> None:
            group = _resolve_maven_value(_direct_text(node, "groupId") or default_group,
                                          properties)
            artifact = _resolve_maven_value(_direct_text(node, "artifactId"), properties)
            version = _resolve_maven_value(_direct_text(node, "version"), properties)
            if not artifact:
                return
            scope = _direct_text(node, "scope") or ("build" if role != "dependency" else "compile")
            key = (group, artifact, version, role)
            item = seen.setdefault(key, {
                "group": group or "(default/unresolved)", "name": artifact,
                "version": version, "role": role, "scope": scope, "sources": [],
            })
            if rel not in item["sources"]:
                item["sources"].append(rel)

        if project_artifact:
            fake = ET.Element("project")
            for key, value in (("groupId", project_group), ("artifactId", project_artifact),
                               ("version", project_version)):
                ET.SubElement(fake, key).text = value
            add(fake, "reactor-module")
        for node in root.iter():
            local = _local_name(node)
            if local == "dependency":
                add(node, "dependency")
            elif local == "plugin":
                add(node, "plugin", "org.apache.maven.plugins")
            elif local == "extension":
                add(node, "extension")
            elif local in ("protocArtifact", "pluginArtifact") and node.text:
                parts = node.text.strip().split(":")
                if len(parts) >= 3:
                    fake = ET.Element("tool")
                    for key, value in (("groupId", parts[0]), ("artifactId", parts[1]),
                                       ("version", parts[2])):
                        ET.SubElement(fake, key).text = value
                    add(fake, "build-tool-artifact")
    return [seen[k] for k in sorted(seen)]


def _maven_declared_licenses(group: str, artifact: str, version: str) -> "list[str]":
    """Read licenses only from the exact resolved ``group:artifact:version`` POM.

    Artifact-name-only matching can associate one version's metadata with a
    different dependency that happens to share the name.  Missing local
    metadata stays missing; this function never guesses or searches another
    version as a substitute.
    """
    if not group or not artifact or not _maven_version_is_pinned(version):
        return []
    def names_from(path: Path) -> "list[str]":
        if not path.is_file():
            return []
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ET.ParseError):
            return []
        names = []
        for node in root.iter():
            if _local_name(node) == "license":
                name = _direct_text(node, "name")
                if name and name not in names:
                    names.append(name)
        return names

    # A reactor module's checked-in POM is the exact source declaration; it is
    # stronger evidence than an absent/stale ~/.m2 copy of the same SNAPSHOT.
    for declaration in _maven_declarations():
        if (declaration["role"] == "reactor-module"
                and (declaration["group"], declaration["name"], declaration["version"])
                == (group, artifact, version)):
            names = []
            for source in declaration["sources"]:
                for name in names_from(REPO_ROOT / source):
                    if name not in names:
                        names.append(name)
            return names

    pom = (Path.home() / ".m2" / "repository" / Path(*group.split(".")) / artifact /
           version / f"{artifact}-{version}.pom")
    return names_from(pom)


def _maven_components() -> "list[dict]":
    """Unique Maven coordinates from checked-in reactor POMs.

    One coordinate can be both a reactor module and a dependency. CycloneDX
    requires one component identity, so roles/scopes/sources are merged rather
    than emitting duplicate purls.
    """
    grouped: "dict[tuple[str, str, str], dict]" = {}
    for entry in _maven_declarations():
        key = (entry["group"], entry["name"], entry["version"])
        item = grouped.setdefault(key, {"roles": set(), "scopes": set(), "sources": set()})
        item["roles"].add(entry["role"])
        item["scopes"].add(entry["scope"])
        item["sources"].update(entry["sources"])
    components = []
    for (g, a, v), entry in sorted(grouped.items()):
        licenses = _maven_declared_licenses(g, a, v)
        first_party = ("reactor-module" in entry["roles"]
                       and not any(source.startswith("Combinatoricslib3parallel/")
                                   for source in entry["sources"]))
        components.append({
            "type": "application" if "reactor-module" in entry["roles"] else "library",
            "name": a, "version": v, "group": g,
            "purl": (f"pkg:maven/{quote(g, safe='.')}/{quote(a, safe='.-_')}@"
                     f"{quote(v, safe='.-+')}"),
            "licenses": [{"license": {"name": value}} for value in licenses],
            "properties": [
                {"name": "bundle:source", "value": ",".join(sorted(entry["sources"]))},
                {"name": "bundle:maven_role", "value": ",".join(sorted(entry["roles"]))},
                {"name": "bundle:maven_scope", "value": ",".join(sorted(entry["scopes"]))},
                {"name": "bundle:first_party", "value": str(first_party).lower()},
            ],
        })
    return components


def _declared_container_images() -> "list[dict]":
    found: "dict[str, set[str]]" = collections.defaultdict(set)
    candidates = [REPO_ROOT / "generator_trunk" / "deploy" / "docker-compose.yml"]
    candidates += sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    candidates += _repository_files(("*Dockerfile*",), "Dockerfile*")
    for path in candidates:
        if not path.is_file() or "/target/" in f"/{arch.repo_relative(path)}/":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        patterns = [r"^\s*image:\s*[\"']?(?P<ref>[^\s\"']+)",
                    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<ref>\S+)"]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                reference = match.group("ref")
                if "${{" in reference or reference.lower() == "scratch":
                    continue
                found[reference].add(arch.repo_relative(path))
    return [{"reference": ref, "sources": sorted(sources)}
            for ref, sources in sorted(found.items())]


def _container_components() -> "list[dict]":
    """Container images named in deploy, CI and Dockerfiles."""
    components = []
    for entry in _declared_container_images():
        reference = entry["reference"]
        without_digest = reference.split("@", 1)[0]
        name, sep, version = without_digest.rpartition(":")
        if not sep or "/" in version:
            name, version = without_digest, "latest"
        components.append({
            "type": "container", "name": name, "version": version or "latest",
            "purl": f"pkg:docker/{name}@{version or 'latest'}",
            "properties": [
                {"name": "bundle:pinned_by_digest", "value": str("@sha256:" in reference)},
                {"name": "bundle:source", "value": ",".join(entry["sources"])},
            ],
        })
    return components


def generate_sbom(*, timestamp: "str | None" = None) -> dict:
    """A CycloneDX SBOM over the Python, Maven and container components declared
    in this checkout.

    Scope is stated in the document: it covers what this repository *declares*,
    resolved from local metadata. It is not a transitive lockfile-derived SBOM,
    because producing one requires resolution the release must not silently
    perform.
    """
    components = _python_components() + _maven_components() + _container_components()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "component": {"type": "application", "name": "framework-bundle",
                          "version": arch.engine_revision()},
            "tools": [{"vendor": "Combinatorics Framework",
                       "name": "bundle_run.py release --sbom"}],
            "properties": [
                {"name": "bundle:scope",
                 "value": "Python components come only from requirements-release.lock; Maven "
                          "covers reactor modules plus declared dependencies/plugins/extensions; "
                          "containers cover deploy, CI and Dockerfiles. This is not a transitive "
                          "Maven dependency SBOM and the Python lock pins versions, not wheel hashes."},
                {"name": "bundle:source_revision",
                 "value": source_revision().get("commit", "unavailable")},
            ],
        },
        "components": components,
    }


# --------------------------------------------------- dependency pin audit ----
#: What "pinned" means per ecosystem, and what an unpinned entry actually risks.
_PIN_KINDS = {
    "github-action": "a mutable tag can be repointed by the action's owner at any time; a full "
                     "commit SHA cannot",
    "container-image": "a tag can be rebuilt and republished; only an immutable @sha256 digest "
                       "identifies the same bytes",
    "python": "a range resolves differently over time; a release gate needs a resolved lock",
    "maven": "a version range or a SNAPSHOT resolves differently over time",
    "node": "a lockfile is required for a reproducible install",
}

# Both YAML spellings: a bare `uses:` under a `- name:` step, and the compact
# `- uses:` list-item form. Missing the second silently UNDER-reports, which
# is the worst failure mode for an audit whose job is to find gaps.
_ACTION_RE = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>[\w.\-/]+)@(?P<version>\S+)", re.MULTILINE)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _maven_version_is_pinned(version: str) -> bool:
    upper = version.upper()
    return bool(version and version != "(managed/unresolved)"
                and "${" not in version and "SNAPSHOT" not in upper
                and not any(ch in version for ch in "[,]()"))


def _dedupe_pin_entries(entries: "Sequence[dict]") -> "list[dict]":
    unique: "dict[tuple[str, str, str], dict]" = {}
    for raw in entries:
        key = (raw["kind"], raw["name"], raw["pin"])
        source = raw.get("source", "")
        if key not in unique:
            item = dict(raw)
            item["sources"] = [source] if source else []
            item["occurrences"] = 1
            unique[key] = item
        else:
            unique[key]["occurrences"] += 1
            if source and source not in unique[key]["sources"]:
                unique[key]["sources"].append(source)
    return [unique[key] for key in sorted(unique)]


def dependency_pins() -> dict:
    """Audit how reproducibly each dependency source is pinned.

    Reports what IS, not what should be. Resolving a tag to a SHA or a digest
    needs the network, and a release manifest must never silently perform network
    resolution — so an unpinned entry is reported as unpinned, with the exact
    command an operator runs to fix it.
    """
    entries: "list[dict]" = []

    for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in _ACTION_RE.finditer(text):
            ref, version = match.group("ref"), match.group("version")
            entries.append({
                "kind": "github-action", "name": ref, "pin": version,
                "pinned": bool(_SHA_RE.match(version)),
                "source": arch.repo_relative(workflow),
                "remediation": f"pin to a full commit SHA: "
                               f"gh api repos/{ref}/commits/{version} --jq .sha",
            })

    for image in _declared_container_images():
        reference = image["reference"]
        for source in image["sources"]:
            entries.append({
                "kind": "container-image", "name": reference.split(":")[0], "pin": reference,
                "pinned": "@sha256:" in reference,
                "source": source,
                "remediation": f"pin by immutable digest: "
                               f"docker buildx imagetools inspect {reference} --format "
                               f"'{{{{.Manifest.Digest}}}}'",
            })

    lock = REPO_ROOT / "requirements-release.lock"
    try:
        locked = locked_python_requirements()
        lock_error = ""
    except ValueError as exc:
        locked, lock_error = [], str(exc)
    locked_by_name = {_canonical_python_name(name): version for name, version in locked}
    if lock_error:
        entries.append({
            "kind": "python", "name": "(release lock)", "pin": arch.repo_relative(lock),
            "pinned": False, "source": arch.repo_relative(lock), "detail": lock_error,
            "remediation": "regenerate a valid exact-version release lock in a clean venv",
        })
    for name, version in locked:
        entries.append({
            "kind": "python", "name": _canonical_python_name(name), "pin": version,
            "pinned": True, "source": arch.repo_relative(lock),
            "detail": "exact version in the Tier-3 lock; artifact hashes are not pinned",
            "remediation": "regenerate the lock from the selected release profiles",
        })
    for declaration in declared_python_requirements():
        name = declaration["name"]
        in_lock = name in locked_by_name
        entries.append({
            "kind": "python", "name": name,
            "pin": locked_by_name[name] if in_lock else declaration["requirement"],
            "pinned": in_lock, "source": declaration["source"],
            "detail": (f"{declaration['role']} declaration; "
                       + ("resolved by requirements-release.lock"
                          if in_lock else "not covered by requirements-release.lock")),
            "remediation": "select the release feature profiles, resolve them in a clean venv, "
                           "and regenerate requirements-release.lock",
        })

    for lockfile in sorted(REPO_ROOT.glob("generator_trunk/constraints/*/package-lock.json")):
        entries.append({
            "kind": "node", "name": lockfile.parent.name, "pin": arch.repo_relative(lockfile),
            "pinned": True, "source": arch.repo_relative(lockfile.parent / "package.json"),
            "remediation": "npm ci (never npm install) in a release build",
        })

    maven_declarations = _maven_declarations()
    reactor_coordinates = {
        (entry["group"], entry["name"], entry["version"])
        for entry in maven_declarations if entry["role"] == "reactor-module"
    }
    for declaration in maven_declarations:
        if declaration["role"] == "reactor-module":
            continue
        coordinate = f"{declaration['group']}:{declaration['name']}"
        reactor_source = (declaration["group"], declaration["name"],
                          declaration["version"]) in reactor_coordinates
        for source in declaration["sources"]:
            entries.append({
                "kind": "maven", "name": coordinate, "pin": declaration["version"],
                "pinned": reactor_source or _maven_version_is_pinned(declaration["version"]),
                "source": source,
                "detail": ("resolved from the same source reactor revision" if reactor_source
                           else f"{declaration['role']} declaration"),
                "remediation": ("build the pinned source reactor" if reactor_source else
                                "set an exact non-SNAPSHOT version in the declaring POM and "
                                "verify the resolved dependency tree"),
            })

    occurrences = len(entries)
    entries = _dedupe_pin_entries(entries)
    unpinned = [e for e in entries if not e["pinned"]]
    return {
        "entries": entries,
        "counts": {"total": len(entries), "pinned": len(entries) - len(unpinned),
                   "unpinned": len(unpinned), "declaration_occurrences": occurrences},
        "unpinned": unpinned,
        "risk_by_kind": dict(_PIN_KINDS),
        "note": "Resolving a tag to a SHA or digest requires network access, which this generator "
                "deliberately does not perform. Each unpinned entry carries the exact command to "
                "resolve it.",
    }


# ------------------------------------------------------- release manifest ----
def release_manifest(*, skips: "Sequence[str]" = (), test_summary: "Mapping | None" = None,
                     timestamp: "str | None" = None) -> dict:
    """The release manifest. Every field is observed, not asserted."""
    from . import sut_manifests as sm
    matrix = caps.capability_matrix()
    skip_report = classify_skips(skips)
    source = source_revision()
    try:
        sut_inventory = sm.report()
        suts = {"count": len(sut_inventory["manifests"]),
                "ids": [m["id"] for m in sut_inventory["manifests"]],
                "drift": sut_inventory["drift"]}
    except Exception as exc:                                  # noqa: BLE001
        suts = {"error": f"{type(exc).__name__}: {exc}"}
    sbom_components = generate_sbom(timestamp=timestamp)["components"]
    def property_value(component: Mapping, name: str) -> str:
        return next((p["value"] for p in component.get("properties", ())
                     if p.get("name") == name), "")
    third_party = [component for component in sbom_components
                   if property_value(component, "bundle:first_party") != "true"]
    license_inventory = {
        "scope": "licenses declared in locally available metadata for checkout-derived components",
        "components": len(third_party),
        "with_declared_license": sum(bool(c.get("licenses")) for c in third_party),
        "without_declared_license": [
            f"{c.get('group') + ':' if c.get('group') else ''}{c['name']}@{c['version']}"
            for c in third_party if not c.get("licenses")],
        "limitation": "absence here means local declaration metadata was unavailable or empty; "
                      "it is not a finding that the component has no license",
    }
    return {
        "schema": RELEASE_SCHEMA,
        "generated_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "source": source,
        "toolchain": toolchain(),
        "release_inputs": release_inputs(),
        "capability_matrix": {
            "schema": matrix["schema"],
            "counts": matrix["counts"],
            "rules": len(matrix["rules"]),
            "sha256": hashlib.sha256(
                json.dumps(matrix, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "canonical_suts": suts,
        "dependency_pins": dependency_pins(),
        "third_party_licenses": license_inventory,
        "tests": dict(test_summary or {}),
        "skips": skip_report.to_dict(),
        "reproducibility": {
            "release_evidence_eligible": bool(source.get("available") and not source.get("dirty")),
            "eligibility_reason": ("clean Git source identity" if source.get("available") and not source.get("dirty")
                                   else "dirty or Git-less source is inventory-only"),
            "claim": "a clean checkout of the same revision should retain the same declared "
                     "component versions and freshly hashed release inputs",
            "not_claimed": [
                "byte-for-byte identical build artifacts: Maven jars embed zip entry timestamps, "
                "so a rebuild from identical source produces a different artifact sha256",
                "platform-independent resolution: platform-specific Python wheels are not pinned "
                "per platform here",
                "a fully transitive Maven dependency lock/SBOM: the SBOM covers checked-in Maven "
                "declarations, while Python components are bounded by requirements-release.lock",
                "a complete Python feature lock/SBOM: requirements-release.lock covers the Tier-3 "
                "test/science/deploy profile; other declared extras are audited as uncovered",
                "dirty-tree equivalence: a Git commit plus dirty paths does not content-address "
                "arbitrary local edits, so a dirty manifest is inventory-only",
                "source-archive reconstruction: CI starts from Git but does not unpack and rebuild "
                "a separately produced source archive",
            ],
            "timestamp_note": "generated_at records when this document was produced. It is "
                              "metadata about the document, never evidence about the build.",
        },
    }


def validate_release_manifest(data: Mapping) -> None:
    """Structural validation. Raises ValueError on a defect."""
    if data.get("schema") != RELEASE_SCHEMA:
        raise ValueError(f"bad schema {data.get('schema')!r} (want {RELEASE_SCHEMA!r})")
    for key in ("generated_at", "source", "toolchain", "release_inputs", "capability_matrix",
                "canonical_suts", "dependency_pins", "third_party_licenses", "tests", "skips",
                "reproducibility"):
        if key not in data:
            raise ValueError(f"release manifest missing required key {key!r}")
    if not data["release_inputs"]:
        raise ValueError("release manifest records no release inputs")
    if not data["reproducibility"].get("not_claimed"):
        raise ValueError("the reproducibility block must state what is NOT claimed")
    for entry in data["release_inputs"]:
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            raise ValueError(f"release input {entry.get('path')!r} has no valid sha256")

    # --- review item A.2 ---------------------------------------------------
    # A manifest is evidence about a source state. If the recorded eligibility
    # disagrees with the recorded source state, one of them is wrong and the
    # document cannot be trusted either way.
    source = data.get("source") or {}
    reproducibility = data.get("reproducibility") or {}
    eligible = reproducibility.get("release_evidence_eligible")
    if not isinstance(eligible, bool):
        raise ValueError("reproducibility.release_evidence_eligible must be a boolean")
    expected = bool(source.get("available") and not source.get("dirty"))
    if eligible != expected:
        raise ValueError(
            f"release_evidence_eligible={eligible} contradicts the recorded source state "
            f"(git available={source.get('available')}, dirty={source.get('dirty')}); a dirty or "
            f"Git-less tree is inventory-only, never release evidence")

    # A canonical-SUT inventory that failed to build is not a passing inventory.
    suts = data.get("canonical_suts") or {}
    if suts.get("error"):
        raise ValueError(f"canonical SUT inventory failed: {suts['error']}")
    drift = suts.get("drift") or {}
    for name, entries in sorted(drift.items()):
        if entries:
            raise ValueError(
                f"canonical SUT drift in {name!r}: {entries}. A manifest that references a "
                f"missing path or an unwired CI gate describes a gate that does not exist.")


def format_release_report(data: Mapping) -> str:
    source = data["source"]
    lines = [f"release manifest {data['schema']}",
             f"  source: " + (f"{source.get('commit', '')[:12]} ({source.get('branch')})"
                              f"{' DIRTY' if source.get('dirty') else ''}"
                              if source.get("available") else "no Git metadata"),
             f"  engine revision: {source['engine_revision']}",
             f"  toolchain: python {data['toolchain']['python']} | {data['toolchain']['java']}",
             f"  release inputs: {len(data['release_inputs'])} files hashed",
             f"  capability matrix: {data['capability_matrix']['counts']}",
             f"  canonical SUTs: {data['canonical_suts'].get('count', 'n/a')}"]
    skips = data["skips"]
    tests = data.get("tests") or {}
    if tests:
        lines.append(
            "  tests: "
            f"passed={tests.get('passed', 0)} failed={tests.get('failed', 0)} "
            f"errors={tests.get('errors', 0)} skipped={tests.get('skipped', 0)} "
            f"complete={tests.get('complete', False)}")
    if skips["total"]:
        lines.append(f"  skips: {skips['total']} " +
                     ", ".join(f"{k}={v}" for k, v in skips["by_class"].items() if v))
        for entry in skips["blocking"]:
            lines.append(f"      ⛔ {BLOCKING_UNEXPECTED}: {entry['reason']}")
    else:
        lines.append("  skips: none reported")
    pins = data.get("dependency_pins")
    if pins:
        counts = pins["counts"]
        lines.append(f"  dependency pins: {counts['pinned']}/{counts['total']} pinned")
        for entry in pins["unpinned"]:
            lines.append(f"      ! {entry['kind']} {entry['name']} pinned as {entry['pin']!r} "
                         f"({arch.repo_relative(entry['source'])})")
    lines.append("  NOT claimed: " + "; ".join(data["reproducibility"]["not_claimed"][:2]))
    return "\n".join(lines)
