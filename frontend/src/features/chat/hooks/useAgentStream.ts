/**
 * F050 — useAgentStream hook
 *
 * 职责: POST /api/v1/agent/chat (SSE), 解析事件流, 写入 chatStore。
 *
 * 调用方式:
 *   const { start, cancel, status } = useAgentStream()
 *   await start({ message: '今天想吃辣的', location_override: '...' })
 *
 * 状态机 (chatStore.status):
 *   idle → streaming → done | error
 *
 * SSE 事件 → store 映射 (见 F004 §4 + F050 §2.3):
 *   cuisine_selected   → selectedCuisines / routingReason + thinking step 1
 *   cuisine_result     → cuisineResultsByCuisine + per-cuisine thinking step
 *   restaurant_found   → restaurantListsByCuisine + thinking step
 *   weather            → weather + thinking step
 *   recommendation     → recommendation + thinking step
 *   error              → error field + error step
 *   done               → status='done' + markLastThinkingDone()
 *
 * 中断 (无 done): status='error' + 追加 ⚠️ 流式中断 红步。
 */
import { useCallback, useRef } from 'react'
import { parseSseStream, type SseFrame } from '../../../lib/sse'
import { useChatStore } from '../../../stores/chatStore'
import type {
  ChatRequest,
  CuisineExpertOutput,
  CuisineId,
  Recommendation,
  Restaurant,
  WeatherInfo,
} from '../types'

export interface AgentStreamApi {
  start: (req: ChatRequest) => Promise<void>
  cancel: () => void
  status: 'idle' | 'streaming' | 'done' | 'error'
}

