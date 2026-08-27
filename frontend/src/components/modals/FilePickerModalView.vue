<template>
  <VModal
    :modelValue="show"
    :size="isVersionPickerMode ? 'lg' : 'md'"
    class="file-picker-modal"
    :class="{ 'is-version-picker': isVersionPickerMode }"
    :full-height="true"
    :mobile-full-height="true"
    :aria-labelledby="filePickerTitleId"
    @update:modelValue="closeFilePicker"
  >
    <template #header>
      <VModalHeader
        :title="filePickerTitle"
        :title-id="filePickerTitleId"
        :subtitle="filePickerSubtitle"
        @close="closeFilePicker"
      />
    </template>

    <!-- Mode rail (tracker import: Add Shots / Bulk Update) -->
    <div v-if="showTrackerImportModeToggle" class="fp-mode-block">
      <span class="fp-control-label">Import type</span>
      <div class="fp-mode-rail">
        <VTabs
          :model-value="trackerImportMode"
          :tabs="trackerImportModeTabs"
          variant="segmented"
          :full-width="true"
          @update:modelValue="setTrackerImportMode"
        />
      </div>
    </div>

    <!-- Target strip (version picker modes only) -->
    <div
      v-if="isVersionPickerMode"
      class="fp-target"
      :class="{ 'is-empty': !selectedVersionPickerShot }"
    >
      <div class="fp-target-thumb">
        <VMediaThumbnail
          v-if="selectedVersionPickerShot && selectedVersionPickerCurrentMediaInput?.path"
          :src="getThumbnailUrl(selectedVersionPickerCurrentMediaInput)"
          :alt="selectedVersionPickerShot.shot_id"
        />
        <div v-else class="fp-target-thumb-placeholder" aria-hidden="true">
          <svg class="icon">
            <use :href="selectedVersionPickerCurrentMediaInput?.is_image ? '#icon-image' : '#icon-video'" />
          </svg>
        </div>
        <span v-if="targetDurationLabel" class="fp-target-duration">{{ targetDurationLabel }}</span>
      </div>

      <div class="fp-target-copy">
        <span class="fp-target-eyebrow v-eyebrow">Current shot</span>
        <div class="fp-target-title-row">
          <strong v-if="selectedVersionPickerShot" class="fp-target-title">{{ selectedVersionPickerShot.shot_id }}</strong>
          <strong v-else class="fp-target-title fp-target-empty">Select a shot to update</strong>
          <span v-if="selectedVersionPickerShot && selectedShotVersionLabel" class="v-tag v-tag--accent">{{ selectedShotVersionLabel }}</span>
          <template v-if="selectedVersionPickerShot && targetDurationLabel">
            <span class="fp-target-dot" aria-hidden="true">·</span>
            <span class="fp-target-meta">{{ targetDurationLabel }}</span>
          </template>
        </div>
      </div>

      <label
        v-if="pickerMode === 'bulk-version-update' && versionPickerShots.length > 1"
        class="v-labeled-select fp-shot-select"
        :title="`Switch shot (${versionPickerShots.length})`"
      >
        <span class="v-labeled-select-eyebrow">Shot</span>
        <span class="v-labeled-select-value">
          <span class="v-labeled-select-text">{{ shotSelectorDisplay }}</span>
          <svg class="icon v-labeled-select-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
        </span>
        <select
          class="v-labeled-select-native"
          :value="versionPickerTargetShotId"
          aria-label="Switch shot"
          @change="selectVersionPickerShot(versionPickerShots.find(shot => (shot.id || shot.shot_id) === $event.target.value || shot.shot_id === $event.target.value))"
        >
          <option
            v-for="(shot, idx) in versionPickerShots"
            :key="shot.id || shot.shot_id"
            :value="shot.id || shot.shot_id"
          >
            {{ shot.shot_id }} ({{ idx + 1 }}/{{ versionPickerShots.length }})
          </option>
        </select>
      </label>
    </div>

    <!-- Source selector -->
    <div v-if="canUseProjectPicker" class="v-modal-section fp-source-section">
      <div class="v-modal-section-head fp-source-head">
        <div>
          <h3 class="v-modal-section-title">Choose a source</h3>
          <p class="v-modal-section-copy">Choose where to browse for files.</p>
        </div>
        <button
          v-if="pickerMode === 'comment-reference'"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm"
          @click="uploadCommentFiles"
        >
          <svg class="icon"><use href="#icon-upload" /></svg>
          Upload from device
        </button>
      </div>

      <div
        v-if="pickerSourceTabs.length > 1"
        class="fp-source-toggle"
        role="radiogroup"
        aria-label="File source"
      >
        <button
          v-for="tab in pickerSourceTabs"
          :key="tab.value"
          type="button"
          class="fp-source-option"
          :class="{ 'is-active': pickerSource === tab.value }"
          role="radio"
          :aria-checked="pickerSource === tab.value"
          @click="setPickerSource(tab.value)"
        >
          <span class="fp-source-option-icon" aria-hidden="true">
            <svg class="icon"><use :href="getSourceMeta(tab.value).icon" /></svg>
          </span>
          <span class="fp-source-option-copy">
            <span class="fp-source-option-title">{{ getSourceMeta(tab.value).title }}</span>
            <span class="fp-source-option-hint">{{ getSourceMeta(tab.value).hint }}</span>
          </span>
          <span class="fp-source-option-check" aria-hidden="true">
            <svg class="icon"><use href="#icon-check" /></svg>
          </span>
        </button>
      </div>

      <div
        v-else-if="pickerSourceTabs.length === 1"
        class="v-modal-card-soft fp-source-single"
      >
        <span class="fp-source-single-icon" aria-hidden="true">
          <svg class="icon"><use :href="getSourceMeta(pickerSourceTabs[0].value).icon" /></svg>
        </span>
        <span class="fp-source-single-copy">
          <span class="fp-source-single-title">{{ getSourceMeta(pickerSourceTabs[0].value).title }}</span>
          <span class="fp-source-single-hint">{{ getSourceMeta(pickerSourceTabs[0].value).hint }}</span>
        </span>
      </div>
    </div>

    <!-- Browser -->
    <div class="v-modal-card fp-browser">
      <div class="fp-browser-toolbar">
        <div class="fp-browser-location">
          <div class="fp-browser-path">
            <span class="fp-browser-path-icon" aria-hidden="true">
              <svg class="icon"><use :href="canUseProjectPicker ? getSourceMeta(pickerSource).icon : '#icon-cloud'" /></svg>
            </span>
            <button
              v-if="pickerPath"
              type="button"
              class="fp-browser-up v-btn v-btn-quiet v-btn-icon v-btn-sm"
              aria-label="Up one folder"
              @click="pickerGoUp"
            >
              <svg class="icon"><use href="#icon-back" /></svg>
            </button>
            <span class="fp-browser-path-text v-truncate">{{ pickerPath || pickerRootLabel }}</span>
            <span class="fp-browser-count" :aria-label="`${pickerCount} items`">{{ pickerCount }}</span>
          </div>
          <p class="fp-browser-guide">{{ browserGuide }}</p>
        </div>
        <div v-if="isVersionPickerMode" class="fp-browser-filter">
          <svg class="icon fp-browser-filter-icon" aria-hidden="true"><use href="#icon-search" /></svg>
          <input
            :value="versionPickerFileSearch"
            class="fp-browser-filter-input"
            placeholder="Filter files"
            aria-label="Filter files"
            @input="setVersionPickerFileSearch($event.target.value)"
          />
        </div>
      </div>

      <div class="fp-list" :class="{ 'is-version-picker': isVersionPickerMode }">
        <template v-if="isVersionPickerMode">
          <button
            v-for="item in versionPickerBrowserItems"
            :key="item.path"
            type="button"
            class="fp-list-row"
            :class="{ 'is-selected': versionPickerSelectedCandidatePath === item.path, 'is-folder': item.type === 'folder' }"
            @click="pickerSelect(item)"
          >
            <div v-if="item.type !== 'folder'" class="fp-list-thumb">
              <VMediaThumbnail
                :src="getThumbnailUrl(getPickerItemMedia(item))"
                :alt="item.name"
                @visible="requestPickerItemMediaInfo(item)"
              />
              <span v-if="getMediaDurationLabel(getPickerItemMedia(item))" class="fp-list-duration">{{ getMediaDurationLabel(getPickerItemMedia(item)) }}</span>
            </div>
            <div v-else class="fp-list-icon" aria-hidden="true">
              <svg class="icon"><use href="#icon-folder" /></svg>
            </div>
            <div class="fp-list-copy">
              <span class="v-truncate fp-list-name">{{ item.name }}</span>
              <span v-if="item.type !== 'folder'" class="fp-list-meta v-truncate">
                {{ getFileMetaLine(item) }}
              </span>
              <span v-else class="fp-list-meta v-truncate">Folder</span>
            </div>
            <span class="fp-list-trail" aria-hidden="true">
              <svg v-if="item.type === 'folder'" class="icon fp-list-chevron"><use href="#icon-chevron-down" /></svg>
              <svg v-else-if="versionPickerSelectedCandidatePath === item.path" class="icon fp-list-check"><use href="#icon-check" /></svg>
            </span>
          </button>

          <div v-if="!versionPickerBrowserItems.length" class="fp-empty">
            <svg class="icon"><use href="#icon-search" /></svg>
            <p>No files or folders match your filter.</p>
          </div>
        </template>

        <template v-else>
          <div
            v-for="item in pickerFiles"
            :key="[item.type, item.id, item.media_asset_id, item.path].filter(Boolean).join(':')"
            class="fp-list-row"
            :class="{ 'is-selected': isPickerSelected(item), 'is-folder': item.type === 'folder' }"
          >
            <button
              type="button"
              class="fp-list-main"
              :aria-pressed="isMultiSelectPickerMode && item.type !== 'folder' ? isPickerSelected(item) : undefined"
              @click="pickerSelect(item)"
            >
              <span v-if="isMediaPickerItem(item)" class="fp-list-thumb">
                <VMediaThumbnail
                  :src="getThumbnailUrl(getPickerItemMedia(item))"
                  :alt="item.name"
                  @visible="requestPickerItemMediaInfo(item)"
                />
                <span v-if="getMediaDurationLabel(getPickerItemMedia(item))" class="fp-list-duration">{{ getMediaDurationLabel(getPickerItemMedia(item)) }}</span>
              </span>
              <span v-else class="fp-list-icon" aria-hidden="true">
                <svg class="icon">
                  <use :href="getPickerItemIcon(item)" />
                </svg>
              </span>
              <span class="fp-list-copy">
                <span class="v-truncate fp-list-name">{{ item.name }}</span>
                <span v-if="pickerMode === 'shot-import' && item.type !== 'folder' && getMediaDurationLabel(getPickerItemMedia(item))" class="fp-list-meta v-truncate">
                  {{ getMediaDurationLabel(getPickerItemMedia(item)) }}
                </span>
                <span v-else-if="getPickerItemMeta(item)" class="fp-list-meta v-truncate">{{ getPickerItemMeta(item) }}</span>
              </span>
              <span
                v-if="isMultiSelectPickerMode && item.type !== 'folder'"
                class="fp-list-checkbox"
                :class="{ 'is-checked': isPickerSelected(item) }"
                aria-hidden="true"
              >
                <svg v-if="isPickerSelected(item)" class="icon"><use href="#icon-check" /></svg>
              </span>
              <span v-else class="fp-list-trail" aria-hidden="true">
                <svg v-if="item.type === 'folder'" class="icon fp-list-chevron"><use href="#icon-chevron-down" /></svg>
                <svg v-else-if="isPickerSelected(item)" class="icon fp-list-check"><use href="#icon-check" /></svg>
              </span>
            </button>
            <button
              v-if="pickerMode === 'shot-import' && item.type === 'folder'"
              type="button"
              class="fp-list-action v-btn v-btn-quiet v-btn-sm"
              :disabled="shotImportApplyBusy"
              @click.stop="importFolder(item)"
            >
              <svg class="icon" :class="{ 'is-spinning': shotImportApplyBusy }"><use :href="shotImportApplyBusy ? '#icon-loader' : '#icon-download'" /></svg>
              <span class="fp-list-action-label">{{ shotImportApplyBusy ? 'Importing…' : 'Import all' }}</span>
            </button>
            <button
              v-else-if="pickerMode === 'comment-reference' && item.type === 'folder'"
              type="button"
              class="fp-list-action v-btn v-btn-quiet v-btn-sm"
              :class="{ 'is-selected': isPickerSelected(item) }"
              :aria-pressed="isPickerSelected(item)"
              @click.stop="pickerSelect({ ...item, _selectFolder: true })"
            >
              <svg class="icon"><use :href="isPickerSelected(item) ? '#icon-check' : '#icon-link'" /></svg>
              <span class="fp-list-action-label">{{ isPickerSelected(item) ? 'Attached' : 'Attach' }}</span>
            </button>
            <button
              v-else-if="pickerMode === 'project-link' && item.type === 'folder'"
              type="button"
              class="fp-list-action v-btn v-btn-quiet v-btn-sm"
              @click.stop="linkFolderToProject(item.path)"
            >
              <svg class="icon"><use href="#icon-link" /></svg>
              <span class="fp-list-action-label">Link</span>
            </button>
            <button
              v-else-if="pickerMode === 'page-resource' && item.type === 'folder'"
              type="button"
              class="fp-list-action v-btn v-btn-quiet v-btn-sm"
              @click.stop="pickerSelect({ ...item, _selectFolder: true })"
            >
              <svg class="icon"><use href="#icon-plus" /></svg>
              <span class="fp-list-action-label">Add</span>
            </button>
          </div>

          <div v-if="!pickerFiles.length" class="fp-empty">
            <svg class="icon"><use href="#icon-folder" /></svg>
            <p>This folder is empty.</p>
          </div>
        </template>
      </div>

      <div v-if="isVersionPickerMode && canLoadMoreVersionPickerCandidates" class="fp-load-more">
        <button class="v-btn v-btn-secondary v-btn-sm" @click="loadMoreVersionPickerCandidates">
          Load {{ remainingVersionPickerCandidateCount }} more
        </button>
      </div>
    </div>

    <template #footer>
      <div v-if="isVersionPickerMode" class="fp-footer">
        <p
          v-if="versionPickerFooterText"
          class="fp-footer-status"
          :class="{ 'is-ready': canApplyVersionPickerSelection }"
          aria-live="polite"
        >
          <span class="fp-footer-status-icon" aria-hidden="true">
            <svg class="icon"><use :href="canApplyVersionPickerSelection ? '#icon-check' : '#icon-info'" /></svg>
          </span>
          <span class="fp-footer-status-text v-truncate">{{ versionPickerFooterText }}</span>
        </p>
        <div class="fp-footer-row">
          <label class="fp-footer-changelog">
            <span class="v-eyebrow">Changelog</span>
            <input
              :value="versionPickerNotes"
              class="fp-footer-changelog-input"
              maxlength="120"
              placeholder="Optional note about what changed"
              @input="setVersionPickerNotes($event.target.value)"
            />
          </label>
          <div class="fp-footer-actions">
            <button class="v-btn v-btn-secondary" @click="closeFilePicker">Cancel</button>
            <button
              class="v-btn v-btn-primary"
              :disabled="!canApplyVersionPickerSelection"
              @click="applyVersionPickerSelection"
            >
              {{ versionPickerApplyBusy ? 'Updating…' : (pickerMode === 'bulk-version-update' ? 'Add & Next' : 'Add Version') }}
            </button>
          </div>
        </div>
      </div>
      <div v-else-if="isMultiSelectPickerMode" class="fp-footer fp-footer-compact">
        <p class="fp-footer-status" :class="{ 'is-ready': canApplyMultiSelectPickerSelection }" aria-live="polite">
          <span class="fp-footer-status-icon" aria-hidden="true">
            <svg class="icon"><use :href="canApplyMultiSelectPickerSelection ? '#icon-check' : '#icon-info'" /></svg>
          </span>
          <span class="fp-footer-status-text v-truncate">
            {{ selectedMultiSelectPickerCount ? `${selectedMultiSelectPickerCount} selected` : multiSelectPickerEmptyLabel }}
          </span>
        </p>
        <div class="fp-footer-actions">
          <button class="v-btn v-btn-secondary" @click="closeFilePicker">Cancel</button>
          <button
            class="v-btn v-btn-primary"
            :disabled="!canApplyMultiSelectPickerSelection"
            @click="applyMultiSelectPickerSelection"
          >
            {{ multiSelectPickerApplyLabel }}
          </button>
        </div>
      </div>
      <button v-else class="v-btn v-btn-secondary" @click="closeFilePicker">Cancel</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed } from 'vue'
