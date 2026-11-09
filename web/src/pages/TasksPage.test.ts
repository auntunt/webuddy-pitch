import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TasksPage from './TasksPage.vue'

const getMock = vi.fn()
const executorsReply = { executors: [{ name: 'codex', title: 'Codex', available: true, last_ok: true, models: ['gpt-6-astra'] }], default_agent: 'codex', default_model: 'gpt-6-astra' }
function getByPath(path: string) {
  if (path.includes('/task-executors')) return Promise.resolve(executorsReply)
  return getMock(path)
}
const postMock = vi.fn()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, get: (...a: unknown[]) => getByPath(a[0] as string), post: (...a: unknown[]) => postMock(...a) }
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

describe('TasksPage environment rows', () => {
  it('adds and removes rows and sends only named secrets, with the value field as password', async () => {
    getMock.mockResolvedValue({ items: [] })
    postMock.mockResolvedValue({ key: 'TSK-2', goal: '修改并测试', secret_names: ['db_host'] })
    const w = mount(TasksPage, { props: { pkey: 'TSK' } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '添加一项')!.trigger('click')
    await w.findAll('button').find((b) => b.text() === '添加一项')!.trigger('click')
    expect(w.findAll('input[type=password]').length).toBe(2)
    const names = w.findAll('input').filter((i) => i.attributes('aria-label') === '名称')
    await names[0].setValue('db_host')
    await names[1].setValue('')
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    await w.find('input').setValue('任务B')
    await w.find('textarea').setValue('做事')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(postMock.mock.calls[0][1].secrets).toEqual([])
  })
})

describe('TasksPage executor and model', () => {
  it('sends the chosen executor and model with the task', async () => {
    getMock.mockResolvedValue({ items: [] })
    postMock.mockResolvedValue({ key: 'TSK-3', goal: '出方案', secret_names: [] })
    const w = mount(TasksPage, { props: { pkey: 'TSK' } })
    await flushPromises()
    const selects = w.findAll('select')
    expect(selects.length).toBeGreaterThanOrEqual(3)
    await w.find('input').setValue('切换')
    await w.find('textarea').setValue('出方案')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(postMock.mock.calls[0][1]).toHaveProperty('agent')
    expect(postMock.mock.calls[0][1]).toHaveProperty('model')
  })
})
