/**
 * F050 — TopBar 单测 (mock Date,固定时间断言 4 时段问候语)
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TopBar } from './TopBar'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('TopBar', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(((...args: unknown[]) => {
      const Original = Intl.DateTimeFormat
      const [locale, opts] = args as [string, Intl.DateTimeFormatOptions]
      if (opts?.weekday) {
        return { format: () => '星期四' } as unknown as Intl.DateTimeFormat
      }
      return new Original(locale, opts)
    }) as unknown as typeof Intl.DateTimeFormat)
  })

  it('渲染品牌"午饭吃什么"', () => {
    render(<TopBar />)
    expect(screen.getByText('午饭吃什么')).toBeInTheDocument()
  })

  it('导航含"推荐" 且为 aria-current', () => {
    render(<TopBar />)
    const link = screen.getByRole('link', { name: '推荐' })
    expect(link).toHaveAttribute('aria-current', 'page')
  })

  it.each([
    { hour: 5, expected: '凌晨好' },
    { hour: 9, expected: '早上好' },
    { hour: 12, expected: '中午好' },
    { hour: 16, expected: '下午好' },
    { hour: 21, expected: '晚上好' },
  ])('hour=$hour 时问候语为 "$expected"', ({ hour, expected }) => {
    vi.setSystemTime(new Date(2026, 0, 1, hour, 30))
    render(<TopBar userName="Bo" />)
    expect(screen.getByLabelText(`问候: ${expected}，Bo 👋`)).toBeInTheDocument()
  })

  it('时钟显示 HH:MM · 星期X (mock 后)', () => {
    vi.setSystemTime(new Date(2026, 0, 1, 14, 7))
    render(<TopBar />)
    const clock = screen.getByLabelText('当前时间')
    expect(clock.textContent).toContain('14:07')
    expect(clock.textContent).toContain('星期四')
  })

  it('avatar aria-label 含首字母 Z', () => {
    render(<TopBar />)
    expect(screen.getByLabelText('用户头像 Z')).toBeInTheDocument()
  })
})