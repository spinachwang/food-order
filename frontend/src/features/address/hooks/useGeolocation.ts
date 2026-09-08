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
import { regeo } from '../../../lib/api-client'
import type { RegeoInfo } from '../../chat/types'

export type GeolocationStatus = 'idle' | 'loading' | 'success' | 'error'

export interface UseGeolocationResult {
  status: GeolocationStatus
  data: RegeoInfo | null
  error: string | null
  request: () => void
  reset: () => void
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
          const msg = err instanceof Error ? err.message : '逆地理编码失败'
          setError(msg)
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