import VMediaThumbnail from '../media/VMediaThumbnail.vue'
import { VModal, VModalHeader, VTabs } from '../primitives'

const filePickerTitleId = 'file-picker-modal-title'

const props = defineProps({
  show: { type: Boolean, required: true },
  isVersionPickerMode: { type: Boolean, required: true },
  filePickerTitle: { type: String, required: true },
  pickerMode: { type: String, required: true },
  showTrackerImportModeToggle: { type: Boolean, default: false },
  trackerImportMode: { type: String, default: 'shot-import' },
  trackerImportModeTabs: { type: Array, default: () => [] },
  pickerPath: { type: String, required: true },
  pickerFiles: { type: Array, required: true },
  pickerSource: { type: String, default: 'nas' },
  canUseProjectPicker: { type: Boolean, default: false },
  pickerSourceTabs: { type: Array, default: () => [] },
  selectedVersionPickerShot: { type: Object, default: null },
  selectedVersionPickerCurrentMedia: { type: Object, default: null },
  selectedVersionPickerCurrentPath: { type: String, default: '' },
  versionPickerCurrentInfo: { type: Object, default: null },
  versionPickerShots: { type: Array, required: true },
  versionPickerTargetShotId: { type: String, default: '' },
  versionPickerFileSearch: { type: String, required: true },
  versionPickerNotes: { type: String, default: '' },
  versionPickerBrowserItems: { type: Array, required: true },
  versionPickerSelectedCandidatePath: { type: String, default: '' },
  canLoadMoreVersionPickerCandidates: { type: Boolean, required: true },
  remainingVersionPickerCandidateCount: { type: Number, required: true },
  versionPickerFooterText: { type: String, required: true },
  canApplyVersionPickerSelection: { type: Boolean, required: true },
  versionPickerApplyBusy: { type: Boolean, required: true },
  selectedShotImportCount: { type: Number, default: 0 },
  canApplyShotImportSelection: { type: Boolean, default: false },
  shotImportApplyBusy: { type: Boolean, default: false },
  shotImportApplyLabel: { type: String, default: 'Import files' },
  selectedProjectLinkCount: { type: Number, default: 0 },
  canApplyProjectLinkSelection: { type: Boolean, default: false },
  projectLinkApplyBusy: { type: Boolean, default: false },
  projectLinkApplyLabel: { type: String, default: 'Link files' },
  closeFilePicker: { type: Function, required: true },
  getThumbnailUrl: { type: Function, required: true },
  getMediaDurationLabel: { type: Function, required: true },
  getShotVersionCount: { type: Function, required: true },
  getPickerItemMedia: { type: Function, required: true },
  requestPickerItemMediaInfo: { type: Function, required: true },
  selectVersionPickerShot: { type: Function, required: true },
  setVersionPickerFileSearch: { type: Function, required: true },
  setVersionPickerNotes: { type: Function, required: true },
  setPickerSource: { type: Function, required: true },
  pickerGoUp: { type: Function, required: true },
  pickerSelect: { type: Function, required: true },
  setTrackerImportMode: { type: Function, required: true },
  loadMoreVersionPickerCandidates: { type: Function, required: true },
  isPickerSelected: { type: Function, required: true },
  importFolder: { type: Function, required: true },
  applyShotImportSelection: { type: Function, required: true },
  linkFolderToProject: { type: Function, required: true },
  applyProjectLinkSelection: { type: Function, required: true },
  applyVersionPickerSelection: { type: Function, required: true },
  uploadCommentFiles: { type: Function, required: true },
})

