<template>
  <Teleport to="body">
    <Transition name="upload-tray">
      <section
        v-if="items.length"
        ref="rootEl"
        class="upload-tray"
        :class="[`is-${state}`, { 'is-collapsed': collapsed }]"
        aria-labelledby="upload-tray-title"
      >
        <span class="v-sr-only" role="status">{{ announcement }}</span>
        <header class="upload-tray-head">
          <span class="upload-tray-mark" aria-hidden="true">
            <svg v-if="state === 'done'" class="icon"><use href="#icon-check" /></svg>
            <svg v-else-if="state === 'error'" class="icon"><use href="#icon-alert" /></svg>
            <svg v-else class="icon"><use href="#icon-upload" /></svg>
          </span>
          <div class="upload-tray-heading" @click="collapsed = !collapsed">
            <span id="upload-tray-title" class="upload-tray-title">{{ title }}</span>
            <span v-if="meta" class="upload-tray-meta">{{ meta }}</span>
          </div>
          <button
            type="button"
            class="v-btn v-btn-quiet v-btn-icon upload-tray-action"
            :aria-expanded="collapsed ? 'false' : 'true'"
            aria-controls="upload-tray-list"
            :aria-label="collapsed ? 'Show upload list' : 'Hide upload list'"
            :title="collapsed ? 'Show upload list' : 'Hide upload list'"
            @click="collapsed = !collapsed"
          >
            <svg class="icon"><use :href="collapsed ? '#icon-chevron-up' : '#icon-chevron-down'" /></svg>
          </button>
          <button
            v-if="!active"
            type="button"
            class="v-btn v-btn-quiet v-btn-icon upload-tray-action"
            aria-label="Close uploads"
            title="Close"
            @click="dismiss"
          >
            <svg class="icon"><use href="#icon-close" /></svg>
          </button>
        </header>

        <div v-if="active" class="upload-tray-bar" aria-hidden="true">
          <span :style="{ width: `${overallPercent}%` }"></span>
        </div>

        <div v-show="!collapsed" id="upload-tray-list" class="upload-tray-body">
          <ul class="upload-tray-list">
            <li v-for="item in visibleItems" :key="item.id" class="upload-tray-item" :class="`is-${item.status}`">
              <span class="upload-tray-status" aria-hidden="true">
                <svg v-if="item.status === 'done'" class="icon"><use href="#icon-check" /></svg>
                <svg v-else-if="item.status === 'error'" class="icon"><use href="#icon-alert" /></svg>
                <svg v-else-if="item.status === 'canceled'" class="icon"><use href="#icon-close" /></svg>
                <svg v-else class="upload-tray-ring" viewBox="0 0 16 16">
                  <circle class="upload-tray-ring-track" cx="8" cy="8" r="6" />
                  <circle
                    class="upload-tray-ring-fill"
                    cx="8"
                    cy="8"
                    r="6"
                    pathLength="100"
                    :stroke-dasharray="`${item.progress || 0} 100`"
                  />
                </svg>
              </span>
              <span class="upload-tray-copy">
                <span class="upload-tray-name" :title="item.relPath || item.name">{{ item.name || item.relPath }}</span>
                <span class="upload-tray-detail" :title="itemDetail(item)">{{ itemDetail(item) }}</span>
              </span>
              <button
                v-if="item.status === 'error'"
                type="button"
                class="v-btn v-btn-ghost v-btn-xs"
                @click="upload.retryUpload(item)"
              >Retry</button>
              <button
                v-else-if="isActive(item)"
                type="button"
                class="v-btn v-btn-quiet v-btn-icon upload-tray-cancel"
                :aria-label="`Cancel upload of ${item.name}`"
                title="Cancel"
                @click="upload.cancelUpload(item)"
              >
                <svg class="icon"><use href="#icon-close" /></svg>
              </button>
            </li>
          </ul>
          <p v-if="hiddenCount" class="upload-tray-more">{{ hiddenCount }} more {{ hiddenCount === 1 ? 'file' : 'files' }}</p>
          <footer v-if="active" class="upload-tray-foot">
            <button type="button" class="v-btn v-btn-ghost v-btn-xs" @click="upload.cancelAllUploads()">Cancel all</button>
          </footer>
        </div>
      </section>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formatSizeBytes } from '../../utils/formatters'

const props = defineProps({
  upload: { type: Object, required: true },
})

const AUTO_HIDE_MS = 6000
const MAX_VISIBLE_ITEMS = 100
const STATUS_ORDER = { error: 0, uploading: 1, retrying: 1, pending: 2, done: 3, canceled: 4 }

