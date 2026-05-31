<template>
  <div class="briefing-detail container">
    <!-- Back navigation -->
    <router-link to="/" class="back-link">
      ← 返回看板
    </router-link>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="skeleton skeleton-title" style="width: 40%; margin-bottom: 2rem"></div>
      <div class="skeleton" style="height: 300px; margin-bottom: 2rem"></div>
      <div v-for="n in 3" :key="n" style="margin-bottom: 1rem">
        <div class="skeleton" style="height: 150px"></div>
      </div>
    </div>

    <!-- Content -->
    <template v-else>
      <!-- Header -->
      <header class="detail-header">
        <div class="detail-header-main">
          <div>
            <h1 class="detail-title">
              {{ date }} 资讯汇编
            </h1>
            <p class="detail-overview" v-if="briefing?.summary_overview">
              {{ briefing.summary_overview }}
            </p>
          </div>
          <button
            v-if="briefing"
            class="btn btn-danger btn-sm"
            :disabled="deleting"
            @click="handleDeleteBriefing"
          >
            {{ deleting ? '删除中...' : '删除早报' }}
          </button>
        </div>
      </header>

      <!-- 🧠 晨报精选区域 -->
      <template v-if="briefing && briefing.status === 'completed'">
        <!-- Mindmap -->
        <section v-if="briefing.mindmap_mermaid" class="mindmap-section editorial-block">
          <h2 class="section-title">技术演进网络</h2>
          <div ref="mermaidContainer" class="mermaid-container"></div>
        </section>

        <!-- Full Markdown Document -->
        <section class="news-section">
          <div class="editorial-news-item full-markdown-body" v-html="renderMarkdown(briefing.full_markdown)"></div>
        </section>
      </template>

      <!-- ⚡ 实时资讯流区域 -->
      <section class="feed-section">
        <h2 class="section-title">实时资讯流 ({{ feedItems.length }})</h2>
        <div v-if="feedItems.length === 0" class="empty-state">
          <p class="text-muted">今日暂无采集数据。</p>
        </div>
        <div v-else class="feed-list">
          <a
            v-for="item in feedItems"
            :key="item.id"
            :href="item.url"
            target="_blank"
            rel="noopener"
            class="feed-card editorial-news-item"
          >
            <div class="feed-score-wrapper">
              <div class="feed-scores-multi">
                <span class="feed-score" :class="scoreClass(item.score)" title="综合得分">{{ item.score }}</span>
                <div class="sub-scores">
                  <span class="sub-score text-muted" title="技术实用分">T:{{ item.tech_utility_score || 0 }}</span>
                  <span class="sub-score text-muted" title="宏观影响分">M:{{ item.macro_impact_score || 0 }}</span>
                </div>
              </div>
            </div>
            <div class="feed-content">
              <h3 class="feed-title">
                <span v-if="item.is_pushed_instantly" class="instant-badge" title="触发了即时推送">⚡</span>
                {{ item.title }}
              </h3>
              <div class="feed-meta">
                <span class="text-muted">{{ formatTime(item.collected_at) }}</span>
                <span class="separator">·</span>
                <span :class="['tag', 'tag-sm', sourceTagClass(item.source)]">{{ sourceLabel(item.source) }}</span>
              </div>
            </div>
          </a>
        </div>
      </section>

    </template>

    <button class="back-to-top-btn" type="button" @click="scrollToTop" title="回到顶部">
      ↑
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { deleteBriefing, fetchBriefingDetail, fetchFeed } from '../api.js'

const props = defineProps({
  date: { type: String, required: true },
})

const router = useRouter()
const briefing = ref(null)
const feedItems = ref([])
const loading = ref(true)
const deleting = ref(false)
const expandedBgs = ref(new Set())
const mermaidContainer = ref(null)
const highlightedNewsId = ref(null)

function sourceTagClass(source) {
  const map = {
    github: 'tag-github',
    hackernews: 'tag-hackernews',
    huggingface: 'tag-huggingface',
  }
  return map[(source || '').toLowerCase()] || 'tag-category'
}

function sourceLabel(source) {
  return source || 'RSS'
}

