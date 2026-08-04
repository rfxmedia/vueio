<template>
  <div class="tracker-list-region">
    <div v-if="!hasAnyTrackerShots" class="v-empty-state v-empty-state-compact empty-shots">
      <svg class="icon v-empty-state-icon"><use href="#icon-project" /></svg>
      <p class="v-empty-state-title">No shots yet</p>
      <p class="v-empty-state-hint">Click “Import” to begin.</p>
    </div>

    <template v-else>
      <div v-if="trackerShotsForDisplay.length === 0" class="v-empty-state v-empty-state-compact empty-shots">
        <svg class="icon v-empty-state-icon"><use :href="hasTrackerFilters ? '#icon-search' : '#icon-inbox'" /></svg>
        <p class="v-empty-state-title">{{ activeEmptyTitle }}</p>
        <p class="v-empty-state-hint">{{ activeEmptyHint }}</p>
        <button v-if="hasTrackerFilters" class="v-btn v-btn-secondary v-btn-sm tracker-empty-action" @click="clearTrackerFilters">
          Clear filters
        </button>
      </div>

      <div
        v-else
        class="tracker-row-list"
        :class="{ 'is-grid-view': trackerDisplayMode === 'grid' }"
      >
        <div
          v-if="selectionEnabled"
          class="tracker-list-selectall"
        >
          <button
            class="tracker-header-select-btn"
            type="button"
            :aria-pressed="allVisibleSelected ? 'true' : 'false'"
            :aria-label="allVisibleSelected ? 'Deselect visible shots' : 'Select visible shots'"
            @click="toggleSelectAllVisible"
          >
            <span class="tracker-header-select-box v-checkbox-box" aria-hidden="true">
              <svg v-if="allVisibleSelected" class="icon"><use href="#icon-check" /></svg>
            </span>
            <span class="tracker-list-selectall-label">
              {{ allVisibleSelected ? 'Deselect all' : 'Select all' }}
            </span>
          </button>
        </div>

        <template
          v-for="group in activeShotGroups"
          :key="group.key"
        >
          <div
            v-if="showActiveTagGroups"
            class="tracker-tag-group-heading v-section-label v-section-label--ruled"
          >
            <span class="tracker-tag-group-dot" :style="{ backgroundColor: group.color }"></span>
            <span class="tracker-tag-group-name">{{ group.label }}</span>
            <span class="tracker-tag-group-count v-section-count">{{ group.items.length }}</span>
            <span v-if="canReorderTagGroup(group)" class="tracker-tag-group-actions">
              <button
                class="tracker-tag-reorder-btn"
                type="button"
                :disabled="!canMoveTagGroup(group, -1)"
                :aria-label="`Move ${group.label} tag up`"
                title="Move tag up"
                @click.stop="moveTagGroup(group, -1)"
              >
                <svg class="icon"><use href="#icon-chevron-up" /></svg>
              </button>
              <button
                class="tracker-tag-reorder-btn"
                type="button"
                :disabled="!canMoveTagGroup(group, 1)"
                :aria-label="`Move ${group.label} tag down`"
                title="Move tag down"
                @click.stop="moveTagGroup(group, 1)"
              >
                <svg class="icon"><use href="#icon-chevron-down" /></svg>
              </button>
            </span>
          </div>

          <TrackerRowCard
            v-for="item in group.items"
            :key="item.shot._originalId || item.shot.shot_id"
            :can-reorder-shots="canReorderShots"
            :drag-over-index="dragOverIndex"
            :index="item.index"
            :presentation="trackerDisplayMode === 'grid' ? 'grid' : 'list'"
            :selection-enabled="selectionEnabled"
            :toggle-shot-selected="toggleActiveShotSelected || toggleShotSelected"
            :shot="item.shot"
          />
        </template>
      </div>

      <section v-if="hasArchivedShots" class="tracker-archive-shelf" :class="{ 'is-open': archivedExpanded }">
        <button
          class="tracker-archive-toggle"
          type="button"
          :aria-expanded="archivedExpanded ? 'true' : 'false'"
          @click="archivedExpanded = !archivedExpanded"
        >
          <span class="tracker-archive-toggle__lead">
            <svg class="icon"><use href="#icon-inbox" /></svg>
            <span>Archived</span>
          </span>
          <span class="tracker-archive-toggle__count">{{ archivedShots.length }}</span>
          <svg class="icon tracker-archive-toggle__chevron"><use href="#icon-chevron-down" /></svg>
        </button>

        <div
          v-if="archivedExpanded"
          class="tracker-archive-list"
          :class="{ 'is-grid-view': trackerDisplayMode === 'grid' }"
        >
          <div
            v-if="archivedSelectionEnabled"
            class="tracker-list-selectall tracker-list-selectall-archive"
          >
            <button
              class="tracker-header-select-btn"
              type="button"
              :aria-pressed="allArchivedSelected ? 'true' : 'false'"
              :aria-label="allArchivedSelected ? 'Deselect archived shots' : 'Select archived shots'"
              @click="toggleSelectAllArchived"
            >
              <span class="tracker-header-select-box v-checkbox-box" aria-hidden="true">
                <svg v-if="allArchivedSelected" class="icon"><use href="#icon-check" /></svg>
              </span>
              <span class="tracker-list-selectall-label">
                {{ allArchivedSelected ? 'Deselect archived' : 'Select archived' }}
              </span>
            </button>
          </div>

          <template
            v-for="group in archivedShotGroups"
            :key="group.key"
          >
            <div
              v-if="showArchivedTagGroups"
              class="tracker-tag-group-heading v-section-label v-section-label--ruled"
            >
              <span class="tracker-tag-group-dot" :style="{ backgroundColor: group.color }"></span>
              <span class="tracker-tag-group-name">{{ group.label }}</span>
              <span class="tracker-tag-group-count v-section-count">{{ group.items.length }}</span>
              <span v-if="canReorderTagGroup(group)" class="tracker-tag-group-actions">
                <button
                  class="tracker-tag-reorder-btn"
                  type="button"
                  :disabled="!canMoveTagGroup(group, -1)"
                  :aria-label="`Move ${group.label} tag up`"
                  title="Move tag up"
                  @click.stop="moveTagGroup(group, -1)"
                >
                  <svg class="icon"><use href="#icon-chevron-up" /></svg>
                </button>
                <button
                  class="tracker-tag-reorder-btn"
                  type="button"
                  :disabled="!canMoveTagGroup(group, 1)"
                  :aria-label="`Move ${group.label} tag down`"
                  title="Move tag down"
                  @click.stop="moveTagGroup(group, 1)"
                >
                  <svg class="icon"><use href="#icon-chevron-down" /></svg>
                </button>
              </span>
            </div>

            <TrackerRowCard
              v-for="item in group.items"
              :key="item.shot.id || item.shot._originalId || item.shot.shot_id"
              :can-reorder-shots="false"
              :drag-over-index="null"
              :index="item.index"
              :presentation="trackerDisplayMode === 'grid' ? 'grid' : 'list'"
              :selection-enabled="archivedSelectionEnabled"
              :toggle-shot-selected="toggleArchivedShotSelected || toggleShotSelected"
              :shot="item.shot"
            />
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'
import TrackerRowCard from './TrackerRowCard.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  trackerDisplayMode: {
    type: String,
    default: 'list',
  },
})

