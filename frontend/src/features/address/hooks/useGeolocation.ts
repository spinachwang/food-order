/**
 * F051 §4.3 — `useGeolocation` hook.
 *
 * 流程:
 *   navigator.geolocation.getCurrentPosition() →
 *     { longitude, latitude } →
 *       regeo(location) → RegeoInfo (含 province / city / district / adcode)
 *
 * 状态机: idle → loading → success | error
 *
 * 调用方 (AddressPickerDialog) 在用户点『📍 使用当前位置』按钮时
 * 调 `request()`, 在 success 时把 RegeoInfo 折成 StructuredAddress 字段.
 */
import { useCallback, useState } from 'react'
import { ApiError, regeo } from '../../../lib/api-client'
import type { RegeoInfo } from '../../chat/types'

export type GeolocationStatus = 'idle' | 'loading' | 'success' | 'error'

export interface UseGeolocationResult {
  status: GeolocationStatus
  data: RegeoInfo | null
  error: string | null
  request: () => void
  reset: () => void
}

/**
 * 把 ApiError 转成对用户友好的中文短句。F051 §2.4 / §7：
 * - `AMAP_LOCATION_INVALID` (HTTP 422) → 「无法识别当前位置，请手动选择」
 * - `AMAP_QUOTA_EXCEEDED` (HTTP 429) → 「服务繁忙，请稍后再试」
 * - `AMAP_INVALID_KEY` / `AMAP_NETWORK_ERROR` → 「定位服务暂不可用」
 * - 其它：保留原 message。
 */
function friendlyMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'AMAP_LOCATION_INVALID':
        return '无法识别当前位置，请手动选择'
      case 'AMAP_QUOTA_EXCEEDED':
        return '服务繁忙，请稍后再试'
      case 'AMAP_INVALID_KEY':
      case 'AMAP_NETWORK_ERROR':
        return '定位服务暂不可用'
      default:
        return err.message
    }
  }
  return err instanceof Error ? err.message : '逆地理编码失败'
}

export function useGeolocation(): UseGeolocationResult {
  const [status, setStatus] = useState<GeolocationStatus>('idle')
  const [data, setData] = useState<RegeoInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const request = useCallback((): void => {
    setStatus('loading')
    setError(null)

    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setStatus('error')
      setError('当前浏览器不支持定位')
      return
    }

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { longitude, latitude } = pos.coords
        try {
          const info = await regeo(`${longitude},${latitude}`)
          setData(info)
          setStatus('success')
        } catch (err: unknown) {
          setError(friendlyMessage(err))
          setStatus('error')
        }
      },
      (err) => {
        setError(err.message || '定位失败')
        setStatus('error')
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }, [])

  const reset = useCallback((): void => {
    setStatus('idle')
    setData(null)
    setError(null)
  }, [])

  return { status, data, error, request, reset }
}
