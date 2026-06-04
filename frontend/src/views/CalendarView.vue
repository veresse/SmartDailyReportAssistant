<template>
  <div class="calendar-view split-layout container">
    <div class="split-left">
      <!-- Hero Section -->
      <section class="hero editorial-hero" style="margin-bottom: 4rem; padding-top: 4rem;">
        <h1 class="editorial-title">
          Intelligence<br>Briefing.
        </h1>
        <p class="editorial-subtitle">
          每日深度解析前沿技术资讯，排除噪音。
        </p>
      </section>

      <!-- Recent Briefings -->
      <section class="recent-section">
        <h2 class="editorial-section-title">Latest Reports</h2>
        <div v-if="loading" class="space-loader-container">
          <div class="space-loader">
            <div class="circle outer"></div>
            <div class="circle middle"></div>
            <div class="circle inner"></div>
            <div class="core-dot"></div>
          </div>
          <p class="loader-text">SYNCING WITH A.I. CORE <span class="blink">_</span></p>
        </div>
        <div v-else-if="recentBriefings.length === 0" class="empty-state">
          <p class="text-muted">暂无早报数据。点击右上角「手动生成今日早报」开始使用。</p>
        </div>
        <div v-else class="briefing-list">
          <router-link
            v-for="b in recentBriefings"
            :key="b.id"
            :to="`/briefing/${b.date}`"
            class="briefing-card card"
          >
            <div class="briefing-card-header">
              <span class="briefing-date">{{ b.date }}</span>
              <span :class="['tag', statusTagClass(b.status)]">{{ statusText(b.status) }}</span>
            </div>
            <p class="briefing-overview">{{ b.summary_overview }}</p>
            <div class="briefing-meta">
              <span class="text-muted">{{ b.item_count }} 条新闻</span>
            </div>
          </router-link>
        </div>
      </section>
    </div>

    <!-- Calendar Navigation -->
    <div class="split-right sticky-sidebar" style="padding-top: 4rem;">
      <section class="calendar-section">
        <h2 class="editorial-section-title">Activity</h2>
        <div class="calendar-header">
          <button class="btn btn-ghost btn-sm" @click="prevMonth">← 上月</button>
          <h2 class="calendar-month-label">{{ monthLabel }}</h2>
          <button class="btn btn-ghost btn-sm" @click="nextMonth">下月 →</button>
        </div>

        <div class="calendar-grid">
          <div v-for="day in weekdays" :key="day" class="calendar-weekday">
            {{ day }}
          </div>
          <div
            v-for="(cell, i) in calendarCells"
            :key="i"
            :class="[
              'calendar-cell',
              {
                'calendar-cell--empty': !cell.date,
                'calendar-cell--today': cell.isToday,
                'calendar-cell--has-data': cell.hasData,
                'calendar-cell--has-briefing': cell.status === 'completed',
                'calendar-cell--processing': cell.status === 'processing' || cell.status === 'collecting',
                'calendar-cell--failed': cell.status === 'failed',
              },
            ]"
            @click="cell.hasData && goToBriefing(cell.dateStr)"
          >
            <span v-if="cell.date" class="calendar-day">{{ cell.date }}</span>
            <div v-if="cell.hasData" class="calendar-indicators">
              <div v-if="cell.status === 'completed'" class="calendar-dot calendar-dot--done" title="早报已生成"></div>
              <div v-else-if="cell.status === 'processing' || cell.status === 'collecting'" class="calendar-dot calendar-dot--processing" title="早报生成中"></div>
              <div v-else-if="cell.status === 'failed'" class="calendar-dot calendar-dot--failed" title="早报生成失败"></div>
              <span class="feed-count-badge" v-if="cell.feedCount > 0" title="今日资讯数量">{{ cell.feedCount }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDates, fetchBriefings } from '../api.js'

const router = useRouter()
const currentYear = ref(new Date().getFullYear())
const currentMonth = ref(new Date().getMonth()) // 0-indexed
const briefingDates = ref({}) // { "2025-05-19": { status: "completed", feedCount: 42 }, ... }
const recentBriefings = ref([])
const loading = ref(true)

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

const monthLabel = computed(() => {
  return `${currentYear.value} 年 ${currentMonth.value + 1} 月`
})

const calendarCells = computed(() => {
  const year = currentYear.value
  const month = currentMonth.value
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const today = new Date()

  const cells = []

  // 填充月初空白
  for (let i = 0; i < firstDay; i++) {
    cells.push({ date: null, dateStr: '', isToday: false, status: null })
  }

  // 填充日期
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const isToday =
      today.getFullYear() === year &&
      today.getMonth() === month &&
      today.getDate() === d

    const dateInfo = briefingDates.value[dateStr] || {}
    cells.push({
      date: d,
      dateStr,
      isToday,
      hasData: !!dateInfo.status || !!dateInfo.feedCount,
      status: dateInfo.status || null,
      feedCount: dateInfo.feedCount || 0,
    })
  }

  return cells
})

function prevMonth() {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
}

function nextMonth() {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
}

function goToBriefing(dateStr) {
  router.push(`/briefing/${dateStr}`)
}

function statusTagClass(status) {
  const map = {
    completed: 'tag-github',
    processing: 'tag-hackernews',
    collecting: 'tag-hackernews',
    failed: 'tag-huggingface',
  }
  return map[status] || 'tag-category'
}

