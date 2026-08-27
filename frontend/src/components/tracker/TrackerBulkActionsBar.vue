<template>
  <Transition name="v-fade">
    <div
      v-if="selectedCount > 0"
      class="tracker-bulk-bar v-surface-panel"
      :class="{ 'is-mobile': isMobile }"
      role="toolbar"
      :aria-label="ariaLabel"
      aria-live="polite"
    >
      <div class="tracker-bulk-summary">
        <span class="tracker-bulk-count">
          <span class="tracker-bulk-count-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-check" /></svg>
          </span>
          <strong>{{ selectedCount }}</strong>
          <span>{{ countLabel }}</span>
        </span>
        <button
          type="button"
          class="tracker-bulk-clear v-btn v-btn-ghost v-btn-sm"
          :disabled="bulkActionBusy"
          title="Deselect all"
          @click="clearSelection"
        >
          <svg class="icon" aria-hidden="true"><use href="#icon-close" /></svg>
          <span>Deselect</span>
        </button>
      </div>

      <div class="tracker-bulk-actions">
        <button
          v-if="canDownload"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm tracker-bulk-action tracker-bulk-download"
          :disabled="bulkActionBusy || downloadBusy || !canDownloadSelected"
          :title="canDownloadSelected ? 'Download latest versions for selected shots' : 'Selected shots have no downloadable versions'"
          @click="downloadSelected"
        >
          <span class="tracker-bulk-action-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-download" /></svg>
          </span>
          <span>Download</span>
        </button>
        <div
          v-if="canBulkUpdateStatus"
          class="tracker-bulk-menu tracker-bulk-status-select"
        >
          <TrackerInlineSelect
            tone="status"
            label="Status"
            :interactive="!bulkActionBusy"
            :flip-up="true"
            :show-chevron="!isMobile"
            :open="!isMobile && openBulkMenu === 'status'"
            @trigger="toggleBulkMenu('status')"
            @close="closeBulkMenus"
          >
            <template #leading>
              <svg class="icon tracker-bulk-status-icon" aria-hidden="true"><use href="#icon-check-square" /></svg>
            </template>
            <template #menu>
              <div class="tracker-select-list">
                <button
                  v-for="option in bulkStatusOptions"
                  :key="option.value"
                  type="button"
                  class="status-option tracker-select-option v-dropdown-item"
                  role="menuitem"
                  @click="selectBulkValue('status', option.value)"
                >
                  <span class="status-dot" :class="`dot-${option.value}`"></span>
                  <span class="tracker-select-option-label">{{ option.label }}</span>
                </button>
              </div>
            </template>
          </TrackerInlineSelect>
        </div>
        <div
          v-if="canBulkUpdateCategory"
          class="tracker-bulk-menu tracker-bulk-category-select"
        >
          <TrackerInlineSelect
            tone="category"
            label="Tag"
            :interactive="!bulkActionBusy"
            :flip-up="true"
            :show-chevron="!isMobile"
            :open="!isMobile && openBulkMenu === 'category'"
            @trigger="toggleBulkMenu('category')"
            @close="closeBulkMenus"
          >
            <template #leading>
              <svg class="icon tracker-bulk-tag-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M20 13.2 10.8 4H4v6.8L13.2 20a2 2 0 0 0 2.8 0l4-4a2 2 0 0 0 0-2.8Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" />
                <circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" />
              </svg>
            </template>
            <template #menu>
              <div class="tracker-select-list">
                <button
                  v-for="option in bulkCategoryOptions"
                  :key="option.value"
                  type="button"
                  class="category-option tracker-select-option v-dropdown-item"
                  role="menuitem"
                  @click="selectBulkValue('category', option.value)"
                >
                  <span class="category-color-indicator" :style="{ backgroundColor: getBulkCategoryColor(option.value) }"></span>
                  <span class="tracker-select-option-label">{{ option.label }}</span>
                </button>
              </div>
            </template>
          </TrackerInlineSelect>
        </div>
        <div
          v-if="canBulkUpdateAssignee"
          class="tracker-bulk-menu tracker-bulk-assignee-select"
        >
          <TrackerInlineSelect
            tone="assignee"
            label="Assign"
            :interactive="!bulkActionBusy"
            :flip-up="true"
            :show-chevron="!isMobile"
            :open="!isMobile && openBulkMenu === 'assignee'"
            @trigger="toggleBulkMenu('assignee')"
            @close="closeBulkMenus"
          >
            <template #leading>
              <svg class="icon tracker-assignee-icon"><use href="#icon-user" /></svg>
            </template>
            <template #menu>
              <div class="tracker-select-list">
                <button
                  v-for="option in bulkAssigneeOptions"
                  :key="option.value"
                  type="button"
                  class="assignee-option tracker-select-option v-dropdown-item"
                  role="menuitem"
                  @click="selectBulkValue('assignee', option.value)"
                >
                  <span class="tracker-select-option-label">{{ option.label }}</span>
                </button>
              </div>
            </template>
          </TrackerInlineSelect>
        </div>
        <button
          v-if="canArchive"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm tracker-bulk-action tracker-bulk-archive"
          :disabled="bulkActionBusy"
          title="Move selected shots to Archived"
          @click="archiveSelected"
        >
          <span class="tracker-bulk-action-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-inbox" /></svg>
          </span>
          <span>Archive</span>
        </button>
        <button
          v-if="canRestore"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm tracker-bulk-action tracker-bulk-restore"
          :disabled="bulkActionBusy"
          @click="restoreSelected"
        >
          <span class="tracker-bulk-action-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-undo" /></svg>
          </span>
          <span>Restore</span>
        </button>
        <button
          v-if="canDelete"
          type="button"
          class="v-btn v-btn-danger v-btn-sm tracker-bulk-action tracker-bulk-delete"
          :disabled="bulkActionBusy"
          title="Permanently delete selected archived shots"
          @click="deleteSelected"
        >
          <span class="tracker-bulk-action-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-trash" /></svg>
          </span>
          <span class="tracker-bulk-delete-label-desktop">Delete permanently</span>
          <span class="tracker-bulk-delete-label-mobile">Delete</span>
        </button>
      </div>
    </div>
  </Transition>

  <VModal
    v-if="isMobile"
    :modelValue="!!bulkSheet"
    size="lg"
    presentation="sheet"
    class="tracker-bulk-sheet-modal"
    @update:modelValue="setBulkSheet"
  >
    <template #header>
      <VModalHeader @close="setBulkSheet(false)">
        <div class="v-modal-header-copy">
          <h2 class="v-modal-header-title">{{ bulkSheetTitle }}</h2>
          <p class="v-modal-header-subtitle">Apply to {{ selectedCount }} selected {{ selectedCount === 1 ? 'shot' : 'shots' }}.</p>
        </div>
      </VModalHeader>
    </template>

    <div class="tracker-bulk-sheet-body">
      <button
        v-for="option in bulkSheetOptions"
        :key="option.value"
        type="button"
        class="tracker-select-option v-dropdown-item"
        @click="selectBulkValue(bulkSheet, option.value)"
      >
        <span v-if="bulkSheet === 'status'" class="status-dot" :class="`dot-${option.value}`"></span>
        <span
          v-else-if="bulkSheet === 'category'"
          class="category-color-indicator"
          :style="{ backgroundColor: getBulkCategoryColor(option.value) }"
        ></span>
        <svg v-else class="icon tracker-assignee-icon"><use href="#icon-user" /></svg>
        <span class="tracker-select-option-label">{{ option.label }}</span>
      </button>
    </div>
  </VModal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VModal, VModalHeader } from '../primitives'
