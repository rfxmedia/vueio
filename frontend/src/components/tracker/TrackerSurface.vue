<template>
  <div class="shot-tracker" :class="{ 'is-scrolled': toolbarPinned }">
    <TrackerDeliveryMode
      v-if="showDeliveryIntro"
      :project="currentProject"
      :current-tracker="currentTracker"
      :team-name="deliveryTeamName"
      :delivery-message="deliveryMessage"
      :delivery-notes="deliveryNotes"
      :delivery-links="deliveryLinks"
      :delivery-logo-url="deliveryLogoUrl"
      :project-thumbnail-url="projectThumbnailUrl"
      :can-download-tracker-latest="canDownloadTrackerLatest"
      :tracker-download-busy="trackerDownloadBusy"
      :tracker-download-progress="trackerDownloadProgress"
      :download-tracker-latest-versions="downloadTrackerLatestVersions"
      @view-tracker="showDeliveryIntro = false"
    />

    <div
      v-else
      class="tracker-surface-main"
      @dragenter="handleProjectDragEnter"
      @dragover="handleProjectDragOver"
      @dragleave="handleProjectDragLeave"
      @drop="handleProjectDrop"
    >
      <div ref="toolbarSentinelRef" class="tracker-toolbar-sentinel" aria-hidden="true"></div>

      <TrackerToolbar
        :can-add-shots="canAddShots"
        :can-add-versions="canAddVersions"
        :can-view-tracker-details="canViewTrackerDetails"
        :clear-tracker-filters="clearTrackerFilters"
        :has-tracker-filters="hasTrackerFilters"
        :is-mobile="isMobile"
        :open-shot-import-picker="openShotImportPicker"
        :show-tracker-details="showTrackerDetails"
        :toggle-tracker-details="toggleTrackerDetails"
        :toggle-tracker-filter-value="toggleTrackerFilterValue"
        :tracker-active-filter-count="trackerActiveFilterCount"
        :tracker-filter-groups="trackerFilterGroups"
        :tracker-filters="trackerFilters"
        :tracker-sort-key="trackerSortKey"
        :tracker-sort-dir="trackerSortDir"
        :toggle-tracker-sort="toggleTrackerSort"
        :tracker-group-key="trackerGroupKey"
        :toggle-tracker-group="toggleTrackerGroup"
        :selection-enabled="selectionEnabled"
        :can-bulk-update-status="canBulkUpdateStatus"
        :can-bulk-update-category="canBulkUpdateCategory"
        :can-bulk-update-assignee="canBulkUpdateAssignee"
        :can-archive-shots="canArchiveShots"
        :can-delete-shots="canDeleteShots"
        :can-download-tracker-latest="canDownloadTrackerLatest"
        :can-download-selected-tracker-latest="canDownloadSelectedTrackerLatest"
        :selected-shot-count="selectedShotCount"
        :selected-archived-shot-count="selectedArchivedShotCount"
        :bulk-status-options="bulkStatusOptions"
        :bulk-category-options="bulkCategoryOptions"
        :bulk-assignee-options="bulkAssigneeOptions"
        :bulk-action-busy="bulkActionBusy"
        :tracker-download-busy="trackerDownloadBusy"
        :tracker-download-progress="trackerDownloadProgress"
        :tracker-display-mode="trackerDisplayMode"
        :set-tracker-display-mode="setTrackerDisplayMode"
        :clear-selected-shots="clearSelectedShots"
        :clear-archived-selected-shots="clearArchivedSelectedShots"
        :download-tracker-latest-versions="downloadTrackerLatestVersions"
        :download-selected-tracker-latest-versions="downloadSelectedTrackerLatestVersions"
        :bulk-update-shot-status="bulkUpdateShotStatus"
        :bulk-update-shot-category="bulkUpdateShotCategory"
        :bulk-update-shot-assignee="bulkUpdateShotAssignee"
        :bulk-update-archived-shot-status="bulkUpdateArchivedShotStatus"
        :bulk-update-archived-shot-category="bulkUpdateArchivedShotCategory"
        :bulk-update-archived-shot-assignee="bulkUpdateArchivedShotAssignee"
        :bulk-archive-shots="bulkArchiveShots"
        :bulk-restore-archived-shots="bulkRestoreArchivedShots"
        :bulk-delete-shots="bulkDeleteShots"
      />

      <div class="tracker-surface-table">
        <TrackerTableView
          :tracker-display-mode="effectiveTrackerDisplayMode"
          :version-drop-shot-ref="projectDropTargetShotRef"
          :version-drop-blocked-reason="projectVersionDropBlockedReason"
          :version-drop-item-name="projectVersionDropItemName"
        />
      </div>

      <Transition name="v-overlay-fade">
        <div
          v-if="projectDragActive && !projectDropTargetShot"
          class="v-drop-overlay tracker-project-drop"
          :class="{ 'is-blocked': Boolean(projectShotImportBlockedReason) }"
          role="status"
          aria-live="polite"
        >
          <div class="v-drop-overlay-inner tracker-project-drop__inner">
            <span class="tracker-project-drop__icon" aria-hidden="true">
              <svg class="icon"><use :href="projectShotImportBlockedReason ? '#icon-close' : '#icon-project'"/></svg>
            </span>
            <strong>{{ projectDropTitle }}</strong>
            <span class="v-drop-overlay-subtitle">{{ projectDropSubtitle }}</span>
          </div>
        </div>
      </Transition>
    </div>

    <Transition name="v-drawer-slide-end">
      <div
        v-if="showDesktopDetails"
        class="v-inspector-overlay"
        :class="{ 'has-shell-sidebar': !shareMode }"
        @click.self="showTrackerDetails = false"
      >
        <aside class="v-inspector-rail is-overlay tracker-details-rail">
          <TrackerDetailsPanel
            :current-tracker="currentTracker"
            :current-user-id="currentUserId"
            :tracker-stats="trackerStats"
            :tracker-activity="trackerActivity"
            :tracker-activity-loading="trackerActivityLoading"
            :tracker-activity-error="trackerActivityError"
            :tracker-activity-has-more="trackerActivityHasMore"
            :activity-restore-busy-id="activityRestoreBusyId"
            :activity-restore-preview="activityRestorePreview"
            :activity-restore-preview-busy-id="activityRestorePreviewBusyId"
            :can-restore-history="canRestoreTrackerHistory"
            :tracker-views="trackerViews"
            :tracker-viewers-active="trackerViewersActive"
            :tracker-views-loading="trackerViewsLoading"
            :tracker-views-error="trackerViewsError"
            :tracker-views-has-more="trackerViewsHasMore"
            :is-admin="isAdmin"
            :is-mobile="false"
            :load-more-tracker-activity="loadMoreTrackerActivity"
            :retry-tracker-activity="retryTrackerActivity"
            :prepare-tracker-history-restore="prepareTrackerHistoryRestore"
            :close-tracker-history-restore="closeTrackerHistoryRestore"
            :restore-tracker-activity="restoreTrackerActivity"
            :load-tracker-views="loadTrackerViews"
            :load-more-tracker-views="loadMoreTrackerViews"
            closeable
            @close="showTrackerDetails = false"
          />
        </aside>
      </div>
    </Transition>

    <VModal
      v-model="showMobileDetails"
      size="lg"
      presentation="sheet"
      :mobile-full-height="true"
      class="tracker-details-sheet-modal"
      aria-label="Tracker details"
    >
      <TrackerDetailsPanel
        :current-tracker="currentTracker"
        :current-user-id="currentUserId"
        :tracker-stats="trackerStats"
        :tracker-activity="trackerActivity"
        :tracker-activity-loading="trackerActivityLoading"
        :tracker-activity-error="trackerActivityError"
        :tracker-activity-has-more="trackerActivityHasMore"
        :activity-restore-busy-id="activityRestoreBusyId"
        :activity-restore-preview="activityRestorePreview"
        :activity-restore-preview-busy-id="activityRestorePreviewBusyId"
        :can-restore-history="canRestoreTrackerHistory"
        :tracker-views="trackerViews"
        :tracker-viewers-active="trackerViewersActive"
        :tracker-views-loading="trackerViewsLoading"
        :tracker-views-error="trackerViewsError"
        :tracker-views-has-more="trackerViewsHasMore"
        :is-admin="isAdmin"
        :is-mobile="true"
        :load-more-tracker-activity="loadMoreTrackerActivity"
        :retry-tracker-activity="retryTrackerActivity"
        :prepare-tracker-history-restore="prepareTrackerHistoryRestore"
        :close-tracker-history-restore="closeTrackerHistoryRestore"
        :restore-tracker-activity="restoreTrackerActivity"
        :load-tracker-views="loadTrackerViews"
        :load-more-tracker-views="loadMoreTrackerViews"
        closeable
        @close="showTrackerDetails = false"
      />
    </VModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { VModal } from '../primitives'
