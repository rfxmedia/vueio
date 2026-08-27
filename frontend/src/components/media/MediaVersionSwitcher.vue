<template>
  <div class="media-version-switcher" :class="[`is-${variant}`, { 'is-open': open }]">
    <VMenu
      v-if="!isMobile"
      :open="open"
      align="start"
      :min-width="publicationControlsEnabled ? 570 : 475"
      teleport
      :offset="14"
      panel-role="dialog"
      panel-class="media-version-switcher-menu"
      @update:open="(value) => { if (!value) $emit('close') }"
    >
      <template #trigger="{ triggerProps }">
        <button
          v-bind="triggerProps"
          type="button"
          class="media-version-switcher-trigger"
          :class="[triggerPillClass, { 'is-active': open }]"
          :aria-label="versionSwitcherAriaLabel"
          :title="versionSwitcherTitle"
          @click.stop="$emit('toggle')"
        >
          <span
            v-if="currentShareState"
            class="media-version-switcher-publication-dot"
            :class="`is-${currentShareState}`"
            :title="currentShareStateLabel"
            aria-hidden="true"
          ></span>
          <span class="media-version-switcher-trigger-label">{{ currentVersionLabel }}</span>
          <svg class="icon media-version-switcher-trigger-chevron" :class="{ 'is-open': open }"><use href="#icon-chevron-down" /></svg>
        </button>
      </template>

      <div class="media-version-switcher-panel">
        <div class="media-version-switcher-panel-header">
          <div class="media-version-switcher-panel-title v-section-label">Versions</div>
          <div class="media-version-switcher-panel-actions">
            <button
              v-if="canCompareVersions"
              type="button"
              class="media-version-switcher-panel-action v-btn v-btn-quiet v-btn-sm"
              @click.stop="$emit('compare-versions')"
            >
              <svg class="icon"><use href="#icon-compare" /></svg>
              Compare
            </button>
            <button
              v-if="canShowAddVersionAction"
              type="button"
              class="media-version-switcher-panel-action v-btn v-btn-quiet v-btn-sm"
              @click.stop="$emit('add-version')"
            >
              <svg class="icon"><use href="#icon-plus" /></svg>
              Add version
            </button>
          </div>
        </div>

        <MediaVersionSwitcherList
          :shot-id="shot?.shot_id || ''"
          :versions="versions"
          :latest-version-id="latestVersionId"
          :current-media="currentMedia"
          :can-delete-versions="canDeleteVersions"
          :can-download-versions="canDownloadVersions"
          :publication-controls-enabled="publicationControlsEnabled"
          :update-version-publication="updateVersionPublication"
          :share-mode="shareMode"
          :get-thumbnail-url="getThumbnailUrl"
          :get-media-duration-label="getMediaDurationLabel"
          :format-version-label="formatVersionLabel"
          :format-version-date-short="formatVersionDateShort"
          @select-version="$emit('select-version', $event)"
          @download-version="$emit('download-version', $event)"
          @delete-version="$emit('delete-version', $event)"
        />
      </div>
    </VMenu>

    <button
      v-else
      type="button"
      class="media-version-switcher-trigger"
      :class="[triggerPillClass, { 'is-active': open }]"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-label="versionSwitcherAriaLabel"
      :title="versionSwitcherTitle"
      @click.stop="$emit('toggle')"
    >
      <span
        v-if="currentShareState"
        class="media-version-switcher-publication-dot"
        :class="`is-${currentShareState}`"
        :title="currentShareStateLabel"
        aria-hidden="true"
      ></span>
      <span class="media-version-switcher-trigger-label">{{ currentVersionLabel }}</span>
      <svg class="icon media-version-switcher-trigger-chevron" :class="{ 'is-open': open }"><use href="#icon-chevron-down" /></svg>
    </button>

    <VModal
      :modelValue="isMobile && open"
      class="media-version-switcher-sheet-modal"
      size="lg"
      presentation="sheet"
      @update:modelValue="handleModalVisibility"
    >
      <template #header>
        <VModalHeader @close="$emit('close')">
          <div class="media-version-switcher-sheet-header">
            <div class="v-modal-header-copy">
              <h2 class="v-modal-header-title">Versions</h2>
              <p class="v-modal-header-subtitle">{{ versionCountLabel }}</p>
            </div>
            <button
              v-if="canShowAddVersionAction"
              type="button"
              class="media-version-switcher-panel-action v-btn v-btn-quiet v-btn-sm"
              @click.stop="$emit('add-version')"
            >
              <svg class="icon"><use href="#icon-plus" /></svg>
              Add version
            </button>
          </div>
        </VModalHeader>
      </template>

      <div class="media-version-switcher-sheet-body">
        <MediaVersionSwitcherList
          sheet
          :shot-id="shot?.shot_id || ''"
          :versions="versions"
          :latest-version-id="latestVersionId"
          :current-media="currentMedia"
          :can-delete-versions="canDeleteVersions"
          :can-download-versions="canDownloadVersions"
          :publication-controls-enabled="publicationControlsEnabled"
          :update-version-publication="updateVersionPublication"
          :share-mode="shareMode"
          :get-thumbnail-url="getThumbnailUrl"
          :get-media-duration-label="getMediaDurationLabel"
          :format-version-label="formatVersionLabel"
          :format-version-date-short="formatVersionDateShort"
          @select-version="$emit('select-version', $event)"
          @download-version="$emit('download-version', $event)"
          @delete-version="$emit('delete-version', $event)"
        />
      </div>
    </VModal>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { mediaEntitiesMatch } from '../../lib/mediaEntity'
