"""F002 §3.3 路由规则表 + 模糊抽样。

Per spec §3.3 — 路由层按"意图标签（tag）分区"，同一 tag 只有一条规则能赢；
标签分两级优先级：显式点名菜系（"想吃川菜"）> 口味修饰（"想吃辣的"）。
互斥标签（spicy × light）同时命中且无显式点名时不做武断合并，直接降级给 LLM。
"""

from __future__ import annotations

import math
import random
import re
from typing import NamedTuple

# `MAX_REASON_CODEPOINTS` is the F002 §2 hard cap on `routing_reason`. We count
# codepoints (Python str length), not graphemes — spec wording is "≤30 字"，
# 即 ≤30 个 Unicode 码位。F050 (chat shell) 渲染时按字符截断。
MAX_REASON_CODEPOINTS: int = 30

# 互斥标签（spec §3.3）—— 同时命中且无显式点名 → 降级 LLM，不武断合并。
# 当前只有 {spicy, light}；新增互斥对时同步更新本表 + 单元测试。
CONTRADICTORY_TAGS: frozenset[str] = frozenset({"spicy", "light"})


class Rule(NamedTuple):
    """一条路由规则。

    `tag` 是意图标签，规则表按 tag 去重（同一 tag 多条规则会被 spec 测试
    锁死为单一来源）；`keywords` 是子串匹配词集合；`cuisines` 是命中后写入
    `selected_cuisines` 的 cuisine_id 序列；`reason` 是命中后直接写入
    `routing_reason` 的静态文案（≤30 码位）。
    """

    tag: str
    keywords: tuple[str, ...]
    cuisines: tuple[str, ...]
    reason: str


# ---------------------------------------------------------------------------
# 优先级 1：显式点名菜系（spec §3.3 — 用户直接说出菜系名，最强信号）
# 14 条，对应 14 个 cuisine_id。tags 与 CUISINE_IDS 一一对应。
# ---------------------------------------------------------------------------

_EXPLICIT_RULES_RAW: tuple[Rule, ...] = (
    Rule("sichuan", ("川菜", "四川菜", "川味", "蜀菜"), ("sichuan",), "想吃川菜 → 川"),
    Rule(
        "cantonese", ("粤菜", "广东菜", "广式", "早茶", "茶餐厅"), ("cantonese",), "想吃粤菜 → 粤"
    ),
    Rule("shandong", ("鲁菜", "山东菜", "胶东菜"), ("shandong",), "想吃鲁菜 → 鲁"),
    Rule("suzhou", ("苏菜", "苏州菜", "淮扬菜", "淮扬"), ("suzhou",), "想吃苏菜 → 苏"),
    Rule("zhejiang", ("浙菜", "浙江菜", "杭帮菜"), ("zhejiang",), "想吃浙菜 → 浙"),
    Rule("fujian", ("闽菜", "福建菜", "闽南"), ("fujian",), "想吃闽菜 → 闽"),
    Rule("hunan", ("湘菜", "湖南菜"), ("hunan",), "想吃湘菜 → 湘"),
    Rule("anhui", ("徽菜", "安徽菜"), ("anhui",), "想吃徽菜 → 徽"),
    Rule("japanese", ("日料", "日本菜", "寿司", "刺身"), ("japanese",), "想吃日料 → 日料"),
    Rule(
        "western",
        ("西餐", "牛排", "意面", "意大利", "法国", "法餐"),
        ("western",),
        "想吃西餐 → 西餐",
    ),
    Rule(
        "western_fastfood",
        ("西式快餐", "汉堡", "麦当劳", "肯德基", "薯条", "披萨"),
        ("western_fastfood",),
        "想吃西式快餐 → 西式快餐",
    ),
    Rule(
        "chinese_fastfood",
        ("中式快餐", "盒饭", "工作餐", "食堂"),
        ("chinese_fastfood",),
        "想吃中式快餐 → 中式快餐",
    ),
    Rule("snacks", ("小吃", "夜宵", "街边", "路边摊", "撸串"), ("snacks",), "想吃小吃 → 小吃"),
    Rule(
        "dessert_drinks",
        ("甜品", "奶茶", "咖啡", "蛋糕", "下午茶", "甜点"),
        ("dessert_drinks",),
        "想喝点甜的 → 甜品饮品",
    ),
)
EXPLICIT_RULES: tuple[Rule, ...] = _EXPLICIT_RULES_RAW


# ---------------------------------------------------------------------------
# 优先级 2：口味修饰意图（spec §3.3 的 5 条）
# 关键词强制 ≥2 字（spec §3.3）—— 单字「快/饱」会触发子串误命中。
# 注：snacks / dessert_drinks 在 EXPLICIT_RULES 里已有同名 cuisine 规则，
# 这里不复列避免 tag 重复。"随便"类模糊意图走 is_ambient_message() 单独识别。
# ---------------------------------------------------------------------------

