<template>
  <MediaVersionSwitcher
    v-if="showTrackerViewerVersionSwitcher"
    class="v-media-topbar-version-switcher"
    :is-mobile="isMobile"
    :open="trackerViewerVersionSwitcherOpen"
    :shot="currentTrackerViewerShot"
    :versions="currentTrackerViewerVersionsDescending"
    :current-media="currentMedia"
    :current-version-label="currentTrackerViewerVersionLabel"
    :keyboard-shortcuts="true"
    :can-add-versions="canAddVersions"
    :can-delete-versions="canDeleteShots"
    :can-download-versions="showShotDownloads"
    :can-compare-versions="canCompareTrackerViewerVersions"
    :publication-controls-enabled="publicationControlsEnabled"
    :update-version-publication="updateCurrentTrackerViewerVersionPublication"
    :share-mode="shareMode"
    :get-thumbnail-url="getThumbnailUrl"
    :get-media-duration-label="getMediaDurationLabel"
    :fetch-batch-media-info="fetchBatchMediaInfo"
    :format-version-label="formatTrackerVersionLabel"
    :format-version-date-short="formatVersionDateShort"
    @toggle="toggleTrackerViewerVersionSwitcher"
    @close="dismissTrackerViewerVersionSwitcher"
    @select-version="selectTrackerViewerVersion"
    @download-version="downloadTrackerViewerVersion"
    @delete-version="deleteTrackerViewerVersion"
    @compare-versions="startTrackerVersionCompare"
    @add-version="openViewerVersionUpload"
  />

  <TrackerInlineSelect
    v-if="showTrackerViewerStatusControl && !isMobile"
    class="v-media-topbar-status"
    tone="status"
    :label="currentTrackerViewerStatusOption.label"
    :accent="getTrackerStatusColor(currentTrackerViewerShot.status)"
    :accent-text="getTrackerStatusTextColor(currentTrackerViewerShot.status)"
    :interactive="true"
    :open="showStatusPicker === currentTrackerViewerShot.shot_id"
    :flip-up="false"
    @trigger="toggleShotStatusPicker($event, currentTrackerViewerShot.shot_id)"
    @close="showStatusPicker = null"
  >
    <template #leading>
      <span
        class="v-status-dot"
        :style="{ backgroundColor: currentTrackerViewerStatusOption.color }"
      ></span>
    </template>
    <template #menu>
      <div class="tracker-select-list">
        <button
          v-for="option in trackerStatusOptions"
          :key="option.value"
          class="v-dropdown-item tracker-select-option"
          :class="{ active: currentTrackerViewerShot.status === option.value }"
          type="button"
          role="menuitemradio"
          :aria-checked="currentTrackerViewerShot.status === option.value ? 'true' : 'false'"
          @click="selectStatus(currentTrackerViewerShot, option.value)"
        >
          <span
            class="v-status-dot"
            :style="{ backgroundColor: option.color }"
          ></span>
          <span class="tracker-select-option-label">{{ option.label }}</span>
          <svg v-if="currentTrackerViewerShot.status === option.value" class="icon tracker-select-check"><use href="#icon-check" /></svg>
        </button>
      </div>
    </template>
  </TrackerInlineSelect>

  <TrackerTagSelect
    v-if="showTrackerViewerStatusControl && !isMobile"
    class="v-media-topbar-tag v-media-topbar-secondary"
    :shot="currentTrackerViewerShot"
  />

  <TrackerAssigneeSelect
    v-if="showTrackerViewerStatusControl && showShotAssignees && !isMobile"
    class="v-media-topbar-assignee v-media-topbar-secondary"
    :shot="currentTrackerViewerShot"
  />
</template>

<script setup>
import MediaVersionSwitcher from '../media/MediaVersionSwitcher.vue'
import { getTrackerStatusColor, getTrackerStatusTextColor } from '../../lib/trackerCatalogs'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useTrackerStore } from '../../ownership/tracker'
import { useViewerStore } from '../../ownership/viewer'
import TrackerAssigneeSelect from './TrackerAssigneeSelect.vue'
import TrackerInlineSelect from './TrackerInlineSelect.vue'
import TrackerTagSelect from './TrackerTagSelect.vue'

const {
  currentTrackerViewerShot,
  currentTrackerViewerVersionsDescending,
  currentTrackerViewerVersionLabel,
  currentTrackerViewerStatusOption,
  trackerViewerVersionSwitcherOpen,
  showTrackerViewerVersionSwitcher,
  showTrackerViewerStatusControl,
  canCompareTrackerViewerVersions,
  trackerStatusOptions,
  showStatusPicker,
  showShotAssignees,
  publicationControlsEnabled,
  getThumbnailUrl,
  getMediaDurationLabel,
  fetchBatchMediaInfo,
  formatTrackerVersionLabel,
  formatVersionDateShort,
  toggleTrackerViewerVersionSwitcher,
  dismissTrackerViewerVersionSwitcher,
  selectTrackerViewerVersion,
  downloadTrackerViewerVersion,
  deleteTrackerViewerVersion,
  updateCurrentTrackerViewerVersionPublication,
  startTrackerVersionCompare,
  openViewerVersionUpload,
  toggleShotStatusPicker,
  selectStatus,
} = useTrackerStore()

const {
  canAddVersions,
  canDeleteShots,
  showShotDownloads,
} = useSessionAuthStore()

const { shareMode } = useShareAccessContext()
const viewer = useViewerStore()
const { currentMedia } = viewer.media.state
const { isMobile } = viewer.presentation
</script>

<style scoped>
/* One width for all three, so they read as a set the way the tracker row's
   status/tag/assignee columns do. */
.v-media-topbar-status,
.v-media-topbar-tag,
.v-media-topbar-assignee {
  width: 144px;
  flex: 0 0 auto;
}

.v-media-topbar-status :deep(.tracker-inline-select-trigger),
.v-media-topbar-tag :deep(.tracker-inline-select-trigger),
.v-media-topbar-assignee :deep(.tracker-inline-select-trigger) {
  min-height: var(--v-control-pill-height-compact);
  padding: 0 10px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-sm);
}

@media (max-width: 1200px) {
  .v-media-topbar-status,
  .v-media-topbar-tag,
  .v-media-topbar-assignee {
    width: 128px;
  }
}

@media (max-width: 960px) {
  .v-media-topbar-secondary {
    display: none;
  }
}
</style>