const {
  allArchivedSelected,
  allVisibleSelected,
  archivedTrackerShots,
  canArchiveShots,
  canBulkUpdateAssignee,
  canBulkUpdateCategory,
  canBulkUpdateStatus,
  canCategorizeShots,
  canReorderShots,
  clearTrackerFilters,
  currentTracker,
  dragOverIndex,
  getCategoryColor,
  hasTrackerFilters,
  moveTrackerTag,
  selectionEnabled,
  shareMode,
  toggleActiveShotSelected,
  toggleArchivedShotSelected,
  toggleSelectAllArchived,
  toggleSelectAllVisible,
  toggleShotSelected,
  trackerCategories,
  trackerShotsForDisplay,
} = useTrackerStore()

const archivedExpanded = ref(false)
const archivedShots = computed(() => archivedTrackerShots.value || [])
const hasArchivedShots = computed(() => archivedShots.value.length > 0)
const hasAnyTrackerShots = computed(() => (currentTracker.value?.shots || []).length > 0)
const archivedSelectionEnabled = computed(() => (
  canArchiveShots.value ||
  canBulkUpdateStatus.value ||
  canBulkUpdateCategory.value ||
  canBulkUpdateAssignee.value
))
const activeEmptyTitle = computed(() => hasTrackerFilters.value ? 'No shots match these filters' : 'No active shots')
const activeEmptyHint = computed(() => (
  hasTrackerFilters.value
    ? 'Try adjusting the filter menu or clear everything to see all active shots.'
    : 'Archived shots are kept below and can be restored when needed.'
))

