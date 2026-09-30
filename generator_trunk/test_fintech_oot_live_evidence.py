# SPDX-License-Identifier: LicenseRef-BUSL-1.1
"""Required live probes cannot pass without observable live evidence.

The gateways are real companion SUT apps connected through an in-memory HTTP
transport. No server, sockets, database, or SUT behavior patches are required.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tomllib
from urllib.parse import urlsplit

import pytest

from fintech_oot import testgen_oot as generator
from sut_paths import project_path

SUT = project_path("fintech")
pytestmark = pytest.mark.skipif(
    not (SUT / "finance_stack" / "gateway.py").is_file(),
    reason="MISSING_AUTHORIZED_BACKEND: companion fintech SUT is unavailable",
)


class GatewayCluster:
    def __init__(self):
        pytest.importorskip("fastapi", reason="EXPECTED_OPTIONAL: fintech gateway regressions use the isolated fintech environment")
        pytest.importorskip("httpx", reason="EXPECTED_OPTIONAL: fintech gateway regressions use the isolated fintech environment")
        sys.path.insert(0, str(SUT))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from finance_stack.ecosystem import Ecosystem
        from finance_stack.gateway import build_gateway_app
        from finance_stack.network import InProcessBankPort

        self.source = Ecosystem()
        self.target = Ecosystem()
        self.source.add_bank("AURUM", "Aurum")
        beneficiary = self.target.add_bank("NORD", "Nord")
        self.source.add_remote_bank("NORD", "Nord", InProcessBankPort(beneficiary.ledger))
        self.source.set_time_config_propagator(
            lambda values: self.target.update_time_config(values, incoming=True)
        )
        self.clients = {}
        for port, alias, eco in ((8121, "toBank1", self.source), (8122, "toBank2", self.target)):
            app = FastAPI()
            app.mount("/" + alias, build_gateway_app(eco, "oot-secret"))
            self.clients[port] = TestClient(app)
        self.observed = []
        self.override = None

    def request(self, method, url, **kwargs):
        import httpx

        parsed = urlsplit(url)
        self.observed.append((method, parsed.path))
        if self.override:
            response = self.override(method, parsed.path)
            if response is not None:
                return response
        if parsed.path == "/toBank2/health":
            return httpx.Response(200, json={"ok": True})
        kwargs.pop("timeout", None)
        return self.clients[parsed.port].request(method, parsed.path, **kwargs)


def execute(http, **parameters):
    namespace = {"__file__": str(Path(__file__).resolve())}
    exec(generator.HEAD, namespace)
    namespace["_httpx"] = http
    namespace.update(parameters)
    exec(generator.TAIL, namespace)
    return namespace


@pytest.fixture
def cluster(monkeypatch):
    monkeypatch.delenv("OOT_MODE", raising=False)
    monkeypatch.setenv("OOT_SECRET", "oot-secret")
    monkeypatch.setenv("OOT_TARGET1", "http://127.0.0.1:8121")
    monkeypatch.setenv("OOT_TARGET2", "http://127.0.0.1:8122")
    return GatewayCluster()


@pytest.mark.parametrize("parameters", [{}, {"LIVE_XFER": "on"}, {"TIME_SYNC": "risk_window_seconds"}])
def test_missing_live_dependency_does_not_emit_a_pass(cluster, parameters, capsys):
    with pytest.raises(RuntimeError, match="required live probe needs httpx"):
        execute(None, **parameters)
    assert "app=fintech_oot" not in capsys.readouterr().out


@pytest.mark.parametrize("auth", ["valid_hmac", "bad_signature", "missing_headers", "expired_timestamp"])
def test_unavailable_live_cluster_never_passes(cluster, auth, capsys):
    def unavailable(*args):
        raise OSError("cluster unavailable")

    cluster.override = unavailable
    with pytest.raises(RuntimeError, match="required live probe unavailable"):
        execute(cluster, AUTH=auth)
    assert "app=fintech_oot" not in capsys.readouterr().out


@pytest.mark.parametrize("status,body", [(503, {"error": "down"}), (200, {}), (200, "not JSON")])
def test_unusable_client_response_is_not_success(cluster, status, body):
    import httpx

    cluster.override = lambda method, path: httpx.Response(status, json=body)
    with pytest.raises(RuntimeError, match="required live"):
        execute(cluster)


@pytest.mark.parametrize("body", [{}, {"ok": False}, "bad health"])
def test_unusable_cross_node_health_fails_closed(cluster, body):
    import httpx

    cluster.override = lambda method, path: httpx.Response(200, json=body) if path.endswith("/health") else None
    with pytest.raises(RuntimeError, match="cross-node health probe failed"):
        execute(cluster)


def test_time_sync_requires_a_readable_observation(cluster):
    import httpx

    cluster.override = lambda method, path: (
        httpx.Response(200, json={}) if method == "GET" and path.endswith("/time-config") else None
    )
    with pytest.raises(RuntimeError, match="no usable response"):
        execute(cluster, TIME_SYNC="risk_window_seconds")


@pytest.mark.parametrize("auth", ["valid_hmac", "bad_signature", "missing_headers", "expired_timestamp"])
def test_real_auth_probe_accepts_correct_enforcement(cluster, auth):
    result = execute(cluster, AUTH=auth)
    assert result["FW_VAR"] == 0
    assert result["METRICS"]["auth_enforced"] == 1


def test_observed_time_sync_mismatch_is_a_domain_failure(cluster):
    import httpx

    cluster.override = lambda method, path: (
        httpx.Response(200, json={"risk_window_seconds": 1234})
        if method == "GET" and path.endswith("/time-config") else None
    )
    result = execute(cluster, TIME_SYNC="risk_window_seconds")
    assert result["FW_VAR"] == 3


@pytest.mark.parametrize("accept,propagate", [("true", "connected"), ("false", "connected"), ("true", "self")])
def test_real_time_sync_policy_remains_observable(cluster, accept, propagate):
    result = execute(cluster, TIME_SYNC="risk_window_seconds", ACCEPT_SYNC=accept, PROPAGATE=propagate)
    assert result["FW_VAR"] == 0
    expected = 60 if accept == "true" and propagate == "connected" else 4321
    assert cluster.target.time_config.risk_window_seconds == expected


@pytest.mark.parametrize("path_suffix,body", [("/accounts", {}), ("/transfers", {"transfer": {}})])
def test_live_transfer_requires_observable_creation(cluster, path_suffix, body):
    import httpx

    cluster.override = lambda method, path: httpx.Response(200, json=body) if path.endswith(path_suffix) else None
    with pytest.raises(RuntimeError, match="no usable"):
        execute(cluster, LIVE_XFER="on")


def test_observed_wrong_live_transfer_state_is_a_domain_failure(cluster):
    import httpx

    cluster.override = lambda method, path: (
        httpx.Response(200, json={"transfer": {"status": "FAILED"}})
        if path.endswith("/transfers") else None
    )
    result = execute(cluster, LIVE_XFER="on")
    assert result["FW_VAR"] == 3
    assert result["METRICS"]["http_final"] == "FAILED"


@pytest.mark.parametrize("amount,expected", [("100.00", "SETTLED"), ("2000.00", "REJECTED")])
def test_real_live_transfer_and_boundary_rejection_remain_valid(cluster, amount, expected):
    result = execute(cluster, LIVE_XFER="on", AMOUNT=amount)
    assert result["FW_VAR"] == 0
    assert result["METRICS"]["http_final"] == expected
    assert result["METRICS"]["http_settled"] == int(expected == "SETTLED")
    assert any(path == "/toBank1/v1/transfers" for _, path in cluster.observed)
    target_accounts = cluster.target.bank("NORD").ledger.list_accounts()
    assert target_accounts[-1].balance.as_str == ("100.00" if expected == "SETTLED" else "0.00")


def test_seeded_domain_failure_still_reaches_oracle(cluster):
    result = execute(cluster, AMOUNT="-1.00")
    assert result["FW_VAR"] == 6
    assert result["METRICS"]["violations"] > 0
    assert result["METRICS"]["settled"] == 1


@pytest.mark.parametrize("factor,expected", [("peer_hold", "ON_HOLD"), ("peer_down", "FAILED")])
def test_intentional_inprocess_peer_outages_remain_valid(cluster, factor, expected):
    result = execute(cluster, TOPOLOGY="cross", FACTORS=["after_initiate:" + factor])
    assert result["FW_VAR"] == 0
    assert result["METRICS"]["transfer_status"] == expected


def test_checked_in_batches_share_the_verified_probe_source():
    for path in generator.BATCHES.glob("*/*.toml"):
        spec = tomllib.loads(path.read_text())
        head = next(slot["values"][0] for slot in spec["slots"] if slot["sheet"] == "HEAD")
        tail = next(slot["values"][0] for slot in spec["slots"] if slot["sheet"] == "TAIL")
        assert head == generator.HEAD
        assert "\n".join(line[4:] for line in tail.splitlines()[4:]) + "\n" == generator.TAIL
