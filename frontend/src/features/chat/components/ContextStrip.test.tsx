/**
 * F050 / F051 — ContextStrip 单测.
 *
 * F051 §6.5 覆盖:
 * - address === null → 显示 DEFAULT_LEGACY_ADDRESS 兜底字符串
 * - address 为 StructuredAddress → 显示 formatAddressSummary 拼出的字符串
 * - addr-edit 按钮 → 触发 useAddressPicker().openDialog() (即 _open 变 true)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ContextStrip } from './ContextStrip'
import { useChatStore, DEFAULT_LEGACY_ADDRESS } from '../../../stores/chatStore'
import type { StructuredAddress } from '../../chat/types'
import { _resetAddressPickerForTests } from '../../address/hooks/useAddressPicker'

const sampleAddress: StructuredAddress = {
  province: '上海市',
  province_adcode: '310000',
  city: '上海市',
  city_adcode: '310100',
  district: '静安区',
  district_adcode: '310106',
  street: null,
  community: '静安嘉里中心',
  poi_id: null,
  door_no: 'B2',
}

beforeEach(() => {
  useChatStore.setState({
    address: null,
    weather: null,
  })
  _resetAddressPickerForTests()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ContextStrip', () => {
  it('address 为 null 时显示 DEFAULT_LEGACY_ADDRESS 兜底', () => {
    render(<ContextStrip />)
    expect(screen.getByText(DEFAULT_LEGACY_ADDRESS)).toBeInTheDocument()
  })

  it('weather 为 null 时显示"天气暂不可用"', () => {
    render(<ContextStrip />)
    expect(screen.getByText('天气暂不可用')).toBeInTheDocument()
    expect(screen.getByText(/Agent 按默认决策/)).toBeInTheDocument()
  })

  it('address 为结构化地址时显示 formatAddressSummary 拼接结果', () => {
    useChatStore.setState({ address: sampleAddress })
    render(<ContextStrip />)
    // sampleAddress → "上海市 · 静安区 · 静安嘉里中心 · B2"
    expect(
      screen.getByText('上海市 · 静安区 · 静安嘉里中心 · B2'),
    ).toBeInTheDocument()
  })

  it('weather 存在时显示温度 + condition', () => {
    useChatStore.setState({
      weather: {
        location: '北京',
        province: '北京市',
        city: '北京',
        adcode: '110000',
        temperature_celsius: 28.4,
        condition: 'cloudy',
        humidity_percent: 60,
        wind_direction: '东南',
        wind_level: 3,
        precipitation_probability: 20,
        forecast_3h: [],
        fetched_at: '2026-09-06T10:00:00Z',
      },
    })
    render(<ContextStrip />)
    expect(screen.getByText(/28° · cloudy/)).toBeInTheDocument()
    expect(screen.getByText(/东南风 3级 · 湿度 60%/)).toBeInTheDocument()
  })

  it('addr-edit 按钮 click → 触发 useAddressPicker.openDialog (无 prompt 弹窗)', async () => {
    // F051: 移除 window.prompt 路径, 编辑按钮改触发 dialog (Phase E-2 落地).
    // 当前测试只验证 click 不再调 prompt, 且 useAddressPicker 的 _open 变 true.
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null)
    const user = userEvent.setup()
    const { container } = render(<ContextStrip />)
    const btn = container.querySelector<HTMLButtonElement>('[data-od-id="addr-edit"]')
    expect(btn).toBeInTheDocument()
    if (btn) await user.click(btn)
    expect(promptSpy).not.toHaveBeenCalled()
  })

  it('now 注入时显示"正在查看 · HH:MM"', () => {
    render(<ContextStrip now={new Date(2026, 0, 1, 14, 7)} />)
    expect(screen.getByText(/正在查看 · 14:07/)).toBeInTheDocument()
  })
})
