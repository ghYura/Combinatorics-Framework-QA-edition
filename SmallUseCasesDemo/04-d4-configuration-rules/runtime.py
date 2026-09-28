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

"""D4 runtime: configuration atoms, one adapter call, one judged record.

HEAD initialises an empty configuration (debug=false, no features). The atoms impl("..");,
env("..");, mode("..");, transport("..");, feature("..");, workers(n); and debug(); fill it; each
factor may be set once. finish("main"|"controls") requires a complete configuration with exactly
two distinct features, calls the SUT, judges the result with the oracle and prints one line:

  app=d4_config FW_VAR=<0|2> case=<id> verdict=<...> rec=<base64url JSON> rec_sha256=<hex>

Incomplete or repeated atoms raise (the Executor records BROKEN, never a domain verdict).
FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d4_config"
CARRIER = 2
AXES = ("env", "mode", "transport", "features", "workers", "debug")
SOURCE_SHA256 = {}
_cfg = {"features": set(), "debug": False}


def _set(key, value, allowed):
    if key in _cfg:
        raise ValueError(f"{key} set twice")
    if value not in allowed:
        raise ValueError(f"{key}={value!r} is outside the contract")
    _cfg[key] = value


def impl(policy):
    _set("policy", policy, sut.POLICIES)


def env(v):
    _set("env", v, ("dev", "prod"))


def mode(v):
    _set("mode", v, ("batch", "live"))


def transport(v):
    _set("transport", v, ("http", "https"))


def workers(n):
    _set("workers", n, (1, 2))


def feature(v):
    if v not in ("audit", "cache", "gzip") or v in _cfg["features"]:
        raise ValueError(f"feature {v!r} unknown or repeated")
    _cfg["features"].add(v)


def debug():
    if _cfg["debug"]:
        raise ValueError("debug set twice")
    _cfg["debug"] = True


def key(c):
    return "|".join(f"{a}={'+'.join(c[a]) if a == 'features' else int(c[a]) if a == 'debug' else c[a]}" for a in AXES)


def finish(phase):
    if phase not in ("main", "controls"):
        raise ValueError(f"unknown phase {phase!r}")
    missing = [k for k in ("policy", "env", "mode", "transport", "workers") if k not in _cfg]
    if missing or len(_cfg["features"]) != 2:
        raise ValueError(f"incomplete configuration: missing {missing}, features {sorted(_cfg['features'])}")
    config = {"env": _cfg["env"], "mode": _cfg["mode"], "transport": _cfg["transport"],
              "features": sorted(_cfg["features"]), "workers": _cfg["workers"], "debug": _cfg["debug"]}
    result = sut.adapt(config, _cfg["policy"])
    judged = oracle.judge(config, result)                 # policy-blind
    fw_var = 0 if judged["ok"] else CARRIER
    rec = {"schema": "d4.observation/v1", "contract": "v1", "case_id": f"{phase}|{_cfg['policy']}|{key(config)}",
           "phase": phase, "policy": _cfg["policy"], "config": config, "result": result, **judged,
           "verdict": "PASS" if fw_var == 0 else "DOMAIN_FAIL", "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % rec["case_id"], "verdict=%s" % rec["verdict"],
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"), "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]),
          flush=True)
    return fw_var
