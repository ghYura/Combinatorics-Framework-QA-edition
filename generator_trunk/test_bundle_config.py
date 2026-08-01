#!/usr/bin/env python3
"""Targeted tests for bundle.config (STEP 13 — unified configuration layering):
CLI > environment > config file > defaults precedence, typed coercion/validation
errors that name the offending key and layer, and the redacted resolved-config
artifact (run: `python3 test_bundle_config.py`)."""
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import fwgen as fg
from bundle import database as database_module
from bundle import stages
from bundle.handoff import HANDOFF_SCHEMA, handoff_from_dict
from bundle.config import BundleConfig, ConfigError, config_to_dict, resolve_config
from bundle.jsonio import REDACTED, redact, to_dict
from bundle.process import CommandResult


def test_defaults_only_reproduce_the_prior_hardcoded_values():
    # STEP 14: passwords are no longer literals in source — `BundleConfig()`'s
    # in-source default is the empty "unconfigured" sentinel. Point the
    # dev-defaults layer at a directory with no such file so this test is
    # independent of whatever local file an operator may have created.
    with tempfile.TemporaryDirectory() as td, \
            patch("bundle.config.DEV_DEFAULTS_PATH", Path(td) / "no-such-file.json"):
        cfg, sources = resolve_config(cli={}, env={})
    assert cfg == BundleConfig()
    assert cfg.main_db_host == "127.0.0.1" and cfg.main_db_port == 5433
    assert cfg.main_db_user == "postgres" and cfg.main_db_password == ""
    assert cfg.results_db_port == 5432 and cfg.results_db_password == ""
    assert cfg.java_cmd == "java" and cfg.scratch_root == ""
    assert all(v == "default" for v in sources.values())


def test_dev_defaults_file_fills_password_gap_but_never_overrides_other_layers():
    # STEP 14 action 3/7: an untracked local file may supply the missing
    # password fallback (so an existing dev setup keeps working without
    # exporting env vars), but it sits *below* config-file/env/CLI, and it
    # can never override a field whose in-source default is non-empty.
    with tempfile.TemporaryDirectory() as td:
        dev_file = Path(td) / "dev-defaults.json"
        dev_file.write_text(json.dumps({
            "main_db_password": "devpass", "results_db_password": "devpass2",
            "main_db_user": "sneaky-should-be-ignored",
        }), encoding="utf-8")
        with patch("bundle.config.DEV_DEFAULTS_PATH", dev_file):
            cfg, sources = resolve_config(cli={}, env={})
            assert cfg.main_db_password == "devpass" and sources["main_db_password"] == "dev-defaults file"
            assert cfg.results_db_password == "devpass2"
            assert cfg.main_db_user == "postgres"          # non-empty in-source default wins

            # environment still beats the dev-defaults fallback
            cfg2, sources2 = resolve_config(cli={}, env={"BUNDLE_MAIN_DB_PASSWORD": "envpass"})
            assert cfg2.main_db_password == "envpass" and sources2["main_db_password"] == "environment"

        # absent file -> no fallback, password stays the empty sentinel
        with patch("bundle.config.DEV_DEFAULTS_PATH", Path(td) / "absent.json"):
            cfg3, sources3 = resolve_config(cli={}, env={})
            assert cfg3.main_db_password == "" and sources3["main_db_password"] == "default"


def test_precedence_cli_beats_environment_beats_config_file_beats_defaults():
    with tempfile.TemporaryDirectory() as td:
        cfile = Path(td) / "bundle.json"
        cfile.write_text(json.dumps({
            "main_db_host": "from-config-file",
            "main_db_port": 1111,
            "java_cmd": "from-config-file-java",
        }), encoding="utf-8")

        # config file alone overrides defaults
        cfg, src = resolve_config(cli={}, env={}, config_file=cfile)
        assert cfg.main_db_host == "from-config-file" and cfg.main_db_port == 1111
        assert cfg.java_cmd == "from-config-file-java"
        assert cfg.main_db_user == "postgres"          # untouched key keeps its default
        assert src["main_db_host"].startswith("config file")
        assert src["main_db_user"] == "default"

        # environment beats the config file
        cfg, src = resolve_config(cli={}, env={"BUNDLE_MAIN_DB_HOST": "from-env"}, config_file=cfile)
        assert cfg.main_db_host == "from-env"
        assert cfg.main_db_port == 1111                 # config-file value still wins over default
        assert src["main_db_host"] == "environment"
        assert src["main_db_port"].startswith("config file")

        # CLI beats both environment and the config file
        cfg, src = resolve_config(cli={"main_db_host": "from-cli"},
                                  env={"BUNDLE_MAIN_DB_HOST": "from-env"}, config_file=cfile)
        assert cfg.main_db_host == "from-cli"
        assert src["main_db_host"] == "CLI"
        assert cfg.java_cmd == "from-config-file-java"   # untouched by CLI/env -> config file still applies