const rootEl = ref(null)
const collapsed = ref(false)
let hideTimer = null
let resizeObserver = null

const items = computed(() => props.upload.uploadQueue || [])
const active = computed(() => Boolean(props.upload.uploadHasActive))
const isActive = item => ['pending', 'uploading', 'retrying'].includes(item.status)
const countOf = status => items.value.filter(item => item.status === status).length
const files = count => `${count} ${count === 1 ? 'file' : 'files'}`

const doneCount = computed(() => countOf('done'))
const failedCount = computed(() => countOf('error'))
const canceledCount = computed(() => countOf('canceled'))
const activeCount = computed(() => items.value.filter(isActive).length)
const state = computed(() => {
  if (active.value) return 'active'
  return failedCount.value ? 'error' : 'done'
})

const overallPercent = computed(() => {
  const totalBytes = items.value.reduce((sum, item) => sum + (item.size || 0), 0)
  if (!totalBytes) return 0
  const sentBytes = items.value.reduce((sum, item) => sum + (item.displayBytesUploaded ?? item.bytesUploaded ?? 0), 0)
  return Math.min(100, Math.round((sentBytes / totalBytes) * 100))
})

const title = computed(() => {
  if (active.value) return `Uploading ${files(activeCount.value)}`
  if (failedCount.value) return `${files(failedCount.value)} could not upload`
  if (doneCount.value) return `${files(doneCount.value)} uploaded`
  return 'Uploads canceled'
})

// Announce state changes, not every file count, so screen readers stay quiet.
const announcement = computed(() => (state.value === 'active' ? 'Uploading files' : title.value))

const destinations = computed(() => [...new Set(items.value.map(item => item.targetLabel).filter(Boolean))])
const meta = computed(() => {
  if (active.value) {
    const { speed, eta } = props.upload.uploadSummary || {}
    return [`${overallPercent.value}%`, speed, eta].filter(Boolean).join(' · ')
  }
  const parts = []
  if (failedCount.value && doneCount.value) parts.push(`${files(doneCount.value)} uploaded`)
  if (canceledCount.value && (doneCount.value || failedCount.value)) parts.push(`${canceledCount.value} canceled`)
  if (!parts.length && destinations.value.length === 1) parts.push(`To ${destinations.value[0]}`)
  return parts.join(' · ')
})

// Problems and live transfers stay on top; finished files settle below.
const sortedItems = computed(() => [...items.value].sort((a, b) => (
  (STATUS_ORDER[a.status] ?? 5) - (STATUS_ORDER[b.status] ?? 5)
)))
const visibleItems = computed(() => sortedItems.value.slice(0, MAX_VISIBLE_ITEMS))
const hiddenCount = computed(() => Math.max(0, items.value.length - MAX_VISIBLE_ITEMS))

function itemDetail(item) {
  if (item.status === 'error') return item.error || 'Upload failed'
  if (item.status === 'canceled') return 'Canceled'
  if (item.status === 'pending') return 'Waiting'
  if (item.status === 'retrying') return 'Connection interrupted. Retrying…'
  if (item.status === 'uploading') return [item.uploadedLabel, item.etaLabel].filter(Boolean).join(' · ')
  // One destination is already named in the header, so rows show size instead.
  if (destinations.value.length > 1 && item.targetLabel) return `To ${item.targetLabel}`
  return formatSizeBytes(item.size || 0)
}

function dismiss() {
  if (active.value) return
  props.upload.clearCompletedUploads()
}

// A clean finish leaves on its own; failures stay until someone reads them.
function scheduleAutoHide() {
  clearTimeout(hideTimer)
  hideTimer = null
  if (active.value || failedCount.value || !items.value.length) return
  hideTimer = setTimeout(() => {
    // Wait while a pointer rests on the tray or a keyboard user is inside it.
    if (rootEl.value?.matches(':hover, :has(:focus-visible)')) return scheduleAutoHide()
    dismiss()
  }, AUTO_HIDE_MS)
}

watch([active, failedCount, () => items.value.length], scheduleAutoHide)

// New files reopen the list so the person sees them start.
watch(() => items.value.length, (count, previous) => {
  if (count > (previous || 0)) collapsed.value = false
})

// Toasts share this corner; publish the tray height so they sit above it.
watch(rootEl, (el) => {
  resizeObserver?.disconnect()
  resizeObserver = null
  const root = document.documentElement
  if (!el) {
    root.style.removeProperty('--v-upload-tray-space')
    return
  }
  resizeObserver = new ResizeObserver(([entry]) => {
    root.style.setProperty('--v-upload-tray-space', `${Math.ceil(entry.borderBoxSize?.[0]?.blockSize ?? el.offsetHeight) + 10}px`)
  })
  resizeObserver.observe(el)
})

