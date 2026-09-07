import { describe, expect, it } from 'vitest'
import { parseSseBlock, parseSseChunk } from './sse'

describe('parseSseBlock', () => {
  it('parses a single event with one-line data', () => {
    const block = 'event: foo\ndata: {"a":1}\n'
    expect(parseSseBlock(block)).toEqual({ event: 'foo', data: { a: 1 } })
  })

  it('joins multiple data lines with \\n (SSE spec)', () => {
    // 后端永远单行 JSON, 这里只验证 spec 层行为: 多行 data 用 \n 拼接。
    // 拼接结果是 "line1\nline2" — 不是合法 JSON, parseSseBlock 因此返回 null。
    const block = 'event: foo\ndata: line1\ndata: line2\n'
    expect(parseSseBlock(block)).toBeNull()
  })

  it('strips single leading space after colon', () => {
    const block = 'event: foo\ndata:  {"a":1}  \n'
    // SSE spec: 第一个空格剥离, 之后保留 (这里第二个空格在 JSON 内部无影响)
    expect(parseSseBlock(block)).toEqual({ event: 'foo', data: { a: 1 } })
  })

  it('skips comment lines starting with colon', () => {
    const block = ': heartbeat\nevent: foo\ndata: 1\n'
    expect(parseSseBlock(block)).toEqual({ event: 'foo', data: 1 })
  })

  it('returns null when event line missing', () => {
    expect(parseSseBlock('data: {"a":1}\n')).toBeNull()
  })

  it('returns null when JSON malformed', () => {
    expect(parseSseBlock('event: foo\ndata: {not-json}\n')).toBeNull()
  })

  it('parses UTF-8 Chinese content', () => {
    const block = 'event: recommendation\ndata: {"headline":"今天吃火锅","confidence":0.9}\n'
    expect(parseSseBlock(block)).toEqual({
      event: 'recommendation',
      data: { headline: '今天吃火锅', confidence: 0.9 },
    })
  })

  it('returns null on empty block', () => {
    expect(parseSseBlock('')).toBeNull()
    expect(parseSseBlock('\n')).toBeNull()
  })
})

describe('parseSseChunk', () => {
  it('extracts one full frame, buffers partial tail', () => {
    const chunk = 'event: foo\ndata: {"a":1}\n\nevent: bar\ndata'
    const { frames, rest } = parseSseChunk(chunk, '')
    expect(frames).toEqual([{ event: 'foo', data: { a: 1 } }])
    expect(rest).toBe('event: bar\ndata')
  })

  it('concatenates incoming chunk with prior rest', () => {
    const { rest: rest1 } = parseSseChunk('event: foo\ndata', '')
    const { frames } = parseSseChunk(':{"a":1}\n\n', rest1)
    expect(frames).toEqual([{ event: 'foo', data: { a: 1 } }])
  })

  it('handles multiple complete frames in one chunk', () => {
    const chunk =
      'event: a\ndata: 1\n\nevent: b\ndata: 2\n\nevent: c\ndata: 3\n\n'
    const { frames } = parseSseChunk(chunk, '')
    expect(frames).toHaveLength(3)
    expect(frames[0]).toEqual({ event: 'a', data: 1 })
    expect(frames[2]).toEqual({ event: 'c', data: 3 })
  })

  it('skips malformed frames silently', () => {
    const chunk = 'garbage\nevent: ok\ndata: {"x":1}\n\nmore garbage\n\n'
    const { frames } = parseSseChunk(chunk, '')
    expect(frames).toEqual([{ event: 'ok', data: { x: 1 } }])
  })
})