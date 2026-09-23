<template>
  <aside
    v-if="context"
    ref="navigatorElement"
    class="app-navigator"
    :class="[`is-${variant}`, { 'is-collapsed': collapsed, 'is-resizing': resizing }]"
    :style="navigatorStyle"
    aria-label="Context navigation"
    :aria-hidden="collapsed ? 'true' : undefined"
    :inert="collapsed ? '' : undefined"
  >
    <div class="navigator-inner">
      <header class="navigator-head">
        <button
          class="navigator-scope"
          type="button"
          :aria-label="`Open ${context.title}`"
          @click="activate(context.scope.run)"
        >
          <span class="navigator-scope-mark">
            <VMediaThumbnail v-if="showThumb" :src="context.thumbnail" class="navigator-scope-thumbnail" />
            <svg v-else class="icon" aria-hidden="true"><use :href="context.icon"/></svg>
          </span>
          <span class="navigator-scope-copy">
            <span class="navigator-eyebrow v-eyebrow">{{ context.eyebrow }}</span>
            <span class="navigator-title v-truncate" :title="context.title">{{ context.title }}</span>
          </span>
        </button>
      </header>

      <div class="navigator-body">
        <button v-if="context.back" class="navigator-back" type="button" @click="activate(context.back.run)">
          <svg class="icon" aria-hidden="true"><use href="#icon-back"/></svg>
          <span>{{ context.back.label }}</span>
        </button>

        <section
          v-for="group in sections"
          :key="group.key"
          class="navigator-section"
          :class="[
            `is-tone-${group.tone}`,
            group.statusVariant ? `is-status-${group.statusVariant}` : '',
            { 'is-open': groupIsOpen(group) },
          ]"
        >
          <button
            class="navigator-group-head"
            type="button"
            :aria-expanded="groupIsOpen(group) ? 'true' : 'false'"
            @click="toggleGroup(group.key)"
          >
            <span class="navigator-group-label">
              <svg v-if="group.icon" class="icon navigator-group-icon" aria-hidden="true"><use :href="group.icon"/></svg>
              <span v-else-if="group.statusVariant" class="navigator-group-dot" aria-hidden="true"></span>
              <span class="v-truncate">{{ group.label }}</span>
              <span v-if="group.count" class="navigator-group-count">{{ group.count }}</span>
            </span>
            <svg class="icon navigator-group-chevron" aria-hidden="true"><use href="#icon-chevron-right"/></svg>
          </button>

          <div class="navigator-group-body" :inert="groupIsOpen(group) ? undefined : ''">
            <div class="navigator-group-body-inner">
              <AppNavigatorItem
                v-for="item in visibleItems(group)"
                :key="item.key"
                :item="item"
                :show-thumbnails="navigatorThumbnails && treeIsVisible && groupIsOpen(group)"
                @select="activate"
              />

              <button
                v-if="hiddenCount(group)"
                class="navigator-more"
                type="button"
                @click="revealAll(group.key)"
              >
                <svg class="icon" aria-hidden="true"><use href="#icon-chevron-down"/></svg>
                <span>Show {{ hiddenCount(group) }} more</span>
              </button>

              <AppNavigatorTree
                v-if="group.tree"
                :key="context.key"
                :root-label="group.tree.rootLabel"
                :root-path="group.tree.rootPath"
                :active-path="group.tree.activePath"
                :load-items="group.tree.loadItems"
                :empty-label="group.tree.emptyLabel"
                :drag-scope="variant === 'rail' ? group.tree.dragScope : null"
                :watch-scope="group.tree.watchScope"
                :active="treeIsVisible && groupIsOpen(group)"
                :selection-mode="variant === 'rail'"
                :thumbnail-for="navigatorThumbnails ? navigatorFileThumbnail : null"
                @open-folder="(path) => activate(() => group.tree.openFolder(path))"
                @open-file="(item) => activate(() => group.tree.openFile(item))"
              />
            </div>
          </div>
        </section>

        <p v-if="!sections.length" class="navigator-empty">{{ context.emptyLabel || 'Nothing here yet' }}</p>
      </div>
      <footer class="navigator-footer">
        <div class="navigator-view-toggle" role="group" aria-label="Sidebar view">
          <button type="button" :aria-pressed="!navigatorThumbnails" @click="showThumbnails(false)">
            <svg class="icon" aria-hidden="true"><use href="#icon-list" /></svg>
            <span>List</span>
          </button>
          <button type="button" :aria-pressed="navigatorThumbnails" @click="showThumbnails(true)">
            <svg class="icon" aria-hidden="true"><use href="#icon-image" /></svg>
            <span>Previews</span>
          </button>
        </div>
      </footer>
    </div>

    <div
      v-if="variant === 'rail' && !collapsed"
      ref="resizeHandle"
      class="navigator-resize-handle"
      role="separator"
      aria-label="Resize file navigation"
      aria-orientation="vertical"
      :aria-valuemin="NAVIGATOR_MIN_WIDTH"
      :aria-valuemax="resizeMaximum"
      :aria-valuenow="navigatorWidth"
      title="Drag to resize. Double-click to reset."
      tabindex="0"
      @pointerdown="startResize"
      @pointermove="moveResize"
      @pointerup="finishResize"
      @pointercancel="finishResize"
      @lostpointercapture="finishResize"
      @dblclick.stop.prevent="resetWidth"
      @keydown="handleResizeKeydown"
    ></div>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import AppNavigatorItem from './AppNavigatorItem.vue'