function scoreClass(score) {
  if (score >= 90) return 'score-high'
  if (score >= 70) return 'score-medium'
  return 'score-low'
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function parseAITags(tagsStr) {
  if (!tagsStr) return [];
  if (Array.isArray(tagsStr)) return tagsStr;
  try {
    const tags = JSON.parse(tagsStr);
    return Array.isArray(tags) ? tags : [];
  } catch (e) {
    return [];
  }
}

function toggleBackground(id) {
  const next = new Set(expandedBgs.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedBgs.value = next
}

function newsAnchorId(item) {
  return `news-item-${item.id}`
}



async function handleDeleteBriefing() {
  if (!briefing.value || deleting.value) return

  const confirmed = window.confirm(`确定删除 ${props.date} 的早报吗？只删除精选摘要数据，实时资讯流将保留。`)
  if (!confirmed) return

  deleting.value = true
  try {
    await deleteBriefing(props.date)
    // 重新加载数据，不再返回首页
    await loadData()
  } catch (err) {
    window.alert(`删除失败：${err.message}`)
  } finally {
    deleting.value = false
  }
}

function renderMarkdown(text) {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const html = escaped
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n/g, '<br>')

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['strong', 'em', 'code', 'h2', 'h3', 'h4', 'ul', 'li', 'br', 'hr', 'blockquote', 'a', 'p'],
    ALLOWED_ATTR: ['href', 'target', 'rel'],
  })
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

async function renderMermaid() {
  if (!briefing.value?.mindmap_mermaid || !mermaidContainer.value) return

  try {
    const mermaid = await import('mermaid')
    mermaid.default.initialize({
      startOnLoad: false,
      theme: 'dark',
      themeVariables: {
        primaryColor: '#6366f1',
        primaryTextColor: '#f1f5f9',
        primaryBorderColor: '#8b5cf6',
        lineColor: '#64748b',
        secondaryColor: '#1e293b',
        tertiaryColor: '#111827',
      },
    })

    const renderId = `mindmap-svg-${briefing.value.id}`
    const { svg } = await mermaid.default.render(
      renderId,
      briefing.value.mindmap_mermaid,
    )
    mermaidContainer.value.innerHTML = svg
  } catch (err) {
    console.error('Mermaid 渲染失败:', err)
    mermaidContainer.value.innerHTML = `
      <pre class="mermaid-fallback"><code>${escapeHtml(briefing.value.mindmap_mermaid)}</code></pre>
    `
  }
}

async function loadData() {
  loading.value = true
  briefing.value = null
  feedItems.value = []
  deleting.value = false
  expandedBgs.value = new Set()
  highlightedNewsId.value = null

  try {
    // Vercel 最佳实践: async-parallel 并发获取相互独立的数据
    const [briefingData, feedData] = await Promise.all([
      fetchBriefingDetail(props.date).catch(() => null),
      fetchFeed(props.date).catch(() => [])
    ])
    
    briefing.value = briefingData
    feedItems.value = feedData
  } catch (err) {
    console.error('加载数据失败:', err)
  } finally {
    loading.value = false
  }

  if (briefing.value?.mindmap_mermaid) {
    await nextTick()
    await renderMermaid()
  }
}

onMounted(loadData)

watch(
  () => props.date,
  () => {
    loadData()
  },
)
</script>

<style scoped>
.back-link {
  display: inline-block;
  margin-bottom: 1.5rem;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  transition: color var(--transition-fast);
}

.back-link:hover {
  color: var(--color-accent-indigo);
}

.loading-state {
  padding: 2rem 0;
}

.empty-state {
  text-align: center;
  padding: 2rem 1rem;
}

/* Detail Header */
.detail-header {
  margin-bottom: 2rem;
}

.detail-header-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.detail-title {
  font-size: 1.8rem;
  font-weight: 800;
  margin-bottom: 0.5rem;
  letter-spacing: -0.01em;
}

.detail-overview {
  color: var(--color-text-secondary);
  font-size: 1rem;
}

.btn-danger {
  background: rgba(244, 63, 94, 0.12);
  color: var(--color-accent-rose);
  border: 1px solid rgba(244, 63, 94, 0.35);
}

.btn-danger:hover {
  background: rgba(244, 63, 94, 0.18);
  border-color: rgba(244, 63, 94, 0.55);
}

/* Mindmap */
.mindmap-section {
  padding: 1.5rem;
  margin-bottom: 2rem;
  overflow-x: auto;
}

.section-title {
  font-size: 1.1rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 1rem;
  margin-bottom: 2rem;
}

.mermaid-container {
  display: flex;
  justify-content: center;
  min-height: 200px;
}

