<template>
  <div class="v-media-thumb" :class="{ 'is-pending': isPending, 'is-ready': isReady, 'is-failed': isFailed }">
    <img
      v-if="resolvedSrc"
      class="v-media-thumb-image"
      :class="{ 'is-visible': isReady }"
      :src="resolvedSrc"
      :alt="alt"
      loading="lazy"
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
import { onBeforeUnmount, ref, watch } from 'vue'
import api from '../../lib/api'

const thumbnailStateCache = new Map()

const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  pollMs: { type: Number, default: 1500 },
  pollPending: { type: Boolean, default: true },
})

const resolvedSrc = ref('')
const isPending = ref(false)
const isReady = ref(false)
const isFailed = ref(false)
let refreshTimer = null
let requestToken = 0

function clearRefreshTimer() {
  if (!refreshTimer) return
  clearTimeout(refreshTimer)
  refreshTimer = null
}

function scheduleRetry() {
  clearRefreshTimer()
  refreshTimer = setTimeout(() => {
    if (props.src && thumbnailStateCache.get(props.src) === 'pending') {
      thumbnailStateCache.delete(props.src)
    }
    refreshSource(props.src)
  }, Math.max(400, props.pollMs || 1500))
}

async function refreshSource(src) {
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

  const cachedState = thumbnailStateCache.get(src)
  if (cachedState === 'ready') {
    resolvedSrc.value = src
    isPending.value = false
    isReady.value = false
    isFailed.value = false
    return
  }
  if (cachedState === 'pending') {
    resolvedSrc.value = ''
    isPending.value = props.pollPending
    isReady.value = false
    isFailed.value = false
    if (props.pollPending) scheduleRetry()
    return
  }

  isFailed.value = false
  resolvedSrc.value = src
  isPending.value = false
  isReady.value = false

  try {
    const response = await api.head(src)
    if (token !== requestToken) return
    const contentType = String(response.headers?.['content-type'] || '').toLowerCase()
    const pending = contentType.includes('image/svg+xml')
    thumbnailStateCache.set(src, pending ? 'pending' : 'ready')
    isPending.value = pending && props.pollPending
    if (pending) {
      resolvedSrc.value = ''
      isReady.value = false
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

function handleImageLoad() {
  if (!props.src || isPending.value) return
  thumbnailStateCache.set(props.src, 'ready')
  isReady.value = true
  isFailed.value = false
}

function handleImageError() {
  if (isPending.value) return
  if (props.src) thumbnailStateCache.delete(props.src)
  resolvedSrc.value = ''
  isReady.value = false
  isFailed.value = true
}

watch(() => props.src, (next) => {
  isReady.value = false
  refreshSource(next)
}, { immediate: true })

onBeforeUnmount(() => {
  requestToken += 1
  clearRefreshTimer()
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
