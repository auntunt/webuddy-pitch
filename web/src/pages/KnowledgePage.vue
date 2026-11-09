<script setup lang="ts">
import { ref, watch } from 'vue'
import { get } from '../api/client'
import DocumentText from '../components/DocumentText.vue'
const props = defineProps<{ pkey: string }>()
const pages = ref<{ id: string; title: string; status: string; summary: string }[]>([])
const query = ref(''), error = ref(''), loading = ref(false)
const selected = ref<{ id: string; text: string; status: string } | null>(null)
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
<template><h1>项目知识</h1><p v-if="error" class="error">{{ error }}</p><form class="searchbar" @submit.prevent="load"><label class="field">搜索知识<input v-model="query" placeholder="业务规则、接口、表或功能" /></label><button class="btn">搜索</button></form><p v-if="loading">正在读取…</p><div class="knowledge-layout"><aside><button v-for="page in pages" :key="page.id" class="knowledge-row" :class="{ selected: page.id === selected?.id }" @click="read(page.id)"><strong>{{ page.title }}</strong><span class="muted">{{ page.status }}</span><p v-if="page.summary">{{ page.summary }}</p></button><p v-if="!pages.length && !loading" class="empty">暂无匹配知识。可在项目设置中构建知识库。</p></aside><section class="panel" v-if="selected"><span class="tag">{{ selected.status }}</span><DocumentText :text="selected.text" /></section></div></template>
<style scoped>.searchbar { display:flex; align-items:center; gap:12px; }.searchbar .field { flex:1; max-width:500px; }.knowledge-layout { display:grid; grid-template-columns:minmax(200px,280px) minmax(0,1fr); gap:24px; }.knowledge-row { background:transparent; border:0; border-bottom:1px solid var(--line); padding:16px 10px; width:100%; text-align:left; cursor:pointer; }.knowledge-row strong { display:block; }.knowledge-row.selected { background:var(--accent-soft); }.knowledge-row p { color:var(--sub); font-size:13px; }@media(max-width:760px){.knowledge-layout{grid-template-columns:1fr;}}</style>
