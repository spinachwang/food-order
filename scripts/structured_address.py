"""F051 §6 冒烟脚本 — 结构化地址端到端验证.

按 CLAUDE.md §4 强制要求, 每个 spec 实现完成都必须随 PR 提交
`scripts/<feature-slug>.py` 一行可跑的端到端冒烟脚本. 本脚本覆盖
F051 三个核心路径:

1. **happy path**: 构造 StructuredAddress → PUT /api/v1/preferences →
   POST /api/v1/agent/chat (SSE) → 断言 weather 帧 city_adcode 匹配 +
   temperature_celsius 非 null.
2. **legacy compat**: 直接 SQL INSERT 一个 default_location 是老字符串
   (e.g. "国贸三期") 的 row → GET /api/v1/preferences → 断言响应
   default_location === null (后端 schema 拒绝解析后落到 null 而非 400).
3. **契约校验 (--fake)**: 不发 HTTP, 仅校验请求 payload 形状匹配后端
   StructuredAddress schema, 用于 CI 缺凭据场景.

用法:
    # 真链路 (需要 backend 在 :8000 + 数据库 + amap key):
    python scripts/structured_address.py \\
        --message "推荐午饭" \\
        --city-adcode 310000 \\
        --district-adcode 310106 \\
        --community "静安嘉里中心" \\
        --door-no "B2"

    # Legacy compat:
    python scripts/structured_address.py --legacy-string "国贸三期"

    # 契约校验 (无 backend, CI 友好):
    python scripts/structured_address.py --fake \\
        --city-adcode 110000 --district-adcode 110105

输出: pretty JSON 到 stdout, 错误到 stderr, 失败退 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Windows console 默认 GBK — UTF-8 输出会炸.
# `conda run` 子进程会强制按父 shell 编码截断 stdout; 即便设了
# PYTHONIOENCODING=utf-8, conda 自己重打一遍也会乱.
# 解法: 用 os.fdopen 在 fd 级别重新包一层 UTF-8, 在 sys.stdout 首次使用前完成.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = os.fdopen(sys.stdout.fileno(), "w", encoding="utf-8", buffering=1)  # line-buffered
if sys.stderr.encoding and sys.stderr.encoding.lower().replace("-", "") != "utf8":
    sys.stderr = os.fdopen(sys.stderr.fileno(), "w", encoding="utf-8", buffering=1)

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ---------------------------------------------------------------------------
# StructuredAddress schema 镜像 (与 backend/app/schemas/structured_address.py
# 保持一致 — 这是契约, smoke script 必须自包含可校验)
# ---------------------------------------------------------------------------

_ADCODE_PATTERN_LEN = 6
_POI_ID_MIN = 20
_POI_ID_MAX = 32
_DOOR_NO_MAX = 64
_NAME_MAX = 32
_CUISINE_IDS = (
    "sichuan", "cantonese", "shandong", "suzhou", "zhejiang", "fujian",
    "hunan", "anhui", "japanese", "western", "western_fastfood",
    "chinese_fastfood", "snacks", "dessert_drinks",
)


@dataclass(frozen=True)
class StructuredAddress:
    province: str
    province_adcode: str
    city: str
    city_adcode: str
    district: str | None = None
    district_adcode: str | None = None
    street: str | None = None
    community: str | None = None
    poi_id: str | None = None
    door_no: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """转为后端 PUT /api/v1/preferences 接受的 JSON 形状."""
        obj: dict[str, Any] = {
            "province": self.province,
            "province_adcode": self.province_adcode,
            "city": self.city,
            "city_adcode": self.city_adcode,
            "district": self.district,
            "district_adcode": self.district_adcode,
            "street": self.street,
            "community": self.community,
            "poi_id": self.poi_id,
            "door_no": self.door_no,
        }
        return obj


def validate_structured_address(addr: StructuredAddress) -> list[str]:
    """返回校验错误列表 (空 = 通过).

    校验规则镜像 backend/app/schemas/structured_address.py:
    - adcode 必须 6 位数字
    - province_adcode 前两位 == city_adcode 前两位
    - district 与 district_adcode 必须同时存在/缺失
    - poi_id 长度 20-32 (高德 POI ID 格式)
    - door_no 长度 ≤ 64
    - 名称 ≤ 32 字符
    """
    errs: list[str] = []
    for field in ("province_adcode", "city_adcode"):
        v = getattr(addr, field)
        if not (v and len(v) == _ADCODE_PATTERN_LEN and v.isdigit()):
            errs.append(f"{field} 必须是 6 位数字字符串")
    for field in ("province", "city"):
        v = getattr(addr, field)
        if not v or len(v) > _NAME_MAX:
            errs.append(f"{field} 必填且 ≤ {_NAME_MAX} 字符")
    if (
        addr.province_adcode[:2] != addr.city_adcode[:2]
        and addr.province_adcode is not None
        and addr.city_adcode is not None
    ):
        errs.append(
            "province_adcode 与 city_adcode 前两位必须一致"
            f" (实际 {addr.province_adcode} vs {addr.city_adcode})"
        )
    if (addr.district is None) != (addr.district_adcode is None):
        errs.append("district 与 district_adcode 必须成对出现")
    if addr.poi_id is not None and not (_POI_ID_MIN <= len(addr.poi_id) <= _POI_ID_MAX):
        errs.append(f"poi_id 长度必须在 {_POI_ID_MIN}-{_POI_ID_MAX} 之间")
    if addr.door_no is not None and len(addr.door_no) > _DOOR_NO_MAX:
        errs.append(f"door_no 长度 ≤ {_DOOR_NO_MAX}")
    return errs


# ---------------------------------------------------------------------------
# HTTP 客户端 (纯 stdlib — 不引入额外依赖)
# ---------------------------------------------------------------------------


def _http_json(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    user_id: str = "smoke",
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-User-Id": user_id,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _http_sse(
    base_url: str,
    path: str,
    body: dict[str, Any],
    user_id: str = "smoke",
) -> list[dict[str, Any]]:
    """POST + 读取 SSE 事件, 返回 [{event, data}, ...] 列表."""
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-User-Id": user_id,
            "Accept": "text/event-stream",
        },
    )
    frames: list[dict[str, Any]] = []
    with urllib.request.urlopen(req, timeout=60) as resp:
        event: str | None = None
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\n").rstrip("\r")
            if not line:
                event = None
                continue
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                try:
                    frames.append({"event": event, "data": json.loads(payload)})
                except json.JSONDecodeError:
                    frames.append({"event": event, "data": payload})
    return frames


# ---------------------------------------------------------------------------
# Path 1: happy path
# ---------------------------------------------------------------------------


def run_happy_path(
    base_url: str,
    user_id: str,
    addr: StructuredAddress,
    message: str,
) -> dict[str, Any]:
    """PUT preferences → POST agent/chat SSE → 断言 weather 帧."""
    errs = validate_structured_address(addr)
    if errs:
        return {
            "path": "happy",
            "ok": False,
            "errors": errs,
        }

    # 1. PUT preferences
    pref_payload = {
        "cuisine_weights": dict.fromkeys(_CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "hot",
        "default_location": addr.to_payload(),
        "budget_lunch_min": None,
        "budget_lunch_max": None,
    }
    try:
        _http_json(base_url, "PUT", "/api/v1/preferences", pref_payload, user_id)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return {
            "path": "happy",
            "ok": False,
            "errors": [f"PUT preferences failed: {e}"],
        }

    # 2. POST agent/chat (SSE) — 不传 location_override, 让后端从 preferences 读
    chat_payload = {"message": message, "session_id": f"smoke-{user_id}"}
    try:
        frames = _http_sse(base_url, "/api/v1/agent/chat", chat_payload, user_id)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        return {
            "path": "happy",
            "ok": False,
            "errors": [f"POST agent/chat failed: {e}"],
        }

    # 3. 找 weather 帧
    weather_frames = [f for f in frames if f["event"] == "weather"]
    if not weather_frames:
        return {
            "path": "happy",
            "ok": False,
            "errors": [f"SSE 流无 weather 帧; 收到事件: {[f['event'] for f in frames]}"],
        }
    weather = weather_frames[0]["data"]

    # 4. 断言
    assert_errs: list[str] = []
    if weather.get("adcode") != addr.city_adcode:
        assert_errs.append(
            f"weather.adcode ({weather.get('adcode')}) 与 city_adcode "
            f"({addr.city_adcode}) 不匹配"
        )
    if weather.get("temperature_celsius") is None:
        assert_errs.append("weather.temperature_celsius 为 null (降级了)")
    if weather.get("city") != addr.city:
        assert_errs.append(
            f"weather.city ({weather.get('city')}) 与 selected city ({addr.city}) 不匹配"
        )

    return {
        "path": "happy",
        "ok": len(assert_errs) == 0,
        "errors": assert_errs,
        "address_sent": addr.to_payload(),
        "weather_received": weather,
        "frames_received": [f["event"] for f in frames],
    }


# ---------------------------------------------------------------------------
# Path 2: legacy compat
# ---------------------------------------------------------------------------


def run_legacy_compat(base_url: str, user_id: str, legacy_string: str) -> dict[str, Any]:
    """直接 DB 插入老字符串 → GET preferences → 断言 default_location is null.

    模拟 DB 历史数据 / 上游 bug 把 raw string 塞进 default_location 字段.
    后端 Pydantic schema 解析失败时, 服务端应落到 null (而非 400), 前端
    dialog 仍可正常打开 (走 DEFAULT_LEGACY_ADDRESS 兜底).
    """
    try:
        from app.core.db import get_engine
        from app.models.user_preference import UserPreference
    except ImportError as e:
        return {
            "path": "legacy_compat",
            "ok": False,
            "errors": [f"无法导入 backend 模块: {e}. 用 conda env food-order 运行."],
        }

    engine = get_engine()
    cleanup_errs: list[str] = []
    try:
        # 1. 直接 SQLAlchemy 插入 raw string (模拟历史 row)
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            existing = session.get(UserPreference, user_id)
            if existing:
                existing.default_location = legacy_string  # type: ignore[assignment]
                session.commit()
            else:
                session.add(
                    UserPreference(
                        user_id=user_id,
                        cuisine_weights={},
                        allergies=[],
                        spice_tolerance=1,
                        temperature_preference="room",
                        default_location=legacy_string,  # type: ignore[arg-type]
                    )
                )
                session.commit()

        # 2. GET preferences, 断言 default_location 落到 null
        try:
            data = _http_json(base_url, "GET", "/api/v1/preferences", user_id=user_id)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return {
                "path": "legacy_compat",
                "ok": False,
                "errors": [f"GET preferences failed: {e}"],
            }

        # 3. 断言
        received = data.get("default_location")
        if received is not None:
            return {
                "path": "legacy_compat",
                "ok": False,
                "errors": [
                    f"default_location 应为 null, 实际: {received!r}"
                ],
                "raw_legacy_string": legacy_string,
                "received_default_location": received,
            }
        return {
            "path": "legacy_compat",
            "ok": True,
            "errors": [],
            "raw_legacy_string": legacy_string,
            "received_default_location": None,
        }
    finally:
        # cleanup: 把 user_id row 删掉, 避免污染
        try:
            from sqlalchemy.orm import Session

            with Session(engine) as session:
                row = session.get(UserPreference, user_id)
                if row:
                    session.delete(row)
                    session.commit()
        except Exception as e:  # noqa: BLE001
            cleanup_errs.append(f"cleanup failed: {e}")
        if cleanup_errs:
            print(f"[smoke] cleanup 警告: {cleanup_errs}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Path 3: 契约校验 (--fake)
# ---------------------------------------------------------------------------


def run_fake_validation(addr: StructuredAddress | None) -> dict[str, Any]:
    """不发 HTTP, 只校验 StructuredAddress 形状. CI 缺凭据时使用."""
    if addr is None:
        return {
            "path": "fake",
            "ok": False,
            "errors": ["--fake 模式需要提供 --city-adcode / --district-adcode 等参数"],
        }
    errs = validate_structured_address(addr)
    return {
        "path": "fake",
        "ok": len(errs) == 0,
        "errors": errs,
        "address_validated": addr.to_payload(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F051 端到端冒烟脚本 (默认真链路, --fake 走契约校验, --legacy-string 走兼容路径)",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="推荐午饭",
        help="用户 query (default: %(default)s)",
    )
    parser.add_argument("--city", default="上海", help="城市中文名")
    parser.add_argument("--city-adcode", default="310000", help="城市 adcode (默认 310000 = 上海)")
    parser.add_argument(
        "--province",
        default=None,
        help="省份中文名 (默认 = --city; 直辖市场景 province == city)",
    )
    parser.add_argument(
        "--province-adcode",
        default=None,
        help="省份 adcode (默认 = --city-adcode[:2] + '0000')",
    )
    parser.add_argument("--district", default="静安区")
    parser.add_argument("--district-adcode", default="310106")
    parser.add_argument("--street", default=None)
    parser.add_argument("--community", default="静安嘉里中心")
    parser.add_argument("--door-no", default="B2")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="backend base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--user-id",
        default="smoke-f051",
        help="X-User-Id header 值 (default: %(default)s)",
    )
    parser.add_argument(
        "--legacy-string",
        default=None,
        help="若提供, 走 legacy 兼容路径: DB 插入此字符串到 default_location, "
        "GET preferences 断言响应 default_location is null",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="不发 HTTP, 仅校验 StructuredAddress 形状",
    )
    args = parser.parse_args(argv)

    # 直辖市场景: province == city, province_adcode 同 city_adcode[:2] + '0000'
    province = args.province if args.province is not None else args.city
    province_adcode = (
        args.province_adcode
        if args.province_adcode is not None
        else args.city_adcode[:2] + "0000"
    )

    results: list[dict[str, Any]] = []

    if args.legacy_string is not None:
        results.append(run_legacy_compat(args.base_url, args.user_id, args.legacy_string))
    elif args.fake:
        addr = StructuredAddress(
            province=province,
            province_adcode=province_adcode,
            city=args.city,
            city_adcode=args.city_adcode,
            district=args.district,
            district_adcode=args.district_adcode,
            street=args.street,
            community=args.community,
            poi_id=None,
            door_no=args.door_no,
        )
        results.append(run_fake_validation(addr))
    else:
        addr = StructuredAddress(
            province=province,
            province_adcode=province_adcode,
            city=args.city,
            city_adcode=args.city_adcode,
            district=args.district,
            district_adcode=args.district_adcode,
            street=args.street,
            community=args.community,
            poi_id=None,
            door_no=args.door_no,
        )
        results.append(run_happy_path(args.base_url, args.user_id, addr, args.message))

    output = {
        "results": results,
        "ok": all(r["ok"] for r in results),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
