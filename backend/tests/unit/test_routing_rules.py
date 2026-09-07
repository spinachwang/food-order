"""Unit tests for the F002 routing layer's static tables (`rules.py`).

Covers F002 §3.3 + §7:
- All rule `cuisines` are valid cuisine ids; `reason` ≤30 字
- No duplicate tags inside `EXPLICIT_RULES` or `MODIFIER_RULES`
- All rule keywords ≥2 chars (regression guard — single-char keywords
  cause substring false positives like "我快到了" → fastfood)
- `sample_by_weights` covers all degenerate cases + reproducibility
"""

from __future__ import annotations

import math
import random

import pytest
from app.agents.routing.rules import (
    AMBIENT_KEYWORDS,
    CONTRADICTORY_TAGS,
    EXPLICIT_RULES,
    MAX_REASON_CODEPOINTS,
    MODIFIER_RULES,
    Rule,
    is_ambient_message,
    match_rules,
    sample_by_weights,
)
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Table integrity
# ---------------------------------------------------------------------------


class TestExplicitRulesTable:
    def test_count_matches_cuisine_ids(self) -> None:
        # One explicit rule per cuisine — never more, never less.
        assert len(EXPLICIT_RULES) == len(CUISINE_IDS)

    def test_each_rule_targets_a_distinct_cuisine(self) -> None:
        tags = [rule.tag for rule in EXPLICIT_RULES]
        assert len(tags) == len(set(tags)), f"duplicate tags: {tags}"
        assert set(tags) == set(CUISINE_IDS), (
            f"explicit tags must cover all 14 cuisines, got {sorted(tags)}"
        )

    def test_each_rule_cuisines_subset_of_cuisine_ids(self) -> None:
        for rule in EXPLICIT_RULES:
            for cuisine in rule.cuisines:
                assert cuisine in CUISINE_IDS, f"{rule.tag} → unknown cuisine {cuisine}"

    def test_each_rule_reasons_within_codepoint_limit(self) -> None:
        for rule in EXPLICIT_RULES:
            assert len(rule.reason) <= MAX_REASON_CODEPOINTS, (
                f"{rule.tag} reason too long ({len(rule.reason)} chars): {rule.reason!r}"
            )

    def test_keywords_all_two_chars_or_more(self) -> None:
        # Regression guard — single-char keywords substring-match false positives
        # like "我快到了" → fastfood. Locked down by F002 §3.3.
        for rule in EXPLICIT_RULES:
            for kw in rule.keywords:
                assert len(kw) >= 2, (
                    f"{rule.tag} has 1-char keyword {kw!r} — would cause substring false positives"
                )


class TestModifierRulesTable:
    def test_no_duplicate_tags(self) -> None:
        tags = [rule.tag for rule in MODIFIER_RULES]
        assert len(tags) == len(set(tags)), f"duplicate modifier tags: {tags}"

    def test_no_tag_collides_with_explicit_rules(self) -> None:
        explicit_tags = {rule.tag for rule in EXPLICIT_RULES}
        modifier_tags = {rule.tag for rule in MODIFIER_RULES}
        assert explicit_tags.isdisjoint(modifier_tags), explicit_tags & modifier_tags

    def test_each_rule_cuisines_subset_of_cuisine_ids(self) -> None:
        for rule in MODIFIER_RULES:
            for cuisine in rule.cuisines:
                assert cuisine in CUISINE_IDS, f"{rule.tag} → unknown cuisine {cuisine}"

    def test_each_rule_reasons_within_codepoint_limit(self) -> None:
        for rule in MODIFIER_RULES:
            assert len(rule.reason) <= MAX_REASON_CODEPOINTS, (
                f"{rule.tag} reason too long ({len(rule.reason)} chars): {rule.reason!r}"
            )

    def test_keywords_all_two_chars_or_more(self) -> None:
        for rule in MODIFIER_RULES:
            for kw in rule.keywords:
                assert len(kw) >= 2, (
                    f"{rule.tag} has 1-char keyword {kw!r} — substring false positive risk"
                )


class TestAmbientKeywords:
    def test_at_least_seven_phrases(self) -> None:
        # Spec §3.3 lists: 随便 / 都行 / 无所谓 / 你决定 / 看你 / 帮我选 / 你来
        assert len(AMBIENT_KEYWORDS) >= 7

    def test_all_ambient_phrases_are_two_chars_or_more(self) -> None:
        for kw in AMBIENT_KEYWORDS:
            assert len(kw) >= 2, kw

    def test_is_ambient_message_true_for_canonical_phrases(self) -> None:
        for kw in AMBIENT_KEYWORDS:
            assert is_ambient_message(kw), kw
            assert is_ambient_message(f"今天{kw}"), kw
            assert is_ambient_message(f"  {kw}  "), kw

    def test_is_ambient_message_false_for_concrete_cravings(self) -> None:
        assert not is_ambient_message("想吃辣")
        assert not is_ambient_message("想吃川菜")
        assert not is_ambient_message("今天天气不错")
        assert not is_ambient_message("")


