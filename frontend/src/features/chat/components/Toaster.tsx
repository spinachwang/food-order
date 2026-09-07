/**
 * F050 — Toast 全局通知组件
 *
 * 订阅 toastStore.toasts, 按 kind 渲染 fixed bottom-right 容器;
 * 自动 4 秒消失 (Phase C 验收: ≤3 条同时显示).
 */
import { useEffect } from 'react'
import { useToastStore } from '../../../stores/toastStore'
import styles from './Toaster.module.css'

const AUTO_DISMISS_MS = 4000

export function Toaster(): JSX.Element {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  // 每条 toast 启动一个 auto-dismiss timer
  useEffect(() => {
    if (toasts.length === 0) return
    const timers = toasts.map((t) =>
      window.setTimeout(() => dismiss(t.id), AUTO_DISMISS_MS),
    )
    return () => {
      timers.forEach((id) => window.clearTimeout(id))
    }
  }, [toasts, dismiss])

  return (
    <div className={styles.container} role="region" aria-label="通知" data-od-id="toaster">
      {toasts.map((t) => (
        <button
          key={t.id}
          className={`${styles.toast} ${styles[t.kind]}`}
          onClick={() => dismiss(t.id)}
          aria-live="polite"
        >
          <span className={styles.message}>{t.message}</span>
        </button>
      ))}
    </div>
  )
}