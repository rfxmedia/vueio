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
          <span class="navigator-scope-mark" :class="{ 'has-thumb': showThumb }">
            <img v-if="showThumb" :src="context.thumbnail" alt="" @error="thumbFailed = true"/>
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
            <span class="navigator-group-mark" aria-hidden="true">
              <svg v-if="group.icon" class="icon navigator-group-icon"><use :href="group.icon"/></svg>
              <span v-else class="navigator-group-dot"></span>
            </span>
            <span class="navigator-group-label v-section-label">{{ group.label }}</span>
            <span v-if="group.count" class="navigator-group-count">{{ group.count }}</span>
            <svg class="icon navigator-group-chevron" aria-hidden="true"><use href="#icon-chevron-right"/></svg>
          </button>

          <div class="navigator-group-body" :inert="groupIsOpen(group) ? undefined : ''">
            <div class="navigator-group-body-inner">
              <AppNavigatorItem
                v-for="item in visibleItems(group)"
                :key="item.key"
                :item="item"
                @select="activate"
              />

              <button
                v-if="hiddenCount(group)"
                class="navigator-more"
                type="button"
                @click="revealAll(group.key)"
              >
                Show {{ hiddenCount(group) }} more
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
                @open-folder="(path) => activate(() => group.tree.openFolder(path))"
                @open-file="(item) => activate(() => group.tree.openFile(item))"
              />
            </div>
          </div>
        </section>

        <p v-if="!sections.length" class="navigator-empty">{{ context.emptyLabel || 'Nothing here yet' }}</p>
      </div>
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
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import AppNavigatorItem from './AppNavigatorItem.vue'
import AppNavigatorTree from './AppNavigatorTree.vue'
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
  navigatorContext: context,
  navigatorWidth,
  setNavigatorWidth,
  resetNavigatorWidth,
  isGroupOpen,
  toggleGroup,
} = useContextNavigator()

const expandedGroups = reactive(new Set())
const thumbFailed = ref(false)
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

const showThumb = computed(() => Boolean(context.value?.thumbnail) && !thumbFailed.value)

watch(() => context.value?.thumbnail, () => { thumbFailed.value = false })

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
  --navigator-row-height: 30px;
  --navigator-group-height: 30px;
  --navigator-disclosure-width: 22px;
  --navigator-row-font-size: var(--v-text-sm);
  position: relative;
  width: var(--v-navigator-width);
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--v-divider);
  background: color-mix(in srgb, var(--v-surface-panel) 42%, var(--v-bg-base));
  box-shadow: inset 1px 0 0 color-mix(in srgb, white 1.5%, transparent);
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
  padding: 0 9px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--v-divider);
  background: color-mix(in srgb, var(--v-shell-topbar-bg) 62%, transparent);
}

.navigator-scope {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  width: 100%;
  min-width: 0;
  min-height: 42px;
  padding: 4px 7px 4px 5px;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    transform var(--v-duration-fast) var(--v-ease-soft),
    border-color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-scope:hover {
  border-color: color-mix(in srgb, var(--v-surface-border-soft) 72%, transparent);
  background: color-mix(in srgb, var(--v-bg-hover) 78%, transparent);
}

.navigator-scope:active {
  transform: scale(0.985);
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
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 70%, transparent);
  background: var(--v-surface-inline);
  color: var(--v-accent);
}

.navigator-scope-mark.has-thumb {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 6%, transparent);
}

.navigator-scope-mark img {
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
  gap: 2px;
  min-width: 0;
}

.navigator-title {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 680;
  line-height: 1.25;
}

.navigator-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  padding: 9px 9px 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.navigator-back {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: var(--navigator-row-height);
  margin-bottom: 7px;
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
  font-weight: 600;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover {
  color: var(--v-text);
  border-color: color-mix(in srgb, var(--v-surface-border-soft) 62%, transparent);
  background: var(--v-bg-hover);
}

.navigator-back:focus-visible,
.navigator-more:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-back .icon {
  width: 12px;
  height: 12px;
  transition: transform var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover .icon {
  transform: translateX(-2px);
}

.navigator-section {
  --navigator-section-tone: var(--v-text-dim);
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.navigator-section + .navigator-section {
  margin-top: 11px;
}

.navigator-section.is-tone-accent {
  --navigator-section-tone: var(--v-accent);
}

.navigator-section.is-tone-page {
  --navigator-section-tone: var(--v-page);
}

.navigator-section.is-status-active { --navigator-section-tone: var(--v-status-active); }
.navigator-section.is-status-review { --navigator-section-tone: var(--v-status-review); }
.navigator-section.is-status-hold { --navigator-section-tone: var(--v-status-hold); }
.navigator-section.is-status-draft { --navigator-section-tone: var(--v-status-draft); }
.navigator-section.is-status-done { --navigator-section-tone: var(--v-status-done); }

.navigator-group-head {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto 14px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  height: var(--navigator-group-height);
  padding: 0 4px 0 2px;
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

.navigator-group-head:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-group-mark {
  display: grid;
  place-items: center;
  width: 18px;
  height: 100%;
  color: color-mix(in srgb, var(--navigator-section-tone) 62%, var(--v-text-dim));
  opacity: 0.74;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    opacity var(--v-duration-fast) linear;
}

.navigator-group-icon {
  width: 14px;
  height: 14px;
}

.navigator-group-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--v-radius-full);
  background: var(--navigator-section-tone);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--navigator-section-tone) 14%, transparent);
}

.navigator-section.is-open .navigator-group-mark,
.navigator-group-head:hover .navigator-group-mark {
  opacity: 1;
  color: var(--navigator-section-tone);
}

.navigator-group-label {
  padding: 0;
  color: inherit;
}

.navigator-group-count {
  color: var(--v-text-dim);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  opacity: 0.58;
}

.navigator-group-chevron {
  width: 11px;
  height: 11px;
  opacity: 0.42;
  transition: transform var(--v-duration-normal) var(--v-ease-emphasized);
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
  margin: 2px 0 0 20px;
  padding: 2px 6px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-xs);
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-more:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-empty {
  margin: 0;
  padding: 0 6px;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.app-navigator.is-drawer {
  --navigator-row-height: 44px;
  --navigator-group-height: 42px;
  --navigator-disclosure-width: 34px;
  --navigator-row-font-size: var(--v-text-base);
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
  padding: 0 0 8px;
  border-bottom: 0;
  background: transparent;
}

.app-navigator.is-drawer .navigator-body {
  padding: 0;
  overflow: visible;
}

.app-navigator.is-drawer .navigator-scope {
  min-height: 56px;
  padding: 6px 9px;
  border-color: var(--v-control-border);
  background: var(--v-surface-raised);
  box-shadow: var(--v-surface-shadow-raised);
}

.app-navigator.is-drawer .navigator-scope:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-raised-strong);
}

.app-navigator.is-drawer .navigator-back {
  font-size: var(--v-text-base);
}

@media (prefers-reduced-motion: reduce) {
  .app-navigator,
  .navigator-scope,
  .navigator-group-body,
  .navigator-group-body-inner,
  .navigator-group-mark,
  .navigator-group-chevron,
  .navigator-back .icon {
    transition: none;
  }

  .navigator-resize-handle::after {
    transition: none;
  }

  .navigator-scope:active,
  .navigator-group-body-inner {
    transform: none;
  }

  .navigator-back:hover .icon {
    transform: none;
  }
}
</style>