const activeShotGroups = computed(() => buildShotGroups(trackerShotsForDisplay.value || []))
const archivedShotGroups = computed(() => buildShotGroups(archivedShots.value))
const showActiveTagGroups = computed(() => shouldShowTagGroups(activeShotGroups.value))
const showArchivedTagGroups = computed(() => shouldShowTagGroups(archivedShotGroups.value))
const orderedTagKeys = computed(() => {
  const keys = []
  const seen = new Set()
  for (const category of trackerCategories.value || []) {
    const label = normalizeTagLabel(category)
    if (!label || label === 'Untagged') continue
    const key = label.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    keys.push(key)
  }
  return keys
})
const tagOrderLookup = computed(() => new Map(orderedTagKeys.value.map((key, index) => [key, index])))
const canReorderTagGroups = computed(() => (
  !shareMode.value &&
  !hasTrackerFilters.value &&
  canCategorizeShots.value &&
  typeof moveTrackerTag === 'function' &&
  orderedTagKeys.value.length > 1
))

function getShotTagLabel(shot) {
  return normalizeTagLabel(shot?.tag ?? shot?.category) || 'Untagged'
}

function normalizeTagLabel(value) {
  const raw = String(value || '').trim()
  if (!raw || raw === 'Uncategorized') return ''
  return raw
}

function shouldShowTagGroups(groups) {
  return groups.length > 1 || (groups.length === 1 && !groups[0].isUntagged)
}

function getTagOrderIndex(label) {
  if (label === 'Untagged') return Number.MAX_SAFE_INTEGER
  const key = String(label || '').toLowerCase()
  return tagOrderLookup.value.get(key) ?? Number.MAX_SAFE_INTEGER - 1
}

function canReorderTagGroup(group) {
  return canReorderTagGroups.value && group && !group.isUntagged
}

function canMoveTagGroup(group, direction) {
  if (!canReorderTagGroup(group)) return false
  const index = tagOrderLookup.value.get(String(group.label || '').toLowerCase())
  if (index === undefined) return false
  return direction < 0 ? index > 0 : index < orderedTagKeys.value.length - 1
}

function moveTagGroup(group, direction) {
  if (!canMoveTagGroup(group, direction)) return
  moveTrackerTag(group.label, direction)
}

function buildShotGroups(shots) {
  const groups = []
  const groupMap = new Map()

  ;(shots || []).forEach((shot, index) => {
    const label = getShotTagLabel(shot)
    const key = label.toLowerCase()
    let group = groupMap.get(key)
    if (!group) {
      group = {
        key,
        label,
        color: getCategoryColor?.(label) || 'var(--v-text-muted)',
        isUntagged: label === 'Untagged',
        items: [],
      }
      groupMap.set(key, group)
      groups.push(group)
    }
    group.items.push({ shot, index })
  })

  return groups.sort((left, right) => {
    const rank = getTagOrderIndex(left.label) - getTagOrderIndex(right.label)
    if (rank !== 0) return rank
    return left.label.localeCompare(right.label, undefined, { numeric: true, sensitivity: 'base' })
  })
}
</script>

