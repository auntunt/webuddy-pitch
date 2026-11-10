<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, post, ApiError, appUrl } from '../api/client'
import { app, legacyUrl, selectProject, prepareLegacy } from '../app'
import DocumentText from '../components/DocumentText.vue'
import RequirementBatch from '../components/RequirementBatch.vue'
import type { Ticket } from '../api/types'

type Preparation = { steps: {name:string; state:string; detail?:string}[] }
type Run = { preparation?:Preparation; continuation?:{next_run:number}; id: number; mode: string; status: string; result?: string; diff?: string; output?: string; verification?: Record<string, unknown> | null; decision?: string; can_retry?: boolean; recheck?: { running?: boolean }; commit?: string }
type Detail = { ticket: Ticket & { body?: string; type?: string }; team_assignment?: {assignee:string;reviewer:string}; stage?: {label:string}; runs: Run[]; auto_next?: string; plain_state?: unknown; events?: { author: string; body: string; created: string }[]; epic?: { children: {key:string; title:string; status:string; after:string[]}[]; paused:string }; parent?: {key:string;title:string} }
const props = defineProps<{ pkey: string; ticketKey?: string; compose?: boolean }>()
const router = useRouter()
const tickets = ref<Ticket[]>([])
const selected = ref('')
const detail = ref<Detail | null>(null)
const run = ref<Run | null>(null)
const title = ref('')
const body = ref('')
const taskType = ref('auto'), acceptance = ref('')
const taskTypes: Record<string,string> = {auto:'自动识别',feature:'需求开发',bug:'缺陷修复',change:'变更',ops:'运维与数据问题',question:'咨询与排查'}
const query = ref('')
const agent = ref('')
const busy = ref('')
const error = ref('')
const loading = ref(false)
const composing = ref(false)
const tab = ref('result')
const batch = ref(false), comment = ref(''), notice = ref('')
let pendingComment: {scope:string; body:string; request_id:string} | null = null
type Preview = {url?:string;preview: {state?:string;why?:string;error?:string}}
const preview = ref<Preview | null>(null)