def test_environment_layer_reads_bundle_prefixed_keys_and_coerces_types():
    cfg, src = resolve_config(cli={}, env={"BUNDLE_MAIN_DB_PORT": "7777", "BUNDLE_CORE_TIMEOUT_SECONDS": "12.5"})
    assert cfg.main_db_port == 7777 and isinstance(cfg.main_db_port, int)
    assert cfg.core_timeout_seconds == 12.5 and isinstance(cfg.core_timeout_seconds, float)
    assert src["main_db_port"] == "environment" and src["core_timeout_seconds"] == "environment"


def test_invalid_type_is_rejected_naming_the_key_and_layer():
    try:
        resolve_config(cli={}, env={"BUNDLE_MAIN_DB_PORT": "not-a-number"})
        assert False, "a non-numeric port must be rejected, not silently coerced/ignored"
    except ConfigError as exc:
        msg = str(exc)
        assert "main_db_port" in msg and "environment" in msg, msg

    try:
        resolve_config(cli={"core_timeout_seconds": "soon"})
        assert False, "a non-numeric timeout from the CLI layer must be rejected"
    except ConfigError as exc:
        msg = str(exc)
        assert "core_timeout_seconds" in msg and "CLI" in msg, msg


def test_unknown_key_is_rejected_naming_the_layer():
    with tempfile.TemporaryDirectory() as td:
        cfile = Path(td) / "bundle.json"
        cfile.write_text(json.dumps({"not_a_real_key": 1}), encoding="utf-8")
        try:
            resolve_config(cli={}, env={}, config_file=cfile)
            assert False, "an unknown config-file key must be rejected, not silently dropped"
        except ConfigError as exc:
            assert "not_a_real_key" in str(exc) and "config file" in str(exc)

    try:
        resolve_config(cli={"not_a_real_key": 1})
        assert False, "an unknown CLI override key must be rejected"
    except ConfigError as exc:
        assert "not_a_real_key" in str(exc) and "CLI" in str(exc)


def test_scratch_for_honours_explicit_root_override():
    cfg = BundleConfig(scratch_root="/srv/fw_scratch")
    assert cfg.scratch_for("mydb") == Path("/srv/fw_scratch/mydb")
    # an unset root falls back to the prior hardcoded /mnt/F-or-/tmp probe —
    # exercised indirectly via `preflight`/the default `BundleConfig()`.
    assert BundleConfig().scratch_for("mydb").name == "mydb"


def test_resolved_python_cmd_falls_back_to_this_interpreter():
    import sys
    assert BundleConfig().resolved_python_cmd() == sys.executable
    assert BundleConfig(python_cmd="/usr/bin/python3.9").resolved_python_cmd() == "/usr/bin/python3.9"


def test_resolved_config_artifact_redacts_passwords_but_keeps_everything_else():
    cfg, sources = resolve_config(cli={"main_db_password": "supersecret", "results_db_password": "alsosecret"})
    assert sources["main_db_password"] == "CLI"          # the (pre-redaction) source map stays informative
    rendered = redact(to_dict(config_to_dict(cfg, sources)))
    assert rendered["values"]["main_db_password"] == REDACTED
    assert rendered["values"]["results_db_password"] == REDACTED
    assert rendered["values"]["main_db_host"] == "127.0.0.1"   # non-secret values pass through untouched
    assert "supersecret" not in json.dumps(rendered) and "alsosecret" not in json.dumps(rendered)


def _ok(display=""):
    return CommandResult(argv=(), display=display, returncode=0, stdout="", stderr="",
                         start=0.0, end=0.0, duration=0.0, timed_out=False)


