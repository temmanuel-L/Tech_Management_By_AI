import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import DrillDown from './views/DrillDown.vue'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        { path: '/', component: Dashboard },
        { path: '/drilldown/:drill_type', name: 'drilldown', component: DrillDown },
    ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