const selectedVersionPickerCurrentMediaInput = computed(() => {
  if (!props.selectedVersionPickerCurrentMedia && !props.selectedVersionPickerCurrentPath) return null
  return {
    ...(props.versionPickerCurrentInfo || {}),
    ...(props.selectedVersionPickerCurrentMedia || {}),
    path: props.selectedVersionPickerCurrentMedia?.path || props.versionPickerCurrentInfo?.path || props.selectedVersionPickerCurrentPath,
    file_path: props.selectedVersionPickerCurrentMedia?.file_path || props.versionPickerCurrentInfo?.file_path || props.selectedVersionPickerCurrentPath,
  }
})

const pickerRootLabel = computed(() => (
  props.canUseProjectPicker ? 'Root' : 'NAS'
))

const filePickerSubtitle = computed(() => {
  if (props.pickerMode === 'shot-import') return 'Select media files, or import every compatible file in a folder.'
  if (props.pickerMode === 'bulk-version-update') return 'Choose a shot, then select the file that should become its next version.'
  if (props.pickerMode === 'shot') return 'Select the file that should become this shot\'s next version.'
  if (props.pickerMode === 'comment-reference') return 'Attach up to three files, folders, trackers, or dashboards.'
  if (props.pickerMode === 'project-link') return 'Select the files you want to link to this project.'
  if (props.pickerMode === 'page-resource') return 'Choose a file or folder to add to this dashboard.'
  return 'Browse folders and choose the file you need.'
})

