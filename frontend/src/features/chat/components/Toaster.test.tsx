/**
 * F050 — Toaster 单测
 * 验证渲染 toastStore 中的 toasts, 自动 dismiss 4s 后移除.
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Toaster } from './Toaster'
import { useToastStore } from '../../../stores/toastStore'

beforeEach(() => {
  useToastStore.setState({ toasts: [] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Toaster', () => {
  it('空 store 时不渲染任何 toast', () => {
    render(<Toaster />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('渲染 toastStore 中的 toast', () => {
    useToastStore.getState().push('info', '保存成功')
    render(<Toaster />)
    expect(screen.getByText('保存成功')).toBeInTheDocument()
  })

  it('kind=error 走 error 样式分支', () => {
    useToastStore.getState().push('error', '网络断了')
    const { container } = render(<Toaster />)
    const toast = container.querySelector('[aria-live="polite"]')
    expect(toast?.className).toMatch(/error/)
  })

  it('kind=success 走 success 样式分支', () => {
    useToastStore.getState().push('success', '已收藏')
    const { container } = render(<Toaster />)
    const toast = container.querySelector('[aria-live="polite"]')
    expect(toast?.className).toMatch(/success/)
  })

  it('toast click 触发 dismiss', async () => {
    useToastStore.getState().push('info', '点我')
    render(<Toaster />)
    await act(async () => {
      screen.getByText('点我').click()
    })
    expect(useToastStore.getState().toasts).toHaveLength(0)
  })

  it('4 秒后自动 dismiss', () => {
    vi.useFakeTimers()
    useToastStore.getState().push('info', '自动消失')
    render(<Toaster />)
    expect(screen.getByText('自动消失')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(useToastStore.getState().toasts).toHaveLength(0)
  })

  it('同时显示最多 3 条 (store MAX_VISIBLE=3 决定)', () => {
    const push = useToastStore.getState().push
    push('info', 'a')
    push('info', 'b')
    push('info', 'c')
    push('info', 'd')
    render(<Toaster />)
    // 队列上限 3, 第一条 'a' 被挤掉
    expect(screen.queryByText('a')).toBeNull()
    expect(screen.getByText('b')).toBeInTheDocument()
    expect(screen.getByText('c')).toBeInTheDocument()
    expect(screen.getByText('d')).toBeInTheDocument()
  })
})