import TrackerInlineSelect from './TrackerInlineSelect.vue'

const props = defineProps({
  selectedCount: { type: Number, default: 0 },
  countLabel: { type: String, default: 'selected' },
  ariaLabel: { type: String, default: 'Selected shot actions' },
  isMobile: { type: Boolean, default: false },
  canBulkUpdateStatus: { type: Boolean, default: false },
  canBulkUpdateCategory: { type: Boolean, default: false },
  canBulkUpdateAssignee: { type: Boolean, default: false },
  canDownload: { type: Boolean, default: false },
  canDownloadSelected: { type: Boolean, default: false },
  canArchive: { type: Boolean, default: false },
  canDelete: { type: Boolean, default: false },
  canRestore: { type: Boolean, default: false },
  bulkStatusOptions: { type: Array, default: () => [] },
  bulkCategoryOptions: { type: Array, default: () => [] },
  bulkAssigneeOptions: { type: Array, default: () => [] },
  bulkActionBusy: { type: Boolean, default: false },
  downloadBusy: { type: Boolean, default: false },
  trackerFilterGroups: { type: Array, default: () => [] },
  clearSelection: { type: Function, default: () => {} },
  downloadSelected: { type: Function, default: () => {} },
  bulkUpdateStatus: { type: Function, default: async () => {} },
  bulkUpdateCategory: { type: Function, default: async () => {} },
  bulkUpdateAssignee: { type: Function, default: async () => {} },
  archiveSelected: { type: Function, default: async () => {} },
  deleteSelected: { type: Function, default: async () => {} },
  restoreSelected: { type: Function, default: async () => {} },
})

