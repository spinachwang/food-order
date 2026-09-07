/**
 * F050 — Chip (通用多选 chip)
 *
 * prototype 行 871-881 (口味) / 行 922-928 (忌口) 通用样式.
 * 受控:父组件持有 selected 集合,通过 onToggle(id) 更新.
 */
import styles from './Chip.module.css'

export type ChipVariant = 'taste' | 'avoid' | 'neutral'

export interface ChipProps<T extends string = string> {
  /** 唯一 id (写入 chatStore.selectedTaste / .allergies 用) */
  id: T
  label: string
  /** 副标题(可选,显示在 label 下方,例如忌口"含花生的菜") */
  hint?: string
  pressed: boolean
  onToggle: (id: T) => void
  variant?: ChipVariant
}

export function Chip<T extends string = string>({
  id,
  label,
  hint,
  pressed,
  onToggle,
  variant = 'taste',
}: ChipProps<T>): JSX.Element {
  return (
    <button
      type="button"
      className={`${styles.chip} ${pressed ? styles.pressed : ''} ${styles[variant]}`}
      aria-pressed={pressed}
      data-od-id={`chip-${id}`}
      onClick={() => onToggle(id)}
    >
      <span className={styles.label}>{label}</span>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </button>
  )
}