import TrackerDetailsPanel from './TrackerDetailsPanel.vue'
import TrackerDeliveryMode from './TrackerDeliveryMode.vue'
import TrackerToolbar from './TrackerToolbar.vue'
import TrackerTableView from './TrackerTableView.vue'
import { hasProjectItemDrag, readProjectItemDrag } from '../../lib/projectItemDrag'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useTrackerStore } from '../../ownership/tracker'
import { notify } from '../../utils/toasts'

const {
  activityRestorePreview,
  activityRestorePreviewBusyId,
  activityRestoreBusyId,
  bulkActionBusy,
  bulkArchiveShots,
  bulkAssigneeOptions,
  bulkCategoryOptions,
  bulkDeleteShots,
  bulkRestoreArchivedShots,
  bulkStatusOptions,
  bulkUpdateArchivedShotAssignee,
  bulkUpdateArchivedShotCategory,
  bulkUpdateArchivedShotStatus,
  bulkUpdateShotAssignee,
  bulkUpdateShotCategory,
  bulkUpdateShotStatus,
  canAddShots,
  canAddVersions,
  canBulkUpdateAssignee,
  canBulkUpdateCategory,
  canBulkUpdateStatus,
  canArchiveShots,
  canDeleteShots,
  canDownloadSelectedTrackerLatest,
  canDownloadTrackerLatest,
  canViewTrackerDetails,
  canRestoreTrackerHistory,
  clearArchivedSelectedShots,
  clearSelectedShots,
  clearTrackerFilters,
  closeTrackerHistoryRestore,
  currentProject,
  currentTracker,
  currentUserId,
  deliveryLinks,
  deliveryLogoUrl,
  deliveryMessage,
  deliveryNotes,
  deliveryTeamName,
  downloadSelectedTrackerLatestVersions,
  downloadTrackerLatestVersions,
  hasTrackerFilters,
  isMobile,
  isAdmin,
  heartbeatTrackerViewSession,
  loadMoreTrackerActivity,
  loadMoreTrackerViews,
  loadTrackerActivity,
  loadTrackerViews,
  openShotImportPicker,
  prepareTrackerHistoryRestore,
  projectThumbnailUrl,
  selectedArchivedShotCount,
  selectedShotCount,
  selectionEnabled,
  shareMode,
  showDeliveryMode,
  toggleTrackerFilterValue,
  toggleTrackerGroup,
  toggleTrackerSort,
  trackerActiveFilterCount,
  trackerActivity,
  trackerActivityError,
  trackerActivityHasMore,
  trackerActivityLoading,
  trackerViews,
  trackerViewersActive,
  trackerViewsError,
  trackerViewsHasMore,
  trackerViewsLoading,
  trackerDownloadBusy,
  trackerDownloadProgress,
  trackerFilterGroups,
  trackerFilters,
  trackerGroupKey,
  trackerSortDir,
  trackerSortKey,
  trackerStats,
  startTrackerViewSession,
  stopTrackerViewSession,
  restoreTrackerActivity,
} = useTrackerStore()

