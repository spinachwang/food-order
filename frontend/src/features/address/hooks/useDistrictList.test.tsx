/**
 * F051 §5.4 — `useDistrictList` hook 测试.
 *
 * 覆盖:
 * - keywords 缺省时不发请求 (enabled=false)
 * - keywords 有值时调 getDistricts, 传递 subdistrict
 * - 24h staleTime 配置 (per spec §5.4 Redis 缓存等效策略)
 * - queryKey 包含 keywords + subdistrict (避免错配)
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as apiClient from '../../../lib/api-client'
import { useDistrictList } from './useDistrictList'

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms))

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useDistrictList', () => {
  it('keywords 缺省时 enabled=false 不发请求', () => {
    const spy = vi.spyOn(apiClient, 'getDistricts')
    const { result } = renderHook(() => useDistrictList({}), { wrapper: makeWrapper() })
    expect(result.current.fetchStatus).toBe('idle')
    expect(spy).not.toHaveBeenCalled()
  })

  it('keywords 存在时调用 getDistricts 并传递 subdistrict', async () => {
    const spy = vi
      .spyOn(apiClient, 'getDistricts')
      .mockResolvedValue([
        {
          adcode: '310000',
          name: '上海市',
          level: 'province',
          center: [121.47, 31.23],
          districts: [],
        },
      ])
    const { result } = renderHook(
      () => useDistrictList({ keywords: '上海', subdistrict: 1 }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith({ keywords: '上海', subdistrict: 1 })
    expect(result.current.data).toEqual([
      expect.objectContaining({ adcode: '310000', name: '上海市' }),
    ])
  })

  it('queryKey 包含 keywords + subdistrict', async () => {
    vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([])
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(
      () => useDistrictList({ keywords: '北京', subdistrict: 2 }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const cacheKeys = qc
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey)
    expect(cacheKeys).toContainEqual(['districts', '北京', 2])
  })

  it('staleTime 配置为 24 小时 — 同一 queryKey 二次渲染不重复请求', async () => {
    const spy = vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([])
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { rerender } = renderHook(
      ({ k }: { k: string }) => useDistrictList({ keywords: k }),
      { wrapper, initialProps: { k: '上海' } },
    )
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    // 24h staleTime 期间内重新渲染同 queryKey 不应再发请求
    rerender({ k: '上海' })
    await sleep(100)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('失败时暴露 error 对象', async () => {
    vi.spyOn(apiClient, 'getDistricts').mockRejectedValue(
      new apiClient.ApiError('AMAP_QUOTA_EXCEEDED', 'quota', 429),
    )
    const { result } = renderHook(
      () => useDistrictList({ keywords: '上海' }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(apiClient.ApiError)
    expect((result.current.error as apiClient.ApiError).code).toBe(
      'AMAP_QUOTA_EXCEEDED',
    )
  })
})
