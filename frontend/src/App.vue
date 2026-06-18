<template>
  <div id="briefing-app">
    <nav class="navbar">
      <router-link to="/" class="navbar-brand">
        <span class="logo-mark">A.I.</span>
        <span class="brand-text">Morning Briefing</span>
      </router-link>
      <div class="navbar-actions">
        <button
          class="btn btn-primary btn-sm"
          :disabled="triggering"
          @click="triggerBriefing"
        >
          {{ triggering ? '抓取中...' : '抓取最新资讯' }}
        </button>
      </div>
    </nav>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Toast notifications -->
    <div class="toast-container">
      <transition-group name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="['toast', `toast-${toast.type}`]"
        >
          {{ toast.message }}
        </div>
      </transition-group>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { API_BASE, API_HEADERS } from './api'

const triggering = ref(false)
const toasts = ref([])

let toastId = 0

function showToast(message, type = 'success') {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 4000)
}

async function triggerBriefing() {
  triggering.value = true
  try {
    const resp = await fetch(`${API_BASE}/trigger?loop=A`, { 
      method: 'POST',
      headers: API_HEADERS
    })
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    showToast(data.message, 'success')
  } catch (err) {
    showToast(`抓取请求失败: ${err.message}`, 'error')
  } finally {
    triggering.value = false
  }
}
</script>

<style scoped>
.main-content {
  flex: 1;
  padding: 2rem 0;
}
.logo-mark {
  font-family: var(--font-mono);
  font-weight: 900;
  font-size: 2.2rem;
  background: var(--gradient-text);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  color: transparent;
  padding-right: 0.5rem;
  display: inline-block;
  transform: translateZ(0);
}
</style>
