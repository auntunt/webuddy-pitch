import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, bindContext, appUrl, tenantBase, requestId } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    bindContext({ token: '', user: '' })
    window.history.pushState({}, '', '/next/p/E2E/verify')
  })

  it('sends X-TMH and JSON body on POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    bindContext({ user: 'alice' })
    await api('POST', '/api/team', { action: 'candidate_resolve' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/team')
    const headers = init.headers as Record<string, string>
    expect(headers['X-TMH']).toBe('1')
    expect(headers['Content-Type']).toBe('application/json')
    expect(headers['X-TMH-User']).toBe('alice')
    expect(init.body).toBe(JSON.stringify({ action: 'candidate_resolve' }))
  })

  it('sends X-Webuddy-Context when a tenant context token is bound', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    bindContext({ token: 'ctx-1' })
    await api('GET', '/api/meta')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['X-Webuddy-Context']).toBe('ctx-1')
  })

  it('prefixes API paths with the tenant base under /t/<id>/', async () => {
    window.history.pushState({}, '', '/t/acme/next/p/E2E/verify')
    expect(tenantBase()).toBe('/t/acme')
    expect(appUrl('/api/meta')).toBe('/t/acme/api/meta')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    await api('GET', '/api/meta')
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/t/acme/api/meta')
    window.history.pushState({}, '', '/next/p/E2E/verify')
  })

  it('maps server error shape to ApiError with status and code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { error: '候选已过期', code: 'stale' })))
    const err = await api('GET', '/api/candidates/1').catch((e: unknown) => e) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.code).toBe('stale')
    expect(err.message).toBe('候选已过期')
  })

  it('uses the HTTPMSG fallback for statuses without a server message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, {})))
    const err = await api('GET', '/api/x').catch((e: unknown) => e) as ApiError
    expect(err.status).toBe(403)
    expect(err.message).toContain('没有权限')
  })

  it('never retries a failed write', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network down'))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api('POST', '/api/team', { action: 'candidate_submit' })).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not retry a failed read either', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network down'))
    vi.stubGlobal('fetch', fetchMock)
    await expect(api('GET', '/api/meta')).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('maps fetch rejection to a connectivity ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    const err = await api('GET', '/api/meta').catch((e: unknown) => e) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.message).toContain('连不上服务器')
  })

  it('requestId produces unique values', () => {
    expect(requestId()).not.toBe(requestId())
  })
})
