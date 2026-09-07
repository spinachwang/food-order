/**
 * F050 — 剪贴板写入
 *
 * 主路径: navigator.clipboard.writeText (HTTPS / localhost / secure context)
 * 降级路径: document.execCommand('copy') + 临时 textarea (旧浏览器 / 非 secure)
 *
 * 不在主路径 catch execCommand — 调用方按 boolean 判定成功, 失败时自行 toast。
 */

/** Feature detect: 现代 Clipboard API 是否可用 */
export function isClipboardApiAvailable(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof navigator.clipboard !== 'undefined' &&
    typeof navigator.clipboard.writeText === 'function' &&
    // secure context 才有 clipboard API (HTTPS / localhost)
    (typeof window !== 'undefined' ? window.isSecureContext : true)
  )
}

/**
 * Copy a text string to the system clipboard.
 * @returns true on success, false if both paths failed.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (isClipboardApiAvailable()) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限拒绝 / page blur 等 → 走降级
    }
  }
  return legacyCopy(text)
}

/** 旧版 execCommand 降级 — 返回 boolean 表示是否成功 */
function legacyCopy(text: string): boolean {
  if (typeof document === 'undefined') return false
  const textarea = document.createElement('textarea')
  textarea.value = text
  // 离开视口避免 iOS Safari 自动聚焦弹键盘
  textarea.style.position = 'fixed'
  textarea.style.top = '0'
  textarea.style.left = '0'
  textarea.style.opacity = '0'
  textarea.setAttribute('readonly', 'true')
  document.body.appendChild(textarea)
  textarea.select()
  textarea.setSelectionRange(0, text.length)

  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(textarea)
  return ok
}