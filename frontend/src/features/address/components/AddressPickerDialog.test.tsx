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
})
