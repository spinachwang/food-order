/**
 * F050 — 偏好面板 (5 行 + CTA)
 *
 * prototype 行 813-928 复刻, 但用 chatStore (本地) + usePutPreferences (远端) 双向同步.
 *
 * - 5 行: 口味 (chip 多选) / 温度 (toggle 三选) / 心情 (mood 四选) /
 *   距离 (slider 0-100 → 分钟) / 预算 (slider 0-100 → ¥).
 * - 忌口 (chip 多选, 第 6 行: 放在预算下, 与 spec §2.4 reset-prefs 排序一致).
 * - CTA 行: 左 "N 项偏好" 计数; 右 "surprise" / "ask-agent" (后者调 useAgentStream.start).
 * - reset-prefs: 恢复默认 + 调 PUT (远端同步).
 * - preset-rainy: 套用雨天 (仅本地, 不调后端, spec §8 #4).
 */
import { useEffect, useMemo, useState } from 'react'
import { useChatStore, DEFAULT_UI_PREFS } from '../../../stores/chatStore'
import { usePutPreferences, usePreferencesQuery } from '../hooks/usePreferences'
import { useToast } from '../hooks/useToast'
import { useAgentStream } from '../hooks/useAgentStream'
import { Chip } from './Chip'
import { Toggle } from './Toggle'
import { Mood, type MoodOption } from './Mood'
import { Slider } from './Slider'
import {
  ALLERGY_VALUES,
  CUISINE_IDS,
  RAINY_PRESET,
  type AllergyValue,
  type CuisineId,
  type TemperaturePreference,
} from '../types'
import {
  sliderToBudget,
  sliderToDistanceMin,
  tasteToCuisineWeights,
} from '../schemas'
import type { ChatRequest } from '../types'
import styles from './PreferencesPanel.module.css'

// =====================================================================
// label maps (UI 层, 独立于 types.ts; 中文展示)
// =====================================================================

const CUISINE_LABELS: Record<CuisineId, string> = {
  sichuan: '川菜',
  cantonese: '粤菜',
  shandong: '鲁菜',
  suzhou: '苏菜',
  zhejiang: '浙菜',
  fujian: '闽菜',
  hunan: '湘菜',
  anhui: '徽菜',
  japanese: '日料',
  western: '西餐',
  western_fastfood: '西式快餐',
  chinese_fastfood: '中式快餐',
  snacks: '小吃',
  dessert_drinks: '甜品饮品',
}

const ALLERGY_LABELS: Record<AllergyValue, string> = {
  peanut: '花生',
  tree_nut: '坚果',
  shellfish: '甲壳类',
  fish: '鱼类',
  egg: '蛋类',
  soy: '大豆',
  wheat: '麸质',
  dairy: '乳制品',
  sesame: '芝麻',
  alcohol: '酒精',
  fried_food: '油炸',
}

const TEMPERATURE_OPTIONS: { id: TemperaturePreference; label: string }[] = [
  { id: 'cold', label: '凉菜 / 沙拉' },
  { id: 'room', label: '常温' },
  { id: 'hot', label: '热菜' },
]

const MOOD_OPTIONS: MoodOption[] = [
  { id: 'want-better', emoji: '🌞', label: '想吃好点' },
  { id: 'want-quick', emoji: '⚡', label: '10 分钟解决' },
  { id: 'want-cheap', emoji: '💸', label: '吃个便宜的' },
  { id: 'want-comfort', emoji: '🍜', label: '想被治愈' },
]

function toggleSet<T>(arr: readonly T[], v: T): T[] {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]
}

function useArrayToggle<K extends string>(
  _key: 'taste' | 'allergies',
  values: readonly K[],
  onChange: (next: K[]) => void,
): (id: K) => void {
  return (id: K) => {
    const next = toggleSet(values, id)
    onChange(next)
  }
}

// =====================================================================
// PreferencesPanel
// =====================================================================

