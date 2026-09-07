/**
 * F050 — Chat 端到端流 (集成测试)
 *
 * 模拟完整 SSE 事件序列, 验证 UI 状态机:
 *   hero 静态 → thinking 步骤追加 → reco-main 渲染 → reco-alt 出现 →
 *   status 由 streaming → done.
 *
 * 走 ChatShell 顶层 (mock PreferencesPanel 避免 TanStack Query 触发).
 */
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatShell } from './ChatShell'
import { useChatStore, DEFAULT_UI_PREFS } from '../../stores/chatStore'
import type {
  AltRecommendation,
  CuisineExpertOutput,
  CuisineId,
  Recommendation,
  Restaurant,
  WeatherInfo,
} from './types'

vi.mock('./components/PreferencesPanel', () => ({
  PreferencesPanel: () => <div data-od-id="prefs-panel" />,
}))

// Mock useAgentStream — 暴露一个注入器让我们手动 dispatch SSE 帧
const dispatch = vi.fn()
vi.mock('./hooks/useAgentStream', () => ({
  useAgentStream: () => ({
    start: vi.fn().mockImplementation(async (req: { message?: string }) => {
      dispatch({ type: 'start', req })
    }),
    cancel: vi.fn(),
    status: useChatStore.getState().status,
  }),
}))

const CUISINE_RESULT: Partial<Record<CuisineId, CuisineExpertOutput>> = {
  sichuan: {
    cuisine_id: 'sichuan',
    conclusion: '川菜适合今天吃',
    keywords: ['麻辣', '暖身'],
    matched_allergies: [],
  },
}

const R: Restaurant = {
  poi_id: 'poi-001',
  name: '蜀香坊',
  address: '国贸路 88 号',
  distance_meters: 420,
  rating: 4.6,
  avg_price: '48',
  cuisine_tags: ['川菜'],
  location: [116.46, 39.92],
}

const ALT: AltRecommendation = {
  cuisine_id: 'japanese',
  restaurant_id: 'poi-002',
  restaurant_name: '和风亭',
  short_reason: '清淡',
}

const RECO: Recommendation = {
  headline: '暖身又下饭,送上门刚好',
  cuisine_id: 'sichuan',
  restaurant_id: 'poi-001',
  restaurant_name: '蜀香坊',
  order_takeout: true,
  reason: '麻婆豆腐暖身,辣度刚好,15 分钟送达',
  confidence: 0.92,
  alternatives: [ALT],
}

const W: WeatherInfo = {
  location: '北京',
  province: '北京市',
  city: '北京',
  adcode: '110000',
  temperature_celsius: 28,
  condition: 'cloudy',
  humidity_percent: 60,
  wind_direction: '东南',
  wind_level: 3,
  precipitation_probability: 0.2,
  forecast_3h: [],
  fetched_at: '2026-09-06T10:00:00Z',
}

/** 直接调 chatStore 的 setter 模拟 useAgentStream dispatchFrame */
function emitCuisineSelected(): void {
  useChatStore.getState().setSelectedCuisines(['sichuan'], '中餐偏好')
  useChatStore.getState().appendThinking({
    title: '已路由到 1 个菜系: sichuan',
    em: '中餐偏好',
    status: 'done',
  })
}
function emitCuisineResult(): void {
  useChatStore.getState().setCuisineResults(CUISINE_RESULT)
}
function emitRestaurantsFound(): void {
  useChatStore.getState().setRestaurantLists({ sichuan: [R] })
}
function emitWeather(): void {
  useChatStore.getState().setWeather(W)
}
function emitRecommendation(): void {
  useChatStore.getState().setRecommendation(RECO)
}
function emitDone(): void {
  useChatStore.getState().markLastThinkingDone()
  useChatStore.getState().setStatus('done')
}

beforeEach(() => {
  useChatStore.setState({
    status: 'idle',
    selectedCuisines: [],
    routingReason: '',
    cuisineResultsByCuisine: {},
    restaurantListsByCuisine: {},
    weather: null,
    recommendation: null,
    thinking: [],
    error: null,
    uiPrefs: { ...DEFAULT_UI_PREFS },
    address: '上海 · 静安嘉里中心',
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ChatShell — 端到端流', () => {
  it('初始: 空 thinking + reco-main-empty 占位', () => {
    const { container } = render(<ChatShell />)
    expect(container.querySelector('[data-od-id="reco-main-empty"]')).toBeInTheDocument()
    expect(container.textContent).toContain('点')
    expect(container.textContent).toContain('问 agent')
    expect(container.textContent).toContain('开始追踪')
  })

  it('逐步 emit SSE → status 由 idle → streaming → done', async () => {
    useChatStore.setState({ status: 'streaming' })
    const { container } = render(<ChatShell />)
    // initial streaming
    expect(container.textContent).toContain('agent 思考中')

    // event 1: cuisine_selected
    emitCuisineSelected()
    expect(useChatStore.getState().selectedCuisines).toEqual(['sichuan'])
    expect(useChatStore.getState().thinking.some((s) => s.title.includes('已路由到'))).toBe(true)

    // event 2: cuisine_result
    emitCuisineResult()
    expect(useChatStore.getState().cuisineResultsByCuisine.sichuan?.conclusion).toBe(
      '川菜适合今天吃',
    )

    // event 3: restaurant_found
    emitRestaurantsFound()
    expect(useChatStore.getState().restaurantListsByCuisine.sichuan?.[0]?.name).toBe('蜀香坊')

    // event 4: weather
    emitWeather()
    expect(useChatStore.getState().weather?.temperature_celsius).toBe(28)

    // event 5: recommendation → main + alt 渲染
    emitRecommendation()
    await waitFor(() => {
      expect(container.querySelector('[data-od-id="reco-main"]')).toBeInTheDocument()
    })
    expect(container.querySelector('[data-od-id="reco-alt"]')).toBeInTheDocument()
    expect(container.querySelector('[data-od-id="alt-1"]')).toBeInTheDocument()

    // event 6: done
    emitDone()
    await waitFor(() => {
      expect(useChatStore.getState().status).toBe('done')
    })
  })

  it('SSE error 事件 → status=error + 推荐区降级', async () => {
    useChatStore.setState({ status: 'streaming' })
    const { container } = render(<ChatShell />)
    expect(container.textContent).toContain('agent 思考中')
    act(() => {
      useChatStore.getState().setError('agent 挂了')
      useChatStore.getState().setStatus('error')
    })
    await waitFor(() => {
      expect(container.textContent).toContain('agent 出错')
    })
    // 空状态占位
    expect(container.querySelector('[data-od-id="reco-main-empty"]')).toBeInTheDocument()
  })
})