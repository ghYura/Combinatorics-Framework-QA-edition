"""Face 1 = the Bundle control panel for EVERYTHING.

These tests enforce the contract Yuri asked for: "do not miss any controllable
parameter through the Bundle without Face 1 knowing/controlling it." Concretely:

  1. every flag the real ``bundle_run.py`` run parser accepts (config + budget +
     repeat groups, and the inline run flags) is reachable from Face 1's server
     registry (``serve_face1.SUPPORTED_RUN_FLAGS``) — or is a deliberately
     env-inherited DB secret (``ENV_INHERITED_FLAGS``);
  2. the UI's ``FIELDS`` registry in ``intake/face1.html`` and the server's
     ``_RUN_FLAG_SPECS`` agree flag-for-flag (neither side silently drops one);
  3. the run-breaking gateway bug is fixed — ``_face_job`` no longer smuggles the
     gateway-owned ``db_name`` (which made every real run 500), and the gateway's
     own validator accepts the projected job;
  4. the LOCAL direct command builder emits the whole surface with no duplicates.
"""
import re
from pathlib import Path

import pytest

import intake.serve_face1 as sf

HERE = Path(__file__).resolve().parent
CLI = HERE / "bundle" / "cli.py"
# The reusable argparse group builders moved out of cli.py into their own module
# (2026-08-05). This test is about flag coverage, not file layout, so it follows
# them rather than pinning the old location.
CLIARGS = HERE / "bundle" / "cliargs.py"
FACE1 = HERE / "intake" / "face1.html"


def _func_src(src: str, name: str) -> str:
    """Source of a top-level ``def name(...)`` up to the next top-level def
    (or end of file, for the last function in a module)."""
    i = src.index(f"def {name}(")
    j = src.find("\ndef ", i + 1)
    return src[i:] if j == -1 else src[i:j]


def _argparse_flags(text: str) -> set:
    return set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', text))


# The run parser's own INLINE flags (main() in cli.py, verified by reading it).
# The auto-growing groups (config/budget/repeat) are extracted from source below.
INLINE_RUN_FLAGS = {
    "--db", "--lang", "--main-port", "--results-port", "--analyzer", "--analysis-mode",
    "--mode", "--sieve", "--draw", "--draw-exact", "--seed-from", "--base-url",
    "--workers", "--duration", "--ramp", "--slo-p99", "--err-budget", "--run-id",
    "--runs-root", "--legacy-scratch", "--legacy-handoff", "--override-budget",
    "--allow-extreme", "--unleash-initial-productivity-power", "--cost-per-candidate",
    "--debug", "--iterations",
}


def _cli_run_flags() -> set:
    args_src = CLIARGS.read_text(encoding="utf-8")
    flags = set(INLINE_RUN_FLAGS)
    for fn in ("_add_bundle_config_args", "_add_budget_ceiling_args", "_add_repeat_args"):
        flags |= _argparse_flags(_func_src(args_src, fn))
    return flags


@pytest.mark.skipif(not CLI.exists(), reason="EXPECTED_OPTIONAL: bundle/cli.py not present")
def test_no_run_flag_is_missing_from_face1():
    """Every bundle_run.py run flag is exposed by Face 1 (or an env-inherited secret)."""
    cli_flags = _cli_run_flags()
    reachable = set(sf.SUPPORTED_RUN_FLAGS) | set(sf.ENV_INHERITED_FLAGS)
    missing = cli_flags - reachable
    assert not missing, (
        "these bundle_run.py run flags are not controllable from Face 1 nor marked "
        f"env-inherited: {sorted(missing)}"
    )
    # The 6 DB credential/host flags must be the env-inherited set exactly.
    assert sf.ENV_INHERITED_FLAGS == {
        "--main-db-host", "--main-db-user", "--main-db-password",
        "--results-db-host", "--results-db-user", "--results-db-password",
    }
    # every env-inherited secret is a real cli flag and is NOT double-exposed
    assert sf.ENV_INHERITED_FLAGS.issubset(
        _argparse_flags(_func_src(CLIARGS.read_text(encoding="utf-8"), "_add_bundle_config_args"))
    )
    assert not (set(sf.SUPPORTED_RUN_FLAGS) & set(sf.ENV_INHERITED_FLAGS))


@pytest.mark.skipif(not FACE1.exists(), reason="EXPECTED_OPTIONAL: intake/face1.html not present")
def test_ui_and_server_registries_agree():
    """The UI FIELDS registry mirrors the server _RUN_FLAG_SPECS flag-for-flag."""
    html = FACE1.read_text(encoding="utf-8")
    fields_txt = html[html.index("const FIELDS=["):html.index("const SECTIONS=")]
    ui_keys = set(re.findall(r'\bf:"([A-Za-z0-9]+)"', fields_txt))
    ui_flags = set(re.findall(r'\bfl:"(--[a-z0-9-]+)"', fields_txt))

    # Every value/bool flag the server can emit is a UI field (reachable).
    server_keys = {k for k, _f, _kind in sf._RUN_FLAG_SPECS}
    server_flags = {f for _k, f, _kind in sf._RUN_FLAG_SPECS}
    assert server_keys <= ui_keys, f"server keys with no UI control: {sorted(server_keys - ui_keys)}"
    assert server_flags <= ui_flags, f"server flags with no UI control: {sorted(server_flags - ui_flags)}"

    # Every stress knob is a UI field too.
    stress_keys = {k for k, _f in sf._STRESS_FLAG_SPECS}
    assert stress_keys <= ui_keys, f"stress knobs missing from UI: {sorted(stress_keys - ui_keys)}"

    # Conversely, every UI flag is something the server knows how to emit.
    assert ui_flags <= set(sf.SUPPORTED_RUN_FLAGS), (
        f"UI exposes flags the server can't emit: {sorted(ui_flags - set(sf.SUPPORTED_RUN_FLAGS))}"
    )


