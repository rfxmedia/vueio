<template>
  <Teleport to="body">
    <Transition name="comment-mention-pop">
      <section
        v-if="open"
        :id="listboxId"
        ref="popoverRef"
        class="comment-mention-popover v-dropdown"
        :class="{ 'is-mobile-tray': mobileTray }"
        :style="positionStyle"
        role="listbox"
        aria-label="Project mentions"
      >
        <header class="comment-mention-header">
          <template v-if="mode === 'browse'">
            <button type="button" class="comment-mention-back" aria-label="Go back" @mousedown.prevent @click="$emit('back')">
              <svg class="icon"><use href="#icon-back"/></svg>
            </button>
            <div class="comment-mention-heading">
              <span class="comment-mention-eyebrow">Browse project</span>
              <strong>{{ browseTitle }}</strong>
            </div>
          </template>
          <template v-else>
            <span class="comment-mention-at" aria-hidden="true">@</span>
            <div class="comment-mention-heading">
              <strong>Mention project item</strong>
              <span>{{ query ? `Results for “${query}”` : 'Recent and nearby' }}</span>
            </div>
          </template>
          <svg v-if="loading" class="icon comment-mention-spinner"><use href="#icon-loader"/></svg>
        </header>

        <div class="comment-mention-scroll">
          <template v-if="mode === 'search'">
            <div v-for="group in groups" :key="group.type" class="comment-mention-group">
              <div class="comment-mention-group-header">
                <span>{{ group.label }}</span>
                <span>{{ group.items.length }}</span>
              </div>
              <button
                v-for="item in group.items"
                :id="optionId(searchItemIndex(item))"
                :key="`${item.target_type}:${item.target_id}`"
                type="button"
                class="comment-mention-row"
                :class="{ 'is-active': activeIndex === searchItemIndex(item) }"
                role="option"
                :aria-selected="activeIndex === searchItemIndex(item)"
                @mouseenter="$emit('set-active', searchItemIndex(item))"
                @mousedown.prevent
                @click="choose(item)"
              >
                <span class="comment-mention-icon" :class="`is-${item.kind || item.target_type}`">
                  <svg class="icon"><use :href="itemIcon(item)"/></svg>
                </span>
                <span class="comment-mention-row-copy">
                  <span class="comment-mention-label">{{ item.label }}</span>
                  <span v-if="item.sublabel" class="comment-mention-sublabel">{{ item.sublabel }}</span>
                </span>
                <span v-if="item.status" class="comment-mention-status">{{ formatStatus(item.status) }}</span>
                <span v-if="item.latest_version_label" class="comment-mention-version">{{ formatVersionLabel({ label: item.latest_version_label }) }}</span>
              </button>
              <button
                v-if="group.has_more"
                type="button"
                class="comment-mention-more"
                @mousedown.prevent
                @click="$emit('show-more', group.type)"
              >Show more {{ group.label.toLowerCase() }}</button>
            </div>

            <button
              :id="optionId(searchBrowseIndex)"
              type="button"
              class="comment-mention-row comment-mention-browse-row"
              :class="{ 'is-active': activeIndex === searchBrowseIndex }"
              role="option"
              :aria-selected="activeIndex === searchBrowseIndex"
              @mouseenter="$emit('set-active', searchBrowseIndex)"
              @mousedown.prevent
              @click="$emit('browse')"
            >
              <span class="comment-mention-icon is-browse"><svg class="icon"><use href="#icon-folder"/></svg></span>
              <span class="comment-mention-row-copy">
                <span class="comment-mention-label">Browse project files…</span>
                <span class="comment-mention-sublabel">Folders, workspaces, trackers, and pages</span>
              </span>
              <svg class="icon comment-mention-chevron"><use href="#icon-chevron-right"/></svg>
            </button>

            <div v-if="!groups.length && !loading" class="comment-mention-empty">
              <svg class="icon"><use href="#icon-search"/></svg>
              <span>No matching project items</span>
            </div>
          </template>

          <template v-else>
            <button
              v-for="(item, index) in browseRows"
              :id="optionId(index)"
              :key="browseItemKey(item)"
              type="button"
              class="comment-mention-row"
              :class="{ 'is-active': activeIndex === index, 'is-disabled': item.disabled, 'is-folder-mention': item.action === 'mention-folder' }"
              :disabled="item.disabled"
              role="option"
              :aria-selected="activeIndex === index"
              :aria-disabled="item.disabled || undefined"
              @mouseenter="!item.disabled && $emit('set-active', index)"
              @mousedown.prevent
              @click="!item.disabled && choose(item)"
            >
              <span class="comment-mention-icon" :class="`is-${item.kind || 'file'}`">
                <svg class="icon"><use :href="itemIcon(item)"/></svg>
              </span>
              <span class="comment-mention-row-copy">
                <span class="comment-mention-label">{{ item.action === 'mention-folder' ? `Mention “${item.label}”` : item.label }}</span>
                <span class="comment-mention-sublabel">{{ item.disabled_hint || item.sublabel }}</span>
              </span>
              <span v-if="item.action === 'mention-folder'" class="comment-mention-scope">Folder</span>
              <svg v-if="item.action === 'folder'" class="icon comment-mention-chevron"><use href="#icon-chevron-right"/></svg>
            </button>
            <div v-if="!browseRows.length && !loading" class="comment-mention-empty">
              <svg class="icon"><use href="#icon-folder"/></svg>
              <span>{{ query ? 'No items match here' : 'This folder is empty' }}</span>
            </div>
          </template>

          <p v-if="error" class="comment-mention-error">{{ error }}</p>
        </div>

        <footer class="comment-mention-footer">
          <span class="comment-mention-desktop-hint"><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span class="comment-mention-desktop-hint"><kbd>↵</kbd> choose</span>
          <span v-if="mode === 'browse'" class="comment-mention-desktop-hint"><kbd>←</kbd> back</span>
          <span class="comment-mention-mobile-hint">{{ mode === 'browse' ? 'Tap to open or mention' : 'Tap an item to mention it' }}</span>
          <span class="comment-mention-footer-spacer"></span>
          <span class="comment-mention-desktop-hint"><kbd>esc</kbd> close</span>
        </footer>
      </section>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatVersionLabel } from '../../utils/versionLabels'

