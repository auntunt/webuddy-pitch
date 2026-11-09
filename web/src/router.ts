import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import SettingsPage from './pages/SettingsPage.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
import AssistantPage from './pages/AssistantPage.vue'
import WorkspacePage from './pages/WorkspacePage.vue'
import FeaturesPage from './pages/FeaturesPage.vue'
import HomePage from './pages/HomePage.vue'
import WorkbenchPage from './pages/WorkbenchPage.vue'
import VerifyPage from './pages/VerifyPage.vue'
import CandidatePage from './pages/CandidatePage.vue'

function routerBase(): string {
  const path = window.location.pathname
  const i = path.indexOf('/next/')
  return i >= 0 ? path.slice(0, i) + '/next/' : '/next/'
}

export const router = createRouter({
  history: createWebHistory(routerBase()),
  routes: [
    { path: '/', component: App, children: [
      { path: '', component: WorkspacePage },
      { path: 'projects', component: HomePage },
      { path: 'features', component: FeaturesPage },
      { path: 'p/:key/assistant', component: AssistantPage, props: r => ({ pkey: r.params.key }) },
      { path: 'settings', component: SettingsPage },
      { path: 'p/:key/settings', component: SettingsPage, props: r => ({ pkey: r.params.key }) },
      { path: 'p/:key/knowledge', component: KnowledgePage, props: r => ({ pkey: r.params.key }) },
      { path: 'p/:key/work', component: WorkbenchPage, props: r => ({ pkey: r.params.key, ticketKey: typeof r.query.ticket === 'string' ? r.query.ticket : '', compose: r.query.compose === '1' }) },
      { path: 'p/:key/verify', component: VerifyPage, props: r => ({ pkey: r.params.key }) },
      { path: 'p/:key/candidates/:id', component: CandidatePage, props: r => ({ pkey: r.params.key, id: r.params.id }) },
    ] },
  ],
})
