import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import CalendarView from './views/CalendarView.vue'
import BriefingDetail from './views/BriefingDetail.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: CalendarView },
    { path: '/briefing/:date', name: 'briefing', component: BriefingDetail, props: true },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
