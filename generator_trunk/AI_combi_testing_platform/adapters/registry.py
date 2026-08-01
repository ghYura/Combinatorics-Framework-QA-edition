"""Adapter lookup with no implicit network path."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import Adapter, AdapterInfrastructureError
from .external import ExternalHTTPAdapter, ExternalHTTPConfig
from .local import FragileControlAdapter, OracleControlAdapter


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
