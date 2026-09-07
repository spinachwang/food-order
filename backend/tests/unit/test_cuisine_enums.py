"""Unit tests for shared domain constants — the foundation for F001 / F003."""
from __future__ import annotations

from app.core.constants import (
    ALLERGY_VALUES,
    CUISINE_IDS,
    DEFAULT_LLM_MODEL,
    SPICE_TOLERANCE_RANGE,
    TEMPERATURE_VALUES,
)


class TestCuisineIds:
    def test_has_exactly_14_entries(self) -> None:
        assert len(CUISINE_IDS) == 14

    def test_no_duplicates(self) -> None:
        assert len(set(CUISINE_IDS)) == len(CUISINE_IDS)

    def test_expected_canonical_set(self) -> None:
        expected = {
            "sichuan", "cantonese", "shandong", "suzhou", "zhejiang",
            "fujian", "hunan", "anhui", "japanese", "western",
            "western_fastfood", "chinese_fastfood", "snacks", "dessert_drinks",
        }
        assert set(CUISINE_IDS) == expected

    def test_is_immutable_tuple(self) -> None:
        # Tuple, not list — protects against mutation in agent code.
        assert isinstance(CUISINE_IDS, tuple)


class TestAllergyValues:
    def test_includes_eleven_known_allergens(self) -> None:
        expected = {
            "peanut", "tree_nut", "shellfish", "fish", "egg", "soy",
            "wheat", "dairy", "sesame", "alcohol", "fried_food",
        }
        assert expected == ALLERGY_VALUES

    def test_is_frozenset(self) -> None:
        assert isinstance(ALLERGY_VALUES, frozenset)


class TestSpiceToleranceRange:
    def test_range_is_0_through_3(self) -> None:
        assert SPICE_TOLERANCE_RANGE == (0, 3)


class TestTemperatureValues:
    def test_three_canonical_values(self) -> None:
        assert frozenset({"cold", "room", "hot"}) == TEMPERATURE_VALUES

    def test_is_frozenset(self) -> None:
        assert isinstance(TEMPERATURE_VALUES, frozenset)


class TestDefaultLlmModel:
    def test_default_model_is_minimax_m3(self) -> None:
        # Per F003 §8.1 — all 14 cuisine experts must use a unified model.
        assert DEFAULT_LLM_MODEL == "MiniMax-M3"
        assert "M3" in DEFAULT_LLM_MODEL