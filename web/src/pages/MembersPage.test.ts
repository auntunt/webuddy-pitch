import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MembersPage from './MembersPage.vue'

const getMock = vi.fn()
const postMock = vi.fn()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, get: (...a: unknown[]) => getMock(...a), post: (...a: unknown[]) => postMock(...a) }
})

describe('MembersPage', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    getMock.mockResolvedValue({ members: [{ name: 'boss', role: 'owner' }, { name: 'ed', role: 'editor' }] })
  })

  it('lists members with roles and gives the owner no change controls', async () => {
    const w = mount(MembersPage)
    await flushPromises()
    expect(w.text()).toContain('boss')
    expect(w.text()).toContain('所有者')
    expect(w.findAll('select').length).toBe(2)
  })

  it('adds a member with the chosen role and sends one request', async () => {
    postMock.mockResolvedValue({ members: [{ name: 'boss', role: 'owner' }] })
    const w = mount(MembersPage)
    await flushPromises()
    const inputs = w.findAll('form.panel input')
    await inputs[0].setValue('newbie')
    await inputs[1].setValue('newbie-pass-1')
    await w.find('form.panel').trigger('submit')
    await flushPromises()
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(postMock.mock.calls[0][1]).toMatchObject({ action: 'add', name: 'newbie', role: 'viewer' })
  })

  it('shows an error and does not resend when an action fails', async () => {
    postMock.mockRejectedValue(new Error('network'))
    const w = mount(MembersPage)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    await flushPromises()
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(w.find('.error').exists()).toBe(true)
  })
})
