<template>
  <div class="tracker-toolbar" role="toolbar" aria-label="Tracker controls">
    <div class="tracker-toolbar-leading">
      <div class="tracker-toolbar-organize" role="group" aria-label="Filter and sort shots">
        <VMenu
        :open="showFilterDropdown && !isMobile"
        align="start"
        class="tracker-toolbar-group tracker-toolbar-group-filter"
        panel-class="tracker-filter-dropdown"
        :close-on-select="false"
        @update:open="open => !open && setFilterOpen(false)"
      >
        <template #trigger="{ triggerProps }">
          <button
            class="tracker-toolbar-action v-btn v-btn-secondary v-btn-sm tracker-filter-btn"
            :class="{ 'v-btn-active': hasTrackerFilters || showFilterDropdown }"
            type="button"
            aria-label="Filters"
            title="Filters"
            v-bind="triggerProps"
            @click.stop="toggleFilterMenu"
          >
            <svg class="icon tracker-filter-icon"><use href="#icon-filter" /></svg>
            <span class="tracker-toolbar-action-label tracker-toolbar-action-label-desktop">Filters</span>
            <span v-if="trackerActiveFilterCount" class="tracker-toolbar-action-count v-chip-count">{{ trackerActiveFilterCount }}</span>
            <svg class="icon tracker-toolbar-action-chevron tracker-toolbar-action-chevron-desktop"><use href="#icon-chevron-down" /></svg>
          </button>
        </template>

        <div class="tracker-filter-dropdown-header">
          <div>
            <p class="tracker-filter-dropdown-title v-section-label">Filters</p>
            <p class="tracker-filter-dropdown-copy">Combine filters to focus this tracker.</p>
          </div>
          <button
            v-if="hasTrackerFilters"
            type="button"
            class="v-btn v-btn-secondary v-btn-sm tracker-filter-clear-btn"
            @click="clearAllFilters"
          >
            Clear
          </button>
        </div>

        <div class="tracker-filter-sections">
              <section
                v-for="group in trackerFilterGroups"
                :key="group.key"
                class="tracker-filter-section"
              >
                <p class="tracker-filter-section-title v-section-label">{{ group.label }}</p>
                <div class="tracker-filter-option-list">
                  <button
                    v-for="option in group.options"
                    :key="`${group.key}:${option.value}`"
                    type="button"
                    class="tracker-filter-option v-dropdown-item"
                    :class="{ active: isFilterSelected(group.key, option.value) }"
                    @click="toggleFilter(group.key, option.value)"
                  >
                    <span class="tracker-filter-option-leading">
                      <span
                        v-if="option.color"
                        class="tracker-filter-option-dot"
                        :style="{ background: option.color }"
                      ></span>
                      <svg v-else-if="option.icon" class="icon tracker-filter-option-icon"><use :href="option.icon" /></svg>
                    </span>
                    <span class="tracker-filter-option-label">{{ option.label }}</span>
                    <span class="tracker-filter-option-meta">
                      <span class="tracker-filter-option-count v-chip-count">{{ option.count }}</span>
                      <svg
                        v-if="isFilterSelected(group.key, option.value)"
                        class="icon tracker-filter-option-check"
                      >
                        <use href="#icon-check" />
                      </svg>
                    </span>
                  </button>
                </div>
          </section>
        </div>
        </VMenu>

        <VMenu
        :open="showSortDropdown && !isMobile"
        align="end"
        class="tracker-sort-mobile"
        panel-class="tracker-sort-dropdown"
        :close-on-select="false"
        @update:open="open => !open && setSortOpen(false)"
      >
        <template #trigger="{ triggerProps }">
          <button
            class="tracker-toolbar-action v-btn v-btn-secondary v-btn-sm sort-mobile-btn"
            :class="{ 'v-btn-active': !!trackerSortKey || !!trackerGroupKey || showSortDropdown }"
            type="button"
            :aria-label="organizeButtonLabel"
            :title="organizeButtonLabel"
            v-bind="triggerProps"
            @click.stop="toggleSortMenu"
          >
            <svg class="icon sort-mobile-icon"><use href="#icon-sort" /></svg>
            <span class="sort-mobile-label">{{ trackerSortKey ? currentSortLabel : 'Sort' }}</span>
            <svg class="icon tracker-toolbar-action-chevron sort-mobile-chevron">
              <use :href="trackerSortKey && trackerSortDir === 'asc' ? '#icon-chevron-up' : '#icon-chevron-down'" />
            </svg>
          </button>
        </template>
        <div class="tracker-organize-menu-label">Sort shots</div>
        <button
          v-for="option in sortOptions"
          :key="option.key"
          class="tracker-sort-option v-dropdown-item"
          :class="{ active: trackerSortKey === option.key }"
          @click="selectSort(option.key)"
        >
          <span>{{ option.label }}</span>
          <svg v-if="trackerSortKey === option.key" class="icon tracker-sort-option-chevron">
            <use :href="trackerSortDir === 'asc' ? '#icon-chevron-up' : '#icon-chevron-down'" />
          </svg>
        </button>
        <div class="v-dropdown-divider"></div>
        <div class="tracker-organize-menu-label">Group shots</div>
        <button
          v-for="option in groupOptions"
          :key="option.key"
          type="button"
          class="tracker-group-option v-dropdown-item"
          :aria-pressed="trackerGroupKey === option.key ? 'true' : 'false'"
          @click="toggleGroup(option.key)"
        >
          <span class="tracker-group-option-check" :class="{ 'is-checked': trackerGroupKey === option.key }">
            <svg v-if="trackerGroupKey === option.key" class="icon"><use href="#icon-check" /></svg>
          </span>
          <span>{{ option.label }}</span>
        </button>
        </VMenu>
      </div>

      <span v-if="!isMobile" class="tracker-toolbar-divider" aria-hidden="true"></span>

      <div
        v-if="!isMobile"
        class="tracker-view-switch"
        role="group"
        aria-label="Shot layout"
      >
        <button
          v-for="mode in displayModes"
          :key="mode.key"
          type="button"
          class="tracker-view-switch__btn"
          :class="{ 'is-active': trackerDisplayMode === mode.key }"
          :aria-pressed="trackerDisplayMode === mode.key ? 'true' : 'false'"
          :title="mode.title"
          @click="setTrackerDisplayMode(mode.key)"
        >
          <svg class="icon"><use :href="mode.icon" /></svg>
          <span class="tracker-view-switch__label">{{ mode.label }}</span>
        </button>
      </div>
    </div>

    <TrackerBulkActionsBar
      v-if="selectionEnabled"
      :selected-count="bulkSelectedCount"
      :count-label="bulkCountLabel"
      :aria-label="bulkAriaLabel"
      :is-mobile="isMobile"
      :can-bulk-update-status="canBulkUpdateStatus"
      :can-bulk-update-category="canBulkUpdateCategory"
      :can-bulk-update-assignee="canBulkUpdateAssignee"
      :can-download="bulkCanDownload"
      :can-download-selected="canDownloadSelectedTrackerLatest"
      :can-archive="bulkCanArchive"
      :can-delete="bulkCanDelete"
      :can-restore="bulkCanRestore"
      :bulk-status-options="bulkStatusOptions"
      :bulk-category-options="bulkCategoryOptions"
      :bulk-assignee-options="bulkAssigneeOptions"
      :bulk-action-busy="bulkActionBusy"
      :download-busy="trackerDownloadBusy"
      :tracker-filter-groups="trackerFilterGroups"
      :clear-selection="bulkClearSelection"
      :download-selected="downloadSelectedTrackerLatestVersions"
      :bulk-update-status="bulkUpdateStatus"
      :bulk-update-category="bulkUpdateCategory"
      :bulk-update-assignee="bulkUpdateAssignee"
      :archive-selected="bulkArchiveShots"
      :delete-selected="bulkDeleteShots"
      :restore-selected="bulkRestoreArchivedShots"
    />

    <div class="tracker-toolbar-actions" role="group" aria-label="Tracker actions">
      <button
        v-if="canDownloadTrackerLatest && !isMobile"
        type="button"
        class="tracker-toolbar-action v-btn v-btn-secondary v-btn-sm tracker-toolbar-quick-action tracker-toolbar-download-all"
        :disabled="trackerDownloadBusy"
        :aria-busy="trackerDownloadBusy ? 'true' : 'false'"
        title="Download latest versions for visible tracker shots"
        @click="downloadTrackerLatestVersions"
      >
        <svg class="icon"><use href="#icon-download" /></svg>
        <span class="tracker-toolbar-action-label">{{ trackerDownloadLabel }}</span>
        <span v-if="trackerDownloadBusy" class="tracker-download-progress" aria-hidden="true">
          <span class="tracker-download-progress-bar" :style="{ width: `${trackerDownloadPercent}%` }" />
        </span>
      </button>

      <button
        v-if="canAddShots || canAddVersions"
        type="button"
        class="tracker-toolbar-action v-btn v-btn-primary v-btn-sm tracker-toolbar-quick-action tracker-toolbar-primary-action"
        aria-label="Import shots"
        title="Import shots"
        @click="openShotImportPicker"
      >
        <svg class="icon"><use href="#icon-plus" /></svg>
        <span class="tracker-toolbar-action-label">Import</span>
      </button>

      <button
        v-if="canViewTrackerDetails"
        type="button"
        class="tracker-toolbar-action v-btn v-btn-secondary v-btn-sm tracker-toolbar-quick-action"
        :class="{ 'v-btn-active': showTrackerDetails }"
        aria-label="Tracker details"
        title="Tracker details"
        :aria-pressed="showTrackerDetails ? 'true' : 'false'"
        @click="toggleTrackerDetails"
      >
        <svg class="icon"><use href="#icon-activity" /></svg>
        <span class="tracker-toolbar-action-label">Details</span>
      </button>
    </div>

    <!-- Mobile: filter drawer -->
    <VModal
      v-if="isMobile"
      :modelValue="showFilterDropdown"
      size="lg"
      presentation="sheet"
      class="tracker-filter-sheet-modal"
      @update:modelValue="setFilterOpen"
    >
      <template #header>
        <VModalHeader @close="setFilterOpen(false)">
          <div class="tracker-filter-sheet-header">
            <div class="v-modal-header-copy">
              <h2 class="v-modal-header-title">Filters</h2>
            <p class="v-modal-header-subtitle">Combine filters to focus this tracker.</p>
            </div>
            <button
              v-if="hasTrackerFilters"
              type="button"
              class="v-btn v-btn-quiet v-btn-sm tracker-filter-sheet-clear"
              @click="clearAllFilters"
            >
              Clear
            </button>
          </div>
        </VModalHeader>
      </template>

      <div class="tracker-filter-sheet-body">
        <section
          v-for="group in trackerFilterGroups"
          :key="group.key"
          class="tracker-filter-section"
        >
          <p class="tracker-filter-section-title v-section-label">{{ group.label }}</p>
          <div class="tracker-filter-option-list">
            <button
              v-for="option in group.options"
              :key="`${group.key}:${option.value}`"
              type="button"
              class="tracker-filter-option v-dropdown-item"
              :class="{ active: isFilterSelected(group.key, option.value) }"
              @click="toggleFilter(group.key, option.value)"
            >
              <span class="tracker-filter-option-leading">
                <span
                  v-if="option.color"
                  class="tracker-filter-option-dot"
                  :style="{ background: option.color }"
                ></span>
                <svg v-else-if="option.icon" class="icon tracker-filter-option-icon"><use :href="option.icon" /></svg>
              </span>
              <span class="tracker-filter-option-label">{{ option.label }}</span>
              <span class="tracker-filter-option-meta">
                <span class="tracker-filter-option-count v-chip-count">{{ option.count }}</span>
                <svg
                  v-if="isFilterSelected(group.key, option.value)"
                  class="icon tracker-filter-option-check"
                >
                  <use href="#icon-check" />
                </svg>
              </span>
            </button>
          </div>
        </section>
      </div>
    </VModal>

    <!-- Mobile: sort drawer -->
    <VModal
      v-if="isMobile"
      :modelValue="showSortDropdown"
      size="lg"
      presentation="sheet"
      class="tracker-sort-sheet-modal"
      @update:modelValue="setSortOpen"
    >
      <template #header>
        <VModalHeader @close="setSortOpen(false)">
          <div class="v-modal-header-copy">
            <h2 class="v-modal-header-title">Sort and group</h2>
            <p class="v-modal-header-subtitle">Choose how shots are ordered and organized.</p>
          </div>
        </VModalHeader>
      </template>

      <div class="tracker-sort-sheet-body">
        <section class="tracker-sort-sheet-section">
          <p class="tracker-organize-menu-label">Sort shots</p>
          <button
            v-for="option in sortOptions"
            :key="option.key"
            type="button"
            class="tracker-sort-option v-dropdown-item"
            :class="{ active: trackerSortKey === option.key }"
            @click="selectSort(option.key)"
          >
            <span>{{ option.label }}</span>
            <svg v-if="trackerSortKey === option.key" class="icon tracker-sort-option-chevron">
              <use :href="trackerSortDir === 'asc' ? '#icon-chevron-up' : '#icon-chevron-down'" />
            </svg>
          </button>
        </section>
        <section class="tracker-sort-sheet-section">
          <p class="tracker-organize-menu-label">Group shots</p>
          <button
            v-for="option in groupOptions"
            :key="option.key"
            type="button"
            class="tracker-group-option v-dropdown-item"
            :aria-pressed="trackerGroupKey === option.key ? 'true' : 'false'"
            @click="toggleGroup(option.key)"
          >
            <span class="tracker-group-option-check" :class="{ 'is-checked': trackerGroupKey === option.key }">
              <svg v-if="trackerGroupKey === option.key" class="icon"><use href="#icon-check" /></svg>
            </span>
            <span>{{ option.label }}</span>
          </button>
        </section>
      </div>
    </VModal>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VMenu, VModal, VModalHeader } from '../primitives'
