<template>
  <article
    class="tracker-row-card v-card"
    :data-tracker-shot-id="shot.id"
    :data-tracker-shot-code="shot.shot_id || shot.shot_code"
    :class="[
      `status-${shot.status}`,
      {
        'drag-over': dragOverIndex === index,
        'is-reorderable': canReorderShots,
        'has-assignee': showShotAssignees,
        'has-utility': hasUtility,
        'has-open-picker': hasOpenPicker,
        'is-selected': isSelected,
        'selection-enabled': selectionEnabled,
        'is-mobile-card': isMobileCard,
        'is-grid-card': isGridCard,
      },
    ]"
    :draggable="canReorderShots"
    @dragstart="canReorderShots && onDragStart($event, index)"
    @dragover.prevent="canReorderShots && onDragOver($event, index)"
    @dragleave="onDragLeave"
    @drop="canReorderShots && onDrop($event, index)"
    @dragend="onDragEnd"
  >
    <div
      v-if="selectionEnabled"
      class="tracker-row-card__select"
    >
      <button
        class="tracker-row-select-btn"
        type="button"
        :aria-label="isSelected ? `Deselect ${shot.shot_id}` : `Select ${shot.shot_id}`"
        :aria-pressed="isSelected ? 'true' : 'false'"
        @click.stop="toggleShotSelected(shot)"
      >
        <span class="tracker-row-select-box v-checkbox-box" aria-hidden="true">
          <svg v-if="isSelected" class="icon"><use href="#icon-check" /></svg>
        </span>
      </button>
    </div>

    <div class="tracker-row-card__preview">
      <ShotVersionStack
        compact
        :shot="shot"
        :can-add-versions="canAddVersions"
        :can-delete-versions="canDeleteShots"
        :can-download-versions="showShotDownloads"
        :can-compare-versions="canCompareShotVersions(shot)"
        :compare-versions="startTrackerVersionCompare"
        :publication-controls-enabled="publicationControlsEnabled"
        :update-version-publication="updateTrackerVersionPublication"
        :share-mode="shareMode"
        :is-mobile="isMobile"
        :delete-shot-version="deleteShotVersion"
        :download-version="downloadVersion"
        :get-shot-versions="getShotVersions"
        :open-shot-video="openShotVideo"
        :play-shot-version="playShotVersion"
        :open-version-upload="openVersionUpload"
        :get-thumbnail-url="getThumbnailUrl"
        :get-shot-duration-label="getShotDurationLabel"
        :get-media-duration-label="getMediaDurationLabel"
        :fetch-batch-media-info="fetchBatchMediaInfo"
        :format-version-label="formatVersionLabel"
        :format-version-date-short="formatVersionDateShort"
      />
    </div>

    <div class="tracker-row-card__body">
      <header class="trc-head">
        <div class="trc-ident">
          <TrackerRowMeta
            :shot="shot"
            :formatted-updated="formatShotLatestAdded(shot)"
            :can-edit-shot-name="canEditShotName"
            :share-mode="shareMode"
            :save-shot="saveShot"
            :can-reorder-shots="canReorderShots"
          />
        </div>

        <div class="trc-controls" :class="{ 'has-assignee': showShotAssignees }">
          <div class="trc-control-cell is-status">
            <TrackerInlineSelect
              tone="status"
              :label="formatStatus(shot.status)"
              :accent="getTrackerStatusColor(shot.status)"
              :accent-text="getTrackerStatusTextColor(shot.status)"
              :open="showStatusPicker === shot.shot_id"
              :flip-up="dropdownFlipUp"
              @trigger="toggleShotStatusPicker($event, shot.shot_id)"
              @close="showStatusPicker = null"
            >
              <template #leading>
                <span class="status-dot" :class="`dot-${shot.status}`"></span>
              </template>
              <template #menu>
                <div class="tracker-select-list">
                  <button v-for="s in STATUS_ORDER" :key="s" class="status-option tracker-select-option v-dropdown-item" :class="{ active: shot.status === s }" @click="selectStatus(shot, s)">
                    <span class="status-dot" :class="`dot-${s}`"></span>
                    <span class="tracker-select-option-label">{{ formatStatus(s) }}</span>
                    <svg v-if="shot.status === s" class="icon tracker-select-check"><use href="#icon-check" /></svg>
                  </button>
                </div>
              </template>
            </TrackerInlineSelect>
          </div>

          <TrackerTagSelect
            class="trc-control-cell is-category"
            :shot="shot"
            :flip-up="dropdownFlipUp"
          />

          <TrackerAssigneeSelect
            v-if="showShotAssignees"
            class="trc-control-cell is-assignee"
            :shot="shot"
            :flip-up="dropdownFlipUp"
          />
        </div>
      </header>

      <div class="trc-copy">
        <button
          v-if="showBriefPreview !== false"
          class="trc-brief"
          type="button"
          :class="{ 'is-empty': isBriefPreviewEmpty(shot) }"
          :aria-label="`Open brief for ${shot.shot_id || 'shot'}`"
          @click.stop="openBriefVideo(shot)"
        >
          <span class="trc-brief-lead" aria-hidden="true">
            <span class="trc-brief-icon">
              <svg class="icon"><use href="#icon-info" /></svg>
            </span>
          </span>
          <div class="trc-brief-main">
            <span class="trc-section-tag trc-brief-tag">Brief</span>
            <span class="trc-brief-body">{{ briefText }}</span>
          </div>
          <span class="trc-open-hint" aria-hidden="true">
            <svg viewBox="0 0 13 13" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2.5 6.5H10.5M10.5 6.5L7 3M10.5 6.5L7 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
        </button>

        <button
          class="trc-note"
          type="button"
          :class="{ 'is-empty': isLatestPreviewEmpty(shot) }"
          :aria-label="`Open latest notes for ${shot.shot_id || 'shot'}`"
          @click.stop="openShotVideo(shot)"
        >
          <span class="trc-note-lead" aria-hidden="true">
            <span class="trc-note-icon">
              <svg class="icon"><use href="#icon-comment" /></svg>
            </span>
            <span v-if="latestCommentCount > 0" class="trc-note-count">{{ latestCommentCount }}</span>
          </span>
          <div class="trc-note-main">
            <span class="trc-section-tag trc-note-tag">Latest notes</span>
            <span class="trc-note-body">{{ latestNoteText }}</span>
          </div>
          <span class="trc-open-hint" aria-hidden="true">
            <svg viewBox="0 0 13 13" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2.5 6.5H10.5M10.5 6.5L7 3M10.5 6.5L7 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
        </button>
      </div>
    </div>

    <div
      v-if="hasUtility"
      class="tracker-row-card__utility"
      :class="{ 'is-centered': centerUtilityAction }"
    >
      <div
        class="tracker-row-card__utility-actions"
        :class="{ 'is-centered': centerUtilityAction }"
      >
        <button
          v-if="showUtilityDownload"
          class="tracker-utility-btn v-icon-action"
          type="button"
          title="Download latest version"
          @click.stop="downloadShotFile(shot)"
        >
          <svg class="icon"><use href="#icon-download" /></svg>
        </button>
        <button
          v-if="showUtilityArchive"
          class="tracker-utility-btn v-icon-action"
          type="button"
          title="Archive shot"
          @click.stop="archiveShot(shot)"
        >
          <svg class="icon"><use href="#icon-inbox" /></svg>
        </button>
        <button
          v-if="showUtilityRestore"
          class="tracker-utility-btn v-icon-action"
          type="button"
          title="Restore shot"
          @click.stop="restoreShot(shot)"
        >
          <svg class="icon"><use href="#icon-undo" /></svg>
        </button>
        <button
          v-if="showUtilityDelete"
          class="tracker-utility-btn tracker-utility-btn-danger v-icon-action is-danger"
          type="button"
          title="Delete shot"
          @click.stop="deleteShot(shot)"
        >
          <svg class="icon"><use href="#icon-trash" /></svg>
        </button>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { buildVersionCommentBatchTarget } from '../../lib/commentTargets'
