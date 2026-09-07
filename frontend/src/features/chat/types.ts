/**
 * F050 — 前端类型层
 *
 * 与后端真实 SSE payload 对齐 (Explore 已校对 backend/app/api/v1/agent.py + 各 TypedDict)。
 * 命名约定: 后端 snake_case 字段在 TypeScript 保持 snake_case (不转 camelCase),
 * 简化前后端契约映射、避免双向转换 bug。
 *
 * 涉及源头:
 * - Recommendation / AltRecommendation → backend/app/agents/summary.py
 * - WeatherInfo / HourlyForecast → backend/app/mcp/amap/weather.py
 * - Restaurant → backend/app/mcp/amap/restaurant.py
 * - CuisineExpertOutput → backend/app/agents/cuisines/base.py
 * - UserPreferences → backend/app/agents/state.py (TypedDict)
 * - SSE 事件帧 → backend/app/api/v1/agent.py:201-234 (_state_payload_for_event)
 */

// =====================================================================
// F003 §3.2 — 14 个菜系 ID 枚举 (SSOT, 后端 CUISINE_REGISTRY)
// =====================================================================

export const CUISINE_IDS = [
  'sichuan',
  'cantonese',
  'shandong',
  'suzhou',
  'zhejiang',
  'fujian',
  'hunan',
  'anhui',
  'japanese',
  'western',
  'western_fastfood',
  'chinese_fastfood',
  'snacks',
  'dessert_drinks',
] as const

export type CuisineId = (typeof CUISINE_IDS)[number]

// =====================================================================
// F001 §3.1 — 过敏原枚举
// =====================================================================

export const ALLERGY_VALUES = [
  'peanut',
  'tree_nut',
  'shellfish',
  'fish',
  'egg',
  'soy',
  'wheat',
  'dairy',
  'sesame',
  'alcohol',
  'fried_food',
] as const

export type AllergyValue = (typeof ALLERGY_VALUES)[number]

// =====================================================================
// F001 §3.4 — 温度偏好 (字符串字面量, 与后端 Literal 对齐)
// =====================================================================

export type TemperaturePreference = 'cold' | 'room' | 'hot'

// =====================================================================
// F001 — UserPreferences (HTTP Pydantic 表面镜像)
// =====================================================================

export interface UserPreferences {
  user_id: string
  cuisine_weights: Record<CuisineId, number>
  allergies: AllergyValue[]
  spice_tolerance: number
  temperature_preference: TemperaturePreference
  default_location: string | null
  budget_lunch_min: number | null
  budget_lunch_max: number | null
}

// =====================================================================
// F003 — CuisineExpertOutput (单菜系专家结论)
// =====================================================================

export interface CuisineExpertOutput {
  cuisine_id: CuisineId
  conclusion: string
  keywords: string[]
  matched_allergies: AllergyValue[]
}

// =====================================================================
// F030 — Restaurant (高德 POI)
// location 字段: 元组 [longitude, latitude] — 注意 lng first, 高德 marker URL 同顺序。
// avg_price: 后端以字符串序列化 Decimal; 前端保留 string 形式, 显示时再解析。
// =====================================================================

export interface Restaurant {
  poi_id: string
  name: string
  address: string
  distance_meters: number
  rating: number | null
  avg_price: string | null
  cuisine_tags: string[]
  location: [number, number]
}

// =====================================================================
// F031 — WeatherInfo
// 字段全部必填; humidity_percent 可能为 0 (extensions=all 时 AMAP 不返回)。
// =====================================================================

export type WeatherCondition = 'sunny' | 'cloudy' | 'rainy' | 'snowy' | 'foggy' | 'dust'

export interface HourlyForecast {
  hour: number
  temperature_celsius: number
  condition: WeatherCondition
  precipitation_probability: number
}

export interface WeatherInfo {
  location: string
  province: string
  city: string
  adcode: string
  temperature_celsius: number
  condition: WeatherCondition
  humidity_percent: number
  wind_direction: string
  wind_level: number
  precipitation_probability: number
  forecast_3h: HourlyForecast[]
  fetched_at: string // ISO datetime (后端 datetime 经 default=str 序列化)
}

