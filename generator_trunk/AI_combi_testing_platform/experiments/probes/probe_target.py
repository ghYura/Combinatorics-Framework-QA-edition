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

"""Probe 1 — the first gate: can headless Firefox reach the target model and READ a reply?

Three things can each kill the transport on their own, and this checks all of
them in one pass: the login surviving a derived profile, headless not being
refused, and the reply text being extractable from the DOM.

That last one is the reason this probe exists at all. The upstream example waits
for generation to finish but never reads the response, so it "works" while
producing nothing an oracle could score.

    python3 probes/probe_target.py
"""
from __future__ import annotations

import sys
import time

from _common import cleanup, launch, target_url


def main() -> int:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver, profile = launch()
    try:
        driver.get(target_url())
        time.sleep(6)
        print("url  :", driver.current_url[:110])
        print("title:", driver.title[:90])

        if "accounts.google.com" in driver.current_url or "signin" in driver.current_url:
            print("RESULT: NOT LOGGED IN — the derived profile did not carry the session")
            return 2

        try:
            box = WebDriverWait(driver, 30).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "rich-textarea div[contenteditable='true'], div[contenteditable='true']")))
        except Exception:
            driver.save_screenshot("/tmp/probe_no_input.png")
            print("RESULT: input box not found (screenshot: /tmp/probe_no_input.png)")
            return 3

        print("input box found — sending a trivial prompt")
        box.click()
        box.send_keys("Reply with exactly: PROBE_OK")
        time.sleep(1)
        box.send_keys(Keys.ENTER)

        # Wait for the reply to stop changing rather than for a fixed duration:
        # generation streams, so a constant sleep either truncates or wastes time.
        deadline = time.time() + 90
        previous, stable = "", 0
        while time.time() < deadline:
            time.sleep(2)
            nodes = driver.find_elements(By.CSS_SELECTOR, "message-content, model-response")
            text = nodes[-1].text.strip() if nodes else ""
            if text and text == previous:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            previous = text

        print(f"RESULT: reply captured ({len(previous)} chars): {previous[:200]!r}")
        return 0 if previous else 4
    finally:
        cleanup(driver, profile)


if __name__ == "__main__":
    sys.exit(main())
