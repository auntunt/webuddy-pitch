<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { get, post } from '../api/client'
import { loadApp, legacyUrl } from '../app'
type Agent = { name: string; title: string; bin: string; available: boolean; engine: string; models: string[][]; defaults: Record<string,string>; timeout: number; environment: Record<string,string> }
type Stage = { id: string; kind: string; command: string; required: boolean; timeout: number; depends_on?: string[]; report?: { format: string; path: string }; criteria?: Record<string,string[]> }
type Tests = { revision: string; can_edit: boolean; profile: null | { executor: string; stages: Stage[]; require_all_criteria: boolean } }
const props = defineProps<{ pkey?: string }>()
const settings = ref<{ agents: Agent[]; revision: string; can_edit: boolean } | null>(null)
const tests = ref<Tests | null>(null)
const command = ref(''), ready = ref('/'), detected = ref(''), error = ref(''), notice = ref(''), busy = ref('')
const selected = ref<Agent | null>(null), model = ref(''), connection = ref<Record<string,unknown> | null>(null)
const survey = ref<Record<string,unknown> | null>(null)
let version = 0, poller: ReturnType<typeof setTimeout> | undefined
const prefix = () => `/api/projects/${encodeURIComponent(props.pkey || '')}`
async function load() {
  const n = ++version; error.value = ''; notice.value = ''; selected.value = null; tests.value = null; survey.value = null
  if (poller) clearTimeout(poller)
  try {
    const data = await get<typeof settings.value>('/api/agent-settings'); if (n !== version) return; settings.value = data
    if (props.pkey) {
      const [preview, contract, state] = await Promise.all([get<{cmd:string;detected:string;ready:string}>(prefix()+'/preview-conf'),get<Tests>(prefix()+'/tests'),get<Record<string,unknown>>(prefix()+'/survey')])
      if (n !== version) return
      command.value = preview.cmd; detected.value = preview.detected; ready.value = preview.ready; tests.value = contract; survey.value = state
    }
  } catch(e) { if(n===version) error.value=String(e) }
}
async function action(key: string, fn: () => Promise<unknown>) {
  if(busy.value) return; busy.value=key; error.value=''; notice.value=''
  try { await fn() } catch(e) { error.value=String(e) } finally { busy.value='' }
}
function edit(agent: Agent) { selected.value=JSON.parse(JSON.stringify(agent)); model.value=agent.defaults.fix || ''; connection.value=null }
async function saveAgent() {
  const a=selected.value!; const models=a.models.map(pair=>[...pair]); const defaults={...a.defaults}
  if(model.value.trim()) { if(!models.some(pair=>pair[0]===model.value.trim())) models.push([model.value.trim(),model.value.trim()]); defaults.fix=model.value.trim() } else delete defaults.fix
  settings.value=await post('/api/agent-settings',{action:'update',name:a.name,revision:settings.value!.revision,config:{title:a.title,bin:a.bin,models,defaults,timeout:a.timeout,environment:a.environment}})
  selected.value=null;notice.value='执行器配置已保存';await loadApp()
}
async function saveTests() {
  tests.value=await post(prefix()+'/tests',{revision:tests.value!.revision,profile:tests.value!.profile}); notice.value='测试流程已保存';tests.value=await get(prefix()+'/tests')
}
function addStage() {
  if(!tests.value) return
  if(!tests.value.profile) tests.value.profile={executor:'local',stages:[],require_all_criteria:false}
  const list=tests.value.profile.stages;let i=list.length+1;while(list.some(s=>s.id==='step'+i))i++
  list.push({id:'step'+i,kind:'unit',command:'',required:true,timeout:300,report:{format:'junit',path:'test-results.xml'}})
}
async function checkSurvey() {
  const n=version;const state=await get<Record<string,unknown>>(prefix()+'/survey');if(n!==version)return;survey.value=state
  if(['starting','building','running','stopping'].includes(String(state.state))) poller=setTimeout(()=>checkSurvey().catch(e=>error.value=String(e)),3000)
}
watch(()=>props.pkey,load,{immediate:true})
onUnmounted(()=>{version++;if(poller)clearTimeout(poller)})
</script>
<template>
<h1>{{ pkey ? '项目与执行设置' : '执行器设置' }}</h1><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="note" role="status">{{ notice }}</p>
<section class="panel"><h2>AI 执行器</h2><div class="agent-row" v-for="a in settings?.agents" :key="a.name"><div><strong>{{ a.title }}</strong><p class="muted">{{ a.available ? '已检测到程序' : '未找到程序' }}</p></div><div class="actions"><button class="btn" @click="edit(a)">配置</button><button class="btn" :disabled="!!busy || !a.available || !settings?.can_edit" @click="action('probe',async()=>{connection=await post('/api/agent-test',{name:a.name})})">{{ busy==='probe' ? '检查中…' : '测试连接' }}</button></div></div>
<form v-if="selected" @submit.prevent="action('agent',saveAgent)" class="editor"><h3>{{ selected.title }}</h3><label class="field">执行命令或绝对路径<input v-model="selected.bin" :disabled="!settings?.can_edit" /></label><label class="field">开发模型（空白使用执行器默认）<input v-model="model" :disabled="!settings?.can_edit" /></label><label class="field">运行时限（秒）<input type="number" v-model.number="selected.timeout" min="1" max="86400" :disabled="!settings?.can_edit" /></label><button class="btn btn-primary" :disabled="!!busy || !settings?.can_edit">保存配置</button></form>
<template v-if="connection"><p :class="connection.ok ? 'note' : 'error'">{{ connection.ok ? '模型连接成功' : '模型连接未通过' }}</p><pre class="raw">{{ JSON.stringify(connection,null,2) }}</pre></template><p class="muted">Cursor 登录可使用 Windows 开始菜单中的“登录 Cursor”。<a :href="legacyUrl('/settings')">高级连接与访问配置</a></p></section>
<template v-if="pkey"><section class="panel"><h2>开发环境</h2><form @submit.prevent="action('preview',async()=>{await post(prefix()+'/preview-conf',{cmd:command,ready});notice='启动命令已保存'})"><label class="field">启动命令<input v-model="command" :placeholder="detected || '例如 npm run dev -- --port {port}'" /></label><label class="field">就绪检查路径<input v-model="ready" placeholder="/" /></label><button class="btn" :disabled="!!busy">保存启动配置</button></form></section>
<section class="panel"><h2>项目检查流程</h2><p class="muted">依次准备依赖、构建和运行相关测试。命令在本次代码工作树中执行。</p><template v-if="tests"><label v-if="tests.profile" class="field">执行位置<select v-model="tests.profile.executor" :disabled="!tests.can_edit"><option value="local">本机</option><option value="testbox">已配置的测试机</option></select></label><fieldset v-for="(stage,i) in tests.profile?.stages" :key="i" class="stage" :disabled="!tests.can_edit"><div class="form-grid"><label class="field">阶段代号<input v-model="stage.id" required /></label><label class="field">类型<select v-model="stage.kind"><option v-for="kind in ['setup','build','static','unit','integration','e2e','security','performance','migration','mutation','cleanup']" :key="kind">{{ kind }}</option></select></label></div><label class="field">命令<input v-model="stage.command" required /></label><div class="form-grid"><label class="field">超时（秒）<input type="number" v-model.number="stage.timeout" min="1" max="7200" /></label><label><input type="checkbox" v-model="stage.required" /> 必须通过</label></div><template v-if="stage.report"><label class="field">用例报告路径<input v-model="stage.report.path" /></label><label class="field">报告格式<select v-model="stage.report.format"><option value="junit">JUnit XML</option><option value="json">JSON</option></select></label></template></fieldset><div class="actions"><button class="btn" :disabled="!tests.can_edit" @click="addStage">添加阶段</button><button class="btn btn-primary" :disabled="!!busy || !tests.can_edit || !tests.profile" @click="action('tests',saveTests)">保存检查流程</button></div></template></section>
<section class="panel"><h2>项目知识构建</h2><p>当前状态：{{ survey?.state || '未读取' }}</p><div class="actions"><button class="btn" :disabled="!!busy || ['starting','building','running','stopping'].includes(String(survey?.state))" @click="action('survey',async()=>{survey=await post(prefix()+'/survey',{});await checkSurvey()})">构建知识库</button><button class="btn" :disabled="!!busy" @click="action('survey-stop',async()=>{survey=await post(prefix()+'/survey/stop',{})})">停止构建</button><button class="btn" @click="action('survey-refresh',checkSurvey)">刷新</button></div></section></template>
</template>
<style scoped>.panel { max-width:860px; }.panel h2 { margin-top:0; }.agent-row { display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--line); padding:12px 0; gap:12px; }.agent-row p { margin:4px 0; }.actions { display:flex; flex-wrap:wrap; gap:8px; }.editor { margin:20px 0; padding:20px; background:var(--bg); }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.stage { margin:18px 0; padding:18px; border:1px solid var(--line); border-radius:8px; }.raw { white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; }@media(max-width:760px){.form-grid{grid-template-columns:1fr}.agent-row{align-items:start;flex-direction:column}}</style>
