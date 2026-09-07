/**
 * F050 — Mood (心情: emoji + 名称,单选)
 *
 * prototype 行 907-921: 4 个心情卡.
 * 受控:父组件持有 selected (单一字符串),传 pressed + onSelect.
 */
import styles from './Mood.module.css'

export interface MoodOption {
  id: string
  emoji: string
  label: string
}

export interface MoodProps {
  option: MoodOption
  pressed: boolean
  onSelect: (id: string) => void
}

export function Mood({ option, pressed, onSelect }: MoodProps): JSX.Element {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={pressed}
      className={`${styles.mood} ${pressed ? styles.pressed : ''}`}
      data-od-id={`mood-${option.id}`}
      onClick={() => onSelect(option.id)}
    >
      <span className={styles.emoji} aria-hidden="true">
        {option.emoji}
      </span>
      <span className={styles.label}>{option.label}</span>
    </button>
  )
}