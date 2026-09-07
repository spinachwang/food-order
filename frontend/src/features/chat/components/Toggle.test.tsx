/**
 * F050 — Toggle 单测
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('role=radio', () => {
    render(<Toggle id="hot" label="热" pressed={false} onSelect={() => {}} />)
    expect(screen.getByRole('radio', { name: '热' })).toBeInTheDocument()
  })

  it('未选中 aria-checked=false', () => {
    render(<Toggle id="hot" label="热" pressed={false} onSelect={() => {}} />)
    expect(screen.getByRole('radio', { name: '热' })).toHaveAttribute('aria-checked', 'false')
  })

  it('选中 aria-checked=true', () => {
    render(<Toggle id="hot" label="热" pressed={true} onSelect={() => {}} />)
    expect(screen.getByRole('radio', { name: '热' })).toHaveAttribute('aria-checked', 'true')
  })

  it('click 触发 onSelect(id)', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<Toggle id="cold" label="凉" pressed={false} onSelect={onSelect} />)
    await user.click(screen.getByRole('radio', { name: '凉' }))
    expect(onSelect).toHaveBeenCalledWith('cold')
  })
})