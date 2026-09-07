/**
 * F050 — Toast 通知 store (Zustand)
 *
 * 3 种类型: info / success / error
 * ≤3 条同时显示; 超出排队 (新 push 替换最旧)
 * 自动 dismiss: 4 秒 (Phase C Toaster 组件订阅 timer)
 */
import { create } from 'zustand'

export type ToastKind = 'info' | 'success' | 'error'

export interface Toast {
  id: string
  kind: ToastKind
  message: string
  createdAt: number
}

interface ToastStore {
  toasts: Toast[]
  push: (kind: ToastKind, message: string) => string
  dismiss: (id: string) => void
  clear: () => void
}

const MAX_VISIBLE = 3
let counter = 0
const nextId = () => `toast-${++counter}-${Date.now()}`

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (kind, message) => {
    const id = nextId()
    set((state) => {
      const next = [...state.toasts, { id, kind, message, createdAt: Date.now() }]
      // 超出最大可见数: 丢弃最早的
      return { toasts: next.slice(-MAX_VISIBLE) }
    })
    return id
  },
  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}))