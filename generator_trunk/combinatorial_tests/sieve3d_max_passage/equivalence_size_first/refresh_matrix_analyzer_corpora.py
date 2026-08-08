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

"""Rebuild matrix Analyzer corpora from independently verified pair proofs."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import staged_passage_search as staged


CORPUS_SCHEMA = "sieve3d-matrix-analyzer-corpora/1"
PAIR_PROVENANCE_FIELDS = ("candidate_id", "run_id", "source_ref")


def _atomic_write_text(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _kv_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line.split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    matrix_path = run_dir / "matrix.json"
    if not matrix_path.is_file():
        raise SystemExit(f"missing matrix: {matrix_path}")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = list(matrix.get("rows") or ())
    expected = int(matrix.get("expected_pair_count", -1))
    if len(rows) != expected or not matrix.get(
            "every_requested_pair_exactly_once"):
        raise SystemExit("matrix is not a complete exactly-once pair scope")

    proofs: list[dict] = []
    proof_hashes: dict[str, str] = {}
    for row in rows:
        pair_id = f"{row['body']}--{row['hole']}"
        proof_path = Path(row["proof_path"]).resolve()
        try:
            relative_proof = proof_path.relative_to(run_dir)
        except ValueError as exc:
            raise SystemExit(
                f"proof escapes matrix run directory: {proof_path}") from exc
        if relative_proof.as_posix() != f"pairs/{pair_id}/proof.json":
            raise SystemExit(f"non-canonical proof path for {pair_id}")
        if not proof_path.is_file():
            raise SystemExit(f"missing proof for {pair_id}: {proof_path}")
        proof_sha256 = staged._sha256_file(proof_path)
        if proof_sha256 != row.get("proof_sha256"):
            raise SystemExit(f"matrix proof hash mismatch for {pair_id}")

        certificate = staged.verify_pair_proof(proof_path, check_files=True)
        if not certificate.get("verdict"):
            raise SystemExit(
                f"independent proof verification failed for {pair_id}: "
                f"{certificate.get('errors')}")
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        if proof.get("pair_id") != pair_id:
            raise SystemExit(f"proof pair mismatch for {pair_id}")
        if proof.get("run_id") != matrix.get("run_id"):
            raise SystemExit(f"proof run mismatch for {pair_id}")
        if (proof.get("body"), proof.get("hole")) != (
                row["body"], row["hole"]):
            raise SystemExit(f"proof geometry mismatch for {pair_id}")

        corpus_proof = copy.deepcopy(proof)
        corpus_proof["proof_path"] = relative_proof.as_posix()
        corpus_proof["proof_sha256"] = proof_sha256
        proofs.append(corpus_proof)
        proof_hashes[pair_id] = proof_sha256

    attempts_lines = [
        staged._attempt_kv_line(matrix["run_id"], attempt)
        for proof in proofs for attempt in proof["attempts"]
    ]
    pair_lines = [staged.pair_kv_line(proof) for proof in proofs]

    if len(pair_lines) != expected:
        raise SystemExit("pair corpus cardinality mismatch")
    seen_pairs: set[str] = set()
    for proof, line in zip(proofs, pair_lines, strict=True):
        fields = _kv_fields(line)
        missing = set(PAIR_PROVENANCE_FIELDS) - set(fields)
        if missing:
            raise SystemExit(
                f"missing pair provenance fields for {proof['pair_id']}: "
                f"{sorted(missing)}")
        expected_candidate = (proof.get("selected_candidate_id") or
                              f"{proof['pair_id']}--declared-exhaustion")
        expected_source = staged._safe(proof["proof_path"])
        if fields["candidate_id"] != staged._safe(expected_candidate):
            raise SystemExit(
                f"candidate provenance mismatch for {proof['pair_id']}")
        if fields["run_id"] != staged._safe(matrix["run_id"]):
            raise SystemExit(f"run provenance mismatch for {proof['pair_id']}")
        if fields["source_ref"] != expected_source:
            raise SystemExit(
                f"source provenance mismatch for {proof['pair_id']}")
        if fields.get("pair_id") in seen_pairs:
            raise SystemExit(f"duplicate pair corpus row: {fields['pair_id']}")
        seen_pairs.add(fields["pair_id"])

    for line in attempts_lines:
        fields = _kv_fields(line)
        if not fields.get("candidate_id") or not fields.get("run_id"):
            raise SystemExit("attempt corpus row lacks candidate/run provenance")
        if fields["run_id"] != staged._safe(matrix["run_id"]):
            raise SystemExit("attempt corpus run provenance mismatch")

    attempts_path = run_dir / "attempts.kv"
    pairs_path = run_dir / "pair_results.kv"
    _atomic_write_text(attempts_path, "\n".join(attempts_lines) + "\n")
    _atomic_write_text(pairs_path, "\n".join(pair_lines) + "\n")
    attempts_sha256 = staged._sha256_file(attempts_path)
    pairs_sha256 = staged._sha256_file(pairs_path)

    matrix["attempts_kv_path"] = str(attempts_path)
    matrix["attempts_kv_sha256"] = attempts_sha256
    matrix["pair_results_kv_path"] = str(pairs_path)
    matrix["pair_results_kv_sha256"] = pairs_sha256
    matrix["analyzer_corpora"] = {
        "schema_version": CORPUS_SCHEMA,
        "generated_from_verified_pair_proofs": True,
        "verified_pair_count": len(proofs),
        "attempt_record_count": len(attempts_lines),
        "pair_record_count": len(pair_lines),
        "pair_provenance_fields": list(PAIR_PROVENANCE_FIELDS),
        "canonical_relative_source_refs": True,
        "all_pair_provenance_explicit": True,
    }
    staged._write_json(matrix_path, matrix)

    manifest = {
        "schema_version": CORPUS_SCHEMA,
        "run_id": matrix["run_id"],
        "matrix_path": str(matrix_path),
        "matrix_sha256": staged._sha256_file(matrix_path),
        "attempts_kv_path": str(attempts_path),
        "attempts_kv_sha256": attempts_sha256,
        "attempt_record_count": len(attempts_lines),
        "pair_results_kv_path": str(pairs_path),
        "pair_results_kv_sha256": pairs_sha256,
        "pair_record_count": len(pair_lines),
        "verified_pair_count": len(proofs),
        "pair_provenance_fields": list(PAIR_PROVENANCE_FIELDS),
        "canonical_relative_source_refs": True,
        "all_pair_provenance_explicit": True,
        "proof_sha256_by_pair": proof_hashes,
    }
    manifest_path = run_dir / "analyzer_corpora_manifest.json"
    staged._write_json(manifest_path, manifest)
    print(json.dumps({
        "verdict": True,
        "manifest": str(manifest_path),
        "attempt_records": len(attempts_lines),
        "pair_records": len(pair_lines),
        "attempts_kv_sha256": attempts_sha256,
        "pair_results_kv_sha256": pairs_sha256,
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
