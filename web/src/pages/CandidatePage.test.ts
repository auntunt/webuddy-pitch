import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import CandidatePage from './CandidatePage.vue'
import { ApiError } from '../api/client'
import type { CandidateView } from '../api/types'

const getMock = vi.fn()
const postMock = vi.fn()

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, get: (...a: unknown[]) => getMock(...a), post: (...a: unknown[]) => postMock(...a) }
})

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }
})

function candidateFixture(overrides: Partial<CandidateView> = {}): CandidateView {
  return {
    id: 7,
    ticket: 'E2E-1',
    run_id: 3,
    author: 'devin',
    base_commit: 'a'.repeat(40),
    commit: 'b'.repeat(40),
    criteria: [{ id: 'A1', text: 'render uses configured rate', check: 'test passes' }],
    summary: 'fixed export',
    current: true,
    blocked: [],
    verification: { check: 'pass', checked_commit: 'b'.repeat(40), commands: [{ kind: 'test', command: 'pytest', exit_code: 0, output: 'ok' }], baseline_tests: [{ kind: 'baseline_tests', command: 'pytest base', exit_code: 0 }] },
    verification_passed: true,
    verification_hash: 'vh',
    preview: null,
    preview_ready: false,
    preview_url: '',
    assessment: { results: [{ id: 'A1', status: 'pass', evidence: 'ran it' }] },
    technical_acceptance: true,
    ready_for_human: true,
    missing: [],
    evidence_hash: 'eh',
    human_decision: null,
    human_accepted: false,
    state: 'awaiting_human',
    gate_findings: { tests_added: [], tests_changed: ['tests/test_flow.py'], tests_deleted: [], gate_files: [], weakening: ['tests/test_flow.py：少了 1 处断言'], blocking: true, sha256: 'g' },
    gate_ack: null,
    control_points: [{ name: 'Webuddy 执行的合并', state: 'enforced', why: 'x' }],
    boundary: 'Agent observations are attributed evidence, not human approval.',
    ...overrides,
  }
}

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: CandidatePage }] })
  await router.push('/p/E2E/candidates/7')
  await router.isReady()
  return mount(CandidatePage, { props: { pkey: 'E2E', id: '7' }, global: { plugins: [router] } })
}

describe('CandidatePage', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
  })

  it('shows an error instead of an empty page when the candidate read fails', async () => {
    getMock.mockRejectedValue(new ApiError('没有这个候选', 404))
    const w = await mountPage()
    await vi.waitFor(() => expect(w.text()).toContain('没有这个候选'))
    expect(w.find('.panel').exists()).toBe(false)
  })

  it('renders conclusion, gate block, criteria and verification records', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/candidates/')) return Promise.resolve(candidateFixture())
      if (path.startsWith('/api/team')) return Promise.resolve({ items: [{ ticket: { key: 'E2E-1' }, assignment: { assignee: 'dev', reviewer: 'rev', revision: 1 }, candidate: { id: 7 } }] })
      return Promise.reject(new ApiError('unexpected ' + path, 404))
    })
    const w = await mountPage()
    await vi.waitFor(() => expect(w.text()).toContain('候选 #7'))
    expect(w.text()).toContain('门禁相关变更')
    expect(w.text()).toContain('少了 1 处断言')
    expect(w.text()).toContain('逐项结果')
    expect(w.text()).toContain('基线对照')
    expect(w.text()).toContain('Webuddy 执行的合并')
    expect(w.find('textarea').exists()).toBe(true) // ack form only while unacknowledged
  })

  it('hides the ack form once the gate is acknowledged', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/candidates/')) return Promise.resolve(candidateFixture({ gate_ack: { actor: 'op', reason: 'ok', created: 'now' } }))
      if (path.startsWith('/api/team')) return Promise.resolve({ items: [] })
      return Promise.reject(new ApiError('unexpected ' + path, 404))
    })
    const w = await mountPage()
    await vi.waitFor(() => expect(w.text()).toContain('候选 #7'))
    expect(w.text()).toContain('门禁相关变更')
    expect(w.find('textarea').exists()).toBe(false)
    expect(w.text()).toContain('已由 op 确认')
  })
})
