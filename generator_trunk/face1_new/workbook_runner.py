"""Run Bundle with an exact Face 1 workbook instead of regenerating one.

The normal launcher remains authoritative for preflight, budgets, stage journals,
Core/Reader/Executor/Analyzer behavior, cancellation semantics and results.  The
only substitution is the Generator stage: it validates and copies the workbook
already authored by the user into the run directory.

The substitution is passed as a `StageTable` (``bundle.stagetable``) rather than
rebound on ``bundle.cli``, so it is visible at the call site and unaffected by
where the orchestrator happens to live.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


def exact_workbook_stage_table(workbook: Path):
    """The production stage table with only the Generator substituted.

    Returns a `StageTable` rather than rebinding ``bundle.cli.stage_gen``: the
    substitution is then visible in the call that uses it, and it survives the
    orchestrator moving between modules.
    """
    import bundle.cli as bundle_cli
    from bundle.errors import StageError, ok
    import fwgen

    source = workbook.resolve()

    def stage_exact_workbook(_spec_dir, scratch):
        print("\n[1/5] USE exact Face 1 workbook (generation bypassed)")
        out = Path(scratch) / "wb"
        out.mkdir(parents=True, exist_ok=True)
        destination = out / source.name
        shutil.copy2(source, destination)
        errors = fwgen.validate_workbook(destination)
        if errors:
            raise StageError("Face 1 workbook failed Core linter: " + "; ".join(errors[:10]))
        ok(f"exact workbook -> {destination.name} (validated; directive positions preserved)")
        return destination

    return bundle_cli.default_stage_table().with_(gen=stage_exact_workbook)


def parse_args(argv: list[str] | None = None) -> tuple[Path, list[str]]:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        divider = values.index("--")
    except ValueError as exc:
        raise SystemExit("workbook_runner requires '--' before bundle arguments") from exc
    parser = argparse.ArgumentParser(description="Run Bundle using an existing validated Core workbook")
    parser.add_argument("--workbook", required=True, type=Path)
    own = parser.parse_args(values[:divider])
    bundle_args = values[divider + 1:]
    if not bundle_args:
        raise SystemExit("no Bundle arguments supplied after '--'")
    return own.workbook, bundle_args


def main(argv: list[str] | None = None) -> None:
    workbook, bundle_args = parse_args(argv)
    if not workbook.is_file():
        raise SystemExit(f"workbook not found: {workbook}")
    stages = exact_workbook_stage_table(workbook)
    import bundle.cli as bundle_cli
    old_argv = sys.argv
    try:
        sys.argv = ["bundle_run.py", *bundle_args]
        bundle_cli.main(stages=stages)
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
