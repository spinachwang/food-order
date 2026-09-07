/**
 * F050 — Slider 单测
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Slider } from './Slider'

describe('Slider', () => {
  it('渲染 label + 当前值 + suffix', () => {
    render(<Slider label="距离" value={25} min={10} max={80} suffix="米" onChange={() => {}} ariaId="distance" />)
    expect(screen.getByText('距离')).toBeInTheDocument()
    expect(screen.getByText('25米')).toBeInTheDocument()
  })

  it('aria-valuenow 跟随 value', () => {
    render(<Slider label="预算" value={55} min={20} max={120} suffix="元" onChange={() => {}} ariaId="budget" />)
    expect(screen.getByLabelText('预算')).toHaveAttribute('aria-valuenow', '55')
    expect(screen.getByLabelText('预算')).toHaveAttribute('aria-valuemin', '20')
    expect(screen.getByLabelText('预算')).toHaveAttribute('aria-valuemax', '120')
  })

  it('change 触发 onChange(数字)', () => {
    const onChange = vi.fn()
    render(<Slider label="距离" value={25} min={10} max={80} onChange={onChange} ariaId="distance" />)
    const input = screen.getByLabelText('距离')
    fireEvent.change(input, { target: { value: '40' } })
    expect(onChange).toHaveBeenCalledWith(40)
  })

  it('data-od-id=<ariaId>-value 显示当前值', () => {
    const { container } = render(<Slider label="预算" value={42} min={20} max={120} onChange={() => {}} ariaId="budget" />)
    expect(container.querySelector('[data-od-id="budget-value"]')?.textContent).toBe('42')
  })
})