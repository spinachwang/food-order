/**
 * F051 §6.5 — `formatAddressSummary` 单元测试.
 *
 * 覆盖 spec §2.3 全部层级组合 + 空白/null 过滤.
 */
import { describe, expect, it } from 'vitest'
import type { StructuredAddress } from '../../chat/types'
import { formatAddressSummary } from './formatAddressSummary'

function addr(overrides: Partial<StructuredAddress> = {}): StructuredAddress {
  return {
    province: '上海市',
    province_adcode: '310000',
    city: '上海市',
    city_adcode: '310100',
    district: null,
    district_adcode: null,
    street: null,
    community: null,
    poi_id: null,
    door_no: null,
    ...overrides,
  }
}

describe('formatAddressSummary', () => {
  it('returns empty string for null', () => {
    expect(formatAddressSummary(null)).toBe('')
  })

  it('renders city only when district/community/door_no are null', () => {
    expect(formatAddressSummary(addr())).toBe('上海市')
  })

  it('joins city + district with middle dot', () => {
    expect(
      formatAddressSummary(
        addr({ district: '静安区', district_adcode: '310106' }),
      ),
    ).toBe('上海市 · 静安区')
  })

  it('joins city + district + community', () => {
    expect(
      formatAddressSummary(
        addr({
          district: '静安区',
          district_adcode: '310106',
          community: '静安嘉里中心',
        }),
      ),
    ).toBe('上海市 · 静安区 · 静安嘉里中心')
  })

  it('joins all four layers when door_no present', () => {
    expect(
      formatAddressSummary(
        addr({
          district: '静安区',
          district_adcode: '310106',
          community: '静安嘉里中心',
          door_no: 'B2',
        }),
      ),
    ).toBe('上海市 · 静安区 · 静安嘉里中心 · B2')
  })

  it('skips empty-string fields', () => {
    expect(
      formatAddressSummary(
        addr({ district: '', district_adcode: null, community: '' }),
      ),
    ).toBe('上海市')
  })

  it('skips whitespace-only fields', () => {
    expect(
      formatAddressSummary(
        addr({ district: '   ', district_adcode: null, community: '\t' }),
      ),
    ).toBe('上海市')
  })

  it('ignores street (UI 不展示这一层)', () => {
    // spec §2.3 摘要规则只展示 city / district / community / door_no;
    // street 字段保留在数据里但不进摘要字符串
    expect(
      formatAddressSummary(
        addr({
          district: '静安区',
          district_adcode: '310106',
          street: '南京西路',
          community: '静安嘉里中心',
        }),
      ),
    ).toBe('上海市 · 静安区 · 静安嘉里中心')
  })
})
