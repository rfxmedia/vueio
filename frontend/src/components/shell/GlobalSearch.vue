<template>
  <div
    v-if="currentUser?.role === 'admin' && !shareMode && showMainContent"
    class="v-search-container"
    :class="[`is-${variant}`]"
    @click.stop
  >
    <div class="v-search" :class="{ 'v-search-focused': searchFocused }">
      <svg class="icon v-search-icon"><use href="#icon-search"/></svg>
      <input
        ref="searchInputRef"
        v-model="globalSearchQuery"
        type="text"
        class="v-search-input"
        role="combobox"
        aria-label="Search Vue.io"
        aria-autocomplete="list"
        :aria-expanded="String(searchOpen && globalSearchQuery.length >= 2)"
        :aria-controls="searchResultsId"
        :aria-activedescendant="activeResultId"
        :placeholder="variant === 'drawer' ? 'Search projects, Vue Trackers, files' : 'Search...'"
        @focus="openSearch"
        @blur="handleSearchBlur"
        @input="debouncedSearch"
        @keydown.escape="closeSearch"
        @keydown.down.prevent="navigateResults(1)"
        @keydown.up.prevent="navigateResults(-1)"
        @keydown.enter="selectResult"
      />
      <kbd v-if="variant !== 'drawer' && !searchFocused" class="v-search-shortcut">⌘K</kbd>
    </div>

    <Transition name="v-menu-pop">
      <div v-if="searchOpen && globalSearchQuery.length >= 2" :id="searchResultsId" class="v-search-results" :class="{ 'is-drawer': variant === 'drawer' }" role="listbox" aria-label="Search results">
        <div v-if="searchResults.projects.length" class="v-search-group">
          <div class="v-search-group-title">Projects</div>
          <div
            v-for="(item, i) in searchResults.projects"
            :key="item.id"
            class="v-search-result"
            :class="{ 'v-search-result-active': selectedResultIndex === i }"
            role="option"
            :id="resultId(i)"
            :aria-selected="selectedResultIndex === i"
            @mousedown.prevent="goToSearchProject(item.id)"
          >
            <svg class="icon v-search-result-icon"><use href="#icon-project"/></svg>
            <span class="v-search-result-title">{{ item.title }}</span>
            <span class="v-status v-status-sm" :class="getSearchStatusClass(item.status)">{{ formatSearchStatus(item.status) }}</span>
          </div>
        </div>

        <div v-if="searchResults.trackers.length" class="v-search-group">
          <div class="v-search-group-title">Vue Trackers</div>
          <div
            v-for="(item, i) in searchResults.trackers"
            :key="item.id"
            class="v-search-result"
            :class="{ 'v-search-result-active': selectedResultIndex === searchResults.projects.length + i }"
            role="option"
            :id="resultId(searchResults.projects.length + i)"
            :aria-selected="selectedResultIndex === searchResults.projects.length + i"
            @mousedown.prevent="goToSearchTracker(item.projectId, item.name)"
          >
            <svg class="icon v-search-result-icon"><use href="#icon-list"/></svg>
            <span class="v-search-result-title">{{ item.name }}</span>
            <span class="v-search-result-meta">in {{ item.projectTitle }}</span>
          </div>
        </div>

        <div v-if="searchResults.files.length" class="v-search-group">
          <div class="v-search-group-title">Files</div>
          <div
            v-for="(item, i) in searchResults.files"
            :key="item.path"
            class="v-search-result"
            :class="{ 'v-search-result-active': selectedResultIndex === searchResults.projects.length + searchResults.trackers.length + i }"
            role="option"
            :id="resultId(searchResults.projects.length + searchResults.trackers.length + i)"
            :aria-selected="selectedResultIndex === searchResults.projects.length + searchResults.trackers.length + i"
            @mousedown.prevent="goToSearchFile(item.path)"
          >
            <svg class="icon v-search-result-icon"><use href="#icon-file"/></svg>
            <span class="v-search-result-title">{{ item.name }}</span>
            <span class="v-search-result-meta">{{ item.folder }}</span>
          </div>
        </div>

        <div v-if="noSearchResults" class="v-search-empty">
          No results for "{{ globalSearchQuery }}"
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import api from '../../lib/api'
import { useAppChromeStore } from '../../ownership/appChrome'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useProjectWorkspaceStore } from '../../ownership/projectWorkspace'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useTrackerStore } from '../../ownership/tracker'