def _spec():
    return fg.parse_spec({"slots": [{"sheet": "A", "values": ["a1", "a2", "a3"]}]}, "props-render")


def test_stage_core_renders_fw_properties_from_typed_config():
    """STEP 13 action 5: Core's `fw.properties` keeps being rendered from the
    typed config — `cfg.main_db_host` reaches the JDBC URL (replacing the
    hardcoded "localhost"), and `cfg.java_cmd`/`cfg.core_timeout_seconds`
    drive the launch command, with no Core jar/DB side effects (the actual
    `java`/`psql` calls are stubbed)."""
    cfg = BundleConfig(main_db_host="cfg-core-host", main_db_user="cfg-core-user",
                       main_db_password="cfg-core-pw", java_cmd="fake-java-core", core_timeout_seconds=42)
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _ok(display=cmd if isinstance(cmd, str) else " ".join(cmd))

    def fake_psql(port, db, sql, **kw):
        captured["psql_kwargs"] = kw
        return "9", 0

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        with patch.object(stages, "run", fake_run), patch.object(stages, "psql", fake_psql):
            stages.stage_core(_spec(), scratch / "wb.xlsx", scratch, "cfgtestdb", 5433, n_opt=0, cfg=cfg)

        rendered = (scratch / "core_cwd" / "fw.properties").read_text(encoding="utf-8")
        assert "jdbc:postgresql://cfg-core-host:5433/cfgtestdb" in rendered
        # STEP 14: db.host/db.user/db.password are also rendered from cfg —
        # no template-supplied "localhost"/"postgres"/"pass" survives.
        assert "db.host=cfg-core-host" in rendered
        assert "db.user=cfg-core-user" in rendered
        assert "db.password=cfg-core-pw" in rendered

    assert "fake-java-core" in captured["cmd"] and "timeout 42 " in captured["cmd"]
    assert captured["psql_kwargs"] == {"host": "cfg-core-host", "user": "cfg-core-user", "password": "cfg-core-pw"}


class _FakeReaderPopen:
    """Stands in for `subprocess.Popen([java, -jar, READER_JAR], ...)`: drops a
    fake candidate file where the Reader would, and reports "already exited"
    so `stage_reader`'s feed-thread/wait loop returns immediately — letting
    the property-rendering and command-construction be checked without a real
    Reader jar/JVM/DB."""
    def __init__(self, argv, cwd=None, stdin=None, stdout=None, stderr=None):
        self.argv = argv
        self.stdin = io.BytesIO()
        src = Path(cwd).parent / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "candidate_0.py").write_text("# fake candidate\n", encoding="utf-8")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_stage_reader_renders_fw_properties_from_typed_config():
    """Same as above for the Reader: `cfg.main_db_host` reaches the JDBC URL,
    `cfg.java_cmd`/`cfg.reader_jar` drive the launched argv — Popen/the JVM
    are stubbed via `_FakeReaderPopen` (no real Reader jar/DB needed)."""
    cfg = BundleConfig(main_db_host="cfg-reader-host", java_cmd="fake-java-reader", reader_jar="/tmp/fake-reader.jar")

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        with patch.object(stages.subprocess, "Popen", _FakeReaderPopen):
            src, hs, n_cands, n_empty, manifest_path = stages.stage_reader(
                scratch, "cfgtestdb", "py", 5433, 5432, fw_final=1, cfg=cfg)

        assert n_cands == 1 and n_empty == 0
        rendered = (scratch / "reader_cwd" / "fw.properties").read_text(encoding="utf-8")
        assert "jdbc:postgresql://cfg-reader-host:5433/cfgtestdb" in rendered


