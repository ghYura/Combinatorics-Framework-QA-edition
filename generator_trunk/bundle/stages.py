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

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .cancel import forget_process, record_process
from .config import BundleConfig
from . import capabilities
from .optional_contract import contract_for_sheet_count
from .database import psql, sql_identifier
from .errors import ok, PreflightError, StageError
from .handoff import handoff_from_dict, HandoffError
from .process import CommandResult, run
from .jsonio import write_json_atomic
from . import shards

HERE = Path(__file__).resolve().parent.parent          # generator_trunk/
SRC = HERE.parent                                       # project root
os.environ.setdefault("BUNDLE_REPO_ROOT", str(SRC))
sys.path.insert(0, str(HERE))
import fwgen as fg                                       # noqa: E402
from sut_paths import discovered_sut_root                # noqa: E402

# Exported so the Core/Reader/Executor subprocesses inherit the SAME root this
# process resolved. It must be the *discovered* root, not a hardcoded `suts/`:
# pinning the literal here made SUT resolution depend on whether anything had
# imported this module yet, which silently disabled the sibling-checkout lookup
# for every caller that ran afterwards.
os.environ.setdefault("BUNDLE_SUT_ROOT", str(discovered_sut_root()))

CORE_JAR = SRC / "Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar"
READER_JAR = SRC / "Reader_trunk/target/CombinatoricsReader-1.0-SNAPSHOT-shaded.jar"
CORE_PROPS = HERE / "config/core.fw.properties"
READER_PROPS = HERE / "config/reader.fw.properties"
PY_EXECUTOR = SRC / "Executor_trunk/py_executor.py"   # moved out of generator_trunk/ into the Executor project
JAVA_EXECUTOR_JAR = SRC / "Executor_trunk/target/Executor-1.0-jar-with-dependencies.jar"
JAVA_JARS_DIR = SRC / "Executor_trunk/lib-src/target"


def probe_python_executor_repeat_capability(cfg: BundleConfig) -> dict:
    """Probe the configured executor without a handoff, DB connection, or candidate run."""
    executor = Path(cfg.py_executor) if cfg.py_executor else PY_EXECUTOR
    result = run([cfg.resolved_python_cmd(), str(executor), "--capabilities", "true"])
    if result.returncode != 0:
        raise StageError(f"Python Executor capability probe failed with status {result.returncode}")
    try:
        document = json.loads((result.stdout or "").strip())
        repeat = document["repeat"]
        valid = (document.get("schema") == "py_executor.capabilities/v1"
                 and repeat.get("local_metrics") is True
                 and repeat.get("raw_sample_identity") is True
                 and repeat.get("runtime_accounting") is True
                 and int(repeat.get("max_k", 0)) >= 1)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StageError(f"Python Executor returned an invalid capability document: {exc}") from exc
    if not valid:
        raise StageError(f"Python Executor lacks the required local/metrics repeat capability: {document}")
    return document


def probe_java_executor_repeat_capability(cfg: BundleConfig) -> dict:
    """Plan-1 3c: probe the configured Java Executor jar's repeat capability without a handoff, DB
    connection, or candidate run (the Java mirror of ``probe_python_executor_repeat_capability``). The
    ``-capabilities`` mode prints ``ResultsV2SchemaMigrator.capabilityDocumentJson()`` and exits 0;
    this validates the local/metrics repeat block (same keys/values py_executor advertises) the
    launcher gate requires before it will let a Java K>1 run proceed."""
    jar = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
    result = run([cfg.java_cmd, "-jar", str(jar), "-capabilities", "true"])
    if result.returncode != 0:
        raise StageError(f"Java Executor capability probe failed with status {result.returncode}")
    try:
        document = json.loads((result.stdout or "").strip())
        repeat = document["repeat"]
        valid = (document.get("schema") == "java_executor.capabilities/v1"
                 and repeat.get("local_metrics") is True
                 and repeat.get("raw_sample_identity") is True
                 and repeat.get("runtime_accounting") is True
                 and int(repeat.get("max_k", 0)) >= 1)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StageError(f"Java Executor returned an invalid capability document: {exc}") from exc
    if not valid:
        raise StageError(f"Java Executor lacks the required local/metrics repeat capability: {document}")
    return document


# Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6): the results_v2 identity the launcher
# requires an executor artifact to advertise BEFORE it is allowed to connect. Co-versioned with
# py_executor.RESULTS_V2_SCHEMA_VERSION / ResultsV2SchemaMigrator.SCHEMA_VERSION.
RESULTS_V2_SCHEMA_VERSION = 2
RESULTS_V2_SAMPLE_INDEX_NAME = "results_v2_sample_uk"
RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH = "RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH"


