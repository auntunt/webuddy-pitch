<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { get } from '../api/client'
import ExperienceRecords from '../components/ExperienceRecords.vue'
import DocumentText from '../components/DocumentText.vue'
const props = defineProps<{ pkey: string }>()
const pages = ref<{ id: string; title: string; status: string; summary: string }[]>([])
const section = ref('pages')
const statusLabel = (value: string) => ({pending:'待构建',draft:'待复核',confirmed:'已确认',stale:'需更新',writing:'构建中',todo:'待构建',done:'已生成',error:'构建失败'}[value] || value)
const query = ref(''), error = ref(''), loading = ref(false)
const selected = ref<{ id: string; text: string; status: string } | null>(null)
const readableText = computed(() => (selected.value?.text || '')
  .replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '')
  .replace(/^<!-- tmh:facts:(?:start[^\n]*|end) -->\r?\n?/gm, ''))
let request = 0
async function load() {
  const n = ++request; error.value = ''; selected.value = null; loading.value = true
  try { const result = await get<{ pages: typeof pages.value }>(`/api/projects/${encodeURIComponent(props.pkey)}/kb?q=${encodeURIComponent(query.value)}`); if (n === request) pages.value = result.pages }
  catch (e) { if (n === request) error.value = String(e) }
  finally { if (n === request) loading.value = false }
}
async function read(id: string) {
  const n = ++request; error.value = ''
  try { const page = await get<typeof selected.value>(`/api/projects/${encodeURIComponent(props.pkey)}/kb/page?id=${encodeURIComponent(id)}`); if (n === request) selected.value = page }
  catch (e) { if (n === request) error.value = String(e) }
}
watch(() => props.pkey, load, { immediate: true })
</script>
<template><h1>项目知识</h1><nav class="knowledge-tabs" aria-label="知识类型"><button class="btn" :class="{'btn-primary':section==='pages'}" @click="section='pages'">知识页</button><button class="btn" :class="{'btn-primary':section==='records'}" @click="section='records'">经验记录</button></nav><ExperienceRecords v-if="section==='records'" :pkey="pkey"/><template v-else><p v-if="error" class="error">{{ error }}</p><form class="searchbar" @submit.prevent="load"><label class="field">搜索知识<input v-model="query" placeholder="业务规则、接口、表或功能" /></label><button class="btn">搜索</button></form><p v-if="loading">正在读取…</p><div class="knowledge-layout"><aside><button v-for="page in pages" :key="page.id" class="knowledge-row" :class="{ selected: page.id === selected?.id }" @click="read(page.id)"><strong>{{ page.title }}</strong><span class="muted">{{ statusLabel(page.status) }}</span><p v-if="page.summary">{{ page.summary }}</p></button><p v-if="!pages.length && !loading" class="empty">暂无匹配知识。<router-link :to="`/p/${encodeURIComponent(pkey)}/settings`">构建知识库</router-link></p></aside><section class="panel" v-if="selected"><span class="tag">{{ statusLabel(selected.status) }}</span><DocumentText :text="readableText" /><details class="source"><summary>完整原文</summary><pre>{{ selected.text }}</pre></details></section></div></template></template>
<style scoped>.source{border-top:1px solid var(--line);padding-top:16px}.source pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.knowledge-tabs{display:flex;gap:24px;margin:20px 0;border-bottom:1px solid var(--line)}.knowledge-tabs .btn{padding:10px 0;border:0;border-bottom:2px solid transparent;border-radius:0;background:none;color:var(--sub)}.knowledge-tabs .btn-primary{color:var(--accent);border-bottom-color:var(--accent)}.searchbar { display:flex; align-items:center; gap:12px; }.searchbar .field { flex:1; max-width:500px; }.knowledge-layout { display:grid; grid-template-columns:minmax(200px,280px) minmax(0,1fr); gap:24px; }.knowledge-layout>aside{max-height:calc(100dvh - 270px);overflow:auto;position:sticky;top:20px}.knowledge-layout>.panel{min-width:0;align-self:start}.knowledge-row { background:transparent; border:0; border-bottom:1px solid var(--line); padding:16px 10px; width:100%; text-align:left; cursor:pointer; }.knowledge-row strong { display:block; }.knowledge-row.selected { background:var(--accent-soft); }.knowledge-row p { color:var(--sub); font-size:13px; }@media(max-width:760px){.knowledge-layout{grid-template-columns:1fr;}.knowledge-layout>aside{max-height:240px;position:static;}}</style>
