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

"""Adapter lookup with no implicit network path."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import Adapter, AdapterInfrastructureError
from .external import ExternalHTTPAdapter, ExternalHTTPConfig
from .local import (
    FragileControlAdapter,
    InjectableControlAdapter,
    OracleControlAdapter,
)


def _config_path(explicit: str | Path | None) -> Path:
    raw = str(explicit or os.environ.get("AI_COMBI_CONFIG") or "").strip()
    if not raw:
        raise AdapterInfrastructureError(
            "external adapter selection requires AI_COMBI_CONFIG or config_path"
        )
    return Path(raw).expanduser().resolve()


def load_adapter(
    adapter_id: str,
    *,
    config_path: str | Path | None = None,
) -> Adapter:
    if adapter_id == "oracle-control":
        return OracleControlAdapter()
    if adapter_id == "fragile-control":
        return FragileControlAdapter()
    if adapter_id == "injectable-control":
        return InjectableControlAdapter()
    path = _config_path(config_path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterInfrastructureError(
            f"cannot read external adapter configuration: {path}"
        ) from exc
    adapters = document.get("external_adapters") if isinstance(document, dict) else None
    if not isinstance(adapters, list):
        raise AdapterInfrastructureError(
            "configuration must contain an external_adapters list"
        )
    for item in adapters:
        if isinstance(item, dict) and str(item.get("id") or "") == adapter_id:
            return ExternalHTTPAdapter(ExternalHTTPConfig.from_dict(item))
    raise AdapterInfrastructureError(f"unknown adapter id: {adapter_id!r}")
