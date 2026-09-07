/**
 * F050 — 底栏
 * prototype 行 1065-1068: 左版本 / 右数据来源.
 */
import styles from './Footer.module.css'

const VERSION = 'Lunch Agent v0.3'
const SLOGAN = '让打工牛马不再为中午吃什么内耗'
const DATA_SOURCES = '数据: 高德 POI · 实时排队 · 你的过去 30 天'

export function Footer(): JSX.Element {
  return (
    <footer className={styles.foot} data-od-id="foot">
      <span>
        午饭吃什么 · {VERSION} · {SLOGAN}
      </span>
      <span>{DATA_SOURCES}</span>
    </footer>
  )
}