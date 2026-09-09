/**
 * F051 §2.1 #6 — `cn-cities` 硬编码数据测试.
 *
 * 覆盖两个并列常量:
 * 1. CN_PROVINCES (34 项省级单位) — AddressPickerDialog 省级 select
 * 2. CN_CITY_CACHE (36 项常用市级单位) — regeo 回调反查市级 adcode
 */
import { describe, expect, it } from 'vitest'
import {
  CN_CITY_CACHE,
  CN_PROVINCES,
  findCityInCacheByAdcode,
  findCityInCacheByName,
  findProvinceByAdcode,
  findProvinceByName,
} from './cn-cities'

describe('CN_PROVINCES (省级单位)', () => {
  it('恰好 34 项 (省级单位总数)', () => {
    expect(CN_PROVINCES).toHaveLength(34)
  })

  it('所有 adcode 6 位数字', () => {
    for (const c of CN_PROVINCES) {
      expect(c.adcode).toMatch(/^\d{6}$/)
    }
  })

  it('所有 adcode 都是省级单位 (末尾 0000)', () => {
    for (const c of CN_PROVINCES) {
      expect(c.adcode.endsWith('0000')).toBe(true)
    }
  })

  it('所有 adcode 无重复', () => {
    const adcodes = CN_PROVINCES.map((c) => c.adcode)
    expect(new Set(adcodes).size).toBe(adcodes.length)
  })

  it('所有 name 无重复', () => {
    const names = CN_PROVINCES.map((c) => c.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it('包含 4 直辖市', () => {
    const names = CN_PROVINCES.map((c) => c.name)
    expect(names).toEqual(
      expect.arrayContaining(['北京市', '天津市', '上海市', '重庆市']),
    )
  })

  it('包含 2 特别行政区', () => {
    const names = CN_PROVINCES.map((c) => c.name)
    expect(names).toEqual(
      expect.arrayContaining(['香港特别行政区', '澳门特别行政区']),
    )
  })

  it('包含浙江省 (regeo 杭州时必须能匹配省级)', () => {
    // F051 §4 bug 修复: 之前 36 项里没有省级浙江省, regeo 返回 "浙江省"
    // 无法匹配, 后续级联全错位
    expect(findProvinceByName('浙江省')).toEqual({
      name: '浙江省',
      adcode: '330000',
    })
  })

  it('省级不混入市级 adcode (末 4 位 ≠ 0000)', () => {
    // 早期 36 项含 「杭州市 (330100)」等市级 adcode,
    // 用户在省 select 实际选到了市, 触发 F051 §4 bug
    const names = CN_PROVINCES.map((c) => c.name)
    expect(names).not.toContain('杭州市')
    expect(names).not.toContain('哈尔滨市')
    expect(names).not.toContain('深圳市')
  })
})

describe('findProvinceByName / findProvinceByAdcode', () => {
  it('按 name 找到上海市', () => {
    expect(findProvinceByName('上海市')).toEqual({
      name: '上海市',
      adcode: '310000',
    })
  })

  it('按 adcode 找到北京市', () => {
    expect(findProvinceByAdcode('110000')).toEqual({
      name: '北京市',
      adcode: '110000',
    })
  })

  it('未找到返回 undefined', () => {
    expect(findProvinceByName('火星市')).toBeUndefined()
    expect(findProvinceByAdcode('999999')).toBeUndefined()
  })
})

describe('CN_CITY_CACHE (常用市级单位)', () => {
  it('恰好 36 项 (4 直辖市 + 27 省会 + 5 计划单列市)', () => {
    expect(CN_CITY_CACHE).toHaveLength(36)
  })

  it('所有 adcode 6 位数字', () => {
    for (const c of CN_CITY_CACHE) {
      expect(c.adcode).toMatch(/^\d{6}$/)
    }
  })

  it('所有 adcode 无重复', () => {
    const adcodes = CN_CITY_CACHE.map((c) => c.adcode)
    expect(new Set(adcodes).size).toBe(adcodes.length)
  })

  it('直辖市 / 省会 / 计划单列市都在内', () => {
    const names = CN_CITY_CACHE.map((c) => c.name)
    expect(names).toEqual(
      expect.arrayContaining([
        // 4 直辖市
        '北京市', '上海市', '天津市', '重庆市',
        // 省会典型
        '杭州市', '广州市', '武汉市', '成都市',
        // 计划单列市
        '大连市', '青岛市', '宁波市', '厦门市', '深圳市',
      ]),
    )
  })

  it('杭州市能查到市级 adcode 330100', () => {
    // F051 §4 bug 修复: regeo city='杭州市' 必须拿到 330100 市级 adcode,
    // 之前若只用省级 CN_PROVINCES 查, fallback 到 330106 区级 — 错
    expect(findCityInCacheByName('杭州市')).toEqual({
      name: '杭州市',
      adcode: '330100',
    })
  })

  it('直辖市在市级 cache 里 (city=北京市 时能查回)', () => {
    // regeo 对北京返回 city='北京市' (同 province 字符串), 必须能查回 110000
    expect(findCityInCacheByName('北京市')).toEqual({
      name: '北京市',
      adcode: '110000',
    })
  })
})

describe('findCityInCacheByName / findCityInCacheByAdcode', () => {
  it('按 name 找到杭州市', () => {
    expect(findCityInCacheByName('杭州市')?.adcode).toBe('330100')
  })

  it('按 adcode 找到深圳市', () => {
    expect(findCityInCacheByAdcode('440300')).toEqual({
      name: '深圳市',
      adcode: '440300',
    })
  })

  it('未找到返回 undefined', () => {
    expect(findCityInCacheByName('火星市')).toBeUndefined()
    expect(findCityInCacheByAdcode('999999')).toBeUndefined()
  })
})