const { currentUser } = useSessionAuthStore()
const { shareMode } = useShareAccessContext()
const { showMainContent, isMobile } = useAppChromeStore()
const { openProject } = useProjectWorkspaceStore()
const { openProjectTracker } = useTrackerStore()
const { navigateTo } = useFileBrowserStore().browser
const variant = computed(() => isMobile.value ? 'drawer' : 'header')

const globalSearchQuery = ref('')
const searchOpen = ref(false)
const searchFocused = ref(false)
const searchResults = ref({ projects: [], trackers: [], files: [] })
const selectedResultIndex = ref(-1)
const searchLoading = ref(false)
const searchInputRef = ref(null)
const searchResultsId = computed(() => `global-search-results-${variant.value}`)
const activeResultId = computed(() => selectedResultIndex.value >= 0 ? resultId(selectedResultIndex.value) : undefined)
let searchDebounceTimer = null
let searchAbortController = null

function resultId(index) {
  return `${searchResultsId.value}-option-${index}`
}

const noSearchResults = computed(() => {
  return globalSearchQuery.value.length >= 2 &&
    !searchLoading.value &&
    searchResults.value.projects.length === 0 &&
    searchResults.value.trackers.length === 0 &&
    searchResults.value.files.length === 0
})

const totalSearchResults = computed(() => {
  return searchResults.value.projects.length +
    searchResults.value.trackers.length +
    searchResults.value.files.length
})

function isRequestCanceled(error) {
  return error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED'
}

function openSearch() {
  searchOpen.value = true
  searchFocused.value = true
  selectedResultIndex.value = -1
}

function focusInput() {
  if (currentUser.value?.role !== 'admin' || shareMode.value || !showMainContent.value) return
  nextTick(() => {
    searchInputRef.value?.focus()
    openSearch()
  })
}

function closeSearch() {
  searchOpen.value = false
  searchFocused.value = false
  globalSearchQuery.value = ''
  selectedResultIndex.value = -1
  searchResults.value = { projects: [], trackers: [], files: [] }
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (searchAbortController) {
    searchAbortController.abort()
    searchAbortController = null
  }
  searchInputRef.value?.blur()
}

function handleSearchBlur() {
  setTimeout(() => {
    searchFocused.value = false
    searchOpen.value = false
  }, 200)
}

async function performSearch() {
  if (globalSearchQuery.value.length < 2) {
    searchResults.value = { projects: [], trackers: [], files: [] }
    return
  }

  if (searchAbortController) searchAbortController.abort()
  const controller = new AbortController()
  searchAbortController = controller
  searchLoading.value = true
  try {
    const res = await api.get(`/api/search?q=${encodeURIComponent(globalSearchQuery.value)}`, { signal: controller.signal })
    searchResults.value = res.data
  } catch (e) {
    if (isRequestCanceled(e)) return
    console.error('Search failed')
    searchResults.value = { projects: [], trackers: [], files: [] }
  } finally {
    if (searchAbortController === controller) searchAbortController = null
    searchLoading.value = false
  }
}

function debouncedSearch() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(performSearch, 200)
}

function navigateResults(direction) {
  const total = totalSearchResults.value
  if (total === 0) return

  selectedResultIndex.value += direction
  if (selectedResultIndex.value < 0) selectedResultIndex.value = total - 1
  if (selectedResultIndex.value >= total) selectedResultIndex.value = 0
}

function selectResult() {
  if (selectedResultIndex.value < 0) return

  const projectsLen = searchResults.value.projects.length
  const trackersLen = searchResults.value.trackers.length

  if (selectedResultIndex.value < projectsLen) {
    const item = searchResults.value.projects[selectedResultIndex.value]
    goToSearchProject(item.id)
  } else if (selectedResultIndex.value < projectsLen + trackersLen) {
    const item = searchResults.value.trackers[selectedResultIndex.value - projectsLen]
    goToSearchTracker(item.projectId, item.name)
  } else {
    const item = searchResults.value.files[selectedResultIndex.value - projectsLen - trackersLen]
    goToSearchFile(item.path)
  }
}

