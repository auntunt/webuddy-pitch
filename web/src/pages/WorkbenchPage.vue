<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, post, ApiError } from '../api/client'
import { app, legacyUrl, selectProject } from '../app'
import type { Ticket } from '../api/types'

type Run = { id: number; mode: string; status: string; result?: string; diff?: string; output?: string; verification?: Record<string, unknown> | null }
type Detail = { ticket: Ticket & { body?: string }; runs: Run[]; auto_next?: string; plain_state?: unknown }
const props = defineProps<{ pkey: string }>()
const router = useRouter()
const tickets = ref<Ticket[]>([])
const selected = ref('')
const detail = ref<Detail | null>(null)
const run = ref<Run | null>(null)
const title = ref('')
const body = ref('')
const query = ref('')
const agent = ref('')
const busy = ref('')
const error = ref('')
const loading = ref(false)
const composing = ref(false)
const tab = ref('result')
let generation = 0
let runRequest = 0
let timer: ReturnType<typeof setTimeout> | undefined
const agents = computed(() => (app.meta?.agents || []).filter(a => a.available))
const visible = computed(() => tickets.value.filter(t => `${t.key} ${t.title}`.toLowerCase().includes(query.value.toLowerCase())))
const active = computed(() => detail.value?.runs.some(r => ['queued', 'running'].includes(r.status)))
const modes: Record<string, string> = { analyze: '分析', plan: '方案', fix: '开发', edit: '协作开发', verify: '验证' }
const states: Record<string, string> = { new: '新建', analyzing: '分析中', confirm: '待确认', doing: '处理中', verify: '待验证', cancelled: '已取消', queued: '等待执行', running: '执行中', done: '已结束', failed: '失败', stopped: '已停止', open: '待处理', closed: '已关闭', planned: '方案待确认', resolved: '待验收' }
const message = (e: unknown) => e instanceof ApiError ? e.message : e instanceof Error ? e.message : '请求失败。'
function clearPoll() { if (timer) clearTimeout(timer); timer = undefined }
async function loadRun(id: number) {
  const stamp = generation
  const request = ++runRequest
  try {
    const value = await get<Run>(`/api/runs/${id}`)
    if (stamp === generation && request === runRequest) run.value = value
  } catch (e) { if (stamp === generation) error.value = message(e) }
}
async function refresh() {
  const stamp = generation
  const key = selected.value
  if (!key) return
  try {
    const value = await get<Detail>(`/api/tickets/${encodeURIComponent(key)}`)
    if (stamp !== generation || key !== selected.value) return
    detail.value = value
    const current = value.runs.find(r => r.id === run.value?.id) || value.runs[0]
    if (current) await loadRun(current.id)
    if (stamp !== generation) return
    clearPoll()
    if (value.runs.some(r => ['queued', 'running'].includes(r.status))) timer = setTimeout(refresh, 3000)
  } catch (e) { if (stamp === generation) error.value = message(e) }
}
async function choose(key: string) {
  generation++
  clearPoll()
  selected.value = key
  detail.value = null
  run.value = null
  composing.value = false
  error.value = ''
  await refresh()
}
async function loadProject() {
  const stamp = ++generation
  clearPoll()
  selected.value = ''
  detail.value = null
  run.value = null
  tickets.value = []
  composing.value = false
  error.value = ''
  loading.value = true
  selectProject(props.pkey)
  try {
    const list = await get<Ticket[]>(`/api/tickets?project=${encodeURIComponent(props.pkey)}&limit=500`)
    if (stamp !== generation) return
    tickets.value = list
    if (list[0]) await choose(list[0].key)
    else composing.value = true
  } catch (e) { if (stamp === generation) error.value = message(e) }
  finally { loading.value = false }
}
async function create() {
  if (!title.value.trim() || busy.value) return
  busy.value = 'create'
  error.value = ''
  const project = props.pkey
  try {
    const value = await post<Ticket>('/api/tickets', { project, title: title.value.trim(), body: body.value, auto: false })
    if (project !== props.pkey) return
    tickets.value.unshift(value)
    title.value = ''
    body.value = ''
    await choose(value.key)
  } catch (e) { error.value = message(e) }
  finally { busy.value = '' }
}
async function start(mode: string) {
  if (!selected.value || busy.value || active.value) return
  busy.value = mode
  error.value = ''
  const stamp = generation
  try {
    const value = await post<Run>(`/api/tickets/${encodeURIComponent(selected.value)}/runs`, { mode, ...(agent.value ? { agent: agent.value } : {}) })
    if (stamp !== generation) return
    run.value = value
    tab.value = 'result'
    await refresh()
  } catch (e) { if (stamp === generation) error.value = message(e) }
  finally { busy.value = '' }
}
function verify() { router.push({ path: `/p/${encodeURIComponent(props.pkey)}/verify`, query: { ticket: selected.value } }) }
watch(() => props.pkey, loadProject, { immediate: true })
onUnmounted(() => { generation++; clearPoll() })
</script>

