/**
 * F050 — REST API 客户端
 *
 * 三个端点:
 * - GET    /api/v1/preferences
 * - PUT    /api/v1/preferences
 * - POST   /api/v1/agent/chat  (SSE, 不走 envelope; 由 useAgentStream 单独处理)
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
import type { UserPreferences } from '../features/chat/types'

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
  default_location: string | null
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