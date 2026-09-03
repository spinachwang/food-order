"""`CUISINE_REGISTRY` — F003 §3.2 maps `cuisine_id` to its expert instance.

This registry is the single source of truth for which cuisines exist. The order
matches `CUISINE_IDS` in `app.core.constants` so iteration is deterministic
(useful for stable UI ordering).
"""
from __future__ import annotations

from app.agents.cuisines.base import BaseCuisineExpert
from app.agents.cuisines.sichuan import SichuanExpert
from app.agents.cuisines.stubs.anhui import AnhuiExpert
from app.agents.cuisines.stubs.cantonese import CantoneseExpert
from app.agents.cuisines.stubs.chinese_fastfood import ChineseFastfoodExpert
from app.agents.cuisines.stubs.dessert_drinks import DessertDrinksExpert
from app.agents.cuisines.stubs.fujian import FujianExpert
from app.agents.cuisines.stubs.hunan import HunanExpert
from app.agents.cuisines.stubs.japanese import JapaneseExpert
from app.agents.cuisines.stubs.shandong import ShandongExpert
from app.agents.cuisines.stubs.snacks import SnacksExpert
from app.agents.cuisines.stubs.suzhou import SuzhouExpert
from app.agents.cuisines.stubs.western import WesternExpert
from app.agents.cuisines.stubs.western_fastfood import WesternFastfoodExpert
from app.agents.cuisines.stubs.zhejiang import ZhejiangExpert
from app.core.constants import CUISINE_IDS

CUISINE_REGISTRY: dict[str, BaseCuisineExpert] = {
    "sichuan": SichuanExpert(),
    "cantonese": CantoneseExpert(),
    "shandong": ShandongExpert(),
    "suzhou": SuzhouExpert(),
    "zhejiang": ZhejiangExpert(),
    "fujian": FujianExpert(),
    "hunan": HunanExpert(),
    "anhui": AnhuiExpert(),
    "japanese": JapaneseExpert(),
    "western": WesternExpert(),
    "western_fastfood": WesternFastfoodExpert(),
    "chinese_fastfood": ChineseFastfoodExpert(),
    "snacks": SnacksExpert(),
    "dessert_drinks": DessertDrinksExpert(),
}


def assert_registry_complete() -> None:
    """Sanity check used by tests: registry keys match `CUISINE_IDS` exactly."""
    expected = set(CUISINE_IDS)
    actual = set(CUISINE_REGISTRY.keys())
    if expected != actual:
        missing = expected - actual
        extra = actual - expected
        raise AssertionError(f"Cuisine registry drift — missing: {missing}, extra: {extra}")