const browserGuide = computed(() => {
  if (props.pickerMode === 'shot-import') return 'Open a folder to browse it. Select files individually or import the whole folder.'
  if (props.isVersionPickerMode) return 'Open folders to browse, then select one media file.'
  if (props.pickerMode === 'comment-reference') return 'Open a folder to browse it, or use Attach to link the whole folder.'
  if (props.isMultiSelectPickerMode) return 'Open folders to browse, then select one or more items.'
  return 'Open folders to browse, then choose an item.'
})

const pickerCount = computed(() => (
  props.isVersionPickerMode ? props.versionPickerBrowserItems.length : props.pickerFiles.length
))

const isMultiSelectPickerMode = computed(() => ['project-link', 'shot-import', 'comment-reference'].includes(props.pickerMode))

const selectedMultiSelectPickerCount = computed(() => (
  props.pickerMode === 'shot-import' ? props.selectedShotImportCount : props.selectedProjectLinkCount
))

const canApplyMultiSelectPickerSelection = computed(() => (
  props.pickerMode === 'shot-import' ? props.canApplyShotImportSelection : props.canApplyProjectLinkSelection
))

const multiSelectPickerApplyLabel = computed(() => (
  props.pickerMode === 'shot-import' ? props.shotImportApplyLabel : props.projectLinkApplyLabel
))

