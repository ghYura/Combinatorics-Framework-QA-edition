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

"""Small stateful service built specifically for an end-to-end Bundle tryout."""
from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import BaseModel, Field


SECRET_RE = re.compile(r"SECRET-[A-Za-z0-9]+")
LEGACY_SECRET_RE = re.compile(r"SECRET-[A-Za-z0-9]+", re.ASCII)
KEYS = {1: "bundle-key-v1", 2: "bundle-key-v2"}


@dataclass
class ScenarioState:
    key_version: int = 1
    poisoned: bool = False


class ProcessRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=120)
    mode: str
    order: list[str]
    features: list[str] = Field(default_factory=list)
    text: str


class EmptyRequest(BaseModel):
    pass


app = FastAPI(title="Bundle Secure Pipeline Tryout", version="1.0.0")
_states: dict[str, ScenarioState] = {}
_lock = threading.RLock()


def _state(scenario_id: str) -> ScenarioState:
    with _lock:
        return _states.setdefault(scenario_id, ScenarioState())


def _robust_redact(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return SECRET_RE.sub("[REDACTED]", normalized)


def _legacy_redact(text: str) -> str:
    return LEGACY_SECRET_RE.sub("[REDACTED]", text)


def _digest(text: str, key_version: int) -> str:
    return hashlib.sha256((KEYS[key_version] + "|" + text).encode("utf-8")).hexdigest()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "bundle-secure-pipeline", "version": "1.0.0"}


@app.post("/scenario/{scenario_id}/rotate-key")
def rotate_key(scenario_id: str, _request: EmptyRequest) -> dict:
    state = _state(scenario_id)
    with _lock:
        state.key_version = 2
    return {"ok": True, "key_version": state.key_version}


@app.post("/scenario/{scenario_id}/poison-cache")
def poison_cache(scenario_id: str, _request: EmptyRequest) -> dict:
    state = _state(scenario_id)
    with _lock:
        state.poisoned = True
    return {"ok": True, "poisoned": state.poisoned}


@app.post("/process")
def process(request: ProcessRequest) -> dict:
    if request.mode not in {"strict", "legacy"}:
        return {"ok": False, "error": "unknown mode"}
    if sorted(request.order) != ["normalize", "redact", "tag"]:
        return {"ok": False, "error": "invalid operation order"}

    state = _state(request.scenario_id)
    text = request.text
    for operation in request.order:
        if operation == "normalize":
            text = unicodedata.normalize("NFKC", text)
        elif operation == "redact":
            text = _robust_redact(text) if request.mode == "strict" else _legacy_redact(text)
        elif operation == "tag":
            text += "|TAG"

    # Deliberate legacy defects for the Bundle oracle to discover:
    # stale key after rotation, and trusting a poisoned digest cache.
    key_version = state.key_version if request.mode == "strict" else 1
    digest = _digest(text, key_version)
    if request.mode == "legacy" and state.poisoned and "cache" in request.features:
        digest = "0" * 64

    return {
        "ok": True,
        "text": text,
        "digest": digest,
        "key_version": key_version,
        "audit": "audit" in request.features,
        "mode": request.mode,
        "order": request.order,
        "features": sorted(request.features),
    }
