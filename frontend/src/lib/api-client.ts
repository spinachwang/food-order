/**
 * F050 / F051 — REST API 客户端
 *
 * 端点:
 * - GET    /api/v1/preferences
 * - PUT    /api/v1/preferences
 * - GET    /api/v1/districts              (F051 §5.1)
 * - GET    /api/v1/places/search          (F051 §5.3)
 * - GET    /api/v1/geocode/regeo          (F051 §5.2)
 * - POST   /api/v1/agent/chat             (SSE, 不走 envelope; 由 useAgentStream 单独处理)
 *
 * 后端 envelope 格式 (见 backend/app/schemas/envelope.py):
 *   成功: { ok: true, data: T }
 *   失败: { ok: false, error: { code, message, details? } }
 *
 * 行为约定:
 * - 始终带 credentials: 'include' 让 x_user_id cookie 透传
 * - 不主动注入 X-User-Id header (cookie 优先; middleware 见 core/user_id.py)
 * - 非 2xx + 解析失败 envelope → 抛 ApiError
 */
import type {
  DistrictInfo,
  PlaceSearchResult,
  RegeoInfo,
  StructuredAddress,
  UserPreferences,
} from '../features/chat/types'

export class ApiError extends Error {
  public readonly code: string
  public readonly status: number
  public readonly details: unknown

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

interface EnvelopeOk<T> {
  ok: true
  data: T
}
interface EnvelopeErr {
  ok: false
  error: {
    code: string
    message: string
    details?: unknown
  }
}
type Envelope<T> = EnvelopeOk<T> | EnvelopeErr

/** 内部 fetch helper — 所有 api 方法都走它 */
async function request<T>(
  method: 'GET' | 'PUT' | 'POST',
  path: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
  }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }
  const res = await fetch(path, init)

  // 204 No Content 等无 body
  const text = await res.text()
  let envelope: Envelope<T> | null = null
  if (text) {
    try {
      envelope = JSON.parse(text) as Envelope<T>
    } catch {
      // 非 JSON 响应, 让上层按 HTTP status 处理
    }
  }

  if (!res.ok) {
    if (envelope && !envelope.ok) {
      throw new ApiError(
        envelope.error.code,
        envelope.error.message,
        res.status,
        envelope.error.details,
      )
    }
    throw new ApiError(
      'HTTP_ERROR',
      `${res.status} ${res.statusText || ''}`.trim(),
      res.status,
    )
  }

  if (envelope && envelope.ok) {
    return envelope.data
  }
  // 2xx 但 envelope 形状错
  throw new ApiError('BAD_ENVELOPE', '响应缺少 ok/data 字段', res.status)
}

// ---- 公开 API ----

export interface PreferencesUpdateBody {
  cuisine_weights: Record<string, number>
  allergies: string[]
  spice_tolerance: number
  temperature_preference: 'cold' | 'room' | 'hot'
  /** F051: StructuredAddress | null — 旧 string 字段已被后端 GET 时归一化为 null. */
  default_location: StructuredAddress | null
  budget_lunch_min: number | null
  budget_lunch_max: number | null
}

export function getPreferences(): Promise<UserPreferences> {
  return request<UserPreferences>('GET', '/api/v1/preferences')
}

export function putPreferences(
  body: PreferencesUpdateBody,
): Promise<UserPreferences> {
  return request<UserPreferences>('PUT', '/api/v1/preferences', body)
}

// =====================================================================
// F051 §5 — AddressPickerDialog 使用的三个高德 MCP proxy
// =====================================================================

/** F051 §5.1 — `/config/district` 行政区划级联.
 *  `keywords` 缺省 → 国家级根（中国 → 34 个省级单位）；`subdistrict` ∈ [0, 3]. */
export function getDistricts(params: {
  keywords?: string
  subdistrict?: 0 | 1 | 2 | 3
}): Promise<DistrictInfo[]> {
  const search = new URLSearchParams()
  if (params.keywords !== undefined) {
    search.set('keywords', params.keywords)
  }
  if (params.subdistrict !== undefined) {
    search.set('subdistrict', String(params.subdistrict))
  }
  const qs = search.toString()
  return request<DistrictInfo[]>(
    'GET',
    `/api/v1/districts${qs ? `?${qs}` : ''}`,
  )
}

/** F051 §5.3 — `place/text` POI 关键字搜索.
 *  `keywords` 必填；`city` 限定时后端自动加 citylimit=true. */
export function searchPlaces(params: {
  keywords: string
  city?: string
  types?: string
  offset?: number
}): Promise<PlaceSearchResult> {
  const search = new URLSearchParams()
  search.set('keywords', params.keywords)
  if (params.city !== undefined) {
    search.set('city', params.city)
  }
  if (params.types !== undefined) {
    search.set('types', params.types)
  }
  if (params.offset !== undefined) {
    search.set('offset', String(params.offset))
  }
  return request<PlaceSearchResult>(
    'GET',
    `/api/v1/places/search?${search.toString()}`,
  )
}

/** F051 §5.2 — `/geocode/regeo` 经纬度 → 行政区划文本 + adcode.
 *  `location` 格式: "lng,lat". */
export function regeo(location: string): Promise<RegeoInfo> {
  const search = new URLSearchParams()
  search.set('location', location)
  return request<RegeoInfo>('GET', `/api/v1/geocode/regeo?${search.toString()}`)
}