"""F023 小吃专家手工试跑入口.

CLI: `python scripts/snacks.py "<消息>"`, 验证小吃专家 build_prompt +
parse_output 两条契约路径 + 与中式快餐(F022)注册表共存不冲突.

设计目的:开发 / 调试阶段快速验证 F023 §2 / §6 验收点.

- Phase 1 stub `run()` 抛 `NotImplementedError`, 所以脚本不调真 LLM, 只走
  专家层的两条核心契约:
  1. `build_prompt`:用户输入 → prompt 字面量(验证菜系词 / 代表菜 /
     街头特点 / 与中式快餐边界澄清是否落到 prompt)
  2. `parse_output`:模拟 LLM 回包 → `CuisineExpertOutput`(happy path +
     非法 JSON fallback)

- `--parallel-check` 验证与中式快餐(F022)注册表共存 + prompt_fragment
  互不污染, 对应 §6 集成验收点"与中式快餐并行不冲突".

- `--canned-json` 注入模拟 LLM 回包走 parse_output 路径; 不指定则只跑
  build_prompt 路径(节省 token / 离线).

用法:

    # 1. Happy path: 用户输入"想吃小吃" → build_prompt 含"小吃"
    python scripts/snacks.py "想吃小吃"

    # 2. 北方场景: 用户输入"想吃煎饼"
    python scripts/snacks.py "想吃煎饼"

    # 3. 川渝场景: 用户输入"想吃麻辣烫"
    python scripts/snacks.py "想吃麻辣烫"

    # 4. 边界场景: 用户输入"想吃黄焖鸡米饭" → 验证边界澄清已落到 prompt
    python scripts/snacks.py "想吃黄焖鸡米饭"

    # 5. parse_output happy path(注入模拟 LLM 回包)
    python scripts/snacks.py --canned-json \\
        '{"conclusion":"今天适合来份煎饼","keywords":["小吃","煎饼","麻辣烫","街头"],"matched_allergies":[]}'

    # 6. parse_output fallback(非法 JSON)
    python scripts/snacks.py --canned-json "not json"

    # 7. 与中式快餐并行不冲突(注册表 + prompt 隔离)
    python scripts/snacks.py "今天都行" --parallel-check

    # 8. 性能硬上限(>2 秒报错退出)
    python scripts/snacks.py "想吃小吃" --max-elapsed-ms 2000
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/snacks.py "..."` 而不需要 PYTHONPATH.
# backend/ 与 scripts/ 同级, 把 backend/ 加到 sys.path 让 `from app.xxx` 工作.
import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agents.cuisines import CUISINE_REGISTRY
from app.agents.cuisines.stubs.chinese_fastfood import ChineseFastfoodExpert
from app.agents.cuisines.stubs.snacks import SnacksExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS


# ---------------------------------------------------------------------------
# Helpers — 输入构造 + prompt 命中检查
# ---------------------------------------------------------------------------


def _build_input(user_message: str) -> CuisineExpertInput:
    """构造最小可用的 `CuisineExpertInput`; 偏好用中性默认."""
    prefs: UserPreferencesDict = {
        "user_id": "dev-f023",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("10.00"),
        "budget_lunch_max": Decimal("30.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_max": 30.0,
        "budget_min": 10.0,
    }


def _check_prompt_hits(prompt: str) -> dict[str, bool]:
    """检查 build_prompt 输出对 F023 §2 / §4 关键提示的命中情况.

    返回字段语义:True = 命中(提示词出现在 prompt 中), False = 缺失.
    """
    return {
        # §2 验收:菜系词覆盖(小吃 / 街头)
        "cuisine_term_xiaochi": "小吃" in prompt,
        "cuisine_term_jietou": "街头" in prompt,
        # §2 验收:代表菜(煎饼 / 麻辣烫 / 烤串)
        "signature_jianbing": "煎饼" in prompt,
        "signature_malatang": "麻辣烫" in prompt,
        "signature_kaochuan": "烤串" in prompt,
        # §2 验收:与中式快餐(F022)的边界
        "distinguish_from_chinese_fastfood": "中式快餐" in prompt,
        # §4 街头 / 摊位 / 非正餐
        "street_food_nature": any(
            token in prompt for token in ("非正餐", "摊位", "档口", "街边店")
        ),
        # §4 价格区间 10-30 元
        "price_range_10_30": "10" in prompt and "30" in prompt,
    }


def _check_parallel_safety() -> dict[str, Any]:
    """F023 §6 集成验收:与中式快餐并行不冲突.

    验证小吃(F023)与中式快餐(F022)注册表共存 + prompt_fragment 互不污染.
    """
    snacks = CUISINE_REGISTRY.get("snacks")
    cf = CUISINE_REGISTRY.get("chinese_fastfood")

    coexists = snacks is not None and cf is not None
    fragments_differ = coexists and SnacksExpert.prompt_fragment != ChineseFastfoodExpert.prompt_fragment
    # 小吃 fragment 不含中式快餐专属代表菜(避免 LLM 误推中式快餐)
    cf_signature_dishes = ("黄焖鸡米饭", "沙县拌面", "兰州拉面", "猪脚饭")
    snacks_no_cf_dish_leak = all(
        dish not in SnacksExpert.prompt_fragment for dish in cf_signature_dishes
    )
    # 中式快餐 fragment 不含小吃专属代表菜
    snacks_signature_dishes = ("煎饼", "麻辣烫", "烤串", "关东煮", "肉夹馍")
    cf_no_snacks_dish_leak = all(
        dish not in ChineseFastfoodExpert.prompt_fragment for dish in snacks_signature_dishes
    )

    return {
        "both_registered": coexists,
        "fragments_differ": fragments_differ,
        "snacks_no_cf_dish_leak": snacks_no_cf_dish_leak,
        "cf_no_snacks_dish_leak": cf_no_snacks_dish_leak,
        "all_pass": all(
            [
                coexists,
                fragments_differ,
                snacks_no_cf_dish_leak,
                cf_no_snacks_dish_leak,
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Step 1: build_prompt 验证
# ---------------------------------------------------------------------------


def _run_build_prompt(user_message: str) -> dict[str, Any]:
    """跑 build_prompt 路径并报告命中情况."""
    started = time.monotonic()
    expert = SnacksExpert()
    inp = _build_input(user_message)
    prompt = expert.build_prompt(inp)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    hits = _check_prompt_hits(prompt)
    hits["user_message_injected"] = user_message in prompt

    # F023 §2 验收点的关键最小集:
    # 菜系词(小吃) + 代表菜(煎饼 / 麻辣烫) + 与中式快餐边界澄清 + 街头特点
    section2_minimum = all(
        [
            hits["cuisine_term_xiaochi"],
            hits["signature_jianbing"],
            hits["signature_malatang"],
            hits["distinguish_from_chinese_fastfood"],
            hits["street_food_nature"],
        ]
    )

    return {
        "step": "build_prompt",
        "user_message": user_message,
        "cuisine_id": expert.cuisine_id,
        "display_name": expert.display_name,
        "llm_model": expert.llm_model,
        "prompt_length": len(prompt),
        "prompt_hits": hits,
        "section2_minimum_pass": section2_minimum,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Step 2: parse_output 验证
# ---------------------------------------------------------------------------


def _run_parse_output(canned_json: str) -> dict[str, Any]:
    """跑 parse_output 路径:模拟 LLM 回包 → `CuisineExpertOutput`."""
    started = time.monotonic()
    expert = SnacksExpert()
    out = expert.parse_output(canned_json)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    is_fallback = (
        out["conclusion"] == "暂不可推荐"
        and out["keywords"] == []
        and out["matched_allergies"] == []
    )

    return {
        "step": "parse_output",
        "canned_input_length": len(canned_json),
        "cuisine_id": out["cuisine_id"],
        "conclusion": out["conclusion"],
        "keywords": out["keywords"],
        "matched_allergies": out["matched_allergies"],
        "is_fallback": is_fallback,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F023 小吃专家手工试跑(默认走 build_prompt; --canned-json 走 parse_output)"
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="想吃小吃",
        help="用户消息原文; 喂给 build_prompt 路径(带引号)",
    )
    parser.add_argument(
        "--canned-json",
        default=None,
        help="模拟 LLM 回包; 喂给 parse_output 路径. 不指定则跳过 parse_output 步骤",
    )
    parser.add_argument(
        "--parallel-check",
        action="store_true",
        help="附加运行:与中式快餐(F022)注册表共存 + prompt_fragment 隔离检查(§6 集成验收)",
    )
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=None,
        help="硬上限; 超过 exit 2; 不指定则仅报告 elapsed_ms",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    steps: list[dict[str, Any]] = []

    # Step 1: build_prompt
    build_result = _run_build_prompt(args.message)
    steps.append(build_result)

    # Step 2: parse_output (optional)
    parse_result: dict[str, Any] | None = None
    if args.canned_json is not None:
        parse_result = _run_parse_output(args.canned_json)
        steps.append(parse_result)

    # Step 3: parallel safety (optional)
    parallel_result: dict[str, Any] | None = None
    if args.parallel_check:
        parallel_result = _check_parallel_safety()
        steps.append({"step": "parallel_check", **parallel_result})

    total_elapsed_ms = int((time.monotonic() - started) * 1000)

    overall_pass = bool(build_result["section2_minimum_pass"])

    result: dict[str, Any] = {
        "cuisine_id": "snacks",
        "display_name": "小吃",
        "user_message": args.message,
        "canned_json_provided": args.canned_json is not None,
        "parallel_check_run": args.parallel_check,
        "overall_pass": overall_pass,
        "build_prompt": build_result,
        "parse_output": parse_result,
        "parallel_safety": parallel_result,
        "total_elapsed_ms": total_elapsed_ms,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    if args.max_elapsed_ms is not None and total_elapsed_ms > args.max_elapsed_ms:
        sys.stderr.write(
            f"total_elapsed_ms {total_elapsed_ms} exceeds --max-elapsed-ms "
            f"{args.max_elapsed_ms}\n"
        )
        return 2

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
