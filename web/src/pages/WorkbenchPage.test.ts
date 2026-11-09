import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkbenchPage from './WorkbenchPage.vue'
import { legacyUrl } from '../app'

const getMock = vi.fn()
const postMock = vi.fn()
vi.mock('../api/client', async (original) => ({ ...await original<typeof import('../api/client')>(), get: (...args: unknown[]) => getMock(...args), post: (...args: unknown[]) => postMock(...args) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
beforeEach(() => { getMock.mockReset(); postMock.mockReset(); localStorage.clear() })

it('creates a saved requirement without starting the automatic workflow', async () => {
  getMock.mockImplementation((url: string) => Promise.resolve(url.startsWith('/api/tickets?') ? [] : { ticket: { key: 'P-1', title: '修改导出' }, runs: [] }))
  postMock.mockResolvedValue({ key: 'P-1', title: '修改导出' })
  const wrapper = mount(WorkbenchPage, { props: { pkey: 'P' } })
  await flushPromises()
  await wrapper.get('.compose input').setValue('修改导出')
  await wrapper.get('textarea').setValue('保留税率规则')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(postMock).toHaveBeenCalledExactlyOnceWith('/api/tickets', { project: 'P', title: '修改导出', body: '保留税率规则', auto: false })
  expect(wrapper.text()).toContain('需求已保存')
  wrapper.unmount()
})

it('keeps the newer run selected when an older request finishes late', async () => {
  let finish: (v: unknown) => void = () => {}
  getMock.mockImplementation((url: string) => {
    if (url.startsWith('/api/tickets?')) return Promise.resolve([{ key: 'P-1', title: '修改导出' }])
    if (url === '/api/tickets/P-1') return Promise.resolve({ ticket: { key: 'P-1', title: '修改导出' }, runs: [{ id: 2, mode: 'plan', status: 'done' }, { id: 1, mode: 'analyze', status: 'done' }] })
    if (url === '/api/runs/1') return new Promise(resolve => { finish = resolve })
    return Promise.resolve({ id: 2, mode: 'plan', status: 'done', result: '最新方案' })
  })
  const wrapper = mount(WorkbenchPage, { props: { pkey: 'P' } })
  await flushPromises()
  await wrapper.findAll('.run')[1]!.trigger('click')
  await wrapper.findAll('.run')[0]!.trigger('click')
  await flushPromises()
  finish({ id: 1, mode: 'analyze', status: 'done', result: '旧分析' })
  await flushPromises()
  expect(wrapper.get('.artifact').text()).toBe('最新方案')
  wrapper.unmount()
})

it('normalizes legacy navigation without duplicate hash prefixes', () => {
  expect(legacyUrl('/#/kb')).toBe('/#/kb')
  expect(legacyUrl('/workspace')).toBe('/#/workspace')
  expect(legacyUrl('#/team/ticket/P-1')).toBe('/#/team/ticket/P-1')
})