function statusText(status) {
  const map = {
    completed: '已完成',
    processing: '处理中',
    collecting: '采集中',
    failed: '失败',
  }
  return map[status] || status
}

onMounted(async () => {
  try {
    const [dates, briefings] = await Promise.all([
      fetchDates(),
      fetchBriefings(10),
    ])

    // 构建日期 -> 状态映射
    for (const d of dates) {
      briefingDates.value[d.date] = {
        status: d.status,
        feedCount: d.feed_count || 0
      }
    }

    recentBriefings.value = briefings
  } catch (err) {
    console.error('加载数据失败:', err)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.editorial-hero {
  text-align: left;
}

.split-wrapper {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 4rem;
  align-items: start;
}

/* Calendar */
.calendar-section {
  background: transparent;
  margin: 0;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2rem;
  margin-bottom: 1.5rem;
}

.calendar-month-label {
  font-size: 1.2rem;
  font-weight: 700;
  min-width: 160px;
  text-align: center;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
  max-width: 640px;
  margin: 0 auto;
}

.calendar-weekday {
  text-align: center;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  padding: 8px 0;
}

.calendar-cell {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: all var(--transition-fast);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  font-size: 0.9rem;
  gap: 2px;
  backdrop-filter: blur(8px);
}

.calendar-cell--empty {
  pointer-events: none;
}

.calendar-cell--today {
  border: 1px solid var(--color-accent-indigo);
}

.calendar-cell--has-data {
  cursor: pointer;
  background: var(--color-bg-card);
}

.calendar-cell--has-data:hover {
  background: rgba(255,255,255,0.06);
  border-color: rgba(255,255,255,0.15);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.calendar-cell--has-briefing {
  background: rgba(34, 211, 238, 0.05);
  border: 1px solid rgba(34, 211, 238, 0.2);
}

.calendar-cell--processing {
  border-color: rgba(245, 158, 11, 0.3);
  background: rgba(245, 158, 11, 0.05);
}

.calendar-cell--failed {
  border-color: rgba(244, 63, 94, 0.3);
  background: rgba(244, 63, 94, 0.05);
}

.calendar-day {
  font-weight: 500;
}

.calendar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.calendar-indicators {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 4px;
}

.feed-count-badge {
  font-size: 0.6rem;
  font-family: var(--font-mono);
  background: var(--color-bg-glass);
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}

.calendar-dot--done {
  background-color: var(--color-accent-emerald);
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
}

.calendar-dot--processing {
  background-color: var(--color-accent-amber);
  box-shadow: 0 0 6px rgba(245, 158, 11, 0.4);
  animation: pulse-amber 1.5s infinite alternate;
}

.calendar-dot--failed {
  background-color: var(--color-accent-rose);
  box-shadow: 0 0 6px rgba(225, 29, 72, 0.4);
}

@keyframes pulse-amber {
  from { opacity: 0.5; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1.1); }
}

/* Recent Section */
.recent-section {
  margin-bottom: 4rem;
}

.section-title {
  font-size: 1.3rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
}

.space-loader-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 0;
  gap: 2rem;
}

.space-loader {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.circle {
  position: absolute;
  border-radius: 50%;
  border: 1px solid transparent;
}

.outer {
  width: 100%;
  height: 100%;
  border-top-color: var(--color-accent-cyan);
  border-bottom-color: rgba(34, 211, 238, 0.2);
  animation: spin 3s linear infinite;
}

.middle {
  width: 70%;
  height: 70%;
  border-left-color: var(--color-accent-violet);
  border-right-color: rgba(139, 92, 246, 0.2);
  animation: spin-reverse 2s linear infinite;
}

.inner {
  width: 40%;
  height: 40%;
  border-top-color: #ffffff;
  border-bottom-color: rgba(255, 255, 255, 0.3);
  animation: spin 1.5s linear infinite;
}

.core-dot {
  width: 6px;
  height: 6px;
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 0 10px #ffffff, 0 0 20px var(--color-accent-cyan);
  animation: pulse-glow 2s ease-in-out infinite alternate;
}

.loader-text {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--color-accent-cyan);
  letter-spacing: 0.2em;
  opacity: 0.8;
}

.blink {
  animation: blinker 1s step-end infinite;
}

@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes spin-reverse { 100% { transform: rotate(-360deg); } }
@keyframes blinker { 50% { opacity: 0; } }
@keyframes pulse-glow {
  0% { transform: scale(0.8); opacity: 0.5; }
  100% { transform: scale(1.2); opacity: 1; }
}

.briefing-list {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
}

.briefing-card {
  display: block;
  padding: 1.5rem;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), var(--shadow-sm);
  backdrop-filter: blur(12px);
  transition: all var(--transition-normal);
  color: var(--color-text-primary);
}

.briefing-card:hover {
  background: var(--color-bg-card-hover);
  border-color: var(--color-border-hover);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), var(--shadow-md);
  transform: translateY(-2px);
}

.briefing-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.briefing-date {
  font-weight: 600;
  font-size: 0.95rem;
}

.briefing-overview {
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.briefing-meta {
  font-size: 0.8rem;
}

@media (max-width: 640px) {
  .hero-title {
    font-size: 1.8rem;
  }

  .calendar-grid {
    gap: 4px;
  }

  .calendar-cell {
    font-size: 0.8rem;
  }
}
</style>