const multiSelectPickerEmptyLabel = computed(() => (
  props.pickerMode === 'shot-import'
    ? 'Select files to import'
    : props.pickerMode === 'comment-reference'
      ? 'Select files, folders, trackers, or dashboards'
      : 'Select files to link'
))

function applyMultiSelectPickerSelection() {
  if (props.pickerMode === 'shot-import') {
    props.applyShotImportSelection()
    return
  }
  props.applyProjectLinkSelection()
}

const targetDurationLabel = computed(() => (
  props.selectedVersionPickerShot
    ? props.getMediaDurationLabel(selectedVersionPickerCurrentMediaInput.value, props.versionPickerCurrentInfo)
    : ''
))

const selectedShotVersionLabel = computed(() => {
  if (!props.selectedVersionPickerShot) return ''
  const count = props.getShotVersionCount(props.selectedVersionPickerShot)
  return count > 0 ? `V${count}` : ''
})

const shotSelectorDisplay = computed(() => {
  const shot = props.selectedVersionPickerShot
  if (!shot) return 'Pick shot'
  const idx = props.versionPickerShots.findIndex(s => (s.id || s.shot_id) === (shot.id || shot.shot_id) || s.shot_id === shot.shot_id)
  const total = props.versionPickerShots.length
  if (total <= 1 || idx < 0) return shot.shot_id
  return `${idx + 1} / ${total}`
})

function getSourceMeta(source) {
  if (source === 'project') {
    return {
      icon: '#icon-project',
      title: 'Project Files',
      hint: 'Browse files linked to this project.',
    }
  }
  return {
    icon: '#icon-cloud',
    title: 'NAS',
    hint: 'Browse network-attached storage.',
  }
}

function isMediaPickerItem(item) {
  if (!item || item.type === 'folder') return false
  return item.type === 'image' || item.type === 'video' || item.is_image || item.is_video
}

function getPickerItemIcon(item) {
  if (item?.type === 'folder') return '#icon-folder'
  if (item?.type === 'tracker') return '#icon-project'
  if (item?.type === 'page') return '#icon-layout'
  if (item?.type === 'video') return '#icon-video'
  if (item?.type === 'image') return '#icon-image'
  return '#icon-file'
}

function getPickerItemMeta(item) {
  if (!item) return ''
  if (item.type === 'folder') {
    if (item.is_workspace) return 'Workspace'
    if (item.is_linked) return 'Linked folder'
    return 'Folder'
  }
  if (item.type === 'tracker') return `${item.shot_count || 0} shots · Vue Tracker`
  if (item.type === 'page') return `${item.block_count || 0} blocks · Dashboard`
  if (item.extension) {
    const kind = item.is_video || item.type === 'video' ? 'Video' : item.is_image || item.type === 'image' ? 'Image' : item.extension.toUpperCase()
    return item.size_formatted ? `${kind} · ${item.size_formatted}` : kind
  }
  return ''
}

function getFileMetaLine(item) {
  if (!item) return ''
  const duration = props.getMediaDurationLabel(props.getPickerItemMedia(item))
  const parts = []
  if (duration) parts.push(duration)
  if (item.size_formatted) parts.push(item.size_formatted)
  if (!parts.length) {
    if (item.is_video || item.type === 'video') return 'Video'
    if (item.is_image || item.type === 'image') return 'Image'
    if (item.extension) return item.extension.toUpperCase()
  }
  return parts.join(' · ')
}
</script>

<style scoped>
/* ─── Shell ────────────────────────────────────────────── */

:global(.file-picker-modal.v-modal-md),
:global(.file-picker-modal.v-modal-lg) {
  display: flex;
  flex-direction: column;
  max-width: 700px;
  max-height: min(calc(100dvh - 48px), 780px);
  --v-modal-header-padding: 18px 20px 16px;
  --v-modal-body-padding: 16px 18px 18px;
  --v-modal-footer-padding: 12px 18px 16px;
  --v-modal-bg: color-mix(in srgb, var(--v-surface-canvas) 96%, var(--v-bg-base));
  --v-modal-header-bg: color-mix(in srgb, var(--v-surface-panel) 82%, var(--v-modal-bg));
  --v-modal-footer-bg: color-mix(in srgb, var(--v-surface-panel) 82%, var(--v-modal-bg));
  border-radius: var(--v-modal-radius);
  border-color: color-mix(in srgb, var(--v-surface-border-strong) 86%, transparent);
  box-shadow:
    0 28px 72px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.035);
  overflow: hidden;
}