function goToSearchProject(projectId) {
  closeSearch()
  openProject(projectId)
}

function goToSearchTracker(projectId, trackerName) {
  closeSearch()
  openProjectTracker(projectId, trackerName)
}

function goToSearchFile(filePath) {
  closeSearch()
  const dir = filePath.includes('/') ? filePath.substring(0, filePath.lastIndexOf('/')) : ''
  navigateTo(dir)
}

function formatSearchStatus(status) {
  const labels = {
    not_started: 'Draft',
    in_progress: 'Active',
    waiting_review: 'Review',
    edits_requested: 'Hold',
    done: 'Done',
  }
  return labels[status] || status
}

function getSearchStatusClass(status) {
  const variants = {
    not_started: 'v-status-draft',
    in_progress: 'v-status-active',
    waiting_review: 'v-status-review',
    edits_requested: 'v-status-hold',
    done: 'v-status-done',
  }
  return variants[status] || 'v-status-draft'
}

onBeforeUnmount(() => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (searchAbortController) searchAbortController.abort()
})

defineExpose({ focusInput, closeSearch })
</script>

<style>
.v-search-container {
  position: relative;
  flex: 1;
  max-width: 320px;
  margin: 0 16px;
}

.v-search {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  padding: var(--v-space-2) var(--v-space-3);
  background: var(--v-bg-field);
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-lg);
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.v-search:hover {
  border-color: var(--v-control-border-hover);
}

.v-search-focused {
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.v-search-icon {
  width: 14px;
  height: 14px;
  color: var(--v-text-muted);
  flex-shrink: 0;
}

.v-search .v-search-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  font-size: var(--v-text-sm);
  color: var(--v-text);
}

.v-search .v-search-input::placeholder {
  color: var(--v-text-muted);
}

.v-search-shortcut {
  font-family: var(--v-font);
  font-size: var(--v-text-2xs);
  color: var(--v-text-muted);
  background: var(--v-surface-inline);
  padding: 2px 5px;
  border-radius: var(--v-radius-sm);
  border: 1px solid var(--v-control-border);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.v-search-results {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: var(--v-space-2);
  background: var(--v-surface-panel);
  border: 1px solid var(--v-border);
  border-radius: var(--v-radius-lg);
  box-shadow: var(--v-menu-shadow);
  max-height: 400px;
  overflow-y: auto;
  z-index: var(--v-z-dropdown);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.v-search-group {
  padding: var(--v-space-2);
}

.v-search-group + .v-search-group {
  border-top: 1px solid var(--v-border);
}

.v-search-group-title {
  font-size: var(--v-text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--v-text-muted);
  padding: var(--v-space-1) var(--v-space-2);
}

.v-search-result {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  padding: var(--v-space-2);
  border-radius: var(--v-radius-md);
  cursor: pointer;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.v-search-result:hover,
.v-search-result-active {
  background: var(--v-surface-inline);
}

.v-search-result-icon {
  width: 14px;
  height: 14px;
  color: var(--v-text-muted);
  flex-shrink: 0;
}

.v-search-result-title {
  flex: 1;
  font-size: var(--v-text-sm);
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.v-search-result-meta {
  font-size: var(--v-text-xs);
  color: var(--v-text-muted);
  white-space: nowrap;
}

.v-search-empty {
  padding: var(--v-space-6);
  text-align: center;
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
}

.v-search-container.is-drawer {
  max-width: none;
  margin: 0;
}

.v-search-container.is-drawer .v-search {
  min-height: 46px;
  padding: 0 14px;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-inline);
}

.v-search-container.is-drawer .v-search-results {
  position: static;
  margin-top: var(--v-space-3);
  max-height: min(46vh, 360px);
  background: var(--v-surface-panel-soft);
  box-shadow: none;
}

.v-status-sm {
  font-size: var(--v-text-3xs);
  padding: 2px 6px;
}
</style>
