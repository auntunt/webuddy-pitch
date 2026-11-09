<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, ApiError } from '../api/client'

const props = defineProps<{ pkey: string; tkey: string }>()

interface Ticket { key: string; title: string; body: string; status: string }
const ticket = ref<Ticket | null>(null)
const error = ref('')
const loading = ref(true)

const base = () => `/api/projects/${encodeURIComponent(props.pkey)}/tasks/${encodeURIComponent(props.tkey)}/return`

async function load() {
  error.value = ''
  try {
    const r = await get<{ ticket: Ticket }>(`/api/tickets/${encodeURIComponent(props.tkey)}`)
    ticket.value = r.ticket
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '任务读取失败。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted">正在读取…</p>
    <template v-else-if="ticket">
      <h1>{{ ticket.title }}</h1>
      <p class="muted">{{ ticket.key }} · {{ ticket.status }}</p>
      <div class="panel desc">{{ ticket.body }}</div>
      <section class="panel">
        <h2>取回代码</h2>
        <p class="muted">下载的补丁、改动文件或完整项目都可以带回本地项目目录。下载不会修改项目目录。</p>
        <div class="actions">
          <a class="btn" :href="base() + '/patch'" download>下载补丁</a>
          <a class="btn" :href="base() + '/files'" download>下载改动文件</a>
          <a class="btn" :href="base() + '/archive'" download>下载完整项目</a>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.desc { white-space: pre-wrap; overflow-wrap: anywhere; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
