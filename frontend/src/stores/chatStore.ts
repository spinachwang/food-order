/**
 * F050 — Chat 业务 store (Zustand)
 *
 * 持有 SSE 流产出 + 本地 UI 状态。useAgentStream 在收到 SSE 事件时调用
 * 这里的 setter; 组件层 useChatStore(selector) 订阅切片。
 *
 * 设计要点:
 * - 不持久化 (sessionStorage 也不存; spec §8 #8 心情 / §8 #4 preset-rainy 仅本地)
 * - status 字段统一表达流式状态机
 * - thinking 步骤由 useAgentStream 维护递增 marker
 */
import { create } from 'zustand'
import type {
  AltRecommendation,
  CuisineExpertOutput,
  CuisineId,
  Recommendation,
  Restaurant,
  ThinkingStep,
  UiPreferences,
  WeatherInfo,
} from '../features/chat/types'
import { DEFAULT_UI_PREFS } from '../features/chat/types'

export { DEFAULT_UI_PREFS }
export type { UiPreferences }

export type ChatStatus = 'idle' | 'streaming' | 'done' | 'error'

interface ChatStore {
  // SSE 流状态
  status: ChatStatus
  selectedCuisines: CuisineId[]
  routingReason: string
  cuisineResultsByCuisine: Partial<Record<CuisineId, CuisineExpertOutput>>
  restaurantListsByCuisine: Partial<Record<CuisineId, Restaurant[]>>
  weather: WeatherInfo | null
  recommendation: Recommendation | null
  thinking: ThinkingStep[]
  error: string | null

  // 用户会话级 prefs (本地; 由 useAgentStream 在 ask-agent 时透传给后端)
  uiPrefs: UiPreferences
  address: string
  locationOverride: string | null
  sessionId: string | null

  // 推荐辅助: 上次被 promote 的 alt 列表, 用于 ThinkingLog / 历史回看
  // (M1 不持久化, 仅当次会话有效)

  // actions
  setStatus: (s: ChatStatus) => void
  setSelectedCuisines: (cuisines: CuisineId[], reason: string) => void
  setCuisineResults: (results: Partial<Record<CuisineId, CuisineExpertOutput>>) => void
  setRestaurantLists: (lists: Partial<Record<CuisineId, Restaurant[]>>) => void
  setWeather: (w: WeatherInfo | null) => void
  setRecommendation: (r: Recommendation | null) => void
  appendThinking: (step: Omit<ThinkingStep, 'marker'>) => void
  setThinking: (steps: ThinkingStep[]) => void
  markLastThinkingDone: () => void
  markLastThinkingError: () => void
  setError: (e: string | null) => void
  promoteAlternative: (alt: AltRecommendation) => void
  reset: () => void

  // UI prefs
  setUiPrefs: (patch: Partial<UiPreferences>) => void
  resetUiPrefs: () => void

  // session / location
  setAddress: (a: string) => void
  setLocationOverride: (loc: string | null) => void
  setSessionId: (id: string | null) => void
}

export const DEFAULT_ADDRESS = '上海 · 静安嘉里中心 B2'
let stepCounter = 0
const nextMarker = () => ++stepCounter

export const useChatStore = create<ChatStore>((set) => ({
  status: 'idle',
  selectedCuisines: [],
  routingReason: '',
  cuisineResultsByCuisine: {},
  restaurantListsByCuisine: {},
  weather: null,
  recommendation: null,
  thinking: [],
  error: null,

  uiPrefs: DEFAULT_UI_PREFS,
  address: DEFAULT_ADDRESS,
  locationOverride: null,
  sessionId: null,

  setStatus: (s) => set({ status: s }),
  setSelectedCuisines: (cuisines, reason) =>
    set({ selectedCuisines: cuisines, routingReason: reason }),
  setCuisineResults: (results) => set({ cuisineResultsByCuisine: results }),
  setRestaurantLists: (lists) => set({ restaurantListsByCuisine: lists }),
  setWeather: (w) => set({ weather: w }),
  setRecommendation: (r) => set({ recommendation: r }),
  appendThinking: (step) =>
    set((state) => ({
      thinking: [
        ...state.thinking,
        { ...step, marker: nextMarker(), status: step.status ?? 'pending' },
      ],
    })),
  setThinking: (steps) => set({ thinking: steps }),
  markLastThinkingDone: () =>
    set((state) => {
      if (state.thinking.length === 0) return state
      const next = state.thinking.slice()
      const last = next[next.length - 1]!
      // 不覆盖已有的 error 状态 (done 帧只是流结束信号, 不修复失败步骤)
      if (last.status === 'error') return state
      next[next.length - 1] = { ...last, status: 'done' }
      return { thinking: next }
    }),
  markLastThinkingError: () =>
    set((state) => {
      if (state.thinking.length === 0) return state
      const next = state.thinking.slice()
      next[next.length - 1] = { ...next[next.length - 1]!, status: 'error' }
      return { thinking: next }
    }),
  setError: (e) => set({ error: e }),

  promoteAlternative: (alt) =>
    set((state) => {
      const current = state.recommendation
      if (!current) return state
      const pool = current.alternatives.filter((a) => a.restaurant_id !== alt.restaurant_id)
      const newMain: Recommendation = {
        headline: alt.restaurant_name,
        cuisine_id: alt.cuisine_id,
        restaurant_id: alt.restaurant_id,
        restaurant_name: alt.restaurant_name,
        // 决策矩阵相关字段: promote 时保留原值 (order_takeout / confidence 同方向)
        order_takeout: current.order_takeout,
        reason: alt.short_reason,
        confidence: current.confidence,
        alternatives: pool,
      }
      return { recommendation: newMain }
    }),

  reset: () =>
    set({
      status: 'idle',
      selectedCuisines: [],
      routingReason: '',
      cuisineResultsByCuisine: {},
      restaurantListsByCuisine: {},
      weather: null,
      recommendation: null,
      thinking: [],
      error: null,
    }),

  setUiPrefs: (patch) =>
    set((state) => ({ uiPrefs: { ...state.uiPrefs, ...patch } })),
  resetUiPrefs: () => set({ uiPrefs: DEFAULT_UI_PREFS }),

  setAddress: (a) => set({ address: a }),
  setLocationOverride: (loc) => set({ locationOverride: loc }),
  setSessionId: (id) => set({ sessionId: id }),
}))

// 让 marker 在 reset 时也重置 (避免跨会话累积)
export function resetChatStepCounter(): void {
  stepCounter = 0
}