const props = defineProps({
  open: { type: Boolean, default: false },
  anchor: { type: Object, default: null },
  mode: { type: String, default: 'search' },
  query: { type: String, default: '' },
  groups: { type: Array, default: () => [] },
  browsePath: { type: String, default: '' },
  browseRows: { type: Array, default: () => [] },
  browseBreadcrumbs: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  activeIndex: { type: Number, default: 0 },
  listboxId: { type: String, default: 'comment-mention-listbox' },
})

const emit = defineEmits(['choose', 'browse', 'back', 'show-more', 'set-active'])
const popoverRef = ref(null)
const mobileTray = ref(false)
const positionStyle = ref({ left: '12px', top: '12px', width: '360px', visibility: 'hidden' })

const MOBILE_BREAKPOINT = 640
const MOBILE_GUTTER = 10
const MOBILE_MIN_TRAY_HEIGHT = 160
const MOBILE_MAX_TRAY_HEIGHT = 390
const VIEWPORT_SETTLE_DELAY = 80

const flattenedSearchItems = computed(() => props.groups.flatMap(group => group.items || []))
const searchBrowseIndex = computed(() => flattenedSearchItems.value.length)
const browseTitle = computed(() => {
  const lastCrumb = props.browseBreadcrumbs.at?.(-1)
  return lastCrumb?.name || lastCrumb?.label || props.browsePath.split('/').filter(Boolean).at(-1) || 'Project files'
})

function optionId(index) {
  return `comment-mention-option-${index}`
}

function searchItemIndex(item) {
  return flattenedSearchItems.value.indexOf(item)
}

function browseItemKey(item) {
  return [item.action, item.target_type, item.target_id, item.path, item.label].filter(Boolean).join(':')
}

function itemIcon(item) {
  if (item.kind === 'workspace') return '#icon-user'
  if (item.action === 'folder' || item.kind === 'folder') return '#icon-folder'
  if (item.target_type === 'shot' || item.kind === 'shot') return '#icon-video'
  if (item.target_type === 'tracker' || item.kind === 'tracker') return '#icon-list'
  if (item.target_type === 'page' || item.kind === 'page') return '#icon-layout'
  if (item.kind === 'image') return '#icon-image'
  if (item.kind === 'video') return '#icon-video'
  if (item.kind === 'audio') return '#icon-mic'
  if (item.kind === 'pdf') return '#icon-pdf'
  return '#icon-file'
}