class _FakeReaderPopenWithManifest(_FakeReaderPopen):
    """STEP 20 tiny-v2 smoke: in addition to dropping a fake candidate (via the
    parent), also dual-writes a structurally-valid Handoff v2 manifest.json at
    the path the launcher told the Reader to use
    (`reader.results.handoffManifest`), echoing back the requested
    `reader.handoff.runId` -- exactly what a real Reader's
    HandoffManifestWriter does -- so the launcher's wait/validate/cross-check
    path can be exercised without a real jar/JVM."""
    def __init__(self, argv, cwd=None, stdin=None, stdout=None, stderr=None):
        super().__init__(argv, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr)
        props = (Path(cwd) / "fw.properties").read_text(encoding="utf-8")
        rendered = dict(ln.split("=", 1) for ln in props.splitlines() if "=" in ln)
        manifest_path = Path(rendered["reader.results.handoffManifest"])
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "protocol": HANDOFF_SCHEMA,
            "run_id": rendered.get("reader.handoff.runId") or "fake-run-id",
            "language": "python",
            "candidate_transport": "loose-files",
            "candidate_count": 1,
            "id_format": "<combi_id>_0_0",
            "sources": [{"kind": "dir", "path": str(Path(cwd).parent / "src")}],
            "result_target": {"host": "127.0.0.1", "port": 5432, "database": "cfgtestdb"},
            "result_schema_mode": "placeholders=9",
            "verdict_mode": "FW_VAR",
            "shift": 1,
        }), encoding="utf-8")


def test_stage_reader_v2_manifest_smoke():
    """STEP 20 tiny-v2 run: a v2 manifest is dual-written at the path the
    launcher steers the Reader to, names the run_id the launcher asked for,
    and round-trips through the same `handoff_from_dict` validation/
    run-ID-and-count cross-check the launcher performs after Reader (see
    cli.py's reader-stage block). It then drives `stage_executor` with that
    manifest + run_id and asserts the launcher actually hands them on to the
    Executor as `-manifest`/`-runId` (the "передаёт manifest Executor" half
    of this step — not just Reader-side bookkeeping). Also confirms the
    normal v2 path leaves the legacy `fwVar.shift` untouched (no launcher
    repair on this path)."""
    cfg = BundleConfig(main_db_host="cfg-reader-host", java_cmd="fake-java-reader", reader_jar="/tmp/fake-reader.jar",
                       results_db_host="cfg-results-host", results_db_user="cfg-results-user")

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        with patch.object(stages.subprocess, "Popen", _FakeReaderPopenWithManifest):
            src, hs, n_cands, n_empty, manifest_path = stages.stage_reader(
                scratch, "cfgtestdb", "py", 5433, 5432, fw_final=1, cfg=cfg,
                run_id="bundle-run-tiny-v2", legacy_handoff=False)

        assert manifest_path == hs / "handoff/manifest.json" and manifest_path.is_file()
        manifest = handoff_from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
        assert manifest.run_id == "bundle-run-tiny-v2"          # launcher cross-check #1: run ID
        assert manifest.candidate_count == n_cands == 1         # launcher cross-check #2: count
        # normal v2 path must NOT carry the legacy never-empty-shift repair (STEP 20 action 4)
        shift = hs / "arguments/fwVar.shift"
        assert not shift.exists() or not shift.read_text().strip()

        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return CommandResult(argv=(), display="", returncode=0,
                                 stdout=("py_executor DONE: processed=1 pass=1 fail=0 broken=0 inserted=1\n"
                                         "py_executor RESULTS_V2: attempted=1 inserted=1 "
                                         "already_present=0 updated_selected=0"),
                                 stderr="", start=0.0, end=0.0, duration=0.0, timed_out=False)

        def fake_psql(port, db, sql, **kw):
            return "1 / pass 1 / fail 0", 0

        # Plan-1 Phase 3b pre-connect fencing runs at the start of stage_executor; this smoke stubs
        # the executor run, so stub the capability probe too (fencing covered in
        # test_bundle_schema_capability.py).
        with patch.object(stages, "run", fake_run), patch.object(stages, "psql", fake_psql), \
             patch.object(stages, "verify_executor_schema_capability",
                          lambda cfg, language=None: {"results_v2_schema": {"version": 2}}):
            stages.stage_executor(src, hs, "cfgtestdb", 5432, cfg=cfg,
                                  manifest_path=manifest_path, run_id="bundle-run-tiny-v2")

        cmd = captured["cmd"]
        assert "--manifest" in cmd and cmd[cmd.index("--manifest") + 1] == str(manifest_path)
        assert "--runId" in cmd and cmd[cmd.index("--runId") + 1] == "bundle-run-tiny-v2"


