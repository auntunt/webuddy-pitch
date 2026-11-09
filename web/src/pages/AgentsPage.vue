<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, post, ApiError } from '../api/client'

interface Executor {
  name: string; title: string; engine: string; installed: boolean; version: string; path: string
  last_test: { at: string; ok: boolean; reason: string } | null
}
interface Usage { runs: number; success: number; success_rate: number | null; last_used: string; total_seconds: number }
interface Page { executors: Executor[]; usage: { days: number; by_executor: Record<string, Usage> } }

const page = ref<Page | null>(null)
const error = ref('')
const testing = ref('')

async function load() {
  error.value = ''
  try {
    page.value = await get<Page>('/api/agent-page')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '智能体页面读取失败。'
  }
}

async function test(name: string) {
  testing.value = name
  error.value = ''
  try {
    await post('/api/agent-test', { name })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '连接测试失败。'
  } finally {
    testing.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>智能体</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!page && !error" class="muted">正在读取…</p>
    <table v-if="page" class="agents">
      <thead>
        <tr><th>执行器</th><th>安装</th><th>上次测试</th><th>近 {{ page.usage.days }} 天</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="e in page.executors" :key="e.name">
          <td>{{ e.title }}<div class="muted">{{ e.engine }}</div></td>
          <td>
            <span v-if="e.installed">已安装 {{ e.version }}</span>
            <span v-else class="muted">未安装</span>
            <div class="muted">{{ e.path }}</div>
          </td>
          <td>
            <template v-if="e.last_test">
              <span :class="e.last_test.ok ? 'tag tag-good' : 'tag tag-bad'">{{ e.last_test.ok ? '可用' : '不可用' }}</span>
              <div v-if="!e.last_test.ok" class="muted">{{ e.last_test.reason }}</div>
              <div class="muted">{{ e.last_test.at }}</div>
            </template>
            <span v-else class="muted">未测试</span>
          </td>
          <td>
            <template v-if="page.usage.by_executor[e.name]">
              {{ page.usage.by_executor[e.name].runs }} 次，成功率 {{ page.usage.by_executor[e.name].success_rate }}
              <div class="muted">最近 {{ page.usage.by_executor[e.name].last_used }} · 合计 {{ page.usage.by_executor[e.name].total_seconds }} 秒</div>
            </template>
            <span v-else class="muted">无记录</span>
          </td>
          <td><button class="btn" :disabled="testing !== ''" @click="test(e.name)">{{ testing === e.name ? '测试中…' : '测试连接' }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.agents { width: 100%; border-collapse: collapse; background: var(--panel); }
.agents th, .agents td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
</style>
