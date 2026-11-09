<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { get, post, requestId, ApiError } from '../api/client'

interface Member { name: string; role: 'owner' | 'editor' | 'viewer' }

const members = ref<Member[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(true)
const busy = ref(false)
const newName = ref('')
const newPassword = ref('')
const newRole = ref<'editor' | 'viewer'>('viewer')
const resetFor = ref('')
const resetPassword = ref('')

const roleLabel: Record<string, string> = { owner: '所有者', editor: '可修改', viewer: '可查看' }

async function load() {
  error.value = ''
  try {
    const r = await get<{ members: Member[] }>('/api/members')
    members.value = r.members
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '成员列表读取失败。'
  } finally {
    loading.value = false
  }
}

async function act(body: Record<string, unknown>, done: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const r = await post<{ members: Member[] }>('/api/members', { ...body, request_id: requestId() })
    members.value = r.members
    notice.value = done
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '操作没有完成，本次没有重试。'
  } finally {
    busy.value = false
  }
}

function add() {
  act({ action: 'add', name: newName.value.trim(), password: newPassword.value, role: newRole.value }, '已添加成员')
  newName.value = ''
  newPassword.value = ''
}

function changeRole(m: Member, role: 'editor' | 'viewer') {
  act({ action: 'role', name: m.name, role }, '已修改角色')
}

function reset(m: Member) {
  act({ action: 'reset_password', name: m.name, password: resetPassword.value }, '已重设密码')
  resetFor.value = ''
  resetPassword.value = ''
}

function remove(m: Member) {
  act({ action: 'remove', name: m.name }, '已删除成员')
}

onMounted(load)
</script>

<template>
  <div>
    <h1>成员</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="note">{{ notice }}</p>
    <p v-if="loading" class="muted">正在读取…</p>
    <table v-else class="members">
      <thead><tr><th>账号</th><th>角色</th><th></th></tr></thead>
      <tbody>
        <tr v-for="m in members" :key="m.name">
          <td>{{ m.name }}</td>
          <td>
            <span v-if="m.role === 'owner'">所有者</span>
            <select v-else :value="m.role" :disabled="busy" @change="changeRole(m, ($event.target as HTMLSelectElement).value as 'editor' | 'viewer')">
              <option value="editor">可修改</option>
              <option value="viewer">可查看</option>
            </select>
          </td>
          <td>
            <template v-if="m.role !== 'owner'">
              <button class="btn" :disabled="busy" @click="resetFor = m.name">重设密码</button>
              <button class="btn" :disabled="busy" @click="remove(m)">删除</button>
              <form v-if="resetFor === m.name" class="inline" @submit.prevent="reset(m)">
                <input v-model="resetPassword" type="password" autocomplete="new-password" aria-label="新密码" required minlength="8" />
                <button class="btn btn-primary" :disabled="busy">确认</button>
              </form>
            </template>
          </td>
        </tr>
      </tbody>
    </table>

    <form class="panel" @submit.prevent="add">
      <h2>添加成员</h2>
      <label class="field">账号<input v-model="newName" required /></label>
      <label class="field">初始密码（至少 8 位）<input v-model="newPassword" type="password" autocomplete="new-password" required minlength="8" /></label>
      <label class="field">角色
        <select v-model="newRole">
          <option value="viewer">可查看</option>
          <option value="editor">可修改</option>
        </select>
      </label>
      <button class="btn btn-primary" :disabled="busy">添加</button>
    </form>
  </div>
</template>

<style scoped>
.members { width: 100%; border-collapse: collapse; background: var(--panel); }
.members th, .members td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
.inline { display: inline-flex; gap: 6px; margin-left: 8px; }
</style>
