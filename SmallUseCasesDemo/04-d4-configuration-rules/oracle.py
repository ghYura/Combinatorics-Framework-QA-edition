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

"""D4 oracle: independent legality rules and envelope checks (never reads the policy).

Acceptance and transformation are judged separately. A rejection must carry exactly the sorted
violated-rule IDs; an accepted envelope must have the exact URL, workers and header map, and its
body must decode (per Content-Encoding) to the original bytes. Gzip container bytes are never
compared, only the decoded payload.
"""
import base64
import gzip

ORIGINAL = b'{"sensor":7}\n'
RULES = ("R1", "R2", "R3", "R4", "R5", "R6")


def violations(c):
    f = set(c["features"])
    found = []
    if c["env"] == "prod" and c["transport"] == "http":
        found.append("R1")
    if c["mode"] == "live" and "cache" in f:
        found.append("R2")
    if c["mode"] == "live" and c["workers"] < 2:
        found.append("R3")
    if c["env"] == "prod" and f - {"audit", "gzip"}:
        found.append("R4")
    if c["mode"] == "batch" and "audit" in f and c["workers"] < 2:
        found.append("R5")
    if c["env"] == "prod" and c["debug"]:
        found.append("R6")
    return found


def expected_envelope(c):
    h = {}
    if "audit" in c["features"]:
        h["X-Audit"] = "1"
    if "cache" in c["features"]:
        h["Cache-Control"] = "max-age=60"
    h["Content-Encoding"] = "gzip" if "gzip" in c["features"] else "identity"
    if c["debug"]:
        h["X-Debug"] = "1"
    return {"url": f"{c['transport']}://telemetry.invalid/{c['mode']}", "workers": c["workers"], "headers": h}


def judge(config, result):
    """Acceptance check, transformation check (or NA), failure classes, overall ok."""
    want = violations(config)
    classes = []
    if want and result["accepted"]:
        classes.append("wrong_acceptance")
    elif not want and not result["accepted"]:
        classes.append("wrong_rejection")
    elif want and result["violations"] != want:
        classes.append("wrong_violation_ids")
    transformation = "not_applicable"
    if result["accepted"] and not want:
        env, exp = result["envelope"], expected_envelope(config)
        body = base64.b64decode(env["body_b64"])
        enc = env["headers"].get("Content-Encoding")
        try:
            decoded = gzip.decompress(body) if enc == "gzip" else body if enc == "identity" else None
        except OSError:
            decoded = None
        t = {"url": env["url"] == exp["url"], "workers": env["workers"] == exp["workers"],
             "headers": env["headers"] == exp["headers"], "payload": decoded == ORIGINAL}
        transformation = t
        classes += [f"wrong_{k}" for k, ok in t.items() if not ok]
    return {"expected_violations": want, "acceptance_ok": not any(c in classes for c in
            ("wrong_acceptance", "wrong_rejection", "wrong_violation_ids")),
            "transformation": transformation, "failure_classes": classes, "ok": not classes}