import { getTrackerStatusColor, getTrackerStatusTextColor } from '../../lib/trackerCatalogs'
import { useTrackerStore } from '../../ownership/tracker'
import ShotVersionStack from './ShotVersionStack.vue'
import TrackerAssigneeSelect from './TrackerAssigneeSelect.vue'
import TrackerInlineSelect from './TrackerInlineSelect.vue'
import TrackerRowMeta from './TrackerRowMeta.vue'
import TrackerTagSelect from './TrackerTagSelect.vue'

const props = defineProps({
  canReorderShots: Boolean,
  dragOverIndex: {
    type: Number,
    default: null,
  },
  index: {
    type: Number,
    required: true,
  },
  presentation: {
    type: String,
    default: 'list',
  },
  selectionEnabled: Boolean,
  shot: {
    type: Object,
    required: true,
  },
  toggleShotSelected: {
    type: Function,
    required: true,
  },
})

const {
  STATUS_ORDER,
  archiveShot,
  canAddVersions,
  canArchiveShots,
  canDeleteShots,
  canCompareShotVersions,
  canEditShotName,
  commentCounts,
  deleteShot,
  deleteShotVersion,
  downloadShotFile,
  downloadVersion,
  dropdownFlipUp,
  fetchBatchMediaInfo,
  formatShotLatestAdded,
  formatStatus,
  formatVersionDateShort,
  formatVersionLabel,
  getBriefPreviewText,
  getLatestPreviewText,
  getLatestShotFile,
  getMediaDurationLabel,
  getShotDurationLabel,
  getShotVersions,
  getThumbnailUrl,
  isBriefPreviewEmpty,
  isLatestPreviewEmpty,
  isMobile,
  isShotSelected,
  onDragEnd,
  onDragLeave,
  onDragOver,
  onDragStart,
  onDrop,
  openBriefVideo,
  openShotVideo,
  openVersionUpload,
  playShotVersion,
  publicationControlsEnabled,
  restoreShot,
  saveShot,
  selectStatus,
  shareMode,
  showAssigneePicker,
  showBriefPreview,
  showCategoryPicker,
  showShotAssignees,
  showShotDownloads,
  showStatusPicker,
  startTrackerVersionCompare,
  toggleShotStatusPicker,
  updateTrackerVersionPublication,
} = useTrackerStore()

const showUtilityDownload = computed(() => (
  showShotDownloads.value && !!getLatestShotFile(props.shot)
))

const showUtilityDelete = computed(() => canDeleteShots.value && !shareMode.value)

const showUtilityArchive = computed(() => (
  canArchiveShots.value &&
  !shareMode.value &&
  !props.shot?.archived_at &&
  typeof archiveShot === 'function'
))

const showUtilityRestore = computed(() => (
  canArchiveShots.value &&
  !shareMode.value &&
  !!props.shot?.archived_at &&
  typeof restoreShot === 'function'
))

const hasUtility = computed(() => showUtilityDownload.value || showUtilityArchive.value || showUtilityRestore.value || showUtilityDelete.value)

const centerUtilityAction = computed(() => (
  shareMode.value &&
  showUtilityDownload.value &&
  !showUtilityArchive.value &&
  !showUtilityRestore.value &&
  !showUtilityDelete.value
))

