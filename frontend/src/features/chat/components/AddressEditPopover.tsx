/**
 * F050 — 地址编辑弹窗 (M1: window.prompt 简易版)
 *
 * spec §6.x.3: 点击地址卡片右侧"编辑" → 弹出 window.prompt;
 * 用户输入新地址 → 写入 chatStore.address;空字符串回退默认值.
 *
 * 这是一个**触发器函数**:它本身不渲染任何 UI,只是执行副作用.
 * 由 ContextStrip 内部的"编辑"按钮调起.
 */
import { DEFAULT_ADDRESS, useChatStore } from '../../../stores/chatStore'

export { DEFAULT_ADDRESS }

/**
 * 在 prompt 中拿到用户输入的地址, 写入 chatStore.
 * 返回用户实际写入的地址(回退默认);若取消则不写入, 返回 null.
 */
export function editAddress(): string | null {
  const current = useChatStore.getState().address
  // jsdom 没有 prompt 实现,需由 host (ContextStrip) 在测试中 mock.
  const raw = window.prompt('更新你现在在的位置', current)
  if (raw === null) return null
  const trimmed = raw.trim()
  const next = trimmed.length === 0 ? DEFAULT_ADDRESS : trimmed
  useChatStore.getState().setAddress(next)
  return next
}