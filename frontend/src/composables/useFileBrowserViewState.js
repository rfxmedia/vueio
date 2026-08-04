import { ref } from 'vue'

import { FILE_SORT_OPTIONS, sortFileBrowserItems } from '../utils/fileBrowserItems'

const VIEW_STORAGE_KEY = 'vueio_view'
const SORT_KEY_STORAGE_KEY = 'vueio_file_sort_key'
const SORT_DIRECTION_STORAGE_KEY = 'vueio_file_sort_direction'
const VALID_SORT_KEYS = new Set(FILE_SORT_OPTIONS.map((option) => option.value))

function readStoredValue(key, fallback) {
  if (typeof localStorage === 'undefined') return fallback
  return localStorage.getItem(key) || fallback
}

function defaultSortDirection(key) {
  return key === 'date' || key === 'size' ? 'desc' : 'asc'
}

export function useFileBrowserViewState() {
  const storedViewMode = readStoredValue(VIEW_STORAGE_KEY, 'grid')
  const storedSortKey = readStoredValue(SORT_KEY_STORAGE_KEY, 'name')
  const storedSortDirection = readStoredValue(SORT_DIRECTION_STORAGE_KEY, 'asc')

  const viewMode = ref(storedViewMode === 'list' ? 'list' : 'grid')
  const fileSortKey = ref(VALID_SORT_KEYS.has(storedSortKey) ? storedSortKey : 'name')
  const fileSortDirection = ref(storedSortDirection === 'desc' ? 'desc' : 'asc')

  function persist(key, value) {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, value)
  }

  function setViewMode(mode) {
    viewMode.value = mode === 'list' ? 'list' : 'grid'
    persist(VIEW_STORAGE_KEY, viewMode.value)
  }

  function toggleViewMode() {
    setViewMode(viewMode.value === 'grid' ? 'list' : 'grid')
  }

  function chooseFileSort(key) {
    if (!VALID_SORT_KEYS.has(key) || key === fileSortKey.value) return
    fileSortKey.value = key
    fileSortDirection.value = defaultSortDirection(key)
    persist(SORT_KEY_STORAGE_KEY, fileSortKey.value)
    persist(SORT_DIRECTION_STORAGE_KEY, fileSortDirection.value)
  }

  function toggleFileSort(key) {
    if (!VALID_SORT_KEYS.has(key)) return
    if (key === fileSortKey.value) {
      toggleFileSortDirection()
      return
    }
    chooseFileSort(key)
  }

  function toggleFileSortDirection() {
    fileSortDirection.value = fileSortDirection.value === 'asc' ? 'desc' : 'asc'
    persist(SORT_DIRECTION_STORAGE_KEY, fileSortDirection.value)
  }

  function sortItems(items) {
    return sortFileBrowserItems(items, fileSortKey.value, fileSortDirection.value)
  }

  return {
    viewMode,
    fileSortKey,
    fileSortDirection,
    setViewMode,
    toggleViewMode,
    chooseFileSort,
    toggleFileSort,
    toggleFileSortDirection,
    sortItems,
  }
}
