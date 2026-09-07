"""F017 徽菜专家手工试跑入口.

CLI：`python scripts/anhui.py "<消息>"`，验证徽菜专家 build_prompt + parse_output
两条契约路径 + 与川菜（F010）注册表共存不冲突。

设计目的：开发 / 调试阶段快速验证 F017 §2 / §6 验收点。

- Phase 1 stub `run()` 抛 `NotImplementedError`，所以脚本不调真 LLM，只走
  专家层的两条核心契约：
  1. `build_prompt`：用户输入 → prompt 字面量（验证菜系词 / 代表菜 / 与川湘
     边界澄清是否落到 prompt）
  2. `parse_output`：模拟 LLM 回包 → `CuisineExpertOutput`（happy path +
     非法 JSON fallback）

- `--parallel-check` 验证与川菜（F010）注册表共存 + prompt_fragment 互不污染，
  对应 §6 集成验收点"与川菜并行时不冲突"。

- `--canned-json` 注入模拟 LLM 回包走 parse_output 路径；不指定则只跑
  build_prompt 路径（节省 token / 离线）。

用法：

    # 1. Happy path: 用户输入"徽州" → build_prompt 含"徽菜"
    python scripts/anhui.py "想吃徽州菜"

    # 2. 边界场景: 用户输入"咸鲜" → 验证与川湘区分提示已落到 prompt
    python scripts/anhui.py "想吃咸鲜"

    # 3. 代表菜场景: 用户输入"臭鳜鱼"
    python scripts/anhui.py "想吃臭鳜鱼"

    # 4. parse_output happy path（注入模拟 LLM 回包）
    python scripts/anhui.py --canned-json \\
        '{"conclusion":"今天适合来份臭鳜鱼","keywords":["徽菜","臭鳜鱼","徽州"],"matched_allergies":[]}'

    # 5. parse_output fallback（非法 JSON）
    python scripts/anhui.py --canned-json "not json"

    # 6. 与川菜并行不冲突（注册表 + prompt 隔离）
    python scripts/anhui.py "今天都行" --parallel-check

    # 7. 性能硬上限（>2 秒报错退出）
    python scripts/anhui.py "想吃徽州菜" --max-elapsed-ms 2000
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/anhui.py "..."` 而不需要 PYTHONPATH。
# backend/ 与 scripts/ 同级，把 backend/ 加到 sys.path 让 `from app.xxx` 工作。
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
from app.agents.cuisines.stubs.anhui import AnhuiExpert
from app.agents.cuisines.stubs.sichuan import SichuanExpert
from app.agents.state import CuisineExpertInput, UserPreferencesDict
from app.core.constants import CUISINE_IDS

# ---------------------------------------------------------------------------
# Helpers — 输入构造 + prompt 命中检查
# ---------------------------------------------------------------------------


def _build_input(user_message: str) -> CuisineExpertInput:
    """构造最小可用的 `CuisineExpertInput`；偏好用中性默认。"""
    prefs: UserPreferencesDict = {
        "user_id": "dev-f017",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    return {
        "user_message": user_message,
        "user_preferences": prefs,
        "location": None,
        "spice_tolerance": 0,
        "budget_max": 80.0,
        "budget_min": 30.0,
    }


def _check_prompt_hits(prompt: str) -> dict[str, bool]:
    """检查 build_prompt 输出对 F017 §2 / §4 关键提示的命中情况。

    返回字段语义：True = 命中（提示词出现在 prompt 中），False = 缺失。
    """
    return {
        # §2 验收：菜系词覆盖
        "cuisine_term_huicai": "徽菜" in prompt,
        "cuisine_term_anhui": "安徽" in prompt,
        "cuisine_term_huizhou": "徽州" in prompt,
        # §2 验收：代表菜
        "signature_dish_chouguiyu": "臭鳜鱼" in prompt,
        # §2 验收：与川菜 / 湘菜的辣度区分
        "distinguish_from_sichuan": "川菜" in prompt,
        "distinguish_from_hunan": "湘菜" in prompt,
        "boundary_mala": "麻辣" in prompt,
        "boundary_xiangla": "香辣" in prompt,
        # §4 风味词
        "flavor_xianxian": "咸鲜" in prompt,
        # 用户原文注入
        "user_message_injected": False,  # 调用方单独检查（因用户消息内容是变量）
    }


def _check_parallel_safety() -> dict[str, Any]:
    """F017 §6 集成验收：与川菜并行时不冲突。

    验证徽菜（F017）与川菜（F010）注册表共存 + prompt_fragment 互不污染。
    """
    anhui = CUISINE_REGISTRY.get("anhui")
    sichuan = CUISINE_REGISTRY.get("sichuan")

    coexists = anhui is not None and sichuan is not None
    fragments_differ = (
        coexists and AnhuiExpert.prompt_fragment != SichuanExpert.prompt_fragment
    )
    # 徽菜 fragment 不含川菜专属代表菜（避免 LLM 误推川）
    sichuan_signature_dishes = ("麻婆豆腐", "回锅肉", "水煮鱼")
    anhui_no_sichuan_dish_leak = all(
        dish not in AnhuiExpert.prompt_fragment for dish in sichuan_signature_dishes
    )
    # 川菜 fragment 不含徽菜专属代表菜
    anhui_signature_dishes = ("臭鳜鱼", "毛豆腐", "火腿炖甲鱼", "徽州腊肉", "刀板香")
    sichuan_no_anhui_dish_leak = all(
        dish not in SichuanExpert.prompt_fragment for dish in anhui_signature_dishes
    )

    return {
        "both_registered": coexists,
        "fragments_differ": fragments_differ,
        "anhui_no_sichuan_dish_leak": anhui_no_sichuan_dish_leak,
        "sichuan_no_anhui_dish_leak": sichuan_no_anhui_dish_leak,
        "all_pass": all(
            [
                coexists,
                fragments_differ,
                anhui_no_sichuan_dish_leak,
                sichuan_no_anhui_dish_leak,
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Step 1: build_prompt 验证
# ---------------------------------------------------------------------------


def _run_build_prompt(user_message: str) -> dict[str, Any]:
    """跑 build_prompt 路径并报告命中情况。"""
    started = time.monotonic()
    expert = AnhuiExpert()
    inp = _build_input(user_message)
    prompt = expert.build_prompt(inp)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    hits = _check_prompt_hits(prompt)
    hits["user_message_injected"] = user_message in prompt

    # F017 §2 验收点的关键最小集：
    # 菜系词至少 1 个 + 代表菜"臭鳜鱼" + 与川湘边界澄清 + 风味词"咸鲜"
    section2_minimum = all(
        [
            hits["signature_dish_chouguiyu"],
            hits["distinguish_from_sichuan"],
            hits["distinguish_from_hunan"],
            hits["boundary_mala"],
            hits["boundary_xiangla"],
            hits["flavor_xianxian"],
            any(
                [
                    hits["cuisine_term_huicai"],
                    hits["cuisine_term_anhui"],
                    hits["cuisine_term_huizhou"],
                ]
            ),
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
    """跑 parse_output 路径：模拟 LLM 回包 → `CuisineExpertOutput`。"""
    started = time.monotonic()
    expert = AnhuiExpert()
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
        description="F017 徽菜专家手工试跑（默认走 build_prompt；--canned-json 走 parse_output）"
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="想吃徽州菜",
        help="用户消息原文；喂给 build_prompt 路径（带引号）",
    )
    parser.add_argument(
        "--canned-json",
        default=None,
        help="模拟 LLM 回包；喂给 parse_output 路径。不指定则跳过 parse_output 步骤",
    )
    parser.add_argument(
        "--parallel-check",
        action="store_true",
        help="附加运行：与川菜（F010）注册表共存 + prompt_fragment 隔离检查（§6 集成验收）",
    )
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=None,
        help="硬上限；超过 exit 2；不指定则仅报告 elapsed_ms",
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

    # 汇总状态：build_prompt §2 最小集 + (parse_output 不为 fallback 才视为 happy)
    overall_pass = bool(build_result["section2_minimum_pass"])
    if parse_result is not None:
        # parse_output 在 happy path 下应有非空结论或非空 keywords；
        # fallback 时 is_fallback=True 仍属正常（F003 §3.3 容错路径），
        # 不影响 overall_pass（这是契约验证脚本，不是 LLM 行为断言）。
        pass

    result: dict[str, Any] = {
        "cuisine_id": "anhui",
        "display_name": "徽菜",
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
