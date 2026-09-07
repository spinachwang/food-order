/**
 * F050 — Mood 单测
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Mood, type MoodOption } from './Mood'

const happy: MoodOption = { id: 'happy', emoji: '🌞', label: '吃好点' }

describe('Mood', () => {
  it('渲染 emoji + label', () => {
    render(<Mood option={happy} pressed={false} onSelect={() => {}} />)
    expect(screen.getByText('🌞')).toBeInTheDocument()
    expect(screen.getByText('吃好点')).toBeInTheDocument()
  })

  it('未选中 aria-checked=false', () => {
    render(<Mood option={happy} pressed={false} onSelect={() => {}} />)
    expect(screen.getByRole('radio', { name: '吃好点' })).toHaveAttribute('aria-checked', 'false')
  })

  it('选中 aria-checked=true', () => {
    render(<Mood option={happy} pressed={true} onSelect={() => {}} />)
    expect(screen.getByRole('radio', { name: '吃好点' })).toHaveAttribute('aria-checked', 'true')
  })

  it('click 触发 onSelect(option.id)', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<Mood option={happy} pressed={false} onSelect={onSelect} />)
    await user.click(screen.getByRole('radio', { name: '吃好点' }))
    expect(onSelect).toHaveBeenCalledWith('happy')
  })

  it('data-od-id=mood-<id>', () => {
    const { container } = render(<Mood option={happy} pressed={false} onSelect={() => {}} />)
    expect(container.querySelector('[data-od-id="mood-happy"]')).toBeInTheDocument()
  })
})