onBeforeUnmount(() => {
  clearTimeout(hideTimer)
  resizeObserver?.disconnect()
  document.documentElement.style.removeProperty('--v-upload-tray-space')
})
</script>

<style scoped>
.upload-tray {
  --upload-tray-tone: var(--v-info);
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: calc(var(--v-z-modal) - 10);
  display: flex;
  width: min(360px, calc(100vw - 36px));
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--v-menu-border);
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-menu-bg) 97%, transparent);
  box-shadow: 0 16px 38px rgba(0, 0, 0, 0.28);
  color: var(--v-text);
}

.upload-tray.is-done { --upload-tray-tone: var(--v-accent); }
.upload-tray.is-error { --upload-tray-tone: var(--v-danger); }

.upload-tray-head {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 52px;
  padding: 8px 8px 8px 12px;
}

.upload-tray-mark {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 6px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--upload-tray-tone) 14%, transparent);
  color: var(--upload-tray-tone);
}

.upload-tray-mark .icon {
  width: 14px;
  height: 14px;
}

.upload-tray-heading {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  cursor: pointer;
}

.upload-tray-title,
.upload-tray-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-tray-title {
  font-size: var(--v-text-base);
  font-weight: 600;
  line-height: 1.3;
}

.upload-tray-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-variant-numeric: tabular-nums;
}

.upload-tray-action {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
}

.upload-tray-bar {
  height: 2px;
  background: color-mix(in srgb, var(--v-text) 8%, transparent);
}

.upload-tray-bar span {
  display: block;
  height: 100%;
  background: var(--upload-tray-tone);
  transition: width var(--v-duration-normal) var(--v-ease-soft);
}

.upload-tray-body {
  border-top: 1px solid var(--v-menu-border);
}

.upload-tray-bar + .upload-tray-body {
  border-top: 0;
}

.upload-tray-list {
  max-height: min(280px, 45vh);
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  list-style: none;
}

.upload-tray-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 5px 10px 5px 14px;
}

.upload-tray-status {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  color: var(--v-text-muted);
}

.upload-tray-status .icon {
  width: 14px;
  height: 14px;
}

.upload-tray-item.is-done .upload-tray-status { color: var(--v-accent); }
.upload-tray-item.is-error .upload-tray-status { color: var(--v-danger); }

.upload-tray-ring {
  width: 15px;
  height: 15px;
  transform: rotate(-90deg);
}

.upload-tray-ring circle {
  fill: none;
  stroke-width: 2.25;
}

.upload-tray-ring-track {
  stroke: color-mix(in srgb, var(--v-text) 14%, transparent);
}

.upload-tray-ring-fill {
  stroke: var(--v-info);
  stroke-linecap: round;
  transition: stroke-dasharray var(--v-duration-normal) var(--v-ease-soft);
}

.upload-tray-ring-fill[stroke-dasharray^="0 "] {
  stroke: transparent;
}

.upload-tray-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.upload-tray-name,
.upload-tray-detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-tray-name {
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.35;
}

.upload-tray-item.is-canceled .upload-tray-name {
  color: var(--v-text-muted);
}

.upload-tray-detail {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
  font-variant-numeric: tabular-nums;
}

.upload-tray-item.is-error .upload-tray-detail {
  color: var(--v-danger-text);
}

.upload-tray-cancel {
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
}

.upload-tray-cancel .icon {
  width: 13px;
  height: 13px;
}

/* With a pointer, per-file cancel waits for hover so the list stays calm. */
@media (hover: hover) {
  .upload-tray-item:not(:hover, :focus-within) .upload-tray-cancel {
    opacity: 0;
  }
}

.upload-tray-more {
  margin: 0;
  padding: 2px 14px 8px 40px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.upload-tray-foot {
  display: flex;
  justify-content: flex-end;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--v-menu-border);
}

.upload-tray-enter-active,
.upload-tray-leave-active {
  transition: opacity var(--v-duration-normal) var(--v-ease-soft), transform var(--v-duration-normal) var(--v-ease-soft);
}

.upload-tray-enter-from,
.upload-tray-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

@media (max-width: 768px) {
  .upload-tray {
    right: 10px;
    bottom: calc(10px + env(safe-area-inset-bottom, 0px));
    width: calc(100vw - 20px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .upload-tray-enter-active,
  .upload-tray-leave-active,
  .upload-tray-bar span,
  .upload-tray-ring-fill {
    transition: none;
  }
}
</style>
