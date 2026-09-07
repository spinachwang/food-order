/**
 * F050 — useToast hook
 *
 * 包 toastStore.push/dismiss/clear, 提供类型化 API:
 *   toast.info(msg) / toast.success(msg) / toast.error(msg)
 */
import { useCallback } from 'react'
import { useToastStore, type ToastKind } from '../../../stores/toastStore'

export interface ToastApi {
  push: (kind: ToastKind, message: string) => string
  info: (message: string) => string
  success: (message: string) => string
  error: (message: string) => string
  dismiss: (id: string) => void
  clear: () => void
}

export function useToast(): ToastApi {
  const pushRaw = useToastStore((s) => s.push)
  const dismiss = useToastStore((s) => s.dismiss)
  const clear = useToastStore((s) => s.clear)

  const info = useCallback((m: string) => pushRaw('info', m), [pushRaw])
  const success = useCallback((m: string) => pushRaw('success', m), [pushRaw])
  const error = useCallback((m: string) => pushRaw('error', m), [pushRaw])

  return { push: pushRaw, info, success, error, dismiss, clear }
}