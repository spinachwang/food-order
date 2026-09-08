/**
 * F051 §4 — AddressPickerDialog 触发器 hook.
 *
 * 当前 (Phase F-3) 只实现开关 state, 由 ContextStrip 编辑按钮调用.
 * 真正的 Dialog 组件在 Phase E-2 落地, 届时此处只接进
 * `<AddressPickerDialog open={open} onClose={close} onSave={...} />`.
 *
 * 用 `useSyncExternalStore` 订阅模块级 boolean — 与 zustand store 一致的
 * 外部订阅模式, 避免 Provider 嵌套; 多个组件订阅同一 state 保持同步.
 */
import { useSyncExternalStore } from 'react'

let _open = false

function subscribe(listener: () => void): () => void {
  _listeners.add(listener)
  return () => {
    _listeners.delete(listener)
  }
}

const _listeners = new Set<() => void>()

function setOpen(next: boolean): void {
  if (_open === next) return
  _open = next
  _listeners.forEach((fn) => fn())
}

function getSnapshot(): boolean {
  return _open
}

export interface UseAddressPickerResult {
  open: boolean
  openDialog: () => void
  closeDialog: () => void
}

export function useAddressPicker(): UseAddressPickerResult {
  const open = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  return {
    open,
    openDialog: () => setOpen(true),
    closeDialog: () => setOpen(false),
  }
}

/** 测试辅助: 重置全局 state. */
export function _resetAddressPickerForTests(): void {
  _open = false
  _listeners.clear()
}
