/**
 * F051 §4.3 — `useGeolocation` hook 测试.
 *
 * 覆盖:
 * - 初始 idle 状态
 * - getCurrentPosition success → regeo(location) → 返回 RegeoInfo
 * - getCurrentPosition error → 返回 Error
 * - retry() 重新触发
 * - navigator.geolocation 不可用时返回 Error
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as apiClient from '../../../lib/api-client'
import type { RegeoInfo } from '../../chat/types'
import { useGeolocation } from './useGeolocation'

const sampleRegeo: RegeoInfo = {
  province: '上海市',
  city: '上海市',
  district: '静安区',
  adcode: '310106',
  formatted_address: '上海市静安区南京西路xxx号',
  longitude: 121.473701,
  latitude: 31.230416,
}

interface MockPosition {
  coords: { longitude: number; latitude: number; accuracy: number }
  timestamp: number
}

function mockGeolocationSuccess(pos: MockPosition) {
  const geo = {
    getCurrentPosition: vi.fn((success: PositionCallback) => {
      success(pos as unknown as GeolocationPosition)
    }),
  }
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: geo,
    configurable: true,
  })
}

function mockGeolocationError(message: string) {
  const geo = {
    getCurrentPosition: vi.fn((_s: PositionCallback, err?: PositionErrorCallback) => {
      err?.({ message, code: 1 } as unknown as GeolocationPositionError)
    }),
  }
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: geo,
    configurable: true,
  })
}

function removeGeolocation() {
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: undefined,
    configurable: true,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useGeolocation', () => {
  it('初始 idle 状态', () => {
    removeGeolocation()
    const { result } = renderHook(() => useGeolocation())
    expect(result.current.status).toBe('idle')
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('navigator.geolocation 不可用时 status=error', async () => {
    removeGeolocation()
    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toMatch(/不支持/)
  })

  it('getCurrentPosition 成功 + regeo 返回 data', async () => {
    mockGeolocationSuccess({
      coords: { longitude: 121.473701, latitude: 31.230416, accuracy: 10 },
      timestamp: Date.now(),
    })
    const regeoSpy = vi
      .spyOn(apiClient, 'regeo')
      .mockResolvedValue(sampleRegeo)

    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())

    await waitFor(() => expect(result.current.status).toBe('success'))
    expect(result.current.data).toEqual(sampleRegeo)
    expect(regeoSpy).toHaveBeenCalledWith('121.473701,31.230416')
  })

  it('getCurrentPosition 失败时 status=error + message 透传', async () => {
    mockGeolocationError('User denied geolocation')
    vi.spyOn(apiClient, 'regeo').mockResolvedValue(sampleRegeo)
    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toMatch(/User denied/)
  })

  it('regeo 失败时 status=error + ApiError', async () => {
    mockGeolocationSuccess({
      coords: { longitude: 121.473701, latitude: 31.230416, accuracy: 10 },
      timestamp: Date.now(),
    })
    vi.spyOn(apiClient, 'regeo').mockRejectedValue(
      new apiClient.ApiError('AMAP_LOCATION_INVALID', '海上无数据', 502),
    )
    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toMatch(/海上无数据/)
  })

  it('retry() 重置后再次 request', async () => {
    mockGeolocationSuccess({
      coords: { longitude: 121.47, latitude: 31.23, accuracy: 10 },
      timestamp: Date.now(),
    })
    vi.spyOn(apiClient, 'regeo').mockResolvedValue(sampleRegeo)
    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())
    await waitFor(() => expect(result.current.status).toBe('success'))
    expect(result.current.data).not.toBeNull()
  })
})
