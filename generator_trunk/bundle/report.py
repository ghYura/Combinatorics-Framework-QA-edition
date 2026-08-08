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

"""Face 3: render a finished run as something a non-author can read.

Every input here is already emitted by a normal run -- ``run.json``,
``state.json``, ``stages/*.json``, ``executor-summary.json`` and
``provenance.json``. This module adds no measurement of its own and starts no
stage; it is a pure read of what the run already recorded, which is what makes
it safe to point at any run directory, including a failed or interrupted one.

The output is a single self-contained HTML file (no external CSS, JS, fonts or
images), so it can be opened from a file:// path, copied to another host, or
attached to a report without carrying assets along.

Design note: the surface deliberately shows what is *absent* as prominently as
what is present -- an unset sandbox backend, a missing Analyzer front, an
interrupted stage. A results view that only renders the happy path would let a
reader mistake "not recorded" for "fine".
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .errors import PreflightError
from .jsonio import read_json

REPORT_SCHEMA = "bundle.report/v1"

#: Stage order as the pipeline runs them, so the timeline reads top-to-bottom
#: in execution order rather than the alphabetical order state.json stores.
STAGE_ORDER = ("gen", "core", "sieve", "draw", "seed_bias", "reader", "executor", "analyzer")

#: Outcome -> semantic class. Anything unknown renders neutral rather than
#: being silently bucketed as a pass or a failure.
OUTCOME_CLASS = {
    "PASS": "ok",
    "DOMAIN_FAIL": "fail",
    "INFRA_FAIL": "bad",
    "BROKEN": "bad",
    "TIMEOUT": "bad",
    "CANCELLED": "warn",
    "SKIPPED": "muted",
}
STATUS_CLASS = {
    "SUCCEEDED": "ok",
    "FAILED": "bad",
    "INTERRUPTED": "warn",
    "RUNNING": "warn",
    "PENDING": "muted",
    "SKIPPED": "muted",
}


def _load(path: Path, what: str):
    """Read a JSON artifact, or return None when the run never produced it."""
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except Exception as exc:                                  # pragma: no cover
        raise PreflightError(f"{what} at {path} is not readable JSON: {exc}")


def collect(root: Path) -> dict:
    """Gather everything the report needs from one run directory.

    Missing artifacts are recorded as None rather than raising: a run that
    failed in Core has no executor summary, and that absence is exactly what
    the reader needs to see.
    """
    root = Path(root)
    manifest = _load(root / "run.json", "run manifest")
    if manifest is None:
        raise PreflightError(f"no run.json in {root} — not a run directory")
    state = _load(root / "state.json", "run state") or {}
    stages_dir = root / "stages"
    stage_records = {}
    if stages_dir.is_dir():
        for p in sorted(stages_dir.glob("*.json")):
            rec = _load(p, f"stage record {p.name}")
            if rec is not None:
                stage_records[p.stem] = rec
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "manifest": manifest,
        "state": state,
        "stages": state.get("stages", {}) or {},
        "stage_records": stage_records,
        "executor": _load(root / "executor-summary.json", "executor summary"),
        "provenance": _load(root / "provenance.json", "provenance"),
        "resolved_config": _load(root / "resolved_config.json", "resolved config"),
    }


# --- text ----------------------------------------------------------------
def format_text(data: dict) -> str:
    """A terse stdout summary, so the command is useful without a browser."""
    m, ex, pv = data["manifest"], data["executor"], data["provenance"]
    out = [f"run {m.get('run_id', '?')}  [{m.get('status', '?')}]",
           f"  spec     {m.get('spec_path', '?')}",
           f"  database {m.get('db_name') or '(none)'}   mode={m.get('mode', '?')}"]
    stages = data["stages"]
    if stages:
        ordered = [s for s in STAGE_ORDER if s in stages] + \
                  [s for s in sorted(stages) if s not in STAGE_ORDER]
        parts = [f"{s}:{stages[s].get('status', '?')}" for s in ordered]
        out.append("  stages   " + "  ".join(parts))
    if ex:
        oc = ex.get("outcomes") or {}
        shown = "  ".join(f"{k}={v}" for k, v in sorted(oc.items()) if v)
        out.append(f"  verdicts processed={ex.get('processed', '?')}  {shown}")
        out.append(f"  sandbox  {ex.get('sandbox_backend') or 'NONE (candidates ran unsandboxed)'}")
    if pv:
        out.append(f"  analyzer mode={pv.get('mode', '?')}  front={len(pv.get('candidates') or [])}"
                   f"  provenance_ok={pv.get('provenance_ok')}")
    return "\n".join(out)


# --- html ----------------------------------------------------------------
def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _bar(segments) -> str:
    """A single proportional bar; segments are (label, count, css-class)."""
    total = sum(c for _, c, _ in segments) or 1
    cells = "".join(
        f'<span class="seg {cls}" style="width:{100.0 * c / total:.4f}%" '
        f'title="{_e(lbl)}: {c}"></span>'
        for lbl, c, cls in segments if c)
    return f'<div class="bar">{cells}</div>'


def _kv_table(rows) -> str:
    body = "".join(f"<tr><th>{_e(k)}</th><td>{v}</td></tr>" for k, v in rows if v is not None)
    return f"<table class='kv'>{body}</table>"


def _section(title, body, note=None) -> str:
    n = f"<p class='note'>{note}</p>" if note else ""
    return f"<section><h2>{_e(title)}</h2>{n}{body}</section>"


def _stage_section(data: dict) -> str:
    stages, records = data["stages"], data["stage_records"]
    if not stages:
        return _section("Stages", "<p class='absent'>No stage state recorded.</p>")
    ordered = [s for s in STAGE_ORDER if s in stages] + \
              [s for s in sorted(stages) if s not in STAGE_ORDER]
    longest = max((stages[s].get("duration_seconds") or 0) for s in ordered) or 1
    rows = []
    for s in ordered:
        st = stages[s]
        status = st.get("status", "?")
        dur = st.get("duration_seconds")
        width = 100.0 * (dur or 0) / longest
        arts = len((records.get(s) or {}).get("artifacts") or [])
        rows.append(
            f"<tr><td class='mono'>{_e(s)}</td>"
            f"<td><span class='pill {STATUS_CLASS.get(status, 'muted')}'>{_e(status)}</span></td>"
            f"<td class='num'>{'' if dur is None else f'{dur:.2f}s'}</td>"
            f"<td class='track'><span style='width:{width:.3f}%'></span></td>"
            f"<td class='num muted'>{arts or ''}</td></tr>")
    return _section(
        "Stages",
        "<table class='grid'><thead><tr><th>stage</th><th>status</th><th>duration</th>"
        "<th>relative</th><th>artifacts</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>")


def _verdict_section(data: dict) -> str:
    ex = data["executor"]
    if not ex:
        return _section(
            "Verdicts", "<p class='absent'>No executor summary — this run produced no verdicts.</p>")
    oc = {k: v for k, v in (ex.get("outcomes") or {}).items()}
    present = [(k, v, OUTCOME_CLASS.get(k, "muted")) for k, v in sorted(oc.items()) if v]
    processed = ex.get("processed") or sum(oc.values())
    passed = oc.get("PASS", 0)
    rate = (100.0 * passed / processed) if processed else 0.0
    chips = "".join(
        f"<span class='chip {OUTCOME_CLASS.get(k, 'muted')}'>{_e(k)} <b>{v}</b></span>"
        for k, v in sorted(oc.items()) if v)
    recon = ex.get("candidate_count_reconciliation") or {}
    mismatch = recon.get("declared") != recon.get("actual") if recon else False
    backend = ex.get("sandbox_backend")
    rows = [
        ("processed", _e(processed)),
        ("pass rate", f"{rate:.1f}%  ({passed}/{processed})"),
        ("declared vs actual",
         f"<span class='{'bad' if mismatch else 'ok'}'>{_e(recon.get('declared'))} / "
         f"{_e(recon.get('actual'))}</span>" if recon else None),
        ("handoff protocol", _e(ex.get("manifest_protocol"))),
        ("sandbox backend",
         _e(backend) if backend else
         "<span class='bad'>none — candidates ran unsandboxed on this host</span>"),
        ("duration", f"{ex.get('duration_seconds')}s" if ex.get("duration_seconds") else None),
    ]
    return _section("Verdicts",
                    f"<div class='chips'>{chips}</div>{_bar(present)}{_kv_table(rows)}")


def _front_section(data: dict) -> str:
    pv = data["provenance"]
    if not pv:
        return _section("Analyzer front",
                        "<p class='absent'>No provenance record — the Analyzer did not run "
                        "for this run.</p>")
    cands = pv.get("candidates") or []
    goals = ", ".join(f"{g.get('key')} {g.get('mode', '').lower()}" for g in (pv.get("goals") or []))
    issues = pv.get("provenance_issues") or []
    head = _kv_table([
        ("mode", _e(pv.get("mode"))),
        ("goals", _e(goals)),
        ("candidates seen", _e(pv.get("candidates_seen"))),
        ("front size", _e(len(cands))),
        ("provenance_ok",
         f"<span class='{'ok' if pv.get('provenance_ok') else 'bad'}'>"
         f"{_e(pv.get('provenance_ok'))}</span>"),
        ("issues", f"<span class='bad'>{_e(len(issues))}</span>" if issues else "0"),
    ])
    if not cands:
        return _section("Analyzer front", head + "<p class='absent'>Front is empty.</p>")
    objective_keys = sorted({k for c in cands for k in (c.get("objectives") or {})})
    dim_keys = sorted({k for c in cands for k in (c.get("dimensions") or {})})
    header = ("<tr><th>candidate</th><th>outcome</th>"
              + "".join(f"<th>{_e(k)}</th>" for k in objective_keys)
              + "".join(f"<th class='muted'>{_e(k)}</th>" for k in dim_keys)
              + "<th>why non-dominated</th></tr>")
    rows = []
    for c in cands:
        obj = c.get("objectives") or {}
        dim = c.get("dimensions") or {}
        outcome = str(c.get("outcome", "")).upper()
        rows.append(
            f"<tr><td class='mono'>{_e(c.get('candidate_id'))}</td>"
            f"<td><span class='pill {OUTCOME_CLASS.get(outcome, 'muted')}'>{_e(outcome)}</span></td>"
            + "".join(f"<td class='num'>{_e(obj.get(k))}</td>" for k in objective_keys)
            + "".join(f"<td class='muted'>{_e(dim.get(k))}</td>" for k in dim_keys)
            + f"<td class='reason'>{_e(c.get('reason_non_dominated'))}</td></tr>")
    return _section(
        "Analyzer front", head
        + f"<table class='grid'><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>",
        note="These are the non-dominated candidates — the trade-off frontier, not a single winner.")


def _artifacts_section(data: dict) -> str:
    records = data["stage_records"]
    rows = []
    for stage in [s for s in STAGE_ORDER if s in records] + \
                 [s for s in sorted(records) if s not in STAGE_ORDER]:
        for a in (records[stage] or {}).get("artifacts") or []:
            sha = (a.get("sha256") or "")[:12]
            rows.append(f"<tr><td class='mono'>{_e(stage)}</td>"
                        f"<td class='mono'>{_e(a.get('kind'))}</td>"
                        f"<td class='num muted'>{_e(a.get('bytes'))}</td>"
                        f"<td class='mono muted'>{_e(sha)}</td>"
                        f"<td class='path'>{_e(a.get('path'))}</td></tr>")
    if not rows:
        return _section("Artifacts", "<p class='absent'>No artifacts recorded.</p>")
    return _section("Artifacts",
                    "<table class='grid'><thead><tr><th>stage</th><th>kind</th><th>bytes</th>"
                    "<th>sha256</th><th>path</th></tr></thead><tbody>"
                    + "".join(rows) + "</tbody></table>")


def _identity_section(data: dict) -> str:
    m = data["manifest"]
    settings = m.get("settings") or {}
    policy = settings.get("execution_policy") or {}
    auth = settings.get("execution_authorization") or {}
    status = m.get("status", "?")
    profile = policy.get("profile") if isinstance(policy, dict) else policy
    rows = [
        ("status", f"<span class='pill {STATUS_CLASS.get(status, 'muted')}'>{_e(status)}</span>"),
        ("spec", f"<span class='mono'>{_e(m.get('spec_path'))}</span>"),
        ("spec sha256", f"<span class='mono muted'>{_e((m.get('spec_sha256') or '')[:16])}</span>"),
        ("database", _e(m.get("db_name") or "(none)")),
        ("language", _e(settings.get("lang"))),
        ("run mode", _e(m.get("mode"))),
        ("analyzer goals", _e(m.get("goals") or "(none)")),
        ("analysis mode", _e(settings.get("analysis_mode"))),
        ("execution profile",
         f"<span class='mono'>{_e(profile)}</span>" if profile else
         "<span class='warn'>not recorded</span>"),
        ("candidate origin", _e(auth.get("origin")) if auth else None),
        ("started", _e(m.get("start"))),
    ]
    return _section("Run", _kv_table(rows))


_CSS = """
:root{--bg:#fbfbfd;--fg:#1c1c22;--mut:#6b7280;--line:#e3e3ea;--card:#fff;
--ok:#1a7f4b;--fail:#b45309;--bad:#b42318;--warn:#8a6d1f;--accent:#3b4cca}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e6ec;--mut:#9aa0ab;
--line:#272a33;--card:#161922;--ok:#4ade80;--fail:#fbbf24;--bad:#f87171;--warn:#facc15;--accent:#8b9dff}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1080px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .25rem}
h2{font-size:1.05rem;margin:0 0 .75rem;letter-spacing:.01em}
.sub{color:var(--mut);margin:0 0 2rem;font-size:.875rem}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:1.1rem 1.25rem;margin:0 0 1.1rem}
.note{color:var(--mut);font-size:.83rem;margin:-.4rem 0 .8rem}
table{border-collapse:collapse;width:100%;font-size:.875rem}
.kv th{text-align:left;font-weight:500;color:var(--mut);padding:.28rem 1rem .28rem 0;
white-space:nowrap;vertical-align:top;width:1%}
.kv td{padding:.28rem 0}
.grid{margin-top:.5rem}
.grid th{text-align:left;font-weight:600;color:var(--mut);font-size:.78rem;
text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line);padding:.4rem .6rem .4rem 0}
.grid td{padding:.4rem .6rem .4rem 0;border-bottom:1px solid var(--line);vertical-align:top}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85em}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.muted{color:var(--mut)}
.path{font-family:ui-monospace,monospace;font-size:.76em;color:var(--mut);word-break:break-all}
.reason{color:var(--mut);font-size:.83em;max-width:32rem}
.pill{display:inline-block;padding:.08rem .5rem;border-radius:99px;font-size:.76rem;
font-weight:600;border:1px solid currentColor}
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.7rem}
.chip{padding:.18rem .6rem;border-radius:6px;font-size:.8rem;border:1px solid var(--line)}
.chip b{font-variant-numeric:tabular-nums}
.ok{color:var(--ok)} .fail{color:var(--fail)} .bad{color:var(--bad)} .warn{color:var(--warn)}
.absent{color:var(--mut);font-style:italic;margin:.2rem 0}
.bar{display:flex;height:9px;border-radius:99px;overflow:hidden;background:var(--line);margin:.2rem 0 .9rem}
.seg{display:block;height:100%}
.seg.ok{background:var(--ok)} .seg.fail{background:var(--fail)}
.seg.bad{background:var(--bad)} .seg.warn{background:var(--warn)} .seg.muted{background:var(--mut)}
.track{width:34%;min-width:6rem}
.track span{display:block;height:7px;border-radius:99px;background:var(--accent);opacity:.65}
footer{color:var(--mut);font-size:.78rem;margin-top:1.5rem;text-align:center}
@media(max-width:720px){body{padding:1rem .75rem 3rem}.track{display:none}}
"""


def render_html(data: dict) -> str:
    m = data["manifest"]
    run_id = m.get("run_id", "?")
    body = (_identity_section(data) + _verdict_section(data) + _stage_section(data)
            + _front_section(data) + _artifacts_section(data))
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Bundle run {_e(run_id)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>Bundle run <span class='mono'>{_e(run_id)}</span></h1>"
        f"<p class='sub'>{_e(data['root'])} · rendered {_e(data['generated_at'])}</p>"
        f"{body}"
        f"<footer>{_e(REPORT_SCHEMA)} — rendered from this run's own recorded artifacts; "
        "no stage was re-executed.</footer>"
        "</main></body></html>\n")
