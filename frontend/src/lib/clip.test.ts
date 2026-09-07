import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { copyToClipboard, isClipboardApiAvailable } from './clip'

describe('isClipboardApiAvailable', () => {
  beforeEach(() => {
    // jsdom 默认 window.isSecureContext = false, 但我们 mock navigator.clipboard
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
    })
  })

  afterEach(() => {
    delete (navigator as { clipboard?: unknown }).clipboard
  })

  it('returns true when navigator.clipboard.writeText is a function in secure context', () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn() },
      configurable: true,
    })
    expect(isClipboardApiAvailable()).toBe(true)
  })

  it('returns false when navigator.clipboard is missing', () => {
    expect(isClipboardApiAvailable()).toBe(false)
  })

  it('returns false when window is not secure context', () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn() },
      configurable: true,
    })
    expect(isClipboardApiAvailable()).toBe(false)
  })
})

describe('copyToClipboard', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
    })
  })

  afterEach(() => {
    delete (navigator as { clipboard?: unknown }).clipboard
    vi.restoreAllMocks()
  })

  it('uses navigator.clipboard.writeText in secure context', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const ok = await copyToClipboard('hello')
    expect(ok).toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
  })

  it('falls back to execCommand when clipboard.writeText rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('permission denied'))
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    const execSpy = vi.spyOn(document, 'execCommand').mockReturnValue(true)
    const ok = await copyToClipboard('fallback text')
    expect(ok).toBe(true)
    expect(execSpy).toHaveBeenCalledWith('copy')
    // 临时 textarea 已被清理
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('returns false when both paths fail', async () => {
    // 无 clipboard API + execCommand 抛错
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
    const execSpy = vi.spyOn(document, 'execCommand').mockImplementation(() => {
      throw new Error('not allowed')
    })
    const ok = await copyToClipboard('nope')
    expect(ok).toBe(false)
    expect(execSpy).toHaveBeenCalled()
  })
})