def test_old_face1_receives_and_consumes_the_canonical_capability_dimensions():
    payload = sf._ping_payload()
    dimensions = payload["capability_dimensions"]
    assert dimensions["language"]["values"] == ["python", "java"]
    assert dimensions["candidate_sink"]["values"] == ["loose-files", "sharded", "grpc"]
    html = FACE1.read_text(encoding="utf-8")
    assert "d.capability_dimensions" in html
    for dimension in ("language", "run_mode", "analyzer", "candidate_sink"):
        assert f'values("{dimension}")' in html


def test_face_job_is_gateway_safe_no_db_name(tmp_path):
    """Regression: _face_job must NOT send db_name (gateway-owned) — that rejection
    (PERMISSION_DENIED) 500'd every real run — and executor_pool must wire through."""
    job = sf._face_job("spec_version='1'\n", {"lang": "py", "executorPool": 3, "mode": "formal",
                                              "profile": "generated-default"})
    assert "db_name" not in job, "db_name is gateway-owned and must not be supplied"
    assert job["executor_pool"] == 3, "executor_pool must read the UI's real key"

    # The gateway's own validator now accepts the projected job (no raise).
    from bundle.gateway.engine import GatewayConfig, GatewayEngine, GatewayLimits
    eng = GatewayEngine(GatewayConfig(
        gen_dir=HERE, runs_root=tmp_path / "gw",
        limits=GatewayLimits(max_concurrent_jobs=1, max_worker_units=4, max_executor_pool=4, max_iterations=5),
    ))
    # Audit F1: the gateway now requires the job to name its execution policy,
    # so the UI projection must carry the operator's choice through.
    norm = eng._normalize_job("face1", sf._face_job(
        "spec_version='1'\n[[slots]]\nsheet='A'\n",
        {"lang": "py", "executorPool": 2, "profile": "generated-default"}))
    assert norm["executor_pool"] == 2
    assert norm["db_name"] == ""  # gateway derives it, tenant did not supply it


def test_direct_command_covers_the_full_surface(tmp_path):
    """LOCAL mode builds the whole flag surface from one config, without duplicates."""
    cfg = {
        "backend": "local", "lang": "java", "runMode": "stress", "db": "My Task", "runId": "r1",
        "iterations": "2", "analyzer": "lat:min,tput:max", "mode": "formal",
        "profile": "networked-api-probe", "transport": "grpc", "grpcHost": "127.0.0.1", "grpcPort": "50070",
        "sieve": True, "drawExact": True, "executorPool": "3", "executorCompiler": "ecj", "seedOutput": True,
        "explorationFloor": "0.3", "minWinnerSupport": "7", "sandboxCandidateEnv": "U=http://x",
        "executorTolerateOutcomes": "BROKEN", "budgetFinalCandidates": "100000", "costPerCandidate": "0.01",
        "overrideBudget": "go", "allowExtreme": True, "unleash": True, "repeat": "3", "repeatPolicy": "local",
        "repeatScope": "metrics", "repeatEnvironments": "2", "coreTimeout": "900", "scratchRoot": "/mnt/fw",
        "javaCmd": "java25", "configFile": "o.json", "legacyHandoff": True, "debug": True,
        "baseUrl": "http://sut", "workers": "24", "duration": "10", "ramp": "3", "sloP99": "1500", "errBudget": "0.01",
    }
    cmd = sf._direct_command(cfg, tmp_path / "spec", "my_task", "r1", tmp_path / "runs")
    flags = [tok for tok in cmd if tok.startswith("--")]
    assert len(flags) == len(set(flags)), f"duplicate flags: {[f for f in flags if flags.count(f) > 1]}"
    assert Path(cmd[1]) == sf.GEN_DIR / "bundle_run.py"
    assert cmd[2] == "iterate"  # iterations>1 => iterate subcommand
    # a representative slice across every component/group is present and correct
    for expect in ("--lang", "--candidate-sink", "--grpc-host", "--executor-pool", "--sieve",
                   "--draw-exact", "--execution-policy-profile", "--repeat-policy", "--budget-final-candidates",
                   "--unleash-initial-productivity-power", "--core-timeout", "--config-file",
                   "--base-url", "--slo-p99", "--analyzer", "--analysis-mode", "--iterations"):
        assert expect in cmd, f"{expect} missing from the direct command"
    # db is slugged; the gateway-owned secret flags never appear
    assert "--db" in cmd and cmd[cmd.index("--db") + 1] == "my_task"
    assert not (set(cmd) & set(sf.ENV_INHERITED_FLAGS))
    # stress knobs only when runMode == stress
    verdict = sf._direct_command(dict(cfg, runMode="verdict"), tmp_path / "s", "d", "r", tmp_path / "r")
    assert "--base-url" not in verdict and "--slo-p99" not in verdict
