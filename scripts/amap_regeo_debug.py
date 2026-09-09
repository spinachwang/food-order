"""高德 API 一键诊断脚本 — 2026-09-08 bug 排查专用.

直接对 `https://restapi.amap.com/v3/...` 发请求, 打印完整响应,
让"前端 502 / 拿不到 POI"的根因一眼可见. 不走 FastAPI / mcp wrapper,
不引入业务层, 只验证高德 key 本身能不能拿到行政区划 / POI.

支持两种 mode:

- `regeo` — 逆地址 (lng,lat → 行政区划). F051 5 级地址选择器依赖.
- `place_text` — 正地址 (关键字 → POI 列表). F051 §5.3 / F030 §3.3 依赖.

用法:

    # regeo 默认 5 个测试点 (上海陆家嘴 / 杭州西湖 / 广州天河 /
    # 北京中关村 / 海上点), extensions=base
    python scripts/amap_regeo_debug.py

    # regeo 自定义经纬度
    python scripts/amap_regeo_debug.py --location "120.28,30.2146"

    # regeo extensions=all (拿 POI 周边, 验证 key 是否开了 regeo 权限)
    python scripts/amap_regeo_debug.py --extensions all

    # place_text 默认 3 个测试点 (全国/上海/上海商圈)
    python scripts/amap_regeo_debug.py --mode place_text

    # place_text 自定义关键字
    python scripts/amap_regeo_debug.py --mode place_text --keywords 海底捞 --city 上海

    # 自定义 .env 路径
    python scripts/amap_regeo_debug.py --env-file ./.env

诊断输出:
- HTTP status / 高德 status / infocode / info (业务级错误码)
- 命中数 (regeo: regeocode 对象存在? / place_text: pois 长度)
- 命中时打印关键字段 (regeo: province/city/district; place_text: name/address/location)
- infocode 映射表: 10001=key 无效 / 10002=未开通 / 10007=域名白名单 /
  10011=日配额耗尽 / 10014=参数错 / 20001/20002=city 解析失败

退出码:
- 0 = 至少一个查询拿到非空结果
- 1 = 所有查询都返回空 (key 未开通 / 配额耗尽 / 关键词无匹配)
- 2 = 网络层失败 / .env 配错
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Windows console 默认 GBK — UTF-8 输出会炸. 同 structured_address.py.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = os.fdopen(sys.stdout.fileno(), "w", encoding="utf-8", buffering=1)
if sys.stderr.encoding and sys.stderr.encoding.lower().replace("-", "") != "utf8":
    sys.stderr = os.fdopen(sys.stderr.fileno(), "w", encoding="utf-8", buffering=1)


# ---------- URL 配置 ----------
URLS: dict[str, str] = {
    "regeo": "https://restapi.amap.com/v3/geocode/regeo",
    "place_text": "https://restapi.amap.com/v3/place/text",
}

# ---------- 默认测试点 ----------

# (label, location, expected_province) — 期望落陆地 + 城市; 海上点 expected=None
DEFAULT_LOCATIONS: list[tuple[str, str, str | None]] = [
    ("上海陆家嘴", "121.505310,31.235170", "上海市"),
    ("杭州西湖", "120.130,30.270", "浙江省"),
    ("广州天河", "113.330,23.130", "广东省"),
    ("北京中关村", "116.310,39.990", "北京市"),
    ("海上点 (东海洋面)", "123.500,30.500", None),  # 预期落空
]

# (label, keywords, city) — city=None 则全国范围
DEFAULT_QUERIES: list[tuple[str, str, str | None]] = [
    ("全国 — 海底捞", "海底捞", None),
    ("上海 — 海底捞", "海底捞", "上海"),
    ("上海 — 南京西路 (商圈关键词)", "南京西路", "上海"),
]

# ---------- infocode 提示表 (高德通用) ----------
INFOCODE_HINTS: dict[str, str] = {
    "10001": "INVALID_USER_KEY — key 不存在 / 被禁用",
    "10002": "服务未开通 — 没勾选对应权限 (regeo / place_text)",
    "10003": "余额不足",
    "10006": "IP 白名单错误 — 当前 IP 不在 key 白名单",
    "10007": "请求来源不在白名单 — Web 端 key 没配 referer",
    "10008": "安全密钥验证失败",
    "10011": "用户日访问量超限",
    "10012": "用户总访问量超限",
    "10014": "INVALID_PARAMS — 参数格式错误 (如 location 不是 lng,lat)",
    "20001": "城市 / 关键字解析失败 (place_text 专属)",
    "20002": "建议城市列表 (place_text 专属, 非错误)",
}


def load_amap_key(env_file: Path) -> str:
    """从 .env 读 AMAP_API_KEY. 不依赖 python-dotenv, 避免给脚本加 deps."""
    if not env_file.exists():
        print(
            f"[ERROR] .env 不存在: {env_file}\n"
            f"        请先 cp .env.example .env 并填入 AMAP_API_KEY",
            file=sys.stderr,
        )
        sys.exit(2)
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "AMAP_API_KEY":
            key = v.strip()
            if not key:
                print("[ERROR] AMAP_API_KEY 为空", file=sys.stderr)
                sys.exit(2)
            return key
    print(f"[ERROR] {env_file} 里找不到 AMAP_API_KEY", file=sys.stderr)
    sys.exit(2)


def call_amap(
    mode: str, key: str, params: dict[str, str], timeout: float = 10.0
) -> dict[str, object]:
    """通用高德调用. 返回 dict 含 http_status / body / error.

    timeout=10s: 弱网 / 服务端抖动场景下, 5s 容易误判网络失败.
    """
    full_params = {**params, "key": key, "output": "JSON"}
    url = f"{URLS[mode]}?{urllib.parse.urlencode(full_params)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return {
                "http_status": resp.status,
                "body": json.loads(body) if body else {},
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "body": {},
            "error": f"HTTPError: {exc.reason}",
        }
    except urllib.error.URLError as exc:
        return {
            "http_status": None,
            "body": {},
            "error": f"URLError: {exc.reason}",
        }
    except (TimeoutError, json.JSONDecodeError) as exc:
        return {
            "http_status": None,
            "body": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _print_infocode_hint(infocode: object) -> None:
    """根据 infocode 打印一行诊断提示 (若有)."""
    if not isinstance(infocode, str):
        return
    hint = INFOCODE_HINTS.get(infocode)
    if hint:
        print(f"  💡 infocode 含义: {hint}")


def render_regeo(label: str, location: str, expected: str | None, result: dict) -> None:
    """打印 regeo 结果 — 分节清晰, 便于截图贴 issue."""
    print(f"\n{'=' * 60}")
    print(f"📍 {label}  ({location})")
    print(f"   期望 province: {expected or '(空 — 预期落到海上)'}")
    print(f"{'=' * 60}")
    if result["error"]:
        print(f"  ❌ 网络层失败: {result['error']}")
        return
    print(f"  HTTP status   : {result['http_status']}")
    body = result["body"]
    if not isinstance(body, dict):
        print(f"  ⚠️  body 不是 dict: {body!r}")
        return
    print(f"  高德 status   : {body.get('status')}  (1=成功, 0=业务失败)")
    print(f"  高德 infocode : {body.get('infocode')}")
    print(f"  高德 info     : {body.get('info')}")
    _print_infocode_hint(body.get("infocode"))
    # 高德 regeo 接口实际返回 `regeocode` (单数 dict), 不是 `regeocodes` 数组
    regeocode = body.get("regeocode")
    if isinstance(regeocode, dict):
        print(f"  formatted_address: {regeocode.get('formatted_address')}")
        comp = regeocode.get("addressComponent") or {}
        if isinstance(comp, dict):
            print(
                f"  addressComponent: province={comp.get('province')!r}  "
                f"city={comp.get('city')!r}  district={comp.get('district')!r}  "
                f"adcode={comp.get('adcode')!r}"
            )
    else:
        print("  regeocode       : 空 (None)")
        if body.get("status") == "1":
            print("  ⚠️  status=1 但 regeocode 为空 → 坐标在海上 / 边界外 / key 未开通 regeo 权限")


def render_place_text(
    label: str, keywords: str, city: str | None, result: dict
) -> None:
    """打印 place_text 结果 — POI 列表便于肉眼核对"""
    print(f"\n{'=' * 60}")
    print(f"🔍 {label}")
    print(f"   keywords={keywords!r}  city={city or '(全国)'}")
    print(f"{'=' * 60}")
    if result["error"]:
        print(f"  ❌ 网络层失败: {result['error']}")
        return
    print(f"  HTTP status   : {result['http_status']}")
    body = result["body"]
    if not isinstance(body, dict):
        print(f"  ⚠️  body 不是 dict: {body!r}")
        return
    print(f"  高德 status   : {body.get('status')}  (1=成功, 0=业务失败)")
    print(f"  高德 infocode : {body.get('infocode')}")
    print(f"  高德 info     : {body.get('info')}")
    _print_infocode_hint(body.get("infocode"))
    pois = body.get("pois") or []
    print(f"  pois 命中数   : {len(pois)}")
    if isinstance(pois, list) and pois:
        # 只列前 5 条, 否则输出爆炸
        for i, item in enumerate(pois[:5], 1):
            if isinstance(item, dict):
                loc = item.get("location") or ""
                print(
                    f"    [{i}] {item.get('name')!r}  "
                    f"addr={item.get('address')!r}  "
                    f"loc={loc}  type={item.get('type')}"
                )
        if len(pois) > 5:
            print(f"    ... (省略 {len(pois) - 5} 条)")
    # 20002 是"建议城市列表", 不是错误
    suggestion = body.get("suggestion")
    if isinstance(suggestion, dict) and suggestion.get("cities"):
        cities = suggestion["cities"]
        if isinstance(cities, list) and cities:
            print(f"  城市建议 (高德提示 keyword 可能需要 city 限定):")
            for c in cities[:3]:
                if isinstance(c, dict):
                    print(f"    - {c.get('name')!r}  adcode={c.get('adcode')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="高德 API 一键诊断 (regeo / place_text)")
    parser.add_argument(
        "--mode",
        choices=["regeo", "place_text"],
        default="regeo",
        help="诊断模式 (默认 regeo)",
    )
    parser.add_argument(
        "--location",
        help='经纬度 "lng,lat" (仅 mode=regeo 时生效)',
    )
    parser.add_argument(
        "--keywords",
        help='搜索关键字 (仅 mode=place_text 时生效)',
    )
    parser.add_argument(
        "--city",
        help='限定城市 (仅 mode=place_text 时; 例: "上海" / "310100")',
    )
    parser.add_argument(
        "--types",
        help='POI 分类 (仅 mode=place_text 时; 例: "050000" 餐饮 / "商务住宅")',
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=10,
        help='返回条数上限 (仅 mode=place_text 时; 1-25, 默认 10)',
    )
    parser.add_argument(
        "--extensions",
        default="base",
        choices=["base", "all"],
        help="extensions 参数 (仅 mode=regeo 时; 默认 base)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".env",
        help=".env 路径",
    )
    args = parser.parse_args()

    key = load_amap_key(args.env_file)
    print(f"🔑 使用 AMAP_API_KEY: {key[:6]}…{key[-4:]}")
    print(f"🌐 端点: {URLS[args.mode]}")
    print(f"⚙️  mode: {args.mode}")

    has_any_hit = False

    if args.mode == "regeo":
        if args.location:
            points: list[tuple[str, str, str | None]] = [
                ("自定义", args.location, None),
            ]
        else:
            points = DEFAULT_LOCATIONS

        for label, location, expected in points:
            params = {
                "location": location,
                "extensions": args.extensions,
            }
            result = call_amap("regeo", key, params)
            render_regeo(label, location, expected, result)
            regeocode = result.get("body", {}).get("regeocode")
            if isinstance(regeocode, dict):
                has_any_hit = True
    else:  # place_text
        if args.keywords:
            queries: list[tuple[str, str, str | None]] = [
                ("自定义", args.keywords, args.city),
            ]
        else:
            queries = DEFAULT_QUERIES

        for label, keywords, city in queries:
            params: dict[str, str] = {
                "keywords": keywords,
                "offset": str(args.offset),
                "extensions": "base",
            }
            if city:
                params["city"] = city
                params["citylimit"] = "true"
            if args.types:
                params["types"] = args.types

            result = call_amap("place_text", key, params)
            render_place_text(label, keywords, city, result)
            pois = result.get("body", {}).get("pois") or []
            if isinstance(pois, list) and pois:
                has_any_hit = True

    # ---- 总结 + 退出码 ----
    print(f"\n{'=' * 60}")
    print("📊 诊断总结")
    print(f"{'=' * 60}")
    if has_any_hit:
        print(f"✅ {args.mode} 至少一个查询命中 — key 权限正常.")
        sys.exit(0)
    else:
        print(f"❌ {args.mode} 全部查询返回空.")
        if args.mode == "regeo":
            print("   最常见原因: 高德 key 没开通「逆地理编码」权限.")
        else:
            print("   最常见原因: 高德 key 没开通「Web 服务 API / POI 搜索」权限,")
            print("   或关键词太冷门 / 没限定 city.")
        print("   → 去 https://lbs.amap.com/dev/key/app 勾选后重跑.")
        sys.exit(1)


if __name__ == "__main__":
    main()