class TestContradictoryTags:
    def test_spicy_and_light_are_marked_contradictory(self) -> None:
        # Per spec §3.3 — these are the mutually-exclusive intent tags.
        assert "spicy" in CONTRADICTORY_TAGS
        assert "light" in CONTRADICTORY_TAGS


class TestRuleDataclass:
    def test_rule_is_immutable(self) -> None:
        rule = Rule(tag="t", keywords=("a",), cuisines=("sichuan",), reason="r")
        with pytest.raises((AttributeError, TypeError)):
            rule.tag = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# match_rules — intent-tag partitioning
# ---------------------------------------------------------------------------


class TestMatchRules:
    def test_explicit_naming_wins_over_modifier(self) -> None:
        # "日料，清淡的" → explicit japanese + modifier light both fire,
        # but explicit wins (japanese is kept in first position).
        result = match_rules("日料，清淡的")
        tags = [rule.tag for rule in result]
        assert "japanese" in tags
        assert "light" in tags
        assert tags.index("japanese") < tags.index("light")

    def test_contradictory_modifiers_without_explicit(self) -> None:
        # spicy + light simultaneously with no explicit naming → escalate.
        # match_rules should still return both (so the caller can detect the
        # contradiction), but RouterOutput has to escalate. We verify
        # detection here by checking both rules fire on the message.
        result = match_rules("想吃辣的，清淡的")
        tags = {rule.tag for rule in result}
        assert "spicy" in tags and "light" in tags

    def test_no_match_returns_empty(self) -> None:
        # Pure gray-zone phrasing: no keyword in any rule fires.
        assert match_rules("想吃点暖胃的") == []

    def test_garbage_message_returns_empty(self) -> None:
        # Caller (route_cuisines) is responsible for the empty/garbage short-
        # circuit, but match_rules itself should not crash on non-keyword text.
        assert match_rules("！！！@#￥") == []

    def test_each_matched_rule_targets_a_real_cuisine(self) -> None:
        result = match_rules("想吃辣的")
        assert len(result) >= 1
        for rule in result:
            for cuisine in rule.cuisines:
                assert cuisine in CUISINE_IDS


# ---------------------------------------------------------------------------
# sample_by_weights — degenerate cases + reproducibility
# ---------------------------------------------------------------------------


class TestSampleByWeights:
    def test_all_zero_weights_returns_n_items_without_crash(self) -> None:
        # When allergy filter zeroes everything, we still need a sample —
        # not an exception, not an infinite loop.
        rng = random.Random(42)
        weights = {c: 0.0 for c in CUISINE_IDS}
        sample = sample_by_weights(weights, n=2, rng=rng)
        assert len(sample) == 2
        assert set(sample) <= set(CUISINE_IDS)

    def test_fewer_candidates_than_n_returns_all(self) -> None:
        rng = random.Random(0)
        sample = sample_by_weights({"sichuan": 0.5}, n=3, rng=rng)
        assert sample == ["sichuan"]

    def test_negative_weights_are_clamped_to_zero(self) -> None:
        rng = random.Random(0)
        weights = {"sichuan": -0.1, "cantonese": 1.0}
        sample = sample_by_weights(weights, n=1, rng=rng)
        assert sample == ["cantonese"]  # only positive-weight key can win

    def test_nan_and_inf_treated_as_zero(self) -> None:
        rng = random.Random(0)
        weights = {"sichuan": math.nan, "cantonese": math.inf, "hunan": 0.0}
        sample = sample_by_weights(weights, n=1, rng=rng)
        # NaN/inf are not finite, so all weights clamp to 0 → uniform fallback.
        # The point of this test is "must not raise"; any key is acceptable.
        assert len(sample) == 1
        assert sample[0] in {"sichuan", "cantonese", "hunan"}

    def test_does_not_return_replacement(self) -> None:
        rng = random.Random(7)
        weights = dict.fromkeys(CUISINE_IDS, 1.0)
        sample = sample_by_weights(weights, n=5, rng=rng)
        assert len(sample) == len(set(sample)), f"replacement occurred: {sample}"

    def test_deterministic_with_fixed_seed(self) -> None:
        weights = {"sichuan": 0.9, "cantonese": 0.1, "hunan": 0.5}
        sample_a = sample_by_weights(weights, n=2, rng=random.Random(123))
        sample_b = sample_by_weights(weights, n=2, rng=random.Random(123))
        assert sample_a == sample_b

    def test_high_weight_dominates_over_many_trials(self) -> None:
        # Statistical guard — with a high weight on sichuan and low on others,
        # sichuan should win substantially more often than chance.
        rng = random.Random(0)
        weights = {"sichuan": 0.9, "cantonese": 0.1, "hunan": 0.1}
        wins = sum(
            sample[0] == "sichuan"
            for _ in range(2000)
            if (sample := sample_by_weights(weights, n=1, rng=rng))
        )
        # 0.9 / (0.9 + 0.1 + 0.1) = 0.82; allow ±0.05.
        assert 0.75 <= wins / 2000 <= 0.90, wins / 2000
