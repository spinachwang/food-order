/**
 * F051 §6.5 — `StructuredAddress` → 单行摘要字符串.
 *
 * 显示规则 (per spec §2.3 + §6.5):
 * - `null` → 返回空字符串 (`''`)，调用方决定回退文本
 * - 仅城市级 → `上海`
 * - 城市 + 区 → `上海 · 静安区`
 * - 城市 + 区 + 小区 → `上海 · 静安区 · 静安嘉里中心`
 * - 全字段 → `上海 · 静安区 · 静安嘉里中心 · B2`
 *
 * 拼接符统一 ` · ` (中点 + 空格)，与现有 `DEFAULT_ADDRESS` 风格一致.
 * 字段为空 / null / 仅空白时跳过该层.
 *
 * 不在这里实现『回退到 DEFAULT_LEGACY_ADDRESS』— 调用方按需叠加,
 * 避免 helper 耦合 store / 常量. UI 显示路径:
 *   `formatAddressSummary(addr) || DEFAULT_LEGACY_ADDRESS`
 */
import type { StructuredAddress } from '../../chat/types'

export function formatAddressSummary(addr: StructuredAddress | null): string {
  if (!addr) return ''
  // 跳过 null / 空字符串 / 仅空白 — 与后端 `str_strip_whitespace=True` 对齐
  const parts = [
    addr.city,
    addr.district,
    addr.community,
    addr.door_no,
  ].filter(
    (p): p is string => typeof p === 'string' && p.trim().length > 0,
  )
  return parts.join(' · ')
}