def verify_executor_schema_capability(cfg: BundleConfig, language) -> dict:
    """Plan-1 Phase 3b (docs/24 §1.6): BEFORE the executor connects, confirm the configured artifact
    advertises the 5-column results_v2 sample-identity writer. A genuinely-old binary cannot report
    it (its capability probe is absent / lacks the ``results_v2_schema`` block), so it is rejected
    here and never connects -- closing the window where its ``ensureSchema`` would resurrect the
    retired 3-column unique index after the cutover. Returns the parsed capability document; raises
    ``StageError`` prefixed ``RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH`` on any failure. Side-effect-free
    (no handoff, no DB connection, no candidate run)."""
    lang = normalize_language(language)
    if lang == "java":
        jar = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
        probe = run([cfg.java_cmd, "-jar", str(jar), "-capabilities", "true"])
    else:
        executor = Path(cfg.py_executor) if cfg.py_executor else PY_EXECUTOR
        probe = run([cfg.resolved_python_cmd(), str(executor), "--capabilities", "true"])
    if probe.returncode != 0:
        raise StageError(
            f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: {lang} Executor capability probe failed "
            f"(status {probe.returncode}) -- refusing to connect a binary that cannot report its "
            f"results_v2 schema capability (it could resurrect the legacy 3-column index)")
    try:
        document = json.loads((probe.stdout or "").strip())
        schema = document["results_v2_schema"]
        compatible = (int(schema["version"]) == RESULTS_V2_SCHEMA_VERSION
                      and schema["unique_index"] == RESULTS_V2_SAMPLE_INDEX_NAME
                      and schema.get("sample_identity_writer") is True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StageError(
            f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: {lang} Executor returned a capability document "
            f"without a valid results_v2_schema block ({exc}) -- refusing to connect") from exc
    if not compatible:
        raise StageError(
            f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: {lang} Executor does not advertise the version "
            f"{RESULTS_V2_SCHEMA_VERSION} 5-column sample-identity writer (got {schema}) -- refusing "
            f"to connect (it could resurrect the legacy 3-column index)")
    return document


def normalize_language(language) -> str:
    value = getattr(language, "value", language)
    normalized = str(value or "python").strip().lower()
    if normalized in ("py", ".py", "python"):
        return "python"
    if normalized in ("java", ".java"):
        return "java"
    raise StageError(f"unsupported candidate language {value!r}; expected python or java")


_KNOWN_CANDIDATE_SINKS = ("loose-files", "sharded", "grpc")


def _candidate_sink(cfg: BundleConfig) -> str:
    """The validated candidate transport this run uses. Fails closed on an unknown
    value — the Reader would silently fall back to loose-files otherwise, making a
    typo'd config change behaviour without any error."""
    sink = str(getattr(cfg, "candidate_sink", "loose-files") or "loose-files").strip()
    if sink not in _KNOWN_CANDIDATE_SINKS:
        raise StageError(f"config key 'candidate_sink': unknown transport {sink!r}; "
                         f"expected one of {list(_KNOWN_CANDIDATE_SINKS)}")
    return sink


# --------------------------------- preflight -------------------------------- #
def capability_selection(args, cfg: BundleConfig) -> "dict":
    """Project the launcher's arguments/config onto the capability registry's
    dimensions. One place translates operator input into matrix coordinates."""
    analyzer_goals = (getattr(args, "analyzer", "") or getattr(cfg, "analyzer_goals", "") or "")
    raw = {
        "language": normalize_language(getattr(args, "lang", "py")),
        "candidate_sink": _candidate_sink(cfg),
        "handoff": "legacy" if getattr(args, "legacy_handoff", False) else "v2",
        "run_mode": getattr(args, "mode", "verdict") or "verdict",
        # Empty while the policy is still unresolved: preflight runs before
        # `authorize_execution`, and a rule that depends on the policy simply does
        # not fire yet (capabilities.UNDECIDED).
        "execution_policy": (getattr(cfg, "execution_policy_profile", "") or "").strip(),
        "executor_pool": ("multi" if int(getattr(cfg, "executor_pool_size", 1) or 1) > 1
                          else "single"),
        "executor_workers": ("multi" if int(getattr(cfg, "executor_workers", 1) or 1) > 1
                             else "single"),
        "repeat": ("k_gt_1" if int(getattr(cfg, "repeat_each_candidate", 1) or 1) > 1 else "k1"),
        "repeat_policy": getattr(cfg, "repeat_policy", "local") or "local",
        "repeat_scope": getattr(cfg, "repeat_scope", "metrics") or "metrics",
        "repeat_environments": ("configured"
                                if int(getattr(cfg, "repeat_environments", 0) or 0) > 0
                                else "inactive"),
        "analyzer": (getattr(args, "analysis_mode", "exploratory") or "exploratory")
                    if analyzer_goals else "none",
        "lifecycle": getattr(args, "lifecycle", "run") or "run",
        "entrypoint": getattr(args, "entrypoint", "direct") or "direct",
    }
    return capabilities.normalize(raw)


def capability_gate(args, cfg: BundleConfig):
    """Classify this run against the capability registry and refuse an
    UNSUPPORTED combination before any side effect.

    Returns the :class:`capabilities.Verdict` so the caller can surface the
    EXPERIMENTAL codes that apply. Raises :class:`PreflightError` carrying the
    registry's stable reason code and its own message — so the matrix, the CLI
    error, the generated documentation and the GUI's disabled-option explanation
    are literally the same string.
    """
    selection = capability_selection(args, cfg)
    try:
        verdict = capabilities.classify(selection)
    except capabilities.UnknownDimensionValue as exc:
        raise PreflightError(f"UNKNOWN_CAPABILITY_VALUE: {exc}")
    blocking = verdict.blocking_code
    if blocking:
        rule = capabilities.RULES_BY_CODE[blocking]
        raise PreflightError(f"{blocking}: {rule.reason}")
    return verdict


def preflight(args, cfg: BundleConfig = BundleConfig()):
    print("[0/5] PREFLIGHT")
    # gRPC live transport (2026-07-03): validated up front, before any DB/stage exists.
    # The stream flows Reader → Java Executor, so the constraints are structural, not
    # incidental: only Java candidates (the ingestion server lives in MainWatch), only
    # the Handoff-v2 flow (the launcher adopts the Executor it started itself), and no
    # stress mode (py_stress reads loose candidate files that a grpc run never writes).
    sink = _candidate_sink(cfg)
    # Executor pool (2026-07-04): structural v1 constraints, validated before any stage.
    # The pool rides the Reader's LEGACY multi-dir round-robin, so it is loose-files-only;
    # py_executor's manifest gate demands exactly one source (java-only); K>1 repeats are
    # the in-executor single-host path (multi-env fan-out is BundleControlPlane's job).
    pool = int(getattr(cfg, "executor_pool_size", 1) or 1)
    if pool < 1 or pool > 64:
        raise PreflightError(f"executor_pool_size must be in 1..64, got {pool}")
    workers = int(getattr(cfg, "executor_workers", 1) or 1)
    if workers < 1 or workers > 64:
        raise PreflightError(f"executor_workers must be in 1..64, got {workers}")

    # Prompt 03 Part A: ONE capability registry decides which combinations run.
    # These constraints used to be a sequence of inline `if`s here plus two more
    # in `cli._run`, restated by hand in the documentation and re-asserted
    # independently by each GUI's option list. `capability_gate` raises the
    # registry's own message, so the matrix, the error, the docs and the GUI
    # cannot disagree. Unknown values fail closed.
    verdict = capability_gate(args, cfg)
    for code in verdict.codes:
        if capabilities.RULES_BY_CODE[code].level == capabilities.EXPERIMENTAL:
            print(f"  ! {code}: {capabilities.RULES_BY_CODE[code].title}")
    if pool > 1:
        ok(f"executor pool preflight OK (pool={pool}, loose-files multi-dir round-robin)")
    if sink == "grpc":
        # Audit F5: validate the RECEIVER's bind interface before any stage runs.
        # The Reader's target below is where it connects to; it never constrained
        # what the receiver listened on.
        bind_host = cfg.validate_grpc_bind_host()
        ok(f"gRPC transport preflight OK (receiver binds {bind_host}:{cfg.grpc_port} "
           f"loopback-only; Reader targets {cfg.grpc_host}:{cfg.grpc_port}; "
           f"plaintext + unauthenticated, local trusted host only)")
    core_jar = Path(cfg.core_jar) if cfg.core_jar else CORE_JAR
    reader_jar = Path(cfg.reader_jar) if cfg.reader_jar else READER_JAR
    for jar, name in ((core_jar, "Core jar"), (reader_jar, "Reader jar")):
        if not jar.exists():
            raise PreflightError(f"{name} missing: {jar}")
        ok(f"{name} present")
    if normalize_language(args.lang) == "java":
        # The Java routing constraints (stress mode, Handoff v2) are enforced by
        # capability_gate above as JAVA_REQUIRES_VERDICT / JAVA_REQUIRES_HANDOFF_V2.
        # What remains here is artifact presence, which is a host fact rather than
        # a capability-matrix fact.
        # Plan-1 3c: the Java Executor now HAS an in-sandbox metrics-harvest transport
        # (MainWatch -metricsFile -- the candidate's TAIL emits its app= line to the injected
        # `fw.metrics.out` path on the in-process path / to captured stdout on the sandbox path,
        # and MainWatch writes the corpus in the SAME _write_metrics_corpus format the Analyzer
        # parses). So Java + --analyzer is supported exactly like Python -- no fail-closed here.
        # A usecase whose candidates emit no metric line is NOT silently waved through: it fails
        # closed later at the analyzer's metrics-count invariant (an honest count mismatch).
        java_executor_jar = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
        java_jars_dir = Path(cfg.java_jars_dir) if cfg.java_jars_dir else JAVA_JARS_DIR
        if not java_executor_jar.is_file():
            raise PreflightError(
                f"Java Executor fat jar missing: {java_executor_jar} "
                f"(build Executor_trunk with 'mvn package' or configure java_executor_jar)")
        if not java_jars_dir.is_dir():
            raise PreflightError(
                f"Java dependency JAR directory missing: {java_jars_dir} "
                f"(create it or configure java_jars_dir)")
        ok("Java Executor and dependency JAR directory present")
    try:
        import pg8000  # noqa: F401
        ok("pg8000 driver present")
    except Exception:
        raise PreflightError("pg8000 missing — install: pip install --break-system-packages pg8000")
    # STEP 14 action 3/acceptance: passwords are never defaulted to a literal
    # in source — name the missing key and how to set it (env var, the
    # lowest-friction layer) rather than letting `psql`/`pg8000` fail later
    # with an opaque auth error deep inside a stage.
    for value, env_key, label in (
        (cfg.main_db_password, "BUNDLE_MAIN_DB_PASSWORD", "main DB"),
        (cfg.results_db_password, "BUNDLE_RESULTS_DB_PASSWORD", "results DB"),
    ):
        if not value:
            raise PreflightError(
                f"{label} password not configured — set {env_key} (or "
                f"--{label.split()[0]}-db-password / a config-file entry) "
                f"before running Bundle.")
    ok("DB credentials configured")
    # STEP 13: host comes from `cfg.main_db_host`/`cfg.results_db_host` — an
    # unset cfg (`BundleConfig()`) reproduces the prior hardcoded "127.0.0.1"
    # for both checks exactly.
    for port, host in ((args.main_port, cfg.main_db_host), (args.results_port, cfg.results_db_host)):
        if run(["pg_isready", "-h", host, "-p", str(port)]).returncode != 0:
            raise PreflightError(
                f"PostgreSQL not accepting on {host}:{port}. Start it, e.g.:\n"
                f"      sudo pg_ctlcluster 18 main start   (and ... my_second_instance start)")
        ok(f"PostgreSQL {host}:{port} up")
    tomls = sorted(Path(args.spec_dir).glob("*.toml"))
    if len(tomls) != 1:
        raise PreflightError(f"expected exactly one .toml in {args.spec_dir}, found {len(tomls)}")
    spec = fg.load_spec(tomls[0])
    ok(f"spec '{spec.name}' ({len(spec.slots)} slots)")
    # STEP 13/14: scratch-root policy lives in `BundleConfig.scratch_for` —
    # default is `/tmp/fw_work/<db>`; `/mnt/F` (or anything else) is only
    # used if `cfg.scratch_root` (CLI/env/config-file) names it explicitly
    # (action 4: "/mnt/F — configured optional candidate, not implicit default").
    scratch = cfg.scratch_for(args.db)
    scratch.mkdir(parents=True, exist_ok=True)
    ok(f"scratch {scratch}")
    return spec, tomls[0], scratch


def _check_prop_value(key: str, value) -> str:
    """Reject a properties value that would not stay a single value.

    ``.properties`` is line-oriented, so a value containing a line break
    silently becomes a second, independent property — an arbitrary key nobody
    asked to set. A leading ``#`` or ``!`` is comment syntax and would make the
    setting vanish instead. Today's only password source is
    ``secrets.token_hex``, which can produce neither, so this closes a latent
    path rather than a live one: it matters the moment a config file, an env
    var or another credential source supplies a raw value.
    """
    text = str(value)
    if "\n" in text or "\r" in text:
        raise StageError(
            f"properties value for '{key}' contains a line break; it would be "
            f"written as a separate property line")
    if text[:1] in ("#", "!"):
        raise StageError(
            f"properties value for '{key}' starts with '{text[:1]}', which "
            f".properties reads as a comment marker")
    return text


def _props(template: Path, edits: dict, out: Path):
    edits = {k: _check_prop_value(k, v) for k, v in edits.items()}
    text = template.read_text(encoding="utf-8")
    lines = []
    seen = set()
    for ln in text.splitlines():
        key = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if key in edits:
            lines.append(f"{key}={edits[key]}"); seen.add(key)
        else:
            lines.append(ln)
    for k, v in edits.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # fw.properties carries the database password in cleartext, so it gets the
    # same owner-only treatment as the deploy `.env`. Best-effort: a filesystem
    # without POSIX modes must not fail the run.
    try:
        out.chmod(0o600)
    except OSError:
        pass


# ----------------------------------- stages --------------------------------- #
def stage_gen(spec_dir, scratch):
    print("\n[1/5] GENERATE workbook (fwgen)")
    out = scratch / "wb"
    r = run([sys.executable, str(HERE / "fwgen_cli.py"), "gen", "--specs", str(spec_dir), "--out", str(out)])
    xlsx = sorted(out.glob("*.xlsx"))
    if r.returncode != 0 or not xlsx:
        print(r.stdout, r.stderr)
        raise StageError("fwgen gen failed")
    ok(f"workbook -> {xlsx[0].name}")
    return xlsx[0]


def stage_core(spec, xlsx, scratch, db, port, n_opt=0, cfg: BundleConfig = BundleConfig(),
               optional_contract=None):
    print("\n[2/5] CORE — fill main DB")
    cwd = scratch / "core_cwd"; cwd.mkdir(exist_ok=True)
    # STEP 13 action 5: properties keep being rendered from the typed config —
    # `cfg.main_db_host` (default "127.0.0.1") replaces the hardcoded "localhost"
    # in the JDBC URL; jar/template/timeout/java-cmd are likewise cfg-overridable
    # while an unset cfg reproduces the prior hardcoded values exactly.
    edits = {"excel.file": str(xlsx), "db.name": db, "db.port": port,
             "hibernate.connection.url": f"jdbc:postgresql://{cfg.main_db_host}:{port}/{db}",
             "db.host": cfg.main_db_host, "db.user": cfg.main_db_user, "db.password": cfg.main_db_password,
             "db.preEraseDB": "true", "isLaunchReader": "false"}
    # Audit F4: the producer property is rendered FROM the canonical optional-table
    # contract, which the Reader's consumer property is rendered from too. Before
    # this both were derived independently from `n_opt` -- correct, but nothing
    # stated or checked the R ⊆ P relationship the two properties must satisfy.
    if optional_contract is not None:
        edits.update(optional_contract.core_edits())
    elif n_opt > 0:      # legacy call path: complete 1..N, same values as the contract
        edits.update(contract_for_sheet_count(n_opt).core_edits())
    core_props = Path(cfg.core_props) if cfg.core_props else CORE_PROPS
    core_jar = Path(cfg.core_jar) if cfg.core_jar else CORE_JAR
    _props(core_props, edits, cwd / "fw.properties")
    log = scratch / "core.log"
    timeout = int(cfg.core_timeout_seconds)
    r = run(f'timeout {timeout} {cfg.java_cmd} -jar "{core_jar}" </dev/null >"{log}" 2>&1', cwd=str(cwd))
    cnt, rc = psql(port, db, "select count(*) from fw_final;",
                   host=cfg.main_db_host, user=cfg.main_db_user, password=cfg.main_db_password)
    est = fg.estimate_core_combos(spec)
    if rc != 0 or not cnt.isdigit():
        raise StageError(f"Core did not fill :{port}/{db} (see {log})")
    ok(f"fw_final = {cnt}  (fwgen est {est}{'  MATCH' if cnt == str(est) else '  — note: rich verbs make est approximate'})")
    return int(cnt)


def stage_draw(spec, scratch, cfg: BundleConfig = BundleConfig(), *, exact=False, db=None, main_port=None):
    """[1.5/5] DRAW — the interactive 'draw the links' face. Serve the single-file editor, open it
    in Firefox, and BLOCK until the user presses Submit; whatever they drew (forbidden/required
    value bonds, gates, n-ary, `when` formulas) comes back as a sidecar that REPLACES the spec's
    constraints/params before the sieve runs. Submitting an empty canvas is valid — the sieve then
    removes nothing ('as if --sieve was off'). Returns ``(constraints, params)``.

    OPTION `exact=True` (runs AFTER Core, with `db`/`main_port`): the editor shows EXACT live impact
    over the whole assembled space `fw_final × (1 + Σ|fw_optX|)` — honest about optional bonds — by
    POSTing each change to a local `/impact` endpoint backed by `sieve.exact_impact`. Default
    (offline, before Core) keeps the fast in-browser estimate."""
    print(f"\n[1.5/5] DRAW — open the link editor (forbid = red, require = green), then press Submit"
          f"{'  [exact impact: live from fw_final × fw_optX]' if exact else ''}")
    sys.path.insert(0, str(HERE / "constraints"))
    import serve  # noqa: E402  (stdlib http.server + the zero-dep single-file editor)
    sheets = {}
    optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
    for s in spec.slots:
        vals = [str(v).strip() for v in s.values]
        if len(vals) >= 2:                              # HEAD/TAIL harness slots aren't bondable dims
            sheets[s.sheet] = vals
    if not sheets:
        print("    (no sheets with >=2 values — nothing to bond; skipping the editor)")
        return spec.constraints, spec.params
    initial = {"version": 1, "params": spec.params, "constraints": spec.constraints}
    if getattr(spec, "orders", None):
        initial["orders"] = spec.orders          # only when present — keeps the no-orders shape unchanged
    impact_fn = None
    if exact and db:
        import pg8000.dbapi
        import threading as _th
        import sieve as sv  # noqa: E402
        port = main_port if isinstance(main_port, int) else cfg.main_db_port
        conn = pg8000.dbapi.connect(host=cfg.main_db_host, port=port,
                                    user=cfg.main_db_user, password=cfg.main_db_password, database=db)
        try:
            code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
            cur = conn.cursor()
            cur.execute("select table_name from information_schema.tables where table_name like 'fw_opt%';")
            opt_tables = sorted(r[0] for r in cur.fetchall())
            cur.close()
            # decode fw_final/fw_optX ONCE, then drop the DB connection — the live preview reuses the
            # cached rows (no per-change DB read; the tables don't change during the draw session).
            finals, opts = sv.decode_assembly(conn, "fw_final", code2val, order, combos_col,
                                              baseline, optional_sheets, opt_tables)
        finally:
            conn.close()
        _lock = _th.Lock()

        def impact_fn(sidecar):                         # serialized, DB-free: pure compute over cached rows
            with _lock:
                return sv.impact_over_rows(finals, opts, sidecar, optional_sheets)
    result = serve.serve_editor(sheets, initial, title=f"Bundle — {spec.name}",
                                lang=(getattr(cfg, "editor_lang", "") or "ru"),
                                browser=(getattr(cfg, "editor_browser", "") or "firefox"),
                                impact_fn=impact_fn, optional_sheets=optional_sheets)
    if result is None:
        print("    (editor closed without Submit — proceeding with the spec's existing constraints)")
        return spec.constraints, spec.params
    cons = result.get("constraints", []) or []
    pars = result.get("params", spec.params) or spec.params
    Path(scratch).mkdir(parents=True, exist_ok=True)
    (Path(scratch) / "sidecar.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
    n_forbid = sum(1 for c in cons if c.get("polarity", "forbid") == "forbid")
    n_req = sum(1 for c in cons if c.get("polarity") == "require")
    ok(f"draw: received {len(cons)} bond(s) — {n_forbid} forbid, {n_req} require "
       f"(sidecar.json saved); the sieve will apply them")
    return cons, pars


def stage_sieve(spec, scratch, db, main_port, fw_final, cfg: BundleConfig = BundleConfig()):
    print("\n[2.5/5] SIEVE — apply the constraint sidecar to fw_final (between Core and Reader)")
    if not getattr(spec, "constraints", None):
        print("    (spec has no constraints — skipping)")
        return fw_final
    import pg8000.dbapi
    sys.path.insert(0, str(HERE / "constraints"))
    import sieve as sv
    sidecar = {"version": 1, "params": spec.params, "constraints": spec.constraints}
    if getattr(spec, "orders", None):
        sidecar["orders"] = spec.orders
    fg.emit_sidecar(spec, scratch / "sidecar.json")     # a copy for the record / standalone re-run
    # STEP 13/14: main-DB host/user/password come from the typed config, not
    # inline literals — no hardcoded credential remains in source; an
    # unconfigured password fails closed in `preflight` before this runs.
    conn = pg8000.dbapi.connect(host=cfg.main_db_host, port=main_port, user=cfg.main_db_user,
                                password=cfg.main_db_password, database=db)
    code2val, baseline, combos_col, order = sv.build_maps_from_db(conn, "fw_final", spec.slots)
    optional_sheets = {s.sheet for s in spec.slots if "FW_Optional" in s.flags}
    for c in spec.constraints:
        print("    rule:", sv.describe(c))
    rep = sv.sieve_fw_final(conn, "fw_final", sidecar, code2val, order, combos_col,
                            id_col="combi_id", baseline=baseline, dry_run=False,
                            optional_sheets=optional_sheets)
    # A bond touching an FW_Optional sheet can't be enforced on the factored fw_final, so compile
    # the DEFERRED ones into compact code-tuple specs; the Reader evaluates them PER assembled
    # candidate during cartesian assembly (scalable — size O(bonds), not the candidate count).
    # Use _referenced_sheets, not only _constraint_sheets: a mandatory target gated by an optional
    # condition still depends on the assembled optional value and cannot be applied to fw_final.
    deferred_cons = [c for c in spec.constraints if optional_sheets & set(sv._referenced_sheets(c))]
    if deferred_cons and rep.get("deferred"):
        domain_values = {s.sheet: [str(v).strip() for v in s.values] for s in spec.slots}
        compiled = sv.optional_bond_compile_report(deferred_cons, spec.params, code2val, combos_col,
                                                   order, optional_sheets, domain_values)
        blockers = compiled.get("blockers", [])
        if blockers:
            detail = "; ".join(
                f"{b['id']} ({','.join(b.get('features') or ['plain'])}) on {b.get('optional_sheets')}: {b.get('reason')}"
                for b in blockers)
            raise StageError(
                "FW_Optional deferred bonds could not be compiled for the Reader OptionalBondFilter; "
                f"refusing to continue with silently unenforced constraints: {detail}")
        bond_lines = compiled.get("lines", [])
        if bond_lines:
            bonds_path = Path(scratch) / "optional_bonds.txt"
            bonds_path.write_text("\n".join(bond_lines) + "\n", encoding="utf-8")
            print(f"      optional bonds → {len(bond_lines)} compiled bond spec(s) for the Reader "
                  f"to enforce at assembly → {bonds_path.name}")
    conn.close()
    # STEP 35: the actual sieve records the SAME statistics the dry-run reports.
    for rid, n in rep["matched"].items():
        print(f"      rule {rid}: matched {n} row(s)")
    for w in rep.get("warnings", []):
        print(f"      WARNING: {w}")
    if rep["overlap"]:
        print(f"      overlap: {rep['overlap']} row(s) removed by >1 rule")
    kept = rep["retained"]
    ok(f"sieve: scanned {rep['scanned']}, unique removals {rep['unique_removals']} "
       f"(overlap {rep['overlap']}) → fw_final now {kept}")
    return kept


def _constraint_key(c: dict) -> str:
    return json.dumps(c, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stage_seed_bias(spec, scratch, db, main_port, seed_from, cfg: BundleConfig = BundleConfig()):
    print("\n[2.25/5] SEED-BIAS — derive sieve constraints from the previous BundleSeed")
    seed_path = Path(seed_from)
    if seed_path.is_dir():
        seed_path = seed_path / "bundle_seed.json"
    if not seed_path.exists():
        raise StageError(f"seed-from {seed_path}: bundle_seed.json not found")
    import pg8000.dbapi
    sys.path.insert(0, str(HERE / "constraints"))
    import sieve as sv
    from . import seedbias

    conn = pg8000.dbapi.connect(host=cfg.main_db_host, port=main_port, user=cfg.main_db_user,
                                password=cfg.main_db_password, database=db)
    try:
        seed = seedbias.load_seed_with_sha(seed_path)
        rows = seedbias.decode_winner_rows(conn, spec, seed.get("winners") or [])
        plan = seedbias.build_bias_plan(
            spec, rows, seed,
            exploration_floor=cfg.exploration_floor,
            min_winner_support=cfg.min_winner_support)
    except seedbias.DegenerateBiasPlan as exc:
        seed_for_hash = seedbias.load_seed_with_sha(seed_path)
        refusal = {
            "schema": seedbias.BIASPLAN_SCHEMA,
            "status": "CONVERGED_NO_SIGNAL",
            "reason": str(exc),
            "source_seed_sha256": seed_for_hash.get("_source_seed_sha256"),
            "exploration_floor": cfg.exploration_floor,
            "min_winner_support": cfg.min_winner_support,
        }
        plan_path = Path(scratch) / "bias_plan.json"
        write_json_atomic(plan_path, refusal)
        print(f"    seed-bias: {exc}; wrote no derived constraints -> {plan_path.name}")
        return {
            "constraints": list(getattr(spec, "constraints", []) or []),
            "params": spec.params,
            "plan_path": plan_path,
            "sidecar_path": None,
            "seed_path": seed_path,
            "seed_sha256": refusal["source_seed_sha256"],
            "excluded_values": 0,
            "post_bias_estimate": None,
            "pre_bias_estimate": None,
            "deduped_constraints": 0,
            "degenerate": True,
            "reason": str(exc),
        }
    except seedbias.SeedBiasError as exc:
        raise StageError(f"seed-from {seed_path}: {exc}") from exc
    finally:
        conn.close()

    sidecar = seedbias.plan_to_sidecar(plan)
    if getattr(spec, "orders", None):
        sidecar["orders"] = spec.orders
    sidecar["params"] = spec.params
    try:
        sv.validate_sidecar(sidecar, strict=True)
    except ValueError as exc:
        raise StageError(f"derived seed-bias sidecar failed strict sieve validation: {exc}") from exc

    human = list(getattr(spec, "constraints", []) or [])
    merged = list(human)
    seen = {_constraint_key(c) for c in human}
    deduped = 0
    for c in plan.derived_constraints:
        key = _constraint_key(c)
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        merged.append(c)
    plan_path = Path(scratch) / "bias_plan.json"
    sidecar_path = Path(scratch) / "derived_sidecar.json"
    seedbias.write_plan(plan, plan_path)
    write_json_atomic(sidecar_path, sidecar)
    excluded_values = sum(len(s.excluded_values) for s in plan.per_sheet.values())
    print(f"    seed-bias: excluded {excluded_values} value(s) across "
          f"{sum(1 for s in plan.per_sheet.values() if s.excluded_values)} sheet(s); "
          f"estimated keep {plan.est_keep_fraction:.3f} -> {plan.est_post_bias_candidates} candidate(s)")
    if deduped:
        print(f"    seed-bias: deduped {deduped} derived constraint(s) already present in human/spec constraints")
    return {
        "constraints": merged,
        "params": spec.params,
        "plan_path": plan_path,
        "sidecar_path": sidecar_path,
        "seed_path": seed_path,
        "seed_sha256": plan.source_seed_sha256,
        "excluded_values": excluded_values,
        "post_bias_estimate": plan.est_post_bias_candidates,
        "pre_bias_estimate": plan.full_space_estimate,
        "deduped_constraints": deduped,
        "degenerate": False,
        "reason": "",
    }


# ---------------------- gRPC live transport (2026-07-03) --------------------- #
# In grpc mode the data flows LIVE (Reader streams, Executor ingests), so the
# Executor must be RUNNING before the Reader launches (the Reader's GrpcCandidateSink
# preflights the connection and aborts otherwise) and must keep running after the
# Reader exits (processing drains asynchronously; MainWatch self-exits via its
# -exitWhenComplete grpc drain condition). The reader stage starts it and registers
# the handle here; the executor stage adopts it, waits for the drain-exit, and reads
# the same executor-summary.json contract the file transports use.
_GRPC_EXECUTORS: "dict[str, dict]" = {}


def _grpc_registry_key(work) -> str:
    return str(Path(work).resolve())


def _start_grpc_executor(work, src, hs, cfg: BundleConfig, run_id=None):
    """Spawn the Java Executor with the gRPC ingestion server and wait until it
    LISTENS (fail closed otherwise — the Reader would abort at preflight anyway,
    this just gives the operator the real cause). Registers the process for
    `bundle cancel` and in the module registry for the executor stage to adopt."""
    java_executor = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
    java_jars = Path(cfg.java_jars_dir) if cfg.java_jars_dir else JAVA_JARS_DIR
    if not java_executor.is_file():
        raise StageError(f"Java Executor fat jar missing: {java_executor}")
    if not java_jars.is_dir():
        raise StageError(f"Java dependency JAR directory missing: {java_jars}")
    work = Path(work)
    log = work / "executor.log"
    jvm_props = []
    compiler = (getattr(cfg, "executor_compiler", "") or "").strip().lower()
    if compiler:
        if compiler not in ("adaptive", "janino", "ecj", "javac"):
            raise StageError(
                f"invalid executor_compiler {compiler!r}; expected adaptive, janino, ecj, or javac")
        jvm_props.append(f"-Dfw.exec.compiler={compiler}")
    # STEP 29 interplay: the live-feed Executor starts BEFORE the Reader, so no manifest
    # (and thus no execution policy document) exists at its launch — it runs under the
    # explicit trusted-local legacy opt-in. cli._run fails closed unless the resolved
    # execution policy profile is trusted-local, so this flag never widens a secure run.
    jvm_props.append("-Dfw.exec.trusted=true")
    cmd = [
        cfg.java_cmd, *jvm_props, "-jar", str(java_executor),
        "-srcDirList", str(src),
        "-dirJars", str(java_jars),
        "-dirResultsDbURL", str(hs / "resultsDbURL"),
        "-dirSqlTemplate", str(hs / "sqlTemplate"),
        "-dirArguments", str(hs / "arguments"),
        "-dirRunFirstOnce", str(hs / "runFirstOnce"),
        "-out2", str(work),
        "-grpcPort", str(cfg.grpc_port),
        # Audit F5: bind an EXPLICIT loopback interface. The Reader targeting
        # 127.0.0.1 never constrained what the receiver listened on.
        "-grpcBindHost", str(cfg.grpc_bind_host),
        "-attempt", "1",
        "-failOnly", "false",
        "-exitWhenComplete", "true",
        "--writeToDB", "true",
        "-metricsFile", str(work / "metrics.kv"),
    ]
    if run_id:
        cmd += ["-runId", str(run_id)]
    cmd += _java_repeat_executor_flags(cfg, run_id)
    (work / "executor-summary.json").unlink(missing_ok=True)
    lf = open(log, "wb")
    proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
    lf.close()   # the child owns the fd now
    if (work / "run.json").is_file():
        record_process(work, "executor", proc)
    deadline = time.time() + 60
    listening = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            if "gRPC candidate ingestion LISTENING" in log.read_text(encoding="utf-8", errors="replace"):
                listening = True
                break
        except OSError:
            pass
        time.sleep(0.5)
    if not listening:
        _abort_grpc_executor_proc(work, proc)
        tail = ""
        try:
            tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
        except (OSError, IndexError):
            pass
        raise StageError(f"gRPC Executor did not start listening on port {cfg.grpc_port} "
                         f"within 60s (see {log}){': ' + tail if tail else ''}")
    _GRPC_EXECUTORS[_grpc_registry_key(work)] = {"proc": proc, "log": log, "port": cfg.grpc_port}
    ok(f"gRPC Executor up (pid {proc.pid}, port {cfg.grpc_port}) — awaiting the Reader's live stream")
    return proc


def _abort_grpc_executor_proc(work, proc) -> None:
    try:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    except Exception:
        pass
    finally:
        if (Path(work) / "run.json").is_file():
            forget_process(Path(work), proc.pid)


def abort_grpc_executor(work) -> None:
    """Kill + deregister the background gRPC Executor after a failure in the reader
    stage (or between stages) so a broken run never leaks a listening JVM."""
    handle = _GRPC_EXECUTORS.pop(_grpc_registry_key(work), None)
    if handle:
        _abort_grpc_executor_proc(work, handle["proc"])


def stage_reader(scratch, db, lang, main_port, results_port, fw_final, n_opt=0, full=None, stress=False,
                 cfg: BundleConfig = BundleConfig(), run_id=None, legacy_handoff=False, policy_ref=None,
                 resume=False, optional_contract=None):
    print("\n[3/5] READER — reassemble candidates + handshake + Results DB")
    cwd = scratch / "reader_cwd"; cwd.mkdir(exist_ok=True)
    src = scratch / "src"; src.mkdir(exist_ok=True)
    # Executor pool (2026-07-04): one candidate dir PER MEMBER, filled by the Reader's
    # legacy round-robin (outZipDirPathList CSV → LooseFileSink dir rotation). The Handoff
    # manifest then declares one source per dir, and each pool member owns source[i].
    pool = int(getattr(cfg, "executor_pool_size", 1) or 1)
    member_dirs = [src / f"e{i}" for i in range(pool)] if pool > 1 else []
    # STEP 32 action 5: on a sharded resume rerun, KEEP the valid shards already in src so the
    # ShardSink (reader.out.shard.resume=true) reuses them instead of rebuilding the corpus.
    if not resume:
        for f in sorted(src.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
    for d in member_dirs:
        d.mkdir(exist_ok=True)
    hs = scratch / "handshake"
    for d in ("resultsDbURL", "sqlTemplate", "runFirstOnce", "arguments"):
        (hs / d).mkdir(parents=True, exist_ok=True)
    lang_norm = normalize_language(lang)
    ext = {"python": ".py", "java": ".java"}[lang_norm]
    # Reader can place a separator between assembled cell fragments. Python code
    # snippets need a statement boundary even when TOML raw values do not carry a
    # trailing newline; Java Properties.load turns the two-character "\n" into
    # an actual newline byte for FW_B_ARR. Keep Java on the historical empty
    # concatenator because some Java specs intentionally split tokens tightly.
    reader_concatenator = "\\n" if lang_norm == "python" else ""
    edits = {
        "db.name": db, "db.port": main_port, "db.preEraseDB": "false",
        "hibernate.connection.url": f"jdbc:postgresql://{cfg.main_db_host}:{main_port}/{db}",
        # The Reader reads the Core sheets via Hibernate (SheetNameDaoImpl), whose
        # connection uses these keys -- NOT db.user/db.password (those drive the raw
        # JDBC path). They must be rendered from the typed config too, exactly like
        # db.user/db.password below: once STEP 14 stripped the hardcoded credential
        # out of the template, an un-overridden hibernate.connection.password keeps a
        # stale template value and the sheet read fails closed ("Connections could not
        # be acquired" -> SessionFactory null). Mirror the main-DB credential here.
        "hibernate.connection.user": cfg.main_db_user, "hibernate.connection.password": cfg.main_db_password,
        "db.host": cfg.main_db_host, "db.user": cfg.main_db_user, "db.password": cfg.main_db_password,
        "results.db.host": cfg.results_db_host, "results.db.user": cfg.results_db_user,
        "results.db.password": cfg.results_db_password,
        "results.db.port": results_port, "results.db.tablespace": "pg_default",
        "reader.core.concatenator": reader_concatenator,
        "reader.out.zipMode": "false", "reader.out.filesMode": "true",
        "reader.out.fileExtension": ext, "reader.cells.preserveWhitespace": "true",
        "reader.javacode.refineInDB": "false", "fw.analyzer.enabled": "false",
        "reader.generalTimeoutToStop": "5",
        "reader.out.outZipDirPathList": (",".join(f"{d}/" for d in member_dirs)
                                         if member_dirs else f"{src}/"),
        "reader.out.outFilePathAndName": str(scratch / "FW_out.tsv"),
        "reader.results.db.configFile": str(hs / "resultsDbURL/resultsDbURL.properties"),
        "reader.results.db.sqlInsertTemplateFile": str(hs / "sqlTemplate/insert.sql"),
        "reader.results.firstRunOnce": str(hs / "runFirstOnce/runmefirstonce.first"),
        "reader.results.arguments": str(hs / "arguments/args"),
        # STEP 20: keep the dual-written Handoff v2 manifest inside the
        # handshake the launcher controls, so it can find it after the Reader
        # exits, instead of the JVM-default scratch root.
        "reader.results.handoffManifest": str(hs / "handoff/manifest.json"),
    }
    # STEP 32: propagate the selected candidate transport into the Reader's fw.properties.
    # "loose-files" (default) is the legacy byte-for-byte path; "sharded" makes the Reader
    # emit compressed *.fwshard containers (ShardSink) instead of one file per candidate;
    # "grpc" (2026-07-03) makes the Reader STREAM candidates live to the Executor's gRPC
    # ingestion server (started below, before the Reader launches).
    grpc_mode = _candidate_sink(cfg) == "grpc"
    if grpc_mode and lang_norm != "java":
        raise StageError("candidate_sink=grpc requires Java candidates (--lang java)")
    edits["reader.out.candidateSink"] = getattr(cfg, "candidate_sink", "loose-files")
    if grpc_mode:
        edits["reader.out.grpc.target"] = f"{cfg.grpc_host}:{cfg.grpc_port}"
    edits["reader.out.shard.maxRecords"] = str(getattr(cfg, "shard_max_records", 1000))
    edits["reader.out.shard.maxBytes"] = str(getattr(cfg, "shard_max_bytes", 8 * 1024 * 1024))
    edits["reader.out.shard.resume"] = "true" if resume else "false"
    if run_id:
        edits["reader.handoff.runId"] = run_id
    if policy_ref:
        # STEP 27: tell the Reader which execution policy this candidate set runs
        # under, so it can stamp execution_policy_ref into the Handoff v2 manifest.
        # Forward-compatible: a Reader that doesn't yet read this property ignores
        # it, and the launcher records/overlays the policy id independently anyway.
        edits["reader.handoff.executionPolicyRef"] = policy_ref
    # Audit F4: same contract object as stage_core rendered its producer list
    # from, so R ⊆ P holds by construction rather than by convention.
    if optional_contract is not None:
        edits.update(optional_contract.reader_edits())
    elif n_opt > 0:      # legacy call path: complete 1..N
        edits.update(contract_for_sheet_count(n_opt).reader_edits())
    else:
        edits["reader.core.processIsOpt"] = "false"
    # If the sieve compiled deferred optional bonds, point the Reader at them so it enforces them
    # per assembled candidate during cartesian assembly. Absent => Reader no-op (zero overhead).
    bonds_file = Path(scratch) / "optional_bonds.txt"
    if bonds_file.is_file():
        edits["reader.constraints.bondsFile"] = str(bonds_file)
    if stress:
        # Storm mode accumulates-then-bursts via a worker POOL, so the single-machine
        # interpreter-pacing that justifies the file-generation ramp no longer applies:
        # saturate the cloud as fast as the invariant (initial>intermediate>delay) allows.
        edits.update({
            "reader.out.fileGenerationInitialDelay": "5",
            "reader.out.fileGenerationIntermediateDelay": "3",
            "reader.out.fileGenerationDelay": "1",
            "reader.out.fileGenerationDelay.rampUp00": "2",
            "reader.out.fileGenerationDelay.rampUp00.delta": "1",
            "reader.out.fileGenerationDelay.rampUp0": "1",
            "reader.out.fileGenerationDelay.rampUp0.delta": "1",
        })
    reader_props = Path(cfg.reader_props) if cfg.reader_props else READER_PROPS
    reader_jar = Path(cfg.reader_jar) if cfg.reader_jar else READER_JAR
    _props(reader_props, edits, cwd / "fw.properties")
    log = scratch / "reader.log"
    # STEP 25: the Reader JVM is the one long-lived owned subprocess this
    # launcher spawns -- recording it (run-directory mode only; `scratch` is
    # the shared legacy tree otherwise, with no run.json to key a registry to)
    # is what lets a *separate* `bundle cancel` invocation find, identity-
    # check, and terminate it later instead of leaving it running orphaned.
    has_run_dir = (scratch / "run.json").is_file()
    try:
        # gRPC live transport: the ingestion Executor must be UP before the Reader
        # (its GrpcCandidateSink preflights the connection and aborts otherwise).
        # Registered in _GRPC_EXECUTORS; the executor stage adopts + drains it.
        if grpc_mode:
            _start_grpc_executor(scratch, src, hs, cfg, run_id=run_id)
        # delayed y/y/no fed from Python (no shell / no fd-leak): keep stdin open until the
        # Reader graceful-stops, then close. Returns the instant the Reader exits.
        with open(log, "wb") as lf:
            proc = subprocess.Popen([cfg.java_cmd, "-jar", str(reader_jar)], cwd=str(cwd),
                                    stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT)
            if has_run_dir:
                record_process(scratch, "reader", proc)

            def feed():
                try:
                    for tok, wait in ((b"y\n", 6), (b"y\n", 3), (b"no\n", 0)):
                        proc.stdin.write(tok); proc.stdin.flush()
                        if wait:
                            time.sleep(wait)
                    while proc.poll() is None:        # hold stdin open while it runs
                        time.sleep(0.5)
                except Exception:
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass

            t = threading.Thread(target=feed, daemon=True); t.start()
            try:
                proc.wait(timeout=cfg.reader_timeout_seconds)
            except subprocess.TimeoutExpired:
                proc.kill()
            t.join(timeout=2)
            if has_run_dir:
                forget_process(scratch, proc.pid)
        # STEP 32: the candidate transport flows through the Reader's fw.properties
        # (reader.out.candidateSink). When it emitted compressed shards (*.fwshard), count
        # the candidate RECORDS across valid finalized shards instead of loose *<ext> files.
        # For the grpc transport nothing lands on disk: the authoritative count is the
        # Reader-emitted Handoff manifest's candidate_count (the sink's tally, already
        # reconciled fail-closed against the Executor's stream receipt — the Reader refuses
        # to write the manifest at all on a receipt mismatch or any send error).
        if grpc_mode:
            grpc_manifest = hs / "handoff/manifest.json"
            try:
                n_cands = int(json.loads(grpc_manifest.read_text(encoding="utf-8"))["candidate_count"])
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise StageError(
                    f"gRPC transport: the Reader did not produce a valid Handoff manifest — "
                    f"the live stream did not reconcile (see {log}): {exc}")
            empty = 0
            if n_cands == 0:
                raise StageError(f"Reader streamed 0 candidates over gRPC (see {log})")
            ok(f"candidates = {n_cands} (grpc → streamed live to {edits['reader.out.grpc.target']}; "
               f"Executor receipt reconciled by the Reader; expected {full or fw_final})")
        elif shards.has_shards(src):
            n_cands = shards.count_candidates(src)
            empty = 0
            if n_cands == 0:
                raise StageError(f"Reader emitted 0 candidates from shards (see {log})")
            ok(f"candidates = {n_cands} (sharded, {len(shards.list_finalized_shards(src))} shard(s); "
               f"expected {full or fw_final})")
        else:
            # pool mode: candidates live one level down (src/e<i>/*.ext); both globs
            # together stay correct for the single-dir layout too.
            cands = sorted(src.glob(f"*{ext}")) + sorted(src.glob(f"*/*{ext}"))
            empty = sum(1 for c in cands if c.stat().st_size == 0)
            if not cands:
                raise StageError(f"Reader emitted 0 candidates (see {log})")
            n_cands = len(cands)
            if member_dirs:
                split = [sum(1 for _ in d.glob(f"*{ext}")) for d in member_dirs]
                ok(f"candidates = {n_cands}{ext} across {pool} member dir(s) {split}  "
                   f"(expected {full or fw_final}; empty {empty})")
            else:
                ok(f"candidates = {n_cands}{ext}  (expected {full or fw_final}; empty {empty})")
    except BaseException:
        # A failed reader stage must never leak a listening Executor JVM.
        if grpc_mode:
            abort_grpc_executor(scratch)
        raise
    insert = hs / "sqlTemplate/insert.sql"
    shift = (hs / "arguments/fwVar.shift")
    if legacy_handoff:
        # STEP 20: this repair now belongs to the legacy compatibility path only
        # — the normal Handoff v2 path relies on the Reader-emitted manifest,
        # whose `shift` field validate_handoff() refuses to leave empty (P6).
        if not shift.exists() or not shift.read_text().strip():
            shift.write_text("1\n")
            print("    (legacy fallback: fixed empty fwVar.shift -> 1)")
    if insert.exists():
        ok(f"handshake ready (insert.sql has {insert.read_text().count('?')} '?', fwVar.shift={shift.read_text().strip() or '(unset, v2 manifest authoritative)'})")
    manifest_path = hs / "handoff/manifest.json"
    return src, hs, n_cands, empty, manifest_path


def _executor_language(manifest_path, requested_language=None) -> str:
    requested = normalize_language(requested_language) if requested_language is not None else None
    if manifest_path is None:
        return requested or "python"
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        manifest_language = normalize_language(handoff_from_dict(data).language)
    except (OSError, json.JSONDecodeError, HandoffError, KeyError, TypeError, ValueError) as exc:
        raise StageError(f"cannot select Executor from invalid Handoff manifest {manifest_path}: {exc}") from exc
    if requested is not None and requested != manifest_language:
        raise StageError(
            f"candidate language mismatch: requested {requested!r}, "
            f"but Handoff manifest declares {manifest_language!r}")
    return manifest_language


def _run_java_executor(cmd, summary_path: Path, timeout_seconds: float) -> CommandResult:
    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    run_dir = summary_path.parent
    tracked = (run_dir / "run.json").is_file()
    if tracked:
        record_process(run_dir, "executor", proc)
    timed_out = False
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
    finally:
        if tracked:
            forget_process(run_dir, proc.pid)
    end = time.time()
    return CommandResult(
        argv=tuple(str(item) for item in cmd), display=" ".join(str(item) for item in cmd),
        returncode=proc.returncode, stdout=stdout or "", stderr=stderr or "",
        start=start, end=end, duration=end - start, timed_out=timed_out,
    )


def _java_executor_summary(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StageError(f"Java Executor did not write completion summary {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError(f"Java Executor summary at {path} is invalid: {exc}") from exc
    outcomes = data.get("outcomes")
    v2_counts = data.get("results_v2_write_counts")
    if not isinstance(outcomes, dict) or not isinstance(v2_counts, dict):
        raise StageError(f"Java Executor summary at {path} lacks outcomes/results_v2_write_counts")
    try:
        processed = int(data["processed_count"])
        passed = int(outcomes.get("PASS", 0))
        failed = int(outcomes.get("DOMAIN_FAIL", 0))
        broken = int(outcomes.get("BROKEN", 0))
        timeout = int(outcomes.get("TIMEOUT", 0))
        infra_fail = int(outcomes.get("INFRA_FAIL", 0))
        normalized_v2 = {
            key: int(v2_counts.get(key, 0))
            for key in ("attempted", "inserted", "already_present", "updated_selected")
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise StageError(f"Java Executor summary at {path} contains invalid counts: {exc}") from exc
    return processed, passed, failed, broken, passed + failed, timeout, infra_fail, normalized_v2


def _repeat_executor_flags(cfg: BundleConfig, run_id=None) -> list:
    """The `py_executor` repeat flags for the verified Python local K>1 paths (docs/24 §5):
    ``--repeat K --repeatPolicy local --repeatScope metrics|all --envId local:<run>``. Returns ``[]``
    for K=1 or any non-capable mode — the launcher capability gate already enforces that only
    local/metrics or local/all reaches a K>1 run, but this re-checks defensively so a stray config can
    never silently turn on repeats.

    Control-plane seam note (2026-07-03): this IN-EXECUTOR repeat is the single-host
    degenerate case of the Java dispatch layer (Analyzer_trunk ``BundleControlPlane`` —
    multi-env fan-out, per-host serialization, budget deadline). The env identity here
    (``local:<run>``) is the seam's contract key: ``bundle.controlplane._default_envs``
    mirrors it byte-for-byte, and ``test_bundle_controlplane_seam.py`` pins both sides.
    Do NOT re-implement multi-env dispatch here — emit a plan for the Java plane instead."""
    policy, scope, k, _e = cfg.validate_repeat()
    if k > 1 and policy == "local" and scope in ("metrics", "all"):
        return ["--repeat", str(k), "--repeatPolicy", policy, "--repeatScope", scope,
                "--envId", f"local:{run_id or 'default'}"]
    return []


def _java_repeat_executor_flags(cfg: BundleConfig, run_id=None) -> list:
    """The Java `MainWatch` repeat flags for the verified local K>1 paths (Plan-1 3c + local/all) --
    the single-dash MainWatch arg form (`-repeat K -repeatPolicy local -repeatScope metrics|all -envId
    local:<run>`), mirroring ``_repeat_executor_flags`` for py_executor (see its control-plane seam
    note: the ``local:<run>`` env id is the Python↔Java contract key). Returns ``[]`` for K=1 or any
    non-capable mode."""
    policy, scope, k, _e = cfg.validate_repeat()
    if k > 1 and policy == "local" and scope in ("metrics", "all"):
        return ["-repeat", str(k), "-repeatPolicy", policy, "-repeatScope", scope,
                "-envId", f"local:{run_id or 'default'}"]
    return []


def _last_match(pattern: str, text: str):
    """The LAST match of `pattern` in `text`, or None.

    A pooled py_executor (``--workers N``) lets every worker print its own
    partition's DONE / OUTCOMES / RESULTS_V2 lines before the dispatcher prints the
    aggregated ones -- so the first match is one worker's share (seen live: 551 of
    3456 candidates, failing the Results-count invariant) and only the last line
    describes the whole run. A serial run prints each line once, so this reads it
    exactly as before."""
    last = None
    for last in re.finditer(pattern, text):
        pass
    return last


def _python_worker_flags(cfg: BundleConfig) -> list:
    """``--workers N`` for py_executor's own local pool (STEP 33), or ``[]`` for N=1.

    The pool re-invokes py_executor once per deterministic id-hash partition and
    re-emits the DONE / OUTCOMES / RESULTS_V2 summary lines this stage parses, so
    the launcher reads a pooled run exactly like a serial one. The capability gate
    has already refused the combinations the pool is not verified for."""
    workers = int(getattr(cfg, "executor_workers", 1) or 1)
    return ["--workers", str(workers)] if workers > 1 else []


def _stage_python_executor(src, hs, cfg: BundleConfig, manifest_path=None, run_id=None,
                           attempt: int = 1, summary_path=None, metrics_path=None):
    py_executor = Path(cfg.py_executor) if cfg.py_executor else PY_EXECUTOR
    cmd = [cfg.resolved_python_cmd(), str(py_executor), "-srcDirList", str(src),
           "-dirResultsDbURL", str(hs / "resultsDbURL"), "-dirSqlTemplate", str(hs / "sqlTemplate"),
           "-dirArguments", str(hs / "arguments"), "-dirRunFirstOnce", str(hs / "runFirstOnce"),
           "--failOnly", "false", "--writeToDB", "true", "--attempt", str(attempt)]
    if summary_path is not None:
        cmd += ["--resultFile", str(summary_path)]
    if metrics_path is not None:
        # Harvest Analyzer metrics from this sandboxed execution instead of
        # re-running Python candidates on the host. Java MainWatch currently
        # has no equivalent metrics-file transport, so this is Python-only.
        cmd += ["--metricsFile", str(metrics_path)]
    if manifest_path is not None:
        cmd += ["--manifest", str(manifest_path)]
        if run_id:
            cmd += ["--runId", run_id]
    # Plan-1 repeat (Python local/metrics K>1, docs/24 §5): re-measure each candidate's metric K
    # times in-sandbox and emit raw samples keyed by (candidate_id, repeat_idx, env_id). K=1 / any
    # non-capable mode ⇒ no flags ⇒ the unchanged single-measurement path (see _repeat_executor_flags).
    cmd += _repeat_executor_flags(cfg, run_id)
    cmd += _python_worker_flags(cfg)
    # manifest mode reads the Results DB password from the environment — the v2
    # manifest never carries a secret (P3/P14). The launcher owns the env-var
    # transport, exactly as the benchmark stage does; a password supplied via
    # config-file / --results-db-password / dev-defaults reaches py_executor only
    # if injected here (it is NOT necessarily exported in the operator's shell).
    env = {**os.environ, "BUNDLE_RESULTS_DB_PASSWORD": cfg.results_db_password}
    r = run(cmd, env=env)
    output = r.stdout + r.stderr
    # Persist py_executor's full stdout/stderr next to the run (symmetric with the
    # Java branch's executor.log and with core.log/reader.log) so per-candidate
    # sandbox/outcome diagnostics survive beyond the printed tail.
    try:
        (Path(hs).parent / "executor.log").write_text(output, encoding="utf-8")
    except OSError:
        pass
    tail = output.strip().splitlines()[-1:] or ["(no output)"]
    print("   ", tail[0])
    summary = _last_match(
        r"py_executor DONE: processed=([0-9]+) pass=([0-9]+) fail=([0-9]+) broken=([0-9]+) inserted=([0-9]+)",
        output,
    )
    if not summary:
        if r.returncode != 0:
            raise StageError(f"py_executor exited with status {r.returncode} "
                             f"and emitted no completion summary (unclassified failure)")
        raise StageError("py_executor did not emit a completion summary")
    if r.returncode != 0:
        print(f"    (py_executor exited with status {r.returncode} but emitted a "
              f"completion summary -- deferring to the launcher's outcome invariants/policy)")
    processed, passed, failed, broken, inserted = map(int, summary.groups())
    outcomes = _last_match(
        r"py_executor OUTCOMES: pass=([0-9]+) domain_fail=([0-9]+) broken=([0-9]+) "
        r"timeout=([0-9]+) infra_fail=([0-9]+) skipped=([0-9]+) cancelled=([0-9]+)",
        output,
    )
    timeout, infra_fail = map(int, outcomes.group(4, 5)) if outcomes else (0, 0)
    v2_summary = _last_match(
        r"py_executor RESULTS_V2: attempted=([0-9]+) inserted=([0-9]+) "
        r"already_present=([0-9]+) updated_selected=([0-9]+)",
        output,
    )
    if manifest_path is not None and not v2_summary:
        raise StageError("py_executor did not emit the required results_v2 write summary")
    v2_values = tuple(map(int, v2_summary.groups())) if v2_summary else (0, 0, 0, 0)
    v2_counts = dict(zip(("attempted", "inserted", "already_present", "updated_selected"), v2_values))
    return processed, passed, failed, broken, inserted, timeout, infra_fail, v2_counts


def _adopt_grpc_executor(work, cfg: BundleConfig, attempt: int = 1):
    """gRPC transport: the Executor was started BEFORE the Reader (it ingested the live
    stream) — adopt it here, wait for its -exitWhenComplete grpc drain-exit (all streams
    closed + every received candidate processed → clean self-exit with the shutdown
    flush), and return the same canonical counts the spawn path returns."""
    handle = _GRPC_EXECUTORS.pop(_grpc_registry_key(work), None)
    if handle is None:
        raise StageError(
            "gRPC transport: no live Executor to adopt — the grpc candidate stream only "
            "exists while the launcher process that ran the reader stage is alive. A "
            "grpc run always re-runs reader+executor together (trusted-upstream reader "
            "reuse / standalone executor resume are loose-files/sharded features).")
    if attempt != 1:
        print(f"    (grpc transport: the live-feed Executor records attempt=1; "
              f"launcher requested attempt={attempt})")
    proc, log = handle["proc"], handle["log"]
    work = Path(work)
    timed_out = False
    try:
        proc.wait(timeout=cfg.executor_timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    finally:
        if (work / "run.json").is_file():
            forget_process(work, proc.pid)
    output = ""
    try:
        output = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    tail = output.strip().splitlines()[-1:] or ["(no output)"]
    print("   ", tail[0])
    if timed_out:
        raise StageError(
            f"gRPC Executor did not drain within {cfg.executor_timeout_seconds:g}s; "
            f"it was terminated after its shutdown flush (see {log})")
    if proc.returncode != 0:
        raise StageError(f"gRPC Executor exited with status {proc.returncode}: {tail[0]}")
    return _java_executor_summary(work / "executor-summary.json")


def stage_executor(src, hs, db, results_port, cfg: BundleConfig = BundleConfig(), manifest_path=None, run_id=None,
                   attempt: int = 1, summary_path=None, metrics_path=None, language=None):
    executor_language = _executor_language(manifest_path, language)
    print(f"\n[4/5] EXECUTOR ({executor_language}) — run candidates, write verdicts")
    # Plan-1 Phase 3b (docs/24 §1.6): fence genuinely-old executor artifacts BEFORE they connect.
    # An artifact that cannot advertise the 5-column results_v2 sample-identity writer is rejected
    # here, so it never runs ensureSchema and resurrects the retired 3-column unique index.
    verify_executor_schema_capability(cfg, executor_language)
    if _candidate_sink(cfg) == "grpc":
        processed, passed, failed, broken, inserted, timeout, infra_fail, v2_counts = (
            _adopt_grpc_executor(Path(hs).parent, cfg, attempt=attempt)
        )
    elif executor_language == "java":
        if manifest_path is None:
            raise StageError("Java Executor requires a validated Handoff v2 manifest")
        java_executor = Path(cfg.java_executor_jar) if cfg.java_executor_jar else JAVA_EXECUTOR_JAR
        java_jars = Path(cfg.java_jars_dir) if cfg.java_jars_dir else JAVA_JARS_DIR
        if not java_executor.is_file():
            raise StageError(f"Java Executor fat jar missing: {java_executor}")
        if not java_jars.is_dir():
            raise StageError(f"Java dependency JAR directory missing: {java_jars}")
        # MainWatch writes its summary as the FIXED name "executor-summary.json" inside
        # -out2 (writeExecutorSummary). Derive the read path from that directory + fixed
        # name, NOT from summary_path's basename -- otherwise a caller passing a
        # differently-named summary_path would make the launcher read a file MainWatch
        # never wrote ("did not write completion summary"). The out2 dir is summary_path's
        # parent (so the artifact the launcher records still lands where expected).
        out2_dir = Path(summary_path).parent if summary_path is not None else Path(hs).parent
        effective_summary = out2_dir / "executor-summary.json"
        out2_dir.mkdir(parents=True, exist_ok=True)
        effective_summary.unlink(missing_ok=True)
        # Optional compiler-backend pin (-Dfw.exec.compiler must precede -jar). "" lets
        # MainWatch use its own default (adaptive). Validated here so a typo fails closed
        # with a clear message rather than MainWatch's IllegalArgumentException mid-run.
        jvm_props = []
        compiler = (getattr(cfg, "executor_compiler", "") or "").strip().lower()
        if compiler:
            if compiler not in ("adaptive", "janino", "ecj", "javac"):
                raise StageError(
                    f"invalid executor_compiler {compiler!r}; expected adaptive, janino, ecj, or javac")
            jvm_props.append(f"-Dfw.exec.compiler={compiler}")
        pool = int(getattr(cfg, "executor_pool_size", 1) or 1)
        if pool > 1:
            processed, passed, failed, broken, inserted, timeout, infra_fail, v2_counts = (
                _stage_java_executor_pool(src, hs, cfg, manifest_path, run_id, attempt,
                                          out2_dir, metrics_path, jvm_props,
                                          java_executor, java_jars, pool))
            return _finish_executor_stage(processed, passed, failed, broken, inserted,
                                          timeout, infra_fail, v2_counts,
                                          db, results_port, cfg)
        cmd = [
            cfg.java_cmd, *jvm_props, "-jar", str(java_executor),
            "-manifest", str(manifest_path),
            "-srcDirList", str(src),
            "-dirJars", str(java_jars),
            "-dirResultsDbURL", str(hs / "resultsDbURL"),
            "-dirSqlTemplate", str(hs / "sqlTemplate"),
            "-dirArguments", str(hs / "arguments"),
            "-dirRunFirstOnce", str(hs / "runFirstOnce"),
            "-out2", str(effective_summary.parent),
            "-attempt", str(attempt),
            "-failOnly", "false",
            "-exitWhenComplete", "true",
            "--writeToDB", "true",
        ]
        if metrics_path is not None:
            # Plan-1 3c: harvest the Analyzer K=V corpus from THIS sandboxed execution (MainWatch
            # reads each candidate's emitted app= line and writes the corpus here), mirroring the
            # Python --metricsFile path. No re-run of generated code on the host.
            cmd += ["-metricsFile", str(metrics_path)]
        # Plan-1 3c sub-increment 2: K>1 repeat fan-out (local/metrics) -- re-measure each candidate's
        # metric K times in-process and emit raw samples keyed by (candidate_id, repeat_idx, env_id).
        # K=1 / non-capable ⇒ no flags ⇒ the unchanged single-shot path. The launcher gate still fences
        # Java K>1 upstream until sub-increment #3 opens it; this is the executor-side wiring.
        cmd += _java_repeat_executor_flags(cfg, run_id)
        r = _run_java_executor(cmd, effective_summary, cfg.executor_timeout_seconds)
        output = r.stdout + r.stderr
        # Persist the Java Executor's full stdout/stderr next to its summary, like
        # core.log/reader.log -- MainWatch's diagnostics (dependency-JAR registration,
        # per-candidate compile/verdict, results_v2 batch) are otherwise captured and
        # dropped except the tail, leaving a Java run far less inspectable than the
        # other stages. Written even on failure so a non-zero/timeout exit is debuggable.
        try:
            (out2_dir / "executor.log").write_text(output, encoding="utf-8")
        except OSError:
            pass
        tail = output.strip().splitlines()[-1:] or ["(no output)"]
        print("   ", tail[0])
        if r.timed_out:
            raise StageError(
                f"Java Executor exceeded {cfg.executor_timeout_seconds:g}s; "
                f"it was terminated after its shutdown flush")
        if r.returncode != 0:
            raise StageError(f"Java Executor exited with status {r.returncode}: {tail[0]}")
        processed, passed, failed, broken, inserted, timeout, infra_fail, v2_counts = (
            _java_executor_summary(effective_summary)
        )
    else:
        processed, passed, failed, broken, inserted, timeout, infra_fail, v2_counts = (
            _stage_python_executor(
                src, hs, cfg, manifest_path=manifest_path, run_id=run_id,
                attempt=attempt, summary_path=summary_path, metrics_path=metrics_path
            )
        )

    # Both executors now return the same canonical count tuple. The DB probe and
    # launcher invariants therefore stay language-independent.
    return _finish_executor_stage(processed, passed, failed, broken, inserted,
                                  timeout, infra_fail, v2_counts, db, results_port, cfg)


def _finish_executor_stage(processed, passed, failed, broken, inserted, timeout, infra_fail,
                           v2_counts, db, results_port, cfg: BundleConfig):
    """Shared stage_executor tail: probe the Results DB and assemble the canonical
    count tuple — identical for single-executor, pool, grpc-adopted and python paths."""
    if processed == 0:
        db_total = 0
    else:
        # Route the table name through sql_identifier() like
        # orchestrator._reset_owned_legacy_results does. `db` is operator- or
        # spec-supplied, so plain interpolation here was an inconsistency
        # rather than a live hole -- but the codebase already owns the right
        # tool for this exact job, and one call site not using it is how the
        # next one gets written wrong too.
        cnt, rc = psql(results_port, db,
                       f'select count(*)||\' / pass \'||count(*) filter(where status)||\' / fail \' '
                       f'||count(*) filter(where not status) from {sql_identifier(db)};',
                       host=cfg.results_db_host, user=cfg.results_db_user, password=cfg.results_db_password)
        if rc != 0:
            raise StageError(f"could not read Results DB :{results_port}/{db}")
        db_total = int(cnt.split("/", 1)[0].strip())
        ok(f"Results DB :{results_port}/{db}: {cnt} (total / pass / fail)")
    return processed, passed, failed, broken, inserted, db_total, timeout, infra_fail, v2_counts


def _stage_java_executor_pool(src, hs, cfg: BundleConfig, manifest_path, run_id, attempt,
                              out2_root: Path, metrics_path, jvm_props, java_executor,
                              java_jars, pool: int):
    """Executor pool (2026-07-04): spawn N MainWatch members, each owning ONE manifest
    source (`-poolIndex i` scopes it to source[i] — the dir the Reader's legacy
    round-robin filled). Members run CONCURRENTLY against the shared Results DB (row
    identity keys on candidate ids, which the round-robin split makes disjoint), each
    self-exits on its own share (member completion target), and the launcher — the
    orchestrator; no external one is introduced — waits for all, MERGES the N
    executor-summary.json files into the canonical one at ``out2_root`` (summed counts
    + a "pool" breakdown), and concatenates the members' metrics corpora into the run's
    metrics.kv. Fail-closed: any member timing out / exiting non-zero / missing its
    summary fails the stage; every member is terminated on the way out."""
    out2_root = Path(out2_root)
    members = []
    print(f"    executor pool: {pool} member(s), one manifest source each")
    global_deadline = time.time() + float(cfg.executor_timeout_seconds)
    has_run_dir = (out2_root / "run.json").is_file()
    try:
        for i in range(pool):
            m_out2 = out2_root / "pool" / f"e{i}"
            m_out2.mkdir(parents=True, exist_ok=True)
            (m_out2 / "executor-summary.json").unlink(missing_ok=True)
            m_metrics = (m_out2 / "metrics.kv") if metrics_path is not None else None
            cmd = [
                cfg.java_cmd, *jvm_props, "-jar", str(java_executor),
                "-manifest", str(manifest_path),
                "-poolIndex", str(i),
                "-srcDirList", str(Path(src) / f"e{i}"),
                "-dirJars", str(java_jars),
                "-dirResultsDbURL", str(hs / "resultsDbURL"),
                "-dirSqlTemplate", str(hs / "sqlTemplate"),
                "-dirArguments", str(hs / "arguments"),
                "-dirRunFirstOnce", str(hs / "runFirstOnce"),
                "-out2", str(m_out2),
                "-attempt", str(attempt),
                "-failOnly", "false",
                "-exitWhenComplete", "true",
                "--writeToDB", "true",
            ]
            if m_metrics is not None:
                cmd += ["-metricsFile", str(m_metrics)]
            log = m_out2 / "executor.log"
            lf = open(log, "wb")
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
            lf.close()
            if has_run_dir:
                record_process(out2_root, f"executor-p{i}", proc)
            members.append({"i": i, "proc": proc, "out2": m_out2, "log": log,
                            "metrics": m_metrics})

        failures = []
        for m in members:
            remaining = max(1.0, global_deadline - time.time())
            try:
                m["proc"].wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                failures.append(f"member {m['i']} exceeded the pool deadline "
                                f"({cfg.executor_timeout_seconds:g}s total)")
                continue
            if m["proc"].returncode != 0:
                tail = ""
                try:
                    tail = m["log"].read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
                except (OSError, IndexError):
                    pass
                failures.append(f"member {m['i']} exited with status {m['proc'].returncode}"
                                + (f": {tail}" if tail else ""))
        if failures:
            raise StageError("executor pool FAILED -- " + "; ".join(failures))
    finally:
        for m in members:
            if m["proc"].poll() is None:
                m["proc"].terminate()
                try:
                    m["proc"].wait(timeout=15)
                except subprocess.TimeoutExpired:
                    m["proc"].kill()
                    m["proc"].wait()
            if has_run_dir:
                forget_process(out2_root, m["proc"].pid)

    # Merge: sum the canonical counts; keep the per-member breakdown for the journal.
    totals = None
    breakdown = []
    for m in members:
        summary_path = m["out2"] / "executor-summary.json"
        vals = _java_executor_summary(summary_path)   # raises on missing/invalid
        processed, passed, failed, broken, inserted, timeout, infra_fail, v2 = vals
        breakdown.append({"member": m["i"], "out2": str(m["out2"]),
                          "processed": processed, "pass": passed, "fail": failed,
                          "broken": broken, "timeout": timeout, "infra_fail": infra_fail,
                          "results_v2": v2})
        print(f"      member {m['i']}: processed={processed} pass={passed} fail={failed}"
              f" broken={broken} timeout={timeout} infra_fail={infra_fail}")
        if totals is None:
            totals = [processed, passed, failed, broken, inserted, timeout, infra_fail, dict(v2)]
        else:
            for k in range(7):
                totals[k] += vals[k]
            for key, val in v2.items():
                totals[7][key] = totals[7].get(key, 0) + val

    # Canonical merged summary at the FIXED path the launcher's fail-closed summary
    # check (_require_executor_summary) reads — same shape as a single executor's,
    # plus the pool breakdown.
    merged = {
        "processed_count": totals[0],
        "outcomes": {"PASS": totals[1], "DOMAIN_FAIL": totals[2], "BROKEN": totals[3],
                     "TIMEOUT": totals[5], "INFRA_FAIL": totals[6], "SKIPPED": 0, "CANCELLED": 0},
        "results_v2_write_counts": totals[7],
        "pool": {"size": pool, "members": breakdown},
    }
    write_json_atomic(out2_root / "executor-summary.json", merged)

    # One corpus for the analyzer stage: concatenate the members' harvests in member order.
    if metrics_path is not None:
        parts = []
        for m in members:
            if m["metrics"] is not None and m["metrics"].is_file():
                text = m["metrics"].read_text(encoding="utf-8")
                if text and not text.endswith("\n"):
                    text += "\n"
                parts.append(text)
        Path(metrics_path).write_text("".join(parts), encoding="utf-8")

    return tuple(totals)


#: Where the run path self-builds the AnalyzeKv driver when the Analyzer
#: directory carries no persisted `analyzer_cp.txt`.
ANALYZER_SELFBUILD_CLASSES = Path("/tmp/analyzekv")
ANALYZER_SELFBUILD_CLASSPATH = Path("/tmp/analyzer_cp_full.txt")


def resolve_analyzer_driver(az: "Path | None" = None) -> "tuple[Path, Path] | None":
    """Locate an already-built AnalyzeKv driver as ``(classes_dir, classpath_file)``.

    Mirrors the run path's preference order — the persisted real build in the
    Analyzer directory first, then the one-time self-build under ``/tmp`` — and
    is shared so read-only callers cannot drift from what a run actually uses.

    This only *finds* an existing build; it never triggers one, which is what
    makes it safe for measurement paths (`bundle bench`) that must not do work
    on behalf of the thing they are timing. Returns None when neither location
    holds a compiled driver.
    """
    az = az or (SRC / "Analyzer_trunk")
    for clsdir, cpfile in ((az / "target/analyzekv", az / "analyzer_cp.txt"),
                           (ANALYZER_SELFBUILD_CLASSES, ANALYZER_SELFBUILD_CLASSPATH)):
        if (clsdir / "AnalyzeKv.class").is_file() and cpfile.is_file():
            return clsdir, cpfile
    return None


def _analyzekv_class_is_stale(class_file: Path, az: Path) -> bool:
    """True if the compiled AnalyzeKv class is missing OR older than ``AnalyzeKv.java`` or any
    Analyzer source it links against (``Analyzer_trunk/src/main/java/**/*.java``). The bundle must
    recompile in that case: a class present but older than its sources silently runs stale analyzer
    logic (it nearly masked the K=1/K=3 objective-set fix)."""
    if not class_file.exists():
        return True
    cls_mtime = class_file.stat().st_mtime
    sources = [az / "AnalyzeKv.java", *(az / "src" / "main" / "java").rglob("*.java")]
    return any(p.exists() and p.stat().st_mtime > cls_mtime for p in sources)


def _analyzer_classes_are_stale(az: Path) -> bool:
    """True if the Analyzer's compiled dependency bytecode (``target/classes``) is missing OR older
    than any Analyzer source (``src/main/java/**/*.java``). AnalyzeKv is BOTH compiled and run
    against ``target/classes``; if a dependency source changed but ``target/classes`` was never
    rebuilt, AnalyzeKv silently links/runs STALE dependency logic — and recompiling only the driver
    (the ``_analyzekv_class_is_stale`` path) does NOT fix it, because the driver is rebuilt against
    the same stale bytecode. Trigger a dependency rebuild first in that case."""
    classes_dir = az / "target" / "classes"
    classes = list(classes_dir.rglob("*.class")) if classes_dir.is_dir() else []
    sources = list((az / "src" / "main" / "java").rglob("*.java"))
    if not sources:
        return False                                     # nothing to compile ⇒ nothing can be stale
    if not classes:
        return True                                      # sources present, no bytecode ⇒ must build
    newest_class = max(c.stat().st_mtime for c in classes)
    return any(s.stat().st_mtime > newest_class for s in sources)


def _rebuild_analyzer_classes(az: Path) -> bool:
    """Recompile the Analyzer's own sources into ``target/classes`` (Maven) so AnalyzeKv links FRESH
    dependency bytecode. Returns True ONLY on a successful build that left a populated
    ``target/classes``. A failed Maven build leaves the previously compiled classes in place (Maven
    does not delete them on a compile error), but the caller must NOT treat them as fresh — so a
    non-zero build, or one that produced no classes, returns False (fail closed)."""
    classes_dir = az / "target" / "classes"
    r = run(f'cd "{az}" && mvn -o -q compile')
    if getattr(r, "returncode", 1) != 0:
        return False
    return classes_dir.is_dir() and any(classes_dir.rglob("*.class"))


def _compile_java_atomic(src_java: Path, clsdir: Path, classpath: str, javac_cmd: str,
                         main_class: str) -> bool:
    """Compile *src_java* into *clsdir* ATOMICALLY: build into a sibling temp dir and, ONLY on a
    successful compile that produced ``<main_class>.class``, move the class file(s) into place (the
    marker class moved LAST, so a fresh marker implies the whole set is present). A failed compile
    never overwrites the in-place class with a partial / falsely-fresh one — any prior class is left
    untouched. ``classpath`` may contain a shell ``$(cat …)`` (run() executes via the shell).
    Returns True on a successful build."""
    clsdir.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix=".jbuild-", dir=clsdir.parent))
    try:
        cp = f'-cp "{classpath}" ' if classpath else ""
        r = run(f'{javac_cmd} {cp}-d "{tmpdir}" "{src_java}"')
        marker = tmpdir / f"{main_class}.class"
        if getattr(r, "returncode", 1) != 0 or not marker.exists():
            return False
        for cls in sorted(tmpdir.glob("*.class")):
            if cls.name != marker.name:
                os.replace(cls, clsdir / cls.name)
        os.replace(marker, clsdir / marker.name)
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _ensure_analyzer_classes_fresh(az: Path, clsdir: Path, cpfile: Path, cfg: BundleConfig,
                                   mode: str, kv: Path) -> bool:
    """Make BOTH the Analyzer dependency bytecode (``target/classes``) and the AnalyzeKv driver
    class fresh before AnalyzeKv is run. A changed Analyzer source invalidates both: the dep classes
    it compiles into AND the driver that links them. Rebuild the dep classes FIRST (recompiling the
    driver against stale deps would silently link old logic — the trap the driver freshness check
    exists to prevent), then recompile the driver. ``target/classes`` is listed before the packaged
    jar on the AnalyzeKv classpath, so refreshing the exploded classes overrides any stale jar copy.

    Returns True when AnalyzeKv is ready to run. A failed dependency build NEVER recompiles the
    driver and NEVER claims freshness: in formal mode it raises ``StageError``; otherwise it returns
    False so the stage falls back to the corpus. Any prior driver/dependency class is left untouched
    (the atomic driver compile and Maven both preserve prior artifacts on failure)."""
    if _analyzer_classes_are_stale(az):
        if not _rebuild_analyzer_classes(az):
            msg = (f"Analyzer dependency classes ({az}/target/classes) are stale and rebuilding "
                   f"them failed; AnalyzeKv was NOT recompiled against stale bytecode")
            if mode == "formal":
                raise StageError(f"formal analysis requires up-to-date Analyzer classes: {msg}; "
                                 f"corpus at {kv}")
            print(f"    ({msg} — corpus ready at {kv})")
            return False
    class_file = clsdir / "AnalyzeKv.class"
    if _analyzekv_class_is_stale(class_file, az):
        built = _compile_java_atomic(az / "AnalyzeKv.java", clsdir,
                                     f'{az}/target/classes:$(cat {cpfile})', cfg.javac_cmd, "AnalyzeKv")
        if not built:
            note = " (a stale class was left untouched and will not be used)" if class_file.exists() else ""
            if mode == "formal":
                raise StageError(f"formal analysis requires AnalyzeKv but compiling it failed{note}; "
                                 f"corpus at {kv}")
            print(f"    (could not compile analyzer{note} — corpus ready at {kv})")
            return False
    return True


def stage_analyzer(src, scratch, goals, cfg: BundleConfig = BundleConfig(),
                   mode: str = "exploratory", corpus_count: int | None = None,
                   run_id: str = "", harvested_metrics=None, seed_out=None):
    print(f"\n[5/5] ANALYZER — ingest candidate stdout K=V  (mode={mode})")
    kv = scratch / "metrics.kv"
    # The corpus is harvested IN-SANDBOX by the Executor (py_executor --metricsFile,
    # one K=V line per candidate captured during its real run). Prefer it: it never
    # re-runs generated code on the host (a sandbox bypass for secure policies) and
    # never re-fires a stateful candidate's one-shot sudden action. collect_kv's
    # host re-execution stays ONLY as the fallback for a trusted-local/legacy run
    # that produced no harvested corpus.
    harvested = Path(harvested_metrics) if harvested_metrics else None
    if harvested and harvested.is_file() and harvested.stat().st_size > 0:
        if harvested != kv:
            kv.write_text(harvested.read_text(encoding="utf-8"), encoding="utf-8")
        n_lines = sum(1 for ln in kv.open(encoding="utf-8") if ln.strip())
        print(f"    corpus harvested in-sandbox by the Executor (no re-run): {n_lines} K=V line(s) → {kv}")
    else:
        # STEP 39: stamp the run_id onto every metric line (provenance) so a selected
        # candidate is attributable to THIS run — formal mode requires it.
        print("    (no in-sandbox corpus — trusted-local/legacy fallback: collect_kv re-runs candidates)")
        collect_cmd = [sys.executable, str(HERE / "api_probe/collect_kv.py"), str(src), str(kv)]
        if run_id:
            collect_cmd.append(str(run_id))
        r = run(collect_cmd)
        print("   ", (r.stdout.strip().splitlines() or ["(collect failed)"])[-1])
    az = SRC / "Analyzer_trunk"
    jar = az / "target/heuristic-analyzer-flatlaf-1.0.0.jar"
    if not (jar.exists() and (az / "AnalyzeKv.java").exists()):
        if mode == "formal":
            raise StageError(f"formal analysis requires the Analyzer, but it is unavailable (corpus at {kv})")
        print("    (analyzer not available — corpus ready at", kv, ")"); return
    # Resolve the analyzer classpath: prefer the persisted real build's analyzer_cp.txt, else
    # self-build it once under /tmp. The dependency bytecode (target/classes) AND the compiled
    # AnalyzeKv class are then kept FRESH below — rebuilt whenever an Analyzer source is newer than
    # them, not only when missing (a stale class/dep tree previously ran old analyzer logic silently).
    real_cp = az / "analyzer_cp.txt"
    if real_cp.exists():                                 # persisted REAL build in the analyzer dir (preferred)
        clsdir, cpfile = az / "target/analyzekv", real_cp
    else:                                                # fallback: one-time self-build classpath under /tmp
        clsdir, cpfile = Path("/tmp/analyzekv"), Path("/tmp/analyzer_cp_full.txt")
        if not cpfile.exists():
            # Offline first: on a warmed ~/.m2 this is fast and needs no network.
            # But `mvn -o` cannot fetch maven-dependency-plugin itself, and the
            # reactor build does not pull it in — so on a cold cache (a fresh CI
            # runner) the offline attempt always fails. Retry online before giving
            # up, otherwise the analyzer is unrunnable on exactly the hosts that
            # matter most: clean ones.
            dep = Path("/tmp/_dep.txt")
            for offline in (True, False):
                flag = "-o " if offline else ""
                run(f'cd "{az}" && mvn {flag}-q dependency:build-classpath -Dmdep.outputFile={dep}')
                if dep.exists():
                    cpfile.write_text(f'{jar}:' + dep.read_text().strip())
                    break
        if not cpfile.exists():
            # Same condition as the missing-jar check above — the analyzer cannot
            # run — so it must fail the same way. Degrading here regardless of mode
            # meant a formal run reported "full Bundle chain green" while the
            # Analyzer stage had silently not executed, and the caller then died on
            # the missing provenance.json instead of being told the real cause.
            if mode == "formal":
                raise StageError(
                    f"formal analysis requires the Analyzer, but its classpath could not be "
                    f"resolved (corpus at {kv}). Build it once with: "
                    f"cd {az} && mvn -q dependency:build-classpath -Dmdep.outputFile=/tmp/_dep.txt")
            print("    (could not resolve analyzer classpath — corpus ready at", kv, ")"); return
    # Refresh the dependency bytecode (target/classes) AND the AnalyzeKv driver class — in that
    # order — before running AnalyzeKv. A failed dependency rebuild raises (formal) or falls back to
    # the corpus (otherwise) and never runs AnalyzeKv against stale/false-fresh classes.
    if not _ensure_analyzer_classes_fresh(az, clsdir, cpfile, cfg, mode, kv):
        return
    # STEP 38: pass the analysis mode through to AnalyzeKv. Formal mode also
    # declares the corpus count (AnalyzeKv fails closed if it != ingested lines —
    # catching a truncated corpus silently changing a formal front).
    # STEP 39: AnalyzeKv writes the versioned provenance report to provenance.json
    # and exits non-zero in formal mode when a selected candidate is unprovenanced.
    prov = scratch / "provenance.json"
    mode_args = f' --mode {mode} --provenance-out "{prov}"'
    if mode == "formal" and corpus_count is not None:
        mode_args += f' --corpus-count {int(corpus_count)}'
    if seed_out is not None:
        mode_args += f' --seed-out "{Path(seed_out)}" --seed-source-run-id "{run_id}"'
    a = run(f'{cfg.java_cmd} -cp "{clsdir}:{az}/target/classes:$(cat {cpfile})" AnalyzeKv "{kv}" 10 "{goals}"{mode_args}')
    if mode == "formal" and a.returncode != 0:
        # AnalyzeKv exits 3 on a FORMAL provenance failure — surface it as a stage failure
        # so the run reflects that a selected candidate could not be traced.
        tail = "\n".join((a.stdout or "").splitlines()[-3:] + (a.stderr or "").splitlines()[-3:])
        raise StageError(f"formal provenance check failed (see {prov}):\n{tail}")
    front = [ln for ln in a.stdout.splitlines() if "Pareto front" in ln]
    prov_line = next((ln for ln in a.stdout.splitlines() if ln.startswith("provenance:")), "")
    seed_line = next((ln for ln in a.stdout.splitlines() if ln.startswith("seed:")), "")
    ok(f"analyzer: {front[0].strip()}" if front else f"analyzer ran (corpus at {kv})")
    if prov_line:
        print("   ", prov_line)
    if seed_line:
        print("   ", seed_line)


def stage_stress(src, hs, db, results_port, a):
    print("\n[4/5] STRESS (py_stress) — combinatorial storm against the live SUT")
    r = run([sys.executable, str(SRC / "Executor_trunk/py_stress.py"), "-srcDirList", str(src),
            "-dirResultsDbURL", str(hs / "resultsDbURL"),
            "-base-url", a.base_url, "-workers", str(a.workers), "-duration", str(a.duration),
            "-ramp", str(a.ramp), "-slo-p99", str(a.slo_p99), "-err-budget", str(a.err_budget),
            "-writeToDB", "true"])
    out = (r.stdout or "").strip()
    print("\n".join("    " + ln for ln in out.splitlines()[-8:]) if out else "    (no output)")
    if r.returncode != 0:
        print((r.stderr or "")[-600:])
        raise StageError("py_stress failed")
    ok("storm complete (verdict is SLO-based, not exact correctness)")
