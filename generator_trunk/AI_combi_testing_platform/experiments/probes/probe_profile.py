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

"""Probe 5 — which Firefox profile gets used, and does it carry the session?

This is the cheapest probe and it would have saved the most time. `profiles.ini`
commonly holds two profiles: an old one marked with the legacy ``Default=1`` and
an ``[InstallXXXX]`` section whose ``Default=<path>`` is what modern Firefox
actually launches. Preferring ``Default=1`` selects a stale, empty profile that
starts perfectly well and is simply signed out — so the symptom is not an error
but a signed-out page, which reads as "the session expired" and sends diagnosis
in entirely the wrong direction.

Runs no browser: pure inspection of profiles.ini and the cookie jar.

    python3 probes/probe_profile.py
"""
from __future__ import annotations

import configparser
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from _common import B

BASE = Path(os.path.expanduser("~/.mozilla/firefox"))


def main() -> int:
    ini = BASE / "profiles.ini"
    if not ini.is_file():
        print(f"no profiles.ini at {ini}")
        return 1

    parser = configparser.ConfigParser()
    parser.read(ini)

    print("profiles.ini declares:")
    install_default = None
    for section in parser.sections():
        path = parser.get(section, "Path", fallback="")
        name = parser.get(section, "Name", fallback="")
        default = parser.get(section, "Default", fallback="")
        if section.startswith("Install") and default:
            install_default = default
            print(f"  [{section}] Default={default}   <- authoritative for current Firefox")
        elif path:
            marker = "  <- legacy Default=1 marker" if default == "1" else ""
            print(f"  [{section}] Name={name:16} Path={path}{marker}")

    chosen = B._default_profile()
    print(f"\nadapter resolves to: {chosen}")
    if install_default and not chosen.endswith(install_default):
        print(f"  !! MISMATCH: [Install*] names {install_default!r}")
        return 2

    cookies = Path(chosen) / "cookies.sqlite"
    if not cookies.is_file():
        print("  !! chosen profile has no cookies.sqlite — it will be signed out")
        return 3

    tmp = tempfile.mktemp(suffix=".sqlite")
    shutil.copy(cookies, tmp)
    try:
        connection = sqlite3.connect(tmp)
        total = connection.execute(
            "select count(*) from moz_cookies where host like '%google%'").fetchone()[0]
        now = int(time.time())
        rows = connection.execute(
            "select name, expiry from moz_cookies where host like '%google%' "
            "and name in ('SID','__Secure-1PSID','SSID','HSID')").fetchall()
        print(f"\ngoogle cookies in chosen profile: {total}")
        for name, expiry in rows:
            status = "never" if not expiry else ("VALID" if expiry > now else "EXPIRED")
            print(f"  {name:18} {status}")
        ok = total > 0 and all(e > now for _n, e in rows if e)
        print(f"\nRESULT: {'session looks usable' if ok else 'session missing or expired'}")
        return 0 if ok else 4
    finally:
        os.unlink(tmp)


if __name__ == "__main__":
    sys.exit(main())
