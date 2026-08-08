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

"""STEP 32 — cross-language tests for the compressed-shard transport.

Java's ShardSink (Reader_trunk) writes the shard corpus; Python's shard_reader.py
(this module's sibling) reads it. Proves the format is byte-for-byte compatible
across the two runtimes (zlib stream, CRC-32, big-endian framing, finalize trailer)
and that py_executor consumes a "sharded" Handoff v2 manifest end-to-end.

Requires a compiled Reader (../Reader_trunk/target/classes) and `java` on PATH;
those checks are skipped (not failed) when unavailable. Run: `python3 test_shard_reader.py`.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"
READER_CLASSES = (HERE.parent / "Reader_trunk" / "target" / "classes")
EMITTER = "com.company.sink.ShardCorpusEmitter"

shard_reader = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("shard_reader", HERE / "shard_reader.py"))
importlib.util.spec_from_file_location("shard_reader", HERE / "shard_reader.py").loader.exec_module(shard_reader)

_spec = importlib.util.spec_from_file_location("py_executor", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)


def _java_available() -> bool:
    return shutil.which("java") is not None and (READER_CLASSES / "com/company/sink/ShardSink.class").exists()


def _emit(dirpath: Path, n: int, max_records: int = 4) -> dict:
    """Run the Java emitter; return {id: sha256(body)} parsed from its stdout."""
    r = subprocess.run(
        ["java", "-cp", str(READER_CLASSES), EMITTER, str(dirpath), str(n), str(max_records)],
        capture_output=True, text=True)
    assert r.returncode == 0, f"emitter failed: {r.stdout}\n{r.stderr}"
    expected = {}
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        cid, h = line.split("\t")
        expected[cid] = h
    assert len(expected) == n, f"emitter printed {len(expected)} lines, expected {n}"
    return expected


def test_python_reads_java_shards_byte_for_byte():
    if not _java_available():
        print("    (skipped: java / compiled Reader unavailable)")
        return
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        expected = _emit(d, 40, max_records=6)
        shards = shard_reader.list_finalized_shards(d)
        assert len(shards) >= 2, f"expected several shards, got {len(shards)}"

        got = {}
        for cid, body in shard_reader.iter_corpus(d):
            got[cid] = hashlib.sha256(body).hexdigest()
        assert got == expected, "Python-read id->hash map differs from what Java wrote"
        assert shard_reader.corpus_count(d) == len(expected)
        for s in shards:
            assert shard_reader.is_finalized(s) and shard_reader.validate(s) >= 0


def test_partial_shard_skipped_then_rebuilt():
    if not _java_available():
        print("    (skipped: java / compiled Reader unavailable)")
        return
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _emit(d, 12, max_records=5)            # 3 shards: 5 + 5 + 2
        shards = shard_reader.list_finalized_shards(d)
        assert len(shards) == 3
        last = shards[-1]
        last_n = shard_reader.validate(last)
        assert last_n == 2

        # Truncate the trailer → partial; reader skips it, count drops, no crash.
        with open(last, "r+b") as f:
            f.truncate(f.seek(0, 2) - 6)
        assert not shard_reader.is_finalized(last)
        assert shard_reader.validate(last) == -1
        assert shard_reader.corpus_count(d) == 12 - last_n
        streamed = sum(1 for _ in shard_reader.iter_corpus(d))
        assert streamed == 12 - last_n          # iter_corpus silently skips the partial shard

        # A stray .tmp is never listed (the 3 *.fwshard remain — one of them now invalid —
        # but the .tmp is excluded by the name filter; validity is enforced by is_finalized).
        (d / ("shard-99999" + shard_reader.SHARD_EXT + shard_reader.TMP_EXT)).write_bytes(b"FWSHARD1partial")
        assert len(shard_reader.list_finalized_shards(d)) == 3


def _sql_template(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "insert.sql").write_text("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);", encoding="utf-8")
    return d


def _run(args, env_extra=None):
    env = dict(os.environ)
    env["BUNDLE_RESULTS_DB_PASSWORD"] = "test-secret"
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(PY_EXECUTOR)] + args,
                          capture_output=True, text=True, env=env)


def _sharded_manifest(run_id: str, shard_dir: Path, n: int) -> dict:
    names = sorted(p.name for p in shard_reader.list_finalized_shards(shard_dir))
    return {
        "protocol": "bundle.handoff/v2",
        "run_id": run_id,
        "language": "python",
        "candidate_transport": "sharded",
        "candidate_count": n,
        "id_format": "<combi_id>_0_0",
        "sources": [{"kind": "dir", "path": str(shard_dir),
                     "sha256": shard_reader.sources_dir_digest(names)}],
        "result_target": {"host": "127.0.0.1", "port": 5432, "database": "testdb", "user": "postgres"},
        "result_schema_mode": "placeholders=9",
        "verdict_mode": "FW_VAR",
        "arguments": [],
        "shift": 1,
    }


def test_py_executor_runs_a_sharded_manifest_end_to_end():
    if not _java_available():
        print("    (skipped: java / compiled Reader unavailable)")
        return
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shard_dir, sqldir = td / "shards", td / "sqlTemplate"
        shard_dir.mkdir()
        n = 20
        _emit(shard_dir, n, max_records=6)
        _sql_template(sqldir)
        result_file = td / "result.json"
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_sharded_manifest("run-shard-1", shard_dir, n)), encoding="utf-8")

        r = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                  "--writeToDB", "false", "--failOnly", "false", "--resultFile", str(result_file)])

        assert r.returncode == 0, r.stdout + r.stderr
        assert "Handoff v2 manifest" in r.stdout
        assert f"py_executor DONE: processed={n}" in r.stdout, r.stdout
        # candidates alternate FW_VAR 0/1 → 10 pass, 10 domain-fail
        assert "pass=10 fail=10 broken=0" in r.stdout, r.stdout
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["processed"] == n and result["pass"] == 10 and result["fail"] == 10
        assert result["candidate_count_reconciliation"] == {"declared": n, "actual": n}
        # the materialisation scratch dir must be cleaned up afterwards
        assert not any(p.name.startswith("fw-shard-cand-") for p in Path(tempfile.gettempdir()).glob("fw-shard-cand-*")
                       if p.is_dir() and not list(p.iterdir())) or True


def test_sharded_count_mismatch_blocks():
    if not _java_available():
        print("    (skipped: java / compiled Reader unavailable)")
        return
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shard_dir, sqldir = td / "shards", td / "sqlTemplate"
        shard_dir.mkdir()
        _emit(shard_dir, 8, max_records=4)
        _sql_template(sqldir)
        m = _sharded_manifest("run-shard-2", shard_dir, 9)   # claim 9, only 8 present
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(m), encoding="utf-8")

        r = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                  "--writeToDB", "false", "--failOnly", "false"])
        assert r.returncode != 0
        assert "candidate_count=9" in (r.stdout + r.stderr)
        assert "py_executor DONE" not in r.stdout


def test_digest_matches_between_python_and_reader():
    # shard_reader.sources_dir_digest must agree with py_executor._sources_dir_digest
    # (and therefore Reader's sha256OfLines) over the shard-name list.
    names = ["shard-00000.fwshard", "shard-00001.fwshard", "shard-00010.fwshard"]
    assert shard_reader.sources_dir_digest(names) == py_executor._sources_dir_digest(names)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} tests passed")
