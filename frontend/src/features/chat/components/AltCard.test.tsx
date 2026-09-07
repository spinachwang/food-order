/**
 * F050 — AltCard 单测
 */
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { AltCard } from './AltCard'
import { useChatStore } from '../../../stores/chatStore'
import type { AltRecommendation, Recommendation } from '../types'

const ALT: AltRecommendation = {
  cuisine_id: 'japanese',
  restaurant_id: 'poi-002',
  restaurant_name: '和风亭',
  short_reason: '清淡,适合想吃日料的下午',
}

const MAIN: Recommendation = {
  headline: '辣到爆',
  cuisine_id: 'sichuan',
  restaurant_id: 'poi-001',
  restaurant_name: '蜀香坊',
  order_takeout: false,
  reason: '麻辣暖身',
  confidence: 0.9,
  alternatives: [ALT, { ...ALT, restaurant_id: 'poi-003', restaurant_name: '渔歌' }],
}

beforeEach(() => {
  useChatStore.setState({ recommendation: MAIN })
})

describe('AltCard', () => {
  it('渲染 restaurant_name + short_reason', () => {
    const { container } = render(<AltCard alternative={ALT} index={0} />)
    expect(container.textContent).toContain('和风亭')
    expect(container.textContent).toContain('清淡')
  })

  it('click 触发 promoteAlternative → 主推替换', async () => {
    const user = userEvent.setup()
    const { container } = render(<AltCard alternative={ALT} index={0} />)
    const card = container.querySelector<HTMLDivElement>('[data-od-id="alt-1"]')
    if (!card) throw new Error('alt-1 not found')
    await user.click(card)
    const r = useChatStore.getState().recommendation
    expect(r?.restaurant_id).toBe('poi-002')
    expect(r?.restaurant_name).toBe('和风亭')
    expect(r?.alternatives).toHaveLength(1)
  })

  it('Enter/Space 触发 promoteAlternative', async () => {
    const { container } = render(<AltCard alternative={ALT} index={0} />)
    const card = container.querySelector<HTMLDivElement>('[data-od-id="alt-1"]')
    if (!card) throw new Error('alt-1 not found')
    card.focus()
    await userEvent.keyboard('{Enter}')
    expect(useChatStore.getState().recommendation?.restaurant_id).toBe('poi-002')
  })

  it('data-od-id=alt-<index+1>', () => {
    const { container } = render(<AltCard alternative={ALT} index={1} />)
    expect(container.querySelector('[data-od-id="alt-2"]')).toBeInTheDocument()
  })
})