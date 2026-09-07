/**
 * F050 — Chat 顶层布局
 *
 * 组合: TopBar + Hero + ContextStrip + PreferencesPanel +
 *       (reco-wrap = RecommendationCard + AltCard[] + ThinkingLog) +
 *       Footer + Toaster.
 *
 * 不挂 router (M1); 主页面即首页.
 */
import { useMemo, useState, useEffect } from 'react'
import { TopBar } from './components/TopBar'
import { Hero } from './components/Hero'
import { ContextStrip } from './components/ContextStrip'
import { PreferencesPanel } from './components/PreferencesPanel'
import { RecommendationCard } from './components/RecommendationCard'
import { AltCard } from './components/AltCard'
import { ThinkingLog } from './components/ThinkingLog'
import { Footer } from './components/Footer'
import { Toaster } from './components/Toaster'
import { useChatStore } from '../../stores/chatStore'
import styles from './ChatShell.module.css'

function greetingFor(hour: number): string {
  if (hour < 6) return '凌晨好'
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

export function ChatShell(): JSX.Element {
  const alternatives = useChatStore((s) => s.recommendation?.alternatives ?? [])

  // 半小时刷一次时钟 + 问候语
  const [now, setNow] = useState<Date>(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const greeting = useMemo(
    () => `${greetingFor(now.getHours())}，张工 👋`,
    [now],
  )

  return (
    <div className={styles.shell}>
      <TopBar />
      <main className={styles.main}>
        <Hero greeting={greeting} />
        <ContextStrip now={now} />
        <PreferencesPanel />
        <section className={styles.recoWrap} data-od-id="reco-wrap">
          <div className={styles.recoMain}>
            <RecommendationCard />
            {alternatives.length > 0 ? (
              <div className={styles.altGrid} data-od-id="reco-alt">
                <p className={styles.altHeading}>备选 (点一下切换)</p>
                {alternatives.map((alt, i) => (
                  <AltCard key={alt.restaurant_id} alternative={alt} index={i} />
                ))}
              </div>
            ) : null}
          </div>
          <ThinkingLog />
        </section>
      </main>
      <Footer />
      <Toaster />
    </div>
  )
}