/**
 * F051 §3 — `structuredAddressSchema` zod 校验 + `userPreferencesUpdateSchema`
 * 在 `default_location` 字段上的级联测试.
 *
 * 校验规则镜像后端 `backend/app/schemas/structured_address.py`:
 * - 必填: province / province_adcode / city / city_adcode
 * - adcode 必须 6 位数字 (正则 ^\d{6}$)
 * - poi_id 必须 20-32 位大写字母+数字 (正则 ^[A-Z0-9]{20,32}$)
 * - 名称字段 (province/city/district/street/community) 长度 1-32, 仅含
 *   中文 / 字母 / 数字 / 空格 / `·`
 * - door_no 长度 ≤ 64
 * - district 与 district_adcode 必须同生同灭 (cross-field)
 */
import { describe, expect, it } from 'vitest'
import {
  structuredAddressSchema,
  userPreferencesUpdateSchema,
} from './schemas'

const validSample = {
  province: '上海市',
  province_adcode: '310000',
  city: '上海市',
  city_adcode: '310100',
  district: '静安区',
  district_adcode: '310106',
  street: '南京西路',
  community: '静安嘉里中心',
  poi_id: 'B0FFFAB6J2ABCDEFGHIJ',
  door_no: 'B2',
}

describe('structuredAddressSchema', () => {
  describe('happy path', () => {
    it('accepts a fully populated address', () => {
      const result = structuredAddressSchema.safeParse(validSample)
      expect(result.success).toBe(true)
    })

    it('accepts minimal address (province + city only)', () => {
      const result = structuredAddressSchema.safeParse({
        province: '北京市',
        province_adcode: '110000',
        city: '北京市',
        city_adcode: '110100',
      })
      expect(result.success).toBe(true)
    })

    it('accepts name with letters / digits / spaces / middle dot', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        community: 'SOHO · 1号',
      })
      expect(result.success).toBe(true)
    })
  })

  describe('adcode validation', () => {
    it('rejects adcode with 5 digits', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        province_adcode: '31000',
      })
      expect(result.success).toBe(false)
    })

    it('rejects adcode with 7 digits', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        city_adcode: '31001000',
      })
      expect(result.success).toBe(false)
    })

    it('rejects adcode with non-digit chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        province_adcode: '31A000',
      })
      expect(result.success).toBe(false)
    })
  })

  describe('poi_id validation', () => {
    it('rejects poi_id shorter than 20 chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        poi_id: 'B0FFFAB6J2',
      })
      expect(result.success).toBe(false)
    })

    it('rejects poi_id with lowercase', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        poi_id: 'b0fffab6j2abcdefghij',
      })
      expect(result.success).toBe(false)
    })

    it('accepts poi_id of 32 chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        poi_id: 'A'.repeat(32),
      })
      expect(result.success).toBe(true)
    })
  })

  describe('name field validation', () => {
    it('rejects empty string', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        province: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects name with disallowed punctuation (slash)', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        city: '上海/市',
      })
      expect(result.success).toBe(false)
    })

    it('rejects name longer than 32 chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        community: '啊'.repeat(33),
      })
      expect(result.success).toBe(false)
    })
  })

  describe('door_no validation', () => {
    it('accepts door_no up to 64 chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        door_no: 'a'.repeat(64),
      })
      expect(result.success).toBe(true)
    })

    it('rejects door_no longer than 64 chars', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        door_no: 'a'.repeat(65),
      })
      expect(result.success).toBe(false)
    })
  })

  describe('cross-field district pairing', () => {
    it('rejects district set but district_adcode null', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        district: '静安区',
        district_adcode: null,
      })
      expect(result.success).toBe(false)
    })

    it('rejects district_adcode set but district null', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        district: null,
        district_adcode: '310106',
      })
      expect(result.success).toBe(false)
    })

    it('accepts both null', () => {
      const result = structuredAddressSchema.safeParse({
        ...validSample,
        district: null,
        district_adcode: null,
      })
      expect(result.success).toBe(true)
    })
  })
})

describe('userPreferencesUpdateSchema default_location', () => {
  // 14 个菜系 keys 全列 — schema 要求 cuisine_weights 完整
  const fullCuisineWeights = Object.fromEntries(
    [
      'sichuan', 'cantonese', 'shandong', 'suzhou', 'zhejiang',
      'fujian', 'hunan', 'anhui', 'japanese', 'western',
      'western_fastfood', 'chinese_fastfood', 'snacks', 'dessert_drinks',
    ].map((id) => [id, 0.5]),
  )

  const baseValidPrefs = {
    cuisine_weights: fullCuisineWeights,
    allergies: [],
    spice_tolerance: 1,
    temperature_preference: 'hot' as const,
    default_location: null as null,
    budget_lunch_min: 20,
    budget_lunch_max: 60,
  }

  it('accepts null default_location (legacy compat: 旧用户未填地址)', () => {
    const result = userPreferencesUpdateSchema.safeParse(baseValidPrefs)
    expect(result.success).toBe(true)
  })

  it('accepts a valid StructuredAddress object', () => {
    const result = userPreferencesUpdateSchema.safeParse({
      ...baseValidPrefs,
      default_location: validSample,
    })
    expect(result.success).toBe(true)
  })

  it('rejects legacy plain string (旧 DB 字段遗留值)', () => {
    const result = userPreferencesUpdateSchema.safeParse({
      ...baseValidPrefs,
      default_location: '上海 · 静安嘉里中心',
    })
    expect(result.success).toBe(false)
  })

  it('rejects malformed StructuredAddress (missing province_adcode)', () => {
    const result = userPreferencesUpdateSchema.safeParse({
      ...baseValidPrefs,
      default_location: {
        province: '上海市',
        city: '上海市',
        city_adcode: '310100',
      },
    })
    expect(result.success).toBe(false)
  })
})
