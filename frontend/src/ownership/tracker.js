import { computed, inject, provide } from 'vue'
import { useTrackerListController } from '../composables/useTrackerListController'
import { useTrackerViewerController } from '../composables/useTrackerViewerController'
import { useTrackerWorkspaceController } from '../composables/useTrackerWorkspaceController'

export const trackerStoreKey = Symbol('vueio.trackerStore')

export function createTrackerStore(context) {
  if (!context?.workspace || !context?.list || !context?.viewer) {
    throw new TypeError('Tracker workspace, list, and viewer contexts are required')
  }

  let listController
  let viewerController
  const workspaceController = useTrackerWorkspaceController({
    ...context.workspace,
    getListController: () => listController,
  })
  listController = useTrackerListController({
    ...context.list,
    saveShot: workspaceController.saveShot,
    selectStatus: workspaceController.selectStatus,
    getShotAssigneeIds: workspaceController.getShotAssigneeIds,
    getShotAssignees: workspaceController.getShotAssignees,
    getShotAssigneeLabel: workspaceController.getShotAssigneeLabel,
    getAllLatestShotFiles: workspaceController.getAllLatestShotFiles,
    getShotLatestCreatedAt: (...args) => viewerController.getShotLatestCreatedAt(...args),
    loadTrackerActivity: workspaceController.loadTrackerActivity,
  })
  viewerController = useTrackerViewerController({
    ...context.viewer,
    openTracker: workspaceController.openTracker,
    recordTrackerMediaView: workspaceController.recordTrackerMediaView,
    invalidateTrackerPayloads: workspaceController.invalidateCurrentTrackerPayloads,
    trackerShotsForDisplay: listController.trackerShotsForDisplay,
    trackerStatusOptions: listController.trackerStatusOptions,
    showStatusPicker: listController.showStatusPicker,
  })

  return Object.freeze({
    ...context.presentation,
    ...workspaceController,
    ...listController,
    ...viewerController,
    STATUS_ORDER: context.list.statusOrder,
    bulkStatusOptions: listController.trackerStatusOptions,
    canCategorizeShots: listController.canBulkUpdateCategory,
    clearSelectedShots: listController.clearActiveSelectedShots,
    currentUserId: computed(() => context.list.currentUser.value?.id || ''),
    formatVersionLabel: viewerController.formatTrackerVersionLabel,
    openShotVideo: viewerController.openTrackerShotVideo,
    selectedArchivedShotCount: computed(() => listController.selectedArchivedShots.value.length),
    selectedShotCount: computed(() => listController.selectedTrackerShots.value.length),
  })
}

export function provideTrackerStore(store) {
  provide(trackerStoreKey, store)
  return store
}

export function useTrackerStore() {
  const store = inject(trackerStoreKey, null)
  if (!store) {
    throw new Error('Tracker store has not been provided')
  }
  return store
}