const hasOpenPicker = computed(() => (
  showStatusPicker.value === props.shot.shot_id ||
  showCategoryPicker.value === props.shot.shot_id ||
  showAssigneePicker.value === props.shot.shot_id
))

const isSelected = computed(() => (
  typeof isShotSelected === 'function' && isShotSelected(props.shot)
))

const isMobileCard = computed(() => isMobile.value || props.presentation === 'grid')
const isGridCard = computed(() => props.presentation === 'grid')

const LOADING_LABEL = 'Loading comments...'

const briefText = computed(() => {
  const raw = getBriefPreviewText(props.shot)
  if (isBriefPreviewEmpty(props.shot)) {
    if (raw === LOADING_LABEL) return raw
    return 'No brief written yet — leave a comment on V1 to start one'
  }
  return raw
})

const latestNoteText = computed(() => {
  const raw = getLatestPreviewText(props.shot)
  if (isLatestPreviewEmpty(props.shot)) {
    if (raw === LOADING_LABEL) return raw
    return 'No new notes yet'
  }
  return raw
})

const latestCommentCount = computed(() => {
  const versions = getShotVersions(props.shot) || []
  const latestVersion = versions[versions.length - 1]
  const target = buildVersionCommentBatchTarget(latestVersion)
  if (!target?.key) return 0
  return commentCounts.value[target.key] || 0
})
</script>

<style scoped>
/* ─── Card shell ─────────────────────────────────────────── */
.tracker-row-card {
  --tracker-row-thumb-width: calc(192px * 1.728);
  --trc-mobile-brief-height: 48px;
  --trc-mobile-note-height: 54px;
  --trc-mobile-copy-line-height: 16px;
  --tracker-row-status-border: var(--v-surface-border-strong);
  --tracker-row-status-border-hover: color-mix(in srgb, var(--tracker-row-status-surface) 88%, white);
  --tracker-row-status-surface: var(--v-surface-canvas);
  --tracker-row-status-surface-hover: color-mix(in srgb, var(--v-surface-canvas) 86%, var(--v-surface-inline));
  --tracker-row-shadow: 0 1px 0 rgba(255, 255, 255, 0.035) inset, 0 10px 24px rgba(0, 0, 0, 0.08);
  --tracker-row-shadow-hover: 0 1px 0 rgba(255, 255, 255, 0.055) inset, 0 14px 34px rgba(0, 0, 0, 0.26);
  position: relative;
  display: grid;
  grid-template-columns:
    var(--tracker-row-thumb-width)
    minmax(0, 1fr)
    var(--tracker-utility-width, 46px);
  grid-template-areas: 'preview body utility';
  align-items: stretch;
  gap: 0;
  border-radius: var(--v-radius-lg);
  background: var(--tracker-row-status-surface);
  border-color: var(--tracker-row-status-border);
  box-shadow: var(--tracker-row-shadow);
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
  overflow: visible;
}

.tracker-row-card.selection-enabled {
  grid-template-columns:
    var(--tracker-selection-width, 28px)
    var(--tracker-row-thumb-width)
    minmax(0, 1fr)
    var(--tracker-utility-width, 46px);
  grid-template-areas: 'select preview body utility';
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}

.tracker-row-card:hover {
  border-color: var(--tracker-row-status-border-hover);
  background: var(--tracker-row-status-surface-hover);
  box-shadow: var(--tracker-row-shadow-hover);
}

.tracker-row-card.selection-enabled:hover {
  border-color: transparent;
  background: transparent;
}

.tracker-row-card.selection-enabled::after {
  content: '';
  position: absolute;
  z-index: 0;
  inset: 0 0 0 calc(var(--tracker-selection-width, 28px) + var(--tracker-row-thumb-width));
  border: 1px solid var(--tracker-row-status-border);
  border-left: 0;
  border-radius: 0 var(--v-radius-lg) var(--v-radius-lg) 0;
  background: var(--tracker-row-status-surface);
  box-shadow: none;
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
  pointer-events: none;
}

.tracker-row-card.selection-enabled .tracker-row-card__preview {
  --tracker-row-preview-border: var(--tracker-row-status-border);
}

.tracker-row-card.selection-enabled:hover::after {
  border-color: var(--tracker-row-status-border-hover);
  background: var(--tracker-row-status-surface-hover);
  box-shadow: var(--tracker-row-shadow-hover);
}

.tracker-row-card.selection-enabled:hover .tracker-row-card__preview {
  --tracker-row-preview-border: var(--tracker-row-status-border-hover);
}

.tracker-row-card.has-open-picker {
  z-index: calc(var(--v-z-dropdown) + 12);
}

.tracker-row-card:has(.media-version-switcher.is-open) {
  z-index: calc(var(--v-z-dropdown) + 8);
}

.tracker-row-card.drag-over,
.tracker-row-card.is-selected,
.tracker-row-card.is-activity-focus {
  background: color-mix(in srgb, var(--v-accent) 7%, var(--tracker-row-status-surface));
  border-color: color-mix(in srgb, var(--v-accent) 28%, var(--tracker-row-status-border));
}

.tracker-row-card.selection-enabled.drag-over,
.tracker-row-card.selection-enabled.is-selected,
.tracker-row-card.selection-enabled.is-activity-focus {
  background: transparent;
  border-color: transparent;
}

.tracker-row-card.selection-enabled.drag-over::after,
.tracker-row-card.selection-enabled.is-selected::after,
.tracker-row-card.selection-enabled.is-activity-focus::after {
  background: color-mix(in srgb, var(--v-accent) 7%, var(--tracker-row-status-surface));
  border-color: color-mix(in srgb, var(--v-accent) 28%, var(--tracker-row-status-border));
}