:deep(.v-modal-body) {
  gap: 14px;
  scrollbar-gutter: stable;
}

:deep(.v-modal-footer) {
  min-height: 66px;
}

/* ─── Mode rail ────────────────────────────────────────── */

.fp-mode-block {
  display: grid;
  gap: 7px;
}

.fp-control-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.fp-mode-rail {
  display: flex;
  padding: 3px;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 78%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-inset) 76%, var(--v-modal-bg));
}

.fp-mode-rail :deep(.v-tabs--segmented) {
  --v-tab-height: 38px;
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
}

.fp-mode-rail :deep(.v-tab-btn) {
  font-size: var(--v-text-base);
  font-weight: 600;
  letter-spacing: 0;
}

/* ─── Target strip (current shot reference) ──────────── */

.fp-target {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-inline);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 65%, transparent);
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
}

.fp-target.is-empty {
  background: var(--v-surface-tint-strong);
  border-style: dashed;
  border-color: color-mix(in srgb, var(--v-control-border) 80%, transparent);
}

.fp-target-thumb {
  position: relative;
  width: 88px;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  background: var(--v-bg-black);
  flex: 0 0 auto;
}

.fp-target-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.fp-target-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v-text-dim);
}

.fp-target-thumb-placeholder .icon {
  width: 22px;
  height: 22px;
}

/* One badge for both layouts: the grid target and the list row render the
   same duration chip, and previously each kept its own identical copy. */
.fp-target-duration,
.fp-list-duration {
  position: absolute;
  right: 4px;
  bottom: 4px;
  height: 16px;
  padding: 0 5px;
  border-radius: var(--v-radius-sm);
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: var(--v-text-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  display: inline-flex;
  align-items: center;
}

.fp-target-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}


.fp-target-title-row {
  display: flex;
  align-items: baseline;
  gap: var(--v-space-2);
  min-width: 0;
  font-variant-numeric: tabular-nums;
}

.fp-target-title {
  font-size: var(--v-text-lg);
  font-weight: 700;
  letter-spacing: 0;
  color: var(--v-text);
  min-width: 0;
}

.fp-target-empty {
  color: var(--v-text-muted);
  font-weight: 600;
}

.fp-target-dot {
  color: var(--v-text-dim);
  opacity: 0.5;
  font-size: var(--v-text-sm);
}

.fp-target-meta {
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
}

.fp-shot-select {
  align-items: flex-end;
}

/* ─── Source selector ────────────────────────────────── */

.fp-source-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fp-source-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-width: 0;
}

.fp-source-toggle {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.fp-source-option {
  position: relative;
  min-width: 0;
  min-height: 58px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 11px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 76%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-raised) 68%, var(--v-modal-bg));
  color: var(--v-text-secondary);
  font: inherit;
  cursor: pointer;
  text-align: left;
  transition: background var(--v-transition-fast), border-color var(--v-transition-fast), color var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.fp-source-option:hover,
.fp-source-option:focus-visible {
  outline: none;
  color: var(--v-text);
  background: var(--v-surface-inline);
  border-color: color-mix(in srgb, var(--v-control-border-hover) 62%, transparent);
}

.fp-source-option.is-active {
  color: var(--v-text);
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-raised));
  border-color: color-mix(in srgb, var(--v-accent) 32%, var(--v-control-border));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 11%, transparent);
}

.fp-source-option-icon,
.fp-source-option-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.fp-source-option-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 70%, transparent);
  background: color-mix(in srgb, var(--v-control-bg) 76%, transparent);
  color: var(--v-text-muted);
}

.fp-source-option.is-active .fp-source-option-icon,
.fp-source-option.is-active .fp-source-option-check {
  color: var(--v-accent);
}

.fp-source-option-icon .icon,
.fp-source-option-check .icon {
  width: 16px;
  height: 16px;
}

.fp-source-option-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.fp-source-option-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--v-text-base);
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1;
}

.fp-source-option-hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.fp-source-option-check {
  width: 20px;
  height: 20px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent) 14%, transparent);
  opacity: 0;
}

.fp-source-option.is-active .fp-source-option-check {
  opacity: 1;
}

/* ─── Single source row ──────────────────────────────── */

.fp-source-single {
  flex-direction: row;
  align-items: center;
  gap: var(--v-space-3);
  padding: 10px 12px;
  border-radius: var(--v-radius-lg);
}

.fp-source-single-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--v-radius-md);
  border: 1px solid var(--v-control-border);
  background: var(--v-control-bg);
  color: var(--v-text-secondary);
  flex: 0 0 auto;
}

.fp-source-single-icon .icon {
  width: 16px;
  height: 16px;
}

.fp-source-single-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fp-source-single-title {
  font-size: var(--v-text-base);
  font-weight: 700;
  letter-spacing: 0;
  color: var(--v-text);
  line-height: 1.2;
}

.fp-source-single-hint {
  font-size: var(--v-text-sm);
  line-height: 1.35;
  color: var(--v-text-muted);
}

/* ─── Browser card ───────────────────────────────────── */

.fp-browser {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  gap: 0;
  padding: 0;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  border-color: color-mix(in srgb, var(--v-surface-border-soft) 82%, transparent);
  background: color-mix(in srgb, var(--v-surface-raised) 72%, var(--v-modal-bg));
  box-shadow: none;
}

.fp-browser-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--v-modal-divider);
  background: color-mix(in srgb, var(--v-surface-inset) 68%, var(--v-modal-bg));
}

