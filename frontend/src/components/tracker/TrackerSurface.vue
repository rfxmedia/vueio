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

    <div v-else class="tracker-surface-main">
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
        :selection-enabled="selectionEnabled"
        :can-bulk-update-status="canBulkUpdateStatus"
        :can-bulk-update-category="canBulkUpdateCategory"
        :can-bulk-update-assignee="canBulkUpdateAssignee"
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
        :bulk-restore-archived-shots="bulkRestoreArchivedShots"
        :bulk-delete-shots="bulkDeleteShots"
      />

      <div class="tracker-surface-table">
        <TrackerTableView
          :tracker-display-mode="effectiveTrackerDisplayMode"
        />
      </div>
    </div>

    <Transition name="v-drawer-slide-end">
      <div
        v-if="showDesktopDetails"
        class="v-inspector-overlay"
        :class="{ 'has-shell-sidebar': !shareMode }"
        @click.self="showTrackerDetails = false"
      >
        <aside class="v-inspector-rail is-overlay">
          <TrackerDetailsPanel
            :current-tracker="currentTracker"
            :current-user-id="currentUserId"
            :tracker-stats="trackerStats"
            :tracker-activity="trackerActivity"
            :tracker-activity-loading="trackerActivityLoading"
            :tracker-activity-has-more="trackerActivityHasMore"
            :is-mobile="false"
            :load-more-tracker-activity="loadMoreTrackerActivity"
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
    >
      <TrackerDetailsPanel
        :current-tracker="currentTracker"
        :current-user-id="currentUserId"
        :tracker-stats="trackerStats"
        :tracker-activity="trackerActivity"
        :tracker-activity-loading="trackerActivityLoading"
        :tracker-activity-has-more="trackerActivityHasMore"
        :is-mobile="true"
        :load-more-tracker-activity="loadMoreTrackerActivity"
        closeable
        @close="showTrackerDetails = false"
      />
    </VModal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VModal } from '../primitives'
import TrackerDetailsPanel from './TrackerDetailsPanel.vue'
import TrackerDeliveryMode from './TrackerDeliveryMode.vue'
import TrackerToolbar from './TrackerToolbar.vue'
import TrackerTableView from './TrackerTableView.vue'
import { useTrackerStore } from '../../ownership/tracker'

const {
  bulkActionBusy,
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
  canDeleteShots,
  canDownloadSelectedTrackerLatest,
  canDownloadTrackerLatest,
  canViewTrackerDetails,
  clearArchivedSelectedShots,
  clearSelectedShots,
  clearTrackerFilters,
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
  loadMoreTrackerActivity,
  openShotImportPicker,
  projectThumbnailUrl,
  selectedArchivedShotCount,
  selectedShotCount,
  selectionEnabled,
  shareMode,
  showDeliveryMode,
  toggleTrackerFilterValue,
  toggleTrackerSort,
  trackerActiveFilterCount,
  trackerActivity,
  trackerActivityHasMore,
  trackerActivityLoading,
  trackerDownloadBusy,
  trackerDownloadProgress,
  trackerFilterGroups,
  trackerFilters,
  trackerSortDir,
  trackerSortKey,
  trackerStats,
} = useTrackerStore()

const showTrackerDetails = ref(false)
const showDeliveryIntro = ref(false)
const trackerDisplayMode = ref('list')

// A sentinel above the sticky toolbar tells us when the list has scrolled
// underneath it, so the toolbar's separator only appears once it earns one.
const toolbarSentinelRef = ref(null)
const toolbarPinned = ref(false)
let toolbarScroller = null

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

const showDesktopDetails = computed(() => showTrackerDetails.value && canViewTrackerDetails.value !== false && !isMobile.value)
const effectiveTrackerDisplayMode = computed(() => (isMobile.value ? 'list' : trackerDisplayMode.value))
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

watch(
  isMobile,
  (mobile) => {
    if (mobile) trackerDisplayMode.value = 'list'
  },
)

watch(
  () => currentTracker.value?.id,
  () => {
    showTrackerDetails.value = false
    showDeliveryIntro.value = showDeliveryMode.value === true
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
  --tracker-toolbar-height: 56px;
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

.tracker-surface-main {
  display: flex;
  flex-direction: column;
  flex: 1;
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

@media (max-width: 900px) {
  .shot-tracker {
    --tracker-toolbar-height: 52px;
  }
}

@media (max-width: 768px) {
  .shot-tracker {
    --tracker-page-gutter: 12px;
    --tracker-toolbar-height: 43px;
  }
}

@media (max-width: 767px) {
  .shot-tracker .v-inspector-rail {
    display: none;
  }
}
</style>
