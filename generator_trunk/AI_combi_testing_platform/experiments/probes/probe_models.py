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

"""Probe 2 — what does the model picker offer, and is the target selectable?

Pinning is not optional. "Whatever the account default happened to be" is
exactly the kind of unrecorded variable this framework exists to refuse, so a
run that cannot name its model is not evidence.

Prints every offered option, so a changed label (the picker is localised and its
wording moves) is visible immediately rather than as a mystery failure inside a
30-minute run.

    python3 probes/probe_models.py
"""
from __future__ import annotations

import sys
import time

from _common import cleanup, launch, target_url

TARGET = "target_model"


def main() -> int:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver, profile = launch()
    try:
        driver.get(target_url())
        WebDriverWait(driver, 40).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR,
             "rich-textarea div[contenteditable='true'], div[contenteditable='true']")))
        time.sleep(4)

        buttons = driver.find_elements(By.CSS_SELECTOR, "bard-mode-switcher button")
        if not buttons:
            driver.save_screenshot("/tmp/probe_models.png")
            print("no model picker found (screenshot: /tmp/probe_models.png)")
            return 3
        trigger = buttons[0]
        print("picker trigger:", repr((trigger.get_attribute("aria-label") or "")[:80]))

        trigger.click()                    # a real click; JS clicks are ignored here
        time.sleep(3)

        print("\noffered options:")
        seen: list[str] = []
        for element in driver.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
            text = (element.text or "").strip().replace("\n", " / ")
            if text and text not in seen:
                seen.append(text)
                print(f"  {text[:100]!r}")
        if not seen:
            driver.save_screenshot("/tmp/probe_models_open.png")
            print("picker opened but no options matched "
                  "(screenshot: /tmp/probe_models_open.png)")
            return 4

        matches = [t for t in seen if TARGET in t.lower().replace(" ", "-")]
        print(f"\ntarget {TARGET!r} present: {bool(matches)} -> {matches}")
        return 0 if matches else 5
    finally:
        cleanup(driver, profile)


if __name__ == "__main__":
    sys.exit(main())