import TrackerBulkActionsBar from './TrackerBulkActionsBar.vue'

const displayModes = [
  { key: 'list', label: 'List', title: 'List view', icon: '#icon-list' },
  { key: 'grid', label: 'Grid', title: 'Grid view', icon: '#icon-grid' },
]

const sortOptions = [
  { key: 'id', label: 'Shot ID' },
  { key: 'updated', label: 'Updated' },
  { key: 'status', label: 'Status' },
  { key: 'category', label: 'Tag' },
  { key: 'assignee', label: 'Assignee' },
]

const groupOptions = [
  { key: 'status', label: 'Group by status' },
  { key: 'assignee', label: 'Group by assignee' },
  { key: 'category', label: 'Group by tag' },
]

const props = defineProps({
  canAddShots: { type: Boolean, default: false },
  canAddVersions: { type: Boolean, default: false },
  canViewTrackerDetails: { type: Boolean, default: true },
  clearTrackerFilters: { type: Function, required: true },
  hasTrackerFilters: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  openShotImportPicker: { type: Function, required: true },
  toggleTrackerFilterValue: { type: Function, required: true },
  trackerActiveFilterCount: { type: Number, default: 0 },
  trackerFilterGroups: { type: Array, default: () => [] },
  trackerFilters: { type: Object, default: () => ({ statuses: [], categories: [], assignees: [] }) },
  showTrackerDetails: { type: Boolean, default: false },
  trackerSortDir: { type: String, default: 'asc' },
  trackerSortKey: { type: String, default: null },
  trackerGroupKey: { type: String, default: null },
  toggleTrackerDetails: { type: Function, required: true },
  toggleTrackerGroup: { type: Function, required: true },
  toggleTrackerSort: { type: Function, required: true },
  selectionEnabled: { type: Boolean, default: false },
  canBulkUpdateStatus: { type: Boolean, default: false },
  canBulkUpdateCategory: { type: Boolean, default: false },
  canBulkUpdateAssignee: { type: Boolean, default: false },
  canArchiveShots: { type: Boolean, default: false },
  canDeleteShots: { type: Boolean, default: false },
  canDownloadTrackerLatest: { type: Boolean, default: false },
  canDownloadSelectedTrackerLatest: { type: Boolean, default: false },
  selectedShotCount: { type: Number, default: 0 },
  selectedArchivedShotCount: { type: Number, default: 0 },
  bulkStatusOptions: { type: Array, default: () => [] },
  bulkCategoryOptions: { type: Array, default: () => [] },
  bulkAssigneeOptions: { type: Array, default: () => [] },
  bulkActionBusy: { type: Boolean, default: false },
  trackerDownloadBusy: { type: Boolean, default: false },
  trackerDownloadProgress: { type: Object, default: null },
  trackerDisplayMode: { type: String, default: 'list' },
  setTrackerDisplayMode: { type: Function, default: () => {} },
  clearSelectedShots: { type: Function, default: () => {} },
  clearArchivedSelectedShots: { type: Function, default: () => {} },
  downloadTrackerLatestVersions: { type: Function, default: () => {} },
  downloadSelectedTrackerLatestVersions: { type: Function, default: () => {} },
  bulkUpdateShotStatus: { type: Function, default: async () => {} },
  bulkUpdateShotCategory: { type: Function, default: async () => {} },
  bulkUpdateShotAssignee: { type: Function, default: async () => {} },
  bulkUpdateArchivedShotStatus: { type: Function, default: async () => {} },
  bulkUpdateArchivedShotCategory: { type: Function, default: async () => {} },
  bulkUpdateArchivedShotAssignee: { type: Function, default: async () => {} },
  bulkArchiveShots: { type: Function, default: async () => {} },
  bulkRestoreArchivedShots: { type: Function, default: async () => {} },
  bulkDeleteShots: { type: Function, default: async () => {} },
})