function formatStatus(value) {
  return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

function choose(item) {
  emit('choose', item)
}

function finiteViewportValue(value, fallback) {
  return Number.isFinite(value) ? value : fallback
}

function positiveViewportValue(value, fallback) {
  return Number.isFinite(value) && value > 0 ? value : fallback
}

function getViewportBounds() {
  const viewport = window.visualViewport
  const left = finiteViewportValue(viewport?.offsetLeft, 0)
  const top = finiteViewportValue(viewport?.offsetTop, 0)
  const width = positiveViewportValue(viewport?.width, window.innerWidth)
  const height = positiveViewportValue(viewport?.height, window.innerHeight)
  return { left, top, right: left + width, bottom: top + height, width, height }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function updateMobilePosition(anchorRect, popover, viewport) {
  const gutter = MOBILE_GUTTER
  const gap = 8
  const visibleTop = viewport.top + gutter
  const visibleBottom = viewport.bottom - gutter
  const maximumHeight = Math.max(0, viewport.height - gutter * 2)
  const contentHeight = Math.max(popover.offsetHeight, popover.scrollHeight, MOBILE_MIN_TRAY_HEIGHT)
  const preferredHeight = Math.min(contentHeight, MOBILE_MAX_TRAY_HEIGHT, maximumHeight)
  const spaceAbove = Math.max(0, anchorRect.top - gap - visibleTop)
  const spaceBelow = Math.max(0, visibleBottom - anchorRect.bottom - gap)
  const anchorIsVisible = anchorRect.bottom > visibleTop && anchorRect.top < visibleBottom

  let trayHeight = preferredHeight
  let top
  if (anchorIsVisible) {
    const placeAbove = spaceAbove >= Math.min(preferredHeight, MOBILE_MIN_TRAY_HEIGHT)
      || spaceAbove >= spaceBelow
    const availableSpace = placeAbove ? spaceAbove : spaceBelow
    trayHeight = Math.min(preferredHeight, availableSpace || maximumHeight)
    top = placeAbove
      ? anchorRect.top - gap - trayHeight
      : anchorRect.bottom + gap
  } else {
    // During the iOS keyboard animation the anchor can briefly report a rect
    // outside the visual viewport. Keep the tray visible until it settles.
    top = anchorRect.top >= visibleBottom
      ? visibleBottom - trayHeight
      : visibleTop
  }

  trayHeight = Math.max(0, Math.min(trayHeight, maximumHeight))
  top = clamp(top, visibleTop, visibleBottom - trayHeight)
  const safeLeft = 'max(10px, env(safe-area-inset-left, 0px))'
  const safeRight = 'max(10px, env(safe-area-inset-right, 0px))'

  mobileTray.value = true
  positionStyle.value = {
    left: `calc(${viewport.left}px + ${safeLeft})`,
    top: `${top}px`,
    width: `calc(${viewport.width}px - ${safeLeft} - ${safeRight})`,
    maxHeight: `${trayHeight}px`,
    visibility: 'visible',
  }
}

function updatePosition() {
  const anchor = props.anchor
  const popover = popoverRef.value
  if (!anchor?.getBoundingClientRect || !popover) return
  const gutter = 12
  const gap = 8
  const viewport = getViewportBounds()
  const anchorRect = anchor.getBoundingClientRect()
  if (Math.min(window.innerWidth, viewport.width) <= MOBILE_BREAKPOINT) {
    updateMobilePosition(anchorRect, popover, viewport)
    return
  }

  mobileTray.value = false
  const width = Math.min(390, Math.max(280, anchorRect.width), viewport.width - gutter * 2)
  const measuredHeight = Math.min(popover.offsetHeight || 420, viewport.height - gutter * 2)
  const visibleTop = viewport.top + gutter
  const visibleBottom = viewport.bottom - gutter
  const spaceAbove = anchorRect.top - visibleTop - gap
  const placeAbove = spaceAbove >= Math.min(measuredHeight, 260)
  const top = placeAbove
    ? Math.max(visibleTop, anchorRect.top - measuredHeight - gap)
    : Math.min(visibleBottom - measuredHeight, anchorRect.bottom + gap)
  const left = Math.min(
    viewport.right - width - gutter,
    Math.max(viewport.left + gutter, anchorRect.left + anchorRect.width - width),
  )
  positionStyle.value = {
    left: `${left}px`,
    top: `${Math.max(visibleTop, top)}px`,
    width: `${width}px`,
    maxHeight: `${Math.max(180, viewport.height - gutter * 2)}px`,
    visibility: 'visible',
  }
}

let positionFrame = 0
let viewportSettleTimer = 0
let positioningActive = false
function schedulePosition() {
  nextTick(() => {
    if (!positioningActive || typeof window === 'undefined') return
    window.cancelAnimationFrame(positionFrame)
    positionFrame = window.requestAnimationFrame(updatePosition)
  })
}

function scheduleViewportPosition() {
  schedulePosition()
  window.clearTimeout(viewportSettleTimer)
  viewportSettleTimer = window.setTimeout(schedulePosition, VIEWPORT_SETTLE_DELAY)
}

watch(
  () => [props.open, props.anchor, props.mode, props.query, props.groups, props.browseRows],
  schedulePosition,
  { deep: true },
)

onMounted(() => {
  positioningActive = true
  window.addEventListener('resize', schedulePosition)
  window.addEventListener('scroll', schedulePosition, true)
  window.visualViewport?.addEventListener('resize', scheduleViewportPosition)
  window.visualViewport?.addEventListener('scroll', scheduleViewportPosition)
  scheduleViewportPosition()
})
onBeforeUnmount(() => {
  positioningActive = false
  window.cancelAnimationFrame(positionFrame)
  window.clearTimeout(viewportSettleTimer)
  window.removeEventListener('resize', schedulePosition)
  window.removeEventListener('scroll', schedulePosition, true)
  window.visualViewport?.removeEventListener('resize', scheduleViewportPosition)
  window.visualViewport?.removeEventListener('scroll', scheduleViewportPosition)
})
</script>

<style scoped>
.comment-mention-popover {
  position: fixed;
  z-index: var(--v-z-dropdown);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--v-menu-border);
  border-radius: var(--v-radius-lg);
  background: var(--v-menu-bg);
  box-shadow: var(--v-menu-shadow);
  color: var(--v-text);
}

.comment-mention-header {
  min-height: 54px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: color-mix(in srgb, var(--v-surface-inline) 72%, transparent);
}

.comment-mention-at,
.comment-mention-back {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  color: var(--v-accent);
}

.comment-mention-at { font: 700 var(--v-text-lg)/1 var(--v-font); }
.comment-mention-back { padding: 0; cursor: pointer; }
.comment-mention-back:hover { background: var(--v-bg-hover); color: var(--v-text); }
.comment-mention-back .icon { width: 13px; height: 13px; }

.comment-mention-heading {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comment-mention-heading strong {
  overflow: hidden;
  font-size: var(--v-text-sm);
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comment-mention-heading span,
.comment-mention-eyebrow {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comment-mention-spinner {
  width: 14px;
  height: 14px;
  margin-left: auto;
  color: var(--v-text-muted);
  animation: comment-mention-spin 0.8s linear infinite;
}

.comment-mention-scroll {
  flex: 1 1 auto;
  min-height: 74px;
  max-height: min(420px, calc(100vh - 170px));
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 5px;
}

.comment-mention-group + .comment-mention-group { margin-top: 4px; }

.comment-mention-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 8px 4px;
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.comment-mention-row {
  width: 100%;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--v-radius-md);
  background: transparent;
  color: var(--v-text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.comment-mention-row.is-active {
  background: var(--v-accent-subtle);
  color: var(--v-text);
}

.comment-mention-row.is-disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.comment-mention-row.is-folder-mention {
  min-height: 52px;
  margin-bottom: 4px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 24%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-accent-subtle) 68%, transparent);
}

.comment-mention-row.is-folder-mention.is-active {
  border-color: color-mix(in srgb, var(--v-accent) 52%, var(--v-control-border));
  background: var(--v-accent-subtle);
}

.comment-mention-row.is-folder-mention .comment-mention-icon {
  border-color: color-mix(in srgb, var(--v-accent) 26%, transparent);
  background: color-mix(in srgb, var(--v-accent-subtle) 86%, var(--v-surface-inline));
  color: var(--v-accent);
}

.comment-mention-icon {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 72%, transparent);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
}

.comment-mention-icon.is-shot,
.comment-mention-icon.is-video,
.comment-mention-icon.is-image,
.comment-mention-icon.is-browse,
.comment-mention-icon.is-workspace { color: var(--v-accent); }
.comment-mention-icon .icon { width: 14px; height: 14px; }

.comment-mention-row-copy {
  min-width: 0;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
}

.comment-mention-label,
.comment-mention-sublabel {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comment-mention-label { font-size: var(--v-text-sm); font-weight: 620; }
.comment-mention-sublabel { color: var(--v-text-muted); font-size: var(--v-text-2xs); }

.comment-mention-status,
.comment-mention-version {
  flex: 0 0 auto;
  padding: 3px 5px;
  border-radius: var(--v-radius-full);
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 650;
  white-space: nowrap;
}

.comment-mention-version { color: var(--v-accent); }
.comment-mention-chevron { width: 12px; height: 12px; flex: 0 0 auto; color: var(--v-text-muted); }

.comment-mention-scope {
  flex: 0 0 auto;
  padding: 3px 6px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 22%, transparent);
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent-subtle) 74%, transparent);
  color: var(--v-accent);
  font-size: var(--v-text-3xs);
  font-weight: 680;
}

