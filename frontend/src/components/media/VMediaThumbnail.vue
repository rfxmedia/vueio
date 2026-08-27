<template>
  <div ref="thumbnailRoot" class="v-media-thumb" :class="{ 'is-pending': isPending, 'is-ready': isReady, 'is-failed': isFailed }">
    <img
      v-if="resolvedSrc"
      class="v-media-thumb-image"
      :class="{ 'is-visible': isReady }"
      :src="resolvedSrc"
      :alt="alt"
      loading="lazy"
      decoding="async"
      fetchpriority="low"
      @load="handleImageLoad"
      @error="handleImageError"
    />
    <div v-if="isPending" class="v-media-thumb-status" aria-hidden="true">
      <span class="v-media-thumb-spinner"></span>
    </div>
    <div v-else-if="isFailed || !resolvedSrc" class="v-media-thumb-status is-failed" aria-hidden="true">
      <svg class="icon"><use href="#icon-image" /></svg>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  clearThumbnailState,
  getThumbnailState,
  observeThumbnail,
  probeThumbnail,
  setThumbnailState,
  subscribeToThumbnailVisibility,
} from './mediaThumbnailProbe'

const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  pollMs: { type: Number, default: 1500 },
  pollPending: { type: Boolean, default: true },
})

const emit = defineEmits(['visible'])

const resolvedSrc = ref('')
const isPending = ref(false)
const isReady = ref(false)
const isFailed = ref(false)
const thumbnailRoot = ref(null)
let refreshTimer = null
let requestToken = 0
let isObserved = false
let isDocumentVisible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
let retryDelayMs = Math.max(400, props.pollMs || 1500)
let visibleEmittedSrc = ''
let stopObserving = null
let stopVisibilitySubscription = null

function clearRefreshTimer() {
  if (!refreshTimer) return
  clearTimeout(refreshTimer)
  refreshTimer = null
}

function canProbe() {
  return isObserved && isDocumentVisible
}

function scheduleRetry() {
  clearRefreshTimer()
  if (!canProbe() || !props.pollPending) return
  const delay = retryDelayMs
  refreshTimer = setTimeout(() => {
    if (!canProbe()) return
    retryDelayMs = Math.min(delay * 2, 15000)
    refreshSource(props.src, { forceProbe: true })
  }, delay)
}

async function refreshSource(src, { forceProbe = false } = {}) {
  clearRefreshTimer()
  requestToken += 1
  const token = requestToken

  if (!src) {
    resolvedSrc.value = ''
    isPending.value = false
    isReady.value = false
    isFailed.value = false
    return
  }

  resolvedSrc.value = ''
  isFailed.value = false
  isPending.value = false
  isReady.value = false

  // Do not assign an image URL until the thumbnail is near the viewport.
  // Native lazy loading is retained as a second browser-level safeguard.
  if (!canProbe()) return

  const cachedState = getThumbnailState(src)
  if (cachedState === 'ready') {
    isPending.value = false
    isReady.value = true
    resolvedSrc.value = src
    return
  }
  if (cachedState === 'pending' && !forceProbe) {
    resolvedSrc.value = ''
    isPending.value = props.pollPending
    isReady.value = false
    if (props.pollPending) scheduleRetry()
    return
  }

  isPending.value = true

  try {
    const state = await probeThumbnail(src)
    if (token !== requestToken) return
    const pending = state === 'pending'
    isPending.value = pending && props.pollPending
    if (pending) {
      resolvedSrc.value = ''
      isReady.value = false
    } else {
      resolvedSrc.value = src
    }
    if (pending && props.pollPending) {
      scheduleRetry()
    }
  } catch {
    if (token !== requestToken) return
    isPending.value = false
    isFailed.value = false
  }
}

function handleIntersection(intersecting) {
  isObserved = intersecting
  if (!intersecting) {
    clearRefreshTimer()
    return
  }
  if (props.src && visibleEmittedSrc !== props.src) {
    visibleEmittedSrc = props.src
    emit('visible', props.src)
  }
  refreshSource(props.src)
}

function handleVisibilityChange(visible) {
  isDocumentVisible = visible
  if (!visible) {
    clearRefreshTimer()
    return
  }
  if (isObserved) refreshSource(props.src)
}

function handleImageLoad() {
  if (!props.src || isPending.value) return
  setThumbnailState(props.src, 'ready')
  isReady.value = true
  isFailed.value = false
}

function handleImageError() {
  if (isPending.value) return
  if (props.src) clearThumbnailState(props.src)
  resolvedSrc.value = ''
  isReady.value = false
  isFailed.value = true
}

watch(() => props.src, (next) => {
  requestToken += 1
  clearRefreshTimer()
  retryDelayMs = Math.max(400, props.pollMs || 1500)
  visibleEmittedSrc = ''
  isReady.value = false
  refreshSource(next)
}, { immediate: true })

onMounted(() => {
  stopVisibilitySubscription = subscribeToThumbnailVisibility(handleVisibilityChange)
  stopObserving = observeThumbnail(thumbnailRoot.value, handleIntersection)
})

onBeforeUnmount(() => {
  requestToken += 1
  clearRefreshTimer()
  stopObserving?.()
  stopVisibilitySubscription?.()
})
</script>

<style scoped>
.v-media-thumb {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: inherit;
  background: var(--v-surface-panel-soft);
}

.v-media-thumb-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity var(--v-duration-normal) var(--v-ease-emphasized), filter var(--v-duration-normal) var(--v-ease-emphasized), transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.v-media-thumb-image.is-visible {
  opacity: 1;
}

.v-media-thumb.is-pending .v-media-thumb-image {
  opacity: 0.28;
  filter: saturate(0.8);
}

.v-media-thumb-status {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(21, 24, 26, 0.18), rgba(16, 18, 20, 0.34));
  pointer-events: none;
}

.v-media-thumb-status.is-failed {
  color: var(--v-text-muted);
}

.v-media-thumb-status .icon {
  width: 20px;
  height: 20px;
  opacity: 0.65;
}

.v-media-thumb-spinner {
  width: 22px;
  height: 22px;
  border-radius: var(--v-radius-full);
  border: 2px solid var(--v-border);
  border-top-color: var(--v-border-hover);
  animation: v-spin 0.8s linear infinite;
  box-shadow: var(--v-shadow-glow);
}
</style>
