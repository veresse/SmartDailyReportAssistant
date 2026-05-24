<template>
  <div class="calendar-view container">
    <!-- Hero Section -->
    <section class="hero">
      <h1 class="hero-title">
        <span class="text-gradient">AI Morning Briefing</span>
      </h1>
      <p class="hero-subtitle">
        每日 AI 技术速递 · GitHub · Hacker News · Hugging Face
      </p>
    </section>

    <!-- Calendar Navigation -->
    <section class="calendar-section">
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
            <span v-if="cell.status === 'completed'" class="calendar-dot calendar-dot--done" title="早报已生成">✓</span>
            <span v-else-if="cell.status === 'processing' || cell.status === 'collecting'" class="calendar-dot calendar-dot--processing" title="早报生成中">⟳</span>
            <span v-else-if="cell.status === 'failed'" class="calendar-dot calendar-dot--failed" title="早报生成失败">✗</span>
            <span class="feed-count-badge" v-if="cell.feedCount > 0" title="今日资讯数量">{{ cell.feedCount }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Recent Briefings -->
    <section class="recent-section">
      <h2 class="section-title">📰 近期早报</h2>
      <div v-if="loading" class="loading-grid">
        <div v-for="n in 3" :key="n" class="card skeleton-card">
          <div class="skeleton skeleton-title"></div>
          <div class="skeleton skeleton-text" style="width: 80%"></div>
          <div class="skeleton skeleton-text" style="width: 50%"></div>
        </div>
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
            <span class="briefing-date">📅 {{ b.date }}</span>
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
/* Hero */
.hero {
  text-align: center;
  padding: 3rem 0 2rem;
}

.hero-title {
  font-size: 2.5rem;
  font-weight: 800;
  margin-bottom: 0.75rem;
  letter-spacing: -0.02em;
}

.hero-subtitle {
  font-size: 1.05rem;
  color: var(--color-text-secondary);
}

/* Calendar */
.calendar-section {
  margin: 2rem 0;
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
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  position: relative;
  transition: all var(--transition-fast);
  font-size: 0.9rem;
  gap: 2px;
}

.calendar-cell--empty {
  pointer-events: none;
}

.calendar-cell--today {
  border-color: var(--color-accent-indigo);
  background: rgba(99, 102, 241, 0.08);
}

.calendar-cell--has-data {
  cursor: pointer;
  background: var(--color-bg-card);
}

.calendar-cell--has-data:hover {
  border-color: var(--color-accent-indigo);
  transform: scale(1.05);
}

.calendar-cell--has-briefing {
  background: var(--gradient-card);
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
  font-size: 0.65rem;
  line-height: 1;
}

.calendar-indicators {
  display: flex;
  align-items: center;
  gap: 4px;
}

.feed-count-badge {
  font-size: 0.6rem;
  background: rgba(255,255,255,0.1);
  padding: 1px 4px;
  border-radius: 4px;
  color: var(--color-text-secondary);
}

.calendar-dot--done {
  color: var(--color-accent-emerald);
}

.calendar-dot--processing {
  color: var(--color-accent-amber);
  animation: spin 2s linear infinite;
}

.calendar-dot--failed {
  color: var(--color-accent-rose);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Recent Section */
.recent-section {
  margin: 3rem 0;
}

.section-title {
  font-size: 1.3rem;
  font-weight: 700;
  margin-bottom: 1.5rem;
}

.loading-grid {
  display: grid;
  gap: 1rem;
}

.skeleton-card {
  padding: 1.5rem;
  min-height: 120px;
}

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
}

.briefing-list {
  display: grid;
  gap: 1rem;
}

.briefing-card {
  display: block;
  padding: 1.25rem 1.5rem;
  color: var(--color-text-primary);
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
