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

"""Probe 4 — session hydration, and what a reload does to it.

Two findings this probe exists to keep visible, both counter-intuitive:

* **`presence_of_element_located` returns too early.** the target model serves a signed-out
  shell that already contains a usable input box, so the DOM being ready is not
  the account being ready. Acting then reads the wrong UI entirely.
* **Reloading too early destroys the session permanently.** A refresh issued
  before the app settles comes back signed out and never re-hydrates, while the
  first load is already authenticated. The upstream example refreshes "to retain
  the session state"; measured here, that is backwards.

    python3 probes/probe_session.py
"""
from __future__ import annotations

import sys
import time

from _common import cleanup, launch, target_url


def state(driver, tag: str) -> None:
    from selenium.webdriver.common.by import By

    signin = [e for e in driver.find_elements(By.CSS_SELECTOR, "button, a")
              if (e.get_attribute("aria-label") or "").strip().lower() in ("sign in", "войти")]
    temp = [e for e in driver.find_elements(By.CSS_SELECTOR, "button, [role='button']")
            if "врем" in (e.get_attribute("aria-label") or "").lower()
            or "temporar" in (e.get_attribute("aria-label") or "").lower()]
    print(f"  {tag:26} signin={len(signin)}  temp_chat_control={len(temp)}  "
          f"url={driver.current_url[-34:]}")


def main() -> int:
    driver, profile = launch()
    try:
        driver.get(target_url())
        # sample while the app hydrates: the early samples are the trap
        for seconds in (2, 5, 9):
            time.sleep(seconds if seconds == 2 else seconds - 2 if seconds == 5 else 4)
            state(driver, f"first load t=+{seconds}s")

        print("\n  --- now reload, which is where the session is lost ---")
        driver.refresh()
        time.sleep(2)
        state(driver, "after refresh t=+2s")
        time.sleep(7)
        state(driver, "after refresh t=+9s")

        from selenium.webdriver.common.by import By
        signin = [e for e in driver.find_elements(By.CSS_SELECTOR, "button, a")
                  if (e.get_attribute("aria-label") or "").strip().lower() in ("sign in", "войти")]
        if signin:
            print("\nRESULT: the reload dropped the session (expected on this setup).")
            print("        The adapter therefore does NOT refresh; it waits for hydration.")
            return 0
        print("\nRESULT: session survived the reload here — behaviour may differ per host.")
        return 0
    finally:
        cleanup(driver, profile)


if __name__ == "__main__":
    sys.exit(main())