const openBulkMenu = ref(null)
const bulkSheet = ref(null)

const bulkSheetTitle = computed(() => {
  if (bulkSheet.value === 'status') return 'Change status'
  if (bulkSheet.value === 'category') return 'Change tag'
  if (bulkSheet.value === 'assignee') return 'Replace assignees'
  return 'Selected shots'
})

const bulkSheetOptions = computed(() => {
  if (bulkSheet.value === 'status') return props.bulkStatusOptions
  if (bulkSheet.value === 'category') return props.bulkCategoryOptions
  if (bulkSheet.value === 'assignee') return props.bulkAssigneeOptions
  return []
})

function getBulkCategoryColor(value) {
  const categoryGroup = props.trackerFilterGroups.find(group => group.key === 'categories')
  return categoryGroup?.options?.find(option => option.value === value)?.color || 'var(--v-text-muted)'
}

function setBulkSheet(open) {
  if (!open) bulkSheet.value = null
}

function closeBulkMenus() {
  openBulkMenu.value = null
  bulkSheet.value = null
}

function toggleBulkMenu(type) {
  if (props.bulkActionBusy) return
  if (props.isMobile) {
    bulkSheet.value = type
    openBulkMenu.value = null
    return
  }
  openBulkMenu.value = openBulkMenu.value === type ? null : type
}

async function selectBulkValue(type, value) {
  if (!value) return
  closeBulkMenus()
  if (type === 'status' && props.canBulkUpdateStatus) {
    await props.bulkUpdateStatus(value)
  } else if (type === 'category' && props.canBulkUpdateCategory) {
    await props.bulkUpdateCategory(value)
  } else if (type === 'assignee' && props.canBulkUpdateAssignee) {
    await props.bulkUpdateAssignee(value)
  }
}

</script>

<style scoped>
.tracker-bulk-bar {
  position: fixed;
  z-index: calc(var(--v-z-sticky) + 20);
  bottom: max(24px, calc(env(safe-area-inset-bottom, 0px) + 24px));
  left: 50%;
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  width: max-content;
  max-width: calc(100vw - 32px);
  min-height: 54px;
  padding: 7px;
  transform: translateX(-50%);
  border-color: var(--v-surface-border-strong);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  box-shadow: var(--v-menu-shadow);
  overflow: visible;
}

.tracker-bulk-summary,
.tracker-bulk-actions {
  display: flex;
  align-items: center;
  min-width: 0;
}

