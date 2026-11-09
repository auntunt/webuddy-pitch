<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get, post, requestId, ApiError } from '../api/client'
import type { CandidateView, TeamItem, TeamActionResult, ReportManifest, ReportSegment } from '../api/types'

const props = defineProps<{ pkey: string; id: string }>()
const router = useRouter()

const candidate = ref<CandidateView | null>(null)
const team = ref<TeamItem | null>(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref('')
const ackReason = ref('')
const reportProgress = ref('')
let poll: ReturnType<typeof setInterval> | null = null

const STATE_LABEL: Record<string, string> = {
  accepted: '已验收',
  stale: '已过期',
  awaiting_human: '待人工决定',
  needs_verification: '需要验证',
}
const CHECK_LABEL: Record<string, string> = { pass: '通过', fail: '失败', skip: '跳过', blocked: '受阻' }
const RESULT_LABEL: Record<string, string> = { pass: '通过', fail: '不通过', unknown: '未验证' }
const GATE_STATE: Record<string, string> = { enforced: '实际生效', advisory_only: '仅建议', not_connected: '未接入' }

const stateLabel = computed(() => {
  const c = candidate.value
  if (!c) return ''
  if (!c.current) return '已过期'
  return STATE_LABEL[c.state] || c.state
})
const stateTone = computed(() => {
  const c = candidate.value
  if (!c) return ''
  if (c.state === 'accepted') return 'tag-good'
  if (!c.current || c.state === 'stale') return 'tag-warn'
  if (c.state === 'needs_verification') return 'tag-bad'
  return 'tag-warn'
})
const gate = computed(() => candidate.value?.gate_findings || null)
const showAck = computed(() => Boolean(gate.value?.blocking && !candidate.value?.gate_ack))
const nextResponsible = computed(() => {
  const t = team.value
  if (!t) return ''
  const a = t.assignment || { assignee: '', reviewer: '' }
  if (t.state === 'approved' || candidate.value?.state === 'accepted') return '业务验收人'
  if (candidate.value?.missing?.length) return a.assignee || '负责人'
  return a.reviewer || '复核人'
})
const assessmentOf = (id: string) =>
  candidate.value?.assessment?.results?.find(r => r.id === id)

async function load() {
  error.value = ''
  try {
    candidate.value = await get<CandidateView>(`/api/candidates/${encodeURIComponent(props.id)}`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '候选读取失败。'
    loading.value = false
    return
  }
  try {
    const ticket = candidate.value.ticket
    const list = await get<{ items?: TeamItem[] } | TeamItem[]>(`/api/team?ticket=${encodeURIComponent(ticket)}`)
    const items = Array.isArray(list) ? list : list.items || []
    team.value = items.find(i => i.candidate?.id === candidate.value?.id) || items[0] || null
  } catch {
    team.value = null
  }
  loading.value = false
  schedulePoll()
}

function schedulePoll() {
  if (poll) clearInterval(poll)
  poll = candidate.value?.recheck?.running
    ? setInterval(() => { if (!busy.value) load() }, 5000)
    : null
}

async function act(action: string, extra: Record<string, unknown> = {}, success = '') {
  const c = candidate.value
  if (!c) return
  busy.value = action
  error.value = ''
  notice.value = ''
  try {
    await post<TeamActionResult>('/api/team', {
      ticket: c.ticket,
      action,
      candidate_id: c.id,
      request_id: requestId(),
      ...extra,
    })
    notice.value = success
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '操作失败，本次没有重试。'
  } finally {
    busy.value = ''
  }
}

async function ackGate() {
  if (!ackReason.value.trim()) return
  await act('candidate_gate_ack', { reason: ackReason.value.trim() }, '门禁确认已记录。')
  ackReason.value = ''
}

function b64ToBytes(b64: string): Uint8Array {
  const s = atob(b64)
  const out = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i)
  return out
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', data as BufferSource)
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0)
  const out = new Uint8Array(total)
  let off = 0
  for (const p of parts) { out.set(p, off); off += p.length }
  return out
}

