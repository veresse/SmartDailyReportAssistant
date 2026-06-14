<template>
  <div class="score-ring-wrapper" :style="{ width: `${size}px`, height: `${size}px` }">
    <!-- Loading State -->
    <template v-if="loading">
      <svg :width="size" :height="size" class="ring-svg">
        <circle
          class="ring-track"
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          :stroke-width="stroke"
          fill="none"
        />
      </svg>
      <div class="ring-center">
        <div class="skeleton-dot"></div>
      </div>
    </template>
    
    <!-- Empty State -->
    <template v-else-if="score === null || score === 0 || score === undefined">
      <svg :width="size" :height="size" class="ring-svg">
        <circle
          class="ring-track"
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          :stroke-width="stroke"
          fill="none"
        />
      </svg>
      <div class="ring-center">
        <span class="empty-text">--</span>
      </div>
    </template>

    <!-- Normal State -->
    <template v-else>
      <svg :width="size" :height="size" class="ring-svg">
        <defs v-if="level === 'high' || level === 'mid'">
          <!-- High Score Gradient -->
          <linearGradient id="score-grad-high" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#22C55E" />
            <stop offset="100%" stop-color="#16A34A" />
          </linearGradient>
          <!-- Mid Score Gradient -->
          <linearGradient id="score-grad-mid" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#F59E0B" />
            <stop offset="100%" stop-color="#FB923C" />
          </linearGradient>
        </defs>

        <circle
          class="ring-track"
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          :stroke-width="stroke"
          fill="none"
        />
        <circle
          class="ring-progress"
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          :stroke-width="stroke"
          fill="none"
          stroke-linecap="round"
          :stroke="strokeColor"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="dashoffset"
        />
      </svg>
      <div class="ring-center" :style="{ color: textColor }">
        <span class="score-number">{{ displayScore }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'

const props = defineProps({
  score: {
    type: Number,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  size: {
    type: Number,
    default: 72
  },
  stroke: {
    type: Number,
    default: 6
  }
})

const radius = computed(() => (props.size - props.stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)

const level = computed(() => {
  if (props.score >= 80) return 'high'
  if (props.score >= 50) return 'mid'
  return 'low'
})

const strokeColor = computed(() => {
  if (level.value === 'high') return 'url(#score-grad-high)'
  if (level.value === 'mid') return 'url(#score-grad-mid)'
  return '#94A3B8'
})

const textColor = computed(() => {
  if (level.value === 'high') return '#22C55E'
  if (level.value === 'mid') return '#F59E0B'
  return '#94A3B8'
})

// Animation state
const animatedScore = ref(0)
const displayScore = computed(() => Math.round(animatedScore.value))

const dashoffset = computed(() => {
  const progress = animatedScore.value / 100
  return circumference.value * (1 - progress)
})

function animateValue(target) {
  const start = animatedScore.value
  const diff = target - start
  if (diff === 0) return
  
  const duration = 800 // ms
  const startTime = performance.now()
  
  function step(currentTime) {
    let elapsed = currentTime - startTime
    if (elapsed > duration) elapsed = duration
    
    // easeOutCubic
    const t = elapsed / duration
    const ease = 1 - Math.pow(1 - t, 3)
    
    animatedScore.value = start + diff * ease
    
    if (elapsed < duration) {
      requestAnimationFrame(step)
    }
  }
  
  requestAnimationFrame(step)
}

onMounted(() => {
  if (!props.loading && props.score) {
    animateValue(props.score)
  }
})

watch(() => props.score, (newVal) => {
  if (newVal) {
    animateValue(newVal)
  }
})
</script>

<style scoped>
.score-ring-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ring-svg {
  transform: rotate(-90deg); /* 起笔正上方 */
  overflow: visible;
}

.ring-track {
  stroke: var(--color-track, #EEF0F4);
}

.ring-progress {
  transition: stroke-dashoffset 0.1s linear; /* fallback to js animation for smooth */
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s ease-out;
}

.score-ring-wrapper:hover .ring-center {
  transform: scale(1.06);
}

.score-number {
  font-size: 22px; /* For 72px default */
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.empty-text {
  color: var(--color-text-muted);
  font-size: 18px;
  font-weight: 600;
}

.skeleton-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #ECEEF5;
  animation: pulse-dot 1.5s infinite alternate;
}

@keyframes pulse-dot {
  0% { opacity: 0.5; }
  100% { opacity: 1; }
}
</style>