const retryTrackerActivity = () => loadTrackerActivity(
  currentTracker.value?.id || currentTracker.value?.slug || currentTracker.value?.name || '',
)

const { picker } = useFileBrowserStore()

const showTrackerDetails = ref(false)
const showDeliveryIntro = ref(false)
const trackerDisplayMode = ref('list')
const projectDragActive = ref(false)
const projectDragItemCount = ref(0)
const projectDragProjectId = ref('')
const projectDragItems = ref([])
const projectDropTargetShot = ref(null)
let projectDragDepth = 0

// A sentinel above the sticky toolbar tells us when the list has scrolled
// underneath it, so the toolbar's separator only appears once it earns one.
const toolbarSentinelRef = ref(null)
const toolbarPinned = ref(false)
let toolbarScroller = null
let trackerViewHeartbeatTimer = null

const TRACKER_VIEW_HEARTBEAT_MS = 45_000

function heartbeatIfVisible() {
  if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
  void heartbeatTrackerViewSession()
}

function beginTrackerViewPresence() {
  stopTrackerViewSession()
  void startTrackerViewSession()
  if (trackerViewHeartbeatTimer !== null) window.clearInterval(trackerViewHeartbeatTimer)
  trackerViewHeartbeatTimer = window.setInterval(heartbeatIfVisible, TRACKER_VIEW_HEARTBEAT_MS)
}

