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

"""Shared setup for the standalone diagnostic probes.

Profile derivation deliberately reuses the adapter's own functions rather than
re-implementing them. A probe that resolves the profile differently from the
adapter can pass while the adapter fails -- which is exactly what happened here:
the probes hardcoded the right profile path while the adapter computed the wrong
one, so every probe was green and every run was signed out.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from generator_trunk.AI_combi_testing_platform.adapters import browser as B  # noqa: E402


def target_url() -> str:
    """The chat endpoint to probe, resolved exactly as the adapter resolves it.

    Probes must never carry their own copy of the target: a probe that agreed
    with a stale URL would report a healthy session for a page the real run
    never visits.
    """
    return B._target_url()


def launch(headless: bool = True, width: int = 1440, height: int = 1000):
    """Return (driver, profile_dir) using the adapter's own profile logic.

    The WebDriver package is whichever one the adapter is configured to use, so
    a probe and the adapter can never drift apart.
    """
    uc = importlib.import_module(
        os.environ.get(B.DRIVER_MODULE_ENV) or B.DEFAULT_DRIVER_MODULE)
    from selenium.webdriver.firefox.options import Options as FirefoxOptions

    profile = B._derive_profile(B._default_profile())
    options = FirefoxOptions()
    if headless:
        options.add_argument("-headless")
    options.add_argument("-profile")
    options.add_argument(profile)
    driver = uc.Firefox(options=options)
    driver.set_window_size(width, height)
    return driver, profile


def cleanup(driver, profile: str) -> None:
    try:
        driver.quit()
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def labels(driver, selector: str = "button, a, [role='button']") -> list[str]:
    """aria-label (or text) of every matching control, stale nodes skipped."""
    from selenium.webdriver.common.by import By

    found = []
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        try:
            text = (element.get_attribute("aria-label") or element.text or "").strip()
        except Exception:
            continue
        if text:
            found.append(text)
    return found
