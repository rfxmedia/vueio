import { computed, inject, provide, ref } from 'vue'

export const projectTrackerSelectionStoreKey = Symbol('vueio.projectTrackerSelectionStore')

export function createProjectTrackerSelectionStore(initial = {}) {
  const currentProject = initial.currentProject || ref(null)
  const currentTracker = initial.currentTracker || ref(null)
  const currentPage = initial.currentPage || ref(null)
  const openingProjectId = initial.openingProjectId || ref(null)
  const currentTrackerRef = computed(() => (
    currentTracker.value?.id ||
    currentTracker.value?.slug ||
    currentTracker.value?.name ||
    ''
  ))

  return {
    currentProject,
    currentTracker,
    currentTrackerRef,
    currentPage,
    openingProjectId,
  }
}

export function provideProjectTrackerSelectionStore(store) {
  provide(projectTrackerSelectionStoreKey, store)
  return store
}

export function useProjectTrackerSelectionStore() {
  const store = inject(projectTrackerSelectionStoreKey, null)
  if (!store) {
    throw new Error('Project/tracker selection store has not been provided')
  }
  return store
}