function endTrackerViewPresence() {
  if (trackerViewHeartbeatTimer !== null) {
    window.clearInterval(trackerViewHeartbeatTimer)
    trackerViewHeartbeatTimer = null
  }
  stopTrackerViewSession()
}

function handleTrackerViewVisibility() {
  if (document.visibilityState === 'visible') heartbeatIfVisible()
}

function findScrollParent(node) {
  let current = node?.parentElement
  while (current) {
    const overflowY = getComputedStyle(current).overflowY
    if (overflowY === 'auto' || overflowY === 'scroll') return current
    current = current.parentElement
  }
  return null
}

function syncToolbarPinned() {
  const sentinel = toolbarSentinelRef.value
  if (!sentinel || !toolbarScroller) return
  toolbarPinned.value = sentinel.getBoundingClientRect().top <= toolbarScroller.getBoundingClientRect().top
}

function detachToolbarScroll() {
  toolbarScroller?.removeEventListener('scroll', syncToolbarPinned)
  toolbarScroller = null
}

watch(
  toolbarSentinelRef,
  (sentinel) => {
    detachToolbarScroll()
    if (!sentinel) {
      toolbarPinned.value = false
      return
    }
    toolbarScroller = findScrollParent(sentinel)
    toolbarScroller?.addEventListener('scroll', syncToolbarPinned, { passive: true })
    syncToolbarPinned()
  },
  { flush: 'post', immediate: true },
)

onBeforeUnmount(detachToolbarScroll)

onMounted(() => {
  beginTrackerViewPresence()
  document.addEventListener('visibilitychange', handleTrackerViewVisibility)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleTrackerViewVisibility)
  endTrackerViewPresence()
  resetProjectDrag()
})

