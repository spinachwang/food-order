import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getPreferences, putPreferences } from './api-client'

describe('api-client envelope handling', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('returns data field on ok envelope', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          data: {
            user_id: 'u1',
            cuisine_weights: { sichuan: 0.8 },
            allergies: [],
            spice_tolerance: 0,
            temperature_preference: 'room',
            default_location: null,
            budget_lunch_min: null,
            budget_lunch_max: null,
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const prefs = await getPreferences()
    expect(prefs.user_id).toBe('u1')
    expect(prefs.cuisine_weights.sichuan).toBe(0.8)
  })

  it('passes credentials: include on every request', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, data: {} }), { status: 200 }),
    )
    globalThis.fetch = fetchSpy
    await getPreferences()
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/preferences',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('serializes PUT body as JSON and sets Content-Type', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, data: {} }), { status: 200 }),
    )
    globalThis.fetch = fetchSpy
    await putPreferences({
      cuisine_weights: { sichuan: 1 },
      allergies: ['peanut'],
      spice_tolerance: 2,
      temperature_preference: 'hot',
      default_location: '上海',
      budget_lunch_min: 20,
      budget_lunch_max: 60,
    })
    const [url, init] = fetchSpy.mock.calls[0]!
    expect(url).toBe('/api/v1/preferences')
    expect((init as RequestInit).method).toBe('PUT')
    expect((init as RequestInit).headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      allergies: ['peanut'],
      temperature_preference: 'hot',
    })
  })

  it('throws ApiError with code/message on error envelope (400)', async () => {
    globalThis.fetch = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            ok: false,
            error: { code: 'INVALID_TEMPERATURE', message: 'bad temperature' },
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    await expect(getPreferences()).rejects.toBeInstanceOf(ApiError)
    await expect(getPreferences()).rejects.toMatchObject({
      code: 'INVALID_TEMPERATURE',
      status: 400,
    })
  })

  it('throws ApiError with HTTP_ERROR when 500 has no envelope', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    )
    await expect(getPreferences()).rejects.toMatchObject({
      code: 'HTTP_ERROR',
      status: 500,
    })
  })

  it('throws ApiError with BAD_ENVELOPE on 200 with malformed body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('not json', { status: 200 }),
    )
    await expect(getPreferences()).rejects.toMatchObject({
      code: 'BAD_ENVELOPE',
      status: 200,
    })
  })
})