.tracker-row-card.selection-enabled.drag-over .tracker-row-card__preview,
.tracker-row-card.selection-enabled.is-selected .tracker-row-card__preview,
.tracker-row-card.selection-enabled.is-activity-focus .tracker-row-card__preview {
  --tracker-row-preview-border: color-mix(in srgb, var(--v-accent) 28%, var(--tracker-row-status-border));
  background: color-mix(in srgb, var(--v-accent) 7%, var(--tracker-row-status-surface));
}

.tracker-row-card.is-selected::before,
.tracker-row-card.is-activity-focus::before {
  content: '';
  position: absolute;
  inset: 10px auto 10px 0;
  width: 2px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
}

.tracker-row-card.selection-enabled.is-selected::before {
  inset: 10px auto 10px var(--tracker-selection-width, 28px);
  z-index: 1;
}

/* ─── Select column ──────────────────────────────────────── */
.tracker-row-card__select {
  grid-area: select;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0;
}

.tracker-row-select-btn {
  position: relative;
  z-index: 3;
  width: 22px;
  height: 22px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text);
  opacity: 1;
  cursor: pointer;
  box-shadow: none;
  /* Lines the 15px box up with the page gutter, not the 22px hit target. */
  transform: translateX(var(--tracker-checkbox-nudge, -4.5px));
  transition: opacity var(--v-transition-fast), background var(--v-transition-fast);
}

@media (hover: hover) and (pointer: fine) {
  .tracker-row-card:not(.is-mobile-card):not(.is-selected) .tracker-row-select-btn {
    opacity: 0;
  }

  .tracker-row-card:not(.is-mobile-card):hover .tracker-row-select-btn,
  .tracker-row-card:not(.is-mobile-card):focus-within .tracker-row-select-btn {
    opacity: 1;
  }
}

.tracker-row-select-btn:hover {
  background: var(--v-control-bg-hover);
}

.tracker-row-select-btn:focus-visible {
  outline: none;
  opacity: 1;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-row-select-box {
  width: 15px;
  height: 15px;
  margin-top: 0;
  flex: 0 0 auto;
  border-radius: var(--v-radius-sm);
  border-color: color-mix(in srgb, var(--v-control-border) 86%, white);
  background: var(--v-surface-inset);
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
}

.tracker-row-card.is-selected .tracker-row-select-box {
  border-color: var(--v-accent);
  background: var(--v-accent);
  color: var(--v-bg-black);
}

.tracker-row-select-box .icon {
  width: 10px;
  height: 10px;
}

/* ─── Cell base ──────────────────────────────────────────── */
.tracker-row-card__preview,
.tracker-row-card__select,
.tracker-row-card__body,
.tracker-row-card__utility {
  min-width: 0;
  position: relative;
  z-index: 1;
}

/* ─── Preview ────────────────────────────────────────────── */
.tracker-row-card__preview {
  grid-area: preview;
  padding: 0;
  display: flex;
  align-items: stretch;
  border-radius: var(--v-radius-lg) 0 0 var(--v-radius-lg);
  overflow: hidden;
  background: var(--tracker-row-status-surface);
  box-shadow:
    inset 1px 0 0 var(--tracker-row-preview-border, var(--tracker-row-status-border)),
    inset 0 1px 0 var(--tracker-row-preview-border, var(--tracker-row-status-border)),
    inset 0 -1px 0 var(--tracker-row-preview-border, var(--tracker-row-status-border));
  transition: box-shadow var(--v-transition-fast), background var(--v-transition-fast);
}

.tracker-row-card__preview::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 4;
  border: 1px solid var(--tracker-row-preview-border, var(--tracker-row-status-border));
  border-right: 0;
  border-radius: var(--v-radius-lg) 0 0 var(--v-radius-lg);
  pointer-events: none;
  transition: border-color var(--v-transition-fast);
}

.tracker-row-card:hover .tracker-row-card__preview {
  background: var(--tracker-row-status-surface-hover);
  box-shadow:
    inset 1px 0 0 var(--tracker-row-preview-border, var(--tracker-row-status-border-hover)),
    inset 0 1px 0 var(--tracker-row-preview-border, var(--tracker-row-status-border-hover)),
    inset 0 -1px 0 var(--tracker-row-preview-border, var(--tracker-row-status-border-hover));
}

.tracker-row-card:hover .tracker-row-card__preview::after {
  border-color: var(--tracker-row-preview-border, var(--tracker-row-status-border-hover));
}

.tracker-row-card:has(.media-version-switcher.is-open) .tracker-row-card__preview {
  z-index: calc(var(--v-z-dropdown) + 9);
}

.tracker-row-card__preview :deep(.shot-version-stack),
.tracker-row-card__preview :deep(.version-wrapper) {
  width: 100%;
  min-height: 100%;
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview {
  padding: 8px;
}

/* A hairline ring keeps the frame from bleeding into the card on dark plates. */
.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.version-card)::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 3;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.tracker-row-card:not(.is-mobile-card):hover .tracker-row-card__preview :deep(.v-media-thumb-image) {
  transform: scale(1.035);
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.shot-version-stack),
.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.version-wrapper) {
  height: auto;
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.version-card) {
  height: auto;
  min-height: 0;
  aspect-ratio: 16 / 9;
  border-radius: var(--v-radius-md);
  border: 0;
  box-shadow: none;
  overflow: hidden;
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.v-media-thumb),
.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.v-media-thumb-image) {
  border-radius: var(--v-radius-md);
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.shot-version-switcher) {
  top: 10px;
  left: 10px;
}

