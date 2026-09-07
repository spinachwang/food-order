/**
 * F050 — Chip 单测
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Chip } from './Chip'

describe('Chip', () => {
  it('渲染 label + hint', () => {
    render(<Chip id="sichuan" label="川菜" hint="麻辣" pressed={false} onToggle={() => {}} />)
    expect(screen.getByText('川菜')).toBeInTheDocument()
    expect(screen.getByText('麻辣')).toBeInTheDocument()
  })

  it('未选中时 aria-pressed=false', () => {
    render(<Chip id="sichuan" label="川菜" pressed={false} onToggle={() => {}} />)
    expect(screen.getByRole('button', { name: /川菜/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('选中时 aria-pressed=true', () => {
    render(<Chip id="sichuan" label="川菜" pressed={true} onToggle={() => {}} />)
    expect(screen.getByRole('button', { name: /川菜/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('click 触发 onToggle(id)', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<Chip id="japanese" label="日料" pressed={false} onToggle={onToggle} />)
    await user.click(screen.getByRole('button', { name: /日料/ }))
    expect(onToggle).toHaveBeenCalledWith('japanese')
  })

  it('data-od-id=chip-<id>', () => {
    const { container } = render(<Chip id="dessert" label="甜品" pressed={false} onToggle={() => {}} />)
    expect(container.querySelector('[data-od-id="chip-dessert"]')).toBeInTheDocument()
  })
})