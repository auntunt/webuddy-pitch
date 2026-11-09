import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TasksPage from './TasksPage.vue'

const getMock = vi.fn()
const postMock = vi.fn()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, get: (...a: unknown[]) => getMock(...a), post: (...a: unknown[]) => postMock(...a) }
})

describe('TasksPage', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
  })

  it('lists tasks with name, first line and stage', async () => {
    getMock.mockResolvedValue({ items: [{ key: 'TSK-1', title: '切换达梦', stage: 'open', first_line: '当前使用 MySQL' }] })
    const w = mount(TasksPage, { props: { pkey: 'TSK' } })
    await flushPromises()
    expect(w.text()).toContain('切换达梦')
    expect(w.text()).toContain('当前使用 MySQL')
    expect(w.text()).toContain('open')
  })

  it('shows an error instead of an empty list when reading fails', async () => {
    getMock.mockRejectedValue(new Error('boom'))
    const w = mount(TasksPage, { props: { pkey: 'TSK' } })
    await flushPromises()
    expect(w.find('.error').exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
  })

  it('creates a task with the default goal and does not resend on failure', async () => {
    getMock.mockResolvedValue({ items: [] })
    postMock.mockRejectedValue(new Error('network'))
    const w = mount(TasksPage, { props: { pkey: 'TSK' } })
    await flushPromises()
    await w.find('input').setValue('任务A')
    await w.find('textarea').setValue('做事')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(postMock).toHaveBeenCalledTimes(1)
    const sent = postMock.mock.calls[0][1]
    expect(sent.goal).toBe('修改并测试')
    expect(sent.request_id).toBeTruthy()
  })
})