// =====================================================================
// F040 — Recommendation / AltRecommendation
// 后端无 Pydantic class, 实际为 dict; 这里给结构化类型便于组件使用。
// confidence 范围 [0, 1]; alternatives 至少 0 个, 后端 _MAX_ALTERNATIVES=2。
// =====================================================================

export interface AltRecommendation {
  cuisine_id: CuisineId
  restaurant_id: string
  restaurant_name: string
  short_reason: string
}

export interface Recommendation {
  headline: string
  cuisine_id: CuisineId
  restaurant_id: string
  restaurant_name: string
  order_takeout: boolean
  reason: string
  confidence: number
  alternatives: AltRecommendation[]
}

/** F040 降级 (无候选) 时 headline 常量。 */
export const DEGRADED_HEADLINE = '今天没合适推荐，换个口味吧'

// =====================================================================
// F004 §4 — SSE 事件 payload (与 agent.py _state_payload_for_event 对齐)
// =====================================================================

/** event: cuisine_selected */
export interface CuisineSelectedEvent {
  cuisines: CuisineId[]
  routing_reason: string
}

/** event: cuisine_result — results 是 dict-keyed by cuisine_id */
export interface CuisineResultEvent {
  results: Partial<Record<CuisineId, CuisineExpertOutput>>
}

/** event: restaurant_found — restaurant_lists 是 dict-keyed by cuisine_id */
export interface RestaurantFoundEvent {
  restaurant_lists: Partial<Record<CuisineId, Restaurant[]>>
}

/** event: weather — null 表示 AMAP 失败 (F031 降级) */
export interface WeatherEvent {
  weather: WeatherInfo | null
}

/** event: recommendation — null 表示 F040 降级到 DEGRADED_HEADLINE */
export interface RecommendationEvent {
  recommendation: Recommendation | null
}

/** event: error */
export interface ErrorEvent {
  code: string
  message: string
}

/** event: done — 空 payload */
export type DoneEvent = Record<string, never>

/** 完整 SSE 事件映射 — lib/sse.ts parse 出 { event, data } 后, 按 event 名称分发。 */
export interface SseEventMap {
  cuisine_selected: CuisineSelectedEvent
  cuisine_result: CuisineResultEvent
  restaurant_found: RestaurantFoundEvent
  weather: WeatherEvent
  recommendation: RecommendationEvent
  error: ErrorEvent
  done: DoneEvent
}

export type SseEventName = keyof SseEventMap
export type SseEventPayload<K extends SseEventName> = SseEventMap[K]

// =====================================================================
// F050 §2.4 — ask-agent 请求体
// =====================================================================

export interface ChatRequest {
  message: string
  session_id?: string | null
  location_override?: string | null
}

// =====================================================================
// F050 §2.3 — ThinkingLog step 结构 (UI 层)
// =====================================================================

export type ThinkingStepStatus = 'pending' | 'done' | 'error'

export interface ThinkingStep {
  /** 1-based marker 编号, 由 useAgentStream 维护递增 */
  marker: number
  /** 主标题 (eg. "已路由到 N 个菜系:xxx / yyy") */
  title: string
  /** 元数据 (eg. "中餐+米饭 · 热乎乎 · 不吃生海鲜") */
  em: string
  status: ThinkingStepStatus
  /** 关联的 cuisine_id (可选, cuisine_result/restaurant_found 步骤用) */
  cuisine_id?: CuisineId
}

// =====================================================================
// F050 §2.4 / §6.x.3 — Preferences (前端 schema 层 — 写到后端前转 cuisine_weights)
// 这里只声明 UI 表单的形状; 真实 PUT /api/v1/preferences 的 zod schema 见 schemas.ts
// =====================================================================

export interface UiPreferences {
  taste: CuisineId[]
  temperature: TemperaturePreference
  mood: string
  distance: number // 0-100 滑杆
  budget: number // 0-100 滑杆 (→ ¥20-¥80)
  allergies: AllergyValue[]
}

export const DEFAULT_UI_PREFS: UiPreferences = {
  taste: [],
  temperature: 'hot',
  mood: 'want-better', // 想吃好点 (F050 §2.4 reset-prefs 默认)
  distance: 35,
  budget: 55,
  allergies: [],
}

export const RAINY_PRESET: Partial<UiPreferences> = {
  temperature: 'hot',
  mood: 'want-comfort', // 想治愈
  distance: 25,
}