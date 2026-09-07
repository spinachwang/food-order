/**
 * F050 — 备选餐厅卡 (小卡, 最多 2 张)
 *
 * 读 recommendation.alternatives.
 * 触发 promote: 把 alt 提升为新主推 (chatStore.promoteAlternative).
 * tabindex=0 + Enter/Space 触发 (a11y).
 */
import type { KeyboardEvent } from 'react'
import { useChatStore } from '../../../stores/chatStore'
import type { AltRecommendation } from '../types'
import styles from './AltCard.module.css'

export interface AltCardProps {
  alternative: AltRecommendation
  index: number
}

export function AltCard({ alternative, index }: AltCardProps): JSX.Element {
  const promoteAlternative = useChatStore((s) => s.promoteAlternative)

  const onActivate = (): void => {
    promoteAlternative(alternative)
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onActivate()
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      className={styles.card}
      data-od-id={`alt-${index + 1}`}
      onClick={onActivate}
      onKeyDown={onKey}
      aria-label={`备选 ${alternative.restaurant_name},点击切换为主推`}
    >
      <div className={styles.body}>
        <p className={styles.eyebrow}>备选 · {alternative.cuisine_id}</p>
        <h4 className={styles.title}>{alternative.restaurant_name}</h4>
        <p className={styles.reason}>{alternative.short_reason}</p>
      </div>
      <span className={styles.cta} aria-hidden="true">换这个 →</span>
    </div>
  )
}