import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AssistantPage from './AssistantPage.vue'
const getMock = vi.fn(), postMock = vi.fn()
vi.mock('../api/client', async original => ({ ...await original<typeof import('../api/client')>(), get: (...a: unknown[]) => getMock(...a), post: (...a: unknown[]) => postMock(...a) }))
beforeEach(() => {
  localStorage.clear(); getMock.mockReset(); postMock.mockReset()
  getMock.mockImplementation((url: string) => Promise.resolve(url.endsWith('/sessions') ? { sessions: [{id:1,title:'项目对话'}] } : {session:{id:1,title:'项目对话'}, messages:[]}))
})
it('reuses the request id after a lost receipt', async () => {
  postMock.mockImplementation((url: string) => url.endsWith('/sessions') ? Promise.resolve({id:1,title:'项目对话'}) : Promise.reject(new Error('连接中断')))
  const wrapper = mount(AssistantPage, {props:{pkey:'P'}})
  await flushPromises()
  await wrapper.get('textarea').setValue('整理需求')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const first = postMock.mock.calls.find(call => call[0].endsWith('/assistant'))![1]
  postMock.mockResolvedValue({message:{id:2,role:'assistant',body:'完成',data:{kind:'assistant',state:'done',step:0}},pending:false,step:0})
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(postMock.mock.calls.at(-1)![1]).toEqual(first)
  expect(first.request_id).toBeTruthy()
  expect(wrapper.text()).toContain('完成')
  wrapper.unmount()
})
it('stops an unfinished stored message without starting a model step', async () => {
  getMock.mockImplementation((url: string) => Promise.resolve(url.endsWith('/sessions') ? { sessions:[{id:1,title:'项目对话'}]} : {session:{id:1,title:'项目对话'},messages:[{id:2,role:'assistant',body:'待继续',data:{kind:'assistant',state:'working',step:3}}]}))
  postMock.mockResolvedValue({message:{id:2,role:'assistant',body:'已停止',data:{kind:'assistant',state:'stopped',step:3}},pending:false,step:3})
  const wrapper=mount(AssistantPage,{props:{pkey:'P'}});await flushPromises()
  await wrapper.get('select').setValue('1');await flushPromises()
  await wrapper.findAll('button').find(button=>button.text()==='停止继续处理')!.trigger('click');await flushPromises()
  expect(postMock).toHaveBeenCalledExactlyOnceWith('/api/sessions/1/assistant',{message:2,action:'stop'})
  expect(wrapper.text()).toContain('已停止');wrapper.unmount()
})
