"""The canonical optional-table contract (docs/32 finding F4).

The invariant: ``R ⊆ P`` — the Reader may not consume an `fw_opt<size>` table
Core never produced. Before this contract existed, both properties were derived
independently and nothing stated or checked the relationship; every standalone
property template violated it. These tests pin the invariant, the exact
multiplier, and the fact that the two properties can no longer drift apart.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bundle import architecture as arch
from bundle.optional_contract import (
    CORE_PROPERTY, MODE_COMPLETE, MODE_EXPLICIT_SUBSET, OptionalContractError,
    OptionalTableContract, READER_PROPERTY, contract_for_sheet_count,
    contract_from_properties, contract_from_spec, validate_contract, verify_materialized,
)

REPO_ROOT = arch.REPO_ROOT


def _spec(*optional_value_counts: int, mandatory: int = 1):
    """A stand-in spec: `mandatory` plain slots plus one FW_Optional slot per
    entry in *optional_value_counts*."""
    slots = [SimpleNamespace(sheet=f"M{i}", values=["a"], flags=()) for i in range(mandatory)]
    slots += [SimpleNamespace(sheet=f"OPT{i}", values=["v"] * n, flags=("FW_Optional",))
              for i, n in enumerate(optional_value_counts)]
    return SimpleNamespace(slots=slots, seq_extra=[])


# ------------------------------------------------------------ construction ---
def test_no_optional_sheets_is_inactive_and_multiplies_by_one() -> None:
    contract = contract_from_spec(_spec())
    assert contract.active is False
    assert contract.produced_sizes == () and contract.consumed_sizes == ()
    assert contract.expected_multiplier() == 1
    assert contract.core_edits() == {}
    assert contract.reader_edits() == {"reader.core.processIsOpt": "false"}


def test_one_optional_sheet() -> None:
    contract = contract_from_spec(_spec(1))
    assert contract.produced_sizes == (1,) and contract.consumed_sizes == (1,)
    assert contract.expected_multiplier() == 2          # absent, or present


def test_three_optional_sheets_produce_and_consume_sizes_1_2_3() -> None:
    contract = contract_from_spec(_spec(1, 1, 1))
    assert contract.produced_sizes == (1, 2, 3)
    assert contract.consumed_sizes == (1, 2, 3)
    assert contract.core_edits()[CORE_PROPERTY] == "1,2,3"
    assert contract.reader_edits()[READER_PROPERTY] == "1,2,3"
    # C(3,1)+C(3,2)+C(3,3) = 3+3+1 = 7 combinations, plus the absent branch.
    assert [contract.combinations_of_size(k) for k in (1, 2, 3)] == [3, 3, 1]
    assert contract.expected_multiplier() == 8


def test_the_docs_27_worked_example_reproduces_exactly() -> None:
    """Four one-valued optional slots -> fw_opt1..4 with 4, 6, 4, 1 rows, so the
    Reader emits |fw_final| x 16."""
    contract = contract_from_spec(_spec(1, 1, 1, 1))
    assert [contract.combinations_of_size(k) for k in (1, 2, 3, 4)] == [4, 6, 4, 1]
    assert contract.expected_multiplier() == 16


def test_multi_valued_optional_slots_match_the_legacy_product_formula() -> None:
    """The launcher's historical factor was Pi(n_i + 1). The contract computes
    1 + sum of elementary symmetric polynomials, which must agree exactly for a
    complete run -- and additionally stays exact for a subset, which the product
    formula cannot express."""
    for counts in [(1,), (2,), (1, 1), (2, 3), (1, 2, 3), (2, 2, 2, 2)]:
        contract = contract_from_spec(_spec(*counts))
        product = 1
        for n in counts:
            product *= (n + 1)
        assert contract.expected_multiplier() == product, counts


def test_an_intentional_subset_is_a_named_mode_with_exact_semantics() -> None:
    contract = contract_from_spec(_spec(1, 1, 1), consumed_override="1,3")
    assert contract.mode == MODE_EXPLICIT_SUBSET
    assert contract.consumed_sizes == (1, 3)
    assert contract.required_tables() == ("fw_opt1", "fw_opt3")
    assert contract.expected_multiplier() == 1 + 3 + 1     # absent + e1 + e3
    validate_contract(contract)                            # a subset is legal...


# --------------------------------------------------------------- invariant ---
def test_reader_may_not_consume_a_table_core_does_not_produce() -> None:
    """The core invariant, stated as an error a human can act on."""
    with pytest.raises(OptionalContractError) as excinfo:
        contract_from_properties("1,2", "1,2,3", optional_sheet_count=3)
    message = str(excinfo.value)
    assert "must be a subset" in message
    assert CORE_PROPERTY in message and READER_PROPERTY in message


def test_a_size_beyond_the_declared_sheet_count_is_rejected() -> None:
    with pytest.raises(OptionalContractError, match="exceeds the 2 declared"):
        contract_from_properties("1,2,3", "1,2,3", optional_sheet_count=2)


@pytest.mark.parametrize("bad,match", [
    ("1,1,2", "duplicate"),
    ("0,1", "must be >= 1"),
    ("-1", "must be >= 1"),
    ("1,,2", "empty entry"),
    ("1,two", "not an integer"),
])
def test_malformed_size_lists_fail_with_stable_diagnostics(bad: str, match: str) -> None:
    with pytest.raises(OptionalContractError, match=match):
        contract_from_properties(bad, bad, optional_sheet_count=4)


def test_a_contract_claiming_complete_while_consuming_a_subset_is_incoherent() -> None:
    contract = OptionalTableContract(
        optional_sheet_count=3, slot_value_counts=(1, 1, 1),
        produced_sizes=(1, 2, 3), consumed_sizes=(1, 2), mode=MODE_COMPLETE, sources={})
    with pytest.raises(OptionalContractError, match="must declare mode"):
        validate_contract(contract)


def test_optional_sizes_without_optional_sheets_are_rejected() -> None:
    contract = OptionalTableContract(
        optional_sheet_count=0, slot_value_counts=(), produced_sizes=(1,), consumed_sizes=(1,),
        mode=MODE_COMPLETE, sources={})
    # The size-vs-sheet-count check fires first and says the same thing more
    # precisely: there is no size-1 combination over zero optional sheets.
    with pytest.raises(OptionalContractError, match="exceeds the 0 declared"):
        validate_contract(contract)


# ------------------------------------------------------- materialization -----
def test_missing_optional_tables_fail_before_the_reader_starts() -> None:
    contract = contract_from_spec(_spec(1, 1))
    verify_materialized(contract, ["fw_final", "fw_opt1", "fw_opt2"])       # complete
    with pytest.raises(OptionalContractError) as excinfo:
        verify_materialized(contract, ["fw_final", "fw_opt1"])
    assert "fw_opt2" in str(excinfo.value)
    assert "Refusing to start the Reader" in str(excinfo.value)


def test_materialization_check_is_case_insensitive_and_inactive_when_unused() -> None:
    verify_materialized(contract_from_spec(_spec()), [])                    # no optional sheets
    verify_materialized(contract_from_spec(_spec(1)), ["FW_OPT1"])          # PostgreSQL folding


# --------------------------------------------- one contract, two properties --
def test_both_properties_are_rendered_from_the_same_contract() -> None:
    """The structural fix: the producer and consumer lists cannot drift because
    neither is written independently."""
    contract = contract_from_spec(_spec(1, 1, 1))
    assert contract.core_edits()[CORE_PROPERTY] == contract.reader_edits()[READER_PROPERTY]
    reader = contract.reader_edits()
    assert reader["reader.core.processIsOpt"] == "true"
    assert reader["reader.core.processBothFinalAndOpt"] == "true"


def test_the_legacy_n_opt_call_path_renders_the_same_values() -> None:
    """`stage_core`/`stage_reader` still accept a bare `n_opt` (benchmarks, direct
    callers). That path must produce the identical properties, or the drift the
    contract removes would simply reappear one call site over."""
    for n in range(0, 5):
        legacy = contract_for_sheet_count(n)
        spec_based = contract_from_spec(_spec(*([1] * n)))
        assert legacy.core_edits() == spec_based.core_edits()
        assert legacy.reader_edits() == spec_based.reader_edits()
        assert legacy.expected_multiplier() == spec_based.expected_multiplier()


# --------------------------------------- the standalone property templates ---
#: The templates the audit found violating R ⊆ P, with the sheet count each is
#: written for. They are development profiles, not the Bundle-rendered run
#: contract; the point of this test is that they are now checked at all.
_TEMPLATES = (
    ("Core_trunk/fw.properties", 4),
    ("Reader_trunk/fw.properties", 4),
    ("generator_trunk/config/core.fw.properties", 3),
    ("generator_trunk/config/reader.fw.properties", 3),
)


def _read_property(path: Path, key: str) -> "str | None":
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            return value.strip()
    return None


def _active_property_values(path: Path, key: str) -> list[str]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == key:
            values.append(value.strip())
    return values


@pytest.mark.parametrize("relative,sheet_count", _TEMPLATES, ids=lambda v: str(v))
def test_standalone_property_templates_satisfy_the_contract(relative, sheet_count) -> None:
    """Audit F4: `Core_trunk/fw.properties` produced size 4 while consuming
    1,2,3,4; `Reader_trunk/fw.properties` produced 1,2,3 while consuming 4. The
    launcher path was always correct, so this was latent — but a standalone
    component launch would have hit it with no preflight to catch it."""
    if isinstance(relative, tuple):                       # parametrize id helper
        relative, sheet_count = relative
    path = REPO_ROOT / relative
    if not path.is_file():
        pytest.skip(f"{relative} is not present in this checkout")
    produced = _read_property(path, CORE_PROPERTY)
    consumed = _read_property(path, READER_PROPERTY)
    if produced is None and consumed is None:
        pytest.skip(f"{relative} declares neither optional property")
    contract_from_properties(produced or "", consumed or "",
                             optional_sheet_count=sheet_count, source=relative)
    # Java Properties accepts duplicate keys with last-one-wins semantics. A
    # duplicate is therefore another hidden contract and must not be allowed.
    assert len(_active_property_values(path, CORE_PROPERTY)) <= 1, relative
    assert len(_active_property_values(path, READER_PROPERTY)) <= 1, relative
