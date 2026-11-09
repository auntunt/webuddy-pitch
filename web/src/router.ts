import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import HomePage from './pages/HomePage.vue'
import VerifyPage from './pages/VerifyPage.vue'
import CandidatePage from './pages/CandidatePage.vue'
import TasksPage from './pages/TasksPage.vue'
import TaskDetailPage from './pages/TaskDetailPage.vue'

function routerBase(): string {
  const path = window.location.pathname
  const i = path.indexOf('/next/')
  return i >= 0 ? path.slice(0, i) + '/next/' : '/next/'
}

export const router = createRouter({
  history: createWebHistory(routerBase()),
  routes: [
    { path: '/', component: App, children: [
      { path: '', component: HomePage },
      { path: 'p/:key/tasks', component: TasksPage, props: r => ({ pkey: r.params.key }) },
      { path: 'p/:key/tasks/:tkey', component: TaskDetailPage, props: r => ({ pkey: r.params.key, tkey: r.params.tkey }) },
      { path: 'p/:key/verify', component: VerifyPage, props: r => ({ pkey: r.params.key }) },
      { path: 'p/:key/candidates/:id', component: CandidatePage, props: r => ({ pkey: r.params.key, id: r.params.id }) },
    ] },
  ],
})
