<template>
  <canvas ref="canvas" class="space-background"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const canvas = ref(null)

let ctx = null
let width = 0
let height = 0
let animationFrameId = null
let stars = []

// Mouse tracking
let targetVx = 0
let targetVy = 0
let currentVx = 0
let currentVy = 0
let lastMouseX = null
let lastMouseY = null
let mouseTimeout = null

const STAR_COUNT = 300
const BASE_SPEED = 0.05
const DAMPING = 0.05       // 平滑阻尼
const DECAY = 0.92         // 动量衰减
const MOUSE_SENSITIVITY = 0.08 // 鼠标移动的推力系数

class Star {
  constructor() {
    this.reset()
    // Randomize initial position anywhere on screen
    this.x = Math.random() * width
    this.y = Math.random() * height
  }

  reset() {
    this.x = Math.random() * width
    this.y = Math.random() * height
    this.z = Math.random() * 2 + 0.1 // Z-depth for parallax
    this.size = Math.random() * 1.5 + 0.5
    this.baseOpacity = Math.random() * 0.5 + 0.2
    this.twinklePhase = Math.random() * Math.PI * 2
    this.twinkleSpeed = Math.random() * 0.02 + 0.01
  }

  update(vx, vy) {
    // Parallax effect: closer stars (smaller Z) move faster
    const parallax = 1 / this.z
    
    // Base movement (drifting left/up slightly) + mouse movement
    this.x += (vx * parallax) - BASE_SPEED * parallax
    this.y += (vy * parallax) - BASE_SPEED * parallax

    // Twinkle
    this.twinklePhase += this.twinkleSpeed
    
    // Wrap around screen
    if (this.x < 0) this.x = width
    if (this.x > width) this.x = 0
    if (this.y < 0) this.y = height
    if (this.y > height) this.y = 0
  }

  draw(ctx) {
    const opacity = this.baseOpacity + Math.sin(this.twinklePhase) * 0.2
    
    ctx.beginPath()
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(255, 255, 255, ${Math.max(0.1, opacity)})`
    
    // Add a slight glow to larger stars
    if (this.size > 1.2) {
      ctx.shadowBlur = 6
      ctx.shadowColor = 'rgba(255, 255, 255, 0.4)'
    } else {
      ctx.shadowBlur = 0
    }
    
    ctx.fill()
  }
}

function initCanvas() {
  if (!canvas.value) return
  ctx = canvas.value.getContext('2d')
  
  const resize = () => {
    width = window.innerWidth
    height = window.innerHeight
    canvas.value.width = width
    canvas.value.height = height
  }
  
  window.addEventListener('resize', resize)
  resize()
  
  for (let i = 0; i < STAR_COUNT; i++) {
    stars.push(new Star())
  }
}

function handleMouseMove(e) {
  // Use e.movementX/Y for direct delta if available, fallback to clientX difference
  let dx = e.movementX;
  let dy = e.movementY;
  
  if (dx === undefined) {
    if (lastMouseX !== null && lastMouseY !== null) {
      dx = e.clientX - lastMouseX;
      dy = e.clientY - lastMouseY;
    } else {
      dx = 0;
      dy = 0;
    }
  }
  
  // Accumulate target velocity (momentum)
  targetVx -= dx * MOUSE_SENSITIVITY
  targetVy -= dy * MOUSE_SENSITIVITY
  
  // Cap the maximum target velocity to prevent insane speeds
  const maxV = 20;
  if (targetVx > maxV) targetVx = maxV;
  if (targetVx < -maxV) targetVx = -maxV;
  if (targetVy > maxV) targetVy = maxV;
  if (targetVy < -maxV) targetVy = -maxV;
  
  lastMouseX = e.clientX
  lastMouseY = e.clientY
}

function animate() {
  if (!ctx) return
  
  // Clear with a very slight trailing effect (not fully clear)
  ctx.fillStyle = 'rgba(2, 0, 10, 1)' // Deep space color
  ctx.fillRect(0, 0, width, height)
  
  // Decay target velocity back to zero over time
  targetVx *= DECAY;
  targetVy *= DECAY;
  
  // Smoothly interpolate current velocity towards target velocity
  currentVx += (targetVx - currentVx) * DAMPING
  currentVy += (targetVy - currentVy) * DAMPING
  
  for (let star of stars) {
    star.update(currentVx, currentVy)
    star.draw(ctx)
  }
  
  animationFrameId = requestAnimationFrame(animate)
}

onMounted(() => {
  initCanvas()
  window.addEventListener('mousemove', handleMouseMove)
  animate()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', initCanvas)
  window.removeEventListener('mousemove', handleMouseMove)
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
})
</script>

<style scoped>
.space-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
  background-color: #02000a;
}
</style>