async function exportReport() {
  const c = candidate.value
  if (!c) return
  busy.value = 'report'
  error.value = ''
  notice.value = ''
  reportProgress.value = ''
  try {
    const created = await post<ReportManifest & { result?: ReportManifest }>('/api/team', {
      ticket: c.ticket,
      action: 'candidate_report_create',
      candidate_id: c.id,
      request_id: requestId(),
    })
    const manifest: ReportManifest = (created as { result?: ReportManifest }).result || created as ReportManifest
    const entry = (manifest.files || []).find(f => f.name === 'report.md')
    if (!entry) throw new ApiError('报告里没有 report.md 附件。', 0)
    const parts: Uint8Array[] = []
    let offset = 0
    for (;;) {
      reportProgress.value = `正在读取报告分段（${entry.bytes} 字节）…`
      const seg = await post<{ result?: ReportSegment } & ReportSegment>('/api/team', {
        ticket: c.ticket,
        action: 'candidate_report_get',
        candidate_id: c.id,
        export_id: manifest.export_id,
        file: 'report.md',
        offset,
        request_id: requestId(),
      })
      const s: ReportSegment = (seg as { result?: ReportSegment }).result || seg as ReportSegment
      parts.push(b64ToBytes(s.data_base64))
      if (s.next_offset == null) break
      offset = s.next_offset
    }
    const body = concat(parts)
    const sha = await sha256Hex(body)
    if (sha !== entry.sha256) {
      throw new ApiError(`报告分段校验失败：sha256 ${sha} 与清单 ${entry.sha256} 不一致，未下载。`, 0)
    }
    const url = URL.createObjectURL(new Blob([body as BlobPart], { type: 'text/markdown;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `candidate-${c.id}-report.md`
    a.click()
    URL.revokeObjectURL(url)
    notice.value = '验证报告已下载，分段与整文件 sha256 均已核对。'
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '报告导出失败，本次没有重试。'
  } finally {
    busy.value = ''
    reportProgress.value = ''
  }
}

const verificationCommands = computed(() => candidate.value?.verification?.commands || [])
const baselineCommands = computed(() => candidate.value?.verification?.baseline_tests || [])

onMounted(load)
onBeforeUnmount(() => { if (poll) clearInterval(poll) })
</script>

<template>
  <div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="note">{{ notice }}</p>
    <p v-if="loading" class="muted">正在读取候选…</p>

    <template v-else-if="candidate">
      <div class="head">
        <div>
          <h1>候选 #{{ candidate.id }} <span class="tag" :class="stateTone">{{ stateLabel }}</span></h1>
          <p class="muted">
            <router-link :to="`/p/${encodeURIComponent(pkey)}/verify?ticket=${encodeURIComponent(candidate.ticket)}`">{{ candidate.ticket }}</router-link>
            · 提交者 {{ candidate.author }} · 运行 #{{ candidate.run_id }}
          </p>
        </div>
        <div class="actions">
          <button v-if="candidate.current && !candidate.recheck?.running" class="btn" :disabled="busy !== ''" @click="act('candidate_verify', {}, '已启动独立检查，请稍后刷新。')">运行技术检查</button>
          <button v-if="candidate.recheck?.running" class="btn" :disabled="busy !== ''" @click="act('candidate_cancel', {}, '已请求停止检查。')">停止检查</button>
          <a v-if="candidate.preview_url" class="btn" :href="candidate.preview_url" target="_blank" rel="noopener">打开预览 ↗</a>
          <button class="btn" :disabled="busy !== ''" @click="exportReport">{{ busy === 'report' ? '导出中…' : '导出验证报告' }}</button>
          <button class="btn" :disabled="busy !== ''" @click="load">刷新</button>
        </div>
      </div>
      <p v-if="reportProgress" class="muted">{{ reportProgress }}</p>

      <div class="panel">
        <h2>固定版本</h2>
        <div class="commits">
          <div><div class="muted">基线</div><code>{{ candidate.base_commit }}</code></div>
          <div><div class="muted">候选</div><code>{{ candidate.commit }}</code></div>
        </div>
        <p v-if="!candidate.current" class="note warn-note">
          该候选已不是当前有效版本：<span v-for="(b, i) in candidate.blocked" :key="i">{{ b }}<br></span>
        </p>
        <div v-else-if="candidate.missing.length" class="note">
          <div v-for="(m, i) in candidate.missing" :key="i">{{ m }}</div>
          <div class="muted" style="margin-top:6px">下一步：{{ nextResponsible }}</div>
        </div>
        <p v-else class="note" style="border-left-color:var(--ok)">当前结论：{{ stateLabel }}。下一步：{{ nextResponsible }}。</p>
        <p class="muted" style="margin-top:10px">{{ candidate.boundary }}</p>
        <div class="desc">{{ candidate.summary }}</div>
        <p v-if="!candidate.criteria.length" class="muted">业务符合性：未知（未提供验收标准）</p>
      </div>

      <div v-if="gate?.blocking || candidate.gate_ack" class="panel">
        <h2>门禁相关变更</h2>
        <template v-if="gate?.blocking">
          <ul class="gate-list">
            <li v-for="f in gate.tests_deleted" :key="'d' + f">删除了测试文件 <code>{{ f }}</code></li>
            <li v-for="f in gate.tests_changed" :key="'c' + f">改动了测试文件 <code>{{ f }}</code></li>
            <li v-for="f in gate.gate_files" :key="'g' + f">改动了门禁/构建配置 <code>{{ f }}</code></li>
            <li v-for="(w, i) in gate.weakening" :key="'w' + i">断言变弱：{{ w }}</li>
          </ul>
          <div v-if="candidate.gate_ack" class="note">
            已由 {{ candidate.gate_ack.actor || '操作者' }} 确认：{{ candidate.gate_ack.reason }}
          </div>
          <div v-else class="ack">
            <label class="field">操作者确认理由
              <textarea v-model="ackReason" placeholder="说明为什么这些门禁相关变更是合理的"></textarea>
            </label>
            <button class="btn" :disabled="busy !== '' || !ackReason.trim()" @click="ackGate">记录门禁确认</button>
          </div>
        </template>
        <p v-else class="muted">未发现门禁相关变更。</p>
      </div>

      <div v-if="candidate.control_points?.length" class="panel">
        <h2>控制点</h2>
        <ul class="cp-list">
          <li v-for="cp in candidate.control_points" :key="cp.name">
            <b>{{ cp.name }}</b>：{{ GATE_STATE[cp.state] || cp.state }}<span v-if="cp.why" class="muted"> — {{ cp.why }}</span>
          </li>
        </ul>
      </div>

      <div v-if="candidate.criteria.length" class="panel">
        <h2>逐项结果</h2>
        <div v-for="c in candidate.criteria" :key="c.id" class="criterion">
          <div><b>{{ c.id }}</b> {{ c.text }}</div>
          <div class="muted">验证方式：{{ c.check }}</div>
          <div class="result">
            <span class="tag" :class="{ 'tag-good': assessmentOf(c.id)?.status === 'pass', 'tag-bad': assessmentOf(c.id)?.status === 'fail' }">
              {{ RESULT_LABEL[assessmentOf(c.id)?.status || 'unknown'] || assessmentOf(c.id)?.status }}
            </span>
            <span v-if="assessmentOf(c.id)?.evidence" class="muted"> {{ assessmentOf(c.id)?.evidence }}</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <h2>验证记录</h2>
        <template v-if="verificationCommands.length || baselineCommands.length">
          <div v-for="(cmd, i) in verificationCommands" :key="'v' + i" class="cmd">
            <div class="cmd-head">
              <code>{{ cmd.command || cmd.cmd || cmd.kind || '检查' }}</code>
              <span class="tag" :class="cmd.exit_code === 0 ? 'tag-good' : 'tag-bad'">退出码 {{ cmd.exit_code ?? '—' }}</span>
            </div>
            <pre v-if="cmd.output || cmd.tail" class="cmd-out">{{ cmd.output || cmd.tail }}</pre>
          </div>
          <template v-if="baselineCommands.length">
            <h3 style="margin-top:16px">基线对照</h3>
            <div v-for="(cmd, i) in baselineCommands" :key="'b' + i" class="cmd">
              <div class="cmd-head">
                <code>{{ cmd.command || cmd.cmd || cmd.kind || '基线检查' }}</code>
                <span class="tag" :class="cmd.exit_code === 0 ? 'tag-good' : 'tag-bad'">退出码 {{ cmd.exit_code ?? '—' }}</span>
              </div>
              <pre v-if="cmd.output || cmd.tail" class="cmd-out">{{ cmd.output || cmd.tail }}</pre>
            </div>
          </template>
          <p class="muted" style="margin-top:10px">
            检查对象：候选 <code>{{ candidate.verification?.checked_commit || candidate.commit }}</code>
            <template v-if="candidate.verification?.checked_base"> · 基线 <code>{{ candidate.verification.checked_base }}</code></template>
            · 结论 {{ CHECK_LABEL[candidate.verification?.check || ''] || candidate.verification?.check || '未知' }}
          </p>
        </template>
        <p v-else class="muted">尚无本次版本的独立检查记录。</p>
      </div>

      <div v-if="candidate.human_decision" class="panel">
        <h2>人工决定</h2>
        <p>{{ candidate.human_decision.author }} · {{ candidate.human_decision.created }} · {{ candidate.human_decision.note }}</p>
        <p v-if="!candidate.human_accepted" class="muted">（不代表当前版本已通过）</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; margin-bottom: 8px; }
.head h1 { margin-bottom: 4px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.commits { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 10px 0; }
.commits code { display: block; margin-top: 4px; }
.warn-note { border-left-color: var(--warn); }
.desc { margin-top: 12px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.gate-list { margin: 8px 0 14px; padding-left: 20px; color: var(--bad); }
.ack { margin-top: 12px; max-width: 560px; }
.cp-list, .criteria { list-style: none; padding: 0; margin: 8px 0 0; }
.cp-list li, .criterion { padding: 10px 0; border-bottom: 1px solid var(--line); }
.cp-list li:last-child, .criterion:last-child { border-bottom: 0; }
.criterion .result { margin-top: 8px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.cmd { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 14px; margin-bottom: 10px; }
.cmd-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.cmd-out {
  margin: 8px 0 0; padding: 10px; background: var(--bg); border-radius: 6px; max-height: 320px; overflow: auto;
  font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere;
}
@media (max-width: 760px) { .commits { grid-template-columns: 1fr; } }
</style>
