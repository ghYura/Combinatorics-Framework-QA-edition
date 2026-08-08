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

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Sequence, Union

Argv = Union[str, Sequence[str]]


@dataclass(frozen=True)
class CommandResult:
    """Immutable, typed outcome of a subprocess invocation.

    Replaces passing raw ``subprocess.CompletedProcess`` between stage helpers so
    every caller sees the same shape: argv, exit status, captured streams, timing
    and an explicit timeout flag (a timeout is not just "some non-zero exit").
    """

    argv: tuple
    display: str
    returncode: int
    stdout: str
    stderr: str
    start: float
    end: float
    duration: float
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _argv_tuple(cmd: Argv) -> tuple:
    return (cmd,) if isinstance(cmd, str) else tuple(str(c) for c in cmd)


def _display(cmd: Argv) -> str:
    return cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)


def _decode(blob) -> str:
    if blob is None:
        return ""
    return blob if isinstance(blob, str) else blob.decode("utf-8", "replace")


def run(cmd: Argv, *, timeout: Optional[float] = None, **kw) -> CommandResult:
    """Run *cmd* and return a typed, immutable :class:`CommandResult`.

    ``cmd`` should be a list argv; a string is accepted only for the legacy
    shell commands that cannot yet be expressed as argv.
    Never logs argv or captured output itself — secrets (DB passwords, JDBC
    URLs) may be embedded in either, and surfacing them is the caller's
    explicit, reasoned choice.
    """
    start = time.time()
    timed_out = False
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, timeout=timeout, **kw)
        returncode, stdout, stderr = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = _decode(exc.stdout)
        stderr = _decode(exc.stderr)
    end = time.time()
    return CommandResult(
        argv=_argv_tuple(cmd),
        display=_display(cmd),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        start=start,
        end=end,
        duration=end - start,
        timed_out=timed_out,
    )