.tracker-bulk-summary {
  flex: 0 0 auto;
  gap: 3px;
  min-height: 36px;
  padding: 0 8px 0 2px;
  border-right: 1px solid var(--v-divider-subtle);
}

.tracker-bulk-count {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 7px 0 3px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
  white-space: nowrap;
}

.tracker-bulk-count strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-variant-numeric: tabular-nums;
}

.tracker-bulk-count-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  flex: 0 0 28px;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--v-accent) 28%, transparent);
  border-radius: var(--v-radius-md);
  background: var(--v-accent-muted);
  color: var(--v-accent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--v-accent) 12%, transparent);
}

.tracker-bulk-count-icon .icon {
  width: 13px;
  height: 13px;
  stroke-width: 2.4;
}

.tracker-bulk-clear {
  min-height: 32px;
  padding-inline: 9px;
  color: var(--v-text-muted);
}

.tracker-bulk-clear .icon {
  width: 11px;
  height: 11px;
}

.tracker-bulk-actions {
  flex: 1 1 auto;
  gap: 6px;
}

.tracker-bulk-action {
  min-height: 36px;
  gap: 6px;
}

.tracker-bulk-action .icon {
  width: 13px;
  height: 13px;
}

.tracker-bulk-action span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracker-bulk-delete-label-mobile {
  display: none;
}

.tracker-bulk-menu {
  width: clamp(112px, 11vw, 132px);
  flex: 0 0 clamp(112px, 11vw, 132px);
  min-width: 0;
}

.tracker-bulk-assignee-select {
  width: clamp(118px, 12vw, 140px);
  flex-basis: clamp(118px, 12vw, 140px);
}

.tracker-bulk-menu :deep(.tracker-inline-select-trigger) {
  min-height: 36px;
  height: 36px;
  padding: 0 11px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-raised);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  color: var(--v-text);
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast),
    color var(--v-transition-fast);
}

.tracker-bulk-menu :deep(.tracker-inline-select-trigger:hover) {
  border-color: var(--v-surface-border-strong);
  background: var(--v-surface-raised-strong);
}

.tracker-bulk-menu :deep(.tracker-inline-select-leading) {
  color: var(--v-text-secondary);
}

.tracker-bulk-menu :deep(.tracker-inline-select-label) {
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.tracker-bulk-menu :deep(.tracker-inline-select-chevron) {
  width: 10px;
  height: 10px;
}

.tracker-bulk-menu :deep(.tracker-inline-select-menu) {
  min-width: 230px;
}

.tracker-bulk-status-icon,
.tracker-bulk-tag-icon,
.tracker-bulk-menu :deep(.tracker-assignee-icon) {
  width: 14px;
  height: 14px;
}

.tracker-bulk-sheet-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px));
}

.tracker-bulk-sheet-body .tracker-select-option {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  padding: 0 10px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 500;
  text-align: left;
}

.tracker-bulk-sheet-body .tracker-select-option:hover,
.tracker-bulk-sheet-body .tracker-select-option:focus-visible {
  background: var(--v-bg-hover);
}

.tracker-bulk-sheet-body .status-dot,
.tracker-bulk-sheet-body .category-color-indicator {
  width: 9px;
  height: 9px;
  flex: 0 0 9px;
  border-radius: var(--v-radius-full);
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 8%, transparent);
}

.tracker-bulk-sheet-body .dot-not_started { background: var(--v-status-draft); }
.tracker-bulk-sheet-body .dot-in_progress { background: var(--v-status-active); }
.tracker-bulk-sheet-body .dot-waiting_review { background: var(--v-status-review); }
.tracker-bulk-sheet-body .dot-edits_requested { background: var(--v-status-hold); }
.tracker-bulk-sheet-body .dot-done { background: var(--v-status-done); }

.tracker-bulk-sheet-body .tracker-assignee-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  color: var(--v-text-secondary);
}

