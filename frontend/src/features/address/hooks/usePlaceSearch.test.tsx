/**
 * F051 §5.4 — `usePlaceSearch` hook 测试.
 *
 * 覆盖:
 * - keywords 为空字符串时 enabled=false
 * - 300ms debounce: 短时间连发只触发最后一次
 * - 调用 searchPlaces 透传 city + types + offset
 *
 * 注: 用真实定时器 (不 mock setTimeout) — react-query 的 fetch resolve
 * 与 setTimeout 共存于同一微任务队列, mock 会导致 race.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as apiClient from '../../../lib/api-client'
import { usePlaceSearch } from './usePlaceSearch'

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms))

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePlaceSearch', () => {
  it('keywords 为空字符串时 enabled=false', async () => {
    const spy = vi.spyOn(apiClient, 'searchPlaces').mockResolvedValue({
      pois: [],
      count: 0,
    })
    const { result } = renderHook(
      () => usePlaceSearch({ keywords: '', city: '310100' }),
      { wrapper: makeWrapper() },
    )
    await sleep(50)
    expect(result.current.fetchStatus).toBe('idle')
    expect(spy).not.toHaveBeenCalled()
  })

  it('300ms debounce: 连续变更 keywords 只触发最后一次', async () => {
    const spy = vi.spyOn(apiClient, 'searchPlaces').mockResolvedValue({
      pois: [],
      count: 0,
    })
    const { rerender } = renderHook(
      ({ kw }: { kw: string }) =>
        usePlaceSearch({ keywords: kw, city: '310100' }),
      { wrapper: makeWrapper(), initialProps: { kw: '' } },
    )

    // 初始为空 — 不发请求
    expect(spy).not.toHaveBeenCalled()

    // 改成 '静' → 等 300+ms
    rerender({ kw: '静' })
    await sleep(400)
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenLastCalledWith({ keywords: '静', city: '310100' })

    // 立即 (50ms 内) 再改成 '静安' → debounce 重置, 不应新发
    rerender({ kw: '静安' })
    await sleep(50)
    expect(spy).toHaveBeenCalledTimes(1)

    // 再等 300ms (累计 350ms 自 '静安') → 应该触发新一次
    await sleep(350)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenLastCalledWith({ keywords: '静安', city: '310100' })
  })

  it('透传 city + types + offset 到 searchPlaces', async () => {
    const spy = vi.spyOn(apiClient, 'searchPlaces').mockResolvedValue({
      pois: [
        {
          poi_id: 'B0FFFAB6J2ABCDEFGHIJ',
          name: '静安嘉里中心',
          address: '南京西路',
          type: '商务住宅',
          location: [121.45, 31.23],
        },
      ],
      count: 1,
    })
    const { result } = renderHook(
      () =>
        usePlaceSearch({
          keywords: '静安',
          city: '310100',
          types: '商圈',
          offset: 5,
        }),
      { wrapper: makeWrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith({
      keywords: '静安',
      city: '310100',
      types: '商圈',
      offset: 5,
    })
  })
})
