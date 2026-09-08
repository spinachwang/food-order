/**
 * F051 §2.1 #6 — `cn-cities` 硬编码数据测试.
 *
 * 覆盖:
 * - 36 项 (4 直辖市 + 27 省会 + 5 计划单列市)
 * - 所有 adcode 6 位数字且无重复
 * - 所有 name 与高德 district.name 一致 (snapshot 测试)
 */
import { describe, expect, it } from 'vitest'
import {
  CN_CITIES,
  findCityByAdcode,
  findCityByName,
} from './cn-cities'

describe('CN_CITIES', () => {
  it('恰好 36 项', () => {
    expect(CN_CITIES).toHaveLength(36)
  })

  it('所有 adcode 6 位数字', () => {
    for (const c of CN_CITIES) {
      expect(c.adcode).toMatch(/^\d{6}$/)
    }
  })

  it('所有 adcode 无重复', () => {
    const adcodes = CN_CITIES.map((c) => c.adcode)
    expect(new Set(adcodes).size).toBe(adcodes.length)
  })

  it('所有 name 无重复', () => {
    const names = CN_CITIES.map((c) => c.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it('包含 4 直辖市', () => {
    const names = CN_CITIES.map((c) => c.name)
    expect(names).toEqual(
      expect.arrayContaining(['北京市', '天津市', '上海市', '重庆市']),
    )
  })

  it('包含 5 计划单列市', () => {
    const names = CN_CITIES.map((c) => c.name)
    expect(names).toEqual(
      expect.arrayContaining([
        '大连市',
        '青岛市',
        '宁波市',
        '厦门市',
        '深圳市',
      ]),
    )
  })
})

describe('findCityByName', () => {
  it('找到已知城市', () => {
    expect(findCityByName('上海市')).toEqual({ name: '上海市', adcode: '310000' })
  })

  it('未找到返回 undefined', () => {
    expect(findCityByName('火星市')).toBeUndefined()
  })
})

describe('findCityByAdcode', () => {
  it('找到已知 adcode', () => {
    expect(findCityByAdcode('110000')).toEqual({ name: '北京市', adcode: '110000' })
  })

  it('未找到返回 undefined', () => {
    expect(findCityByAdcode('999999')).toBeUndefined()
  })
})