_MODIFIER_RULES_RAW: tuple[Rule, ...] = (
    Rule(
        "spicy",
        ("想吃辣", "吃辣", "麻辣", "辣的", "重口"),
        ("sichuan", "hunan"),
        "你说想吃辣的 → 川 + 湘",
    ),
    Rule(
        "light",
        ("清淡", "养生", "不油", "少油"),
        ("cantonese", "suzhou", "zhejiang"),
        "你说想清淡点 → 粤 + 苏 + 浙",
    ),
    Rule(
        "fastfood",
        ("快餐", "简餐", "吃快", "快点吃", "吃饱", "饱腹", "扛饿"),
        ("western_fastfood", "chinese_fastfood"),
        "你想快点吃饱 → 快餐",
    ),
)
MODIFIER_RULES: tuple[Rule, ...] = _MODIFIER_RULES_RAW


# ---------------------------------------------------------------------------
# 模糊意图关键词（"随便" 类）
# ---------------------------------------------------------------------------

AMBIENT_KEYWORDS: tuple[str, ...] = (
    "随便",
    "都行",
    "无所谓",
    "你决定",
    "看你",
    "帮我选",
    "你来",
)

# 子串匹配——关键词≥2 字 + 命中测试已在 tests/unit/test_routing_rules.py 锁定。
_AMBIENT_RE = re.compile("|".join(re.escape(k) for k in AMBIENT_KEYWORDS))


def is_ambient_message(message: str) -> bool:
    """判断消息是否表达"随便 / 你决定"等模糊意图。

    使用子串匹配：任何 ambient 关键词出现在消息中即视为模糊意图。
    短消息（如"随便"）与长消息（如"今天真的随便，你决定"）都覆盖。
    """
    if not message:
        return False
    return _AMBIENT_RE.search(message) is not None


# ---------------------------------------------------------------------------
# 规则匹配 — 意图标签分区
# ---------------------------------------------------------------------------


def match_rules(message: str) -> list[Rule]:
    """对一条用户消息跑两层规则，返回所有命中的规则。

    命中规则按「显式 > 修饰」顺序排序；同 tag 多条规则会由调用方处理去重
    （本函数不做去重，避免丢失优先级信息——后续判断互斥标签需要看完整命中集）。

    子串匹配使用 `re.search`，无大小写敏感——因为关键词都是中文。
    """
    if not message:
        return []
    matched: list[Rule] = []
    for rule in EXPLICIT_RULES:
        if any(kw in message for kw in rule.keywords):
            matched.append(rule)
    for rule in MODIFIER_RULES:
        if rule.cuisines and any(kw in message for kw in rule.keywords):
            matched.append(rule)
    return matched


# ---------------------------------------------------------------------------
# 加权随机抽样 — ambient 路径用
# ---------------------------------------------------------------------------


def sample_by_weights(
    weights: dict[str, float],
    n: int,
    rng: random.Random,
) -> list[str]:
    """按权重无放回抽 n 个 key。

    - 容忍 NaN / inf / 负数：先把非有限值与负数夹到 0
    - 容忍总和为 0（忌口清零等情形）：均匀无放回回退
    - 容忍候选数 < n：直接返回全部，不补齐（spec 不要求）
    - 不修改入参 dict

    实现说明：随机.choice 的累积分布按当前 RNG 状态走，因此传入固定 seed
    时本函数完全确定（test_routing_rules.TestSampleByWeights 锁死此行为）。
    """
    if n <= 0 or not weights:
        return []

    # 净化权重：非有限 / 负数 → 0；保留原 key 顺序作为"按定义顺序破平"的兜底。
    cleaned: dict[str, float] = {
        k: (w if (math.isfinite(w) and w > 0.0) else 0.0) for k, w in weights.items()
    }
    keys = list(cleaned.keys())
    total = sum(cleaned.values())

    if total <= 0.0:
        # 全部为零权重：均匀无放回。
        return rng.sample(keys, min(n, len(keys)))

    # 加权无放回：每次按累积概率抽 1 个，从池中剔除后归一化剩余权重。
    pool: dict[str, float] = dict(cleaned)
    picked: list[str] = []
    remaining = n
    while remaining > 0 and pool:
        pool_total = sum(pool.values())
        if pool_total <= 0.0:
            # 剩余全为零（不可能，但兜底），用均匀回退收尾。
            picked.extend(rng.sample(list(pool.keys()), min(remaining, len(pool))))
            break
        r = rng.random() * pool_total
        cursor = 0.0
        chosen_key: str | None = None
        for k, w in pool.items():
            cursor += w
            if r <= cursor:
                chosen_key = k
                break
        if chosen_key is None:
            # 浮点累积误差兜底。
            chosen_key = next(iter(pool.keys()))
        picked.append(chosen_key)
        del pool[chosen_key]
        remaining -= 1

    return picked
