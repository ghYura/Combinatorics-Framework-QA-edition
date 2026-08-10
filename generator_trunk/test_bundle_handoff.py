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

"""Targeted tests for bundle.handoff (STEP 16): round-trip, legacy adapter,
real JSON-Schema validation against bundle-handoff-v2.schema.json,
schema/count/path/custom-verdict rejection, and password redaction
(run: `python3 test_bundle_handoff.py`)."""
import dataclasses
import json
from pathlib import Path

from bundle.handoff import (
    CandidateTransport,
    CustomVerdictEntry,
    HANDOFF_SCHEMA,
    HandoffError,
    HandoffV2,
    Language,
    ResultTargetRef,
    SchemaError,
    SourceLocation,
    VerdictMode,
    handoff_from_dict,
    handoff_from_legacy,
    handoff_to_dict,
    validate_against_json_schema,
    validate_handoff,
)
from bundle.jsonio import redact, REDACTED

SCHEMA_PATH = Path(__file__).resolve().parent / "bundle-handoff-v2.schema.json"
SCHEMA_DOC = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _sample_handoff() -> HandoffV2:
    return HandoffV2(
        schema=HANDOFF_SCHEMA,
        run_id="secure_pipeline-20260607-abcd",
        language=Language.PYTHON,
        candidate_transport=CandidateTransport.LOOSE_FILES,
        candidate_count=288,
        id_format="<combi_id>_0_0",
        sources=(SourceLocation(kind="dir", path="/scratch/secure_pipeline/candidates"),),
        result_target=ResultTargetRef(host="127.0.0.1", port=5433, database="secure_pipeline", user="fw"),
        result_schema_mode="placeholders=9",
        verdict_mode=VerdictMode.FW_VAR,
        arguments=("noargs",),
        shift=1,
    )


def _replace(obj, **changes):
    return dataclasses.replace(obj, **changes)


# ------------------------------- round-trip / version ------------------------- #
def test_handoff_round_trips_through_json():
    original = _sample_handoff()
    blob = json.dumps(handoff_to_dict(original))
    restored = handoff_from_dict(json.loads(blob))
    assert restored == original


def test_unknown_protocol_version_rejected():
    bad = dict(handoff_to_dict(_sample_handoff()))
    bad["protocol"] = "bundle.handoff/v99"
    try:
        handoff_from_dict(bad)
    except SchemaError:
        pass
    else:
        raise AssertionError("expected SchemaError for unknown major protocol version")


# ------------------------- real JSON Schema validation ------------------------ #
def test_sample_document_satisfies_json_schema():
    validate_against_json_schema(handoff_to_dict(_sample_handoff()), SCHEMA_DOC)


def test_json_schema_rejects_negative_count():
    doc = dict(handoff_to_dict(_sample_handoff()))
    doc["candidate_count"] = -1
    try:
        validate_against_json_schema(doc, SCHEMA_DOC)
    except HandoffError as e:
        assert "minimum" in str(e)
    else:
        raise AssertionError("schema should reject candidate_count below its minimum")


def test_json_schema_rejects_unknown_transport_and_extra_property():
    doc = dict(handoff_to_dict(_sample_handoff()))
    doc["candidate_transport"] = "carrier-pigeon"
    try:
        validate_against_json_schema(doc, SCHEMA_DOC)
    except HandoffError as e:
        assert "enum" in str(e)
    else:
        raise AssertionError("schema should reject a transport outside its enum")

    doc2 = dict(handoff_to_dict(_sample_handoff()))
    doc2["unexpected_field"] = "nope"
    try:
        validate_against_json_schema(doc2, SCHEMA_DOC)
    except HandoffError as e:
        assert "unexpected property" in str(e)
    else:
        raise AssertionError("schema is additionalProperties:false; extra keys must be rejected")


def test_json_schema_requires_custom_verdicts_when_mode_is_custom():
    doc = dict(handoff_to_dict(_sample_handoff()))
    doc["verdict_mode"] = "FW_CUSTOM_VAR"
    try:
        validate_against_json_schema(doc, SCHEMA_DOC)
    except HandoffError as e:
        assert "custom_verdicts" in str(e)
    else:
        raise AssertionError("schema's if/then must require non-empty custom_verdicts in custom mode")

    doc["custom_verdicts"] = [{"code": 2, "message": "generic"}]
    validate_against_json_schema(doc, SCHEMA_DOC)  # now satisfied — should not raise

    # FW_VAR mode (the original sample) carries no custom_verdicts and must pass.
    validate_against_json_schema(handoff_to_dict(_sample_handoff()), SCHEMA_DOC)


def test_json_schema_rejects_a_password_shaped_result_target():
    doc = dict(handoff_to_dict(_sample_handoff()))
    doc["result_target"] = dict(doc["result_target"], password="hunter2")
    try:
        validate_against_json_schema(doc, SCHEMA_DOC)
    except HandoffError as e:
        assert "unexpected property" in str(e)
    else:
        raise AssertionError("result_target_ref schema must reject a password field outright")


# --------------------------- dataclass-side validation ------------------------- #
def test_handoff_from_dict_rejects_invalid_count_and_path_at_the_boundary():
    base = dict(handoff_to_dict(_sample_handoff()))

    bad_count = dict(base, candidate_count=-1)
    try:
        handoff_from_dict(bad_count)
    except HandoffError:
        pass
    else:
        raise AssertionError("handoff_from_dict must reject negative candidate_count, not just validate_handoff")

    bad_path = dict(base, sources=[{"kind": "dir", "path": "   "}])
    try:
        handoff_from_dict(bad_path)
    except HandoffError:
        pass
    else:
        raise AssertionError("handoff_from_dict must reject an empty source path, not just validate_handoff")