.tracker-row-card:not(.is-mobile-card) .tracker-row-card__preview :deep(.duration-badge.v-media-badge) {
  right: 10px;
  bottom: 10px;
}

/* ─── Body ───────────────────────────────────────────────── */
.tracker-row-card__body {
  grid-area: body;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  padding: 14px 14px 14px 18px;
}

.tracker-row-card.has-open-picker .tracker-row-card__body {
  z-index: calc(var(--v-z-dropdown) + 13);
}

/* ─── Identity strip ─────────────────────────────────────── */
.trc-head {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
}

.trc-ident {
  flex: 1 1 auto;
  min-width: 0;
}

.trc-controls {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(110px, 148px));
  gap: 6px;
  align-items: center;
}

.trc-controls.has-assignee {
  grid-template-columns: repeat(3, minmax(108px, 148px));
}

.trc-control-cell {
  display: flex;
  min-width: 0;
}

.trc-controls :deep(.tracker-inline-select),
.trc-controls :deep(.tracker-inline-select-trigger) {
  width: 100%;
  max-width: none;
}

.trc-controls :deep(.tracker-inline-select-trigger) {
  min-height: 32px;
  padding: 0 10px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-sm);
}

.trc-controls :deep(.tracker-inline-select-label) {
  flex: 1 1 auto;
}

/* 144 chevrons on a full list is noise — keep them faint until you reach for one. */
.trc-controls :deep(.tracker-inline-select-chevron) {
  opacity: 0.4;
  transition: opacity var(--v-transition-fast);
}

.tracker-row-card:hover .trc-controls :deep(.tracker-inline-select-chevron),
.trc-controls :deep(.tracker-inline-select-trigger:hover .tracker-inline-select-chevron),
.trc-controls :deep(.tracker-inline-select.is-open .tracker-inline-select-chevron) {
  opacity: 0.85;
}

/* Status/tag/assignee tone treatment lives in TrackerInlineSelect, so the rows
   and the viewer topbar render the same value identically. */

/* ─── Combined Brief + Latest notes panel ────────────────── */
.trc-copy {
  --trc-lead-width: 40px;
  /* Fits the longest label ("Latest notes" measures 80px at 9px/800/0.15em)
     with a little air, so nothing silently clips. */
  --trc-label-width: 84px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
  overflow: hidden;
}

.trc-copy > :only-child {
  padding-top: 7px;
  padding-bottom: 7px;
}

.trc-brief + .trc-note::before {
  content: '';
  position: absolute;
  inset: 0 10px auto;
  height: 1px;
  background: rgba(255, 255, 255, 0.045);
  pointer-events: none;
}

.trc-brief {
  position: relative;
  display: grid;
  grid-template-columns: var(--trc-lead-width) minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 7px 12px 6px 10px;
  border: 0;
  background: transparent;
  border-radius: 0;
  cursor: pointer;
  text-align: left;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.trc-brief:hover,
.trc-brief:focus-visible {
  background: color-mix(in srgb, var(--v-bg-hover) 70%, transparent);
  outline: none;
}

.trc-brief:focus-visible {
  box-shadow: inset 0 0 0 2px var(--v-accent-muted);
}

.trc-brief-lead {
  display: inline-flex;
  align-items: center;
  width: var(--trc-lead-width);
  min-width: var(--trc-lead-width);
  flex-shrink: 0;
}

.trc-brief-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: color-mix(in srgb, var(--v-text-dim) 88%, transparent);
  transition: color var(--v-transition-fast);
}

.trc-brief.is-empty .trc-brief-icon {
  color: color-mix(in srgb, var(--v-text-dim) 78%, transparent);
}

.trc-brief-icon .icon {
  width: 15px;
  height: 15px;
}

/* Fixed label column so Brief and Notes copy starts on the same x. */
.trc-brief-main,
.trc-note-main {
  display: grid;
  grid-template-columns: var(--trc-label-width) minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.trc-section-tag {
  min-width: 0;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-3xs);
  font-weight: 800;
  letter-spacing: 0.15em;
  line-height: 1;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: clip;
  transition: color var(--v-transition-fast);
}

.trc-brief-tag {
  color: color-mix(in srgb, var(--v-text-dim) 76%, transparent);
}

.trc-brief-body {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--v-text-sm);
  line-height: 1.45;
  color: color-mix(in srgb, var(--v-text-muted) 94%, transparent);
  font-weight: 400;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 20px), transparent 100%);
          mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 20px), transparent 100%);
}

.trc-brief.is-empty .trc-brief-body {
  color: color-mix(in srgb, var(--v-text-dim) 90%, transparent);
  font-style: italic;
}

.trc-open-hint {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
  opacity: 0;
  transition: color var(--v-transition-fast), transform var(--v-transition-fast), opacity var(--v-transition-fast);
}

.trc-open-hint svg {
  width: 13px;
  height: 13px;
}

.trc-brief:hover .trc-open-hint,
.trc-brief:focus-visible .trc-open-hint,
.trc-note:hover .trc-open-hint,
.trc-note:focus-visible .trc-open-hint {
  color: var(--v-text-secondary);
  opacity: 1;
  transform: translateX(2px);
}

.trc-brief:hover .trc-brief-icon,
.trc-brief:focus-visible .trc-brief-icon {
  color: var(--v-text-muted);
}

.trc-brief:hover .trc-brief-tag,
.trc-brief:focus-visible .trc-brief-tag {
  color: var(--v-text-muted);
}

.trc-brief:hover .trc-brief-body,
.trc-brief:focus-visible .trc-brief-body {
  color: var(--v-text-secondary);
}

