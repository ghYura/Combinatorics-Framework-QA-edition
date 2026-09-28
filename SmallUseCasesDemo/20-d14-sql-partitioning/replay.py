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


"""Replay complete D14b candidates against the retained, unchanged fixture; compare their records with the campaign's.

    python replay.py --run evidence/<run-id> --case '<id>'      # one witness
    python replay.py --run evidence/<run-id> --witnesses        # the five named witnesses (witnesses.json)

The candidate comes from the run's candidates.tar.gz, byte for byte, and runs through the Framework's own
Executor sandbox exactly as in the campaign: networked-api-probe, the fixture as the only allowlisted
target, the same local client image, D14B_FIXTURE set. Each replay is an additional attempt (four more
data SELECTs), recorded under evidence/<run-id>/replays/ with the fixture's SQL log segment for the
replays. Every mathematical field must equal the campaign record; live provenance (backend PID,
snapshot) is expected to differ and is recorded separately.
"""
import argparse
import base64
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
import fixture as fixture_tool                     # the same sandbox helper the setup probe used; not the verifier

LIVE = ("provenance", "framework")


def replay(run: Path, case: str, tmp: Path, fixture: str, image: str):
    records = {json.loads(l)["id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rec = records[case]
    name = rec["framework"]["source_ref"]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress((run / "candidates.tar.gz").read_bytes()))) as tar:
        data = tar.extractfile(f"src/{name}").read()
    if hashlib.sha256(data).hexdigest() != rec["framework"]["source_sha256"]:
        raise SystemExit(f"{name}: archive bytes differ from the executed candidate's hash")
    path = tmp / name
    path.write_bytes(data)
    path.chmod(0o644)
    res = fixture_tool.run_sandboxed(fixture, image, path)
    line = next((l for l in (res["stdout"] or "").splitlines() if l.startswith("app=") and "FW_VAR=" in l), "")
    tokens = dict(t.split("=", 1) for t in line.split() if "=" in t)
    replayed = json.loads(base64.urlsafe_b64decode(tokens["rec"])) if "rec" in tokens else None
    same = replayed is not None and {k: v for k, v in replayed.items() if k not in LIVE} == {k: v for k, v in rec.items() if k not in LIVE}
    fwv = next((l for l in (res["stdout"] or "").splitlines() if l.startswith("__FWV__")), "")
    return {"case_id": case, "candidate": name, "candidate_sha256": rec["framework"]["source_sha256"], "exit_code": res["exit_code"],
            "sandbox": res["describe"], "attached_targets": res["attached_targets"], "fwv_marker": fwv, "stderr_tail": res["stderr_tail"],
            "campaign_outcome": rec["framework"]["outcome"], "replayed_verdict": replayed and replayed["verdict"],
            "mathematical_fields_identical": same, "replayed_rec_sha256": tokens.get("rec_sha256"),
            "provenance": {"campaign": {k: rec["provenance"][k] for k in ("backend_pid", "snapshot")},
                           "replay": {k: replayed["provenance"][k] for k in ("backend_pid", "snapshot", "database", "user",
                                                                             "transaction_isolation", "transaction_read_only")} if replayed else None},
            "data_selects": sum(1 for s in (replayed or {}).get("provenance", {}).get("statements", []) if s["kind"].startswith("data:"))}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--case")
    g.add_argument("--witnesses", action="store_true")
    a = ap.parse_args()
    run = a.run.resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    fixture, image, stamp = manifest["fixture"]["names"]["container"], manifest["fixture"]["names"]["image"], manifest["fixture"]["stamp"]
    if a.witnesses:
        w = json.loads((run / "witnesses.json").read_text())
        cases = list(dict.fromkeys(x["case_id"] for x in w["witnesses"] if x.get("replay", "").startswith("python replay.py")))
    else:
        cases = [a.case]
    out_dir = run / "replays"
    out_dir.mkdir(exist_ok=True)
    stamp_now = datetime.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    pre = fixture_tool.docker("logs", fixture)
    pre_text = pre.stdout + pre.stderr
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        results = [replay(run, c, Path(tmp), fixture, image) for c in cases]
    post = fixture_tool.docker("logs", fixture)
    segment = (post.stdout + post.stderr)[len(pre_text):]
    (out_dir / f"replay-sql-{stamp_now}.log").write_text(segment)
    after = fixture_tool.export(stamp, out_dir / f"fixture-after-replay-{stamp_now}", "after-replay")
    data_lines = [l for l in segment.splitlines() if "statement: SELECT i.val " in l]
    doc = {"schema": "d14b.replay/v1", "run": run.name, "started": stamp_now, "image": image, "fixture": fixture,
           "note": "additional attempts, not part of the repeat=1 campaign attempts", "replays": results,
           "replay_data_selects_in_server_log": len(data_lines), "fixture_after_replay": after,
           "fixture_unchanged": all(after[k] == manifest["fixture"]["export_before"][k] for k in ("items_sha256", "tags_sha256", "catalog_sha256"))}
    (out_dir / f"replay-{stamp_now}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    same = sum(r["mathematical_fields_identical"] for r in results)
    print(f"replay: {same}/{len(results)} records identical in every mathematical field; {len(data_lines)} data SELECTs in the "
          f"server log; fixture unchanged: {doc['fixture_unchanged']} -> {out_dir.name}/replay-{stamp_now}.json")
    raise SystemExit(0 if same == len(results) and doc["fixture_unchanged"] else 1)


if __name__ == "__main__":
    main()