<template>
  <section>
    <header class="heading"><h1>开发工作台</h1><button class="btn btn-primary" @click="composing = true">新需求</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="workbench">
      <aside class="queue" aria-label="需求列表">
        <input v-model="query" class="search" aria-label="搜索需求" placeholder="搜索需求" />
        <p v-if="loading" class="muted">正在读取…</p>
        <button v-for="item in visible" :key="item.key" class="ticket" :class="{ selected: item.key === selected && !composing }" @click="choose(item.key)">
          <strong>{{ item.title }}</strong><span>{{ item.key }} <span v-if="item.status">· {{ states[item.status] || item.status }}</span></span>
        </button>
        <p v-if="!loading && !visible.length" class="empty">{{ query ? '没有匹配的需求' : '从一个小需求开始' }}</p>
        <a :href="legacyUrl('/tickets')" class="all-tickets">查看全部工单</a>
      </aside>
      <div class="desk">
        <form v-if="composing" class="compose" @submit.prevent="create">
          <h2>这次要改什么？</h2>
          <label class="field">需求名称<input v-model="title" required placeholder="例如：导出金额跟随税率配置" /></label>
          <label class="field">需求与项目说明<textarea v-model="body" rows="8" placeholder="描述现在的情况、希望改成什么。可以补充实际子项目目录、启动方式和不能改变的规则。" /></label>
          <div class="actions"><button class="btn btn-primary" :disabled="!!busy || !title.trim()">{{ busy === 'create' ? '保存中…' : '保存需求' }}</button><button v-if="selected" type="button" class="btn" @click="composing = false">返回</button></div>
        </form>
        <template v-else-if="detail">
          <header class="task-heading"><span class="muted">{{ detail.ticket.key }}</span><h2>{{ detail.ticket.title }}</h2></header>
          <details v-if="detail.ticket.body" class="requirement"><summary>需求原文</summary><pre>{{ detail.ticket.body }}</pre></details>
          <div class="toolbar">
            <label class="field executor">执行器<select v-model="agent" :disabled="!!busy || active"><option value="">项目默认</option><option v-for="a in agents" :key="a.name" :value="a.name">{{ a.title }}</option></select></label>
            <div class="actions">
              <button v-for="mode in ['analyze', 'plan', 'fix']" :key="mode" class="btn" :disabled="!!busy || active" @click="start(mode)">{{ busy === mode ? '启动中…' : ({ analyze: '分析需求', plan: '生成方案', fix: '开始开发' }[mode]) }}</button>
              <button class="btn" @click="verify">验证现有改动</button>
            </div>
          </div>
          <div class="run-heading"><h3>执行记录</h3><button class="text-button" :disabled="!!busy" @click="refresh">刷新</button></div>
          <div v-if="detail.runs.length" class="runs" aria-label="执行记录">
            <button v-for="item in detail.runs" :key="item.id" class="run" :class="{ current: item.id === run?.id }" @click="loadRun(item.id)">{{ modes[item.mode] || item.mode }} #{{ item.id }} <span :class="{ running: ['running', 'queued'].includes(item.status) }">{{ states[item.status] || item.status }}</span></button>
          </div>
          <p v-else class="empty">需求已保存。先分析需求或生成方案。</p>
          <template v-if="run">
            <nav class="tabs" aria-label="运行产物"><button v-for="[key, label] in [['result','结果'], ['diff','代码差异'], ['verification','验证回执'], ['output','执行日志']]" :key="key" :class="{ current: tab === key }" @click="tab = key!">{{ label }}</button></nav>
            <pre v-if="tab === 'result' && run.result" class="artifact">{{ run.result }}</pre>
            <pre v-else-if="tab === 'diff' && run.diff" class="artifact diff"><span v-for="(line, index) in run.diff.split('\n')" :key="index" class="diff-line" :class="{ added: line.startsWith('+'), removed: line.startsWith('-'), hunk: line.startsWith('@@') }">{{ line }}{{ '\n' }}</span></pre>
            <pre v-else-if="tab === 'verification' && run.verification" class="artifact">{{ JSON.stringify(run.verification, null, 2) }}</pre>
            <pre v-else-if="tab === 'output' && run.output" class="artifact logs">{{ run.output }}</pre>
            <p v-else class="empty">{{ tab === 'verification' ? '暂无验证回执。执行结束不代表验证通过。' : tab === 'diff' ? '本次运行暂无代码差异。' : ['queued','running'].includes(run.status) ? '正在执行，结果会自动更新。' : '本次运行未产生这项内容。' }}</p>
          </template>
        </template>
        <p v-else-if="!loading" class="empty">选择一项需求，或创建新需求。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.heading,.task-heading,.run-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.heading { margin-bottom:24px; }.heading h1 { margin:0; }