def test_validate_handoff_rejects_negative_count_and_empty_path_directly():
    try:
        validate_handoff(_replace(_sample_handoff(), candidate_count=-1))
    except HandoffError:
        pass
    else:
        raise AssertionError("expected HandoffError for negative candidate_count")

    try:
        validate_handoff(_replace(_sample_handoff(), sources=(SourceLocation(kind="dir", path="  "),)))
    except HandoffError:
        pass
    else:
        raise AssertionError("expected HandoffError for empty source path")


def test_validate_requires_custom_verdicts_in_custom_mode():
    custom = _replace(_sample_handoff(), verdict_mode=VerdictMode.FW_CUSTOM_VAR)
    try:
        validate_handoff(custom)
    except HandoffError:
        pass
    else:
        raise AssertionError("expected HandoffError when FW_CUSTOM_VAR mode lacks custom_verdicts")
    validate_handoff(_replace(
        custom, custom_verdicts=(CustomVerdictEntry(code=2, message="generic"),)
    ))  # should not raise


# -------------------------------- legacy adapter ------------------------------ #
def test_legacy_adapter_maps_handshake_to_v2_and_auto_validates():
    h = handoff_from_legacy(
        run_id="secure_pipeline-20260607-abcd",
        language="python",
        candidate_count=288,
        id_format="<combi_id>_0_0",
        source_dir="/scratch/secure_pipeline/candidates",
        legacy_results_db_url="jdbc:postgresql://127.0.0.1:5433/secure_pipeline?user=fw&password=hunter2",
        legacy_insert_sql="INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);",
        legacy_args_text=" --flag value ",
        legacy_shift_text="",
        legacy_runme_path="/scratch/secure_pipeline/runFirstOnce/runmefirstonce.first",
    )
    assert h.result_target == ResultTargetRef(host="127.0.0.1", port=5433, database="secure_pipeline", user="fw")
    assert h.result_schema_mode == "placeholders=9"
    assert h.verdict_mode is VerdictMode.FW_VAR
    assert h.arguments == ("--flag", "value")
    assert h.shift == 1, "fwVar.shift must never be empty (P6): blank legacy text -> default 1"
    assert h.preprocess == "/scratch/secure_pipeline/runFirstOnce/runmefirstonce.first"
    validate_against_json_schema(handoff_to_dict(h), SCHEMA_DOC)
    # No password anywhere on the model — it is a *reference*, not a credential.
    assert "password" not in json.dumps(handoff_to_dict(h))
    assert "hunter2" not in json.dumps(handoff_to_dict(h))


def test_legacy_adapter_selects_custom_verdict_mode_on_six_placeholders():
    common = dict(
        run_id="r", language="java", candidate_count=1, id_format="<combi_id>_0_0",
        source_dir="/scratch/r/candidates",
        legacy_results_db_url="jdbc:postgresql://h:5432/db",
        legacy_insert_sql="INSERT INTO results VALUES (?,?,?,?,?,?);",
    )
    # The legacy handshake itself carries no FW_CUSTOM_VAR code/message map (it
    # lives in the spec's custom_vars) — validate_handoff rejects custom mode
    # without one, same as it would reject a hand-built v2 document.
    try:
        handoff_from_legacy(**common)
    except HandoffError as e:
        assert "custom_verdicts" in str(e)
    else:
        raise AssertionError("custom mode (6 placeholders) without a supplied custom_verdicts map must be rejected")

    h = handoff_from_legacy(**common, custom_verdicts=(CustomVerdictEntry(code=2, message="generic"),))
    assert h.verdict_mode is VerdictMode.FW_CUSTOM_VAR
    assert h.result_schema_mode == "placeholders=6"
    assert h.custom_verdicts == (CustomVerdictEntry(code=2, message="generic"),)
    validate_against_json_schema(handoff_to_dict(h), SCHEMA_DOC)


def test_legacy_adapter_rejects_invalid_count():
    try:
        handoff_from_legacy(
            run_id="r", language="python", candidate_count=-5, id_format="<combi_id>_0_0",
            source_dir="/scratch/r/candidates",
            legacy_results_db_url="jdbc:postgresql://h:5432/db",
            legacy_insert_sql="INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);",
        )
    except HandoffError:
        pass
    else:
        raise AssertionError("handoff_from_legacy must reject a negative candidate_count")


def test_legacy_adapter_rejects_blank_source_dir():
    try:
        handoff_from_legacy(
            run_id="r", language="python", candidate_count=1, id_format="<combi_id>_0_0",
            source_dir="   ",
            legacy_results_db_url="jdbc:postgresql://h:5432/db",
            legacy_insert_sql="INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);",
        )
    except HandoffError:
        pass
    else:
        raise AssertionError("handoff_from_legacy must reject a blank source_dir path")


def test_redaction_covers_handoff_dict_shape():
    # Defence in depth: even if a future caller smuggled a password-shaped key
    # into settings/extra fields, write_json_atomic's redact() must catch it.
    shaped = {"result_target": {"host": "h", "password": "hunter2"}}
    assert redact(shaped)["result_target"]["password"] == REDACTED


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} tests passed")