export function PreferencesPanel(): JSX.Element {
  const uiPrefs = useChatStore((s) => s.uiPrefs)
  const setUiPrefs = useChatStore((s) => s.setUiPrefs)
  const resetUiPrefs = useChatStore((s) => s.resetUiPrefs)
  const sessionId = useChatStore((s) => s.sessionId)
  const setSessionId = useChatStore((s) => s.setSessionId)
  const address = useChatStore((s) => s.address)
  const status = useChatStore((s) => s.status)

  const { mutateAsync: putPrefs } = usePutPreferences()
  const { data: remotePrefs } = usePreferencesQuery()
  const toast = useToast()
  const { start } = useAgentStream()

  // 起步时把后端拉到的 cuisine_weights / 预算同步进本地 uiPrefs (一次性)
  const [hydrated, setHydrated] = useState(false)
  useEffect(() => {
    if (hydrated || !remotePrefs) return
    const cuisineWeights = remotePrefs.cuisine_weights
    const taste = CUISINE_IDS.filter((id) => (cuisineWeights[id] ?? 0.5) >= 0.99)
    setUiPrefs({
      taste,
      allergies: remotePrefs.allergies,
      temperature: remotePrefs.temperature_preference,
      budget: Math.round(((remotePrefs.budget_lunch_max ?? 55) - 20) / 0.6),
    })
    setHydrated(true)
  }, [hydrated, remotePrefs, setUiPrefs])

  const totalCount = useMemo(
    () =>
      uiPrefs.taste.length +
      uiPrefs.allergies.length +
      (uiPrefs.temperature === 'hot' ? 0 : 1) +
      (uiPrefs.mood === 'want-better' ? 0 : 1) +
      (uiPrefs.distance === 35 ? 0 : 1) +
      (uiPrefs.budget === 55 ? 0 : 1),
    [uiPrefs],
  )

  const onTasteToggle = useArrayToggle('taste', uiPrefs.taste, (next) =>
    setUiPrefs({ taste: next }),
  )
  const onAllergyToggle = useArrayToggle('allergies', uiPrefs.allergies, (next) =>
    setUiPrefs({ allergies: next }),
  )
  const onTempSelect = (id: string) =>
    setUiPrefs({ temperature: id as TemperaturePreference })
  const onMoodSelect = (id: string) => setUiPrefs({ mood: id })
  const onDistanceChange = (v: number) => setUiPrefs({ distance: v })
  const onBudgetChange = (v: number) => setUiPrefs({ budget: v })

  async function buildApiPayload() {
    return {
      cuisine_weights: tasteToCuisineWeights(uiPrefs.taste),
      allergies: uiPrefs.allergies,
      spice_tolerance: 1,
      temperature_preference: uiPrefs.temperature,
      default_location: address,
      budget_lunch_min: null,
      budget_lunch_max: sliderToBudget(uiPrefs.budget),
    }
  }

  async function handleAskAgent(): Promise<void> {
    const payload = await buildApiPayload()
    try {
      await putPrefs(payload)
    } catch (err: unknown) {
      toast.push('error', '偏好保存失败,仍继续推荐')
    }
    const req: ChatRequest = {
      message: `mood=${uiPrefs.mood}, distance=${sliderToDistanceMin(uiPrefs.distance)}min, temp=${uiPrefs.temperature}`,
      session_id: sessionId,
    }
    try {
      await start(req)
      const sid = useChatStore.getState().sessionId
      if (!sid) setSessionId(crypto.randomUUID())
    } catch (err: unknown) {
      toast.push('error', 'agent 出错了')
    }
  }

  async function handleReset(): Promise<void> {
    resetUiPrefs()
    try {
      await putPrefs({
        cuisine_weights: tasteToCuisineWeights([]),
        allergies: [],
        spice_tolerance: 1,
        temperature_preference: DEFAULT_UI_PREFS.temperature,
        default_location: address,
        budget_lunch_min: null,
        budget_lunch_max: sliderToBudget(DEFAULT_UI_PREFS.budget),
      })
      toast.push('success', '偏好已重置')
    } catch (err: unknown) {
      toast.push('error', '重置失败,已恢复本地')
    }
  }

  function handleRainy(): void {
    // 仅本地; spec §8 #4 不发后端
    setUiPrefs(RAINY_PRESET)
    toast.push('info', '已套用雨天方案 · 本地生效')
  }

  return (
    <section className={styles.panel} data-od-id="prefs-panel" aria-label="偏好设置">
      <div className={styles.row}>
        <div className={styles.rowHead}>
          <span className={styles.rowTitle}>口味偏好</span>
          <span className={styles.rowHint}>勾选你今天想吃的菜系</span>
        </div>
        <div className={styles.chips} role="group" aria-label="口味">
          {CUISINE_IDS.map((id) => (
            <Chip<CuisineId>
              key={id}
              id={id}
              label={CUISINE_LABELS[id]}
              pressed={uiPrefs.taste.includes(id)}
              onToggle={onTasteToggle}
              variant="taste"
            />
          ))}
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.rowHead}>
          <span className={styles.rowTitle}>温度</span>
          <span className={styles.rowHint}>今天想吃哪种温度</span>
        </div>
        <div className={styles.toggleRow} role="radiogroup" aria-label="温度">
          {TEMPERATURE_OPTIONS.map((opt) => (
            <Toggle
              key={opt.id}
              id={opt.id}
              label={opt.label}
              pressed={uiPrefs.temperature === opt.id}
              onSelect={onTempSelect}
            />
          ))}
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.rowHead}>
          <span className={styles.rowTitle}>心情</span>
          <span className={styles.rowHint}>你现在的状态</span>
        </div>
        <div className={styles.moodRow} role="radiogroup" aria-label="心情">
          {MOOD_OPTIONS.map((opt) => (
            <Mood
              key={opt.id}
              option={opt}
              pressed={uiPrefs.mood === opt.id}
              onSelect={onMoodSelect}
            />
          ))}
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.rowHead}>
          <span className={styles.rowTitle}>距离 / 预算</span>
          <span className={styles.rowHint}>步行分钟数 / 午餐单价</span>
        </div>
        <div className={styles.sliderStack}>
          <Slider
            label="距离"
            value={uiPrefs.distance}
            min={0}
            max={100}
            suffix={` 分 (${sliderToDistanceMin(uiPrefs.distance)})`}
            onChange={onDistanceChange}
            ariaId="slider-distance"
          />
          <Slider
            label="预算"
            value={uiPrefs.budget}
            min={0}
            max={100}
            suffix={` (¥${sliderToBudget(uiPrefs.budget)})`}
            onChange={onBudgetChange}
            ariaId="slider-budget"
          />
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.rowHead}>
          <span className={styles.rowTitle}>忌口</span>
          <span className={styles.rowHint}>勾选你不吃的</span>
        </div>
        <div className={styles.chips} role="group" aria-label="忌口">
          {ALLERGY_VALUES.map((id) => (
            <Chip<AllergyValue>
              key={id}
              id={id}
              label={ALLERGY_LABELS[id]}
              pressed={uiPrefs.allergies.includes(id)}
              onToggle={onAllergyToggle}
              variant="avoid"
            />
          ))}
        </div>
      </div>

      <div className={styles.ctaRow}>
        <span className={styles.ctaCount} data-od-id="prefs-count">
          {totalCount} 项偏好
        </span>
        <div className={styles.ctaActions}>
          <button
            type="button"
            className={styles.ctaSecondary}
            data-od-id="reset-prefs"
            onClick={() => void handleReset()}
          >
            重置默认
          </button>
          <button
            type="button"
            className={styles.ctaSecondary}
            data-od-id="preset-rainy"
            onClick={handleRainy}
          >
            雨天方案
          </button>
          <button
            type="button"
            className={styles.ctaPrimary}
            data-od-id="ask-agent"
            onClick={() => void handleAskAgent()}
            disabled={status === 'streaming'}
          >
            {status === 'streaming' ? '推荐中…' : '问 agent'}
          </button>
        </div>
      </div>
    </section>
  )
}