const showFilterDropdown = ref(false)
const showSortDropdown = ref(false)

const currentSortLabel = computed(
  () => sortOptions.find(option => option.key === props.trackerSortKey)?.label ?? '',
)

const organizeButtonLabel = computed(() => {
  const actions = []
  if (props.trackerSortKey) actions.push(`sorted by ${currentSortLabel.value}`)
  const groupLabel = groupOptions.find(option => option.key === props.trackerGroupKey)?.label
  if (groupLabel) actions.push(groupLabel.toLowerCase())
  return actions.length ? `Sort and group shots: ${actions.join(', ')}` : 'Sort and group shots'
})

const trackerDownloadPercent = computed(() => {
  const raw = Number(props.trackerDownloadProgress?.progress || 0)
  return Math.max(0, Math.min(100, Math.round(raw)))
})

const trackerDownloadLabel = computed(() => {
  if (!props.trackerDownloadBusy) return 'Download All'
  const message = props.trackerDownloadProgress?.message || 'Packaging'
  const percent = trackerDownloadPercent.value
  if (percent > 0 && percent < 100) return `${message} ${percent}%`
  if (percent >= 100) return 'Starting download…'
  return `${message}…`
})

const hasArchivedBulkSelection = computed(() => props.selectedArchivedShotCount > 0)
const bulkSelectedCount = computed(() => (
  hasArchivedBulkSelection.value ? props.selectedArchivedShotCount : props.selectedShotCount
))
const bulkCountLabel = computed(() => (
  hasArchivedBulkSelection.value ? 'archived selected' : 'selected'
))
const bulkAriaLabel = computed(() => (
  hasArchivedBulkSelection.value ? 'Selected archived shot actions' : 'Selected shot actions'
))
const bulkCanDownload = computed(() => (
  !hasArchivedBulkSelection.value && props.canDownloadTrackerLatest
))
const bulkCanArchive = computed(() => (
  !hasArchivedBulkSelection.value && props.canArchiveShots
))
const bulkCanDelete = computed(() => (
  hasArchivedBulkSelection.value && props.canDeleteShots
))
const bulkCanRestore = computed(() => hasArchivedBulkSelection.value)
const bulkClearSelection = computed(() => (
  hasArchivedBulkSelection.value ? props.clearArchivedSelectedShots : props.clearSelectedShots
))
const bulkUpdateStatus = computed(() => (
  hasArchivedBulkSelection.value ? props.bulkUpdateArchivedShotStatus : props.bulkUpdateShotStatus
))
const bulkUpdateCategory = computed(() => (
  hasArchivedBulkSelection.value ? props.bulkUpdateArchivedShotCategory : props.bulkUpdateShotCategory
))
const bulkUpdateAssignee = computed(() => (
  hasArchivedBulkSelection.value ? props.bulkUpdateArchivedShotAssignee : props.bulkUpdateShotAssignee
))

