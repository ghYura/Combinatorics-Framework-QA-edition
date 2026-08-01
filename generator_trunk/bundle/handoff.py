"""Reader -> Executor handoff v2 model (STEP 16): formalizes the contract
documented in bundle-handoff-v2.schema.json before any component changes.

Today's Reader/Executor still speak the legacy file-watch handshake
(resultsDbURL.properties/insert.sql/arguments/fwVar.shift/runmefirstonce.first
— see Reader's HandshakeWriter and Executor_trunk/py_executor.read_handshake).
``handoff_from_legacy`` converts that legacy artifact content into this same
v2 model so later steps can migrate Reader/Executor onto it incrementally
without changing what either side does *in this step*.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .models import SchemaError, require_schema, to_dict

HANDOFF_SCHEMA = "bundle.handoff/v2"


class Language(str, Enum):
    PYTHON = "python"
    JAVA = "java"


class CandidateTransport(str, Enum):
    LOOSE_FILES = "loose-files"
    SHARDED = "sharded"
    # gRPC live transport (2026-07-03): candidates are streamed to the Executor's
    # -grpcPort ingestion server during the Reader stage; the manifest's single
    # source names the endpoint (kind="grpc", path="grpc://host:port") and there
    # is no on-disk candidate corpus to re-verify — delivery was reconciled
    # in-stream (the Reader fail-closes on an Executor receipt mismatch).
    GRPC = "grpc"


class VerdictMode(str, Enum):
    FW_VAR = "FW_VAR"
    FW_CUSTOM_VAR = "FW_CUSTOM_VAR"


class HandoffError(ValueError):
    """Raised when a handoff document fails validation (bad count/path/version/...)."""


# ---------------------------------- value types ------------------------------ #
@dataclass(frozen=True)
class SourceLocation:
    kind: str
    path: str
    sha256: "str | None" = None


@dataclass(frozen=True)
class ResultTargetRef:
    """Results-DB connection coordinates. NEVER carries a password (plan item 3)
    — credentials are resolved at runtime from BundleConfig/environment, mirroring
    the legacy resultsDbURL.properties jdbc URL with its password stripped."""

    host: str
    port: int
    database: str
    user: "str | None" = None


@dataclass(frozen=True)
class CustomVerdictEntry:
    code: int
    message: str


@dataclass(frozen=True)
class HandoffV2:
    schema: str
    run_id: str
    language: Language
    candidate_transport: CandidateTransport
    candidate_count: int
    id_format: str
    sources: Sequence[SourceLocation]
    result_target: ResultTargetRef
    result_schema_mode: str
    verdict_mode: VerdictMode
    custom_verdicts: Sequence[CustomVerdictEntry] = field(default_factory=tuple)
    arguments: Sequence[str] = field(default_factory=tuple)
    shift: int = 1
    preprocess: "str | None" = None
    execution_policy_ref: "str | None" = None


# ----------------------------------- validation ------------------------------ #
def validate_handoff(handoff: HandoffV2) -> None:
    """Reject structurally-invalid handoffs: bad version, count, or paths.

    Raises :class:`HandoffError`; never mutates *handoff*. Called by both
    :func:`handoff_from_dict` and :func:`handoff_from_legacy` — there is no
    path that produces an unvalidated :class:`HandoffV2` from external input.
    """
    require_schema(handoff.schema, HANDOFF_SCHEMA)
    if handoff.candidate_count < 0:
        raise HandoffError(f"candidate_count must be >= 0, got {handoff.candidate_count}")
    if not handoff.id_format or not handoff.id_format.strip():
        raise HandoffError("id_format must not be empty")
    if not handoff.sources:
        raise HandoffError("handoff must declare at least one source location")
    for src in handoff.sources:
        if not src.path or not src.path.strip():
            raise HandoffError(f"source location has an empty path (kind={src.kind!r})")
    if not handoff.result_target.host or not handoff.result_target.host.strip():
        raise HandoffError("result_target.host must not be empty")
    if not (1 <= handoff.result_target.port <= 65535):
        raise HandoffError(f"result_target.port out of range: {handoff.result_target.port}")
    if not handoff.result_target.database or not handoff.result_target.database.strip():
        raise HandoffError("result_target.database must not be empty")
    if handoff.verdict_mode is VerdictMode.FW_CUSTOM_VAR and not handoff.custom_verdicts:
        raise HandoffError("FW_CUSTOM_VAR mode requires a non-empty custom_verdicts map")
    if handoff.shift is None:
        raise HandoffError("shift must never be empty (P6: legacy never-empty fwVar.shift gotcha)")


# ------------------------------- JSON (de)serialization ---------------------- #
def handoff_from_dict(data: Mapping[str, Any]) -> HandoffV2:
    """Parse + validate. Never returns a :class:`HandoffV2` that
    :func:`validate_handoff` would reject — invalid count/path/version raise
    here, at the boundary, rather than being silently accepted."""
    schema = require_schema(data.get("protocol", ""), HANDOFF_SCHEMA)
    handoff = HandoffV2(
        schema=schema,
        run_id=data["run_id"],
        language=Language(data["language"]),
        candidate_transport=CandidateTransport(data["candidate_transport"]),
        candidate_count=data["candidate_count"],
        id_format=data["id_format"],
        sources=tuple(SourceLocation(**s) for s in data.get("sources", ())),
        result_target=ResultTargetRef(**data["result_target"]),
        result_schema_mode=data["result_schema_mode"],
        verdict_mode=VerdictMode(data["verdict_mode"]),
        custom_verdicts=tuple(CustomVerdictEntry(**c) for c in data.get("custom_verdicts", ())),
        arguments=tuple(data.get("arguments", ())),
        shift=data.get("shift", 1),
        preprocess=data.get("preprocess"),
        execution_policy_ref=data.get("execution_policy_ref"),
    )
    validate_handoff(handoff)
    return handoff


def handoff_to_dict(handoff: HandoffV2) -> Mapping[str, Any]:
    """Like ``to_dict`` but emits the wire key ``protocol`` for ``schema``
    (the schema document and Reader/Executor speak ``protocol``; the Python
    side keeps the field named ``schema`` for consistency with bundle.models)."""
    out = dict(to_dict(handoff))
    out["protocol"] = out.pop("schema")
    return out


# ------------------------------- JSON Schema check ---------------------------- #
# Minimal recursive validator for the (small, hand-known) subset of JSON Schema
# 2020-12 that this project's schema documents actually use — `jsonschema` is not
# a dependency. Originally for bundle-handoff-v2.schema.json; also drives
# bundle-spec-v1.schema.json (STEP 36 added pattern/not/oneOf/maxItems for the
# alias field + alias|verb mutual-exclusion). Validates a *plain dict* (e.g.
# handoff_to_dict output, or any external document) directly against the schema
# document on disk, independently of HandoffV2/validate_handoff, so the schema
# file itself is exercised rather than just the dataclass-side checks.
_JSON_TYPES = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "array": list, "object": dict, "null": type(None),
}


def _resolve_ref(ref: str, root: Mapping[str, Any]) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise HandoffError(f"unsupported $ref: {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _check_type(instance: Any, type_decl: Any, path: str) -> None:
    types = type_decl if isinstance(type_decl, list) else [type_decl]
    for t in types:
        py_t = _JSON_TYPES[t]
        if t == "integer":
            if isinstance(instance, bool) or not isinstance(instance, int):
                continue
        elif not isinstance(instance, py_t):
            continue
        return
    raise HandoffError(f"{path}: expected type {type_decl!r}, got {type(instance).__name__}")


def _validate_node(instance: Any, schema: Mapping[str, Any], root: Mapping[str, Any], path: str) -> None:
    if "$ref" in schema:
        _validate_node(instance, _resolve_ref(schema["$ref"], root), root, path)
        return
    if "const" in schema and instance != schema["const"]:
        raise HandoffError(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise HandoffError(f"{path}: {instance!r} not in enum {schema['enum']!r}")
    if "type" in schema:
        _check_type(instance, schema["type"], path)
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise HandoffError(f"{path}: string shorter than minLength={schema['minLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise HandoffError(f"{path}: {instance!r} does not match pattern {schema['pattern']!r}")
    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise HandoffError(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            raise HandoffError(f"{path}: {instance} > maximum {schema['maximum']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise HandoffError(f"{path}: array shorter than minItems={schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise HandoffError(f"{path}: array longer than maxItems={schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(instance):
                _validate_node(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        for key in schema.get("required", ()):
            if key not in instance:
                raise HandoffError(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                _validate_node(value, props[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise HandoffError(f"{path}: unexpected property {key!r}")
    for sub in schema.get("allOf", ()):
        _validate_node(instance, sub, root, path)
    if "oneOf" in schema:
        matched = 0
        for sub in schema["oneOf"]:
            try:
                _validate_node(instance, sub, root, path)
            except HandoffError:
                continue
            matched += 1
        if matched != 1:
            raise HandoffError(f"{path}: matched {matched} of oneOf branches, expected exactly 1")
    if "not" in schema:
        try:
            _validate_node(instance, schema["not"], root, path)
        except HandoffError:
            pass                               # good: instance does NOT match the forbidden schema
        else:
            raise HandoffError(f"{path}: must NOT match schema {schema['not']!r}")
    if "if" in schema:
        try:
            _validate_node(instance, schema["if"], root, path)
        except HandoffError:
            if "else" in schema:
                _validate_node(instance, schema["else"], root, path)
        else:
            if "then" in schema:
                _validate_node(instance, schema["then"], root, path)


def validate_against_json_schema(data: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Validate *data* against a JSON Schema document, raising
    :class:`HandoffError` on the first violation found (path prefixed `$`)."""
    _validate_node(data, schema, schema, "$")


