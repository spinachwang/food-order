/**
 * F050 — Hero 主欢迎区
 *
 * prototype 行 753-767: 左侧问候语 + h1 (含 em "吃点好的") + 副文案;
 * 右侧 hero-meta: 午餐窗口 + Agent 在线绿点.
 */
import styles from './Hero.module.css'

export interface HeroProps {
  greeting: string
}

const LUNCH_WINDOW = '11:50 — 13:30'

export function Hero({ greeting }: HeroProps): JSX.Element {
  return (
    <section className={styles.hero} data-od-id="hero">
      <div className={styles.lead}>
        <p className={styles.greet}>{greeting}</p>
        <h1 className={styles.headline}>
          今天中午,<em>吃点好的</em>
          <br />
          别再吃昨天那家了。
        </h1>
        <p className={styles.sub}>
          告诉我你现在在哪、想吃什么, 我把方圆一公里内最适合你这顿午饭的选项筛出来 ——
          不再让你在地图 APP 里翻 20 分钟。
        </p>
      </div>
      <aside className={styles.meta} aria-label="实时上下文">
        <div className={styles.metaCard}>
          <p className={styles.metaLabel}>午餐窗口</p>
          <p className={styles.metaValue}>{LUNCH_WINDOW}</p>
          <p className={styles.metaHint}>开放时段</p>
        </div>
        <div className={styles.metaRow}>
          <span className={styles.metaDot} aria-hidden="true" />
          <span>Agent 在线 · 实时拉取高德 POI</span>
        </div>
      </aside>
    </section>
  )
}