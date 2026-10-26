<template>
  <div
    ref="root"
    class="media-scrub"
    aria-hidden="true"
    @pointerenter="handleEnter"
    @pointermove="handleMove"
    @pointerleave="handleLeave"
  >
    <template v-if="active">
      <div class="media-scrub-frame" :style="frameStyle"></div>
      <div class="media-scrub-playhead" :style="{ left: `${position * 100}%` }"></div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

// Matches the backend sprite grid (SCRUB_COLUMNS x SCRUB_ROWS).
const COLUMNS = 6
const ROWS = 5
const FRAMES = COLUMNS * ROWS
// A short dwell keeps a sweep across many cards from loading every sheet.
const LOAD_DELAY_MS = 120
// The first request starts generation; retry while the pointer stays.
const RETRY_DELAYS_MS = [1500, 2500, 4000]
const UNAVAILABLE_MS = 60 * 1000

// Shared by every card, so a sheet loads once per page.
const readySources = new Set()
const unavailableUntil = new Map()

const props = defineProps({
  src: { type: String, default: '' },
})

const emit = defineEmits(['active'])

const root = ref(null)
const hovering = ref(false)
const loaded = ref(false)
const position = ref(0)
const active = computed(() => hovering.value && loaded.value)

let loadTimer = 0
let retryTimer = 0
let frameRequest = 0
let pendingClientX = 0
let attempt = 0

const frameStyle = computed(() => {
  const index = Math.min(FRAMES - 1, Math.floor(position.value * FRAMES))
  const column = index % COLUMNS
  const row = Math.floor(index / COLUMNS)
  return {
    backgroundImage: `url("${props.src}")`,
    backgroundSize: `${COLUMNS * 100}% ${ROWS * 100}%`,
    backgroundPosition: `${(column / (COLUMNS - 1)) * 100}% ${(row / (ROWS - 1)) * 100}%`,
  }
})

function load() {
  const src = props.src
  if (!src || !hovering.value) return
  if (readySources.has(src)) {
    loaded.value = true
    return
  }
  if ((unavailableUntil.get(src) || 0) > Date.now()) return
  const image = new Image()
  image.onload = () => {
    readySources.add(src)
    if (props.src === src) loaded.value = true
  }
  // A 202 while the sheet is being made also lands here.
  image.onerror = () => {
    if (props.src !== src) return
    if (hovering.value && attempt < RETRY_DELAYS_MS.length) {
      retryTimer = window.setTimeout(load, RETRY_DELAYS_MS[attempt])
      attempt += 1
    } else {
      unavailableUntil.set(src, Date.now() + UNAVAILABLE_MS)
    }
  }
  image.src = src
}

function updatePosition(clientX) {
  const rect = root.value?.getBoundingClientRect()
  if (rect?.width > 0) position.value = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
}

function handleEnter(event) {
  if (event.pointerType !== 'mouse' || !props.src) return
  hovering.value = true
  updatePosition(event.clientX)
  if (readySources.has(props.src)) loaded.value = true
  else loadTimer = window.setTimeout(load, LOAD_DELAY_MS)
}

function handleMove(event) {
  if (!hovering.value) return
  pendingClientX = event.clientX
  if (frameRequest) return
  frameRequest = window.requestAnimationFrame(() => {
    frameRequest = 0
    updatePosition(pendingClientX)
  })
}

function clearTimers() {
  window.clearTimeout(loadTimer)
  window.clearTimeout(retryTimer)
  window.cancelAnimationFrame(frameRequest)
  loadTimer = 0
  retryTimer = 0
  frameRequest = 0
}

function handleLeave() {
  hovering.value = false
  attempt = 0
  clearTimers()
}

watch(() => props.src, (src) => {
  attempt = 0
  clearTimers()
  loaded.value = readySources.has(src)
})

watch(active, value => emit('active', value))

onBeforeUnmount(clearTimers)
</script>

<style scoped>
.media-scrub {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.media-scrub-frame {
  position: absolute;
  inset: 0;
  background-color: var(--v-bg-black);
  background-repeat: no-repeat;
}

.media-scrub-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--v-danger);
  box-shadow: 0 0 0 1px color-mix(in srgb, black 25%, transparent);
  pointer-events: none;
}
</style>
