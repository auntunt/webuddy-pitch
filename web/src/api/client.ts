export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = '') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export interface ApiContext {
  token: string
  user: string
}

const HTTPMSG: Record<number, string> = {
  401: '登录已过期，刷新页面重新登录。',
  403: '没有权限做这一步，需要的话找管理员开通。',
  404: '要找的内容不存在，可能已被删除或改名。',
  413: '文件太大了，换小一点的再试。',
  429: '操作太频繁，稍等一下再试。',
  500: '服务器出错了，这一步没有完成。刷新看看结果再决定要不要重试；一直这样请告诉管理员。',
  502: '服务器暂时不可用，稍后再试。',
  503: '服务器暂时不可用，稍后再试。',
  504: '服务器响应超时，稍后再试；如果是长任务，它可能还在后台跑。',
}

let context: ApiContext = { token: '', user: '' }

export function bindContext(next: Partial<ApiContext>) {
  context = { ...context, ...next }
}

export function tenantBase(): string {
  const m = window.location.pathname.match(/^\/t\/[A-Za-z0-9_-]+/)
  return m ? m[0] : ''
}

export function appUrl(path: string): string {
  return tenantBase() + path
}

export async function api<T = unknown>(method: string, path: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { 'X-TMH': '1', ...extraHeaders }
  if (context.user) headers['X-TMH-User'] = encodeURIComponent(context.user)
  if (context.token) headers['X-Webuddy-Context'] = context.token
  const init: RequestInit = { method, headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let r: Response
  try {
    r = await fetch(appUrl(path), init)
  } catch {
    throw new ApiError(navigator.onLine === false ? '网络断了，连上后再试。' : '连不上服务器：可能是网络问题，或服务没在运行。稍后再试。', 0)
  }
  let j: Record<string, unknown> = {}
  try {
    j = (await r.json()) as Record<string, unknown>
  } catch {
    j = {}
  }
  if (!r.ok) {
    const message = typeof j.error === 'string' && r.status !== 401 ? j.error : HTTPMSG[r.status] || HTTPMSG[Math.floor(r.status / 100) * 100] || `出错了（${r.status}），稍后再试。`
    throw new ApiError(message, r.status, typeof j.code === 'string' ? j.code : '')
  }
  return j as T
}

export const get = <T = unknown>(path: string) => api<T>('GET', path)
export const post = <T = unknown>(path: string, body?: unknown, headers?: Record<string, string>) => api<T>('POST', path, body ?? {}, headers)

export function requestId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `r-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}
