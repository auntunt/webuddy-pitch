<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { app, loadApp, legacyUrl } from '../app'

const router = useRouter()
const projects = computed(() => app.projects)

onMounted(() => {
  if (!app.ready) loadApp()
})
</script>

<template>
  <div>
    <h1>开发工作台</h1>
    <p v-if="!projects.length" class="empty">还没有可访问的项目。</p>
    <ul v-else class="project-list">
      <li v-for="p in projects" :key="p.key">
        <button class="link" @click="router.push(`/p/${encodeURIComponent(p.key)}/work`)">{{ p.name || p.key }}</button>
      </li>
    </ul>
    <p class="muted">项目接入与配置： <a :href="legacyUrl('/workspace')">项目管理</a>。</p>
  </div>
</template>

<style scoped>
.project-list { list-style: none; padding: 0; margin: 16px 0; }
.project-list li { padding: 10px 0; border-bottom: 1px solid var(--line); }
.link { background: none; border: 0; padding: 0; font: inherit; color: var(--accent); cursor: pointer; text-align: left; }
.muted { color: var(--sub); font-size: 13px; }
.empty { color: var(--sub); }
</style>
