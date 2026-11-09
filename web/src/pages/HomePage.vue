<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { app, loadApp, selectProject } from '../app'
import { get, post } from '../api/client'
const router = useRouter()
const adding = ref(false), busy = ref(false), error = ref(''), mode = ref('local')
const key = ref(''), name = ref(''), root = ref(''), url = ref(''), brief = ref('')
const importStatus = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
function open(key: string) { selectProject(key); router.push(`/p/${encodeURIComponent(key)}/work`) }
async function poll(job: string) {
  try {
    const data = await get<{ status: string; step?: string; error?: string; key: string }>(`/api/projects/import/${job}`)
    importStatus.value = data.step || data.status
    if (data.status === 'done') { busy.value = false; await loadApp(); open(data.key) }
    else if (data.status === 'failed') { busy.value = false; error.value = data.error || '导入失败，请检查仓库地址和权限。' }
    else timer = setTimeout(() => poll(job), 1500)
  } catch (e) { error.value = String(e); busy.value = false }
}
async function add() {
  busy.value = true; error.value = ''
  try {
    if (mode.value === 'git') {
      const result = await post<{ job: string }>('/api/projects/import', { key: key.value, name: name.value, source: 'git', url: url.value })
      await poll(result.job); return
    }
    if (mode.value === 'new') await post('/api/projects/bootstrap', { key: key.value, name: name.value, brief: brief.value, template: 'web' })
    else await post('/api/projects', { key: key.value, name: name.value, root: root.value, description: brief.value })
    await loadApp(); open(key.value.toUpperCase()); busy.value = false
  } catch (e) { error.value = String(e); busy.value = false }
}
onUnmounted(() => { if (timer) clearTimeout(timer) })
</script>
<template>
  <header class="heading"><h1>项目</h1><button class="btn btn-primary" @click="adding = !adding">接入项目</button></header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <form v-if="adding || !app.projects.length" class="panel project-form" @submit.prevent="add">
    <h2>开始一个项目</h2>
    <label class="field">接入方式<select v-model="mode" :disabled="busy"><option value="local">已有本地目录</option><option value="git">Git 仓库</option><option value="new">新建网页项目</option></select></label>
    <div class="form-grid"><label class="field">项目名称<input v-model="name" required :disabled="busy" /></label><label class="field">项目代号<input v-model="key" pattern="[A-Za-z][A-Za-z0-9]{0,9}" required maxlength="10" placeholder="例如 HR" :disabled="busy" /></label></div>
    <label v-if="mode === 'local'" class="field">服务运行电脑上的项目目录<input v-model="root" required placeholder="例如 D:\Projects\my-app" :disabled="busy" /></label>
    <label v-if="mode === 'git'" class="field">仓库地址<input v-model="url" required placeholder="https://… 或 SSH 地址" :disabled="busy" /></label>
    <label v-else class="field">项目说明<textarea v-model="brief" :required="mode === 'new'" placeholder="项目用途、实际开发目录和需要遵守的规则" :disabled="busy" /></label>
    <button class="btn btn-primary" :disabled="busy">{{ busy ? '正在接入…' : '创建项目' }}</button><p v-if="importStatus" role="status">{{ importStatus }}</p>
  </form>
  <div class="projects"><button v-for="p in app.projects" :key="p.key" class="project" @click="open(p.key)"><h2>{{ p.name || p.key }}</h2><span class="muted">{{ p.key }}</span><span class="arrow" aria-hidden="true">→</span></button></div>
</template>
<style scoped>.heading { display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; }.heading h1 { margin:0; }.project-form { max-width:720px; }.project-form h2 { margin-top:0; }.form-grid { display:grid; grid-template-columns:2fr 1fr; gap:16px; }.projects { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:16px; }.project { position:relative; text-align:left; padding:24px; background:var(--panel); border:1px solid var(--line); border-radius:8px; cursor:pointer; }.project:hover { border-color:var(--accent); }.project h2 { margin:0 0 12px; }.arrow { position:absolute; right:24px; bottom:24px; color:var(--accent); }</style>
