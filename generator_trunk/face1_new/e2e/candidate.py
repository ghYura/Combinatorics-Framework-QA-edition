"""Runtime called by generated Bundle candidates."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile

from .actions import FlowResult, run_flow
from .page_object import Face1Page, browser_session


VIEWPORTS = {
    "desktop": (1440, 1000),
    "compact": (900, 760),
}


def configured_endpoints() -> tuple[str, ...]:
    raw = os.environ.get("FACE1_E2E_URLS", "http://127.0.0.1:8088")
    endpoints = tuple(item.strip().rstrip("/") for item in raw.split(";") if item.strip())
    if not endpoints:
        raise RuntimeError("FACE1_E2E_URLS contains no endpoints")
    if any(not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")) for endpoint in endpoints):
        raise RuntimeError("Face 1 dogfood candidates accept local test endpoints only")
    return endpoints


def endpoint_for(browser: str, viewport: str, flow: str, data_profile: str) -> str:
    endpoints = configured_endpoints()
    identity = "\0".join((browser, viewport, flow, data_profile)).encode()
    index = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") % len(endpoints)
    return endpoints[index]


def execute_candidate(browser: str, viewport: str, flow: str, data_profile: str) -> FlowResult:
    if viewport not in VIEWPORTS:
        return FlowResult(flow, False, 0, 0.0, f"unknown viewport {viewport!r}")
    endpoint = endpoint_for(browser, viewport, flow, data_profile)
    with tempfile.TemporaryDirectory(prefix="face1-e2e-download-") as tmp:
        downloads = Path(tmp)
        try:
            headless = os.environ.get("FACE1_E2E_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}
            with browser_session(browser, downloads, VIEWPORTS[viewport], headless=headless) as driver:
                page = Face1Page(driver, endpoint, download_dir=downloads, timeout=20)
                return run_flow(page, flow, data_profile)
        except Exception as exc:
            error = re.sub(r"\s+", " ", f"{type(exc).__name__}: {exc}").strip()[:500]
            return FlowResult(flow, False, 0, 0.0, error)


def metric_line(result: FlowResult, browser: str, viewport: str, data_profile: str) -> str:
    """Exactly one Analyzer-compatible K=V line per generated candidate."""
    safe = lambda value: re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))  # noqa: E731
    error_id = hashlib.sha256(result.error.encode()).hexdigest()[:12] if result.error else "none"
    classified = re.match(
        r"^(?P<kind>[A-Za-z]+) at (?P<file>[A-Za-z0-9_.-]+):(?P<line>[0-9]+):(?P<func>[A-Za-z0-9_<>-]+)",
        result.error,
    )
    error_type = classified.group("kind") if classified else ("none" if not result.error else "unclassified")
    error_site = (
        f"{classified.group('file')}.L{classified.group('line')}.{classified.group('func')}"
        if classified else "none"
    )
    return (
        "app=face1_new_e2e "
        f"flow={safe(result.flow)} browser={safe(browser)} viewport={safe(viewport)} "
        f"data_profile={safe(data_profile)} correct={int(result.ok)} checks={result.checks} "
        f"latency_ms={result.latency_ms:.3f} error_id={error_id} "
        f"error_type={safe(error_type)} error_site={safe(error_site)} "
        f"FW_VAR={0 if result.ok else 2}"
    )
