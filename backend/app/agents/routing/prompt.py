"""F002 §4 router LLM 兜底层的 prompt 渲染 + JSON 回包解析。

仅当规则层未命中时调用；规则层命中场景不进此 prompt。spec §4 锁定模板，
不在此函数中"创意发挥"。
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from app.agents.llm.types import ChatRequest
from app.agents.state import UserPreferencesDict
from app.core.constants import CUISINE_IDS

_logger = logging.getLogger(__name__)


# LLM 回包类型——便于 type narrowing。
class RouterLLMResponse(TypedDict):
    selected_cuisines: list[str]
    routing_reason: str


# 可选菜系列表——把 cuisine_id → 中文名展示给 LLM，便于其判断。
# 名称顺序与 CUISINE_IDS 一致以稳定渲染。
_CUISINE_DISPLAY: tuple[tuple[str, str], ...] = (
    ("sichuan", "川菜"),
    ("cantonese", "粤菜"),
    ("shandong", "鲁菜"),
    ("suzhou", "苏菜"),
    ("zhejiang", "浙菜"),
    ("fujian", "闽菜"),
    ("hunan", "湘菜"),
    ("anhui", "徽菜"),
    ("japanese", "日料"),
    ("western", "西餐"),
    ("western_fastfood", "西式快餐"),
    ("chinese_fastfood", "中式快餐"),
    ("snacks", "小吃"),
    ("dessert_drinks", "甜品饮品"),
)


def _format_cuisine_weights(weights: dict[str, float]) -> str:
    """Top-3 cuisine_weights 给 LLM 看，权重从高到低。"""
    sorted_items = sorted(
        ((k, v) for k, v in weights.items() if v > 0),
        key=lambda kv: (-kv[1], CUISINE_IDS.index(kv[0]) if kv[0] in CUISINE_IDS else 99),
    )[:3]
    if not sorted_items:
        return "无"
    return ", ".join(f"{_cuisine_display_name(k)}={v:.1f}" for k, v in sorted_items)


def _cuisine_display_name(cuisine_id: str) -> str:
    for cid, name in _CUISINE_DISPLAY:
        if cid == cuisine_id:
            return name
    return cuisine_id


def _format_allergies(allergies: list[str]) -> str:
    if not allergies:
        return "无"
    return ", ".join(allergies)


def _format_spice(spice_tolerance: int) -> str:
    """0-3 → 不辣/微辣/中辣/重辣，给 LLM 一个可读的语义档位。"""
    return {0: "不辣", 1: "微辣", 2: "中辣", 3: "重辣"}.get(spice_tolerance, "不辣")


def build_router_prompt(preferences: UserPreferencesDict, message: str) -> ChatRequest:
    """渲染 spec §4 的 router LLM prompt。

    Returns a `ChatRequest` ready for `LLMProvider.complete(...)`. The system
    prompt carries the task framing; the user message carries the actual
    user input + preference digest.
    """
    cuisine_weights_top3 = _format_cuisine_weights(preferences.get("cuisine_weights", {}))
    allergies = _format_allergies(list(preferences.get("allergies", [])))
    spice = _format_spice(int(preferences.get("spice_tolerance", 0)))

    cuisine_registry_keys_and_names = ", ".join(
        f"{cid}（{name}）" for cid, name in _CUISINE_DISPLAY
    )

    system_content = (
        '你是"午餐决策助手"的路由 Agent。决定调哪些菜系专家。\n'
        "\n"
        "【可选菜系】\n"
        f"{cuisine_registry_keys_and_names}\n"
        "\n"
        "【任务】\n"
        "1. 输出 selected_cuisines：1-3 个 cuisine_id\n"
        "2. 输出 routing_reason：≤30 字说明\n"
        "\n"
        "【输出格式】严格 JSON：\n"
        "{\n"
        '  "selected_cuisines": ["...", "..."],\n'
        '  "routing_reason": "..."\n'
        "}"
    )

    user_content = (
        "【用户消息】\n"
        f"{message}\n"
        "\n"
        "【用户偏好摘要】\n"
        f"- 菜系权重：{cuisine_weights_top3}\n"
        f"- 忌口：{allergies}\n"
        f"- 辣度：{spice}\n"
    )

    request: ChatRequest = {
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
    }
    return request


class RouterResponseError(ValueError):
    """LLM 回包无法解析为合法 `selected_cuisines` / `routing_reason` 时抛出。

    由 `route_cuisines` 捕获并降级到 `NO_CUISINE_MATCHED`。
    """


def parse_router_response(raw_content: str) -> RouterLLMResponse:
    """解析 LLM 的 JSON 回包。

    容忍 `code fence`（首尾 ```json / ``` 包裹）；非 dict / 缺字段 / 类型不对
    一律抛 `RouterResponseError`—— caller 必须不向用户暴露异常，而是降级。
    """
    text = raw_content.strip()
    if text.startswith("```"):
        # ```json\n...\n``` → 去掉首尾 fence。
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        _logger.info("router LLM response is not valid JSON: %s", e)
        raise RouterResponseError("not JSON") from e

    if not isinstance(data, dict):
        raise RouterResponseError("not an object")

    selected = data.get("selected_cuisines")
    if not isinstance(selected, list):
        raise RouterResponseError("selected_cuisines is not a list")

    reason = data.get("routing_reason", "")
    if not isinstance(reason, str):
        reason = ""

    return {"selected_cuisines": [str(x) for x in selected], "routing_reason": reason}
