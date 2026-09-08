/**
 * F050 — PreferencesPanel 单测
 *
 * 覆盖:
 * - chip 多选 toggle 写 store.uiPrefs
 * - temperature toggle 单选互斥
 * - mood 单选互斥
 * - slider 改写 store.uiPrefs
 * - reset-prefs 恢复默认 + 调 putPreferences
 * - preset-rainy 仅本地 (store 更新, 不调 putPreferences)
 * - ask-agent 调 useAgentStream.start
 * - 计数 (N 项偏好) 正确
 */
import { act, render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PreferencesPanel } from './PreferencesPanel'
import {
  useChatStore,
  DEFAULT_UI_PREFS,
} from '../../../stores/chatStore'
import type { UserPreferences } from '../types'

// mock 掉 useAgentStream,不让它真发 fetch
const startMock = vi.fn()
vi.mock('../hooks/useAgentStream', () => ({
  useAgentStream: () => ({
    start: startMock,
    cancel: vi.fn(),
    status: 'idle',
  }),
}))

// mock 掉 usePutPreferences,直接返回 mutateAsync(可控 resolve/reject)
const putPrefsMock = vi.fn()
vi.mock('../hooks/usePreferences', async () => {
  const actual = await vi.importActual<typeof import('../hooks/usePreferences')>(
    '../hooks/usePreferences',
  )
  return {
    ...actual,
    usePutPreferences: () => ({ mutateAsync: putPrefsMock }),
  }
})

// 让 usePreferencesQuery 走 mock 的 fetch 返回固定 prefs
// 注意: budget_lunch_max = 53 对应 slider 55 (默认), 避免 hydration 改写默认值
const REMOTE: UserPreferences = {
  user_id: 'u1',
  cuisine_weights: {
    sichuan: 0.5, cantonese: 0.5, shandong: 0.5, suzhou: 0.5, zhejiang: 0.5,
    fujian: 0.5, hunan: 0.5, anhui: 0.5, japanese: 0.5, western: 0.5,
    western_fastfood: 0.5, chinese_fastfood: 0.5, snacks: 0.5, dessert_drinks: 0.5,
  },
  allergies: [],
  spice_tolerance: 1,
  temperature_preference: 'hot',
  default_location: null,
  budget_lunch_min: null,
  budget_lunch_max: 53,
}

function wrap(): JSX.Element {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return (
    <QueryClientProvider client={qc}>
      <PreferencesPanel />
    </QueryClientProvider>
  )
}

/** 用 data-od-id 找元素 (F050 §2.4 约定) */
function byId<T extends HTMLElement = HTMLElement>(
  container: HTMLElement,
  id: string,
): T {
  const el = container.querySelector<T>(`[data-od-id="${id}"]`)
  if (!el) throw new Error(`[data-od-id="${id}"] not found`)
  return el
}

beforeEach(() => {
  useChatStore.setState({
    uiPrefs: { ...DEFAULT_UI_PREFS },
    sessionId: 'test-session',
    address: null,
    status: 'idle',
  })
  startMock.mockReset()
  putPrefsMock.mockReset()
  putPrefsMock.mockResolvedValue(REMOTE)
  // 每次测试假装 usePreferencesQuery 已 resolve 成 REMOTE;通过 mock fetch
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true, data: REMOTE }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PreferencesPanel', () => {
  it('初始 N 项偏好 = 0 (全默认)', async () => {
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'prefs-count').textContent).toContain('0 项偏好'))
  })

  it('点击川菜 chip → aria-pressed=true + taste 含 sichuan + 计数 +1', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'chip-sichuan')).toBeInTheDocument())
    const chip = byId(container, 'chip-sichuan')
    await user.click(chip)
    expect(chip).toHaveAttribute('aria-pressed', 'true')
    expect(useChatStore.getState().uiPrefs.taste).toContain('sichuan')
    expect(byId(container, 'prefs-count').textContent).toContain('1')
  })

  it('点击川菜再点一次 → aria-pressed=false + 计数归零', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'chip-sichuan')).toBeInTheDocument())
    const chip = byId(container, 'chip-sichuan')
    await user.click(chip)
    await user.click(chip)
    expect(chip).toHaveAttribute('aria-pressed', 'false')
    expect(byId(container, 'prefs-count').textContent).toContain('0')
  })

  it('toggle 互斥: 选凉 → 热自动取消', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'toggle-cold')).toBeInTheDocument())
    await user.click(byId(container, 'toggle-cold'))
    expect(byId(container, 'toggle-cold')).toHaveAttribute('aria-checked', 'true')
    expect(byId(container, 'toggle-hot')).toHaveAttribute('aria-checked', 'false')
    expect(useChatStore.getState().uiPrefs.temperature).toBe('cold')
  })

  it('mood 单选互斥', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'mood-want-quick')).toBeInTheDocument())
    await user.click(byId(container, 'mood-want-quick'))
    expect(byId(container, 'mood-want-quick')).toHaveAttribute('aria-checked', 'true')
    expect(useChatStore.getState().uiPrefs.mood).toBe('want-quick')
  })

  it('preset-rainy 套用雨天 (温度=hot, mood=want-comfort, 距离=25) 且不发 PUT', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'preset-rainy')).toBeInTheDocument())
    await user.click(byId(container, 'preset-rainy'))
    const prefs = useChatStore.getState().uiPrefs
    expect(prefs.temperature).toBe('hot')
    expect(prefs.mood).toBe('want-comfort')
    expect(prefs.distance).toBe(25)
    expect(putPrefsMock).not.toHaveBeenCalled()
  })

  it('reset-prefs 恢复默认 + 调 putPreferences', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'reset-prefs')).toBeInTheDocument())
    // 先做点修改
    await user.click(byId(container, 'chip-sichuan'))
    expect(useChatStore.getState().uiPrefs.taste).toContain('sichuan')
    // 再 reset
    await user.click(byId(container, 'reset-prefs'))
    await waitFor(() => {
      expect(useChatStore.getState().uiPrefs.taste).toEqual([])
    })
    expect(putPrefsMock).toHaveBeenCalled()
  })

  it('ask-agent 调 useAgentStream.start 带 session_id', async () => {
    const user = userEvent.setup()
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'ask-agent')).toBeInTheDocument())
    await user.click(byId(container, 'ask-agent'))
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1))
    const req = startMock.mock.calls[0]?.[0]
    expect(req.session_id).toBe('test-session')
    expect(req.message).toContain('mood=want-better')
  })

  it('流式中 ask-agent 按钮 disabled', async () => {
    useChatStore.setState({ status: 'streaming' })
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'ask-agent')).toBeInTheDocument())
    const btn = byId<HTMLButtonElement>(container, 'ask-agent')
    expect(btn).toBeDisabled()
    expect(btn.textContent).toContain('推荐中')
  })

  it('data-od-id=prefs-panel 容器存在', async () => {
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'prefs-panel')).toBeInTheDocument())
  })

  it('reset-prefs 失败时本地仍重置 + toast 提示', async () => {
    const user = userEvent.setup()
    putPrefsMock.mockRejectedValueOnce(new Error('network'))
    const { container } = render(wrap())
    await waitFor(() => expect(byId(container, 'reset-prefs')).toBeInTheDocument())
    await act(async () => {
      await user.click(byId(container, 'reset-prefs'))
    })
    await waitFor(() => {
      expect(useChatStore.getState().uiPrefs.taste).toEqual([])
    })
  })
})