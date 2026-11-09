<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { app, loadApp, legacyUrl, logoutUrl, selectProject, prepareLegacy } from './app'

const route = useRoute()
watch(() => [route.params.key, app.ready], () => {
  const key = String(route.params.key || '')
  if (app.ready && app.projects.some(project => project.key === key)) selectProject(key)
}, { immediate: true })

const nav = computed(() => {
  const key = String(route.params.key || app.project || '')
  const verify = key ? `/p/${encodeURIComponent(key)}/verify` : '/'
  return [
    { to: '/', label: '任务总览', internal: true },
    { to: key ? `/p/${encodeURIComponent(key)}/assistant` : '/projects', label: 'AI 助手', internal: true },
    { to: key ? `/p/${encodeURIComponent(key)}/work` : '/', label: '开发工作台', internal: true },
    { to: verify, label: '验证现有改动', internal: true },
    { to: key ? `/p/${encodeURIComponent(key)}/knowledge` : '/', label: '知识库', internal: true },
    { to: '/features', label: '全部功能', internal: true },
    { to: key ? `/p/${encodeURIComponent(key)}/settings` : '/settings', label: '设置', internal: true },
  ]
})

const mobileNav = computed(() => nav.value.filter(item => !['验证现有改动','设置'].includes(item.label)))
const fullNav = [['/team','团队与分工'],['/meetings','会议与行动'],['/reform','改造计划'],['/deliveries','验证与交付'],['/projects','项目与环境'],['/runs','运行记录'],['/lead','流程与统计']]
const isActive = (to: string) => route.path === to

onMounted(() => {
  if (!app.ready) loadApp()
})
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <router-link class="brand" to="/" :aria-label="app.meta?.brand || 'Webuddy'">
        <span class="brand-mark" aria-hidden="true">W</span>
        <span>{{ app.meta?.brand || 'Webuddy' }}</span>
      </router-link>
      <label class="project-picker">
        <span class="sr">项目</span>
        <select :value="route.params.key || app.project" @change="selectProject(($event.target as HTMLSelectElement).value); $router.push({ path: `/p/${encodeURIComponent(($event.target as HTMLSelectElement).value)}/work` })">
          <option v-for="p in app.projects" :key="p.key" :value="p.key">{{ p.name || p.key }}</option>
        </select>
      </label>
      <div class="user"><a class="full-workspace" :href="legacyUrl('/workspace')" @click="prepareLegacy('*')">完整工作台</a>
        <span v-if="app.meta?.user">{{ app.meta.user }}</span>
        <a :href="logoutUrl()">退出</a>
      </div>
    </header>
    <div class="body">
      <nav class="sidenav" aria-label="主导航">
        <template v-for="item in nav" :key="item.label">
          <router-link :to="item.to" :class="{ active: isActive(item.to) }" class="navlink">{{ item.label }}</router-link>
        </template>
        <div class="nav-divider"></div>
        <a v-for="[path,label] in fullNav" :key="path" class="navlink" :href="legacyUrl(path!)" @click="prepareLegacy('*')">{{label}}</a>
      </nav>
      <main class="content">
        <p v-if="app.error" class="error" role="alert">{{ app.error }}</p>
        <p v-else-if="!app.ready" class="muted">正在读取…</p>
        <router-view v-else />
      </main>
    </div>
    <nav class="bottomnav" aria-label="主导航">
      <template v-for="item in mobileNav" :key="item.label">
        <router-link :to="item.to" :class="{ active: isActive(item.to) }">{{ item.label }}</router-link>
      </template>
    </nav>
  </div>
</template>

