/**
 * F050 — usePreferences hook
 *
 * TanStack Query 包装 GET /api/v1/preferences + PUT mutation.
 *
 * - query: GET, staleTime 5 分钟 (cookie x_user_id 短期稳定)
 * - mutation: PUT, zod 校验前端 schema 后再发; 成功后 invalidate query
 * - 校验失败: 抛 zod issues 给上层 catch, 由 Phase C Toaster 提示
 *
 * 注: 这里的 PUT body 字段名对齐 backend/app/schemas/preferences.py (snake_case),
 * 校验 schema 见 features/chat/schemas.ts (UserPreferencesUpdate)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ApiError,
  type PreferencesUpdateBody,
  getPreferences,
  putPreferences,
} from '../../../lib/api-client'
import {
  userPreferencesUpdateSchema,
  type UserPreferencesUpdate,
} from '../schemas'
import type { UserPreferences } from '../types'

const QUERY_KEY = ['preferences'] as const

export function usePreferencesQuery() {
  return useQuery<UserPreferences, ApiError>({
    queryKey: QUERY_KEY,
    queryFn: getPreferences,
    staleTime: 5 * 60 * 1000,
  })
}

export interface PutPreferencesInput extends UserPreferencesUpdate {}

/**
 * PUT preferences — 前端 zod 校验 → api-client PUT → invalidate query.
 * 校验失败抛 z.ZodError; 网络 / 4xx 抛 ApiError. 调用方负责 toast.
 */
export function usePutPreferences() {
  const qc = useQueryClient()
  return useMutation<UserPreferences, Error, PutPreferencesInput>({
    mutationFn: async (input) => {
      const parsed = userPreferencesUpdateSchema.parse(input)
      const body: PreferencesUpdateBody = {
        cuisine_weights: parsed.cuisine_weights,
        allergies: parsed.allergies,
        spice_tolerance: parsed.spice_tolerance,
        temperature_preference: parsed.temperature_preference,
        default_location: parsed.default_location,
        budget_lunch_min: parsed.budget_lunch_min,
        budget_lunch_max: parsed.budget_lunch_max,
      }
      return putPreferences(body)
    },
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
    },
  })
}