.comment-mention-browse-row {
  margin-top: 5px;
  border-top: 1px solid var(--v-divider-subtle);
  border-radius: 0 0 var(--v-radius-md) var(--v-radius-md);
}

.comment-mention-more {
  width: 100%;
  padding: 5px 8px 7px 47px;
  border: 0;
  background: transparent;
  color: var(--v-accent);
  font: 600 var(--v-text-2xs)/1.3 var(--v-font);
  text-align: left;
  cursor: pointer;
}

.comment-mention-empty {
  min-height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 7px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}
.comment-mention-empty .icon { width: 20px; height: 20px; opacity: 0.66; }

.comment-mention-error {
  margin: 5px;
  padding: 7px 8px;
  border-radius: var(--v-radius-sm);
  background: var(--v-warning-bg);
  color: var(--v-warning);
  font-size: var(--v-text-2xs);
}

.comment-mention-footer {
  min-height: 31px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 9px;
  border-top: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
}

.comment-mention-footer kbd {
  min-width: 17px;
  height: 17px;
  display: inline-grid;
  place-items: center;
  margin-right: 2px;
  padding: 0 3px;
  border: 1px solid var(--v-control-border);
  border-radius: 4px;
  background: var(--v-surface-inset);
  color: var(--v-text-secondary);
  font: inherit;
}

