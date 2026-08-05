"""Reusable argparse builders shared by the bundle subcommands.
"""
from __future__ import annotations
from .cliutil import _UNSET
from .config import BundleConfig
from .policy import ORIGINS, profile_choices


def _optional_number(kind):
    """argparse `type=` for a budget ceiling: a number, or 'none'/'unlimited'/''
    to explicitly disable that dimension's gate (-> BudgetLimits field = None,
    evaluated as OK rather than an implicit zero ceiling)."""
    def parse(s):
        if s is None or str(s).strip().lower() in ("", "none", "unlimited"):
            return None
        return kind(s)
    return parse


def _add_budget_ceiling_args(ap) -> None:
    """STEP-12 budget-ceiling flags (`--budget-*`), layered into `BundleConfig` via
    `_CLI_ARG_TO_CONFIG_KEY`. Shared by the run parser and `bundle plan` (Plan-1 Phase 2,
    Automation #29 finding 1) so a repeat campaign's budget can be gated from the plan-only path —
    not only via `BUNDLE_BUDGET_*` env vars. The operational/accountability flags
    (`--override-budget`/`--allow-extreme`/`--unleash-*`) stay on the run parser only."""
    _bl = BundleConfig()
    ap.add_argument("--budget-mandatory-rows", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on mandatory Core rows (default: {_bl.budget_mandatory_rows})")
    ap.add_argument("--budget-final-candidates", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on final candidates (default: {_bl.budget_final_candidates})")
    ap.add_argument("--budget-disk-bytes", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated disk bytes (default: {_bl.budget_disk_bytes})")
    ap.add_argument("--budget-inodes", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated loose-file inodes (default: {_bl.budget_inodes})")
    ap.add_argument("--budget-wall-time-seconds", type=_optional_number(float), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated wall time, seconds (default: {_bl.budget_wall_time_seconds:g})")
    ap.add_argument("--budget-requests", type=_optional_number(int), default=_UNSET,
                    metavar="N|none", help=f"hard ceiling on estimated external requests (default: {_bl.budget_external_requests})")
    ap.add_argument("--budget-monetary-cost", type=_optional_number(float), default=_UNSET,
                    metavar="N|none", help="hard ceiling on estimated monetary cost (default: none — not gated)")
    ap.add_argument("--budget-warn-fraction", type=float, default=_UNSET,
                    help=f"warning threshold as a fraction of each hard ceiling (default: {_bl.budget_warn_fraction:g})")


def _add_repeat_args(ap) -> None:
    """Plan-1 Phase 2 (docs/24 §3): per-candidate repeat-policy CLI flags, layered into
    `BundleConfig` like every other config flag (default `_UNSET` ⇒ falls through to
    env/config/default). K=1 (default) is the legacy single run; K>1 is plan-only until the
    executor/schema phases land — a run is refused before any run dir/stage is created with
    `REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY` (docs/24 §4)."""
    rg = ap.add_argument_group("repeat policy (Plan-1 Phase 2, docs/24 §3)")
    rg.add_argument("--repeat", dest="repeat", type=int, default=_UNSET, metavar="K",
                    help="run each candidate K times (default 1 = legacy single run)")
    rg.add_argument("--repeat-policy", dest="repeat_policy", default=_UNSET,
                    choices=["disperse", "local", "nested"],
                    help="distribution of the K repeats (default: local)")
    rg.add_argument("--repeat-scope", dest="repeat_scope", default=_UNSET,
                    choices=["all", "metrics"],
                    help="repeat the whole verdict ('all') or only the metric measurement "
                         "('metrics', default — does not re-run the deterministic FW_VAR verdict)")
    rg.add_argument("--repeat-environments", dest="repeat_environments", type=int, default=_UNSET,
                    metavar="E",
                    help="planned executor-environment count; REQUIRED for --repeat-policy nested "
                         "with K>1 (this is NOT --workers stress concurrency)")


def _add_bundle_config_args(ap) -> None:
    """Register the typed-`BundleConfig` CLI layer (STEP 13) on *ap*: DB
    credentials/hosts, scratch root, jar/props/executor paths, java/python
    commands, timeouts, sandbox policy, outcome-tolerance list. Shared by the
    main run parser and `bundle resume` (STEP 24) -- resuming talks to the
    same DBs/jars/timeouts a fresh run would and must accept the same
    overrides (credentials are never persisted in run.json, see STEP 14, so
    they must be resuppliable here exactly as for a fresh run).

    Every flag defaults to `_UNSET` ("not given"): an unspecified flag must
    not shadow the environment/config-file layers beneath it -- only an
    explicit override wins at "CLI" precedence (see `_resolve_bundle_config`).
    """
    cg = ap.add_argument_group("configuration (STEP 13: typed, layered BundleConfig)")
    cg.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON object of BundleConfig overrides; layered beneath "
                         "environment (BUNDLE_<KEY>) and CLI, above defaults")
    cg.add_argument("--main-db-host", default=_UNSET, metavar="HOST")
    cg.add_argument("--main-db-user", default=_UNSET, metavar="USER")
    cg.add_argument("--main-db-password", default=_UNSET, metavar="PASSWORD")
    cg.add_argument("--results-db-host", default=_UNSET, metavar="HOST")
    cg.add_argument("--results-db-user", default=_UNSET, metavar="USER")
    cg.add_argument("--results-db-password", default=_UNSET, metavar="PASSWORD")
    cg.add_argument("--scratch-root", default=_UNSET, metavar="DIR",
                    help="parent directory for per-db scratch trees "
                         "(default: '/tmp/fw_work'; set e.g. '/mnt/F/fw_work' to opt into that volume)")
    cg.add_argument("--core-jar", default=_UNSET, metavar="PATH")
    cg.add_argument("--reader-jar", default=_UNSET, metavar="PATH")
    cg.add_argument("--core-props", default=_UNSET, metavar="PATH")
    cg.add_argument("--reader-props", default=_UNSET, metavar="PATH")
    cg.add_argument("--py-executor", default=_UNSET, metavar="PATH")
    cg.add_argument("--java-executor-jar", default=_UNSET, metavar="PATH",
                    help="Java Executor fat jar (default: Executor_trunk/target/Executor-1.0-jar-with-dependencies.jar)")
    cg.add_argument("--java-jars-dir", default=_UNSET, metavar="DIR",
                    help="dependency JAR directory exposed to incoming Java candidates "
                         "(default: Executor_trunk/lib-src/target)")
    cg.add_argument("--java-cmd", default=_UNSET, metavar="CMD", help="default: 'java'")
    cg.add_argument("--javac-cmd", default=_UNSET, metavar="CMD", help="default: 'javac'")
    cg.add_argument("--executor-compiler", default=_UNSET, choices=["adaptive", "janino", "ecj", "javac"],
                    help="pin the Java Executor compiler backend (-Dfw.exec.compiler); "
                         "default: MainWatch's own 'adaptive' (Janino fast path, ECJ fallback)")
    cg.add_argument("--python-cmd", default=_UNSET, metavar="CMD", help="default: this interpreter")
    cg.add_argument("--core-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="Core jar wall-time ceiling (default: 600)")
    cg.add_argument("--reader-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="Reader jar wall-time ceiling (default: 600)")
    cg.add_argument("--executor-timeout", type=float, default=_UNSET, metavar="SECONDS",
                    help="candidate Executor wall-time ceiling (default: 3600)")
    cg.add_argument("--sandbox-policy", default=_UNSET, metavar="ID",
                    help="Legacy free-form sandbox policy ID (recorded only; the real STEP 28 "
                         "sandbox backend is selected by --execution-policy-profile; default: 'sandbox')")
    cg.add_argument("--execution-policy-profile", default=_UNSET, metavar="PROFILE",
                    choices=[c["profile"] for c in profile_choices()],
                    help="execution-policy profile every candidate runs under -- also selects the "
                         "sandbox backend: 'generated-default' (container; use this for generated "
                         "or untrusted candidates) | 'networked-api-probe' (container, allowlisted "
                         "local-only egress) | 'trusted-local' (NO SANDBOX, host access; requires "
                         "--candidate-origin and --acknowledge-trusted-local). There is NO default: "
                         "a run refuses until a policy is chosen. 'bundle plan' needs none.")
    cg.add_argument("--candidate-origin", dest="candidate_origin", default=_UNSET, metavar="ORIGIN",
                    choices=list(ORIGINS),
                    help="where the candidate source came from, declared by YOU (never read from "
                         "the spec): " + " | ".join(ORIGINS) + ". Required for trusted-local, which "
                         "accepts only 'reviewed-checked-in' or 'locally-authored'. Recorded in the "
                         "run manifest.")
    cg.add_argument("--acknowledge-trusted-local", dest="trusted_local_acknowledgement",
                    default=_UNSET, metavar="REASON",
                    help="explicit, recorded reason for running candidates on this host WITHOUT a "
                         "sandbox. Required by --execution-policy-profile trusted-local; must be "
                         "non-empty. Persisted in the run manifest and re-verified on resume.")
    cg.add_argument("--sandbox-network-allowlist", dest="sandbox_network_allowlist",
                    default=_UNSET, metavar="TARGETS",
                    help="STEP 28: comma-separated target container name(s)/host(s) a "
                         "networked-api-probe candidate may reach (e.g. 'api-server' or "
                         "'api-server:8000'). Folded into the persisted execution policy and "
                         "attached to the candidate's dedicated local-only internal network. "
                         "Requires --execution-policy-profile networked-api-probe.")
    cg.add_argument("--sandbox-candidate-env", dest="sandbox_candidate_env",
                    default=_UNSET, metavar="NAME=VALUE,...",
                    help="STEP 30: comma-separated NAME=VALUE env passed into sandboxed "
                         "candidates (e.g. 'TRYOUT_URL=http://secure-app:8025'). NAMEs are "
                         "folded into the policy's env_allowlist; credential-shaped names are "
                         "refused (a secure sandbox never receives secrets).")
    cg.add_argument("--executor-tolerate-outcomes", default=_UNSET, metavar="LIST",
                    help="STEP 21 success policy: comma-separated infrastructure outcomes "
                         "to tolerate (subset of BROKEN,TIMEOUT,INFRA_FAIL) -- run still "
                         "succeeds and the corresponding invariant is recorded as WARNING "
                         "rather than failing closed. DOMAIN_FAIL is always tolerated and "
                         "needs no entry here (default: '' -- none tolerated)")
    cg.add_argument("--candidate-sink", dest="candidate_sink", default=_UNSET,
                    choices=["loose-files", "sharded", "grpc"],
                    help="candidate transport Reader→Executor: 'loose-files' (default; one file "
                         "per candidate), 'sharded' (*.fwshard containers), or 'grpc' "
                         "(2026-07-03: stream candidates LIVE to the Java Executor's gRPC "
                         "ingestion server — no on-disk corpus; requires --lang java and the "
                         "trusted-local execution policy)")
    cg.add_argument("--grpc-host", dest="grpc_host", default=_UNSET, metavar="HOST",
                    help="gRPC transport: host the Reader streams to (default: 127.0.0.1)")
    cg.add_argument("--grpc-port", dest="grpc_port", type=int, default=_UNSET, metavar="PORT",
                    help="gRPC transport: port the Executor's ingestion server binds "
                         "(-grpcPort) and the Reader streams to (default: 50061)")
    cg.add_argument("--executor-pool", dest="executor_pool_size", type=int, default=_UNSET, metavar="N",
                    help="Executor pool (2026-07-04): run N Java Executors, one per Reader "
                         "round-robin candidate directory (the legacy outZipDirPathList CSV). "
                         "The launcher spawns/journals/cancels the members and merges their "
                         "summaries. Requires --lang java, loose-files transport, K=1 "
                         "(default: 1 — single executor, unchanged)")
    cg.add_argument("--seed-output", dest="seed_output", default=_UNSET, action="store_const", const=True,
                    help="emit bundle_seed.json from the Analyzer stage (default: off; iterate forces it on)")
    cg.add_argument("--exploration-floor", dest="exploration_floor", type=float, default=_UNSET, metavar="FRACTION",
                    help="minimum per-sheet value fraction retained by seed bias (default: 0.25)")
    cg.add_argument("--min-winner-support", dest="min_winner_support", type=int, default=_UNSET, metavar="N",
                    help="minimum winner observations before a sheet may be narrowed (default: 5)")
    _add_repeat_args(ap)