<style>
.tracker-list-region {
  --tracker-list-pad-x: var(--tracker-page-gutter, 18px);
  /* Pulls the 22px hit target back so its 15px box — not the target, and not the
     1px card/button border around it — lands exactly on the page gutter. */
  --tracker-checkbox-nudge: -4.5px;
  min-width: 0;
  padding: 14px var(--tracker-list-pad-x) 40px;
}

.shot-tracker:has(.tracker-bulk-bar) .tracker-list-region {
  padding-bottom: 112px;
}

.tracker-row-list {
  --tracker-selection-width: 28px;
  --tracker-utility-width: 56px;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
}

.tracker-row-list.is-grid-view {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  align-items: start;
  gap: var(--v-space-5);
}

.tracker-row-list.is-grid-view .tracker-list-selectall {
  grid-column: 1 / -1;
}

/* Section-label styling comes from .v-section-label; this only adds the
   sticky behaviour that parks the group name under the pinned toolbar. */
.tracker-tag-group-heading {
  position: sticky;
  top: calc(var(--tracker-toolbar-height, 56px) - 1px);
  z-index: 12;
  max-width: 100%;
  min-height: 34px;
  margin: 18px 0 2px;
}

.tracker-tag-group-heading::before {
  content: '';
  position: absolute;
  inset: -4px calc(var(--tracker-list-pad-x, 18px) * -1);
  z-index: -1;
  background: var(--v-bg-base);
  -webkit-mask-image: linear-gradient(180deg, #000 0%, #000 74%, transparent 100%);
          mask-image: linear-gradient(180deg, #000 0%, #000 74%, transparent 100%);
  pointer-events: none;
}

.tracker-row-list > .tracker-tag-group-heading:first-child,
.tracker-archive-list > .tracker-tag-group-heading:first-child,
.tracker-list-selectall + .tracker-tag-group-heading {
  margin-top: 2px;
}

.tracker-row-list.is-grid-view .tracker-tag-group-heading,
.tracker-archive-list.is-grid-view .tracker-tag-group-heading {
  grid-column: 1 / -1;
}

.tracker-tag-group-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-surface-panel) 70%, transparent);
}

.tracker-tag-group-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--v-text-secondary);
}

.tracker-tag-group-actions {
  order: 91;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
  opacity: 0;
  pointer-events: none;
  transform: translateX(-2px);
  transition:
    opacity var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.tracker-tag-group-heading:hover .tracker-tag-group-actions,
.tracker-tag-group-heading:focus-within .tracker-tag-group-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.tracker-tag-reorder-btn {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    opacity var(--v-transition-fast);
}

.tracker-tag-reorder-btn:hover:not(:disabled) {
  border-color: var(--v-control-border);
  background: color-mix(in srgb, var(--v-surface-inset) 74%, transparent);
  color: var(--v-text-secondary);
}

.tracker-tag-reorder-btn:focus-visible {
  outline: none;
  border-color: color-mix(in srgb, var(--v-accent) 42%, var(--v-control-border));
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-tag-reorder-btn:disabled {
  cursor: default;
  opacity: 0.28;
}

.tracker-tag-reorder-btn .icon {
  width: 13px;
  height: 13px;
}

.empty-shots {
  min-height: 220px;
}

.tracker-empty-action {
  margin-top: var(--v-space-3);
}

.tracker-archive-shelf {
  margin-top: 28px;
  padding-top: 18px;
  border-top: 1px solid color-mix(in srgb, var(--v-surface-panel) 90%, white);
}

.tracker-archive-toggle {
  width: 100%;
  min-height: 44px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast);
}

.tracker-archive-toggle:hover {
  border-color: var(--v-control-border);
  background: color-mix(in srgb, var(--v-surface-inset) 70%, transparent);
  color: var(--v-text);
}

.tracker-archive-shelf.is-open .tracker-archive-toggle {
  color: var(--v-text-secondary);
}

.tracker-archive-toggle:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-archive-toggle__lead {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 9px;
}

.tracker-archive-toggle__lead .icon,
.tracker-archive-toggle__chevron {
  width: 14px;
  height: 14px;
}

.tracker-archive-toggle__count {
  min-width: 22px;
  height: 20px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-full);
  background: var(--v-control-bg);
  box-shadow: var(--v-surface-shadow-inset);
  color: var(--v-text-secondary);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.tracker-archive-toggle__chevron {
  transition: transform var(--v-transition-fast);
}

.tracker-archive-shelf.is-open .tracker-archive-toggle__chevron {
  transform: rotate(180deg);
}

.tracker-archive-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 0 0;
}