export function useAgentStream(): AgentStreamApi {
  const status = useChatStore((s) => s.status)
  const abortRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const start = useCallback(async (req: ChatRequest) => {
    const store = useChatStore.getState()
    store.reset()
    store.setStatus('streaming')
    // 起始 thinking step
    store.appendThinking({
      title: '读取偏好与忌口',
      em: '加载你的口味与温度偏好',
      status: 'pending',
    })

    const ctrl = new AbortController()
    abortRef.current = ctrl

    let res: Response
    try {
      res = await fetch('/api/v1/agent/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      })
    } catch (err: unknown) {
      // 网络错误 / 中断
      const msg = err instanceof Error ? err.message : 'unknown network error'
      useChatStore.setState((s) => {
        const thinking = s.thinking.slice()
        const last = thinking.length > 0 ? thinking[thinking.length - 1]! : null
        if (last && last.status === 'pending') {
          thinking[thinking.length - 1] = { ...last, status: 'error' }
        }
        return {
          status: 'error',
          error: msg,
          thinking: [
            ...thinking,
            { marker: thinking.length + 1, title: '⚠️ 网络中断', em: msg, status: 'error' },
          ],
        }
      })
      return
    }

    if (!res.ok || !res.body) {
      const code = res.status
      useChatStore.setState({
        status: 'error',
        error: `HTTP ${code}`,
      })
      return
    }

    let sawDone = false
    try {
      for await (const frame of parseSseStream(res.body.getReader() as ReadableStreamDefaultReader<Uint8Array>)) {
        if (ctrl.signal.aborted) break
        dispatchFrame(frame)
        if (frame.event === 'done') sawDone = true
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'stream parse error'
      useChatStore.getState().setError(msg)
    }

    if (!sawDone && !ctrl.signal.aborted) {
      // 流式中断 — 追加红步 + status=error
      useChatStore.setState((s) => {
        const thinking = [...s.thinking]
        const last = thinking.length > 0 ? thinking[thinking.length - 1]! : null
        if (last && last.status === 'pending') {
          thinking[thinking.length - 1] = { ...last, status: 'error' }
        }
        thinking.push({
          marker: thinking.length + 1,
          title: '⚠️ 流式中断',
          em: 'agent 还没说完，请稍后再试',
          status: 'error',
        })
        return { status: 'error', error: 'stream interrupted', thinking }
      })
    } else if (sawDone) {
      useChatStore.getState().markLastThinkingDone()
      useChatStore.getState().setStatus('done')
    }

    abortRef.current = null
  }, [])

  return { start, cancel, status }
}

// ---- frame dispatcher ----

function dispatchFrame(frame: SseFrame): void {
  const store = useChatStore.getState()
  switch (frame.event) {
    case 'cuisine_selected': {
      const { cuisines, routing_reason } = frame.data as {
        cuisines: CuisineId[]
        routing_reason: string
      }
      store.setSelectedCuisines(cuisines, routing_reason)
      store.appendThinking({
        title: `已路由到 ${cuisines.length} 个菜系: ${cuisines.join(' / ')}`,
        em: routing_reason,
        status: 'done',
      })
      // 新一轮 pending step
      store.appendThinking({
        title: '菜系专家并行分析中…',
        em: '等待各 cuisine Node 返回结论',
        status: 'pending',
      })
      return
    }
    case 'cuisine_result': {
      const { results } = frame.data as {
        results: Partial<Record<CuisineId, CuisineExpertOutput>>
      }
      store.setCuisineResults(results)
      const ids = Object.keys(results) as CuisineId[]
      ids.forEach((id) => {
        store.appendThinking({
          title: `${id} 专家结论: ${results[id]?.conclusion ?? '(空)'}`,
          em: `关键词: ${(results[id]?.keywords ?? []).join(', ')}`,
          status: 'done',
          cuisine_id: id,
        })
      })
      return
    }
    case 'restaurant_found': {
      const { restaurant_lists } = frame.data as {
        restaurant_lists: Partial<Record<CuisineId, Restaurant[]>>
      }
      store.setRestaurantLists(restaurant_lists)
      const ids = Object.keys(restaurant_lists) as CuisineId[]
      ids.forEach((id) => {
        const list = restaurant_lists[id] ?? []
        store.appendThinking({
          title: `拉取 ${list.length} 家店 · ${id}`,
          em: list.length === 0 ? '该菜系无 POI' : `前 3: ${list.slice(0, 3).map((r) => r.name).join(', ')}`,
          status: 'done',
          cuisine_id: id,
        })
      })
      store.appendThinking({
        title: '获取实时天气…',
        em: 'AMAP 天气查询',
        status: 'pending',
      })
      return
    }
    case 'weather': {
      const { weather } = frame.data as { weather: WeatherInfo | null }
      store.setWeather(weather)
      if (weather) {
        store.appendThinking({
          title: `天气信号注入 · ${weather.temperature_celsius.toFixed(0)}° ${conditionLabel(weather.condition)}`,
          em: `湿度 ${weather.humidity_percent}% · 降水概率 ${(weather.precipitation_probability * 100).toFixed(0)}%`,
          status: 'done',
        })
      } else {
        store.appendThinking({
          title: '天气暂不可用',
          em: 'F040 按默认决策走',
          status: 'error',
        })
      }
      store.appendThinking({
        title: '重排序 · 输出 Top 3',
        em: 'SummaryAgent 聚合',
        status: 'pending',
      })
      return
    }
    case 'recommendation': {
      const { recommendation } = frame.data as { recommendation: Recommendation | null }
      store.setRecommendation(recommendation)
      store.appendThinking({
        title: recommendation
          ? `主推: ${recommendation.headline}`
          : '今日无合适推荐',
        em: recommendation
          ? `置信度 ${(recommendation.confidence * 100).toFixed(0)}% · ${recommendation.order_takeout ? '外卖' : '到店'}`
          : 'F040 降级输出',
        status: 'done',
      })
      return
    }
    case 'error': {
      const { message } = frame.data as { code: string; message: string }
      store.setError(message)
      store.appendThinking({
        title: '✗ agent 出错',
        em: message,
        status: 'error',
      })
      return
    }
    case 'done': {
      store.markLastThinkingDone()
      store.setStatus('done')
      return
    }
    default:
      // 未知事件 — 忽略
      return
  }
}

function conditionLabel(c: WeatherInfo['condition']): string {
  switch (c) {
    case 'sunny': return '晴'
    case 'cloudy': return '多云'
    case 'rainy': return '雨'
    case 'snowy': return '雪'
    case 'foggy': return '雾'
    case 'dust': return '沙尘'
  }
}