import AppNavigatorTree from './AppNavigatorTree.vue'
import VMediaThumbnail from '../media/VMediaThumbnail.vue'
import { useAppChromeStore } from '../../ownership/appChrome'
import {
  NAVIGATOR_DEFAULT_WIDTH,
  NAVIGATOR_MAX_WIDTH,
  NAVIGATOR_MIN_WIDTH,
  clampNavigatorWidth,
  useContextNavigator,
} from '../../composables/useContextNavigator'

const GROUP_LIMIT = 8

const props = defineProps({
  variant: {
    type: String,
    default: 'rail',
    validator: (value) => ['rail', 'drawer'].includes(value),
  },
  collapsed: { type: Boolean, default: false },
})

const emit = defineEmits(['navigate'])

const {
  navigatorThumbnails,
  navigatorFileThumbnail,
  toggleNavigatorThumbnails,
  navigatorContext: context,
  navigatorWidth,
  setNavigatorWidth,
  resetNavigatorWidth,
  isGroupOpen,
  toggleGroup,
} = useContextNavigator()
const { isMobile, mobileNavOpen } = useAppChromeStore()

const treeIsVisible = computed(() => !props.collapsed && (
  props.variant === 'drawer' ? isMobile.value && mobileNavOpen.value : !isMobile.value
))

const expandedGroups = reactive(new Set())
const navigatorElement = ref(null)
const resizeHandle = ref(null)
const resizing = ref(false)
const resizeMaximum = ref(availableResizeMaximum())
let resizeStartX = 0
let resizeStartWidth = NAVIGATOR_DEFAULT_WIDTH
let pendingResizeWidth = null

const navigatorStyle = computed(() => (
  props.variant === 'rail'
    ? { '--v-navigator-width': `clamp(${NAVIGATOR_MIN_WIDTH}px, ${navigatorWidth.value}px, calc(100vw - 480px))` }
    : undefined
))

const sections = computed(() => {
  if (!context.value) return []
  const groups = context.value.groups.map((group) => ({ ...group, count: group.items.length }))
  if (context.value.tree) {
    groups.push({
      key: 'tree',
      label: context.value.tree.label,
      icon: context.value.tree.icon || '#icon-folder',
      tone: 'default',
      items: [],
      count: 0,
      tree: context.value.tree,
    })
  }
  return groups
})