# ------------------------------- legacy adapter ------------------------------ #
# Mirrors Executor_trunk/py_executor.parse_jdbc, but drops the credentials —
# a v2 ResultTargetRef is a *reference*, never a place passwords may live.
_JDBC_RE = re.compile(r"jdbc:postgresql://([^:/]+):(\d+)/([^?]+)(\?(.*))?")


def _legacy_target_from_jdbc_url(url: str) -> ResultTargetRef:
    m = _JDBC_RE.search(url.strip())
    if not m:
        raise HandoffError(f"cannot parse legacy resultsDbURL.properties JDBC URL: {url!r}")
    host, port, db, _, qs = m.groups()
    params = dict(kv.split("=", 1) for kv in (qs or "").split("&") if "=" in kv)
    return ResultTargetRef(host=host, port=int(port), database=db, user=params.get("user"))


def handoff_from_legacy(
    *,
    run_id: str,
    language: "Language | str",
    candidate_count: int,
    id_format: str,
    source_dir: str,
    legacy_results_db_url: str,
    legacy_insert_sql: str,
    legacy_args_text: str = "",
    legacy_shift_text: str = "",
    legacy_runme_path: "str | None" = None,
    execution_policy_ref: "str | None" = None,
    custom_verdicts: Sequence[CustomVerdictEntry] = (),
) -> HandoffV2:
    """Build a :class:`HandoffV2` from the *content* of the five legacy
    handshake artifacts (STEP 16 action 4 mapping):

    =====================================  =================================
    legacy artifact                        v2 field
    =====================================  =================================
    resultsDbURL.properties (jdbc URL)     result_target (password dropped)
    insert.sql ('?' count -> mode)         result_schema_mode, verdict_mode
    arguments/args                         arguments
    arguments/fwVar.shift                  shift (never empty; default "1")
    runFirstOnce/runmefirstonce.first      preprocess
    =====================================  =================================

    The legacy handshake carries no FW_CUSTOM_VAR code/message map (that lives
    in the spec's ``custom_vars``, outside this handshake) — pass it via
    *custom_verdicts* when ``insert.sql`` selects custom mode (6 placeholders);
    :func:`validate_handoff` (run on the result) rejects custom mode with an
    empty map, same as it would for a hand-built v2 document.

    Pure mapping — does not read files itself, so it has no opinion on where
    the legacy artifacts live; callers (e.g. a future Reader/Executor adapter
    in STEP 17-18) supply the already-read text. Reader/Executor behaviour is
    unchanged by this step: nothing here is wired into either component yet.
    """
    insert_sql = legacy_insert_sql.strip().rstrip(";")
    n_q = insert_sql.count("?")
    custom_mode = (n_q == 6)

    argv = legacy_args_text.strip().split() if legacy_args_text.strip() else []
    shift_text = legacy_shift_text.strip()
    shift = int(shift_text) if shift_text else 1  # P6: never-empty default

    handoff = HandoffV2(
        schema=HANDOFF_SCHEMA,
        run_id=run_id,
        language=Language(language),
        candidate_transport=CandidateTransport.LOOSE_FILES,
        candidate_count=candidate_count,
        id_format=id_format,
        sources=(SourceLocation(kind="dir", path=source_dir),),
        result_target=_legacy_target_from_jdbc_url(legacy_results_db_url),
        result_schema_mode=f"placeholders={n_q}",
        verdict_mode=VerdictMode.FW_CUSTOM_VAR if custom_mode else VerdictMode.FW_VAR,
        custom_verdicts=tuple(custom_verdicts),
        arguments=tuple(argv),
        shift=shift,
        preprocess=legacy_runme_path,
        execution_policy_ref=execution_policy_ref,
    )
    validate_handoff(handoff)
    return handoff