let generation = 0
let runRequest = 0
let timer: ReturnType<typeof setTimeout> | undefined
const agents = computed(() => (app.meta?.agents || []).filter(a => a.available))
const visible = computed(() => tickets.value.filter(t => `${t.key} ${t.title}`.toLowerCase().includes(query.value.toLowerCase())))
const active = computed(() => detail.value?.runs.some(r => ['queued', 'running'].includes(r.status)))
const modes: Record<string, string> = { continue: '处理补充', analyze: '分析', plan: '方案', fix: '开发', edit: '协作开发', verify: '验证' }
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
    const listed = tickets.value.find(t => t.key === key)
    if (listed) Object.assign(listed, value.ticket)
    const next = run.value?.continuation?.next_run
    const current = value.runs.find(r => r.id === (next || run.value?.id)) || value.runs[0]
    if (current) await loadRun(current.id)
    if (stamp !== generation) return
    if (preview.value && run.value) {
      const state = await get<Preview>(`/api/tickets/${encodeURIComponent(key)}/preview?run_id=${run.value.id}`)
      if (stamp !== generation) return
      preview.value = state
    }
    clearPoll()
    if (value.runs.some(r => ['queued', 'running'].includes(r.status)) || run.value?.recheck?.running || preview.value?.preview.state === 'starting') timer = setTimeout(refresh, 3000)
  } catch (e) { if (stamp === generation) error.value = message(e) }
}
async function choose(key: string) {
  generation++
  clearPoll()
  selected.value = key
  detail.value = null
  run.value = null
  composing.value = false
  batch.value = false
  preview.value = null
  notice.value = ''
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
  batch.value = false
  preview.value = null
  notice.value = ''
  error.value = ''
  loading.value = true
  selectProject(props.pkey)
  try {
    const list = await get<Ticket[]>(`/api/tickets?project=${encodeURIComponent(props.pkey)}&limit=500`)
    if (stamp !== generation) return
    tickets.value = list
    if (props.ticketKey?.startsWith(props.pkey + '-')) await choose(props.ticketKey)
    else if (list[0]) await choose(list[0].key)
    else composing.value = true
    if (props.compose) composing.value = true
  } catch (e) { if (stamp === generation) error.value = message(e) }
  finally { loading.value = false }
}
async function create() {
  if (!title.value.trim() || busy.value) return
  busy.value = 'create'
  error.value = ''
  const project = props.pkey
  try {
    const criteria = acceptance.value.trim()
    const description = body.value + (criteria ? '\n\n## 验收标准（提单人填写）\n' + criteria.split('\n').filter(line => line.trim()).map((line,i) => `- A${i+1} ${line}`).join('\n') : '')
    const value = await post<Ticket>('/api/tickets', { project, title: title.value.trim(), body: description, auto: false, ...(taskType.value !== 'auto' ? {type:taskType.value} : {}) })
    if (project !== props.pkey) return
    tickets.value.unshift(value)
    title.value = ''
    body.value = ''
    acceptance.value = ''
    taskType.value = 'auto'
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
async function perform(action: string, payload: unknown = {}) {
  if (busy.value) return
  const stamp = generation
  busy.value = action; error.value = ''; notice.value = ''
  try {
    const ticketPath = `/api/tickets/${encodeURIComponent(selected.value)}`
    const path = action === 'auto' ? ticketPath : action === 'comments' ? ticketPath + '/comments' : action.startsWith('epic-') ? ticketPath + '/epic' : `/api/runs/${run.value!.id}/${action}`
    if (action === 'comments') {
      const scope = `${props.pkey}/${selected.value}`
      if (!pendingComment || pendingComment.scope !== scope || pendingComment.body !== comment.value)
        pendingComment = {scope, body:comment.value, request_id:crypto.randomUUID()}
      payload = {body:pendingComment.body, request_id:pendingComment.request_id, continue:true, ...(agent.value?{agent:agent.value}:{})}
    }
    const response = await post<{run?:number}>(path, action === 'auto' ? {auto:'go'} : action.startsWith('epic-') ? {action:action.slice(5)} : payload)
    if(stamp !== generation)return
    if(action === 'comments' && response.run) await loadRun(response.run)
    notice.value = action === 'comments' ? '评论已提交，智能体会接着处理' : '操作已提交'; comment.value = ''; if(action === 'comments')pendingComment = null; await refresh()
  } catch(e) { if(stamp === generation)error.value=message(e) } finally {busy.value=''}
}
async function previewRun() {
  if(!run.value || busy.value)return
  const stamp=generation
  busy.value='preview';error.value=''
  try { const result=await post<Preview>(`/api/tickets/${encodeURIComponent(selected.value)}/preview`,{action:'start',run_id:run.value.id}); if(stamp===generation){preview.value=result;await refresh()} } catch(e) {error.value=message(e)} finally {busy.value=''}
}
async function batchCreated(key:string) { await loadProject(); if(key)await choose(key) }
function verify() { router.push({ path: `/p/${encodeURIComponent(props.pkey)}/verify`, query: { ticket: selected.value } }) }
watch(() => [props.pkey, props.ticketKey, props.compose], loadProject, { immediate: true })
onUnmounted(() => { generation++; clearPoll() })
</script>

<template>
  <section>
    <header class="heading"><h1>开发工作台</h1><button class="btn btn-primary" @click="composing = true; batch = false">新需求</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="note" role="status">{{ notice }}</p>
    <div class="workbench">
      <aside class="queue" aria-label="需求列表">
        <input v-model="query" class="search" aria-label="搜索需求" placeholder="搜索需求" />
        <p v-if="loading" class="muted">正在读取…</p>
        <button v-for="item in visible" :key="item.key" class="ticket" :class="{ selected: item.key === selected && !composing }" @click="choose(item.key)">
          <strong>{{ item.title }}</strong><span>{{ item.key }} <span v-if="item.status">· {{ states[item.status] || item.status }}</span></span>
        </button>
        <p v-if="!loading && !visible.length" class="empty">{{ query ? '没有匹配的需求' : '从一个小需求开始' }}</p>
        <a :href="legacyUrl('/tickets')" class="all-tickets" @click="prepareLegacy(pkey)">查看全部工单</a>
      </aside>
      <div class="desk">
        <RequirementBatch v-if="batch" :pkey="pkey" @created="batchCreated" />
        <form v-else-if="composing" class="compose" @submit.prevent="create">
          <h2>这次要处理什么？</h2><button type="button" class="text-button" @click="batch=true">多项相关需求一起处理</button>
          <label class="field">任务名称<input v-model="title" required placeholder="例如：导出金额跟随税率配置" /></label>
          <label class="field">任务类型<select v-model="taskType"><option v-for="(label,key) in taskTypes" :key="key" :value="key">{{label}}</option></select></label>
          <label class="field">需求与项目说明<textarea v-model="body" rows="8" placeholder="描述现在的情况、希望改成什么。可以补充实际子项目目录、启动方式和不能改变的规则。" /></label>
          <label class="field">验收目标<textarea v-model="acceptance" rows="3" placeholder="每行一项可核对的结果，例如：同一标书的金额单位在页面和导出中一致。" /></label>
          <div class="actions"><button class="btn btn-primary" :disabled="!!busy || !title.trim()">{{ busy === 'create' ? '保存中…' : '保存需求' }}</button><button v-if="selected" type="button" class="btn" @click="composing = false">返回</button></div>
        </form>
        <template v-else-if="detail">
          <header class="task-heading"><span class="muted">{{ detail.ticket.key }}</span><h2>{{ detail.ticket.title }}</h2></header>
          <section class="responsibility" aria-label="处理与交接">
            <dl><div><dt>类型</dt><dd>{{taskTypes[detail.ticket.type || ''] || '未登记'}}</dd></div><div><dt>负责人</dt><dd>{{detail.team_assignment?.assignee || detail.ticket.assignee || '待分配'}}</dd></div><div><dt>复核人</dt><dd>{{detail.team_assignment?.reviewer || '待分配'}}</dd></div><div><dt>当前进展</dt><dd>{{detail.stage?.label || states[detail.ticket.status || ''] || '待处理'}}</dd></div></dl>
            <div class="actions"><a class="btn" :href="legacyUrl('/team/ticket/'+encodeURIComponent(detail.ticket.key))" @click="prepareLegacy(pkey)">分配与复核</a><a class="btn" :href="legacyUrl('/t/'+encodeURIComponent(detail.ticket.key))" @click="prepareLegacy(pkey)">交接与验收</a></div>
          </section>
          <details v-if="detail.ticket.body" class="requirement"><summary>需求原文</summary><pre>{{ detail.ticket.body }}</pre></details>
          <p v-if="detail.parent"><button class="text-button" @click="choose(detail.parent.key)">返回 {{ detail.parent.title }}</button></p>
          <section v-if="detail.epic" class="panel"><h3>子任务与依赖</h3><p v-if="detail.epic.paused" class="error">{{ detail.epic.paused }}</p><div v-for="child in detail.epic.children" :key="child.key" class="child-task"><button class="text-button" @click="choose(child.key)">{{ child.title }}</button><span>{{ states[child.status] || child.status }}</span><span v-if="child.after.length" class="muted">依赖 {{ child.after.join('、') }}</span></div><div class="actions"><button class="btn" :disabled="!!busy" @click="perform('epic-release')">推进下一批</button><button class="btn" :disabled="!!busy" @click="perform('epic-resume')">恢复协作</button></div></section>
          <div v-else class="toolbar">
            <label class="field executor">执行器<select v-model="agent" :disabled="!!busy || active"><option value="">项目默认</option><option v-for="a in agents" :key="a.name" :value="a.name">{{ a.title }}</option></select></label>
            <div class="actions">
              <button v-for="mode in ['analyze', 'plan', 'fix']" :key="mode" class="btn" :disabled="!!busy || active" @click="start(mode)">{{ busy === mode ? '启动中…' : ({ analyze: '分析需求', plan: '生成方案', fix: '开始开发' }[mode]) }}</button>
              <button class="btn" :disabled="!!busy || active" @click="perform('auto')">继续自动处理</button><button class="btn" @click="verify">验证现有改动</button>
            </div>
          </div>
          <div class="run-heading"><h3>执行记录</h3><button class="text-button" :disabled="!!busy" @click="refresh">刷新</button></div>
          <div v-if="detail.runs.length" class="runs" aria-label="执行记录">
            <button v-for="item in detail.runs" :key="item.id" class="run" :class="{ current: item.id === run?.id }" @click="loadRun(item.id)">{{ modes[item.mode] || item.mode }} #{{ item.id }} <span :class="{ running: ['running', 'queued'].includes(item.status) }">{{ states[item.status] || item.status }}</span></button>
          </div>
          <p v-else class="empty">需求已保存。先分析需求或生成方案。</p>
          <template v-if="run">
            <ol v-if="run.preparation?.steps.length" class="preparation" aria-label="任务进度">
              <li v-for="step in run.preparation.steps" :key="step.name" :class="step.state"><span class="step-icon">{{step.state==='done'?'✓':step.state==='failed'?'!':step.state==='cancelled'?'—':'…'}}</span><div><strong>{{step.name}}</strong><p v-if="step.detail">{{step.detail}}</p></div></li>
            </ol>
            <button v-if="run.continuation?.next_run" class="btn primary" @click="loadRun(run.continuation.next_run)">查看后续任务 #{{run.continuation.next_run}}</button>
            <div class="actions run-actions"><button v-if="['running','queued'].includes(run.status)" class="btn" :disabled="!!busy" @click="perform('cancel')">停止运行</button><button v-if="run.can_retry" class="btn" :disabled="!!busy" @click="perform('retry')">重试本次运行</button><button v-if="run.mode==='fix' && run.status==='done'" class="btn" :disabled="!!busy || run.recheck?.running" @click="perform('recheck',{kind:'tests'})">{{run.recheck?.running?'正在验证…':'运行项目检查'}}</button><button v-if="run.mode==='fix' && run.status==='done' && !run.decision" class="btn" :disabled="!!busy" @click="perform('decide',{decision:'accept'})">采纳当前改动</button><button v-if="run.decision?.startsWith('accept')" class="btn" :disabled="!!busy" @click="previewRun">启动预览</button><a v-if="preview?.url" class="btn" :href="appUrl(preview.url)" target="_blank" rel="noopener">打开预览</a></div>
            <p v-if="preview?.preview.state === 'starting'" role="status">预览正在启动…</p><p v-if="preview?.preview.why || preview?.preview.error" class="error">{{preview.preview.why || preview.preview.error}}</p>

            <nav class="tabs" aria-label="运行产物"><button v-for="[key, label] in [['result','结果'], ['diff','代码差异'], ['verification','验证回执'], ['output','执行日志']]" :key="key" :class="{ current: tab === key }" @click="tab = key!">{{ label }}</button></nav>
            <DocumentText v-if="tab === 'result' && run.result" class="artifact" :text="run.result" />
            <pre v-else-if="tab === 'diff' && run.diff" class="artifact diff"><span v-for="(line, index) in run.diff.split('\n')" :key="index" class="diff-line" :class="{ added: line.startsWith('+'), removed: line.startsWith('-'), hunk: line.startsWith('@@') }">{{ line }}{{ '\n' }}</span></pre>
            <pre v-else-if="tab === 'verification' && run.verification" class="artifact">{{ JSON.stringify(run.verification, null, 2) }}</pre>
            <pre v-else-if="tab === 'output' && run.output" class="artifact logs">{{ run.output }}</pre>
            <p v-else class="empty">{{ tab === 'verification' ? '暂无验证回执。执行结束不代表验证通过。' : tab === 'diff' ? '本次运行暂无代码差异。' : ['queued','running'].includes(run.status) ? '正在执行，结果会自动更新。' : '本次运行未产生这项内容。' }}</p>
          </template>
          <form class="discussion" @submit.prevent="perform('comments',{body:comment})"><label class="field">补充下一步<textarea v-model="comment" placeholder="描述下一步；推送时写明仓库地址和分支" /></label><button class="btn" :disabled="!!busy || !comment.trim()">{{active?'补充并排队继续':'评论并继续'}}</button></form>
          <details v-if="detail.events?.length" class="history"><summary>完整操作记录</summary><article v-for="(event,i) in detail.events" :key="i"><strong>{{event.author}} · {{event.created}}</strong><DocumentText :text="event.body || ''" /></article></details>
        </template>
        <p v-else-if="!loading" class="empty">选择一项需求，或创建新需求。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.preparation {list-style:none;padding:0;display:grid;gap:12px;margin:20px 0}.preparation li{display:flex;gap:10px;align-items:flex-start}.step-icon{width:24px;height:24px;border-radius:50%;background:var(--line);text-align:center;flex-shrink:0}.preparation .done .step-icon{color:#167044;background:#e9f6ee}.preparation .failed .step-icon{color:#b42318;background:#fff0ee}.preparation .running .step-icon{color:var(--primary);background:#eef3ff}.preparation p{margin:4px 0 0;overflow-wrap:anywhere;white-space:pre-wrap}

.run-actions { margin:16px 0; }.discussion { border-top:1px solid var(--line); padding-top:20px; margin-top:28px; }.history { margin-top:20px; }.child-task { display:flex; flex-wrap:wrap; gap:16px; margin:12px 0; }
.heading,.task-heading,.run-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.heading { margin-bottom:24px; }.heading h1 { margin:0; }
.workbench { display:grid; grid-template-columns:260px minmax(0,1fr); background:var(--panel); border:1px solid var(--line); border-radius:10px; min-height:65vh; overflow:hidden; }
.queue { padding:16px 12px; border-right:1px solid var(--line); background:#fafbfc; }
.search { width:100%; border:1px solid var(--line); border-radius:6px; padding:9px 10px; margin-bottom:14px; }
.ticket { width:100%; text-align:left; border:0; border-radius:6px; background:transparent; padding:13px 10px; cursor:pointer; margin-bottom:5px; }
.ticket strong { display:block; font-size:14px; font-weight:550; line-height:1.5; overflow-wrap:anywhere; }.ticket>span { display:block; color:var(--sub); font-size:12px; margin-top:6px; }.ticket:hover,.ticket.selected { background:var(--accent-soft); }.ticket.selected strong { color:var(--accent); }
.all-tickets { display:block; padding:14px 10px; font-size:13px; }
.responsibility{padding:16px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:16px}.responsibility dl{display:flex;gap:16px 32px;flex-wrap:wrap;margin:0 0 14px}.responsibility dt{font-size:12px;color:var(--sub)}.responsibility dd{margin:4px 0 0;overflow-wrap:anywhere}
.desk { min-width:0; padding:24px; }.compose { max-width:680px; }.compose h2 { margin-top:0; font-size:22px; }.task-heading { display:block; }.task-heading h2 { margin:5px 0 20px; font-size:22px; overflow-wrap:anywhere; }
.requirement { border-bottom:1px solid var(--line); padding:0 0 16px; margin-bottom:18px; }.requirement summary { cursor:pointer; color:var(--sub); }.requirement pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; }
.toolbar { display:flex; flex-wrap:wrap; align-items:end; gap:14px; }.executor { min-width:160px; margin:0; }.actions { display:flex; gap:8px; flex-wrap:wrap; }.actions .btn { font-size:13px; }
.run-heading { margin-top:30px; }.run-heading h3 { margin:0; }.text-button { border:0; background:transparent; color:var(--accent); cursor:pointer; }
.runs { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 22px; }.run { background:var(--panel); border:1px solid var(--line); padding:7px 10px; border-radius:5px; cursor:pointer; font-size:12px; }.run span { color:var(--sub); margin-left:8px; }.run.current { border-color:var(--accent); }.run span.running { color:var(--accent); }
.diff-line { display:block; white-space:pre-wrap; }.diff-line.added { background:#e4f4e9; color:#145b32; }.diff-line.removed { background:#fde8e8; color:#9b2929; }.diff-line.hunk { color:var(--accent); }
.tabs { display:flex; gap:20px; border-bottom:1px solid var(--line); }.tabs button { border:0; border-bottom:2px solid transparent; background:transparent; padding:12px 0; cursor:pointer; color:var(--sub); font-size:13px; }.tabs button.current { border-bottom-color:var(--accent); color:var(--accent); }
.artifact { overflow-wrap:anywhere; margin:0; padding:22px 0; }.artifact:not(.document) { white-space:pre-wrap; font:13px/1.8 ui-monospace,monospace; }.diff,.logs { background:#f7f9fb; padding:18px; margin-top:16px; font-size:12px; }
@media(max-width:1000px) { .workbench { grid-template-columns:210px minmax(0,1fr); }.desk { padding:20px; } }
@media(max-width:760px) { .workbench { grid-template-columns:1fr; }.queue { border-right:0; border-bottom:1px solid var(--line); max-height:230px; overflow:auto; }.desk { padding:18px; }.tabs { gap:16px; }.task-heading h2 { font-size:20px; } }
</style>