.fp-browser-location {
  display: grid;
  gap: 2px;
  min-width: 0;
  flex: 1 1 auto;
}

.fp-browser-path {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.fp-browser-path-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: 0 0 auto;
  color: var(--v-text-muted);
}

.fp-browser-path-icon .icon {
  width: 14px;
  height: 14px;
}

.fp-browser-up {
  width: 26px;
  min-width: 26px;
  height: 26px;
  min-height: 26px;
  flex: 0 0 auto;
}

.fp-browser-up .icon {
  width: 13px;
  height: 13px;
}

.fp-browser-path-text {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--v-text-base);
  font-weight: 600;
  color: var(--v-text);
  letter-spacing: 0;
}

.fp-browser-guide {
  margin: 0 0 0 34px;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fp-browser-count {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: var(--v-control-pill-height-compact);
  padding: 0 7px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-control-bg) 65%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.fp-browser-filter {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  width: 210px;
  margin-top: 1px;
}

.fp-browser-filter-icon {
  position: absolute;
  left: 10px;
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
  pointer-events: none;
}

.fp-browser-filter-input {
  width: 100%;
  height: 34px;
  padding: 0 12px 0 30px;
  border-radius: var(--v-button-radius);
  border: 1px solid var(--v-control-border);
  background: var(--v-surface-inline);
  color: var(--v-text);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  transition: border-color var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.fp-browser-filter-input::placeholder {
  color: var(--v-text-muted);
}

.fp-browser-filter-input:focus {
  outline: none;
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

/* ─── List ──────────────────────────────────────────── */

.fp-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-height: 0;
  overflow-y: auto;
  margin: 0;
  padding: 5px;
  flex: 1;
}

.fp-list-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: 50px;
  padding: 0;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text);
  text-align: left;
  cursor: default;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.fp-list-row:has(> .fp-list-main) {
  grid-template-columns: minmax(0, 1fr) auto;
}

.fp-list-row:not(:has(> .fp-list-main)) {
  padding: 6px 8px;
  cursor: pointer;
}

.fp-list-row:hover,
.fp-list-row:focus-within {
  background: var(--v-bg-hover);
}

.fp-list-row:not(:has(> .fp-list-main)):focus-visible {
  outline: 2px solid var(--v-control-border-focus);
  outline-offset: -2px;
}

.fp-list-row.is-selected {
  background: color-mix(in srgb, var(--v-accent-muted) 45%, transparent);
}

.fp-list-row.is-selected:hover,
.fp-list-row.is-selected:focus-within {
  background: color-mix(in srgb, var(--v-accent-muted) 60%, transparent);
}

.fp-list-main {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
  min-height: 50px;
  padding: 6px 8px;
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.fp-list-main:focus-visible {
  outline: 2px solid var(--v-control-border-focus);
  outline-offset: -2px;
}

.fp-list-thumb {
  position: relative;
  width: 88px;
  aspect-ratio: 16 / 9;
  border-radius: var(--v-radius-md);
  overflow: hidden;
  background: var(--v-bg-black);
  flex: 0 0 auto;
}

.fp-list-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}


.fp-list-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
  flex: 0 0 auto;
}

.fp-list-icon .icon {
  width: 16px;
  height: 16px;
}

.fp-list-row.is-folder .fp-list-icon {
  color: var(--v-text-secondary);
}

.fp-list-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fp-list-name {
  font-size: var(--v-text-md);
  font-weight: 600;
  letter-spacing: 0;
  color: var(--v-text);
}

.fp-list-meta {
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
  font-variant-numeric: tabular-nums;
}

.fp-list-trail {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
}

.fp-list-chevron {
  width: 14px;
  height: 14px;
  color: var(--v-text-dim);
  transform: rotate(-90deg);
  transition: color var(--v-transition-fast);
}

.fp-list-row:hover .fp-list-chevron,
.fp-list-row:focus-within .fp-list-chevron {
  color: var(--v-text-muted);
}

.fp-list-check {
  width: 16px;
  height: 16px;
  color: var(--v-accent);
}

.fp-list-checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--v-radius-sm);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 84%, transparent);
  background: color-mix(in srgb, var(--v-control-bg) 68%, transparent);
  color: var(--v-on-accent);
  flex: 0 0 auto;
  transition: background var(--v-transition-fast), border-color var(--v-transition-fast), color var(--v-transition-fast);
}

.fp-list-checkbox .icon {
  width: 14px;
  height: 14px;
}

.fp-list-checkbox.is-checked {
  border-color: var(--v-accent);
  background: var(--v-accent);
  color: var(--v-on-accent);
}

.fp-list-action {
  flex: 0 0 auto;
  height: 32px;
  min-height: 32px;
  padding: 0 12px;
  margin-right: 7px;
  gap: 6px;
  font-size: var(--v-text-sm);
  font-weight: 600;
  color: var(--v-text-secondary);
  border-radius: var(--v-button-radius);
}

.fp-list-action .icon {
  width: 12px;
  height: 12px;
}

.fp-list-row:hover .fp-list-action {
  color: var(--v-text);
}

.fp-list-action:hover {
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
}

/* ─── Empty state ─────────────────────────────────── */

.fp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-2);
  padding: 40px 20px;
  color: var(--v-text-muted);
  text-align: center;
}

.fp-empty .icon {
  width: 22px;
  height: 22px;
  color: var(--v-text-dim);
  opacity: 0.65;
}

.fp-empty p {
  margin: 0;
  font-size: var(--v-text-base);
  line-height: 1.4;
}

/* ─── Load more ───────────────────────────────────── */