const showDesktopDetails = computed(() => showTrackerDetails.value && canViewTrackerDetails.value !== false && !isMobile.value)
const effectiveTrackerDisplayMode = computed(() => (isMobile.value ? 'list' : trackerDisplayMode.value))
const projectShotImportBlockedReason = computed(() => {
  if (!canAddShots.value) return 'You do not have permission to add shots to this tracker.'
  if (picker.shotImportApplyBusy.value || picker.versionPickerApplyBusy.value) return 'Another tracker update is already in progress.'
  if (projectDragProjectId.value && projectDragProjectId.value !== String(currentProject.value?.id || '')) {
    return 'These items belong to a different project.'
  }
  return ''
})
const projectVersionDropBlockedReason = computed(() => {
  if (!projectDropTargetShot.value) return ''
  if (!canAddVersions.value) return 'You do not have permission to add versions to this tracker.'
  if (picker.versionPickerApplyBusy.value || picker.shotImportApplyBusy.value) return 'Another tracker update is already in progress.'
  if (projectDragProjectId.value && projectDragProjectId.value !== String(currentProject.value?.id || '')) {
    return 'This file belongs to a different project.'
  }
  if (projectDragItems.value.length !== 1) return 'Drop exactly one image or video onto a shot.'
  const item = projectDragItems.value[0]
  if (item?.type === 'folder' || !picker.isTrackerImportMediaItem(item)) return 'Only image or video files can become versions.'
  return ''
})
const projectDropTargetShotRef = computed(() => getShotRef(projectDropTargetShot.value))
const projectVersionDropItemName = computed(() => (
  projectDragItems.value.length === 1 ? projectDragItems.value[0]?.name || '' : ''
))
const projectDropTitle = computed(() => {
  if (projectShotImportBlockedReason.value) return 'Cannot import these items here'
  if (projectDragItemCount.value === 1) return 'Import 1 file'
  if (projectDragItemCount.value > 1) return `Import ${projectDragItemCount.value} files`
  return 'Import files into tracker'
})
const projectDropSubtitle = computed(() => (
  projectShotImportBlockedReason.value || 'Release here to create shots, or hover a shot to add one new version.'
))
const showMobileDetails = computed({
  get: () => showTrackerDetails.value && canViewTrackerDetails.value !== false && isMobile.value,
  set: (value) => {
    showTrackerDetails.value = value
  },
})

function toggleTrackerDetails() {
  if (canViewTrackerDetails.value === false) return
  showTrackerDetails.value = !showTrackerDetails.value
}

function setTrackerDisplayMode(mode) {
  trackerDisplayMode.value = mode === 'grid' ? 'grid' : 'list'
}

function inspectProjectDrag(event) {
  if (!hasProjectItemDrag(event?.dataTransfer)) return null
  return readProjectItemDrag(event.dataTransfer)
}

function syncProjectDrag(payload) {
  projectDragProjectId.value = payload?.projectId || ''
  projectDragItems.value = payload?.items || []
  projectDragItemCount.value = projectDragItems.value.filter(item => item.type === 'file').length
}

function getShotRef(shot) {
  return String(shot?.id || shot?._originalId || shot?.shot_id || shot?.shot_code || '')
}

function findProjectDropShot(event) {
  const card = event?.target?.closest?.('[data-tracker-shot-id]')
  if (!card || !event?.currentTarget?.contains?.(card)) return null
  const targetRef = String(card.dataset.trackerShotId || card.dataset.trackerShotCode || '')
  if (!targetRef) return null
  return (currentTracker.value?.shots || []).find(shot => (
    getShotRef(shot) === targetRef || String(shot?.shot_id || shot?.shot_code || '') === targetRef
  )) || null
}

function syncProjectDropTarget(event) {
  projectDropTargetShot.value = findProjectDropShot(event)
}

function resetProjectDrag() {
  projectDragDepth = 0
  projectDragActive.value = false
  projectDragItemCount.value = 0
  projectDragProjectId.value = ''
  projectDragItems.value = []
  projectDropTargetShot.value = null
}

function handleProjectDragEnter(event) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  projectDragDepth += 1
  projectDragActive.value = true
  syncProjectDrag(inspectProjectDrag(event))
  syncProjectDropTarget(event)
}

function handleProjectDragOver(event) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  if (!projectDragActive.value) projectDragActive.value = true
  if (!projectDragProjectId.value) syncProjectDrag(inspectProjectDrag(event))
  syncProjectDropTarget(event)
  const blockedReason = projectDropTargetShot.value
    ? projectVersionDropBlockedReason.value
    : projectShotImportBlockedReason.value
  event.dataTransfer.dropEffect = blockedReason ? 'none' : 'copy'
}

