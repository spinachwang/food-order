/**
 * F051 §4 — AddressPickerDialog 单测.
 *
 * 覆盖 plan E-2 §测试 全部场景:
 * - 渲染 5 层 + 摘要
 * - 改省 → 市/区/商圈/小区/门牌号 reset
 * - 改市 → 区/商圈/小区/门牌号 reset
 * - 选 POI suggestion → 写入 community + poi_id
 * - 点保存 → 调 usePutPreferences mutation + chatStore.setAddress
 * - zod 校验失败 → 显示红字
 * - Esc → 关闭
 * - "使用当前位置" → mock navigator.geolocation → 自动填 city/district
 */
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as apiClient from '../../../lib/api-client'
import { AddressPickerDialog } from './AddressPickerDialog'
import { useChatStore } from '../../../stores/chatStore'
import {
  _resetAddressPickerForTests,
  useAddressPicker,
} from '../hooks/useAddressPicker'
import type { StructuredAddress } from '../../chat/types'

const mutateAsyncMock = vi.fn()
vi.mock('../../chat/hooks/usePreferences', () => ({
  usePutPreferences: () => ({
    mutateAsync: mutateAsyncMock,
    isPending: false,
  }),
}))

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

/** 通过 data-od-id 取元素 — 与 spec Playwright e2e 选择器一致 */
function qBy<T extends HTMLElement = HTMLElement>(
  container: HTMLElement,
  id: string,
): T {
  const el = container.querySelector<T>(`[data-od-id="${id}"]`)
  if (!el) throw new Error(`[data-od-id="${id}"] not found`)
  return el
}

/** 触发 open 的辅助组件 — 与 dialog 共享 useAddressPicker 全局状态 */
function OpenHelper() {
  const { openDialog } = useAddressPicker()
  return (
    <button
      type="button"
      data-testid="open-helper"
      onClick={() => openDialog()}
    >
      open
    </button>
  )
}

