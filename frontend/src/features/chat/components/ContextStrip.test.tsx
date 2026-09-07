/**
 * F050 — ContextStrip 单测
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ContextStrip } from './ContextStrip'
import { useChatStore, DEFAULT_ADDRESS } from '../../../stores/chatStore'

beforeEach(() => {
  useChatStore.setState({
    address: DEFAULT_ADDRESS,
    weather: null,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ContextStrip', () => {
  it('渲染默认地址', () => {
    render(<ContextStrip />)
    expect(screen.getByText(DEFAULT_ADDRESS)).toBeInTheDocument()
  })

  it('weather 为 null 时显示"天气暂不可用"', () => {
    render(<ContextStrip />)
    expect(screen.getByText('天气暂不可用')).toBeInTheDocument()
    expect(screen.getByText(/Agent 按默认决策/)).toBeInTheDocument()
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

  it('addr-edit 按钮 click → 调用 window.prompt 并写 store', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'prompt').mockReturnValue('中关村')
    const { container } = render(<ContextStrip />)
    const btn = container.querySelector<HTMLButtonElement>('[data-od-id="addr-edit"]')
    expect(btn).toBeInTheDocument()
    if (btn) await user.click(btn)
    expect(useChatStore.getState().address).toBe('中关村')
  })

  it('now 注入时显示"正在查看 · HH:MM"', () => {
    render(<ContextStrip now={new Date(2026, 0, 1, 14, 7)} />)
    expect(screen.getByText(/正在查看 · 14:07/)).toBeInTheDocument()
  })
})