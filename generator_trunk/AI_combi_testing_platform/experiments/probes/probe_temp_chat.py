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

"""Probe 3 — is temporary chat actually engaged? Verified by effect.

This is the probe that corrected a wrong conclusion, so it is worth stating what
went wrong: temporary chat was first "verified" by reading `aria-pressed`, which
the app never sets. The check therefore passed while the mode was off, and the
first candidates were silently written to history. The click was also issued via
`execute_script`, which the app's own handlers ignore.

Neither the attribute, the URL, nor the page text changes when the mode engages,
so the only honest verification is by consequence: send a message and confirm the
conversation count did not grow.

    python3 probes/probe_temp_chat.py
"""
from __future__ import annotations

import sys
import time

from _common import cleanup, labels, launch, target_url

HISTORY_SELECTOR = ("[data-test-id='conversation'], .conversation-title, [role='listitem']")


def main() -> int:
    from selenium.webdriver.common.by import By

    driver, profile = launch()
    try:
        driver.get(target_url())
        time.sleep(9)

        def history() -> list[str]:
            return [e.text.strip()[:40]
                    for e in driver.find_elements(By.CSS_SELECTOR, HISTORY_SELECTOR)
                    if (e.text or "").strip()]

        before = history()
        print(f"conversations before: {len(before)}")
        if not before:
            print("  note: baseline is 0, so this probe cannot prove anything.")
            print("  Run it on an account that already has saved conversations.")

        button = None
        for element in driver.find_elements(By.CSS_SELECTOR, "button, a, [role='button']"):
            try:
                label = (element.get_attribute("aria-label") or "").strip().lower()
            except Exception:
                continue
            if "временный чат" in label or "temporary chat" in label:
                button = element
                break
        if button is None:
            print("temporary-chat control not found. Visible controls:")
            for text in labels(driver)[:25]:
                print(f"   {text[:60]!r}")
            return 3

        print(f"control found: {(button.get_attribute('aria-label') or '')[:50]!r}")
        print(f"  aria-pressed = {button.get_attribute('aria-pressed')!r} "
              f"(never set — do not verify with this)")
        button.click()                     # real click; a JS click does nothing here
        time.sleep(4)

        box = driver.find_element(
            By.CSS_SELECTOR, "rich-textarea div[contenteditable='true'], div[contenteditable='true']")
        driver.execute_script(
            "arguments[0].focus(); arguments[0].innerText = arguments[1];"
            "arguments[0].dispatchEvent(new InputEvent('input', {bubbles: true}));",
            box, "Reply with exactly: EFFECT_TEST")
        time.sleep(1)
        sent = False
        for css in ("button[aria-label*='Отправить' i]", "button[aria-label*='Send' i]"):
            candidates = [b for b in driver.find_elements(By.CSS_SELECTOR, css)
                          if b.is_displayed() and b.is_enabled()]
            if candidates:
                candidates[-1].click()
                sent = True
                break
        print(f"message sent: {sent}")
        time.sleep(18)

        after = history()
        new = [item for item in after if item not in before]
        print(f"conversations after : {len(after)}")
        if new:
            print(f"RESULT: temporary chat FAILED — new entries: {new[:3]}")
            return 4
        print("RESULT: temporary chat WORKS — nothing was written to history")
        return 0
    finally:
        cleanup(driver, profile)


if __name__ == "__main__":
    sys.exit(main())