.fp-load-more {
  display: flex;
  justify-content: center;
  padding: 8px 10px;
  border-top: 1px solid var(--v-modal-divider);
}

/* ─── Footer ─────────────────────────────────────── */

.fp-footer {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fp-footer-status {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
  line-height: 1.35;
}

.fp-footer-status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--v-text-dim);
  flex: 0 0 auto;
  transition: color var(--v-transition-fast);
}

.fp-footer-status-icon .icon {
  width: 14px;
  height: 14px;
}

.fp-footer-status.is-ready {
  color: var(--v-text);
}

.fp-footer-status.is-ready .fp-footer-status-icon {
  color: var(--v-accent);
}

.fp-footer-status-text {
  min-width: 0;
}

.fp-footer-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
}

.fp-footer-changelog {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-bg-field);
  transition: border-color var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.fp-footer-changelog:focus-within {
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.fp-footer-changelog-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: var(--v-font);
  font-size: var(--v-text-base);
  outline: none;
}

.fp-footer-changelog-input::placeholder {
  color: var(--v-text-muted);
}

.fp-footer-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
}

.fp-footer-compact {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

/* ─── Mobile ───────────────────────────────────────── */

@media (max-width: 768px) {
  :global(.file-picker-modal.v-modal-md.is-mobile-full-height),
  :global(.file-picker-modal.v-modal-lg.is-mobile-full-height) {
    min-height: calc(100dvh - 8px);
    max-height: calc(100dvh - 8px);
    --v-modal-header-padding: 18px 16px 16px;
    --v-modal-body-padding: 14px 14px 18px;
    --v-modal-footer-padding: 12px 14px max(14px, env(safe-area-inset-bottom));
  }

  :deep(.v-modal-body) {
    gap: 12px;
    scrollbar-gutter: auto;
  }

  :deep(.v-modal-footer) {
    min-height: 76px;
  }

  .fp-control-label {
    display: none;
  }

  .fp-mode-rail :deep(.v-tabs--segmented) {
    --v-tab-height: 44px;
  }

  .fp-target {
    grid-template-columns: 72px minmax(0, 1fr) auto;
    grid-template-areas:
      'thumb copy select';
    gap: 10px;
    padding: var(--v-space-2);
  }

  .fp-target-thumb {
    width: 72px;
    grid-area: thumb;
  }

  .fp-target-copy {
    grid-area: copy;
  }

  .fp-shot-select {
    grid-area: select;
    width: 88px;
    min-height: 36px;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    padding: 0 10px;
  }

  .fp-shot-select .v-labeled-select-eyebrow {
    display: none;
  }

  .fp-shot-select .v-labeled-select-text {
    font-size: var(--v-text-base);
  }

  .fp-source-section {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .fp-source-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .fp-source-head .v-modal-section-copy {
    margin-top: 2px;
  }

  .fp-source-toggle {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    gap: 6px;
    padding: 0;
  }

  .fp-source-option {
    height: 48px;
    min-height: 48px;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 8px;
    padding: 0 10px;
    border-radius: var(--v-radius-md);
  }

  .fp-source-option:hover,
  .fp-source-option:focus-visible {
    background: color-mix(in srgb, var(--v-surface-inline-pressed) 48%, transparent);
    border-color: color-mix(in srgb, var(--v-control-border-hover) 62%, transparent);
  }

  .fp-source-option.is-active {
    background: color-mix(in srgb, var(--v-accent) 10%, var(--v-surface-inline-pressed));
    border-color: color-mix(in srgb, var(--v-accent) 28%, var(--v-control-border));
  }

  .fp-source-option-icon {
    width: 24px;
    height: 24px;
    border: 0;
    background: transparent;
  }

  .fp-source-option-hint {
    display: none;
  }

  .fp-source-option-check {
    width: 18px;
    height: 18px;
  }

  .fp-source-option-title {
    font-size: var(--v-text-base);
  }

  .fp-browser-toolbar {
    display: grid;
    gap: 10px;
    padding: 10px;
  }

  .fp-browser-guide {
    margin-left: 34px;
    white-space: normal;
  }

  .fp-browser-filter {
    width: 100%;
    margin: 0;
  }

  .fp-browser-filter-input {
    height: 44px;
    border-color: var(--v-control-border);
    background: var(--v-surface-inline);
    font-size: var(--v-text-base);
    padding-left: 34px;
  }

  .fp-browser-filter-icon {
    left: 12px;
    width: 14px;
    height: 14px;
  }

  .fp-list-row {
    min-height: 56px;
    gap: 4px;
  }

  .fp-list-main {
    min-height: 56px;
    gap: 10px;
    padding: 7px 8px;
  }

  .fp-list-thumb {
    width: 80px;
  }

  .fp-list-icon {
    width: 32px;
    height: 32px;
  }

  .fp-list-name {
    font-size: var(--v-text-md);
  }

  .fp-list-action {
    min-width: 94px;
    height: 44px;
    min-height: 44px;
    margin-right: 6px;
    padding: 0 10px;
    border-radius: var(--v-radius-md);
  }

  .fp-footer-row {
    grid-template-columns: 1fr;
    gap: var(--v-space-2);
  }

  .fp-footer-changelog {
    height: 44px;
  }

  .fp-footer-actions {
    display: grid;
    grid-template-columns: 0.8fr 1.2fr;
    gap: var(--v-space-2);
  }

  .fp-footer-compact {
    flex-direction: column;
    align-items: stretch;
  }

  .fp-footer-actions .v-btn {
    width: 100%;
    min-height: 44px;
    justify-content: center;
  }
}
</style>