function isFilterSelected(groupKey, value) {
  return Array.isArray(props.trackerFilters?.[groupKey]) && props.trackerFilters[groupKey].includes(value)
}

function toggleFilter(groupKey, value) {
  props.toggleTrackerFilterValue(groupKey, value)
}

function clearAllFilters() {
  props.clearTrackerFilters()
}

function setFilterOpen(open) {
  showFilterDropdown.value = !!open
  if (showFilterDropdown.value) showSortDropdown.value = false
}

function setSortOpen(open) {
  showSortDropdown.value = !!open
  if (showSortDropdown.value) showFilterDropdown.value = false
}

function toggleFilterMenu() {
  setFilterOpen(!showFilterDropdown.value)
}

function toggleSortMenu() {
  setSortOpen(!showSortDropdown.value)
}

function selectSort(key) {
  props.toggleTrackerSort(key)
  showSortDropdown.value = false
}

function toggleGroup(key) {
  props.toggleTrackerGroup(key)
}

</script>

<style>
.tracker-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: var(--tracker-toolbar-height, 53px);
  padding: 8px var(--tracker-page-gutter, 18px);
  border-bottom: 1px solid var(--v-tracker-masthead-divider, var(--v-divider));
  background: var(
    --v-tracker-masthead-bg,
    color-mix(in srgb, var(--v-surface-panel) 36%, var(--v-shell-topbar-bg))
  );
  box-shadow: none;
  position: sticky;
  top: 0;
  /* Above cards, below any open row menu (see --v-z-dropdown offsets in the row card). */
  z-index: 30;
}

