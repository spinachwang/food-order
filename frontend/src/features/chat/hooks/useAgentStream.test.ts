import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useChatStore, resetChatStepCounter } from '../../../stores/chatStore'
import type { ChatRequest } from '../types'

/** 构造 SSE 文本流 (按 SSE spec 用 \n\n 分隔) */
function sseText(events: Array<{ event: string; data: unknown }>): string {
  return events
    .map(
      (e) =>
        `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n`,
    )
    .join('\n')
}

/** 把字符串包成 ReadableStream<Uint8Array> */
function makeStream(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text))
      controller.close()
    },
  })
}

beforeEach(() => {
  resetChatStepCounter()
  // 重置 store
  useChatStore.setState({
    status: 'idle',
    selectedCuisines: [],
    routingReason: '',
    cuisineResultsByCuisine: {},
    restaurantListsByCuisine: {},
    weather: null,
    recommendation: null,
    thinking: [],
    error: null,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useAgentStream — dispatch of full event sequence', () => {
  it('parses 6 SSE events and updates store accordingly', async () => {
    const { useAgentStream } = await import('./useAgentStream')

    const events = [
      { event: 'cuisine_selected', data: { cuisines: ['sichuan', 'hunan'], routing_reason: '你说想吃辣的' } },
      {
        event: 'cuisine_result',
        data: {
          results: {
            sichuan: {
              cuisine_id: 'sichuan',
              conclusion: '川菜以麻辣著称',
              keywords: ['麻', '辣'],
              matched_allergies: [],
            },
          },
        },
      },
      {
        event: 'restaurant_found',
        data: {
          restaurant_lists: {
            sichuan: [
              {
                poi_id: 'B001',
                name: '蜀香苑',
                address: '国贸三期',
                distance_meters: 380,
                rating: 4.6,
                avg_price: '48',
                cuisine_tags: ['川菜'],
                location: [116.46, 39.91],
              },
            ],
          },
        },
      },
      {
        event: 'weather',
        data: {
          weather: {
            location: '北京',
            province: '北京',
            city: '北京',
            adcode: '110000',
            temperature_celsius: 30,
            condition: 'sunny',
            humidity_percent: 60,
            wind_direction: '东南',
            wind_level: 2,
            precipitation_probability: 0.05,
            forecast_3h: [],
            fetched_at: '2026-09-07T12:00:00Z',
          },
        },
      },
      {
        event: 'recommendation',
        data: {
          recommendation: {
            headline: '今天吃蜀香苑',
            cuisine_id: 'sichuan',
            restaurant_id: 'B001',
            restaurant_name: '蜀香苑',
            order_takeout: false,
            reason: '距离 380m, 天气晴朗',
            confidence: 0.92,
            alternatives: [],
          },
        },
      },
      { event: 'done', data: {} },
    ]

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(makeStream(sseText(events)), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )

    const { start } = renderHook(() => useAgentStream()).result.current
    await start({ message: '今天想吃辣的' } as ChatRequest)

    const s = useChatStore.getState()
    expect(s.status).toBe('done')
    expect(s.selectedCuisines).toEqual(['sichuan', 'hunan'])
    expect(s.routingReason).toBe('你说想吃辣的')
    expect(s.cuisineResultsByCuisine.sichuan?.conclusion).toBe('川菜以麻辣著称')
    expect(s.restaurantListsByCuisine.sichuan?.[0]?.poi_id).toBe('B001')
    expect(s.weather?.temperature_celsius).toBe(30)
    expect(s.recommendation?.headline).toBe('今天吃蜀香苑')
    // thinking 应有 ≥4 步
    expect(s.thinking.length).toBeGreaterThanOrEqual(4)
    // 最后一步标记 done
    expect(s.thinking[s.thinking.length - 1]!.status).toBe('done')
  })

  it('sets status=error when fetch rejects', async () => {
    const { useAgentStream } = await import('./useAgentStream')
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('network down'))

    const { start } = renderHook(() => useAgentStream()).result.current
    await start({ message: 'no network' } as ChatRequest)

    const s = useChatStore.getState()
    expect(s.status).toBe('error')
    expect(s.error).toContain('network')
  })

  it('marks status=error with stream-interrupted step when done missing', async () => {
    const { useAgentStream } = await import('./useAgentStream')
    // 只有 cuisine_selected 就关闭流, 没有 done
    const partial = sseText([
      { event: 'cuisine_selected', data: { cuisines: ['sichuan'], routing_reason: 'partial' } },
    ])
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(makeStream(partial), { status: 200 }),
    )

    const { start } = renderHook(() => useAgentStream()).result.current
    await start({ message: 'half' } as ChatRequest)

    const s = useChatStore.getState()
    expect(s.status).toBe('error')
    expect(s.error).toMatch(/流式|中断|interrupted/i)
    // 最后一步 status=error
    expect(s.thinking.at(-1)?.status).toBe('error')
  })

  it('appends error step on SSE error event', async () => {
    const { useAgentStream } = await import('./useAgentStream')
    const events = sseText([
      {
        event: 'error',
        data: { code: 'AGENT_GRAPH_ERROR', message: 'LLM timeout' },
      },
      { event: 'done', data: {} },
    ])
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(makeStream(events), { status: 200 }),
    )

    const { start } = renderHook(() => useAgentStream()).result.current
    await start({ message: 'err' } as ChatRequest)

    const s = useChatStore.getState()
    expect(s.error).toContain('LLM timeout')
    // 找到 status=error 的 step
    expect(s.thinking.some((t) => t.status === 'error')).toBe(true)
  })
})