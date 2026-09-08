/**
 * F051 §4.2 — `usePlaceSearch` hook.
 *
 * 包装 `/api/v1/places/search`, 用于 AddressPickerDialog 的『商圈 / 小区』
 * 关键字搜索.
 *
 * 设计要点 (per spec §4.2):
 * - 300ms debounce: 用户连打字时只发最后一次请求
 * - keywords 为空字符串 / 仅空白时 enabled=false
 * - staleTime = 0: 搜索结果每次都重新拉, 用户切换关键词要立刻看到新结果
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  searchPlaces,
} from '../../../lib/api-client'
import type { PlaceSearchResult } from '../../chat/types'

const DEBOUNCE_MS = 300

export interface UsePlaceSearchParams {
  keywords: string
  city?: string
  types?: string
  offset?: number
}

export function usePlaceSearch(
  params: UsePlaceSearchParams,
): UseQueryResult<PlaceSearchResult, ApiError> {
  const debouncedKeywords = useDebouncedValue(params.keywords, DEBOUNCE_MS)
  const enabled = debouncedKeywords.trim().length > 0

  const memoParams = useMemo(
    () => ({
      keywords: debouncedKeywords,
      city: params.city,
      types: params.types,
      offset: params.offset,
    }),
    [debouncedKeywords, params.city, params.types, params.offset],
  )

  return useQuery<PlaceSearchResult, ApiError>({
    queryKey: ['places', memoParams],
    queryFn: () => searchPlaces(memoParams),
    enabled,
    staleTime: 0,
  })
}

/** 简化的 debounce — useEffect + setTimeout. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
