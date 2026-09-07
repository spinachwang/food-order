/**
 * F050 — ThinkingLog 单测
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { ThinkingLog } from './ThinkingLog'
import { useChatStore } from '../../../stores/chatStore'

beforeEach(() => {
  useChatStore.setState({ thinking: [], status: 'idle' })
})

describe('ThinkingLog', () => {
  it('空数组显示占位文案', () => {
    render(<ThinkingLog />)
    expect(screen.getByText(/点.*问 agent.*开始追踪/)).toBeInTheDocument()
  })

  it('idle 状态 head 显示"今日决策路径"', () => {
    render(<ThinkingLog />)
    expect(screen.getByText('今日决策路径')).toBeInTheDocument()
  })

  it('streaming 状态 head 显示"agent 思考中"', () => {
    useChatStore.setState({ status: 'streaming' })
    render(<ThinkingLog />)
    expect(screen.getByText('agent 思考中…')).toBeInTheDocument()
  })

  it('error 状态 head 显示"agent 出错"', () => {
    useChatStore.setState({ status: 'error' })
    render(<ThinkingLog />)
    expect(screen.getByText('agent 出错')).toBeInTheDocument()
  })

  it('逐条渲染 thinking step', () => {
    useChatStore.setState({
      thinking: [
        { marker: 1, title: '读取偏好', em: '口味:川菜', status: 'done' },
        { marker: 2, title: '菜系专家分析', em: '等待中', status: 'pending' },
        { marker: 3, title: 'agent 出错', em: 'HTTP 500', status: 'error' },
      ],
    })
    render(<ThinkingLog />)
    expect(screen.getByText('读取偏好')).toBeInTheDocument()
    expect(screen.getByText('口味:川菜')).toBeInTheDocument()
    expect(screen.getByText('菜系专家分析')).toBeInTheDocument()
    expect(screen.getByText('agent 出错')).toBeInTheDocument()
    expect(screen.getByText('HTTP 500')).toBeInTheDocument()
  })

  it('data-od-id=thinking-log', () => {
    const { container } = render(<ThinkingLog />)
    expect(container.querySelector('[data-od-id="thinking-log"]')).toBeInTheDocument()
  })
})