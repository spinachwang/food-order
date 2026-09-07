"""Unit tests for the F002 allergy conflict table (`routing/allergies.py`).

Covers F002 §3.3 conflict-table scope (strict "100% conflict" — only the
3 cuisines where the cuisine is essentially off-limits) and the immutability
contract on the helper that zeros out weights for the fuzzy routing path.
"""

from __future__ import annotations

from app.agents.routing.allergies import (
    HARD_ALLERGY_CONFLICTS,
    filter_conflicts,
    zero_out_conflicts,
)
from app.core.constants import ALLERGY_VALUES, CUISINE_IDS

# ---------------------------------------------------------------------------
# Table integrity
# ---------------------------------------------------------------------------


class TestConflictTable:
    def test_keys_subset_of_cuisine_ids(self) -> None:
        for cuisine in HARD_ALLERGY_CONFLICTS:
            assert cuisine in CUISINE_IDS, f"unknown cuisine: {cuisine}"

    def test_values_subset_of_allergy_values(self) -> None:
        for cuisine, allergies in HARD_ALLERGY_CONFLICTS.items():
            for allergy in allergies:
                assert allergy in ALLERGY_VALUES, f"{cuisine} has unknown allergy {allergy!r}"

    def test_table_contains_only_three_cuisines(self) -> None:
        # F002 §3.3 — strict "100% conflict" scope, deliberately conservative.
        assert set(HARD_ALLERGY_CONFLICTS.keys()) == {"fujian", "western_fastfood", "sichuan"}

    def test_fujian_blocks_shellfish_and_fish(self) -> None:
        assert "shellfish" in HARD_ALLERGY_CONFLICTS["fujian"]
        assert "fish" in HARD_ALLERGY_CONFLICTS["fujian"]

    def test_western_fastfood_blocks_fried_food(self) -> None:
        assert HARD_ALLERGY_CONFLICTS["western_fastfood"] == frozenset({"fried_food"})

    def test_sichuan_blocks_peanut(self) -> None:
        assert HARD_ALLERGY_CONFLICTS["sichuan"] == frozenset({"peanut"})


# ---------------------------------------------------------------------------
# filter_conflicts
# ---------------------------------------------------------------------------


class TestFilterConflicts:
    def test_sichuan_filtered_when_peanut_allergic(self) -> None:
        result = filter_conflicts(["sichuan", "cantonese"], {"peanut"})
        assert "sichuan" not in result
        assert "cantonese" in result

    def test_fujian_filtered_when_shellfish_allergic(self) -> None:
        result = filter_conflicts(["fujian", "suzhou"], {"shellfish"})
        assert "fujian" not in result
        assert "suzhou" in result

    def test_fujian_filtered_when_fish_allergic(self) -> None:
        result = filter_conflicts(["fujian"], {"fish"})
        assert result == []

    def test_western_fastfood_filtered_when_fried_food_allergic(self) -> None:
        result = filter_conflicts(["western_fastfood"], {"fried_food"})
        assert result == []

    def test_allergies_outside_conflict_table_are_no_op(self) -> None:
        # soy / wheat / dairy are NOT in the hard-conflict table — they
        # belong to dish-level filtering in the cuisine expert, not the router.
        result = filter_conflicts(["cantonese", "suzhou", "western"], {"soy", "wheat", "dairy"})
        assert result == ["cantonese", "suzhou", "western"]

    def test_empty_allergy_set_returns_input_unchanged(self) -> None:
        result = filter_conflicts(["sichuan", "cantonese"], set())
        assert result == ["sichuan", "cantonese"]

    def test_empty_cuisine_set_returns_empty(self) -> None:
        assert filter_conflicts([], {"peanut"}) == []

    def test_does_not_mutate_input_list(self) -> None:
        original = ["sichuan", "cantonese"]
        filter_conflicts(original, {"peanut"})
        assert original == ["sichuan", "cantonese"]


# ---------------------------------------------------------------------------
# zero_out_conflicts — fuzzy routing path
# ---------------------------------------------------------------------------


class TestZeroOutConflicts:
    def test_returns_new_dict(self) -> None:
        weights = {"sichuan": 0.8, "cantonese": 0.5}
        new_weights = zero_out_conflicts(weights, {"peanut"})
        assert new_weights is not weights

    def test_zeros_out_sichuan_when_peanut_allergic(self) -> None:
        weights = {"sichuan": 0.8, "cantonese": 0.5, "hunan": 0.5}
        new_weights = zero_out_conflicts(weights, {"peanut"})
        assert new_weights["sichuan"] == 0.0
        assert new_weights["cantonese"] == 0.5
        assert new_weights["hunan"] == 0.5

    def test_unknown_allergies_are_no_op(self) -> None:
        weights = {"cantonese": 0.5, "suzhou": 0.5}
        new_weights = zero_out_conflicts(weights, {"soy", "wheat"})
        assert new_weights == weights
        assert new_weights is not weights  # still returns a fresh dict

    def test_does_not_mutate_input(self) -> None:
        weights = {"sichuan": 0.8, "cantonese": 0.5}
        snapshot = dict(weights)
        zero_out_conflicts(weights, {"peanut"})
        assert weights == snapshot

    def test_all_zero_result_is_supported(self) -> None:
        # Every cuisine is conflicted (hypothetical) — must not raise.
        weights = {"sichuan": 0.8}
        new_weights = zero_out_conflicts(weights, {"peanut"})
        assert new_weights["sichuan"] == 0.0