import { VMenu, VModal, VModalHeader } from '../primitives'
import MediaVersionSwitcherList from './MediaVersionSwitcherList.vue'

const props = defineProps({
  isMobile: { type: Boolean, default: false },
  open: { type: Boolean, default: false },
  variant: { type: String, default: 'control' }, // 'control' | 'overlay'
  shot: { type: Object, default: null },
  versions: { type: Array, default: () => [] },
  currentMedia: { type: Object, default: null },
  currentVersionLabel: { type: String, default: 'Versions' },
  keyboardShortcuts: { type: Boolean, default: false },
  canAddVersions: { type: Boolean, default: false },
  canDeleteVersions: { type: Boolean, default: false },
  canDownloadVersions: { type: Boolean, default: false },
  canCompareVersions: { type: Boolean, default: false },
  publicationControlsEnabled: { type: Boolean, default: false },
  updateVersionPublication: { type: Function, default: null },
  shareMode: { type: Boolean, default: false },
  getThumbnailUrl: { type: Function, required: true },
  getMediaDurationLabel: { type: Function, default: () => '' },
  fetchBatchMediaInfo: { type: Function, default: null },
  formatVersionLabel: { type: Function, required: true },
  formatVersionDateShort: { type: Function, required: true },
})

const emit = defineEmits(['toggle', 'close', 'select-version', 'add-version', 'download-version', 'delete-version', 'compare-versions'])

const triggerPillClass = computed(() => (
  props.variant === 'overlay'
    ? 'v-overlay-pill'
    : 'v-control-pill v-control-pill-compact'
))

const canShowAddVersionAction = computed(() => props.canAddVersions && !props.shareMode)
const versionCountLabel = computed(() => `${props.versions.length} version${props.versions.length === 1 ? '' : 's'}`)
const latestVersionId = computed(() => {
  const latestLabel = String(props.shot?.latest_version_label ?? '').trim()
  const matched = latestLabel
    ? props.versions.find(version => String(version?.label ?? version?.version ?? '').trim() === latestLabel)
    : null
  return matched?.id || props.versions[0]?.id || ''
})
const currentVersion = computed(() => (
  props.versions.find(version => mediaEntitiesMatch(version, props.currentMedia)) || props.currentMedia
))
const currentShareState = computed(() => {
  if (props.shareMode) return ''
  const state = String(currentVersion.value?.share_state || '').trim().toLowerCase()
  if (['pending', 'internal'].includes(state)) return state
  return props.publicationControlsEnabled && state === 'published' ? state : ''
})
const currentShareStateLabel = computed(() => ({
  published: 'Published to shares',
  pending: 'Awaiting publication',
  internal: 'Internal version',
}[currentShareState.value] || ''))
const versionSwitcherAriaLabel = computed(() => {
  const publication = currentShareStateLabel.value ? `. ${currentShareStateLabel.value}` : ''
  return `Switch version. Current ${props.currentVersionLabel}${publication}`
})
const versionSwitcherTitle = computed(() => (
  props.keyboardShortcuts
    ? 'Switch version · ↑ newer · ↓ older · Numpad 8/2'
    : versionSwitcherAriaLabel.value
))

