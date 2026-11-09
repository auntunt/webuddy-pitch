import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AgentsPage from './AgentsPage.vue'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    get: vi.fn().mockResolvedValue({
      executors: [{ name: 'codex', title: 'Codex', engine: 'codex', installed: true, version: '0.166', path: '/bin/codex',
        last_test: { at: '2026-11-10 00:00', ok: false, reason: '未登录' } }],
      usage: { days: 7, by_executor: { codex: { runs: 2, success: 1, success_rate: 0.5, last_used: '2026-11-10 00:00', total_seconds: 90 } } },
    }),
    post: vi.fn(),
  }
})

describe('AgentsPage', () => {
  it('shows installed state, the last test reason and usage without tokens', async () => {
    const w = mount(AgentsPage)
    await flushPromises()
    expect(w.text()).toContain('已安装 0.166')
    expect(w.text()).toContain('不可用')
    expect(w.text()).toContain('未登录')
    expect(w.text()).toContain('成功率 0.5')
    expect(w.text()).not.toMatch(/token/i)
  })
})