/* The rule only appears once the list scrolls beneath the toolbar. */
.tracker-toolbar::after {
  content: '';
  position: absolute;
  inset: auto 0 -1px;
  height: 1px;
  background: var(--v-surface-border-strong);
  opacity: 0;
  transition: opacity var(--v-transition-fast);
  pointer-events: none;
}

.shot-tracker.is-scrolled .tracker-toolbar::after {
  opacity: 1;
}

.tracker-toolbar-leading,
.tracker-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tracker-toolbar-organize {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.tracker-toolbar-divider {
  width: 1px;
  height: 24px;
  margin: 0 2px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  background: var(--v-divider);
}

/* ─── Segmented list / grid switch ───────────────────────── */
.tracker-view-switch {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  flex: 0 0 auto;
  padding: 2px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  box-shadow: none;
}

.tracker-view-switch__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: calc(var(--v-button-radius) - 3px);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-weight: 650;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    color var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
}

.tracker-view-switch__btn .icon {
  width: 13px;
  height: 13px;
  opacity: 0.9;
}

.tracker-view-switch__btn:hover:not(.is-active) {
  color: var(--v-text-secondary);
  background: color-mix(in srgb, var(--v-bg-hover) 60%, transparent);
}

.tracker-view-switch__btn.is-active {
  color: var(--v-accent);
  background: var(--v-control-bg-active);
  box-shadow: none;
}