watch(() => props.open, (isOpen) => {
  if (!isOpen || typeof props.fetchBatchMediaInfo !== 'function') return
  const paths = (props.versions || [])
    .map(version => version?.path || version?.file_path)
    .filter(Boolean)
  if (paths.length) props.fetchBatchMediaInfo(paths)
})

function handleModalVisibility(nextValue) {
  if (!nextValue) {
    emit('close')
  }
}
</script>

<style scoped>
.media-version-switcher {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
}

.media-version-switcher-trigger {
  gap: 6px;
  padding: 0 10px;
  justify-content: center;
}

.media-version-switcher-publication-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  background: var(--v-text-muted);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-text-muted) 10%, transparent);
}

.media-version-switcher-publication-dot.is-pending {
  background: var(--v-warning);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-warning) 11%, transparent);
}

.media-version-switcher-publication-dot.is-published {
  background: var(--v-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 11%, transparent);
}

.media-version-switcher-trigger-label {
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
  color: var(--v-text);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.media-version-switcher-trigger-chevron {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
  transition: transform var(--v-transition-fast), color var(--v-transition-fast);
  flex: 0 0 auto;
}

/* Overlay variant: sits on top of media thumbnails (tracker row cards) */
.media-version-switcher.is-overlay .media-version-switcher-trigger {
  gap: var(--v-space-1);
  padding: 0 8px;
  border-color: color-mix(in srgb, var(--v-accent) 58%, var(--v-overlay-pill-border));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 18%, transparent);
}

.media-version-switcher.is-overlay .media-version-switcher-trigger:hover,
.media-version-switcher.is-overlay .media-version-switcher-trigger.is-active {
  border-color: color-mix(in srgb, var(--v-accent) 72%, var(--v-overlay-pill-border));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 28%, transparent);
}

.media-version-switcher.is-overlay .media-version-switcher-trigger-label {
  font-size: var(--v-overlay-pill-font-size);
  font-weight: var(--v-overlay-pill-font-weight);
  letter-spacing: 0.04em;
}

.media-version-switcher.is-overlay .media-version-switcher-trigger-chevron {
  width: 10px;
  height: 10px;
  color: color-mix(in srgb, var(--v-overlay-pill-text) 70%, transparent);
}

.media-version-switcher.is-overlay .media-version-switcher-trigger:hover .media-version-switcher-trigger-chevron,
.media-version-switcher.is-overlay .media-version-switcher-trigger.is-active .media-version-switcher-trigger-chevron {
  color: var(--v-overlay-pill-text);
}

.media-version-switcher-trigger:hover .media-version-switcher-trigger-chevron,
.media-version-switcher-trigger.is-active .media-version-switcher-trigger-chevron {
  color: var(--v-text);
}

.media-version-switcher-trigger-chevron.is-open {
  transform: rotate(180deg);
}

.media-version-switcher-panel {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  padding: var(--v-space-1);
}

.media-version-switcher-panel-header,
.media-version-switcher-sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.media-version-switcher-panel-header {
  padding: 6px 8px 8px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--v-divider-subtle);
}


.media-version-switcher-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.media-version-switcher-panel-action {
  flex: 0 0 auto;
  min-height: 28px;
  padding: 0 10px;
  gap: 6px;
  font-size: var(--v-text-xs);
}

.media-version-switcher-sheet-body {
  padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
}

:deep(.media-version-switcher-menu) {
  z-index: calc(var(--v-z-dropdown) + 20);
  padding: 0;
  overflow: hidden;
  margin-top: 14px;
  max-height: min(560px, calc(100vh - var(--v-shell-header-height) - 28px));
  display: flex;
  flex-direction: column;
  border-radius: var(--v-radius-lg);
}

:deep(.media-version-switcher-sheet-modal .v-modal-body) {
  padding-top: var(--v-space-2);
}

@media (max-width: 768px) {
  .media-version-switcher-sheet-header {
    align-items: flex-start;
  }
}
</style>
