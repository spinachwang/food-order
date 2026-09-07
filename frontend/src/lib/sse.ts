/**
 * F050 — SSE (text/event-stream) 解析器
 *
 * 与后端 `backend/app/api/v1/agent.py` 帧格式对齐:
 *   event: <name>\n
 *   data: <json>\n
 *   \n
 *
 * 解析行为:
 * - 缺 `event:` 行的帧视为非法, 跳过 (与 backend _frame_from_event 容错一致)
 * - 多行 `data:` 按 SSE spec 拼接 (用 \n), 再 JSON.parse
 * - 空行是帧分隔符
 * - 注释行 (`:` 开头) 跳过
 *
 * 暴露为 async iterable (for await ... of parseSseStream(reader)),
 * 上层 hooks (useAgentStream) 把事件分发到 store。
 */
import type { SseEventName, SseEventPayload } from '../features/chat/types'

export interface SseFrame<K extends SseEventName = SseEventName> {
  event: K
  data: SseEventPayload<K>
}

/** Parse a single SSE message block (one or more `key: value` lines + blank). */
export function parseSseBlock(block: string): SseFrame | null {
  const lines = block.split('\n')
  let eventName: string | null = null
  const dataLines: string[] = []

  for (const rawLine of lines) {
    if (rawLine === '') continue
    // 注释行 — SSE spec 允许 `: comment`
    if (rawLine.startsWith(':')) continue

    const colonAt = rawLine.indexOf(':')
    if (colonAt === -1) continue

    const field = rawLine.slice(0, colonAt)
    let value = rawLine.slice(colonAt + 1)
    // spec: leading single space after colon is stripped
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') {
      eventName = value
    } else if (field === 'data') {
      dataLines.push(value)
    }
    // 其它 field (id / retry) 暂不消费
  }

  if (eventName === null) return null

  const joinedData = dataLines.join('\n')
  let parsed: unknown
  try {
    parsed = JSON.parse(joinedData)
  } catch {
    // 非法 JSON 帧 — 跳过
    return null
  }

  return {
    event: eventName as SseEventName,
    data: parsed as SseEventPayload<SseEventName>,
  }
}

/**
 * Parse a full UTF-8 chunk (decoded by caller) into zero or more SSE frames.
 * Handles partial frames across chunks by buffering incomplete tail.
 *
 * Returns the parsed frames AND the trailing incomplete buffer (caller appends
 * next chunk and re-calls).
 */
export function parseSseChunk(
  chunk: string,
  buffer: string,
): { frames: SseFrame[]; rest: string } {
  const combined = buffer + chunk
  // SSE 帧分隔符: 一个或多个连续 \n\n (允许 \r\n\r\n 与 \n\n 兼容)
  // 我们按 "\n\n" 切; 余下不足一帧的部分留在 rest。
  const parts = combined.split('\n\n')
  const rest = parts.pop() ?? ''
  const frames: SseFrame[] = []
  for (const block of parts) {
    if (block.trim() === '') continue
    const parsed = parseSseBlock(block)
    if (parsed) frames.push(parsed)
  }
  return { frames, rest }
}

/**
 * 把一个 ReadableStream<Uint8Array> 包装成 async iterable<SseFrame>.
 *
 * 由 useAgentStream 在 fetch 拿到 Response 后调用, 实现流式监听。
 */
export async function* parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SseFrame, void, void> {
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) {
      // 流结束 — flush buffer (可能末尾还有一帧无 trailing newline)
      if (buffer.trim() !== '') {
        const final = parseSseBlock(buffer)
        if (final) yield final
      }
      return
    }
    const text = decoder.decode(value, { stream: true })
    const { frames, rest } = parseSseChunk(text, buffer)
    buffer = rest
    for (const frame of frames) yield frame
  }
}