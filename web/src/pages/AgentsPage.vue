<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, post, ApiError } from '../api/client'
import { reactive } from 'vue'

interface Executor {
  name: string; title: string; engine: string; installed: boolean; version: string; path: string
  last_test: { at: string; ok: boolean; reason: string } | null
}
interface Usage { runs: number; success: number; success_rate: number | null; last_used: string; total_seconds: number }
interface Page { executors: Executor[]; usage: { days: number; by_executor: Record<string, Usage> } }

const page = ref<Page | null>(null)
const error = ref('')
const testing = ref('')
const loginLines = ref<Record<string, string[]>>({})
const apiForm = reactive<Record<string, { base_url: string; api_key: string; model: string }>>({})
const gatewayUrl = ref('http://127.0.0.1:3425')
const gatewayKey = ref('')
const gatewayModels = ref<string[]>([])
const gatewayEngine = ref('')

async function login(name: string) {
  error.value = ''
  try {
    const r = await post<{ session: string; command: string }>('/api/agent-login', { name })
    loginLines.value[name] = ['$ ' + r.command]
    await pollLogin(name, r.session)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '本机登录没有启动。'
  }
}

async function pollLogin(name: string, sid: string) {
  for (let i = 0; i < 300; i++) {
    const r = await get<{ lines: string[]; done: boolean }>('/api/agent-login/' + encodeURIComponent(sid))
    loginLines.value[name] = ['$ ' + (loginLines.value[name]?.[0] ?? ''), ...r.lines]
    if (r.done) return
    await new Promise((res) => setTimeout(res, 1000))
  }
}

function form(name: string) {
  if (!apiForm[name]) apiForm[name] = { base_url: '', api_key: '', model: '' }
  return apiForm[name]
}

async function currentRevision(): Promise<number> {
  const r = await get<{ revision: number }>('/api/agent-settings')
  return r.revision
}

async function saveApi(name: string) {
  const f = form(name)
  if (!f.base_url || !f.api_key || !f.model) {
    error.value = '填写 API 地址、密钥和模型。'
    return
  }
  error.value = ''
  try {
    await post('/api/agent-settings', { action: 'update', name, revision: await currentRevision(), config: {
      title: name, models: [[f.model, f.model]], defaults: {}, timeout: 1800,
      engine: name, secrets: { base_url: f.base_url, api_key: f.api_key, model: f.model } } })
    await test(name)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '保存失败。'
  }
}

async function probeGateway(name: string) {
  error.value = ''
  gatewayEngine.value = name
  try {
    const r = await post<{ models: string[] }>('/api/agent-gateway/models', { url: gatewayUrl.value, key: gatewayKey.value })
    gatewayModels.value = r.models
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '网关探测失败。'
  }
}

async function saveGateway(name: string, model: string) {
  error.value = ''
  try {
    await post('/api/agent-settings', { action: 'update', name, revision: await currentRevision(), config: {
      title: name, models: [[model, model]], defaults: {}, timeout: 1800,
      engine: 'codex', secrets: { base_url: gatewayUrl.value, api_key: gatewayKey.value || 'gateway', model } } })
    await test(name)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '保存网关配置失败。'
  }
}

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
          <td>
            <button class="btn" :disabled="testing !== ''" @click="test(e.name)">{{ testing === e.name ? '测试中…' : '测试连接' }}</button>
            <button class="btn" @click="login(e.name)">本机登录</button>
            <pre v-if="loginLines[e.name]" class="login">{{ loginLines[e.name].join('\n') }}</pre>
            <details>
              <summary>API 方式</summary>
              <label class="field">API 地址<input v-model="form(e.name).base_url" /></label>
              <label class="field">密钥<input type="password" autocomplete="off" v-model="form(e.name).api_key" /></label>
              <label class="field">模型<input v-model="form(e.name).model" /></label>
              <button class="btn" @click="saveApi(e.name)">保存并测试</button>
            </details>
            <details>
              <summary>本机网关</summary>
              <label class="field">网关地址<input v-model="gatewayUrl" /></label>
              <label class="field">网关密钥（可空）<input type="password" autocomplete="off" v-model="gatewayKey" /></label>
              <button class="btn" @click="probeGateway(e.name)">读取模型</button>
              <div v-if="gatewayEngine === e.name && gatewayModels.length">
                <button v-for="m in gatewayModels" :key="m" class="btn" @click="saveGateway(e.name, m)">用 {{ m }} 保存并测试</button>
              </div>
            </details>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.login { white-space: pre-wrap; max-height: 240px; overflow: auto; background: var(--soft); padding: 8px; }
.agents { width: 100%; border-collapse: collapse; background: var(--panel); }
.agents th, .agents td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
</style>
