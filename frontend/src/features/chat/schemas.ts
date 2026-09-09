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

/**
 * F051 §3 — StructuredAddress 校验规则镜像后端
 * `backend/app/schemas/structured_address.py`:
 * - 必填: province / province_adcode / city / city_adcode
 * - adcode 必须 6 位数字 (正则 ^\d{6}$)
 * - poi_id 必须 8-32 位大写字母+数字 (正则 ^[A-Z0-9]{8,32}$)
 *   AMAP 实际 id 8-12 字符为主 (如 `B0I6KCBRAM`), 长 id 是早期风格的遗留
 * - 名称字段长度 1-32, 仅含 中文 / 字母 / 数字 / 空格 / `·`
 * - door_no 长度 ≤ 64
 * - longitude ∈ [-180, 180] / latitude ∈ [-90, 90] (F051 §6.4: regeo 一次性捕获,
 *   search_restaurants 用它当 place/around 锚点, 不必再走 district 中心点 fallback)
 * - district 与 district_adcode 必须同生同灭 (cross-field, 用 refine)
 * - longitude 与 latitude 必须同生同灭 (cross-field, 用 refine)
 */
const _ADCODE_PATTERN = /^\d{6}$/
const _POI_ID_PATTERN = /^[A-Z0-9]{8,32}$/
const _NAME_PATTERN = /^[一-龥一-鿿A-Za-z0-9 ·]{1,32}$/
const _NAME_MAX = 32
const _DOOR_NO_MAX = 64
const _LNG_MIN = -180
const _LNG_MAX = 180
const _LAT_MIN = -90
const _LAT_MAX = 90

const _adcodeFieldSchema = z
  .string()
  .regex(_ADCODE_PATTERN, 'adcode 必须是 6 位数字')
const _poiIdFieldSchema = z
  .string()
  .regex(_POI_ID_PATTERN, 'poi_id 必须是 8-32 位大写字母+数字')
const _nameFieldSchema = z
  .string()
  .max(_NAME_MAX, `名称字段长度必须 ≤ ${_NAME_MAX}`)
  .regex(
    _NAME_PATTERN,
    '名称字段仅含中文 / 字母 / 数字 / 空格 / 中点 ·',
  )
// F051 §6.4: regeo 一次性捕获的坐标. 用 z.number() (允许 int/float, 排除 NaN/Infinity),
// 与后端 StructuredAddress._check_longitude 镜像.
const _lngFieldSchema = z
  .number()
  .min(_LNG_MIN, `longitude 必须在 [${_LNG_MIN}, ${_LNG_MAX}]`)
  .max(_LNG_MAX, `longitude 必须在 [${_LNG_MIN}, ${_LNG_MAX}]`)
const _latFieldSchema = z
  .number()
  .min(_LAT_MIN, `latitude 必须在 [${_LAT_MIN}, ${_LAT_MAX}]`)
  .max(_LAT_MAX, `latitude 必须在 [${_LAT_MIN}, ${_LAT_MAX}]`)

/**
 * 可选字段：缺省视为 null，与后端 `Optional[...] = None` 行为一致。
 * 用 `.default(null)` 让 zod 输出类型保持 `T | null`（required but nullable），
 * 而不是 `T | null | undefined`，与 `StructuredAddress` interface 对齐。
 */
const _nullableAdcode = _adcodeFieldSchema.nullable().default(null)
const _nullablePoiId = _poiIdFieldSchema.nullable().default(null)
const _nullableName = _nameFieldSchema.nullable().default(null)
const _nullableLng = _lngFieldSchema.nullable().default(null)
const _nullableLat = _latFieldSchema.nullable().default(null)

export const structuredAddressSchema = z
  .object({
    province: _nameFieldSchema,
    province_adcode: _adcodeFieldSchema,
    city: _nameFieldSchema,
    city_adcode: _adcodeFieldSchema,
    district: _nullableName,
    district_adcode: _nullableAdcode,
    street: _nullableName,
    community: _nullableName,
    poi_id: _nullablePoiId,
    door_no: z.string().max(_DOOR_NO_MAX, `door_no 长度必须 ≤ ${_DOOR_NO_MAX}`).nullable().default(null),
    longitude: _nullableLng,
    latitude: _nullableLat,
  })
  .refine(
    (addr) =>
      (addr.district === null) === (addr.district_adcode === null),
    {
      message: 'district 与 district_adcode 必须同生同灭',
      path: ['district_adcode'],
    },
  )
  .refine(
    (addr) =>
      (addr.longitude === null) === (addr.latitude === null),
    {
      message: 'longitude 与 latitude 必须同生同灭',
      path: ['latitude'],
    },
  )

/** F051 §6.4 — `default_location` 由 string | null 迁移到 StructuredAddress | null.
 *  旧 DB 字段（plain string）会被后端 GET 时归一化为 null（见 preferences service
 *  `_normalize_default_location`），前端 PUT 时只接受 null 或完整对象。 */
const defaultLocationSchema = structuredAddressSchema.nullable()

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