/* ─── Latest note row (same quiet system as Brief) ───────── */
.trc-note {
  position: relative;
  display: grid;
  grid-template-columns: var(--trc-lead-width) minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 6px 12px 7px 10px;
  border: 0;
  background: transparent;
  box-shadow: none;
  border-radius: 0;
  cursor: pointer;
  text-align: left;
  transition: background var(--v-transition-fast);
}

/* Same luminance as the gray panel wash, just hue-shifted when notes exist */
.trc-note:not(.is-empty) {
  background: color-mix(
    in srgb,
    var(--v-accent) 9%,
    color-mix(in srgb, var(--v-bg-hover) 40%, transparent)
  );
}

/* A live-notes row earns a thin accent edge you can catch at a glance. */
.trc-note:not(.is-empty)::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: color-mix(in srgb, var(--v-accent) 70%, transparent);
  pointer-events: none;
}

.trc-note:hover,
.trc-note:focus-visible {
  background: color-mix(in srgb, var(--v-bg-hover) 70%, transparent);
  outline: none;
}

.trc-note:not(.is-empty):hover,
.trc-note:not(.is-empty):focus-visible {
  background: color-mix(
    in srgb,
    var(--v-accent) 13%,
    color-mix(in srgb, var(--v-bg-hover) 48%, transparent)
  );
}

.trc-note:focus-visible {
  box-shadow: inset 0 0 0 2px var(--v-accent-muted);
}

.trc-note-lead {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: var(--trc-lead-width);
  min-width: var(--trc-lead-width);
  flex-shrink: 0;
}

.trc-note-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: color-mix(in srgb, var(--v-text-dim) 88%, transparent);
  transition: color var(--v-transition-fast);
}

.trc-note:not(.is-empty) .trc-note-icon {
  color: color-mix(in srgb, var(--v-accent) 85%, var(--v-text));
}

.trc-note.is-empty:hover .trc-note-icon,
.trc-note.is-empty:focus-visible .trc-note-icon {
  color: var(--v-text-muted);
}

.trc-note-icon .icon {
  width: 15px;
  height: 15px;
}

.trc-note-count {
  min-width: 14px;
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  text-align: left;
  color: color-mix(in srgb, var(--v-accent) 82%, var(--v-text-secondary));
}

.trc-note.is-empty .trc-note-count {
  color: var(--v-text-muted);
}

.trc-note-tag {
  color: color-mix(in srgb, var(--v-accent) 72%, var(--v-text-muted));
}

.trc-note.is-empty .trc-note-tag {
  color: color-mix(in srgb, var(--v-text-dim) 76%, transparent);
}

.trc-note-body {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--v-text-sm);
  line-height: 1.45;
  color: var(--v-text-secondary);
  font-weight: 450;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 20px), transparent 100%);
          mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 20px), transparent 100%);
}

.trc-note.is-empty .trc-note-body {
  color: color-mix(in srgb, var(--v-text-dim) 90%, transparent);
  font-style: italic;
  font-weight: 400;
}

.trc-note:not(.is-empty):hover .trc-note-body,
.trc-note:not(.is-empty):focus-visible .trc-note-body {
  color: var(--v-text);
}

/* ─── Utility column ─────────────────────────────────────── */
.tracker-row-card__utility {
  grid-area: utility;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 7px 0 0;
}

.tracker-row-card__utility.is-centered {
  justify-content: center;
}

.tracker-row-card__utility-actions {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--tracker-utility-gap, 2px);
  opacity: 0;
  transform: translateX(4px);
  transition:
    opacity var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.tracker-row-card:hover .tracker-row-card__utility-actions,
.tracker-row-card:focus-within .tracker-row-card__utility-actions {
  opacity: 1;
  transform: none;
}

.tracker-row-card__utility-actions.is-centered {
  justify-content: center;
}

.tracker-utility-btn {
  position: relative;
  width: 30px;
  min-width: 30px;
  height: 30px;
  min-height: 30px;
  z-index: 0;
  background: transparent;
  border-color: transparent;
  color: var(--v-text-muted);
}

.tracker-utility-btn:hover:not(:disabled) {
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border);
  color: var(--v-text);
}

.tracker-utility-btn .icon {
  width: 13px;
  height: 13px;
}

/* ─── Status / category dots ─────────────────────────────── */
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: var(--v-radius-full);
  flex-shrink: 0;
}

.dot-not_started { background: var(--v-status-draft); }
.dot-in_progress { background: var(--v-status-active); }
.dot-waiting_review { background: var(--v-status-review); }
.dot-edits_requested { background: var(--v-status-hold); }
.dot-done { background: var(--v-status-done); }

/* ─── Responsive: head wraps on narrower viewports ───────── */
@media (max-width: 1200px) {
  .tracker-row-card {
    --tracker-row-thumb-width: clamp(220px, 27vw, 300px);
  }

  .trc-controls {
    grid-template-columns: repeat(2, minmax(96px, 132px));
    gap: 5px;
  }

  .trc-controls.has-assignee {
    grid-template-columns: repeat(3, minmax(92px, 124px));
  }
}

@media (max-width: 1024px) {
  .trc-head {
    flex-direction: column;
    align-items: stretch;
    gap: var(--v-space-2);
  }

  .trc-controls,
  .trc-controls.has-assignee {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }

  .trc-controls.has-assignee .trc-control-cell.is-status {
    grid-column: 1 / -1;
  }
}

