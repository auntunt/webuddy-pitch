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

it('preserves the original request and adds explicit operations criteria without running it', async () => {
  getMock.mockImplementation((url:string)=>Promise.resolve(url.startsWith('/api/tickets?')?[]:{ticket:{key:'P-1',title:'金额单位排查',type:'ops',body:'原文'},team_assignment:{assignee:'工程师',reviewer:'复核人'},stage:{label:'待核对'},runs:[]}))
  postMock.mockResolvedValue({key:'P-1',title:'金额单位排查'})
  const wrapper=mount(WorkbenchPage,{props:{pkey:'P'}});await flushPromises()
  await wrapper.get('.compose input').setValue('金额单位排查')
  await wrapper.get('.compose select').setValue('ops')
  await wrapper.findAll('.compose textarea')[0]!.setValue('客户原话：显示金额不对，不确定原因。')
  await wrapper.findAll('.compose textarea')[1]!.setValue('页面与导出单位一致\n核对原始数据')
  await wrapper.get('form').trigger('submit');await flushPromises()
  expect(postMock).toHaveBeenCalledExactlyOnceWith('/api/tickets',{project:'P',title:'金额单位排查',type:'ops',auto:false,body:'客户原话：显示金额不对，不确定原因。\n\n## 验收标准（提单人填写）\n- A1 页面与导出单位一致\n- A2 核对原始数据'})
  expect(wrapper.get('[aria-label="处理与交接"]').text()).toContain('工程师')
  expect(wrapper.get('[aria-label="处理与交接"]').text()).toContain('复核人')
  wrapper.unmount()
})

it('continues from a comment and reuses its request id after a lost reply', async () => {
  getMock.mockImplementation((url:string)=>Promise.resolve(url.startsWith('/api/tickets?')?[{key:'P-1',title:'修复'}]:{ticket:{key:'P-1',title:'修复'},runs:[]}))
  postMock.mockRejectedValueOnce(new Error('connection lost')).mockResolvedValue({ok:true,run:7})
  const wrapper=mount(WorkbenchPage,{props:{pkey:'P'}});await flushPromises()
  await wrapper.get('.discussion textarea').setValue('按评论继续')
  await wrapper.get('.discussion').trigger('submit');await flushPromises()
  const first=postMock.mock.calls[0]!
  expect(first[0]).toBe('/api/tickets/P-1/comments')
  expect(first[1]).toMatchObject({body:'按评论继续',continue:true,request_id:expect.any(String)})
  expect((wrapper.get('.discussion textarea').element as HTMLTextAreaElement).value).toBe('按评论继续')
  await wrapper.get('.discussion').trigger('submit');await flushPromises()
  expect(postMock.mock.calls[1]).toEqual(first)
  expect(wrapper.text()).toContain('评论已发送，智能体已继续执行')
  wrapper.unmount()
})
