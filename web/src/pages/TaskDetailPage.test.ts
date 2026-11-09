import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TaskDetailPage from './TaskDetailPage.vue'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, get: vi.fn().mockResolvedValue({ ticket: { key: 'TSK-1', title: '切换达梦', body: '当前使用 MySQL', status: 'open' } }) }
})

describe('TaskDetailPage', () => {
  it('shows the task and the three read-only download links', async () => {
    const w = mount(TaskDetailPage, { props: { pkey: 'TSK', tkey: 'TSK-1' } })
    await flushPromises()
    expect(w.text()).toContain('切换达梦')
    const hrefs = w.findAll('a.btn').map((a) => a.attributes('href'))
    expect(hrefs).toEqual([
      '/api/projects/TSK/tasks/TSK-1/return/patch',
      '/api/projects/TSK/tasks/TSK-1/return/files',
      '/api/projects/TSK/tasks/TSK-1/return/archive',
    ])
  })
})