<style>
:root {
  --bg: #F6F7F9;
  --panel: #FFFFFF;
  --fg: #111827;
  --sub: #4B5563;
  --line: #DCE1E8;
  --accent: #1D4ED8;
  --accent-soft: #EAF2FF;
  --ok: #18794E;
  --ok-bg: #EFFAF3;
  --ok-line: #C7E9D3;
  --bad: #B63131;
  --bad-bg: #FFF2F2;
  --bad-line: #EFCCCC;
  --warn: #966324;
  --warn-bg: #FFF8EB;
  --warn-line: #EDDBB7;
  --radius: 8px;
}
* { box-sizing: border-box; }
html, body, #app { height: 100%; margin: 0; }
body {
  background: var(--bg);
  color: var(--fg);
  font: 14px/1.65 -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
}
h1 { font-size: 24px; margin: 0 0 16px; }
h2 { font-size: 16px; margin: 24px 0 10px; }
h3 { font-size: 15px; margin: 0 0 12px; }
a { color: var(--accent); }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; overflow-wrap: anywhere; }
.muted { color: var(--sub); font-size: 13px; }
.error { color: var(--bad); background: var(--bad-bg); border: 1px solid var(--bad-line); border-radius: var(--radius); padding: 10px 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.empty { color: var(--sub); padding: 32px 0; text-align: center; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
button, input, select, textarea { font: inherit; }
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.btn {
  display: inline-block; border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
  color: var(--fg); padding: 8px 14px; cursor: pointer; line-height: 1.4; text-decoration: none;
}
.btn:hover { border-color: var(--accent); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--fg); border-color: var(--fg); color: #fff; }
.btn-primary:hover { background: #000; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--sub); margin-bottom: 14px; }
.field input, .field select, .field textarea {
  box-sizing: border-box; width: 100%; background: var(--panel); color: var(--fg);
  border: 1px solid var(--line); border-radius: 6px; padding: 9px 10px; line-height: 1.5;
}
.field textarea { resize: vertical; min-height: 90px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px; }
.tag { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 6px; padding: 2px 8px; font-size: 12px; line-height: 1.5; }
.tag-good { color: var(--ok); background: var(--ok-bg); border-color: var(--ok-line); }
.tag-warn { color: var(--warn); background: var(--warn-bg); border-color: var(--warn-line); }
.tag-bad { color: var(--bad); background: var(--bad-bg); border-color: var(--bad-line); }
.note { border-left: 3px solid var(--accent); background: var(--bg); padding: 10px 14px; border-radius: 0 6px 6px 0; line-height: 1.6; font-size: 13px; margin: 12px 0; }
</style>

<style scoped>
.shell { min-height: 100%; display: flex; flex-direction: column; }
.topbar {
  display: flex; align-items: center; gap: 16px; padding: 0 20px; height: 52px;
  background: var(--panel); border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 9px; font-weight: 600; color: var(--fg); text-decoration: none; }
.brand-mark {
  width: 28px; height: 28px; border-radius: 8px; background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 14px;
}
.project-picker select {
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel); color: var(--fg);
  padding: 6px 10px; font-size: 13px; max-width: 220px;
}
.user { margin-left: auto; display: flex; gap: 12px; align-items: center; font-size: 13px; color: var(--sub); }
.user a { color: var(--sub); }
.body { flex: 1; display: flex; min-height: 0; }
.nav-divider { border-top:1px solid var(--line); margin:14px 8px; }
.sidenav { width: 190px; flex-shrink: 0; padding: 16px 12px; display: flex; flex-direction: column; gap: 2px; }
.navlink {
  display: block; padding: 8px 12px; border-radius: 6px; color: var(--sub); text-decoration: none; font-size: 14px;
}
.navlink:hover { background: var(--accent-soft); color: var(--fg); }
.navlink.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.content { flex: 1; min-width: 0; padding: 28px 32px 64px; max-width: 1560px; }
.bottomnav { display: none; }
@media (max-width: 760px) {
  .sidenav { display: none; }
  .content { padding: 20px 16px 88px; }
  .topbar { padding: 0 14px; gap: 10px; }
  .full-workspace { display:none; }
  .project-picker select { max-width: 130px; }
  .bottomnav {
    display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
    background: var(--panel); border-top: 1px solid var(--line);
  }
  .bottomnav a {
    flex: 1; text-align: center; padding: 12px 4px; color: var(--sub); text-decoration: none; font-size: 13px;
  }
  .bottomnav a.active { color: var(--accent); font-weight: 600; }
}
</style>
