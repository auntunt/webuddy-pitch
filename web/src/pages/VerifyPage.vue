<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, post, requestId, ApiError } from '../api/client'
import type { Ticket, DevelopmentInfo, ResolveResult, TeamActionResult } from '../api/types'
import { app, legacyUrl } from '../app'

const props = defineProps<{ pkey: string }>()
const router = useRouter()

const tickets = ref<Ticket[]>([])
const ticketKey = ref('')
const dev = ref<DevelopmentInfo | null>(null)
const devError = ref('')
const devLoading = ref(false)
const base = ref('')
const commit = ref('')
const summary = ref('')
const resolved = ref<ResolveResult | null>(null)
const busy = ref('')
const error = ref('')
const notice = ref('')

const criteria = computed(() => dev.value?.payload.criteria || [])
const confirmed = computed(() => dev.value?.state === 'confirmed')
const canSubmit = computed(() => Boolean(dev.value?.work?.can_submit))
const submitBlockReason = computed(() => {
  const w = dev.value?.work
  if (!w) return ''
  if (w.repository_ready === false && w.repository_reason) return w.repository_reason
  if (!w.can_submit) return '请由已分配的负责人提交代码。'
  return ''
})

async function loadTickets() {
  error.value = ''
  try {
    tickets.value = await get<Ticket[]>(`/api/tickets?project=${encodeURIComponent(props.pkey)}&limit=200`)
    const wanted = new URLSearchParams(window.location.search).get('ticket') || ''
    if (wanted && tickets.value.some(t => t.key === wanted)) ticketKey.value = wanted
    else if (!ticketKey.value && tickets.value.length) ticketKey.value = tickets.value[0].key
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '工单列表读取失败。'
  }
}

async function loadDev() {
  dev.value = null
  devError.value = ''
  resolved.value = null
  if (!ticketKey.value) return
  devLoading.value = true
  try {
    dev.value = await get<DevelopmentInfo>(`/api/tickets/${encodeURIComponent(ticketKey.value)}/development`)
  } catch (e) {
    devError.value = e instanceof ApiError ? e.message : '开发约定读取失败。'
  } finally {
    devLoading.value = false
  }
}

watch(ticketKey, loadDev)

async function resolveRefs() {
  if (!ticketKey.value || !base.value.trim() || !commit.value.trim()) return
  busy.value = 'resolve'
  error.value = ''
  notice.value = ''
  try {
    const r = await post<{ result: ResolveResult }>('/api/team', {
      ticket: ticketKey.value,
      action: 'candidate_resolve',
      base: base.value.trim(),
      commit: commit.value.trim(),
      request_id: requestId(),
    })
    resolved.value = r.result
    if (r.result.base.resolved) base.value = r.result.base.commit
    if (r.result.commit.resolved) commit.value = r.result.commit.commit
    if (!r.result.base.resolved || !r.result.commit.resolved) {
      notice.value = '有一侧编号无法解析为提交，请核对后重试。'
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '解析失败。'
  } finally {
    busy.value = ''
  }
}

async function submit() {
  const w = dev.value?.work
  if (!ticketKey.value || !w?.requirement_hash) return
  busy.value = 'submit'
  error.value = ''
  notice.value = ''
  try {
    const r = await post<TeamActionResult>('/api/team', {
      ticket: ticketKey.value,
      action: 'candidate_submit',
      base_commit: base.value.trim(),
      commit: commit.value.trim(),
      requirement_hash: w.requirement_hash,
      criteria: criteria.value,
      summary: summary.value,
      request_id: requestId(),
    })
    const submitted = r.result as { candidate_id?: number } | undefined
    const cid = submitted?.candidate_id ?? r.item?.candidate?.id
    if (cid) {
      router.push(`/p/${encodeURIComponent(props.pkey)}/candidates/${cid}`)
    } else {
      notice.value = '已提交，但暂时读不到候选编号，请到工单页查看。'
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '提交失败，本次没有重试。'
  } finally {
    busy.value = ''
  }
}

onMounted(loadTickets)
</script>

<template>
  <div>
    <h1>验证现有改动</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="panel">
      <label class="field">
        工单
        <select v-model="ticketKey" :disabled="!tickets.length">
          <option v-for="t in tickets" :key="t.key" :value="t.key">{{ t.key }} · {{ t.title }}</option>
        </select>
      </label>
      <p v-if="!tickets.length && !error" class="muted">这个项目还没有工单。<a :href="legacyUrl('/#/tickets')">到旧版创建工单</a>。</p>
      <p v-else class="muted">没有合适的工单？<a :href="legacyUrl('/#/tickets')">到旧版创建</a>。</p>

      <div v-if="devLoading" class="muted">正在读取开发约定…</div>
      <div v-else-if="devError" class="error" role="alert">{{ devError }}</div>
      <template v-else-if="dev">
        <div v-if="dev.state !== 'confirmed'" class="note">
          开发约定当前状态：{{ dev.state }}。验收标准以确认后的约定为准；
          <a :href="legacyUrl(`/#/t/${dev.ticket}`)">到旧版工单页处理</a>。
        </div>
        <h2>验收标准</h2>
        <ul v-if="criteria.length" class="criteria">
          <li v-for="c in criteria" :key="c.id"><b>{{ c.id }}</b> {{ c.text }}<div class="muted">验证方式：{{ c.check }}</div></li>
        </ul>
        <p v-else class="muted">业务符合性：未知（未提供验收标准）</p>
      </template>
    </div>

    <div class="panel">
      <div class="grid2">
        <label class="field">基线提交或分支
          <input v-model="base" autocomplete="off" placeholder="main、v1.0 或完整 SHA" />
        </label>
        <label class="field">候选提交或分支
          <input v-model="commit" autocomplete="off" placeholder="feature/x 或完整 SHA" />
        </label>
      </div>
      <label class="field">实现说明
        <textarea v-model="summary" placeholder="说明实际完成了什么，以及仍未验证的边界"></textarea>
      </label>

      <p v-if="resolved" class="resolved">
        <template v-if="resolved.base.resolved">基线 <code>{{ resolved.base.commit.slice(0, 12) }}</code></template>
        <template v-else>基线无法解析</template>
        ·
        <template v-if="resolved.commit.resolved">候选 <code>{{ resolved.commit.commit.slice(0, 12) }}</code></template>
        <template v-else>候选无法解析</template>
      </p>

      <div class="actions">
        <button class="btn" :disabled="busy !== '' || !ticketKey || !base.trim() || !commit.trim()" @click="resolveRefs">
          {{ busy === 'resolve' ? '解析中…' : '解析提交编号' }}
        </button>
        <button class="btn btn-primary" :disabled="busy !== '' || !ticketKey || !base.trim() || !commit.trim() || !canSubmit" @click="submit">
          {{ busy === 'submit' ? '提交中…' : '验证现有改动' }}
        </button>
      </div>
      <p v-if="submitBlockReason" class="muted" style="margin-top:10px">{{ submitBlockReason }}</p>
      <p v-if="notice" class="note">{{ notice }}</p>
    </div>
  </div>
</template>

<style scoped>
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.criteria { padding-left: 20px; margin: 8px 0 0; }
.criteria li { margin-bottom: 10px; }
.resolved { font-size: 13px; color: var(--sub); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
@media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
</style>
