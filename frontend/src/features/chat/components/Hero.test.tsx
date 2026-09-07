/**
 * F050 — Hero 单测
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Hero } from './Hero'

describe('Hero', () => {
  it('渲染 h1 含 <em>吃点好的</em>', () => {
    render(<Hero greeting="中午好,张工" />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading.textContent).toContain('吃点好的')
    expect(heading.querySelector('em')?.textContent).toBe('吃点好的')
  })

  it('greeting 行可见', () => {
    render(<Hero greeting="下午好,张工" />)
    expect(screen.getByText('下午好,张工')).toBeInTheDocument()
  })

  it('hero-meta 显示午餐窗口与 Agent 在线', () => {
    render(<Hero greeting="晚上好" />)
    expect(screen.getByText('午餐窗口')).toBeInTheDocument()
    expect(screen.getByText('11:50 — 13:30')).toBeInTheDocument()
    expect(screen.getByText(/Agent 在线/)).toBeInTheDocument()
  })

  it('data-od-id=hero', () => {
    const { container } = render(<Hero greeting="早上好" />)
    expect(container.querySelector('[data-od-id="hero"]')).toBeInTheDocument()
  })
})