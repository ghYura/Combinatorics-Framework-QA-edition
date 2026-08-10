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

from __future__ import annotations

import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

EXPECTED_GRPC_TOOLS = "1.82.1"


def main() -> int:
    try:
        installed_version = version("grpcio-tools")
    except PackageNotFoundError:
        print(
            f"grpcio-tools {EXPECTED_GRPC_TOOLS} is required; install the gateway dependencies first.",
            file=sys.stderr,
        )
        return 2
    if installed_version != EXPECTED_GRPC_TOOLS:
        print(
            f"grpcio-tools {EXPECTED_GRPC_TOOLS} is required, but {installed_version} is installed.",
            file=sys.stderr,
        )
        return 2

    gen_dir = Path(__file__).resolve().parents[2]
    out_dir = Path(__file__).resolve().parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").write_text('"""Generated gRPC stubs for the Evaluation Gateway proto."""\n',
                                         encoding="utf-8")
    proto = gen_dir / "proto" / "evaluation_gateway.proto"
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{gen_dir / 'proto'}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        str(proto),
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
