/**
 * F050 — Toggle (3 选 1 radiogroup 中的一个按钮)
 *
 * prototype 行 873-883 行 — 凉/温/热 三选一;同一行内互斥.
 * 受控:父组件持有 selected,传 pressed + onSelect.
 */
import styles from './Toggle.module.css'

export interface ToggleProps {
  /** 单选项 id (推荐联合,例如 'cold' | 'room' | 'hot');父组件持有 selected */
  id: string
  label: string
  pressed: boolean
  onSelect: (id: string) => void
}

export function Toggle({ id, label, pressed, onSelect }: ToggleProps): JSX.Element {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={pressed}
      className={`${styles.toggle} ${pressed ? styles.pressed : ''}`}
      data-od-id={`toggle-${id}`}
      onClick={() => onSelect(id)}
    >
      {label}
    </button>
  )
}