.comment-mention-footer-spacer { flex: 1; }
.comment-mention-mobile-hint { display: none; }

.comment-mention-pop-enter-active,
.comment-mention-pop-leave-active { transition: opacity var(--v-transition-fast), transform var(--v-transition-fast); }
.comment-mention-pop-enter-from,
.comment-mention-pop-leave-to { opacity: 0; transform: translateY(4px) scale(0.985); }

@keyframes comment-mention-spin { to { transform: rotate(360deg); } }

.comment-mention-popover.is-mobile-tray {
  border-color: var(--v-surface-border-strong);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised), var(--v-menu-shadow);
}

.comment-mention-popover.is-mobile-tray .comment-mention-header,
.comment-mention-popover.is-mobile-tray .comment-mention-footer {
  flex: 0 0 auto;
}

.comment-mention-popover.is-mobile-tray .comment-mention-scroll {
  min-height: 0;
  max-height: none;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
}

.comment-mention-popover.is-mobile-tray .comment-mention-row {
  min-height: 54px;
  padding-block: 8px;
}

.comment-mention-popover.is-mobile-tray .comment-mention-desktop-hint { display: none; }
.comment-mention-popover.is-mobile-tray .comment-mention-mobile-hint { display: inline; }

@media (prefers-reduced-motion: reduce) {
  .comment-mention-pop-enter-active,
  .comment-mention-pop-leave-active { transition: none; }
}
</style>