const showThumb = computed(() => Boolean(context.value?.thumbnail))

function visibleItems(group) {
  if (expandedGroups.has(group.key)) return group.items
  return group.items.slice(0, GROUP_LIMIT)
}

function groupIsOpen(group) {
  return isGroupOpen(group.key, group.defaultOpen !== false)
}

function hiddenCount(group) {
  return group.items.length - visibleItems(group).length
}

function revealAll(key) {
  expandedGroups.add(key)
}

function showThumbnails(value) {
  if (navigatorThumbnails.value !== value) toggleNavigatorThumbnails()
}

function activate(run) {
  run?.()
  emit('navigate')
}

function availableResizeMaximum() {
  if (typeof window === 'undefined') return NAVIGATOR_MAX_WIDTH
  const mainWorkspaceMinimum = 420
  const primarySidebarWidth = 60
  return Math.max(
    NAVIGATOR_MIN_WIDTH,
    Math.min(NAVIGATOR_MAX_WIDTH, window.innerWidth - primarySidebarWidth - mainWorkspaceMinimum),
  )
}

function boundedWidth(value) {
  resizeMaximum.value = availableResizeMaximum()
  return Math.min(resizeMaximum.value, clampNavigatorWidth(value))
}

function applyLiveWidth(value) {
  const width = boundedWidth(value)
  pendingResizeWidth = width
  navigatorElement.value?.style.setProperty('--v-navigator-width', `${width}px`)
  resizeHandle.value?.setAttribute('aria-valuenow', String(width))
  return width
}

function startResize(event) {
  if (event.button !== 0) return
  event.preventDefault()
  resizeStartX = event.clientX
  resizeStartWidth = navigatorElement.value?.getBoundingClientRect().width || navigatorWidth.value
  pendingResizeWidth = boundedWidth(resizeStartWidth)
  resizing.value = true
  document.body.classList.add('is-resizing-navigator')
  try { event.currentTarget?.setPointerCapture?.(event.pointerId) } catch { /* Pointer capture is best effort. */ }
}

function moveResize(event) {
  if (!resizing.value) return
  applyLiveWidth(resizeStartWidth + event.clientX - resizeStartX)
}

function finishResize(event) {
  if (!resizing.value) return
  try { event?.currentTarget?.releasePointerCapture?.(event.pointerId) } catch { /* Capture may already be gone. */ }
  resizing.value = false
  document.body.classList.remove('is-resizing-navigator')
  if (pendingResizeWidth !== null) setNavigatorWidth(pendingResizeWidth)
  pendingResizeWidth = null
}

function resetWidth() {
  finishResize()
  resetNavigatorWidth()
  navigatorElement.value?.style.setProperty('--v-navigator-width', `${NAVIGATOR_DEFAULT_WIDTH}px`)
}

function handleResizeKeydown(event) {
  const direction = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
  let nextWidth = null
  if (direction) nextWidth = navigatorWidth.value + direction * (event.shiftKey ? 24 : 12)
  else if (event.key === 'Home') nextWidth = NAVIGATOR_MIN_WIDTH
  else if (event.key === 'End') nextWidth = availableResizeMaximum()
  if (nextWidth === null) return
  event.preventDefault()
  setNavigatorWidth(applyLiveWidth(nextWidth))
  pendingResizeWidth = null
}

onBeforeUnmount(() => {
  if (resizing.value) finishResize()
  document.body.classList.remove('is-resizing-navigator')
})
</script>

<style scoped>
.app-navigator {
  --navigator-row-height: 32px;
  --navigator-group-height: 30px;
  --navigator-disclosure-width: 24px;
  --navigator-row-font-size: var(--v-text-base);
  --navigator-group-font-size: var(--v-text-sm);
  position: relative;
  width: var(--v-navigator-width);
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--v-divider);
  background: color-mix(in srgb, var(--v-surface-panel) 42%, var(--v-bg-base));
  transition:
    width var(--v-duration-normal) var(--v-ease-emphasized),
    opacity var(--v-duration-fast) linear;
}