.workbench { display:grid; grid-template-columns:260px minmax(0,1fr); background:var(--panel); border:1px solid var(--line); border-radius:10px; min-height:65vh; overflow:hidden; }
.queue { padding:16px 12px; border-right:1px solid var(--line); background:#fafbfc; }
.search { width:100%; border:1px solid var(--line); border-radius:6px; padding:9px 10px; margin-bottom:14px; }
.ticket { width:100%; text-align:left; border:0; border-radius:6px; background:transparent; padding:13px 10px; cursor:pointer; margin-bottom:5px; }
.ticket strong { display:block; font-size:14px; font-weight:550; line-height:1.5; overflow-wrap:anywhere; }.ticket>span { display:block; color:var(--sub); font-size:12px; margin-top:6px; }.ticket:hover,.ticket.selected { background:var(--accent-soft); }.ticket.selected strong { color:var(--accent); }
.all-tickets { display:block; padding:14px 10px; font-size:13px; }
.desk { min-width:0; padding:24px; }.compose { max-width:680px; }.compose h2 { margin-top:0; font-size:22px; }.task-heading { display:block; }.task-heading h2 { margin:5px 0 20px; font-size:22px; overflow-wrap:anywhere; }
.requirement { border-bottom:1px solid var(--line); padding:0 0 16px; margin-bottom:18px; }.requirement summary { cursor:pointer; color:var(--sub); }.requirement pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; }
.toolbar { display:flex; flex-wrap:wrap; align-items:end; gap:14px; }.executor { min-width:160px; margin:0; }.actions { display:flex; gap:8px; flex-wrap:wrap; }.actions .btn { font-size:13px; }
.run-heading { margin-top:30px; }.run-heading h3 { margin:0; }.text-button { border:0; background:transparent; color:var(--accent); cursor:pointer; }
.runs { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 22px; }.run { background:var(--panel); border:1px solid var(--line); padding:7px 10px; border-radius:5px; cursor:pointer; font-size:12px; }.run span { color:var(--sub); margin-left:8px; }.run.current { border-color:var(--accent); }.run span.running { color:var(--accent); }
.diff-line { display:block; white-space:pre-wrap; }.diff-line.added { background:#e4f4e9; color:#145b32; }.diff-line.removed { background:#fde8e8; color:#9b2929; }.diff-line.hunk { color:var(--accent); }
.tabs { display:flex; gap:20px; border-bottom:1px solid var(--line); }.tabs button { border:0; border-bottom:2px solid transparent; background:transparent; padding:12px 0; cursor:pointer; color:var(--sub); font-size:13px; }.tabs button.current { border-bottom-color:var(--accent); color:var(--accent); }
.artifact { white-space:pre-wrap; overflow-wrap:anywhere; font:14px/1.8 ui-monospace,monospace; margin:0; padding:22px 0; }.diff,.logs { background:#f7f9fb; padding:18px; margin-top:16px; font-size:12px; }
@media(max-width:1000px) { .workbench { grid-template-columns:210px minmax(0,1fr); }.desk { padding:20px; } }
@media(max-width:760px) { .workbench { grid-template-columns:1fr; }.queue { border-right:0; border-bottom:1px solid var(--line); max-height:230px; overflow:auto; }.desk { padding:18px; }.tabs { gap:16px; }.task-heading h2 { font-size:20px; } }
</style>
