/**
 * F051 §5.1 — `useDistrictList` hook.
 *
 * 包装 `/api/v1/districts` 给 AddressPickerDialog 级联下拉用.
 *
 * 设计要点 (per spec §5.4):
 * - `keywords` 缺省 → enabled=false, 不发请求 (顶层国家级列表走 cn-cities 硬编码)
 * - 命中后 24h staleTime, 模拟后端 Redis 24h 缓存策略 (M2 接入 Redis 前先在
 *   客户端兜底, 避免重复往返)
 * - queryKey 含 keywords + subdistrict, 切换父级时不互相干扰
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import {
  ApiError,
  getDistricts,
} from '../../../lib/api-client'
import type { DistrictInfo } from '../../chat/types'

const STALE_TIME_24H = 24 * 60 * 60 * 1000

export interface UseDistrictListParams {
  keywords?: string
  subdistrict?: 0 | 1 | 2 | 3
}

export function useDistrictList(
  params: UseDistrictListParams,
): UseQueryResult<DistrictInfo[], ApiError> {
  const enabled = typeof params.keywords === 'string'
  return useQuery<DistrictInfo[], ApiError>({
    queryKey: ['districts', params.keywords, params.subdistrict],
    queryFn: () => getDistricts(params),
    enabled,
    staleTime: STALE_TIME_24H,
  })
}