.tracker-archive-list.is-grid-view {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  align-items: start;
  gap: 18px;
}

.tracker-archive-list.is-grid-view .tracker-list-selectall {
  grid-column: 1 / -1;
}

/* ─── Select-all (checkbox box aligns to the page gutter) ───── */
.tracker-list-selectall {
  display: flex;
  align-items: center;
  margin: 0 0 12px;
  padding: 0;
  border-bottom: 0;
  background: transparent;
}

.tracker-list-selectall-archive {
  margin: 0 0 2px;
  padding: 0;
  border-bottom: 0;
  background: transparent;
}

.tracker-list-selectall-archive .tracker-header-select-btn {
  min-height: 34px;
}

.tracker-header-select-btn {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-height: 28px;
  padding: 0 10px 0 0;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  cursor: pointer;
  margin-left: var(--tracker-checkbox-nudge, -4.5px);
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
}

.tracker-header-select-btn:hover {
  color: var(--v-text);
}

.tracker-header-select-btn:hover .tracker-header-select-box {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inset-hover);
}

.tracker-header-select-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-header-select-box {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-sm);
  margin: 0 calc((22px - 15px) / 2);
  background: color-mix(in srgb, var(--v-bg-base) 52%, var(--v-surface-panel));
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
}

.tracker-header-select-btn[aria-pressed='true'] {
  color: var(--v-text);
}

.tracker-header-select-btn[aria-pressed='true'] .tracker-header-select-box {
  border-color: var(--v-accent);
  background: var(--v-accent);
  color: var(--v-bg-black);
}

.tracker-header-select-box .icon {
  width: 10px;
  height: 10px;
}

.tracker-list-selectall-label {
  flex: 1;
}

@media (max-width: 768px) {
  .tracker-list-region {
    --tracker-checkbox-nudge: 0px;
    padding: 8px var(--tracker-list-pad-x) var(--v-space-5);
  }

  .shot-tracker:has(.tracker-bulk-bar) .tracker-list-region {
    padding-bottom: 280px;
  }

  .tracker-row-list {
    gap: 10px;
  }

  .tracker-archive-list {
    gap: 14px;
  }

  .tracker-tag-group-heading {
    width: 100%;
    min-height: 32px;
    margin: 12px 0 2px;
    padding: 0;
    gap: 8px;
  }

  .tracker-tag-group-heading:has(.tracker-tag-group-actions) {
    min-height: 40px;
  }

  .tracker-tag-group-dot {
    width: 6px;
    height: 6px;
  }

  .tracker-tag-group-actions {
    opacity: 1;
    pointer-events: auto;
    transform: none;
    gap: var(--v-space-1);
  }

  .tracker-tag-reorder-btn {
    width: 40px;
    height: 40px;
    border-radius: var(--v-button-radius);
    border-color: color-mix(in srgb, var(--v-control-border) 76%, transparent);
    background: color-mix(in srgb, var(--v-surface-inset) 62%, transparent);
  }

  .tracker-tag-reorder-btn .icon {
    width: 13px;
    height: 13px;
  }

  .tracker-list-selectall {
    margin: 0;
    padding: 0;
  }

  .tracker-header-select-btn {
    min-height: 32px;
    padding: 0 8px 0 0;
    font-size: var(--v-text-xs);
    font-weight: 650;
  }

  .tracker-header-select-box {
    width: 16px;
    height: 16px;
    margin: 0;
  }

  .tracker-list-selectall-archive {
    margin: 0 0 2px;
    padding: 0;
  }

  .tracker-archive-shelf {
    margin-top: var(--v-space-4);
  }

  .tracker-archive-toggle {
    min-height: 48px;
    padding: 0 12px;
  }

}
</style>