/* ─── Responsive: mobile ─────────────────────────────────── */
.tracker-row-card.is-mobile-card {
    --trc-card-inset: 14px;
    --trc-thumb-overlay-inset: 10px;
    border-radius: var(--v-radius-lg);
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      'preview'
      'title'
      'controls'
      'copy';
    align-items: start;
    row-gap: 0;
    padding: 0;
    overflow: visible;
    background: var(--tracker-row-status-surface);
    border: 1px solid var(--tracker-row-status-border);
    box-shadow: none;
}

.tracker-row-card.is-mobile-card:hover {
    background: var(--tracker-row-status-surface-hover);
    border-color: var(--tracker-row-status-border-hover);
}

.tracker-row-card.is-mobile-card.selection-enabled,
.tracker-row-card.is-mobile-card.selection-enabled:hover {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      'preview'
      'title'
      'controls'
      'copy';
    background: var(--tracker-row-status-surface);
    border-color: var(--tracker-row-status-border);
}

.tracker-row-card.is-mobile-card.selection-enabled::after {
    content: none;
}

.tracker-row-card.is-mobile-card.selection-enabled.is-selected,
.tracker-row-card.is-mobile-card.is-selected {
    background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-raised));
    border-color: color-mix(in srgb, var(--v-accent) 28%, var(--v-surface-border-soft));
}

.tracker-row-card.is-mobile-card.selection-enabled.is-selected::before {
    inset: 10px auto 10px 0;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview {
    grid-area: preview;
    position: relative;
    padding: var(--trc-card-inset) var(--trc-card-inset) 0;
    width: 100%;
    border-radius: var(--v-radius-lg) var(--v-radius-lg) 0 0;
    overflow: hidden;
    aspect-ratio: auto;
    background: var(--tracker-row-status-surface);
    box-shadow: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview::after {
    content: none;
}

.tracker-row-card.is-mobile-card:hover .tracker-row-card__preview {
    box-shadow: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.version-card),
.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.version-wrapper),
.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.shot-version-stack) {
    border-radius: var(--v-radius-md);
    overflow: hidden;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.duration-badge.v-media-badge) {
    left: var(--trc-thumb-overlay-inset);
    right: auto;
    bottom: var(--trc-thumb-overlay-inset);
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.shot-version-stack),
.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.version-wrapper),
.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.version-card) {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
    border: 0;
    border-radius: var(--v-radius-md);
    box-shadow: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.version-hover) {
    display: none;
}

.tracker-row-card.is-grid-card .tracker-row-card__preview :deep(.version-hover) {
    display: flex;
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.v-media-thumb) {
    height: 100%;
    border-radius: var(--v-radius-md);
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.v-media-thumb-image) {
    border-radius: var(--v-radius-md);
}

.tracker-row-card.is-mobile-card .tracker-row-card__preview :deep(.shot-version-switcher) {
    top: var(--trc-thumb-overlay-inset);
    left: var(--trc-thumb-overlay-inset);
}

.tracker-row-card.is-mobile-card .tracker-row-card__body {
    display: contents;
}

.tracker-row-card.is-mobile-card .trc-head {
    display: contents;
}

.tracker-row-card.is-mobile-card .trc-ident {
    grid-area: title;
    display: flex;
    align-items: center;
    min-height: 0;
    /* Bare text reads wider than pill/box surfaces; nudge in slightly */
    padding: 12px calc(var(--trc-card-inset) + 4px) 0;
}

.tracker-row-card.is-mobile-card .trc-ident :deep(.tracker-row-meta) {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    flex-wrap: nowrap;
    gap: var(--v-space-3);
    line-height: 1.2;
}

.tracker-row-card.is-mobile-card .trc-ident :deep(.tracker-row-id-input),
.tracker-row-card.is-mobile-card .trc-ident :deep(.tracker-row-id-text) {
    flex: 1 1 auto;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.tracker-row-card.is-mobile-card .trc-ident :deep(.tracker-row-updated) {
    flex: 0 0 auto;
    margin-left: auto;
    color: color-mix(in srgb, var(--v-text-dim) 72%, var(--v-bg-base));
    white-space: nowrap;
    text-align: right;
}

.tracker-row-card.is-mobile-card .trc-controls {
    grid-area: controls;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
    padding: 10px var(--trc-card-inset) 0;
}

.tracker-row-card.is-mobile-card .trc-controls.has-assignee {
    grid-area: controls;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 6px;
    padding: 10px var(--trc-card-inset) 0;
}

.tracker-row-card.is-mobile-card .trc-controls.has-assignee .trc-control-cell.is-status {
    grid-column: auto;
}

.tracker-row-card.is-mobile-card .trc-controls :deep(.tracker-inline-select-trigger) {
    min-height: 32px;
    padding: 0 10px;
    border-radius: var(--v-button-radius);
    border-color: var(--v-control-border);
    background: var(--v-control-bg);
    box-shadow: var(--v-surface-shadow-inset);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    font-size: var(--v-text-sm);
}

.tracker-row-card.is-mobile-card .trc-controls :deep(.tracker-inline-select-label) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.tracker-row-card.is-mobile-card .trc-controls :deep(.tracker-inline-select-trigger:hover),
.tracker-row-card.is-mobile-card .trc-controls :deep(.tracker-inline-select.is-open .tracker-inline-select-trigger) {
    border-color: var(--v-control-border-hover);
    background: var(--v-control-bg-hover);
}

.tracker-row-card.is-mobile-card .trc-controls :deep(.tracker-inline-select-chevron) {
    display: block;
    width: 11px;
    height: 11px;
    flex: 0 0 auto;
    color: var(--v-text-dim);
}

.tracker-row-card.is-mobile-card .trc-copy {
    grid-area: copy;
    margin: 10px var(--trc-card-inset) 12px;
}

.tracker-row-card.is-mobile-card .trc-brief {
    grid-template-columns: var(--trc-lead-width) minmax(0, 1fr);
    align-items: stretch;
    margin: 0;
    width: auto;
    padding: 6px 12px 4px 8px;
    gap: 10px;
    height: var(--trc-mobile-brief-height);
    min-height: var(--trc-mobile-brief-height);
    max-height: var(--trc-mobile-brief-height);
    border: 0;
    border-radius: 0;
    overflow: hidden;
}

.tracker-row-card.is-mobile-card .trc-brief.is-empty {
    border-color: transparent;
}

.tracker-row-card.is-mobile-card .trc-brief:hover,
.tracker-row-card.is-mobile-card .trc-brief:focus-visible {
    background: color-mix(in srgb, var(--v-control-bg-hover) 55%, transparent);
    border-color: transparent;
}

.tracker-row-card.is-mobile-card .trc-brief-main {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-content: center;
    gap: 5px;
    height: 100%;
    min-height: 0;
}

.tracker-row-card.is-mobile-card .trc-brief-body {
    flex-basis: 100%;
    -webkit-mask-image: none;
            mask-image: none;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 1;
    white-space: normal;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--v-text-sm);
    line-height: var(--trc-mobile-copy-line-height);
    max-height: var(--trc-mobile-copy-line-height);
}