@media (max-width: 900px) {
  .tracker-bulk-bar {
    right: 14px;
    left: 14px;
    width: auto;
    max-width: none;
    transform: none;
  }
}

@media (max-width: 768px) {
  .tracker-bulk-sheet-modal.v-modal.is-sheet {
    min-height: 0;
    max-height: min(70dvh, 620px);
  }

  .tracker-bulk-sheet-modal.v-modal.is-sheet :deep(.v-modal-body) {
    flex: 0 1 auto;
    padding: 8px 12px 4px;
  }

  .tracker-bulk-bar {
    right: 10px;
    bottom: max(10px, calc(env(safe-area-inset-bottom, 0px) + 10px));
    left: 10px;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    width: auto;
    min-height: 0;
    padding: 6px;
    border-color: var(--v-surface-border-strong);
    background: var(--v-surface-canvas);
  }

  .tracker-bulk-summary {
    width: 100%;
    min-height: 40px;
    justify-content: space-between;
    padding: 0 4px 0 6px;
    border: 1px solid var(--v-surface-border-soft);
    border-radius: var(--v-button-radius);
    background: var(--v-modal-header-bg);
  }

  .tracker-bulk-count {
    min-height: 38px;
    gap: 6px;
    padding: 0;
  }

  .tracker-bulk-count-icon {
    width: 24px;
    height: 24px;
    flex-basis: 24px;
    border-radius: var(--v-radius-sm);
  }

  .tracker-bulk-count-icon .icon {
    width: 11px;
    height: 11px;
  }

  .tracker-bulk-clear {
    min-height: var(--v-btn-height-sm);
    height: var(--v-btn-height-sm);
    padding-inline: var(--v-space-2);
    font-size: var(--v-text-xs);
  }

  .tracker-bulk-clear .icon {
    display: none;
  }

  .tracker-bulk-actions {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: minmax(0, 1fr);
    gap: 5px;
    width: 100%;
  }

  .tracker-bulk-actions > * {
    min-width: 0;
    height: 56px;
  }

  .tracker-bulk-menu {
    width: auto;
    min-width: 0;
    flex: none;
  }

  .tracker-bulk-action {
    width: 100%;
    min-width: 0;
    min-height: 56px;
    flex-direction: column;
    gap: 5px;
    padding: 0 3px;
    border-radius: var(--v-button-radius);
    font-size: var(--v-text-xs);
    line-height: 1;
    box-shadow: var(--v-surface-shadow-inset);
  }

  .tracker-bulk-action-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--v-text-secondary);
  }

  .tracker-bulk-action-icon .icon {
    width: 15px;
    height: 15px;
  }

  .tracker-bulk-menu :deep(.tracker-inline-select) {
    height: 100%;
    --tracker-select-gap: 5px;
    --tracker-select-leading-size: 15px;
  }

  .tracker-bulk-menu :deep(.tracker-inline-select-trigger) {
    min-height: 56px;
    height: 56px;
    justify-content: center;
    flex-direction: column;
    gap: 5px;
    padding: 0 3px;
    border-radius: var(--v-button-radius);
    background: var(--v-surface-raised);
  }

  .tracker-bulk-menu :deep(.tracker-inline-select-label) {
    flex: 0 0 auto;
    width: 100%;
    font-size: var(--v-text-xs);
    line-height: 1;
    text-align: center;
  }

  .tracker-bulk-status-icon,
  .tracker-bulk-tag-icon,
  .tracker-bulk-menu :deep(.tracker-assignee-icon) {
    width: 15px;
    height: 15px;
  }

  .tracker-bulk-delete {
    border-color: var(--v-danger-border);
    background: var(--v-danger-bg);
    color: var(--v-danger-text);
  }

  .tracker-bulk-delete .tracker-bulk-action-icon {
    color: var(--v-danger-text);
  }

  .tracker-bulk-delete-label-desktop {
    display: none;
  }

  .tracker-bulk-delete-label-mobile {
    display: inline;
  }
}
</style>
