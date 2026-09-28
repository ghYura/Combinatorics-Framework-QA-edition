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

"""Replay one D11 candidate exactly as rendered, and compare its record with the campaign's.

    python replay.py --run evidence/<run-id> --case '<case_id>'   # one witness
    python replay.py --run evidence/<run-id> --witnesses          # every witness in witnesses.json (D11)

The candidate comes from the run's candidates.tar.gz, byte for byte. It runs in the
same sandbox image as the campaign (`python:3-slim`, no network, read-only root, file
mounted read-only) through the Executor's own runner shape (runpy, then FW_VAR). Replays
are additional attempts, recorded under evidence/<run-id>/replays/, separate from the
campaign attempts. The replayed record must be byte-identical to the campaign's.
"""
import argparse
import base64
import datetime
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "python:3-slim"
RUNNER = ("import runpy,sys\n"
          "ns = runpy.run_path(sys.argv[1], run_name='__main__')\n"
          "print('__FWV__ %d %d' % (int(ns.get('FW_VAR', -999)), int(ns.get('FW_CUSTOM_VAR', -999))))\n")


def replay(run: Path, case: str, tmp: Path):
    records = {json.loads(l)["case_id"]: json.loads(l)
               for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rec = records[case]
    name = rec["framework"]["source_ref"]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress((run / "candidates.tar.gz").read_bytes()))) as tar:
        data = tar.extractfile(f"src/{name}").read()
    if hashlib.sha256(data).hexdigest() != rec["framework"]["source_sha256"]:
        raise SystemExit(f"{name}: archive bytes differ from the executed candidate's hash")
    path = tmp / name
    path.write_bytes(data)
    path.chmod(0o644)
    cmd = ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
           "--memory", "512m", "--pids-limit", "64", "-v", f"{path}:/cand/{name}:ro", IMAGE,
           "python", "-c", RUNNER, f"/cand/{name}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    line = next((l for l in r.stdout.splitlines() if l.startswith("app=") and "FW_VAR=" in l), "")
    tokens = dict(t.split("=", 1) for t in line.split() if "=" in t)
    replayed = json.loads(base64.urlsafe_b64decode(tokens["rec"])) if "rec" in tokens else None
    campaign = {k: v for k, v in rec.items() if k != "framework"}
    fwv = next((l for l in r.stdout.splitlines() if l.startswith("__FWV__")), "")
    return {"case_id": case, "candidate": name, "candidate_sha256": rec["framework"]["source_sha256"],
            "command": cmd[:-4] + ["python", "-c", "<Executor runner>", f"/cand/{name}"],
            "exit_code": r.returncode, "fwv_marker": fwv, "stderr_tail": r.stderr[-500:],
            "campaign_outcome": rec["framework"]["outcome"], "replayed_verdict": replayed and replayed["verdict"],
            "record_identical": replayed == campaign,
            "replayed_rec_sha256": tokens.get("rec_sha256")}


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
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        results = [replay(run, c, Path(tmp)) for c in cases]
    doc = {"schema": "d11.replay/v1", "run": run.name, "started": stamp, "image": IMAGE,
           "note": "additional attempts, not part of the K=1 campaign attempts", "replays": results}
    (out_dir / f"replay-{stamp}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    same = sum(r["record_identical"] for r in results)
    print(f"replay: {same}/{len(results)} records byte-identical to the campaign -> {out_dir.name}/replay-{stamp}.json")
    raise SystemExit(0 if same == len(results) else 1)


if __name__ == "__main__":
    main()