.app-navigator.is-resizing {
  transition: opacity var(--v-duration-fast) linear;
  user-select: none;
}

.app-navigator.is-collapsed {
  width: 0;
  border-right-width: 0;
  opacity: 0;
}

.navigator-inner {
  display: flex;
  flex-direction: column;
  width: var(--v-navigator-width);
  height: 100%;
  min-height: 0;
}

.navigator-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  width: 8px;
  touch-action: none;
  cursor: col-resize;
}

.navigator-resize-handle::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 2px;
  background: var(--v-accent);
  opacity: 0;
  transform: scaleX(0.5);
  transform-origin: right center;
  transition:
    opacity var(--v-duration-fast) linear,
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.navigator-resize-handle:hover::after,
.navigator-resize-handle:focus-visible::after,
.app-navigator.is-resizing .navigator-resize-handle::after {
  opacity: 0.72;
  transform: scaleX(1);
}

.navigator-resize-handle:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

:global(body.is-resizing-navigator),
:global(body.is-resizing-navigator *) {
  cursor: col-resize !important;
}

.navigator-head {
  display: flex;
  align-items: center;
  height: var(--v-shell-header-height);
  padding: 0 var(--v-space-2);
  flex-shrink: 0;
  border-bottom: 1px solid var(--v-divider);
}

.navigator-scope {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 5px 8px 5px 6px;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-scope:hover {
  border-color: color-mix(in srgb, var(--v-surface-border-soft) 72%, transparent);
  background: color-mix(in srgb, var(--v-bg-hover) 78%, transparent);
}

.navigator-scope:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-scope-mark {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  color: var(--v-text-secondary);
}

/* A hairline frame keeps dark and light artwork crisp against the rail. */
.navigator-scope-mark::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-text) 9%, transparent);
  pointer-events: none;
}

.navigator-scope-thumbnail {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.navigator-scope-mark .icon {
  width: 15px;
  height: 15px;
}

.navigator-scope-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.navigator-title {
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 650;
  line-height: 1.2;
}

.navigator-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: var(--v-space-3) var(--v-space-2) var(--v-space-6);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--v-text) 14%, transparent) transparent;
}

.navigator-back {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  width: 100%;
  min-height: 30px;
  margin-bottom: var(--v-space-3);
  padding: 0 var(--v-space-2);
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 500;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-back .icon {
  width: 13px;
  height: 13px;
  transition: transform var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover .icon {
  transform: translateX(-2px);
}

.navigator-back:focus-visible,
.navigator-more:focus-visible,
.navigator-group-head:focus-visible,
.navigator-view-toggle button:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-section {
  --navigator-section-tone: var(--v-text-dim);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.navigator-section + .navigator-section {
  margin-top: var(--v-space-4);
}

.navigator-section.is-tone-accent { --navigator-section-tone: var(--v-accent); }
.navigator-section.is-tone-page { --navigator-section-tone: var(--v-page); }

.navigator-section.is-status-active { --navigator-status-color: var(--v-status-active); }
.navigator-section.is-status-review { --navigator-status-color: var(--v-status-review); }
.navigator-section.is-status-done { --navigator-status-color: var(--v-status-done); }
.navigator-section.is-status-hold { --navigator-status-color: var(--v-status-hold); }
.navigator-section.is-status-draft { --navigator-status-color: color-mix(in srgb, var(--v-text-secondary) 58%, var(--v-bg-base)); }

.navigator-group-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 14px;
  gap: var(--v-space-2);
  align-items: center;
  width: 100%;
  min-width: 0;
  height: var(--navigator-group-height);
  padding: 0 var(--v-space-2);
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-group-head:hover {
  color: var(--v-text-secondary);
  background: color-mix(in srgb, var(--v-bg-hover) 72%, transparent);
}

.navigator-group-label {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v-space-2);
  font-size: var(--navigator-group-font-size);
  font-weight: 600;
  letter-spacing: 0.01em;
  line-height: 1.4;
}

.navigator-group-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: color-mix(in srgb, var(--navigator-section-tone) 76%, var(--v-text-dim));
}

/* Status groups use the same colour language as the project cards. */
.navigator-group-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  margin: 0 3px 0 4px;
  border-radius: var(--v-radius-full);
  background: var(--navigator-status-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--navigator-status-color) 18%, transparent);
}

