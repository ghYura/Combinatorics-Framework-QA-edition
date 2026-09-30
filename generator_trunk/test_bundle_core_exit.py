# SPDX-License-Identifier: LicenseRef-BUSL-1.1
"""A failed Core process cannot promote leftover rows into a successful stage."""

from unittest.mock import Mock
from subprocess import CompletedProcess

import pytest

import fwgen
from bundle import stages
from bundle.errors import StageError


@pytest.mark.parametrize("status", [1, 124, 137])
def test_failed_core_refuses_stale_or_partial_database_rows(monkeypatch, tmp_path, status):
    spec = fwgen.Spec(name="failed_core", title="failed core", slots=[
        fwgen.Slot("A", "a", ["a", "b"]),
    ])
    # A stale table would satisfy the old success check even when Core failed
    # or was terminated. Database reads must wait for successful process exit.
    query = Mock(return_value=("2", 0))
    monkeypatch.setattr(stages, "psql", query)
    monkeypatch.setattr(stages, "run", lambda *args, **kwargs: CompletedProcess([], status, "", ""))
    monkeypatch.setattr(stages, "_props", lambda *args, **kwargs: None)

    with pytest.raises(StageError, match=f"Core exited with status {status}"):
        stages.stage_core(spec, tmp_path / "input.xlsx", tmp_path, "failed_core", 5433)
    query.assert_not_called()
