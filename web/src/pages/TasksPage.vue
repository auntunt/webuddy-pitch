<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, post, requestId, ApiError } from '../api/client'

const props = defineProps<{ pkey: string }>()

interface TaskRow { key: string; title: string; stage: string; first_line: string }
const tasks = ref<TaskRow[]>([])
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const notice = ref('')
const title = ref('')
const body = ref('')
const goal = ref<'出方案' | '修改并测试'>('修改并测试')
const envRows = ref<{ name: string; value: string }[]>([])

function addRow() { envRows.value.push({ name: '', value: '' }) }
function removeRow(i: number) { envRows.value.splice(i, 1) }

async function load() {
  error.value = ''
  try {
    const r = await get<{ items: TaskRow[] }>(`/api/projects/${encodeURIComponent(props.pkey)}/tasks`)
    tasks.value = r.items
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '任务列表读取失败。'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (busy.value || !title.value.trim() || !body.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    const r = await post<{ key: string }>(`/api/projects/${encodeURIComponent(props.pkey)}/tasks`, {
      title: title.value.trim(), body: body.value.trim(), goal: goal.value, request_id: requestId(),
      secrets: envRows.value.filter((r) => r.name.trim()).map((r) => ({ name: r.name.trim(), value: r.value })),
    })
    notice.value = `已创建 ${r.key}`
    title.value = ''
    body.value = ''
    envRows.value = []
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '创建失败，本次没有重试。'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>任务</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="note">{{ notice }}</p>
    <p v-if="loading" class="muted">正在读取…</p>
    <table v-else-if="tasks.length" class="tasks">
      <thead><tr><th>任务</th><th>工作内容</th><th>阶段</th></tr></thead>
      <tbody>
        <tr v-for="t in tasks" :key="t.key">
          <td>{{ t.title }}</td>
          <td>{{ t.first_line }}</td>
          <td>{{ t.stage }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">还没有任务。</p>

    <form class="panel" @submit.prevent="create">
      <h2>新建任务</h2>
      <label class="field">任务名<input v-model="title" required /></label>
      <label class="field">工作内容<textarea v-model="body" required></textarea></label>
      <label class="field">要做到哪一步
        <select v-model="goal">
          <option value="修改并测试">修改并测试</option>
          <option value="出方案">出方案</option>
        </select>
      </label>
      <fieldset class="env">
        <legend>测试环境</legend>
        <div v-for="(row, i) in envRows" :key="i" class="env-row">
          <input v-model="row.name" placeholder="名称，例如 db_host" aria-label="名称" />
          <input v-model="row.value" type="password" autocomplete="off" placeholder="值" aria-label="值" />
          <button type="button" class="btn" @click="removeRow(i)">删除</button>
        </div>
        <button type="button" class="btn" @click="addRow">添加一项</button>
      </fieldset>
      <button class="btn btn-primary" :disabled="busy">{{ busy ? '创建中…' : '创建任务' }}</button>
    </form>
  </div>
</template>

<style scoped>
.tasks { width: 100%; border-collapse: collapse; background: var(--panel); }
.env { margin: 12px 0; border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
.env-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; margin-bottom: 8px; }
.tasks th, .tasks td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
</style>