beforeEach(() => {
  mutateAsyncMock.mockReset()
  mutateAsyncMock.mockResolvedValue({})
  useChatStore.setState({ address: null })
  _resetAddressPickerForTests()
  // 默认 mock geolocation 不可用 — 单测按需覆盖
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    value: undefined,
    configurable: true,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AddressPickerDialog', () => {
  it('未 open 时不渲染', () => {
    const { container } = render(<AddressPickerDialog />, {
      wrapper: makeWrapper(),
    })
    expect(
      container.querySelector('[data-od-id="addr-picker-dialog"]'),
    ).toBeNull()
  })

  it('open 后渲染 5 层字段 + 实时摘要占位', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))

    expect(qBy(container, 'addr-picker-dialog')).toBeInTheDocument()
    expect(qBy(container, 'addr-picker-province')).toBeInTheDocument()
    expect(qBy(container, 'addr-picker-city')).toBeInTheDocument()
    expect(qBy(container, 'addr-picker-district')).toBeInTheDocument()
    expect(qBy(container, 'addr-picker-community')).toBeInTheDocument()
    expect(qBy(container, 'addr-picker-door')).toBeInTheDocument()
    expect(
      qBy(container, 'addr-picker-summary').textContent,
    ).toMatch(/至少选到城市级/)
  })

  // ---- F051 §6.4 修复回归: 点 POI 建议 → 把 POI 自带的 lng/lat 回填进 draft.
  // 修复前 onCommunitySelect 主动清空坐标, 导致保存后只剩 district_adcode,
  // 后端 search_restaurants 走 wrapper 的 district center fallback,
  // 1.5km 半径在大区里几乎搜不到东西 (用户报的"餐厅不在具体地址附近").

  it('点 POI 建议 → 保存时带上 POI 自带的精确坐标 (F051 §6.4 回归)', async () => {
    const user = userEvent.setup()
    vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([
      { adcode: '310106', name: '静安区', level: 'district', center: [0, 0], districts: [] },
    ])
    vi.spyOn(apiClient, 'searchPlaces').mockResolvedValue({
      count: 1,
      pois: [
        {
          poi_id: 'B0FFJ5AIYZ',
          name: '静安嘉里中心',
          address: '上海市静安区南京西路1515号',
          type: '商务住宅;楼宇;商务写字楼',
          // 高德 place/text 原生 location 字段 — 这就是要回填的精确锚点
          location: [121.450123, 31.228456],
        },
      ],
    })

    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))

    fireEvent.change(qBy(container, 'addr-picker-province'), {
      target: { value: '上海市' },
    })
    fireEvent.change(qBy(container, 'addr-picker-city'), {
      target: { value: '上海市' },
    })
    fireEvent.change(qBy(container, 'addr-picker-district'), {
      target: { value: '静安区' },
    })

    // 输入 community 关键字 → 触发 debounce → 走 searchPlaces mock → 渲染建议
    const communityInput = qBy<HTMLInputElement>(container, 'addr-picker-community')
    fireEvent.change(communityInput, { target: { value: '静安嘉里' } })

    // 建议列表渲染出 "静安嘉里中心" 按钮
    const suggestBtn = await screen.findByRole('button', {
      name: /静安嘉里中心/,
    })
    await user.click(suggestBtn)

    await user.click(qBy(container, 'addr-picker-save'))

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledTimes(1))
    const callArg = mutateAsyncMock.mock.calls[0]?.[0] as {
      default_location: StructuredAddress
    }
    expect(callArg.default_location.community).toBe('静安嘉里中心')
    expect(callArg.default_location.poi_id).toBe('B0FFJ5AIYZ')
    // 关键: lng/lat 必须等于 POI 自带的精确坐标 (不是 district center)
    expect(callArg.default_location.longitude).toBe(121.450123)
    expect(callArg.default_location.latitude).toBe(31.228456)
  })

  it('改省 → 摘要同步更新 + 清空下游 city/district', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))

    const provinceSelect = qBy<HTMLSelectElement>(
      container,
      'addr-picker-province',
    )
    fireEvent.change(provinceSelect, { target: { value: '上海市' } })

    const citySelect = qBy<HTMLSelectElement>(container, 'addr-picker-city')
    expect(citySelect.value).toBe('')
    expect(
      qBy(container, 'addr-picker-summary').textContent,
    ).toMatch(/至少选到城市级/)
  })

  it('直辖市选完省即可直接保存 (city == province)', async () => {
    const user = userEvent.setup()
    vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([])

    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))

    fireEvent.change(qBy(container, 'addr-picker-province'), {
      target: { value: '上海市' },
    })
    fireEvent.change(qBy(container, 'addr-picker-city'), {
      target: { value: '上海市' },
    })

    await user.click(qBy(container, 'addr-picker-save'))

    await waitFor(() =>
      expect(mutateAsyncMock).toHaveBeenCalledTimes(1),
    )
    const callArg = mutateAsyncMock.mock.calls[0]?.[0] as {
      default_location: StructuredAddress
    }
    expect(callArg.default_location.province).toBe('上海市')
    expect(callArg.default_location.city).toBe('上海市')
    expect(callArg.default_location.province_adcode).toBe('310000')
    // 直辖市: cn-cities 缓存里 city 条目与 province 同 adcode — 这是高德
    // API 直辖市的真实 adcode 体系 (310000 同时充当 city_adcode).
    expect(callArg.default_location.city_adcode).toBe('310000')
    expect(useChatStore.getState().address?.city).toBe('上海市')
  })

  it('省/市都未填就保存 → 显示校验失败红字, 不调 mutation', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))

    await user.click(qBy(container, 'addr-picker-save'))

    await waitFor(() => {
      const alert = container.querySelector('[role="alert"]')
      expect(alert?.textContent).toMatch(/至少选到城市级/)
    })
    expect(mutateAsyncMock).not.toHaveBeenCalled()
  })

  it('Esc 关闭 dialog', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))
    expect(qBy(container, 'addr-picker-dialog')).toBeInTheDocument()

    await user.keyboard('{Escape}')

    await waitFor(() =>
      expect(
        container.querySelector('[data-od-id="addr-picker-dialog"]'),
      ).toBeNull(),
    )
  })

  it('"使用当前位置" → 成功时自动填 city/district', async () => {
    const geoSuccess = vi.fn((success: PositionCallback) => {
      success({
        coords: {
          longitude: 121.473701,
          latitude: 31.230416,
          accuracy: 10,
        },
        timestamp: Date.now(),
      } as unknown as GeolocationPosition)
    })
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: { getCurrentPosition: geoSuccess },
      configurable: true,
    })
    vi.spyOn(apiClient, 'regeo').mockResolvedValue({
      province: '上海市',
      city: '上海市',
      district: '静安区',
      adcode: '310106',
      formatted_address: '上海市静安区南京西路',
      longitude: 121.473701,
      latitude: 31.230416,
      // F051 §3.2: 细粒度字段 mock 全为 null (geolocation 默认只到区级)
      street: null,
      community: null,
      door_no: null,
      poi_id: null,
    })

    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))
    await user.click(qBy(container, 'addr-picker-geolocate'))

    await waitFor(() =>
      expect(
        qBy(container, 'addr-picker-summary').textContent,
      ).toMatch(/上海市 · 静安区/),
    )
  })

  // ---- F051 §6.4: regeo 一次性捕获的 lng/lat 必须落到 default_location ----

  it('"使用当前位置" → 保存时把 lng/lat 一起发出去 (供 place/around 锚点)', async () => {
    const geoSuccess = vi.fn((success: PositionCallback) => {
      success({
        coords: {
          longitude: 121.473701,
          latitude: 31.230416,
          accuracy: 10,
        },
        timestamp: Date.now(),
      } as unknown as GeolocationPosition)
    })
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: { getCurrentPosition: geoSuccess },
      configurable: true,
    })
    vi.spyOn(apiClient, 'regeo').mockResolvedValue({
      province: '上海市',
      city: '上海市',
      district: '静安区',
      adcode: '310106',
      formatted_address: '上海市静安区南京西路',
      longitude: 121.473701,
      latitude: 31.230416,
      street: null,
      community: null,
      door_no: null,
      poi_id: null,
    })
    vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([])

    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))
    await user.click(qBy(container, 'addr-picker-geolocate'))

    // 等 regeo 填充完成 (province/city/district 都有)
    await waitFor(() =>
      expect(qBy(container, 'addr-picker-province')).toHaveValue('上海市'),
    )

    await user.click(qBy(container, 'addr-picker-save'))

    await waitFor(() =>
      expect(mutateAsyncMock).toHaveBeenCalledTimes(1),
    )
    const callArg = mutateAsyncMock.mock.calls[0]?.[0] as {
      default_location: StructuredAddress
    }
    // F051 §6.4 关键断言: lng/lat 必须被持久化, 不然后端要走
    // district_adcode → 区中心点 (「整个区只搜到 1.5km 内 POI」bug).
    expect(callArg.default_location.longitude).toBe(121.473701)
    expect(callArg.default_location.latitude).toBe(31.230416)
  })

  it('"使用当前位置" 之后再改省 → lng/lat 被清空 (老坐标不再代表新地址)', async () => {
    const geoSuccess = vi.fn((success: PositionCallback) => {
      success({
        coords: {
          longitude: 121.473701,
          latitude: 31.230416,
          accuracy: 10,
        },
        timestamp: Date.now(),
      } as unknown as GeolocationPosition)
    })
    Object.defineProperty(globalThis.navigator, 'geolocation', {
      value: { getCurrentPosition: geoSuccess },
      configurable: true,
    })
    vi.spyOn(apiClient, 'regeo').mockResolvedValue({
      province: '上海市',
      city: '上海市',
      district: '静安区',
      adcode: '310106',
      formatted_address: '上海市静安区南京西路',
      longitude: 121.473701,
      latitude: 31.230416,
      street: null,
      community: null,
      door_no: null,
      poi_id: null,
    })
    vi.spyOn(apiClient, 'getDistricts').mockResolvedValue([])

    const user = userEvent.setup()
    const { container } = render(
      <>
        <OpenHelper />
        <AddressPickerDialog />
      </>,
      { wrapper: makeWrapper() },
    )
    await user.click(screen.getByTestId('open-helper'))
    await user.click(qBy(container, 'addr-picker-geolocate'))

    await waitFor(() =>
      expect(qBy(container, 'addr-picker-province')).toHaveValue('上海市'),
    )

    // 改省 → 老坐标不再代表新地址, 一律清空 (同时 city 也被 reset, 故需要
    // 补填 city 才能让保存通过校验, 然后才能断言 lng/lat 是 null).
    fireEvent.change(qBy(container, 'addr-picker-province'), {
      target: { value: '北京市' },
    })
    fireEvent.change(qBy(container, 'addr-picker-city'), {
      target: { value: '北京市' },
    })

    await user.click(qBy(container, 'addr-picker-save'))

    await waitFor(() =>
      expect(mutateAsyncMock).toHaveBeenCalledTimes(1),
    )
    const callArg = mutateAsyncMock.mock.calls[0]?.[0] as {
      default_location: StructuredAddress
    }
    expect(callArg.default_location.province).toBe('北京市')
    expect(callArg.default_location.city).toBe('北京市')
    // 关键: lng/lat 必须为 null, 不然后端会用旧上海的坐标当北京的锚点
    expect(callArg.default_location.longitude).toBeNull()
    expect(callArg.default_location.latitude).toBeNull()
  })
})