function handleProjectDragLeave(event) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.stopPropagation()
  projectDragDepth = Math.max(0, projectDragDepth - 1)
  if (projectDragDepth === 0) resetProjectDrag()
}

async function handleProjectDrop(event) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  const payload = inspectProjectDrag(event)
  syncProjectDrag(payload)
  projectDropTargetShot.value = findProjectDropShot(event)
  const targetShot = projectDropTargetShot.value
  const blockedReason = targetShot
    ? projectVersionDropBlockedReason.value
    : projectShotImportBlockedReason.value
  resetProjectDrag()
  if (!payload) {
    notify('Those sidebar items could not be read. Try dragging them again.')
    return
  }
  if (blockedReason) {
    notify(blockedReason)
    return
  }
  if (targetShot) {
    await picker.addProjectItemVersion(targetShot, payload.items[0])
    return
  }
  await picker.importProjectItems(payload.items)
}

watch(
  isMobile,
  (mobile) => {
    if (mobile) trackerDisplayMode.value = 'list'
  },
)

watch(
  () => currentTracker.value?.id,
  (trackerId, previousTrackerId) => {
    showTrackerDetails.value = false
    showDeliveryIntro.value = showDeliveryMode.value === true
    if (trackerId && previousTrackerId && trackerId !== previousTrackerId) beginTrackerViewPresence()
  },
)

watch(
  showDeliveryMode,
  (enabled) => {
    showDeliveryIntro.value = enabled === true
  },
  { immediate: true },
)

watch(
  canViewTrackerDetails,
  (canView) => {
    if (canView === false) showTrackerDetails.value = false
  },
)
</script>

<style>
.shot-tracker {
  /* One page gutter shared by the header bar, the toolbar and the shot list. */
  --tracker-page-gutter: 18px;
  /* Height of the pinned toolbar — tag headings park directly beneath it. */
  --tracker-toolbar-height: 53px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  overflow: visible;
  position: relative;
}

.tracker-surface-main,
.tracker-surface-table {
  min-height: 0;
}

.v-inspector-rail.is-overlay.tracker-details-rail {
  width: min(680px, 66vw);
  min-width: min(520px, 66vw);
  max-width: min(680px, 66vw);
  padding: 0;
}

.tracker-details-sheet-modal .v-modal-body {
  min-height: 0;
  padding: 0;
}

.tracker-surface-main {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
}

.tracker-project-drop {
  z-index: 12;
  border-color: color-mix(in srgb, var(--v-accent) 68%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-bg-base) 66%, transparent);
}

.tracker-project-drop__inner {
  min-width: min(320px, calc(100% - 32px));
  padding: var(--v-space-5);
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
  color: var(--v-text);
  text-align: center;
}

.tracker-project-drop__icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  margin-bottom: var(--v-space-1);
  border: 1px solid color-mix(in srgb, var(--v-accent) 24%, var(--v-control-border));
  border-radius: var(--v-radius-md);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.tracker-project-drop__icon .icon {
  width: 18px;
  height: 18px;
}

.tracker-project-drop.is-blocked {
  border-color: var(--v-danger-border);
}

.tracker-project-drop.is-blocked .tracker-project-drop__icon {
  border-color: var(--v-danger-border);
  background: var(--v-danger-bg);
  color: var(--v-danger);
}

.tracker-surface-table {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 1px rather than 0 — IntersectionObserver never reports a zero-area target. */
.tracker-toolbar-sentinel {
  height: 1px;
  margin-bottom: -1px;
  flex: 0 0 auto;
  pointer-events: none;
}

@media (max-width: 768px) {
  .shot-tracker {
    --tracker-page-gutter: 12px;
    --tracker-toolbar-height: 55px;
  }
}

@media (max-width: 767px) {
  .shot-tracker .v-inspector-rail {
    display: none;
  }
}
</style>
