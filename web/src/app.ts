import { reactive } from 'vue'
import { get, post, bindContext, appUrl, tenantBase, ApiError } from './api/client'
import type { Meta, Project } from './api/types'

export interface AppState {
  meta: Meta | null
  projects: Project[]
  project: string
  ready: boolean
  error: string
}

export const app = reactive<AppState>({ meta: null, projects: [], project: '', ready: false, error: '' })

export function legacyUrl(hash: string): string {
  return appUrl('/#' + hash)
}

export async function loadApp() {
  app.error = ''
  try {
    const meta = await get<Meta>('/api/meta')
    app.meta = meta
    bindContext({ token: meta.access?.context_token || '', user: meta.access?.user || meta.user || '' })
    try {
      const list = await get<{ items?: Project[] } | Project[]>('/api/projects')
      app.projects = Array.isArray(list) ? list : list.items || []
    } catch {
      app.projects = []
    }
    app.project = localStorage.getItem('tmh.proj') || app.projects[0]?.key || ''
    app.ready = true
  } catch (e) {
    app.error = e instanceof ApiError ? e.message : '连不上服务器，稍后再试。'
    app.ready = true
  }
}

export function selectProject(key: string) {
  app.project = key
  localStorage.setItem('tmh.proj', key)
}

export function logoutUrl(): string {
  return appUrl('/logout')
}
