/**
 * F050 — 主推餐厅卡 (大卡, No.1)
 *
 * 读 chatStore.recommendation + restaurantListsByCuisine 取距离/人均.
 * 三按钮: go-eat / share-eat / save-eat (spec §2.4).
 *   go-eat: 跳转高德 marker (lng,lat,name)
 *   share-eat: copy + toast
 *   save-eat: 切按钮文案 + toast (M1 不发后端, spec §8 #2)
 *
 * 降级态: recommendation=null → 占位文案 (spec §5).
 */
import { useMemo, useState } from 'react'
import { useChatStore } from '../../../stores/chatStore'
import { useToast } from '../hooks/useToast'
import { copyToClipboard } from '../../../lib/clip'
import { DEGRADED_HEADLINE, type CuisineId } from '../types'
import styles from './RecommendationCard.module.css'

const HIGHLIGHT_KEYWORDS = ['暖身', '治愈', '快速', '实惠', '麻辣', '清淡'] as const

function formatDistance(m: number | null | undefined): string {
  if (m == null) return '未知'
  return m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1)}km`
}

function formatPrice(p: string | null | undefined): string {
  if (!p) return '—'
  return `¥${p}`
}

function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}/100`
}

function amapMarkerUrl(lngLat: [number, number] | undefined, name: string): string {
  if (!lngLat) return 'https://uri.amap.com/marker'
  const [lng, lat] = lngLat
  return `https://uri.amap.com/marker?position=${lng},${lat}&name=${encodeURIComponent(name)}`
}

export function RecommendationCard(): JSX.Element {
  const recommendation = useChatStore((s) => s.recommendation)
  const restaurantLists = useChatStore((s) => s.restaurantListsByCuisine)
  const status = useChatStore((s) => s.status)
  const toast = useToast()
  const [saved, setSaved] = useState(false)

  const restaurant = useMemo(() => {
    if (!recommendation) return null
    const list = restaurantLists[recommendation.cuisine_id as CuisineId] ?? []
    return list.find((r) => r.poi_id === recommendation.restaurant_id) ?? null
  }, [recommendation, restaurantLists])

  // 降级: 无主推 / 流式中断后空
  if (!recommendation) {
    const isError = status === 'error'
    return (
      <article className={`${styles.card} ${styles.empty}`} data-od-id="reco-main-empty">
        <div className={styles.emptyInner}>
          <p className={styles.emptyEyebrow}>暂无主推</p>
          <h3 className={styles.emptyTitle}>
            {isError ? 'agent 没跑完 · 试试调整距离/预算' : DEGRADED_HEADLINE}
          </h3>
          <p className={styles.emptyHint}>
            {isError ? '或者直接编辑上面的偏好再问一次' : '可以试试勾几个口味 chip, 再问一次'}
          </p>
        </div>
      </article>
    )
  }

  const onGoEat = (): void => {
    const url = amapMarkerUrl(restaurant?.location, recommendation.restaurant_name)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const onShare = async (): Promise<void> => {
    const dist = formatDistance(restaurant?.distance_meters)
    const url = amapMarkerUrl(restaurant?.location, recommendation.restaurant_name)
    const text = `${recommendation.restaurant_name} · ${dist}\n${url}`
    try {
      await copyToClipboard(text)
      toast.push('success', '已复制到剪贴板')
    } catch (err: unknown) {
      toast.push('error', '复制失败')
    }
  }

  const onSave = (): void => {
    // M1 仅本地, spec §8 #2
    setSaved(true)
    toast.push('success', '已收藏(本地)')
  }

  const highlightTags: string[] = HIGHLIGHT_KEYWORDS.filter((k) => recommendation.reason.includes(k))
  const allTags =
    highlightTags.length > 0
      ? highlightTags
      : [recommendation.order_takeout ? '外卖' : '到店']

  return (
    <article className={styles.card} data-od-id="reco-main">
      <div className={styles.visual}>
        <span className={styles.badge}>No.1 · 今日主推</span>
        <span className={styles.score} aria-label={`匹配度 ${formatConfidence(recommendation.confidence)}`}>
          {formatConfidence(recommendation.confidence)}
        </span>
      </div>
      <div className={styles.body}>
        <p className={styles.eyebrow}>
          {recommendation.order_takeout ? '外卖 · ' : '到店 · '}
          <strong>{recommendation.restaurant_name}</strong>
        </p>
        <h3 className={styles.headline}>{recommendation.headline}</h3>
        <p className={styles.dish}>
          {recommendation.cuisine_id} · {recommendation.order_takeout ? '送上门' : '堂食'}
        </p>
        <p className={styles.desc}>{recommendation.reason}</p>
        <div className={styles.tags}>
          {allTags.map((t) => (
            <span key={t} className={styles.tagGood}>
              ✓ {t}
            </span>
          ))}
        </div>
        <dl className={styles.stats}>
          <div className={styles.stat}>
            <dt>距离</dt>
            <dd>{formatDistance(restaurant?.distance_meters)}</dd>
          </div>
          <div className={styles.stat}>
            <dt>人均</dt>
            <dd>{formatPrice(restaurant?.avg_price)}</dd>
          </div>
          <div className={styles.stat}>
            <dt>匹配度</dt>
            <dd>{formatConfidence(recommendation.confidence)}</dd>
          </div>
        </dl>
        <div className={styles.cta}>
          <button type="button" className={styles.primary} data-od-id="go-eat" onClick={onGoEat}>
            出发去吃
          </button>
          <button type="button" className={styles.secondary} data-od-id="share-eat" onClick={() => void onShare()}>
            分享这顿
          </button>
          <button
            type="button"
            className={`${styles.secondary} ${saved ? styles.saved : ''}`}
            data-od-id="save-eat"
            onClick={onSave}
            disabled={saved}
          >
            {saved ? '已收藏' : '收藏'}
          </button>
        </div>
      </div>
    </article>
  )
}