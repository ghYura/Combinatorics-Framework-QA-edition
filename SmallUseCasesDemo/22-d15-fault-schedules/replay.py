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


"""Replay complete D15 candidates exactly as rendered; compare their semantic records and digests with the campaign's.

    python replay.py --run evidence/<run-id> --case '<id>'   # one witness
    python replay.py --run evidence/<run-id> --witnesses      # the five named witnesses (witnesses.json)

The candidate comes from the run's candidates.tar.gz, byte for byte, and runs through the Framework's own
Executor sandbox under generated-default (container, network none, read-only root, tmpfs scratch,
python:3-slim, the Executor's runner shape), exactly like the campaign. It starts three fresh worker
processes and injects the same faults. Replays are additional attempts, recorded under
evidence/<run-id>/replays/. The semantic record (factors, attempts, every snapshot, acknowledged ops, checks,
verdict), its semantic_sha256 and the final WAL evidence must be identical; live PIDs and paths are new.
"""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preflight  # noqa: E402  (the same sandbox helper the preflight used; not the verifier)

LIVE = ("framework", "provenance")


def replay(box, run: Path, case: str, tmp: Path):
    records = {json.loads(l)["id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rec = records[case]
    name = rec["framework"]["source_ref"]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress((run / "candidates.tar.gz").read_bytes()))) as tar:
        data = tar.extractfile(f"src/{name}").read()
    if hashlib.sha256(data).hexdigest() != rec["framework"]["source_sha256"]:
        raise SystemExit(f"{name}: archive bytes differ from the executed candidate's hash")
    r = preflight.run(box, data.decode("utf-8"), tmp, name)
    replayed = r["record"]
    campaign = {k: v for k, v in rec.items() if k not in LIVE}
    same = replayed is not None and {k: v for k, v in replayed.items() if k not in LIVE} == campaign
    return {"case_id": case, "candidate": name, "candidate_sha256": rec["framework"]["source_sha256"], "exit_code": r["exit_code"],
            "timed_out": r["timed_out"], "spawn_error": r["spawn_error"], "stderr_tail": r["stderr_tail"],
            "campaign_outcome": rec["framework"]["outcome"], "replayed_verdict": replayed and replayed["verdict"],
            "record_identical_except_live_provenance": same,
            "campaign_semantic_sha256": rec["semantic_sha256"], "replayed_semantic_sha256": replayed and replayed["semantic_sha256"],
            "digest_identical": replayed is not None and replayed["semantic_sha256"] == rec["semantic_sha256"],
            "wal_evidence_identical": replayed is not None and replayed["wal_evidence"] == rec["wal_evidence"],
            "fresh_pids": {"campaign": [e["pid"] for e in rec["provenance"]["events"] if e["event"] == "start"],
                           "replay": [e["pid"] for e in replayed["provenance"]["events"] if e["event"] == "start"] if replayed else None},
            "kills": [e["returncode"] for e in replayed["provenance"]["events"] if e["event"] == "kill"] if replayed else None,
            "replayed_rec_sha256": r["rec_sha256"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--case")
    g.add_argument("--witnesses", action="store_true")
    a = ap.parse_args()
    run = a.run.resolve()
    if a.witnesses:
        w = json.loads((run / "witnesses.json").read_text())
        cases = list(dict.fromkeys(x["case_id"] for x in w["witnesses"] if x.get("replay", "").startswith("python replay.py")))
    else:
        cases = [a.case]
    out_dir = run / "replays"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    box, policy = preflight.sandbox()
    try:
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            results = [replay(box, run, c, Path(tmp)) for c in cases]
    finally:
        box.close()
    doc = {"schema": "d15.replay/v1", "run": run.name, "started": stamp, "sandbox": box.describe(), "policy": policy,
           "note": "additional attempts through the Framework sandbox, not part of the repeat=1 campaign attempts", "replays": results}
    (out_dir / f"replay-{stamp}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    same = sum(r["record_identical_except_live_provenance"] and r["digest_identical"] and r["wal_evidence_identical"] for r in results)
    print(f"replay: {same}/{len(results)} semantic records, digests and WAL evidence identical -> {out_dir.name}/replay-{stamp}.json")
    raise SystemExit(0 if same == len(results) else 1)


if __name__ == "__main__":
    main()
