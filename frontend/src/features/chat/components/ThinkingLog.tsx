/**
 * F050 — Thinking 步骤日志 (sticky aside)
 *
 * 读 chatStore.thinking, 渲染步骤列表.
 * 步骤由 useAgentStream 维护, 每条 SSE 事件对应 1 步或 N 步.
 */
import { useChatStore } from '../../../stores/chatStore'
import styles from './ThinkingLog.module.css'

function statusClass(s: string): string {
  switch (s) {
    case 'done':
      return styles.done ?? ''
    case 'error':
      return styles.error ?? ''
    default:
      return styles.pending ?? ''
  }
}

function statusIcon(s: string): string {
  switch (s) {
    case 'done':
      return '✓'
    case 'error':
      return '✗'
    default:
      return '…'
  }
}

export function ThinkingLog(): JSX.Element {
  const thinking = useChatStore((s) => s.thinking)
  const status = useChatStore((s) => s.status)

  const headLabel = status === 'streaming' ? 'agent 思考中…' : status === 'error' ? 'agent 出错' : '今日决策路径'

  return (
    <aside className={styles.aside} data-od-id="thinking-log" aria-label="思考日志">
      <header className={styles.head}>
        <span className={`${styles.dot} ${styles[`dot_${status}`] ?? ''}`} aria-hidden="true" />
        <span className={styles.headLabel}>{headLabel}</span>
      </header>
      {thinking.length === 0 ? (
        <p className={styles.placeholder}>点"问 agent"开始追踪</p>
      ) : (
        <ol className={styles.list}>
          {thinking.map((step) => (
            <li key={step.marker} className={`${styles.item} ${statusClass(step.status)}`}>
              <span className={styles.marker} aria-hidden="true">
                {statusIcon(step.status)}
              </span>
              <div className={styles.itemBody}>
                <p className={styles.itemTitle}>{step.title}</p>
                <p className={styles.itemEm}>{step.em}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  )
}