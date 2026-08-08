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

"""Provenance and third-party license inventory (Prompt 04 Part A).

**Non-operative.** This module gathers evidence for a publication decision. It
activates nothing, and it is not legal advice.

The discipline it enforces is one distinction, applied everywhere:

    what the OWNER ATTESTS   ≠   what this repository can DEMONSTRATE

The owner reports approximately 99.9% personal authorship of Core + Reader +
Executor. That is recorded verbatim as an attestation. It is deliberately *not*
converted into a file-by-file finding, because this QA edition intentionally
starts from one curated root snapshot, not the development record. Saying so is
the useful output; a fabricated corroboration would be worse than none.

Third-party licenses are read from the **exact resolved group/artifact/version
POM** and only from Python distributions named by the checked-in release lock.
A dependency whose exact metadata is absent is reported as ``not declared`` or
``metadata unavailable``, never inferred from another installed package.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree import ElementTree as ET

from . import architecture as arch

SCHEMA = "bundle.provenance/v1"
REPO_ROOT = arch.REPO_ROOT

#: The draft licensing direction this inventory is assessed against. It is
#: deliberately non-operative: no root LICENSE file is created by this edition.
PROPOSED_ENGINE_LICENSE = "LicenseRef-Bundle-QA-Personal-Single-Instance-DRAFT"

#: The owner's statement, recorded as an attestation and never as a finding.
OWNER_ATTESTATION = {
    "claim": "approximately 99.9% personal authorship and effort in Core + Reader + Executor",
    "kind": "owner attestation",
    "corroborated_by_git_history": False,
    "why_not": "this QA edition deliberately begins with one curated root snapshot; its Git "
               "history cannot evidence authorship of work done before that snapshot",
    # The development timeline the snapshot cannot show. Recorded because a bare
    # percentage invites the reading that the engine is recent, AI-era work; it
    # is not. Attested by the owner, like the percentage itself.
    "timeline": {
        "conceived": "Q4 2012",
        "first_solid_versions": "2022-2023",
        "ai_assistance_began": "2025",
        "ai_assistance_scope": "layers around the engine — control plane, presentation, reference "
                               "applications, evidence tooling and documentation; not Core, Reader "
                               "or Executor",
    },
    "engine_predates_widespread_llm_services": True,
    "separate_records_provided_by_owner": [],
    "note": "The owner's separate historical provenance records are retained privately outside "
            "this curated QA edition. They are not independently verified here and are not a "
            "substitute for qualified review.",
    "ai_is_not_an_author": "No AI system is an author of this project. An AI assistant that helps "
                           "prepare a change set is not thereby a co-author; authorship remains "
                           "a human legal and factual determination.",
}

# ------------------------------------------------ file provenance categories --
OWNER_ATTESTED_ENGINE = "owner-attested-core-reader-executor"
AI_ASSISTED = "ai-assisted-owner-directed"
MACHINE_GENERATED = "machine-generated-requires-review"
GENERATED_BINDINGS = "generated-protocol-bindings"
THIRD_PARTY_FORK = "third-party-fork"
BINARY_ARTIFACT = "binary-or-media-artifact"
GENERATED_CORPUS = "generated-test-corpus"
UNKNOWN = "unknown-requires-resolution"

#: Legacy branch-name markers retained as a classification hint. A clean QA
#: edition history is not expected to contain these source-development merges.
_AI_BRANCH_MARKERS = ("ai-assist/",)

#: Paths whose provenance is decided by location rather than by commit history.
_PATH_CATEGORIES: "tuple[tuple[str, str, str], ...]" = (
    ("Core_trunk", OWNER_ATTESTED_ENGINE,
     "covered by the owner's Core + Reader + Executor authorship attestation; this is an "
     "attestation scope marker, not independent file-level corroboration"),
    ("Reader_trunk", OWNER_ATTESTED_ENGINE,
     "covered by the owner's Core + Reader + Executor authorship attestation; this is an "
     "attestation scope marker, not independent file-level corroboration"),
    ("Executor_trunk", OWNER_ATTESTED_ENGINE,
     "covered by the owner's Core + Reader + Executor authorship attestation; this is an "
     "attestation scope marker, not independent file-level corroboration"),
    ("generator_trunk/bundle/gateway/generated", GENERATED_BINDINGS,
     "grpcio-tools output from generator_trunk/proto; regenerated by bundle/gateway/codegen.py"),
    ("Combinatoricslib3parallel", THIRD_PARTY_FORK,
     "technical evidence: a fork/modification of upstream com.github.dpaukov:combinatoricslib3 "
     "(upstream declares Apache-2.0 and LGPL-3.0). Its legal classification is NOT decided here; "
     "provenance, upstream notice and licence-election treatment require qualified review"),
    ("generator_trunk/generated_tests", GENERATED_CORPUS,
     "generated candidate corpus committed as source; review whether it belongs in a published tree"),
    ("generator_trunk/generated_tests_fintech", GENERATED_CORPUS,
     "generated candidate corpus committed as source; same review"),
    ("generator_trunk/AI_combi_testing_platform", AI_ASSISTED,
     "introduced by ai-assist/* pull requests #1 and #2 under owner direction"),
)

_BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".xlsx", ".jar", ".class",
                    ".so", ".dll", ".zip", ".gz", ".whl", ".bin", ".onnx", ".pt")


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True,
                              text=True, timeout=120)
        return proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def git_history() -> dict:
    """What the Git history in this checkout can and cannot evidence."""
    log = _git("log", "--format=%H%x1f%an%x1f%ae%x1f%ad%x1f%s", "--date=short")
    if not log.strip():
        return {"available": False,
                "limitation": "no Git metadata in this tree; authorship cannot be evidenced here"}
    commits = []
    for line in log.strip().splitlines():
        parts = line.split("\x1f")
        if len(parts) == 5:
            commits.append({"sha": parts[0][:12], "author": parts[1], "email": parts[2],
                            "date": parts[3], "subject": parts[4]})
    authors = collections.Counter(f"{c['author']} <{c['email']}>" for c in commits)
    dates = sorted(c["date"] for c in commits)
    merges = [line.strip() for line in _git("log", "--merges", "--format=%h %s").splitlines()
              if line.strip()]
    ai_merges = [m for m in merges if any(marker in m for marker in _AI_BRANCH_MARKERS)]
    return {
        "available": True,
        "commit_count": len(commits),
        "first_commit_date": dates[0] if dates else "",
        "last_commit_date": dates[-1] if dates else "",
        "distinct_author_identities": len(authors),
        "authors": [{"identity": k, "commits": v} for k, v in authors.most_common()],
        "merge_commits": merges,
        "ai_assisted_merges": ai_merges,
        "limitation": (
            "This history spans "
            f"{dates[0] if dates else '?'}..{dates[-1] if dates else '?'} across "
            f"{len(commits)} commits. This edition history is a curated source snapshot: it "
            "evidences who committed the snapshot, NOT who authored the engine over its "
            "development lifetime. No "
            "file-by-file authorship finding can be derived from it."),
        "external_contributors": (
            "No contributor other than the two commit identities below appears in this history. "
            "The identities are consistent with the owner's statement that both are theirs, but "
            "this tool observes commit metadata only and cannot independently establish that two "
            "identities belong to the same person. Confirm identity ownership, and confirm that "
            "no unattributed third-party contribution exists, before publication."),
    }


# ------------------------------------------------------- file classification --
def file_provenance() -> dict:
    """Classify every current source file visible to Git.

    Both tracked files and ``--others --exclude-standard`` are included. During
    a prepared handoff the new Phase files are intentionally untracked; omitting
    them made the claimed whole-tree inventory incomplete exactly when it was
    most needed.
    """
    tracked = [line.strip() for line in _git("ls-files").splitlines() if line.strip()]
    untracked = [line.strip() for line in
                 _git("ls-files", "--others", "--exclude-standard").splitlines()
                 if line.strip()]
    tracked_set = set(tracked)
    buckets: "dict[str, list[str]]" = collections.defaultdict(list)
    bucket_status: "dict[str, collections.Counter]" = collections.defaultdict(collections.Counter)
    reasons: "dict[str, str]" = {}
    for path in sorted(tracked_set | set(untracked)):
        category = UNKNOWN
        reasons[UNKNOWN] = (
            "no path rule or independent file-level record establishes provenance; resolve from "
            "owner records/history before publication")
        # Review item C.4: the binary check runs FIRST. A .jar or image inside
        # Core_trunk/ is still a redistribution question, and letting a broad
        # attestation-scope path rule absorb it would hide exactly that.
        if path.endswith(_BINARY_SUFFIXES):
            category = BINARY_ARTIFACT
            reasons[BINARY_ARTIFACT] = ("tracked binary or media; confirm redistribution rights "
                                        "and whether it belongs in a published tree")
        else:
            for prefix, cat, reason in _PATH_CATEGORIES:
                if path == prefix or path.startswith(prefix + "/"):
                    category, reasons[cat] = cat, reason
                    break
        buckets[category].append(path)
        bucket_status[category]["tracked" if path in tracked_set else "untracked"] += 1
    return {
        "files": len(tracked_set | set(untracked)),
        "tracked_files": len(tracked),
        "untracked_files": len(untracked),
        "categories": {
            cat: {"count": len(paths), "reason": reasons.get(cat, ""),
                  "tracked": bucket_status[cat]["tracked"],
                  "untracked": bucket_status[cat]["untracked"],
                  "examples": sorted(paths)[:8]}
            for cat, paths in sorted(buckets.items())
        },
        "caveat": (
            f"{UNKNOWN!r} is the residual bucket and explicitly not a positive finding of "
            "authorship. {OWNER_ATTESTED_ENGINE!r} records the scope of the owner's attestation, "
            "not independent corroboration. Untracked, non-ignored handoff files are included."),
    }


# --------------------------------------------------------- license inventory --
#: Substring -> SPDX-ish family, for compatibility triage against the draft
#: QA-edition licensing direction. Matching is on the text the dependency itself
#: declares; anything unmatched is reported as unrecognized rather than guessed.
_LICENSE_FAMILIES: "tuple[tuple[str, str], ...]" = (
    ("apache", "Apache-2.0"), ("bsd", "BSD"), ("mit", "MIT"),
    ("epl", "EPL"), ("eclipse public", "EPL"),
    ("lesser general public", "LGPL"), ("lgpl", "LGPL"),
    ("gnu library", "LGPL"),
    ("affero", "AGPL"),
    ("general public license", "GPL"),
    ("mozilla", "MPL"), ("cddl", "CDDL"), ("psf", "PSF"), ("python software", "PSF"),
)

#: Families that, combined into a work under the final selected terms, need a
#: qualified opinion. Compatibility is a legal question; this records WHY the entry
#: is flagged, not a conclusion.
# Review item C.5: these entries route a dependency to qualified review. They
# deliberately describe WHAT to examine, never whether the terms conflict —
# combining differently-licensed works is a legal question this tool does not
# answer, and a tool that answered it would be relied on.
_FLAGGED_FAMILIES = {
    "EPL": "Copyleft terms differing from the proposed engine licence. Record the exact licence "
           "and version, whether a dual arm exists and which arm the project would elect, and "
           "obtain a qualified opinion on combining it.",
    "GPL": "Copyleft terms whose scope depends on version and on any linking exception. Record "
           "the exact version and exception text, then obtain a qualified opinion.",
    "CDDL": "Terms from a different copyleft family, sometimes with a classpath exception. Record "
            "the exact terms and whether the published engine actually reaches this dependency, "
            "then obtain a qualified opinion.",
    "MPL": "File-level copyleft with version-dependent secondary-licence provisions. Record the "
           "exact version, then obtain a qualified opinion.",
}


def _families(names: "Sequence[str]") -> "list[str]":
    out = []
    for name in names:
        lowered = name.lower()
        for needle, family in _LICENSE_FAMILIES:
            if needle in lowered:
                if family not in out:
                    out.append(family)
                break
        else:
            if "unrecognized" not in out:
                out.append("unrecognized")
    return out


def _maven_pom_path(coordinate: Mapping[str, object]) -> Path:
    """Exact host metadata path for one non-reactor Maven coordinate."""
    group = str(coordinate["group_id"])
    artifact = str(coordinate["artifact_id"])
    version = str(coordinate["version"])
    return (Path.home() / ".m2" / "repository" / Path(*group.split(".")) / artifact /
            version / f"{artifact}-{version}.pom")


def _readable_xml(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        ET.parse(path)
    except (OSError, ET.ParseError):
        return False
    return True


def maven_licenses() -> dict:
    """Licenses declared by the RESOLVED Maven POMs in the local repository.

    Reads what each dependency declares about itself. A POM with no ``<license>``
    element yields ``not declared``. An absent/unreadable exact POM is different:
    it yields ``metadata unavailable`` and never claims what the artifact says.
    """
    from . import release
    declared_pom = _declared_maven_coordinates()
    entries, flagged, undeclared, unavailable = [], [], [], []
    for coordinate in declared_pom:
        artifact = coordinate["artifact_id"]
        pom_path = _maven_pom_path(coordinate)
        metadata_available = _readable_xml(pom_path)
        names = (release._maven_declared_licenses(
            coordinate["group_id"], artifact, coordinate["version"])
                 if metadata_available else [])
        families = _families(names) if names else []
        entry = {
            "coordinate": f"{coordinate['group_id']}:{artifact}",
            "version": coordinate["version"],
            "declared_licenses": names,
            "families": families,
            "first_party": coordinate["first_party"],
            "role": coordinate["role"],
            "sources": coordinate["sources"],
            "metadata_path": str(pom_path),
            "metadata_available": metadata_available,
        }
        if coordinate["first_party"]:
            entry["status"] = "first-party scope"
            entries.append(entry)
            continue
        if not metadata_available:
            entry["status"] = "metadata unavailable"
            entry["action"] = ("resolve the exact coordinate POM before publication; missing host "
                               "metadata is not evidence that the POM declares no license")
            unavailable.append(entry)
        elif not names:
            entry["status"] = "not declared"
            entry["action"] = ("resolve the license from the upstream project before "
                               "publication; a dependency with no declared license cannot be "
                               "assessed")
            undeclared.append(entry)
        elif len(families) > 1:
            entry["status"] = "dual/multi-licensed"
            entry["action"] = ("record which arm this project elects; a dual license is only "
                               "resolved once the election is written down")
            flagged.append(entry)
        elif families and families[0] in _FLAGGED_FAMILIES:
            entry["status"] = "flagged"
            entry["action"] = _FLAGGED_FAMILIES[families[0]]
            flagged.append(entry)
        else:
            entry["status"] = "declared"
        entries.append(entry)
    third_party_entries = [entry for entry in entries if not entry["first_party"]]
    return {
        "available": True,
        "assessed_against": PROPOSED_ENGINE_LICENSE,
        "evidence_source": "exact resolved third-party POMs under the running user's ~/.m2/repository",
        "metadata_root": str(Path.home() / ".m2" / "repository"),
        "total": len(entries),
        "metadata_expected": len(third_party_entries),
        "exact_metadata": sum(1 for entry in third_party_entries
                              if entry["metadata_available"]),
        "flagged": flagged,
        "undeclared": undeclared,
        "metadata_unavailable": unavailable,
        # Compatibility union. Never describe every member as undeclared.
        "unresolved": undeclared + unavailable,
        "entries": entries,
    }


def _declared_maven_coordinates() -> "list[dict]":
    """Every Maven dependency/plugin/extension declaration in the reactor."""
    from . import release
    # Review item C.2: first-party means "authored here", not "published under a
    # namespace we control". `com.github.ghYura:combinatoricslib3parallel` is a
    # fork of upstream third-party source; treating it as first-party would hide
    # exactly the provenance question that needs review.
    first_party_groups = ("com.yurii", "com.company")
    seen: "dict[str, dict]" = {}
    for declaration in release._maven_declarations():
        if declaration["role"] == "reactor-module":
            continue
        key = (f"{declaration['group']}:{declaration['name']}:"
               f"{declaration['version']}:{declaration['role']}")
        seen.setdefault(key, {
            "group_id": declaration["group"], "artifact_id": declaration["name"],
            "version": declaration["version"], "role": declaration["role"],
            "sources": declaration["sources"],
            "first_party": declaration["group"].startswith(first_party_groups),
        })
    return [seen[k] for k in sorted(seen)]


def python_licenses() -> dict:
    """License metadata for only the checked-in release-lock distributions."""
    from . import release
    entries, undeclared, unavailable = [], [], []
    try:
        from importlib import metadata
        locked = release.locked_python_requirements()
    except Exception as exc:                                  # noqa: BLE001
        return {"available": False, "reason": f"release lock/metadata unavailable: {exc}"}
    for name, version in locked:
        installed_version = "not-installed"
        names: "list[str]" = []
        try:
            dist = metadata.distribution(name)
            installed_version = dist.version or "unknown"
            # Review item C.1: metadata is evidence for the version it came from,
            # and for no other. Reading a locally installed 2.5.1 to describe a
            # locked 2.4.0 borrows a licence statement from a different artifact —
            # which is exactly the kind of "resolved-looking unknown" a reviewer
            # skips. Only an EXACT version match contributes licence names.
            if installed_version == version:
                names = release._declared_license_names(dist.metadata)
        except metadata.PackageNotFoundError:
            pass
        entry = {"name": name, "version": version,
                 "installed_metadata_version": installed_version,
                 "declared_licenses": names, "families": _families(names) if names else []}
        if names:
            entry["status"] = "declared"
            entry["evidence"] = "exact locked-version metadata installed on this host"
        else:
            # Two different facts, and folding them together makes the report lie
            # in one direction or the other. "This artifact declares no license"
            # is a claim about the artifact; "I could not read this artifact" is
            # a claim about THIS HOST. Only the first is a publication blocker
            # about the dependency; the second is missing evidence.
            if installed_version == "not-installed":
                entry["status"] = "metadata unavailable"
                entry["action"] = "install the exact locked version, or record its metadata, to assess it"
                unavailable.append(entry)
            elif installed_version != version:
                entry["status"] = "metadata version mismatch"
                entry["note"] = (f"installed {installed_version} != locked {version}; its metadata "
                                 f"is not evidence for the locked version")
                entry["action"] = "install the exact locked version, or record its metadata, to assess it"
                unavailable.append(entry)
            else:
                entry["status"] = "not declared"
                entry["action"] = "resolve the license of this exact locked version before publication"
                undeclared.append(entry)
        entries.append(entry)
    statuses = collections.Counter(e["status"] for e in entries)
    return {"available": True, "scope": "requirements-release.lock only",
            "assessed_against": PROPOSED_ENGINE_LICENSE,
            # This section is HOST evidence, not a property of the checked-in tree:
            # which distributions can be read depends on the interpreter in use, so
            # the counts below travel with the result and must be quoted with it.
            "evidence_source": "importlib.metadata of the running interpreter",
            "interpreter": sys.executable,
            # "declared" and "not declared" are both exact-version READS — the
            # difference between them is what the artifact says, not whether we
            # could see it. Only absent/mismatch mean the evidence is missing.
            "exact_match": statuses["declared"] + statuses["not declared"],
            "absent": statuses["metadata unavailable"],
            "version_mismatch": statuses["metadata version mismatch"],
            "total": len(entries),
            "undeclared": undeclared,
            "metadata_unavailable": unavailable,
            # kept as the union: "not resolved" stays true for both buckets
            "unresolved": undeclared + unavailable,
            "entries": entries}


def third_party_notices() -> dict:
    """Notice files present in the tree, and the artifacts they cover."""
    notices = [arch.repo_relative(p) for p in sorted(REPO_ROOT.rglob("*NOTICE*"))
               if p.is_file() and "__pycache__" not in str(p) and "/target/" not in str(p)
               and ".venv" not in str(p) and "/.git/" not in str(p)]
    kit = sorted(p.name for p in (REPO_ROOT / "LEGAL_LICENSE_KIT").glob("*.md")) \
        if (REPO_ROOT / "LEGAL_LICENSE_KIT").is_dir() else []
    return {
        "notice_files": notices,
        "legal_license_kit": {
            "present": bool(kit), "documents": kit,
            "note": ("The broad legal-option kit is intentionally omitted from this QA edition. "
                     "No root licence is activated; see docs/qa_edition for the owner's "
                     "non-operative use direction." if not kit else
                     "Owner-drafted licence material is present but remains non-operative."),
        },
        "root_license_present": (REPO_ROOT / "LICENSE").is_file(),
    }


# ------------------------------------------------------------------ report ----
def report() -> dict:
    """The full, regenerable provenance inventory."""
    history = git_history()
    maven = maven_licenses()
    python = python_licenses()
    blockers = []
    files = file_provenance()
    unknown_files = files["categories"].get(UNKNOWN, {}).get("count", 0)
    if unknown_files:
        blockers.append({
            "id": "FILE_PROVENANCE_UNRESOLVED",
            "severity": "high",
            "summary": f"{unknown_files} file(s) remain in the explicit unknown provenance bucket",
            "items": files["categories"][UNKNOWN]["examples"],
        })
    # Review item C.4: a fork and a tracked binary each raise a distinct question
    # that no licence-family check answers. Both must be visible as blockers
    # rather than as a quiet row in a file-category table.
    fork_files = files["categories"].get(THIRD_PARTY_FORK, {})
    if fork_files.get("count"):
        blockers.append({
            "id": "THIRD_PARTY_FORK_REVIEW",
            "severity": "high",
            "summary": f"{fork_files['count']} file(s) are a fork/modification of upstream "
                       f"third-party source; provenance, upstream notice retention and licence "
                       f"treatment require qualified review before publication",
            "items": fork_files.get("examples", []),
        })
    binary_files = files["categories"].get(BINARY_ARTIFACT, {})
    if binary_files.get("count"):
        blockers.append({
            "id": "BINARY_REDISTRIBUTION_REVIEW",
            "severity": "medium",
            "summary": f"{binary_files['count']} tracked binary/media file(s) need a "
                       f"redistribution-rights decision and a publish-or-remove disposition",
            "items": binary_files.get("examples", []),
        })
    corpus_files = files["categories"].get(GENERATED_CORPUS, {})
    if corpus_files.get("count"):
        blockers.append({
            "id": "GENERATED_CORPUS_DISPOSITION",
            "severity": "medium",
            "summary": f"{corpus_files['count']} generated candidate file(s) are committed as "
                       f"source; decide publish-or-remove — reproducible output is not authored "
                       f"material",
            "items": corpus_files.get("examples", []),
        })
    if maven.get("flagged"):
        blockers.append({
            "id": "MAVEN_LICENSE_FLAGGED",
            "severity": "high",
            "summary": f"{len(maven['flagged'])} Maven dependenc(ies) are dual-licensed or in a "
                       f"family that needs a decision or qualified opinion before distribution "
                       f"under {PROPOSED_ENGINE_LICENSE}",
            "items": [e["coordinate"] for e in maven["flagged"]],
        })
    if maven.get("undeclared"):
        blockers.append({
            "id": "MAVEN_LICENSE_UNDECLARED",
            "severity": "high",
            "summary": f"{len(maven['undeclared'])} Maven dependenc(ies) declare no license in "
                       f"their resolved POM and cannot be assessed",
            "items": [e["coordinate"] for e in maven["undeclared"]],
        })
    if maven.get("metadata_unavailable"):
        blockers.append({
            "id": "MAVEN_LICENSE_METADATA_UNAVAILABLE",
            "severity": "high",
            "summary": f"{len(maven['metadata_unavailable'])} exact Maven POM(s) could not be "
                       f"read under {maven['metadata_root']}. This is MISSING EVIDENCE, not a "
                       f"finding that those POMs declare no license",
            "items": [e["coordinate"] for e in maven["metadata_unavailable"]],
        })
    if python.get("undeclared"):
        blockers.append({
            "id": "PYTHON_LICENSE_UNDECLARED",
            "severity": "medium",
            "summary": f"{len(python['undeclared'])} Python distribution(s) declare no license in "
                       f"the metadata of their exact locked version",
            "items": [e["name"] for e in python["undeclared"]],
        })
    if python.get("metadata_unavailable"):
        blockers.append({
            "id": "PYTHON_LICENSE_METADATA_UNAVAILABLE",
            "severity": "medium",
            "summary": f"{len(python['metadata_unavailable'])} locked Python distribution(s) could "
                       f"not be assessed on this host ({python['interpreter']}): the exact locked "
                       f"version is absent or a different version is installed. This is MISSING "
                       f"EVIDENCE, not a finding that the license is absent",
            "items": [e["name"] for e in python["metadata_unavailable"]],
        })
    if history.get("available") and history.get("commit_count", 0) < 100:
        blockers.append({
            "id": "HISTORY_IS_A_SNAPSHOT",
            "severity": "high",
            "summary": "the Git history is a curated source snapshot and cannot corroborate "
                       "authorship of the engine over its development lifetime; the owner's "
                       "attestation stands alone",
            "items": [history["limitation"]],
        })
    if history.get("ai_assisted_merges"):
        blockers.append({
            "id": "AI_ASSISTED_CONTRIBUTION",
            "severity": "medium",
            "summary": "part of the tree was produced with AI assistance under owner direction; "
                       "the terms under which that output may be published must be confirmed",
            "items": history["ai_assisted_merges"],
        })
    return {
        "schema": SCHEMA,
        "status": "DRAFT — non-operative. Evidence for a publication decision; not legal advice.",
        "engine_revision": arch.engine_revision(),
        "proposed_engine_license": PROPOSED_ENGINE_LICENSE,
        "owner_attestation": dict(OWNER_ATTESTATION),
        "git_history": history,
        "file_provenance": files,
        "maven_licenses": maven,
        "python_licenses": python,
        "third_party_notices": third_party_notices(),
        "blockers": blockers,
        "notes": [
            "Attestation and evidence are kept separate throughout. The owner's authorship claim "
            "is recorded as a claim; nothing here converts it into a finding.",
            "A dependency whose POM or metadata declares no license is reported as 'not "
            "declared'. It is never guessed: an unknown that looks resolved is the one a "
            "reviewer skips.",
            "License COMPATIBILITY is a legal question. This inventory flags what needs an "
            "opinion and says why; it does not render one.",
            "Nothing here activates a license, adopts a CLA, or changes repository visibility.",
        ],
    }


def format_report(data: "dict | None" = None) -> str:
    data = data or report()
    history, maven, python = data["git_history"], data["maven_licenses"], data["python_licenses"]
    lines = [f"provenance inventory {data['schema']}  ({data['status'].split('.')[0]})",
             f"  draft licensing direction: {data['proposed_engine_license']} (NOT activated)",
             f"  owner attestation: {data['owner_attestation']['claim']}",
             f"      timeline: conceived {data['owner_attestation']['timeline']['conceived']}, "
             f"first solid versions {data['owner_attestation']['timeline']['first_solid_versions']}, "
             f"AI assistance from {data['owner_attestation']['timeline']['ai_assistance_began']} "
             f"({data['owner_attestation']['timeline']['ai_assistance_scope']})",
             f"      corroborated by Git history: "
             f"{data['owner_attestation']['corroborated_by_git_history']} "
             f"(the snapshot predates nothing it could evidence — this is a limit of the "
             f"snapshot, not a doubt about the timeline)"]
    if history.get("available"):
        lines.append(f"  git: {history['commit_count']} commits "
                     f"{history['first_commit_date']}..{history['last_commit_date']}, "
                     f"{history['distinct_author_identities']} author identit(ies), "
                     f"{len(history['ai_assisted_merges'])} AI-assisted merge(s)")
    files = data["file_provenance"]
    lines.append(f"  files visible to Git: {files['files']} "
                 f"({files['tracked_files']} tracked, {files['untracked_files']} untracked)")
    for category, info in files["categories"].items():
        lines.append(f"      {category:<34} {info['count']:>5}")
    if maven.get("available"):
        lines.append(f"  maven dependencies: {maven['total']} "
                     f"({len(maven['flagged'])} flagged, "
                     f"{len(maven['undeclared'])} undeclared, "
                     f"{len(maven['metadata_unavailable'])} metadata unavailable)")
        lines.append(f"      license evidence read from {maven['evidence_source']}: "
                     f"{maven['metadata_root']} — these counts describe THIS environment, "
                     f"not the repository")
    if python.get("available"):
        lines.append(f"  python distributions: {python['total']} "
                     f"({len(python['undeclared'])} undeclared, "
                     f"{len(python['metadata_unavailable'])} metadata unavailable)")
        lines.append(f"      license evidence read from {python['evidence_source']}: "
                     f"{python['interpreter']}")
        lines.append(f"      exact-version match {python['exact_match']}, absent {python['absent']}, "
                     f"version mismatch {python['version_mismatch']} "
                     f"— these counts describe THIS environment, not the repository")
    lines.append(f"  root LICENSE present: {data['third_party_notices']['root_license_present']}")
    lines.append(f"  blockers: {len(data['blockers'])}")
    for blocker in data["blockers"]:
        lines.append(f"      [{blocker['severity']:<6}] {blocker['id']}: {blocker['summary']}")
    return "\n".join(lines)