.mermaid-container :deep(svg) {
  max-width: 100%;
  height: auto;
}

.mermaid-fallback {
  background: var(--color-bg-secondary);
  padding: 1rem;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

/* News Section */
.news-section {
  margin-bottom: 2rem;
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.editorial-news-item {
  padding: 2rem 0;
  scroll-margin-top: 84px;
  border-bottom: 1px solid var(--color-border);
}

.editorial-news-item:last-child {
  border-bottom: none;
}

.news-card--highlighted {
  border-left: 3px solid var(--color-accent-cyan);
  padding-left: 1.5rem;
  background: rgba(6, 182, 212, 0.03);
}

.news-card--dimmed {
  opacity: 0.55;
  filter: grayscale(0.5);
  transition: opacity var(--transition-normal);
}

.news-card--dimmed:hover {
  opacity: 0.95;
  filter: grayscale(0);
}

.mermaid-container :deep(.mindmap-clickable-node) {
  cursor: pointer;
}

.mermaid-container :deep(.mindmap-clickable-node:hover rect),
.mermaid-container :deep(.mindmap-clickable-node:hover circle),
.mermaid-container :deep(.mindmap-clickable-node:hover ellipse),
.mermaid-container :deep(.mindmap-clickable-node:hover polygon),
.mermaid-container :deep(.mindmap-clickable-node:hover path) {
  filter: brightness(1.18);
}

.mermaid-container :deep(.mindmap-clickable-node:hover text),
.mermaid-container :deep(.mindmap-clickable-node:hover tspan),
.mermaid-container :deep(.mindmap-clickable-node:hover .nodeLabel) {
  fill: var(--color-accent-cyan) !important;
}

.back-to-top-btn {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 900;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid rgba(99, 102, 241, 0.45);
  background: rgba(17, 24, 39, 0.86);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(12px);
  cursor: pointer;
  font-size: 1.2rem;
  font-weight: 700;
  transition: all var(--transition-normal);
}

.back-to-top-btn:hover {
  border-color: var(--color-accent-cyan);
  color: var(--color-accent-cyan);
  transform: translateY(-2px);
}

.news-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.news-card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.news-link {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  transition: color var(--transition-fast);
}

.news-link:hover {
  color: var(--color-accent-indigo);
}

.news-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 0.75rem;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.news-summary {
  color: var(--color-text-secondary);
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

/* Key Points */
.key-points {
  list-style: none;
  margin-bottom: 0.75rem;
  padding-left: 0;
}

.key-points li {
  position: relative;
  padding-left: 1.25rem;
  margin-bottom: 0.4rem;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  line-height: 1.5;
}

.key-points li::before {
  content: '▸';
  position: absolute;
  left: 0;
  color: var(--color-accent-indigo);
  font-weight: 700;
}

/* Importance */
.importance {
  font-size: 0.88rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: rgba(99, 102, 241, 0.06);
  border-left: 3px solid var(--color-accent-indigo);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

/* Background */
.toggle-bg-btn {
  margin-top: 0.25rem;
}

.background-content {
  margin-top: 0.75rem;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.background-content :deep(code) {
  background: rgba(99, 102, 241, 0.15);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
}

.background-content :deep(strong) {
  color: var(--color-text-primary);
}

.background-content :deep(h3),
.background-content :deep(h4) {
  color: var(--color-text-primary);
  margin: 0.75rem 0 0.3rem;
}

.background-content :deep(ul) {
  padding-left: 1.25rem;
  margin: 0.3rem 0;
}

/* Feed Section */
.feed-section {
  margin-top: 3rem;
  margin-bottom: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--color-border);
}

.feed-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.feed-card {
  display: flex;
  align-items: flex-start;
  padding: 1.5rem 0;
  gap: 1.5rem;
  color: inherit;
  border-bottom: 1px solid var(--color-border);
  transition: opacity var(--transition-fast);
}

.feed-card:last-child {
  border-bottom: none;
}

.feed-card:hover {
  opacity: 0.7;
}

.feed-score-wrapper {
  flex-shrink: 0;
  width: 40px;
  text-align: center;
}

.feed-score {
  font-weight: 800;
  font-size: 1.1rem;
}

.score-high { color: var(--color-accent-rose); }
.score-medium { color: var(--color-accent-amber); }
.score-low { color: var(--color-text-muted); }

.feed-content {
  flex: 1;
  min-width: 0;
}

.feed-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.instant-badge {
  font-size: 0.85rem;
}

.feed-meta {
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 6px;
}

.separator {
  color: var(--color-border);
}

.tag-sm {
  font-size: 0.65rem;
  padding: 1px 6px;
}

@media (max-width: 640px) {
  .detail-header-main {
    flex-direction: column;
  }

  .detail-title {
    font-size: 1.4rem;
  }
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.news-link {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  transition: color var(--transition-fast);
}

.news-link:hover {
  color: var(--color-accent-indigo);
}

.news-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 0.75rem;
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.news-summary {
  color: var(--color-text-secondary);
  font-size: 0.95rem;
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

/* Key Points */
.key-points {
  list-style: none;
  margin-bottom: 0.75rem;
  padding-left: 0;
}

.key-points li {
  position: relative;
  padding-left: 1.25rem;
  margin-bottom: 0.4rem;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  line-height: 1.5;
}

.key-points li::before {
  content: '▸';
  position: absolute;
  left: 0;
  color: var(--color-accent-indigo);
  font-weight: 700;
}

/* Importance */
.importance {
  font-size: 0.88rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: rgba(99, 102, 241, 0.06);
  border-left: 3px solid var(--color-accent-indigo);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

/* Background */
.toggle-bg-btn {
  margin-top: 0.25rem;
}

.background-content {
  margin-top: 0.75rem;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
  line-height: 1.7;
  color: var(--color-text-secondary);
}

.background-content :deep(code) {
  background: rgba(99, 102, 241, 0.15);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
}

.background-content :deep(strong) {
  color: var(--color-text-primary);
}

.background-content :deep(h3),
.background-content :deep(h4) {
  color: var(--color-text-primary);
  margin: 0.75rem 0 0.3rem;
}

.background-content :deep(ul) {
  padding-left: 1.25rem;
  margin: 0.3rem 0;
}

/* Feed Section */
.feed-section {
  margin-top: 3rem;
  margin-bottom: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--color-border);
}

.feed-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.feed-card {
  display: flex;
  align-items: flex-start;
  padding: 1.5rem 0;
  gap: 1.5rem;
  color: inherit;
  border-bottom: 1px solid var(--color-border);
  transition: opacity var(--transition-fast);
}

.feed-card:last-child {
  border-bottom: none;
}

.feed-card:hover {
  opacity: 0.7;
}

.feed-score-wrapper {
  flex-shrink: 0;
  width: 40px;
  text-align: center;
}

.feed-score {
  font-weight: 800;
  font-size: 1.1rem;
}

.score-high { color: var(--color-accent-rose); }
.score-medium { color: var(--color-accent-amber); }
.score-low { color: var(--color-text-muted); }

.feed-content {
  flex: 1;
  min-width: 0;
}

.feed-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.instant-badge {
  font-size: 0.85rem;
}

.feed-meta {
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 6px;
}

.separator {
  color: var(--color-border);
}

.tag-sm {
  font-size: 0.65rem;
  padding: 1px 6px;
}

@media (max-width: 640px) {
  .detail-header-main {
    flex-direction: column;
  }

  .detail-title {
    font-size: 1.4rem;
  }

  .news-card {
    padding: 1rem;
  }

  .feed-card {
    padding: 0.75rem;
    gap: 0.75rem;
  }

  .feed-title {
    font-size: 0.95rem;
  }
}
</style>

<style scoped>
.full-markdown-body {
  padding: 1.5rem;
  line-height: 1.7;
  color: var(--color-text-primary);
  font-size: 1rem;
}

.full-markdown-body :deep(h2) {
  margin-top: 2rem;
  margin-bottom: 1rem;
  color: var(--color-accent-indigo);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0.5rem;
}

.full-markdown-body :deep(h3) {
  margin-top: 1.5rem;
  margin-bottom: 0.8rem;
  color: var(--color-text-primary);
}

.full-markdown-body :deep(blockquote) {
  border-left: 4px solid var(--color-accent-cyan);
  padding-left: 1rem;
  margin-left: 0;
  color: var(--color-text-secondary);
  background: rgba(6, 182, 212, 0.05);
  padding: 0.5rem 1rem;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.feed-scores-multi {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.sub-scores {
  display: flex;
  gap: 4px;
  font-size: 0.7rem;
}

.sub-score {
  background: var(--color-bg-tertiary);
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
