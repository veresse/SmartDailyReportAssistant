<template>
  <a :href="item.url" target="_blank" rel="noopener" class="featured-card">
    <div class="card-top-gradient"></div>
    
    <div v-if="item.is_pushed_instantly" class="instant-badge" title="触发了即时推送">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
      </svg>
    </div>

    <div class="card-inner">
      <div class="card-content">
        <div class="card-meta">
          <span :class="['source-tag', sourceTagClass(item.source)]">
            {{ sourceLabel(item.source) }}
          </span>
          <span class="time-text">{{ formatTime(item.collected_at) }}</span>
        </div>
        
        <h3 class="card-title">{{ item.title }}</h3>
        <p class="card-summary" v-if="item.summary">{{ truncate(item.summary, 120) }}</p>
        
        <!-- T / M Dimension Bars -->
        <div class="dimension-bars" v-if="item.tech_utility_score || item.macro_impact_score">
          <div class="dim-bar-wrapper">
            <span class="dim-label">T</span>
            <div class="dim-track">
              <div class="dim-fill dim-t" :style="{ width: `${item.tech_utility_score || 0}%` }"></div>
            </div>
          </div>
          <div class="dim-bar-wrapper">
            <span class="dim-label">M</span>
            <div class="dim-track">
              <div class="dim-fill dim-m" :style="{ width: `${item.macro_impact_score || 0}%` }"></div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="card-ring">
        <ScoreRing :score="item.score" :size="72" :stroke="6" />
      </div>
    </div>
  </a>
</template>

<script setup>
import { computed } from 'vue'
import ScoreRing from './ScoreRing.vue'

const props = defineProps({
  item: {
    type: Object,
    required: true
  }
})

function sourceTagClass(source) {
  const map = {
    github: 'tag-github',
    hackernews: 'tag-hackernews',
    huggingface: 'tag-huggingface',
  }
  return map[(source || '').toLowerCase()] || 'tag-default'
}

function sourceLabel(source) {
  return source || 'RSS'
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function truncate(text, len) {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}
</script>

<style scoped>
.featured-card {
  position: relative;
  display: block;
  min-width: 360px;
  background: var(--color-bg-card);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 20px;
  color: var(--color-text-primary);
  text-decoration: none;
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-normal), box-shadow var(--transition-normal);
  outline: none;
}

.featured-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
}

.featured-card:active {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.featured-card:focus-visible {
  box-shadow: 0 0 0 3px rgba(91, 108, 255, 0.35);
}

.card-top-gradient {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--gradient-card);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.instant-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #FFE9EE;
  color: #FB7185;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 1.8s infinite;
}

@keyframes breathe {
  0% { box-shadow: 0 0 0 0 rgba(251, 113, 133, 0.45); }
  100% { box-shadow: 0 0 0 8px rgba(251, 113, 133, 0); }
}

.card-inner {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.source-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
}

.tag-github { background: #EEF0F4; color: #1E2138; }
.tag-hackernews { background: #FFF1E8; color: #E8590C; }
.tag-huggingface { background: #FFF8E6; color: #B8860B; }
.tag-default { background: rgba(6, 182, 212, 0.1); color: #06B6D4; }

.time-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-muted);
}

.card-title {
  font-size: 18px;
  line-height: 26px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 8px 0;
  /* Max 2 lines */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-summary {
  font-size: 14px;
  line-height: 22px;
  font-weight: 400;
  color: var(--color-text-secondary);
  margin: 0 0 16px 0;
  /* Max 3 lines */
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dimension-bars {
  display: flex;
  align-items: center;
  gap: 16px;
}

.dim-bar-wrapper {
  display: flex;
  align-items: center;
  width: 120px;
  gap: 6px;
}

.dim-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  width: 12px;
}

.dim-track {
  flex: 1;
  height: 6px;
  background: var(--color-track);
  border-radius: 999px;
  overflow: hidden;
}

.dim-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.8s ease-out;
}

.dim-t { background: #06B6D4; }
.dim-m { background: #A855F7; }

.card-ring {
  flex-shrink: 0;
  /* Align ring top with title top approx (12px meta + 24px tag height gives 36px offset if meta is above, but meta is above title. Let's just flex-start to keep it simple, or use margin top) */
  margin-top: 4px;
}
</style>
