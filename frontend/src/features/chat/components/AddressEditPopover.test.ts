/**
 * F050 — AddressEditPopover 单测 (prompt 触发与 store 写入)
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { editAddress, DEFAULT_ADDRESS } from './AddressEditPopover'
import { useChatStore } from '../../../stores/chatStore'

afterEach(() => {
  vi.restoreAllMocks()
  useChatStore.setState({
    address: DEFAULT_ADDRESS,
    locationOverride: null,
  })
})

describe('editAddress', () => {
  it('用户输入非空 → 写入 store 并返回新地址', () => {
    useChatStore.setState({ address: DEFAULT_ADDRESS })
    vi.spyOn(window, 'prompt').mockReturnValue('中关村 · 鼎好大厦')
    const out = editAddress()
    expect(out).toBe('中关村 · 鼎好大厦')
    expect(useChatStore.getState().address).toBe('中关村 · 鼎好大厦')
  })

  it('用户取消 (prompt 返回 null) → 不写 store 并返回 null', () => {
    useChatStore.setState({ address: '三元桥' })
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    const out = editAddress()
    expect(out).toBeNull()
    expect(useChatStore.getState().address).toBe('三元桥')
  })

  it('用户输入空字符串 → 回退默认地址', () => {
    useChatStore.setState({ address: '国贸' })
    vi.spyOn(window, 'prompt').mockReturnValue('   ')
    const out = editAddress()
    expect(out).toBe(DEFAULT_ADDRESS)
    expect(useChatStore.getState().address).toBe(DEFAULT_ADDRESS)
  })

  it('默认提示文本带当前地址', () => {
    useChatStore.setState({ address: '国贸' })
    const spy = vi.spyOn(window, 'prompt').mockReturnValue(null)
    editAddress()
    expect(spy).toHaveBeenCalledWith('更新你现在在的位置', '国贸')
  })
})