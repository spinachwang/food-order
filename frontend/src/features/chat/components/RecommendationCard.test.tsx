/**
 * F050 — RecommendationCard 单测
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RecommendationCard } from './RecommendationCard'
import { useChatStore } from '../../../stores/chatStore'
import type { Recommendation, Restaurant } from '../types'

const RECO: Recommendation = {
  headline: '暖身又下饭,送上门刚好',
  cuisine_id: 'sichuan',
  restaurant_id: 'poi-001',
  restaurant_name: '蜀香坊',
  order_takeout: true,
  reason: '麻婆豆腐暖身,辣度刚好,15 分钟送达',
  confidence: 0.92,
  alternatives: [],
}

const R: Restaurant = {
  poi_id: 'poi-001',
  name: '蜀香坊',
  address: '国贸路 88 号',
  distance_meters: 420,
  rating: 4.6,
  avg_price: '48',
  cuisine_tags: ['川菜'],
  location: [116.46, 39.92],
}

function byId<T extends HTMLElement = HTMLElement>(
  container: HTMLElement,
  id: string,
): T {
  const el = container.querySelector<T>(`[data-od-id="${id}"]`)
  if (!el) throw new Error(`[data-od-id="${id}"] not found`)
  return el
}

beforeEach(() => {
  useChatStore.setState({
    recommendation: null,
    restaurantListsByCuisine: {},
    status: 'idle',
  })
})

describe('RecommendationCard', () => {
  it('降级态: 无 recommendation 时显示占位文案', () => {
    const { container } = render(<RecommendationCard />)
    expect(byId(container, 'reco-main-empty')).toBeInTheDocument()
    expect(screen.getByText(/今天没合适推荐/)).toBeInTheDocument()
  })

  it('降级态: status=error 时显示 agent 出错文案', () => {
    useChatStore.setState({ status: 'error' })
    render(<RecommendationCard />)
    expect(screen.getByText(/agent 没跑完/)).toBeInTheDocument()
  })

  it('渲染完整 6 字段 + 3 按钮', () => {
    useChatStore.setState({
      recommendation: RECO,
      restaurantListsByCuisine: { sichuan: [R] },
    })
    const { container } = render(<RecommendationCard />)
    expect(byId(container, 'reco-main')).toBeInTheDocument()
    expect(screen.getByText(RECO.headline)).toBeInTheDocument()
    expect(screen.getByText(RECO.restaurant_name)).toBeInTheDocument()
    expect(screen.getAllByText('92/100').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('420m')).toBeInTheDocument()
    expect(screen.getByText('¥48')).toBeInTheDocument()
    expect(byId(container, 'go-eat')).toBeInTheDocument()
    expect(byId(container, 'share-eat')).toBeInTheDocument()
    expect(byId(container, 'save-eat')).toBeInTheDocument()
  })

  it('无 restaurant 数据时显示未知 / —', () => {
    useChatStore.setState({ recommendation: RECO })
    render(<RecommendationCard />)
    expect(screen.getByText('未知')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('go-eat 跳到 amap marker URL', async () => {
    const open = vi.fn()
    Object.defineProperty(window, 'open', { value: open, writable: true })
    useChatStore.setState({
      recommendation: RECO,
      restaurantListsByCuisine: { sichuan: [R] },
    })
    const user = userEvent.setup()
    const { container } = render(<RecommendationCard />)
    await user.click(byId(container, 'go-eat'))
    expect(open).toHaveBeenCalled()
    const url = open.mock.calls[0]?.[0] as string
    expect(url).toContain('uri.amap.com/marker')
    expect(url).toContain('116.46,39.92')
    expect(url).toContain(encodeURIComponent('蜀香坊'))
  })

  it('share-eat 渲染 share 按钮', () => {
    useChatStore.setState({
      recommendation: RECO,
      restaurantListsByCuisine: { sichuan: [R] },
    })
    const { container } = render(<RecommendationCard />)
    expect(byId(container, 'share-eat')).toBeInTheDocument()
  })

  it('save-eat 切按钮文案 (M1 仅本地)', async () => {
    const user = userEvent.setup()
    useChatStore.setState({ recommendation: RECO })
    const { container } = render(<RecommendationCard />)
    const btn = byId<HTMLButtonElement>(container, 'save-eat')
    expect(btn.textContent).toContain('收藏')
    await user.click(btn)
    expect(btn.textContent).toContain('已收藏')
    expect(btn).toBeDisabled()
  })
})