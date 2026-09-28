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

"""D4 system under test: a local telemetry-request adapter (never sends anything).

CONTRACT.md v1. `adapt(config, policy)` validates one configuration and either rejects it with the
sorted violated-rule IDs or builds a request envelope. Policies: correct; drops_gzip (identity
encoding and raw body even when gzip is selected); ignores_debug_rule (validation without R6).
Nothing here knows the reference or the expected results.
"""
import base64
import gzip

POLICIES = ("correct", "drops_gzip", "ignores_debug_rule")
BODY = b'{"sensor":7}\n'


def _violations(c, policy):
    feats = set(c["features"])
    rules = [("R1", c["env"] == "prod" and c["transport"] == "http"),
             ("R2", c["mode"] == "live" and "cache" in feats),
             ("R3", c["mode"] == "live" and c["workers"] < 2),
             ("R4", c["env"] == "prod" and not feats <= {"audit", "gzip"}),
             ("R5", c["mode"] == "batch" and "audit" in feats and c["workers"] < 2),
             ("R6", c["env"] == "prod" and c["debug"])]
    return sorted(r for r, bad in rules if bad and not (policy == "ignores_debug_rule" and r == "R6"))


def adapt(config, policy):
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    bad = _violations(config, policy)
    if bad:
        return {"accepted": False, "violations": bad, "envelope": None}
    headers = {}
    if "audit" in config["features"]:
        headers["X-Audit"] = "1"
    if "cache" in config["features"]:
        headers["Cache-Control"] = "max-age=60"
    if "gzip" in config["features"] and policy != "drops_gzip":
        headers["Content-Encoding"], body = "gzip", gzip.compress(BODY, mtime=0)
    else:
        headers["Content-Encoding"], body = "identity", BODY
    if config["debug"]:
        headers["X-Debug"] = "1"
    return {"accepted": True, "violations": [],
            "envelope": {"url": f"{config['transport']}://telemetry.invalid/{config['mode']}",
                         "workers": config["workers"], "headers": headers,
                         "body_b64": base64.b64encode(body).decode("ascii")}}
