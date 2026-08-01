#!/usr/bin/env python3
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