.navigator-group-count {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  line-height: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.navigator-group-chevron {
  justify-self: center;
  width: 11px;
  height: 11px;
  color: var(--v-text-muted);
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-group-head:hover .navigator-group-chevron {
  color: var(--v-text-secondary);
}

.navigator-section.is-open .navigator-group-chevron {
  transform: rotate(90deg);
}

.navigator-group-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-section.is-open .navigator-group-body {
  grid-template-rows: 1fr;
}

.navigator-group-body-inner {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-height: 0;
  overflow: hidden;
  opacity: 0;
  transform: translateY(-3px);
  transition:
    opacity var(--v-duration-normal) var(--v-ease-soft),
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-section.is-open .navigator-group-body-inner {
  opacity: 1;
  transform: translateY(0);
}

.navigator-more {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  width: 100%;
  min-height: 30px;
  padding: 0 var(--v-space-2);
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-muted);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-more .icon {
  width: 12px;
  height: 12px;
  margin: 0 1px;
}

.navigator-more:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-empty {
  margin: 0;
  padding: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.navigator-footer {
  flex-shrink: 0;
  padding: var(--v-space-2);
  border-top: 1px solid var(--v-divider);
}

.navigator-view-toggle {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.navigator-view-toggle button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  height: 28px;
  padding: 0 var(--v-space-2);
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 500;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft),
    box-shadow var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-view-toggle button:hover {
  color: var(--v-text);
}

.navigator-view-toggle button[aria-pressed="true"] {
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--v-text) 7%, transparent),
    0 1px 2px rgba(0, 0, 0, 0.24);
}

.navigator-view-toggle .icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
}

.app-navigator.is-drawer {
  --navigator-row-height: 44px;
  --navigator-group-height: 40px;
  --navigator-disclosure-width: 34px;
  --navigator-row-font-size: var(--v-text-md);
  --navigator-group-font-size: var(--v-text-base);
  width: 100%;
  border-right: 0;
  background: transparent;
}

.app-navigator.is-drawer .navigator-inner {
  width: 100%;
  height: auto;
}

.app-navigator.is-drawer .navigator-head {
  height: auto;
  padding: 0 0 var(--v-space-2);
  border-bottom: 0;
}

.app-navigator.is-drawer .navigator-body {
  padding: 0;
  overflow: visible;
}

.app-navigator.is-drawer .navigator-scope {
  min-height: 56px;
  padding: 6px 9px;
}

.app-navigator.is-drawer .navigator-back,
.app-navigator.is-drawer .navigator-more {
  min-height: 40px;
  font-size: var(--v-text-base);
}

.app-navigator.is-drawer .navigator-footer {
  margin-top: var(--v-space-4);
  padding: var(--v-space-3) 0 0;
}

.app-navigator.is-drawer .navigator-view-toggle button {
  height: 36px;
}

@media (prefers-reduced-motion: reduce) {
  .app-navigator,
  .navigator-scope,
  .navigator-back .icon,
  .navigator-group-body,
  .navigator-group-body-inner,
  .navigator-group-chevron,
  .navigator-view-toggle button,
  .navigator-resize-handle::after {
    transition: none;
  }

  .navigator-back:hover .icon,
  .navigator-group-body-inner {
    transform: none;
  }
}
</style>
