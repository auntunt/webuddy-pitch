import { createApp } from 'vue'
import Root from './Root.vue'
import { router } from './router'
import { loadApp } from './app'

const app = createApp(Root)
app.use(router)
loadApp().finally(() => app.mount('#app'))
