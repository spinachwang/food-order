/**
 * F050 — Slider (原生 input[type=range] 样式封装)
 *
 * 复用 prototype 行 309-318 的 thumb 样式.
 * 受控:父组件持有 value + onChange.
 */
import type { ChangeEvent } from 'react'
import styles from './Slider.module.css'

export interface SliderProps {
  label: string
  value: number
  min: number
  max: number
  step?: number
  suffix?: string
  onChange: (value: number) => void
  /** a11y id, 必填;父组件传 `slider-distance` / `slider-budget` 等 */
  ariaId: string
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  suffix,
  onChange,
  ariaId,
}: SliderProps): JSX.Element {
  const handle = (e: ChangeEvent<HTMLInputElement>): void => {
    const next = Number(e.target.value)
    if (!Number.isFinite(next)) return
    onChange(next)
  }

  return (
    <label className={styles.row} htmlFor={ariaId}>
      <span className={styles.label}>{label}</span>
      <input
        id={ariaId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={handle}
        className={styles.input}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
      />
      <span className={styles.value} data-od-id={`${ariaId}-value`}>
        {value}
        {suffix ?? ''}
      </span>
    </label>
  )
}