def test_stage_reader_legacy_handoff_smoke():
    """STEP 20 forced-legacy-fallback smoke: with the explicit compatibility
    option (`legacy_handoff=True`, i.e. `--legacy-handoff`), the launcher
    repairs the legacy never-empty `fwVar.shift` handshake file -- with a
    visible "(legacy fallback: ...)" message -- instead of waiting on a v2
    manifest (STEP 20 action 5: legacy repair lives only in the legacy path,
    with a warning)."""
    cfg = BundleConfig(main_db_host="cfg-reader-host", java_cmd="fake-java-reader", reader_jar="/tmp/fake-reader.jar")

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        with patch.object(stages.subprocess, "Popen", _FakeReaderPopen), \
                patch("builtins.print") as fake_print:
            src, hs, n_cands, n_empty, manifest_path = stages.stage_reader(
                scratch, "cfgtestdb", "py", 5433, 5432, fw_final=1, cfg=cfg,
                run_id="bundle-run-legacy", legacy_handoff=True)

        shift = hs / "arguments/fwVar.shift"
        assert shift.read_text().strip() == "1"
        assert any("legacy fallback: fixed empty fwVar.shift -> 1" in str(c.args[0])
                   for c in fake_print.call_args_list)


# ----- STEP 28: sandbox network allowlist -> validated, layered, persisted ----- #
def test_network_allowlist_targets_parsed_and_validated():
    cfg = BundleConfig(sandbox_network_allowlist="api-server, api-server:8000 ,db")
    assert cfg.network_allowlist_targets() == ("api-server", "api-server:8000", "db")
    assert BundleConfig().network_allowlist_targets() == ()              # default: none
    # invalid entries fail closed, naming the offending value
    for bad in ("bad host", "evil/../x", "has space", "-bad"):
        with pytest.raises(ConfigError):
            BundleConfig(sandbox_network_allowlist=bad).network_allowlist_targets()


def test_network_allowlist_layers_cli_over_env():
    cfg, sources = resolve_config(
        cli={"sandbox_network_allowlist": "from-cli"},
        env={"BUNDLE_SANDBOX_NETWORK_ALLOWLIST": "from-env"})
    assert cfg.sandbox_network_allowlist == "from-cli"        # CLI wins over env
    assert sources["sandbox_network_allowlist"] == "CLI"
    cfg2, src2 = resolve_config(cli={}, env={"BUNDLE_SANDBOX_NETWORK_ALLOWLIST": "svc1,svc2"})
    assert cfg2.network_allowlist_targets() == ("svc1", "svc2")
    assert src2["sandbox_network_allowlist"] == "environment"


def test_resolve_execution_policy_folds_targets_into_persisted_policy():
    """The end the launcher actually uses: config -> _resolve_execution_policy ->
    the policy VIEW that is persisted in run.json + execution_policy.json (what
    the Executor reads). The configured targets must appear there."""
    from bundle.cli import _resolve_execution_policy
    cfg, _ = resolve_config(cli={"execution_policy_profile": "networked-api-probe",
                                 "sandbox_network_allowlist": "api-server:8000,db"})
    policy, view, _auth = _resolve_execution_policy(cfg)
    assert view["policy"]["network"] == "allowlist"
    assert view["policy"]["network_allowlist"] == ["api-server:8000", "db"]
    assert policy.network_allowlist == ("api-server:8000", "db")


def test_resolve_execution_policy_rejects_targets_on_non_allowlist_profile():
    from bundle.cli import _resolve_execution_policy
    cfg, _ = resolve_config(cli={"execution_policy_profile": "generated-default",
                                 "sandbox_network_allowlist": "api-server"})
    with pytest.raises(ConfigError):
        _resolve_execution_policy(cfg)


def test_resolve_execution_policy_refuses_an_unconfigured_run():
    # Phase 02 / audit F1: nothing configured used to resolve to unsandboxed
    # trusted-local. There is now no default to fall back to.
    from bundle.cli import _resolve_execution_policy
    cfg, _ = resolve_config(cli={})
    with pytest.raises(ConfigError, match="no execution policy selected"):
        _resolve_execution_policy(cfg)


def test_resolve_execution_policy_default_has_no_targets():
    from bundle.cli import _resolve_execution_policy
    cfg, _ = resolve_config(cli={"execution_policy_profile": "generated-default"})
    policy, view, auth = _resolve_execution_policy(cfg)
    assert view["policy"]["profile"] == "generated-default"
    assert policy.network_allowlist == ()
    assert auth.sandboxed is True


