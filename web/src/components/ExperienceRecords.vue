<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { get, post } from '../api/client'
import { legacyUrl } from '../app'
import DocumentText from './DocumentText.vue'
const props = defineProps<{ pkey: string }>()
const labels = { symptom: '适用场景', cause: '原因与判断', fix: '做法', verify: '验证依据', anti: '注意事项与不适用情况' }
type Fields = Record<keyof typeof labels, string>
type Lesson = Partial<Fields> & { id: string; title: string; status: string; by?: string; created?: string; source_project: string; scope_label: string; auto_use: boolean; ticket?: string }
const lessons = ref<Lesson[]>([]), query = ref(''), error = ref(''), notice = ref(''), title = ref('')
const fields = ref<Fields>({symptom:'',cause:'',fix:'',verify:'',anti:''})
const adding = ref(false), busy = ref(false), loading = ref(false)
let generation=0
const states:Record<string,string>={candidate:'待确认',active:'已确认',probation:'观察中',retired:'已停用'}
async function load() {
  const n=++generation;loading.value=true;error.value=''
  try { const result=await get<{lessons:Lesson[]}>(`/api/memory?project=${encodeURIComponent(props.pkey)}&section=lessons&q=${encodeURIComponent(query.value)}`);if(n===generation)lessons.value=result.lessons }
  catch(e){if(n===generation)error.value=String(e)}finally{if(n===generation)loading.value=false}
}
async function save() {
  if(busy.value)return
  const project=props.pkey;busy.value=true;error.value='';notice.value=''
  try {
    await post('/api/memory',{action:'lesson_create',project,title:title.value,fields:fields.value})
    if(project!==props.pkey)return
    adding.value=false;title.value='';fields.value={symptom:'',cause:'',fix:'',verify:'',anti:''};query.value=''
    await load();notice.value='经验已记录，确认后用于本项目相近任务。'
  }catch(e){if(project===props.pkey)error.value=String(e)}finally{busy.value=false}
}
watch(()=>props.pkey,()=>{lessons.value=[];query.value='';notice.value='';adding.value=false;title.value='';fields.value={symptom:'',cause:'',fix:'',verify:'',anti:''};load()},{immediate:true})
onUnmounted(()=>generation++)
</script>
<template>
<div class="record-toolbar"><form @submit.prevent="load"><input v-model="query" aria-label="搜索经验" placeholder="搜索经验" /><button class="btn">搜索</button></form><button class="btn btn-primary" @click="adding=!adding">记录经验</button><a class="btn" :href="legacyUrl('/memory/lessons')">确认与管理</a></div>
<p v-if="error" class="error" role="alert">{{error}}</p><p v-if="notice" class="note" role="status">{{notice}}</p>
<form v-if="adding" class="panel" @submit.prevent="save"><label class="field">经验标题<input v-model="title" required /></label><label v-for="(label,key) in labels" :key="key" class="field">{{label}}<textarea v-model="fields[key]" :required="key==='symptom'||key==='fix'" :placeholder="key==='verify'?'填写工单、运行编号、文件或实际检查结果；未验证的部分请注明。':''" /></label><button class="btn btn-primary" :disabled="busy">{{busy?'正在保存…':'保存记录'}}</button></form>
<p v-if="loading" role="status">正在读取…</p><p v-else-if="!lessons.length" class="empty">暂无匹配经验。</p>
<article v-for="item in lessons" :key="item.source_project+':'+item.id" class="panel"><div class="record-heading"><h2>{{item.title}}</h2><span class="tag">{{states[item.status] || item.status}}</span></div><p class="muted">{{item.scope_label}} · {{item.source_project}} · {{item.by}}<span v-if="item.ticket"> · {{item.ticket}}</span></p><template v-for="(label,key) in labels" :key="key"><section v-if="item[key]"><h3>{{label}}</h3><DocumentText :text="item[key]!" /></section></template><p v-if="item.auto_use" class="note">相近任务可复用</p></article>
</template>
<style scoped>.record-toolbar,.record-toolbar form,.record-heading{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.record-toolbar{margin:20px 0}.record-toolbar input{max-width:280px;padding:10px 12px;border:1px solid var(--line);border-radius:6px;font:inherit;background:var(--panel)}.record-heading{justify-content:space-between}.record-heading h2{margin:0}.panel{max-width:900px}.panel h3{font-size:14px;margin:20px 0 0}.panel :deep(.document){padding:6px 0}.panel textarea{min-height:90px}</style>