.tracker-view-switch__btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-toolbar-group-filter,
.tracker-sort-mobile {
  position: relative;
  flex: 0 0 auto;
}

.tracker-toolbar-actions {
  margin-left: auto;
  justify-content: flex-end;
}

.tracker-toolbar-action.v-btn {
  min-height: var(--v-btn-height);
  gap: 6px;
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  color: var(--v-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  box-shadow: none;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.tracker-toolbar-action.v-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: var(--v-surface-inline);
  border-color: var(--v-control-border);
  color: var(--v-text);
}

.tracker-toolbar-action.v-btn:active:not(:disabled) {
  transform: scale(0.98);
}

.tracker-toolbar-action.v-btn-active {
  background: var(--v-control-bg-active);
  border-color: color-mix(in srgb, var(--v-accent) 34%, var(--v-control-border));
  color: var(--v-accent);
}

/* Import is the one thing this toolbar wants you to do first. */
.tracker-toolbar-primary-action.v-btn {
  padding-inline: 13px;
  color: var(--v-on-accent);
  background: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 82%, white);
}

.tracker-toolbar-primary-action.v-btn .icon {
  color: currentColor;
  opacity: 1;
}

.tracker-toolbar-primary-action.v-btn:hover:not(:disabled) {
  color: var(--v-on-accent);
  background: var(--v-accent-hover);
  border-color: var(--v-accent-hover);
}

.tracker-filter-btn,
.sort-mobile-btn,
.tracker-toolbar-quick-action {
  justify-content: center;
}

.tracker-toolbar-action .icon {
  opacity: 0.85;
}

.tracker-toolbar-action-label {
  min-width: 0;
}

.tracker-toolbar-action-chevron {
  width: 10px;
  height: 10px;
  margin-left: 2px;
  opacity: 0.5;
  flex-shrink: 0;
}

.tracker-toolbar-action-count {
  margin-left: 2px;
}

.tracker-sort-mobile {
  display: block;
}

.sort-mobile-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tracker-filter-dropdown,
.tracker-sort-dropdown {
  position: absolute;
  z-index: 40;
  top: calc(100% + 8px);
}

.tracker-filter-dropdown {
  left: 0;
  width: min(360px, calc(100vw - 32px));
  max-height: min(560px, calc(100vh - 180px));
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--v-space-2);
}

.tracker-sort-dropdown {
  right: 0;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
}

.tracker-organize-menu-label {
  margin: 0;
  padding: 6px 8px 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.12em;
  line-height: 1;
  text-transform: uppercase;
}

.tracker-filter-dropdown-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 4px 4px 2px;
}

.tracker-filter-dropdown-title,
.tracker-filter-section-title {
  margin: 0;
}