# ----- STEP 30: candidate-env passthrough (e.g. TRYOUT_URL) -> persisted policy --- #
def test_candidate_env_passthrough_parsed_and_validated():
    cfg = BundleConfig(sandbox_candidate_env="TRYOUT_URL=http://app:8025, FOO=bar")
    assert cfg.candidate_env_passthrough() == {"TRYOUT_URL": "http://app:8025", "FOO": "bar"}
    assert BundleConfig().candidate_env_passthrough() == {}
    for bad in ("NOEQUALS", "1BAD=x", "BAD NAME=x"):           # malformed name/entry
        with pytest.raises(ConfigError):
            BundleConfig(sandbox_candidate_env=bad).candidate_env_passthrough()
    for secret in ("API_TOKEN=x", "DB_PASSWORD=x", "MY_SECRET=x", "AUTH_KEY=x"):
        with pytest.raises(ConfigError):                        # credential-shaped names refused
            BundleConfig(sandbox_candidate_env=secret).candidate_env_passthrough()


def test_resolve_execution_policy_folds_candidate_env_into_allowlist():
    from bundle.cli import _resolve_execution_policy
    cfg, _ = resolve_config(cli={"execution_policy_profile": "networked-api-probe",
                                 "sandbox_candidate_env": "TRYOUT_URL=http://app:8025"})
    policy, view, _auth = _resolve_execution_policy(cfg)
    assert "TRYOUT_URL" in view["policy"]["env_allowlist"]      # reaches the PERSISTED policy
    assert policy.env_allowlist[-1] == "TRYOUT_URL"


# ----- STEP 30: executor-summary.json is required + backend-checked (fail-closed) - #
def test_require_executor_summary_is_fail_closed(tmp_path):
    from bundle.cli import _require_executor_summary
    from bundle.errors import StageError
    from bundle.policy import resolve_policy
    # Audit F3: the requirement is derived from the resolved POLICY, so no call
    # site can forget it (both resume sites previously did).
    secure = resolve_policy("generated-default")
    p = tmp_path / "executor-summary.json"

    # missing summary -> stage fails (cannot confirm the sandbox backend)
    with pytest.raises(StageError):
        _require_executor_summary(p, secure)
    # invalid JSON -> stage fails
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(StageError):
        _require_executor_summary(p, secure)
    # secure policy but the run did NOT go through the container sandbox -> stage fails
    for bad in (None, "local (no namespace isolation)", "bubblewrap (ro-runtime)"):
        p.write_text(json.dumps({"sandbox_backend": bad}), encoding="utf-8")
        with pytest.raises(StageError):
            _require_executor_summary(p, secure)
    # valid secure summary -> returns the parsed summary
    p.write_text(json.dumps({"sandbox_backend": "container (rootless docker, ...)", "processed": 2}),
                 encoding="utf-8")
    assert _require_executor_summary(p, secure)["processed"] == 2
    # non-secure (required_backend=None): existence + valid JSON only, a None backend is allowed
    p.write_text(json.dumps({"sandbox_backend": None, "processed": 1}), encoding="utf-8")
    assert _require_executor_summary(p, resolve_policy("trusted-local"))["processed"] == 1
    # ...but a missing summary still fails even for a non-secure run
    with pytest.raises(StageError):
        _require_executor_summary(tmp_path / "nope.json", resolve_policy("trusted-local"))


def test_psql_is_noninteractive_and_explicit_password_wins(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs["env"]))
        return SimpleNamespace(stdout=" 1\n", returncode=0)

    monkeypatch.setenv("PGPASSWORD", "inherited-wrong-value")
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    monkeypatch.setattr(database_module, "run", fake_run)

    stdout, returncode = database_module.psql(
        5432, "postgres", "select 1;", password="configured-value"
    )

    cmd, env = calls[0]
    assert stdout == "1" and returncode == 0
    assert "--no-password" in cmd
    assert env["PGPASSWORD"] == "configured-value"
    assert env["PGCONNECT_TIMEOUT"] == "5"

    stdout, returncode = database_module.psql(
        5432, "postgres", "select 1;", password=""
    )
    cmd, env = calls[1]
    assert stdout == "1" and returncode == 0
    assert "--no-password" in cmd
    assert env["PGPASSWORD"] == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
