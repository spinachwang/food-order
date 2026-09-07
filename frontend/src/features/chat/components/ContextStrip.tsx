/**
 * F050 — ContextStrip (实时上下文卡片: 地址 + 天气)
 *
 * prototype 行 770-810 顶部双卡.
 * 左侧: 地址 (来自 chatStore.address) + 编辑按钮 → 调 editAddress.
 * 右侧: 天气 (来自 chatStore.weather); 实时由 useAgentStream 注入;
 *        空态: "天气暂不可用 · agent 按默认决策" (spec §5).
 */
import { useChatStore } from '../../../stores/chatStore'
import { editAddress } from './AddressEditPopover'
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

  const hour = now?.getHours()
  const minute = now?.getMinutes()
  const clock =
    typeof hour === 'number' && typeof minute === 'number'
      ? `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
      : null

  return (
    <section className={styles.strip} data-od-id="context-strip">
      <article className={styles.card}>
        <div className={styles.iconCircle} aria-hidden="true">
          📍
        </div>
        <div className={styles.body}>
          <p className={styles.label}>你在</p>
          <p className={styles.value}>{address}</p>
          <p className={styles.hint}>
            {clock ? `正在查看 · ${clock} · Agent 已锁定这个位置` : 'Agent 已锁定这个位置'}
          </p>
        </div>
        <button
          type="button"
          className={styles.edit}
          data-od-id="addr-edit"
          onClick={() => editAddress()}
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