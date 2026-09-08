/**
 * F050 / F051 — ContextStrip (实时上下文卡片: 地址 + 天气)
 *
 * prototype 行 770-810 顶部双卡.
 * 左侧: 地址 (来自 chatStore.address → formatAddressSummary) + 编辑按钮.
 * 右侧: 天气 (来自 chatStore.weather); 空态: "天气暂不可用 · agent 按默认决策".
 *
 * F051 §6.5 变更:
 * - `address` 现在是 `StructuredAddress | null`，由 `formatAddressSummary`
 *   拼成单行字符串；为 null 时回退到 `DEFAULT_LEGACY_ADDRESS` (UI 兜底).
 * - 编辑按钮改为触发 `useAddressPicker()` (Phase E-2 落地实际 Dialog).
 *   原 `window.prompt` 流 (AddressEditPopover.tsx) 已删除.
 */
import { useChatStore, DEFAULT_LEGACY_ADDRESS } from '../../../stores/chatStore'
import { useAddressPicker } from '../../address/hooks/useAddressPicker'
import { formatAddressSummary } from '../../address/utils/formatAddressSummary'
import styles from './ContextStrip.module.css'

export interface ContextStripProps {
  /** 当前时间(由外部注入,用于"查看时间"显示). 不传则隐藏. */
  now?: Date
}

function formatTemp(c: number): string {
  return `${Math.round(c)}°`
}

function formatWind(direction: string, level: number): string {
  return `${direction}风 ${level}级`
}

export function ContextStrip({ now }: ContextStripProps): JSX.Element {
  const address = useChatStore((s) => s.address)
  const weather = useChatStore((s) => s.weather)
  const { openDialog } = useAddressPicker()

  const hour = now?.getHours()
  const minute = now?.getMinutes()
  const clock =
    typeof hour === 'number' && typeof minute === 'number'
      ? `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
      : null

  // F051 §6.5: 结构化地址 → 单行摘要；为 null 时显示旧字符串兜底
  const addressDisplay =
    formatAddressSummary(address) || DEFAULT_LEGACY_ADDRESS

  return (
    <section className={styles.strip} data-od-id="context-strip">
      <article className={styles.card}>
        <div className={styles.iconCircle} aria-hidden="true">
          📍
        </div>
        <div className={styles.body}>
          <p className={styles.label}>你在</p>
          <p className={styles.value} data-od-id="addr-summary">{addressDisplay}</p>
          <p className={styles.hint}>
            {clock ? `正在查看 · ${clock} · Agent 已锁定这个位置` : 'Agent 已锁定这个位置'}
          </p>
        </div>
        <button
          type="button"
          className={styles.edit}
          data-od-id="addr-edit"
          onClick={openDialog}
        >
          编辑
        </button>
      </article>
      <article className={styles.card}>
        <div className={styles.iconCircle} aria-hidden="true">
          {weather ? weatherIconFor(weather.condition) : '☁️'}
        </div>
        <div className={styles.body}>
          <p className={styles.label}>天气</p>
          {weather ? (
            <>
              <p className={styles.value}>
                {formatTemp(weather.temperature_celsius)} · {weather.condition}
              </p>
              <p className={styles.hint}>
                {formatWind(weather.wind_direction, weather.wind_level)} · 湿度{' '}
                {weather.humidity_percent}%
              </p>
            </>
          ) : (
            <>
              <p className={styles.valueMuted}>天气暂不可用</p>
              <p className={styles.hint}>Agent 按默认决策</p>
            </>
          )}
        </div>
      </article>
    </section>
  )
}

function weatherIconFor(condition: string): string {
  switch (condition) {
    case 'sunny':
      return '☀️'
    case 'cloudy':
      return '☁️'
    case 'rainy':
      return '🌧️'
    case 'snowy':
      return '❄️'
    case 'foggy':
      return '🌫️'
    case 'dust':
      return '🌪️'
    default:
      return '☁️'
  }
}
