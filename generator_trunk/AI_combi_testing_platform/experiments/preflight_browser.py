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

"""Preflight for the browser transport: check every failure mode before a run.

A 108-request run costs ~30 minutes, so discovering at request 3 that the
session never hydrated is expensive. Each check below corresponds to a failure
that actually occurred while building this, and each one is cheap:

1. **profile resolution** — `profiles.ini` commonly holds a stale profile marked
   with the legacy ``Default=1`` alongside an ``[InstallXXXX]`` section whose
   ``Default=<path>`` is what Firefox really launches. Picking the stale one
   yields a profile that starts fine and is simply signed out, so the symptom
   looks like an expired session and sends diagnosis the wrong way.
2. **session hydration** — the target model serves a signed-out shell that already
   contains a usable input box, so "the DOM is ready" is not "the account is
   ready".
3. **model pinning** — a result that cannot name its model is not evidence.
4. **temporary chat** — verified *by effect* (history must not grow), because
   the control sets no `aria-pressed` and a synthetic JS click is ignored.
5. **reply extraction** — the upstream example waits for generation to finish
   but never reads the reply; without this the oracle has nothing to score.

Run:
    export AI_COMBI_ALLOW_BROWSER=1
    python3 experiments/preflight_browser.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from generator_trunk.AI_combi_testing_platform.adapters import browser as B


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def main() -> int:
    failures = 0

    print("preflight: browser transport\n")
    try:
        profile = B._default_profile()
    except Exception as exc:
        check("profile resolution", False, str(exc))
        return 1
    failures += not check("profile resolution", Path(profile).is_dir(), profile)

    cookies = Path(profile) / "cookies.sqlite"
    failures += not check("session files present", cookies.is_file(),
                          f"{cookies.stat().st_size // 1024} KB" if cookies.is_file() else "missing")

    adapter = B.BrowserChatAdapter()
    try:
        started = time.time()
        adapter.start()                          # hydration + model pinning happen here
        failures += not check("headless launch + session hydration", True,
                              f"{time.time()-started:.0f}s")
        failures += not check("model pinned", bool(adapter._model_label),
                              repr(adapter._model_label))

        before = adapter.history_count()
        print(f"\n  saved conversations before probe: {before}")

        from generator_trunk.AI_combi_testing_platform.adapters.base import CompletionRequest
        from generator_trunk.AI_combi_testing_platform.task_ir import generate_task

        task = generate_task("ordering", seed=1, complexity=2)
        request = CompletionRequest(
            prompt="Reply with exactly this and nothing else: PREFLIGHT_OK",
            task=task, output_schema="plain")
        completion = adapter.complete(request)
        failures += not check("reply extracted", bool(completion.text.strip()),
                              repr(completion.text[:60]))
        failures += not check("latency recorded", completion.latency_us > 0,
                              f"{completion.latency_us/1e6:.1f}s")

        after = adapter.history_count()
        # With temporary chat engaged the conversation is never written to
        # history. `after` can also read 0 because the sidebar is not rendered on
        # that screen, so only growth is treated as a definite failure.
        failures += not check("temporary chat (history did not grow)", after <= before,
                              f"{before} -> {after}")
        if after == 0 and before == 0:
            print("       note: history reads 0 on both sides; this check is weak here.")
            print("       Strong evidence requires a non-zero baseline before the probe.")
    except Exception as exc:
        check("live probe", False, f"{type(exc).__name__}: {exc}")
        failures += 1
    finally:
        adapter.close()

    print(f"\n{'PREFLIGHT PASSED' if not failures else f'PREFLIGHT FAILED ({failures} check(s))'}")
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
