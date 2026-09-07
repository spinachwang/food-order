/**
 * F050 — ChatShell 集成测试
 *
 * 不渲染全部依赖 (PreferencesPanel 已经独立测了), 直接走 ChatShell
 * 验证: 顶层容器存在 + 推荐区占位 + 时钟渲染 + 空 thinking 状态.
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatShell } from './ChatShell'
import { useChatStore } from '../../stores/chatStore'

// Mock 整个 PreferencesPanel, 避免它去触发 TanStack Query
vi.mock('./components/PreferencesPanel', () => ({
  PreferencesPanel: () => <div data-od-id="prefs-panel" />,
}))

beforeEach(() => {
  useChatStore.setState({
    recommendation: null,
    thinking: [],
    status: 'idle',
    weather: null,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ChatShell', () => {
  it('顶层组装 TopBar + Hero + ContextStrip + RecommendationCard + Footer + Toaster', () => {
    const { container } = render(<ChatShell />)
    expect(screen.getByText('午饭吃什么')).toBeInTheDocument() // TopBar
    expect(screen.getByText(/今天中午/)).toBeInTheDocument() // Hero
    expect(screen.getByText(/天气暂不可用/)).toBeInTheDocument() // ContextStrip
    expect(container.querySelector('[data-od-id="reco-main-empty"]')).toBeInTheDocument()
    expect(container.querySelector('[data-od-id="thinking-log"]')).toBeInTheDocument()
    expect(screen.getByText(/数据:/)).toBeInTheDocument() // Footer
  })

  it('reco-wrap 容器存在', () => {
    const { container } = render(<ChatShell />)
    expect(container.querySelector('[data-od-id="reco-wrap"]')).toBeInTheDocument()
  })

  it('有 alternatives 时渲染 AltCard', () => {
    useChatStore.setState({
      recommendation: {
        headline: '辣',
        cuisine_id: 'sichuan',
        restaurant_id: 'poi-001',
        restaurant_name: '蜀香坊',
        order_takeout: false,
        reason: '麻辣',
        confidence: 0.9,
        alternatives: [
          {
            cuisine_id: 'japanese',
            restaurant_id: 'poi-002',
            restaurant_name: '和风亭',
            short_reason: '清淡',
          },
        ],
      },
    })
    const { container } = render(<ChatShell />)
    expect(container.querySelector('[data-od-id="reco-alt"]')).toBeInTheDocument()
    expect(container.querySelector('[data-od-id="alt-1"]')).toBeInTheDocument()
  })

  it('无 alternatives 时不渲染 alt-grid', () => {
    const { container } = render(<ChatShell />)
    expect(container.querySelector('[data-od-id="reco-alt"]')).toBeNull()
  })
})