.tracker-filter-dropdown-copy {
  margin: 4px 0 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.tracker-filter-clear-btn {
  flex-shrink: 0;
}

.tracker-filter-sections {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  overflow-y: auto;
  padding-right: 2px;
}

.tracker-filter-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tracker-filter-section + .tracker-filter-section {
  padding-top: var(--v-space-2);
  border-top: 1px solid var(--v-divider-subtle);
}

.tracker-filter-option-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tracker-filter-option,
.tracker-sort-option,
.tracker-group-option {
  justify-content: space-between;
  gap: 10px;
  font-size: var(--v-text-base);
  font-weight: 500;
  border-radius: var(--v-button-radius);
}

.tracker-group-option {
  justify-content: flex-start;
}

.tracker-group-option-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-sm);
  background: var(--v-bg-field);
  color: var(--v-accent);
}

.tracker-group-option-check.is-checked {
  border-color: color-mix(in srgb, var(--v-accent) 48%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-accent) 10%, transparent);
}

.tracker-group-option-check .icon {
  width: 12px;
  height: 12px;
}

.tracker-filter-option.active,
.tracker-sort-option.active {
  color: var(--v-text);
  background: color-mix(in srgb, var(--v-accent) 10%, transparent);
}

.tracker-filter-option-leading {
  width: 14px;
  min-width: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tracker-filter-option-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v-radius-full);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--v-border-hover) 28%, transparent);
}

.tracker-filter-option-icon {
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
}

.tracker-filter-option-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-transform: none;
  letter-spacing: 0;
}

.tracker-filter-option-meta {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  flex-shrink: 0;
}

.tracker-filter-option-count {
  min-width: 20px;
}

.tracker-filter-option-check,
.tracker-sort-option-chevron {
  width: 13px;
  height: 13px;
  opacity: 0.72;
  flex-shrink: 0;
}

/* Mobile drawer (sheet) styling for filter + sort */
.tracker-filter-sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  width: 100%;
}

.tracker-filter-sheet-clear {
  flex: 0 0 auto;
  gap: var(--v-space-1);
}

.tracker-filter-sheet-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px));
}

.tracker-filter-sheet-body .tracker-filter-section + .tracker-filter-section {
  padding-top: 14px;
  border-top: 1px solid var(--v-divider-subtle);
}

.tracker-filter-sheet-body .tracker-filter-option,
.tracker-sort-sheet-body .tracker-sort-option,
.tracker-sort-sheet-body .tracker-group-option {
  min-height: 44px;
  font-size: var(--v-text-md);
  padding: 0 12px;
}

.tracker-filter-sheet-body .tracker-filter-section-title {
  font-size: var(--v-text-xs);
  letter-spacing: 0.16em;
  padding: 0 2px;
}

.tracker-sort-sheet-body {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-5);
  padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px));
}

