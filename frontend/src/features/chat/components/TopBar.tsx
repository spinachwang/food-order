/**
 * F050 — 顶栏
 *
 * prototype 行 734-748: 品牌 (午饭吃什么) + 单链接导航 (推荐) +
 * 时钟 (HH:MM · 周X) + 用户头像 (首字母 Z).
 * 时钟 30s tick (spec §6.x.3); 问候语按时段切换.
 */
import { useEffect, useState } from 'react'
import styles from './TopBar.module.css'

const AVATAR_INITIAL = 'Z'

interface TimeState {
  hours: number
  minutes: number
  weekday: string
}

function readNow(): TimeState {
  const d = new Date()
  return {
    hours: d.getHours(),
    minutes: d.getMinutes(),
    weekday: new Intl.DateTimeFormat('zh-CN', { weekday: 'long' }).format(d),
  }
}

function greetingFor(hour: number): string {
  if (hour < 6) return '凌晨好'
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

function formatClock(hours: number, minutes: number): string {
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

export interface TopBarProps {
  /** 用户显示名 (默认"张工" — prototype 行 755) */
  userName?: string
}

export function TopBar({ userName = '张工' }: TopBarProps): JSX.Element {
  const [time, setTime] = useState<TimeState>(() => readNow())

  useEffect(() => {
    const tick = () => setTime(readNow())
    tick()
    const id = window.setInterval(tick, 30_000)
    return () => window.clearInterval(id)
  }, [])

  const greeting = `${greetingFor(time.hours)}，${userName} 👋`

  return (
    <header className={styles.topbar} data-od-id="topbar">
      <div className={styles.inner}>
        <a className={styles.brand} href="#" data-od-id="brand">
          <span className={styles.brandDot} aria-hidden="true" />
          <span className={styles.brandText}>午饭吃什么</span>
        </a>
        <nav className={styles.nav} aria-label="主导航">
          <a className={styles.navLink} aria-current="page" href="#">
            推荐
          </a>
        </nav>
        <div className={styles.right}>
          <span className={styles.clock} aria-label="当前时间">
            <span className="mono">{formatClock(time.hours, time.minutes)}</span>
            <span className={styles.dotSep}> · </span>
            <span>{time.weekday}</span>
          </span>
          <div className={styles.avatar} aria-label={`用户头像 ${AVATAR_INITIAL}`}>
            {AVATAR_INITIAL}
          </div>
          <span className={styles.greetingSr} aria-label={`问候: ${greeting}`}>
            {greeting}
          </span>
        </div>
      </div>
    </header>
  )
}