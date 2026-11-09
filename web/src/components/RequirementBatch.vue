<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { get, post, tenantBase } from '../api/client'
type Question = { slot: string; q: string; options?: string[] }
type Intake = { id: string; state: string; title?: string; items: { text?: string; title?: string; questions: Question[]; ac?: unknown[] }[]; spec_q?: Question[]; spec?: Record<string,unknown>; tickets: string[]; epic?: string }
const props=defineProps<{pkey:string}>()
const emit=defineEmits<{created:[key:string]}>()
const text=ref(''), session=ref<Intake|null>(null), error=ref(''), busy=ref(false), wave=ref(2)
const answers=ref<Record<string,Record<string,string>>>({}), dependencies=ref<Record<string,string>>({})
const key=()=>`${tenantBase()}:batch:${props.pkey}`
let timer:ReturnType<typeof setTimeout>|undefined, generation=0
const questions=computed(()=>session.value ? [...session.value.items.flatMap((it,i)=>(it.questions||[]).map(q=>({...q,item:String(i)}))),...(session.value.spec_q||[]).map(q=>({...q,item:'spec'}))] : [])
function accept(value:Intake) { session.value=value; for(const q of questions.value) { answers.value[q.item] ||= {}; answers.value[q.item]![q.slot] ||= '' } }
async function refresh(id:string) {
  const n=generation
  try { const value=await get<Intake>(`/api/intake/${id}`); if(n!==generation)return;accept(value);if(value.state==='understanding')timer=setTimeout(()=>refresh(id),2000) }
  catch(e){if(n===generation)error.value=String(e)}
}
async function act(action:string) {
  if(busy.value)return;busy.value=true;error.value='';const n=generation
  try {
    let value:Intake
    if(action==='start') {
      if(text.value.length>4000)throw new Error('一次需求最多 4000 字，请分批提交，原文已保留。')
      value=await post(`/api/projects/${encodeURIComponent(props.pkey)}/intake`,{text:text.value,big:true})
    } else {
      const deps=Object.fromEntries(Object.entries(dependencies.value).filter(([,v])=>v.trim()).map(([i,v])=>[i,v.split(/[,，\s]+/).map(s=>Number(s)-1)]))
      value=await post(`/api/intake/${session.value!.id}`,action==='answer'?{action,answers:answers.value}:{action,deps,wave:wave.value})
    }
    if(n!==generation)return
    localStorage.setItem(key(),value.id);accept(value)
    if(value.state==='understanding')timer=setTimeout(()=>refresh(value.id),2000)
    if(value.state==='confirmed') { localStorage.removeItem(key());emit('created',value.epic||value.tickets[0]||'') }
  } catch(e){if(n===generation)error.value=String(e)}finally{busy.value=false}
}
watch(()=>props.pkey,()=>{generation++;if(timer)clearTimeout(timer);session.value=null;answers.value={};dependencies.value={};const saved=localStorage.getItem(key());if(saved)refresh(saved)},{immediate:true})
onUnmounted(()=>{generation++;if(timer)clearTimeout(timer)})
</script>
<template><section class="batch"><h2>多项需求协作</h2><p v-if="error" class="error" role="alert">{{ error }}</p><template v-if="!session"><label class="field">需求描述<textarea v-model="text" rows="8" placeholder="一次描述多个相关改动。系统先拆分、澄清，再按依赖分批推进。" /></label><button class="btn btn-primary" :disabled="busy || !text.trim()" @click="act('start')">{{ busy?'正在提交…':'拆分需求' }}</button></template><template v-else><p v-if="session.state==='understanding'" role="status">正在理解需求…</p><h3>{{ session.title }}</h3><section v-for="(item,i) in session.items" :key="i" class="item"><h3>{{ i+1 }}. {{ item.title || item.text }}</h3><pre v-if="item.ac?.length">{{ item.ac.map(v=>typeof v==='string'?v:JSON.stringify(v)).join('\n') }}</pre><label class="field">依赖前面的需求编号（可留空）<input v-model="dependencies[String(i)]" placeholder="例如 1, 2" /></label></section><label class="field" v-for="(q,i) in questions" :key="q.item+q.slot">{{ q.q }}<input v-model="answers[q.item]![q.slot]" :list="'options-'+i" /><datalist :id="'options-'+i"><option v-for="option in q.options" :key="option" :value="option" /></datalist></label><button v-if="questions.length" class="btn" :disabled="busy || session.state==='understanding'" @click="act('answer')">补充回答</button><label class="field">每批任务数<input type="number" v-model.number="wave" min="1" max="8" /></label><button class="btn btn-primary" :disabled="busy || session.state==='understanding' || session.state==='confirmed' || !!questions.length" @click="act('confirm')">确认并分批开发</button><details v-if="session.spec"><summary>整体要求</summary><pre>{{ JSON.stringify(session.spec,null,2) }}</pre></details></template></section></template>
<style scoped>.batch h2 { margin-top:0; }.item { border-bottom:1px solid var(--line); margin:20px 0; }.batch pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; font-size:13px; }.batch .field { margin-top:16px; }</style>