.tracker-sort-sheet-section {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.tracker-sort-sheet-section + .tracker-sort-sheet-section {
  padding-top: var(--v-space-4);
  border-top: 1px solid var(--v-divider-subtle);
}

.tracker-sort-sheet-section .tracker-organize-menu-label {
  padding-inline: 2px;
}

@media (max-width: 900px) {
  .tracker-toolbar {
    padding-block: 8px;
    gap: var(--v-space-2);
  }

  .tracker-toolbar-leading {
    flex: 0 0 auto;
  }

  .tracker-toolbar-actions {
    flex: 1 1 auto;
    justify-content: flex-end;
  }

  .tracker-toolbar-quick-action {
    min-width: 0;
    flex: 0 1 auto;
  }

  .tracker-sort-mobile {
    display: block;
  }

  .sort-mobile-btn {
    min-width: 94px;
  }

  .tracker-filter-dropdown {
    left: 0;
    right: auto;
    width: min(360px, calc(100vw - 28px));
    max-height: min(70vh, 520px);
  }
}

@media (max-width: 768px) {
  .tracker-toolbar {
    flex-wrap: nowrap;
    align-items: center;
    padding-block: 5px;
    gap: 6px;
    border-bottom: 1px solid var(--v-tracker-masthead-divider, var(--v-divider));
    background: var(
      --v-tracker-masthead-bg,
      color-mix(in srgb, var(--v-surface-panel) 36%, var(--v-shell-topbar-bg))
    );
    box-shadow: none;
  }

  .tracker-toolbar-action.v-btn {
    height: var(--v-btn-height-lg);
    min-height: var(--v-btn-height-lg);
    padding: 0 9px;
    border: 1px solid transparent;
    border-radius: var(--v-button-radius);
    background: transparent;
    box-shadow: none;
    transform: none;
  }

  .tracker-toolbar-action.v-btn:hover:not(:disabled) {
    transform: none;
    border-color: var(--v-control-border-hover);
    background: var(--v-control-bg-hover);
  }

  .tracker-toolbar-action.v-btn-active {
    border-color: color-mix(in srgb, var(--v-accent) 34%, var(--v-control-border));
    background: color-mix(in srgb, var(--v-accent) 12%, var(--v-surface-inline));
    color: var(--v-text);
    box-shadow: none;
  }

  .tracker-toolbar-primary-action.v-btn,
  .tracker-toolbar-primary-action.v-btn:hover:not(:disabled) {
    color: var(--v-on-accent);
    background: var(--v-accent);
    border-color: var(--v-accent);
  }

  .tracker-toolbar-leading {
    display: flex;
    gap: 5px;
    flex: 0 0 auto;
    width: auto;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }

  .tracker-toolbar-organize {
    gap: 1px;
  }

  .tracker-toolbar-actions {
    display: flex;
    gap: 5px;
    flex: 0 0 auto;
    width: auto;
    margin-left: auto;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
  }

  .tracker-filter-btn,
  .sort-mobile-btn {
    width: var(--v-btn-height-lg);
    min-width: var(--v-btn-height-lg);
    padding: 0;
    justify-content: center;
  }

  .tracker-toolbar-group-filter,
  .tracker-sort-mobile {
    position: relative;
    flex: 0 0 auto;
    min-width: var(--v-icon-btn-size);
  }

  .tracker-filter-btn .tracker-toolbar-action-label,
  .tracker-filter-btn .tracker-toolbar-action-count,
  .sort-mobile-label,
  .tracker-toolbar-action-chevron-desktop,
  .sort-mobile-chevron {
    display: none;
  }

  .tracker-filter-btn .tracker-filter-icon {
    width: 15px;
    height: 15px;
  }

  .tracker-toolbar-action-count {
    position: static;
    margin-left: auto;
  }

  .tracker-toolbar-quick-action {
    width: auto;
    min-width: 0;
    flex: 0 0 auto;
    padding-inline: 9px;
  }

  .tracker-toolbar-download-all {
    display: none;
  }

  .tracker-filter-dropdown {
    width: min(360px, calc(100vw - 24px));
  }
}

/* Show Filter/Sort labels only where the labeled controls fit comfortably. */
@media (min-width: 481px) and (max-width: 768px) {
  .tracker-filter-btn,
  .sort-mobile-btn {
    width: auto;
    min-width: 0;
  }

  .tracker-filter-btn .tracker-toolbar-action-label,
  .sort-mobile-label {
    display: inline;
  }

  .tracker-filter-btn .tracker-toolbar-action-count {
    display: inline-flex;
    margin-left: 1px;
  }
}

@media (max-width: 480px) {
  .tracker-toolbar {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    padding-block: 5px;
    gap: 5px;
  }

  .tracker-toolbar-leading,
  .tracker-toolbar-actions {
    display: contents;
  }

  .tracker-toolbar-organize {
    display: contents;
  }

  .tracker-toolbar-group-filter,
  .tracker-sort-mobile {
    width: 100%;
    min-width: 0;
  }

  .tracker-toolbar-action.v-btn {
    width: 100%;
    min-width: 0;
    padding-inline: 6px;
  }

  .tracker-filter-btn,
  .sort-mobile-btn {
    overflow: hidden;
  }

  .tracker-filter-btn .tracker-toolbar-action-label,
  .sort-mobile-label,
  .tracker-toolbar-quick-action .tracker-toolbar-action-label {
    display: inline;
    font-size: var(--v-text-xs);
  }

  .tracker-toolbar-action-chevron-desktop,
  .sort-mobile-chevron {
    display: none;
  }

  .tracker-filter-btn .tracker-toolbar-action-count {
    display: inline-flex;
    margin-left: 0;
  }

  .tracker-toolbar-quick-action.tracker-toolbar-action.v-btn {
    padding: 0;
  }

}
.tracker-download-progress {
  display: block;
  width: 76px;
  height: 3px;
  overflow: hidden;
  border-radius: var(--v-radius-full);
  background: rgba(255, 255, 255, 0.18);
}

.tracker-download-progress-bar {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: currentColor;
  transition: width 180ms ease;
}

</style>
