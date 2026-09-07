/**
 * F050 — 前端 zod schema 层
 *
 * 用途: 在 PUT /api/v1/preferences 之前本地校验, 避免发 400 (F001 §6 错误码)。
 * 与 backend/app/schemas/preferences.py 保持形状一致; 字段名小写 snake_case。
 *
 * 注意: cuisine_weights 在 UI 层是 chip 二元选择, 转 API 前会展开为
 * { [cuisine_id]: 选中?1.0:0.0 } — 见 usePreferences.toApiPayload。
 */
import { z } from 'zod'
import {
  ALLERGY_VALUES,
  CUISINE_IDS,
  type CuisineId,
} from './types'

// =====================================================================
// 枚举 schema (与 F001 §3.1 / §3.4 / F003 §3.2 对齐)
// =====================================================================

export const cuisineIdSchema = z.enum(CUISINE_IDS) as z.ZodType<CuisineId>

export const allergySchema = z.enum(ALLERGY_VALUES)

export const temperatureSchema = z.enum(['cold', 'room', 'hot'])

// =====================================================================
// F001 §3 — UserPreferences 字段
// =====================================================================

/** cuisine_weights: 14 keys (F003), 每个值 ∈ [0, 1] */
const cuisineWeightsSchema = z
  .record(cuisineIdSchema, z.number().min(0).max(1))
  .refine(
    (weights) => {
      // 校验 14 个 key 都存在 (缺失视为中性 0.5, 由后端默认填; 前端要完整上传)
      return CUISINE_IDS.every((id) => id in weights)
    },
    { message: 'cuisine_weights must contain all 14 cuisine IDs' },
  )

/** allergies: 0-N, 去重 */
const allergiesSchema = z.array(allergySchema).max(ALLERGY_VALUES.length)

/** spice_tolerance ∈ [0, 3] (F001 §3.2) */
const spiceToleranceSchema = z.number().int().min(0).max(3)

/** default_location: string | null */
const defaultLocationSchema = z.string().min(1).max(200).nullable()

/** budget: Decimal | null, 上限必须 ≥ 下限 (F001 §6 INVALID_BUDGET) */
const budgetSchema = z
  .number()
  .min(0)
  .max(10000)
  .nullable()

// =====================================================================
// 顶层 UserPreferencesUpdate (PUT 请求体)
// 与 backend/app/schemas/preferences.py PreferencesUpdate 字段对齐。
// 注: user_id 不在请求体内 (由 cookie/header 标识), 此处省略。
// 跨字段约束: budget_lunch_min ≤ budget_lunch_max (任一为 null 时跳过)。
// =====================================================================

export const userPreferencesUpdateSchema = z
  .object({
    cuisine_weights: cuisineWeightsSchema,
    allergies: allergiesSchema,
    spice_tolerance: spiceToleranceSchema,
    temperature_preference: temperatureSchema,
    default_location: defaultLocationSchema,
    budget_lunch_min: budgetSchema,
    budget_lunch_max: budgetSchema,
  })
  .refine(
    ({ budget_lunch_min, budget_lunch_max }) => {
      if (budget_lunch_min === null || budget_lunch_max === null) return true
      return budget_lunch_min <= budget_lunch_max
    },
    { message: 'budget_lunch_min must be <= budget_lunch_max', path: ['budget_lunch_min'] },
  )

export type UserPreferencesUpdate = z.infer<typeof userPreferencesUpdateSchema>

/** F001 §6 错误码 → zod issue 路径映射 (debug 友好) */
export const PREFERENCE_FIELD_TO_ERROR_CODE: Record<string, string> = {
  cuisine_weights: 'INVALID_CUISINE_ID',
  allergies: 'INVALID_ALLERGY',
  spice_tolerance: 'INVALID_SPICE',
  temperature_preference: 'INVALID_TEMPERATURE',
  default_location: 'INVALID_BUDGET',
  budget_lunch_min: 'INVALID_BUDGET',
  budget_lunch_max: 'INVALID_BUDGET',
}

// =====================================================================
// F050 §3 — UI → API 转换工具
// 把 chip 二元选择 + 滑杆 + 心情/temperature 翻成 UserPreferencesUpdate。
// 这里只写 zod 校验部分; 实际转换在 usePreferences.ts (Phase B)。
// =====================================================================

/** 滑杆 0-100 → 预算 ¥20-¥80 (线性映射, 整数元) */
export const sliderToBudget = (value: number): number => {
  const clamped = Math.max(0, Math.min(100, value))
  return Math.round(20 + (clamped / 100) * 60)
}

/** 滑杆 0-100 → 步行分钟 0-20 (线性映射, 取整) */
export const sliderToDistanceMin = (value: number): number => {
  const clamped = Math.max(0, Math.min(100, value))
  return Math.round((clamped / 100) * 20)
}

/** 把 UI chip 多选展开为 cuisine_weights: 选中=1.0, 未选=0.0, 未涉及 = 0.5 中性 */
export const tasteToCuisineWeights = (
  taste: CuisineId[],
): Record<CuisineId, number> => {
  const set = new Set(taste)
  return Object.fromEntries(
    CUISINE_IDS.map((id) => [id, set.has(id) ? 1.0 : 0.5] as const),
  ) as Record<CuisineId, number>
}