.tracker-row-card.is-mobile-card .trc-brief .trc-open-hint {
    display: none;
}

.tracker-row-card.is-mobile-card .trc-note {
    grid-template-columns: var(--trc-lead-width) minmax(0, 1fr);
    align-items: stretch;
    margin: 0;
    width: auto;
    padding: 4px 12px 6px 8px;
    height: var(--trc-mobile-note-height);
    min-height: var(--trc-mobile-note-height);
    max-height: var(--trc-mobile-note-height);
    border: 0;
    border-radius: 0;
    box-shadow: none;
    overflow: hidden;
}

.tracker-row-card.is-mobile-card .trc-note:hover,
.tracker-row-card.is-mobile-card .trc-note:focus-visible {
    background: color-mix(in srgb, var(--v-bg-hover) 55%, transparent);
}

.tracker-row-card.is-mobile-card .trc-note:not(.is-empty):hover,
.tracker-row-card.is-mobile-card .trc-note:not(.is-empty):focus-visible {
    background: color-mix(
      in srgb,
      var(--v-accent) 12%,
      color-mix(in srgb, var(--v-bg-hover) 48%, transparent)
    );
}

.tracker-row-card.is-mobile-card .trc-note-main {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-content: center;
    gap: 5px;
    height: 100%;
    min-height: 0;
}

.tracker-row-card.is-mobile-card .trc-note-body {
    flex-basis: 100%;
    -webkit-mask-image: none;
            mask-image: none;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 1;
    white-space: normal;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--v-text-sm);
    line-height: var(--trc-mobile-copy-line-height);
    max-height: var(--trc-mobile-copy-line-height);
}

.tracker-row-card.is-mobile-card .trc-note .trc-open-hint {
    display: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__select {
    position: static;
    grid-area: preview;
    align-self: start;
    justify-self: end;
    z-index: 5;
    margin: var(--trc-card-inset) var(--trc-card-inset) 0 0;
    padding: 0;
    pointer-events: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__select .tracker-row-select-btn {
    width: 44px;
    height: 44px;
    opacity: 0.72;
    background: transparent;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    pointer-events: auto;
    transform: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__select .tracker-row-select-box {
    width: 18px;
    height: 18px;
}

.tracker-row-card.is-mobile-card .tracker-row-card__utility {
    position: static;
    grid-area: preview;
    align-self: end;
    justify-self: end;
    z-index: 5;
    margin: 0
      calc(var(--trc-card-inset) + var(--trc-thumb-overlay-inset))
      var(--trc-thumb-overlay-inset);
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    pointer-events: none;
}

.tracker-row-card.is-mobile-card .tracker-row-card__utility-actions {
    flex-direction: row;
    gap: 1px;
    opacity: 1;
    pointer-events: auto;
    padding: 2px;
    border-radius: var(--v-button-radius);
    background: color-mix(in srgb, var(--v-overlay-pill-bg) 58%, transparent);
    border: 1px solid color-mix(in srgb, var(--v-overlay-pill-border) 55%, transparent);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}

.tracker-row-card.is-mobile-card .tracker-utility-btn {
    width: 40px;
    min-width: 40px;
    height: 40px;
    min-height: 40px;
    border-radius: var(--v-button-radius);
    border: 0;
    background: transparent;
    color: var(--v-overlay-pill-text);
    opacity: 0.72;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    box-shadow: none;
    transition: background var(--v-transition-fast), color var(--v-transition-fast), opacity var(--v-transition-fast);
}

.tracker-row-card.is-mobile-card .tracker-utility-btn:hover,
.tracker-row-card.is-mobile-card .tracker-utility-btn:active {
    background: color-mix(in srgb, white 10%, transparent);
    border-color: transparent;
    color: var(--v-text);
    opacity: 1;
}

.tracker-row-card.is-mobile-card .tracker-utility-btn-danger:hover,
.tracker-row-card.is-mobile-card .tracker-utility-btn-danger:active {
    background: color-mix(in srgb, var(--v-danger) 22%, transparent);
    border-color: transparent;
    color: var(--v-danger-text);
    opacity: 1;
}

.tracker-row-card.is-mobile-card .status-dot,
.tracker-row-card.is-mobile-card :deep(.category-color-indicator) {
    width: 6px;
    height: 6px;
}
</style>
