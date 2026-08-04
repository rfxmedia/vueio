<template>
  <div ref="rootEl" class="global-activity" :class="{ 'is-open': open }">
    <button
      type="button"
      class="v-btn v-btn-quiet v-btn-icon global-activity-trigger"
      :class="{ 'has-unread': unreadCount > 0 }"
      :aria-expanded="open ? 'true' : 'false'"
      aria-label="Activity notifications"
      @click.stop="toggleGlobalActivityTray"
    >
      <svg class="icon"><use href="#icon-bell" /></svg>
      <span v-if="unreadCount > 0" class="global-activity-badge">{{ unreadLabel }}</span>
    </button>

    <Transition name="v-menu-pop">
      <section v-if="open" class="global-activity-panel" role="dialog" aria-label="Activity notifications" @click.stop>
        <header class="global-activity-head">
          <div class="global-activity-head-text">
            <h2 class="global-activity-title">Activity</h2>
            <p class="global-activity-meta">{{ activityMetaLabel }}</p>
          </div>
          <div class="global-activity-head-actions">
            <button
              v-if="readStatus === 'unread' && unreadCount > 0"
              type="button"
              class="global-activity-mark-read"
              :title="unreadCount > 1 ? `Mark all ${unreadLabel} as read` : 'Mark as read'"
              aria-label="Mark all unread notifications as read"
              @click="markGlobalActivitySeen"
            >
              <svg class="icon" aria-hidden="true"><use href="#icon-check" /></svg>
              <span>Mark as read</span>
            </button>
            <button
              type="button"
              class="v-icon-action is-muted global-activity-refresh"
              :disabled="loading"
              title="Refresh"
              aria-label="Refresh activity"
              @click="refreshGlobalActivity"
            >
              <svg class="icon" :class="{ spinning: loading }"><use href="#icon-refresh" /></svg>
            </button>
          </div>
        </header>

        <div class="global-activity-controls">
          <div class="v-tabs v-tabs--segmented global-activity-read-toggle" role="tablist" aria-label="Notification read state">
            <button
              v-for="option in readStatusOptions"
              :key="option.value"
              type="button"
              class="v-tab-btn global-activity-read-option"
              :class="{
                active: readStatus === option.value,
                'is-unread-option': option.value === 'unread',
                'is-read-option': option.value === 'read',
              }"
              role="tab"
              :aria-selected="readStatus === option.value ? 'true' : 'false'"
              @click="setGlobalActivityReadStatus(option.value)"
            >
              <span>{{ option.label }}</span>
              <span v-if="option.value === 'unread' && unreadCount > 0" class="v-tab-btn__count">{{ unreadLabel }}</span>
            </button>
          </div>

          <div v-if="items.length" class="global-activity-filters" role="tablist" aria-label="Activity filters">
            <button
              v-for="filter in visibleFilters"
              :key="filter.value"
              type="button"
              class="global-activity-filter"
              :class="{ active: activeFilter === filter.value }"
              role="tab"
              :aria-selected="activeFilter === filter.value ? 'true' : 'false'"
              :title="`${filter.label}: ${countForFilter(filter.value)}`"
              @click="activeFilter = filter.value"
            >
              <svg class="icon"><use :href="filter.icon" /></svg>
              <span class="global-activity-filter-label">{{ filter.label }}</span>
              <span class="global-activity-filter-count">{{ countForFilter(filter.value) }}</span>
            </button>
          </div>
        </div>

        <div v-if="loading && !items.length" class="global-activity-empty">
          <svg class="icon spinning"><use href="#icon-loader" /></svg>
          <span>Loading activity</span>
        </div>

        <div v-else-if="!items.length" class="global-activity-empty">
          <svg class="icon"><use :href="readStatus === 'read' ? '#icon-check' : '#icon-bell'" /></svg>
          <span>{{ emptyStateLabel }}</span>
        </div>

        <div v-else-if="!filteredItems.length" class="global-activity-empty">
          <svg class="icon"><use :href="activeFilterIcon" /></svg>
          <span>No {{ activeFilterLabel.toLowerCase() }} activity yet</span>
        </div>

        <ol v-else class="global-activity-list">
          <li v-for="section in groupedItems" :key="section.key" class="global-activity-day">
            <header class="global-activity-day-head">
              <span class="global-activity-day-label v-section-label">{{ section.label }}</span>
              <span class="v-eyebrow global-activity-day-detail">{{ section.detail }}</span>
            </header>
            <ol class="global-activity-project-list">
              <li
                v-for="project in section.projects"
                :key="project.key"
                class="global-activity-project"
                :class="{ 'has-unread': readStatus === 'unread', 'is-read-group': readStatus === 'read' }"
              >
                <button
                  type="button"
                  class="global-activity-project-head"
                  :aria-label="`Open ${project.title}`"
                  @click="activateProject(project)"
                >
                  <span
                    class="global-activity-project-thumb"
                    :class="{ 'has-thumb': project.thumbnailUrl }"
                    aria-hidden="true"
                  >
                    <span class="global-activity-project-thumb-fallback">
                      {{ initialsFor(project.title || project.key) }}
                    </span>
                    <img
                      v-if="project.thumbnailUrl"
                      :src="project.thumbnailUrl"
                      alt=""
                      loading="lazy"
                      @error="hideBrokenThumbnail"
                    >
                  </span>
                  <span class="global-activity-project-copy">
                    <span class="global-activity-project-title-row">
                      <span class="global-activity-project-title v-truncate">{{ project.title }}</span>
                      <span class="global-activity-project-count">{{ project.countLabel }}</span>
                    </span>
                    <span class="global-activity-project-detail v-truncate">{{ project.detail }}</span>
                  </span>
                </button>
                <ol class="global-activity-day-list">
                  <template v-for="entry in project.entries" :key="entry.key">
                    <li
                      v-if="entry.kind === 'bundle'"
                      class="global-activity-bundle"
                      :class="{ 'is-open': isBundleExpanded(entry.key), 'is-read': readStatus === 'read' }"
                      :style="eventBadgeStyle(entry.event_type)"
                    >
                      <button
                        type="button"
                        class="global-activity-bundle-toggle"
                        :aria-expanded="isBundleExpanded(entry.key) ? 'true' : 'false'"
                        @click="toggleBundle(entry.key)"
                      >
                        <span class="global-activity-bundle-icon" aria-hidden="true">
                          <svg class="icon"><use :href="eventIcon(entry.event_type)" /></svg>
                        </span>
                        <span class="global-activity-bundle-copy">
                          <span class="global-activity-bundle-title">{{ entry.title }}</span>
                          <span class="global-activity-bundle-meta">{{ entry.detail }}</span>
                        </span>
                        <span class="global-activity-bundle-side">
                          <span class="global-activity-bundle-count">{{ entry.items.length }}</span>
                          <svg class="icon global-activity-bundle-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
                        </span>
                      </button>
                      <Transition name="global-activity-bundle-expand">
                        <ol v-if="isBundleExpanded(entry.key)" class="global-activity-bundle-items">
                        <li
                          v-for="item in entry.items"
                          :key="item.id"
                          class="global-activity-item is-in-bundle"
                          :class="{
                            'is-actionable': canActivate(item),
                            'is-read': readStatus === 'read',
                          }"
                          :style="eventBadgeStyle(item.event_type)"
                          :role="canActivate(item) ? 'button' : undefined"
                          :tabindex="canActivate(item) ? 0 : undefined"
                          :aria-label="canActivate(item) ? `Open ${displaySummary(item)}` : undefined"
                          @click="activateItem(item)"
                          @keydown.enter.prevent="activateItem(item)"
                          @keydown.space.prevent="activateItem(item)"
                        >
                          <span class="global-activity-item-icon" aria-hidden="true">
                            <svg class="icon"><use :href="eventIcon(item.event_type)" /></svg>
                          </span>
                          <div class="global-activity-item-body">
                            <p class="global-activity-summary">
                              <span class="global-activity-summary-main">
                                <span>{{ displaySummary(item) }}</span>
                                <span v-if="showPrimaryShotChip(item)" class="v-tag v-tag--accent">{{ primaryShotLabel(item) }}</span>
                              </span>
                              <svg v-if="canActivate(item)" class="icon global-activity-open-icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
                            </p>
                            <p v-if="contextText(item)" class="global-activity-context">
                              {{ trimContext(contextText(item)) }}
                            </p>
                            <div class="global-activity-foot">
                              <span class="global-activity-actor">
                                <span class="global-activity-avatar" :style="avatarStyle(item.actor_id || item.actor_name)">
                                  {{ initialsFor(item.actor_name) }}
                                </span>
                                <span class="v-truncate">{{ actorLabel(item) }}</span>
                              </span>
                              <span class="global-activity-foot-dot" aria-hidden="true"></span>
                              <span class="global-activity-scope v-truncate">{{ item.tracker_name || 'Tracker' }}</span>
                              <span class="global-activity-foot-dot" aria-hidden="true"></span>
                              <span :title="absoluteTimestamp(item.created_at)">{{ relativeTimestamp(item.created_at) }}</span>
                              <span v-if="item.group_count > 1" class="v-tag v-tag--accent">{{ item.group_count }} updates</span>
                            </div>
                          </div>
                        </li>
                        </ol>
                      </Transition>
                    </li>
                    <li
                      v-else
                      class="global-activity-item"
                      :class="{
                        'is-actionable': canActivate(entry.item),
                        'is-read': readStatus === 'read',
                      }"
                      :style="eventBadgeStyle(entry.item.event_type)"
                      :role="canActivate(entry.item) ? 'button' : undefined"
                      :tabindex="canActivate(entry.item) ? 0 : undefined"
                      :aria-label="canActivate(entry.item) ? `Open ${displaySummary(entry.item)}` : undefined"
                      @click="activateItem(entry.item)"
                      @keydown.enter.prevent="activateItem(entry.item)"
                      @keydown.space.prevent="activateItem(entry.item)"
                    >
                      <span class="global-activity-item-icon" aria-hidden="true">
                        <svg class="icon"><use :href="eventIcon(entry.item.event_type)" /></svg>
                      </span>
                      <div class="global-activity-item-body">
                        <p class="global-activity-summary">
                          <span class="global-activity-summary-main">
                            <span>{{ displaySummary(entry.item) }}</span>
                            <span v-if="showPrimaryShotChip(entry.item)" class="v-tag v-tag--accent">{{ primaryShotLabel(entry.item) }}</span>
                          </span>
                          <svg v-if="canActivate(entry.item)" class="icon global-activity-open-icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
                        </p>
                        <p v-if="contextText(entry.item)" class="global-activity-context">
                          {{ trimContext(contextText(entry.item)) }}
                        </p>
                        <div class="global-activity-foot">
                          <span class="global-activity-actor">
                            <span class="global-activity-avatar" :style="avatarStyle(entry.item.actor_id || entry.item.actor_name)">
                              {{ initialsFor(entry.item.actor_name) }}
                            </span>
                            <span class="v-truncate">{{ actorLabel(entry.item) }}</span>
                          </span>
                          <span class="global-activity-foot-dot" aria-hidden="true"></span>
                          <span class="global-activity-scope v-truncate">{{ entry.item.tracker_name || 'Tracker' }}</span>
                          <span class="global-activity-foot-dot" aria-hidden="true"></span>
                          <span :title="absoluteTimestamp(entry.item.created_at)">{{ relativeTimestamp(entry.item.created_at) }}</span>
                          <span v-if="entry.item.group_count > 1" class="v-tag v-tag--accent">{{ entry.item.group_count }} updates</span>
                        </div>
                      </div>
                    </li>
                  </template>
                </ol>
              </li>
            </ol>
          </li>
        </ol>

        <button
          v-if="hasMore"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm global-activity-more"
          :disabled="loading"
          @click="loadMoreGlobalActivity"
        >
          <svg v-if="loading" class="icon spinning"><use href="#icon-loader" /></svg>
          <span>{{ loading ? 'Loading' : 'Load more' }}</span>
        </button>
      </section>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useOutsideClick } from '../../composables/useOutsideClick'
import { getTrackerEventIcon } from '../../lib/trackerCatalogs'
import {
  formatActivityAbsoluteTimestamp as absoluteTimestamp,
  formatActivityRelativeTimestamp as relativeTimestamp,
  formatLocaleDate,
  toDate,
} from '../../utils/formatters'
import { useActivityStore } from '../../ownership/activity'

const {
  globalActivityOpen: open,
  globalActivityItems: items,
  globalActivityLoading: loading,
  globalActivityHasMore: hasMore,
  globalActivityUnreadCount: unreadCount,
  globalActivityReadStatus: readStatus,
  setGlobalActivityReadStatus,
  toggleGlobalActivityTray,
  closeGlobalActivityTray,
  refreshGlobalActivity,
  loadMoreGlobalActivity,
  markGlobalActivitySeen,
  openGlobalActivityTarget,
} = useActivityStore()

const PALETTE = {
  versions: 'var(--v-info)',
  comments: 'color-mix(in srgb, var(--v-info) 62%, var(--v-text-secondary))',
  assignments: 'var(--v-warning)',
  status: 'var(--v-accent)',
  updates: 'color-mix(in srgb, var(--v-info) 52%, var(--v-accent))',
  default: 'var(--v-text-muted)',
}

const AVATAR_HUES = [
  'var(--v-accent)',
  'var(--v-info)',
  'color-mix(in srgb, var(--v-accent) 58%, var(--v-info))',
  'color-mix(in srgb, var(--v-info) 64%, var(--v-text-secondary))',
  'color-mix(in srgb, var(--v-accent) 48%, var(--v-text-secondary))',
  'var(--v-warning)',
]
const GROUP_WINDOW_SECONDS = 30 * 60
const rootEl = ref(null)
const activeFilter = ref('all')
const expandedBundles = ref(new Set())
const readStatusOptions = [
  { value: 'unread', label: 'Unread' },
  { value: 'read', label: 'Read' },
]

useOutsideClick(rootEl, closeGlobalActivityTray, {
  enabled: open,
  escape: true,
})

const filters = [
  { value: 'all', label: 'All', icon: '#icon-activity' },
  { value: 'comments', label: 'Comments', icon: '#icon-comment' },
  { value: 'status', label: 'Status', icon: '#icon-circle' },
  { value: 'assignments', label: 'Assigned', icon: '#icon-user' },
  { value: 'versions', label: 'Versions', icon: '#icon-video' },
  { value: 'downloads', label: 'Downloads', icon: '#icon-download' },
  { value: 'updates', label: 'Updates', icon: '#icon-edit-3' },
]

const unreadLabel = computed(() => unreadCount.value > 9 ? '9+' : String(unreadCount.value))
const activeFilterConfig = computed(() => filters.find(filter => filter.value === activeFilter.value) || filters[0])
const activeFilterLabel = computed(() => activeFilterConfig.value.label)
const activeFilterIcon = computed(() => activeFilterConfig.value.icon)
const emptyStateLabel = computed(() => readStatus.value === 'read' ? 'No read notifications yet' : 'All caught up')
const visibleFilters = computed(() => filters.filter((filter) => {
  if (filter.value === 'all' || filter.value === activeFilter.value) return true
  return countForFilter(filter.value) > 0
}))
const activityMetaLabel = computed(() => {
  const count = items.value.length
  if (!count) {
    return readStatus.value === 'read' ? 'Viewing read notifications' : 'Viewing unread notifications'
  }
  const visibleCount = filteredItems.value.length
  const projectCount = new Set(filteredItems.value.map(projectKeyForItem)).size || 1
  const stateLabel = readStatus.value === 'read' ? 'read' : 'unread'
  const projectLabel = `${projectCount} ${projectCount === 1 ? 'project' : 'projects'}`
  if (activeFilter.value === 'all') {
    return `${count} ${stateLabel} ${count === 1 ? 'update' : 'updates'} from ${projectLabel}`
  }
  return `${visibleCount} of ${count} ${stateLabel} ${visibleCount === 1 ? 'update' : 'updates'} from ${projectLabel}`
})
const filteredItems = computed(() => {
  if (activeFilter.value === 'all') return items.value
  return items.value.filter(item => activityFilterForEvent(item.event_type) === activeFilter.value)
})
const smartGroupedItems = computed(() => groupActivityItems(filteredItems.value))
const groupedItems = computed(() => {
  const groups = []
  const groupMap = new Map()
  smartGroupedItems.value.forEach((item) => {
    const date = toDate(item.created_at, { unit: 'seconds' }) || new Date(NaN)
    const key = Number.isNaN(date.getTime()) ? 'unknown' : [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0'),
    ].join('-')
    if (!groupMap.has(key)) {
      const group = {
        key,
        label: dateGroupLabel(date),
        detail: dateGroupDetail(date),
        projects: [],
        _projectMap: new Map(),
      }
      groupMap.set(key, group)
      groups.push(group)
    }
    const group = groupMap.get(key)
    const projectKey = projectKeyForItem(item)
    if (!group._projectMap.has(projectKey)) {
      const project = {
        key: projectKey,
        title: item.project_title || 'Project',
        thumbnailUrl: projectThumbnailUrl(item),
        detail: '',
        countLabel: '',
        items: [],
        entries: [],
      }
      group._projectMap.set(projectKey, project)
      group.projects.push(project)
    }
    const project = group._projectMap.get(projectKey)
    project.items.push(item)
  })
  groups.forEach((group) => {
    group.projects.forEach((project) => {
      project.countLabel = countLabel(activityCountForItems(project.items))
      project.detail = projectDetailForItems(project.items)
      project.entries = bundleProjectItems(project.items, `${group.key}|${project.key}`)
    })
  })
  return groups.map(({ _projectMap, ...group }) => group)
})

function activityFilterForEvent(eventType) {
  if ([
    'version_added',
    'versions_bulk_updated',
    'version_published',
    'version_kept_internal',
    'version_removed_from_shares',
    'brief_file_uploaded',
    'shots_imported',
  ].includes(eventType)) return 'versions'
  if (['comment_added', 'comment_resolved', 'comment_deleted'].includes(eventType)) return 'comments'
  if (eventType === 'assignee_changed') return 'assignments'
  if (['status_changed', 'status_changed_bulk'].includes(eventType)) return 'status'
  if (eventType === 'download_started') return 'downloads'
  return 'updates'
}

function countForFilter(filterValue) {
  if (filterValue === 'all') return items.value.length
  return items.value.filter(item => activityFilterForEvent(item.event_type) === filterValue).length
}

function groupActivityItems(items) {
  const grouped = []
  items.forEach((item) => {
    const groupKey = groupingKeyForItem(item)
    const latestGroup = grouped[grouped.length - 1]
    if (
      groupKey &&
      latestGroup?._group_key === groupKey &&
      Math.abs(Number(latestGroup.created_at || 0) - Number(item.created_at || 0)) <= GROUP_WINDOW_SECONDS
    ) {
      latestGroup.group_count += 1
      latestGroup.group_items.push(item)
      latestGroup._actor_names.add(item.actor_name || 'Someone')
      latestGroup._shot_codes.add(item.payload?.shot_code || item.target?.shot_code || item.shot_id || '')
      latestGroup._summaries.push(item.summary)
      return
    }

    grouped.push({
      ...item,
      group_count: 1,
      group_items: [item],
      _group_key: groupKey,
      _actor_names: new Set([item.actor_name || 'Someone']),
      _shot_codes: new Set([item.payload?.shot_code || item.target?.shot_code || item.shot_id || '']),
      _summaries: [item.summary],
    })
  })
  return grouped
}

function groupingKeyForItem(item) {
  if (!item?.event_type || isBulkEvent(item.event_type)) return ''
  const projectId = item.project_id || item.target?.project_id || 'project'
  const trackerId = item.tracker_id || item.tracker_name || item.target?.tracker_id || item.target?.tracker_ref || 'tracker'
  const shotId = item.shot_id || item.target?.shot_id || item.payload?.shot_code || 'tracker'
  const actorId = item.event_type === 'comment_added' ? 'anyone' : (item.actor_id || item.actor_name || 'someone')
  return [
    projectId,
    trackerId,
    item.event_type,
    actorId,
    groupingValueForItem(item),
    shotId,
  ].join('|')
}

function groupingValueForItem(item) {
  if (item.event_type === 'status_changed') return item.payload?.new_value || item.payload?.new_label || ''
  if (item.event_type === 'assignee_changed') return Array.isArray(item.payload?.assignee_user_ids)
    ? item.payload.assignee_user_ids.join(',')
    : (item.payload?.assignee_id || item.payload?.assignee_name || item.payload?.new_value || '')
  if (item.event_type === 'category_changed') return item.payload?.new_value || item.payload?.tag || item.payload?.category || ''
  return ''
}

function isBulkEvent(eventType) {
  return ['shot_reordered', 'shots_imported', 'versions_bulk_updated', 'status_changed_bulk', 'shots_bulk_updated', 'shots_deleted_bulk'].includes(eventType)
}

function bundleProjectItems(items, projectKey) {
  const buckets = []
  const bucketMap = new Map()

  items.forEach((item, index) => {
    const bucketKey = bundleGroupKeyForItem(item)
    if (!bucketMap.has(bucketKey)) {
      const bucket = {
        key: bucketKey,
        firstIndex: index,
        event_type: item.event_type,
        sourceItems: [],
        items: [],
      }
      bucketMap.set(bucketKey, bucket)
      buckets.push(bucket)
    }

    const bucket = bucketMap.get(bucketKey)
    bucket.sourceItems.push(item)
    bucket.items.push(...flattenActivityItem(item))
  })

  return buckets
    .sort((a, b) => a.firstIndex - b.firstIndex)
    .flatMap((bucket) => {
      if (bucket.items.length <= 1) {
        return [{
          kind: 'item',
          key: bucket.sourceItems[0]?.id || `${projectKey}|${bucket.key}|${bucket.firstIndex}`,
          item: bucket.sourceItems[0],
        }]
      }

      return [{
        kind: 'bundle',
        key: `${projectKey}|${bucket.key}|${bucket.items[0]?.id || bucket.items[0]?.created_at || bucket.firstIndex}`,
        event_type: bucket.event_type,
        title: bundleTitleForItems(bucket.event_type, bucket.items),
        detail: bundleDetailForItems(bucket.items),
        items: bucket.items,
      }]
    })
}

function bundleGroupKeyForItem(item) {
  return item?.event_type || 'activity'
}

function flattenActivityItem(item) {
  return Array.isArray(item?.group_items) && item.group_items.length ? item.group_items : [item]
}

function isBundleExpanded(key) {
  return expandedBundles.value.has(key)
}

function toggleBundle(key) {
  const next = new Set(expandedBundles.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedBundles.value = next
}

function bundleTitleForItems(eventType, items) {
  const count = items.length
  if (eventType === 'comment_added') return `${count} new ${pluralize('comment', count)}`
  if (eventType === 'comment_resolved') return `${count} resolved ${pluralize('comment', count)}`
  if (eventType === 'comment_deleted') return `${count} deleted ${pluralize('comment', count)}`
  if (eventType === 'version_added') return `Added ${count} ${pluralize('version', count)}`
  if (eventType === 'versions_bulk_updated') return `${count} version ${count === 1 ? 'batch' : 'batches'}`
  if (eventType === 'status_changed' || eventType === 'status_changed_bulk') return `${count} status ${count === 1 ? 'change' : 'changes'}`
  if (eventType === 'assignee_changed') return `${count} assignment ${count === 1 ? 'change' : 'changes'}`
  if (eventType === 'category_changed') return `${count} tag ${count === 1 ? 'change' : 'changes'}`
  if (eventType === 'brief_changed') return `${count} brief ${count === 1 ? 'update' : 'updates'}`
  if (eventType === 'brief_file_uploaded') return `${count} brief ${pluralize('attachment', count)}`
  if (eventType === 'shot_created') return `${count} new ${pluralize('shot', count)}`
  if (eventType === 'shot_deleted' || eventType === 'shots_deleted_bulk') return `${count} deleted ${pluralize('shot', count)}`
  if (eventType === 'shot_archived') return `${count} archived ${pluralize('shot', count)}`
  if (eventType === 'shot_restored') return `${count} restored ${pluralize('shot', count)}`
  if (eventType === 'shots_imported') return `${count} import ${count === 1 ? 'event' : 'events'}`
  return `${count} related ${pluralize('update', count)}`
}

function bundleDetailForItems(items) {
  const firstItem = items[0]
  return [
    actorSummaryForItems(items),
    targetSummaryForItems(items),
    firstItem?.tracker_name || firstItem?.target?.tracker_name || 'Tracker',
    relativeTimestamp(firstItem?.created_at),
  ].filter(Boolean).join(' · ')
}

function actorSummaryForItems(items) {
  const actors = uniqueValues(items.map(item => item?.actor_name || 'Someone'))
  if (actors.length <= 1) return actors[0] || 'Someone'
  return `${actors.length} people`
}

function targetSummaryForItems(items) {
  const shotCodes = uniqueValues(items.map(item => item?.payload?.shot_code || item?.target?.shot_code || item?.shot_id || ''))
  if (shotCodes.length === 1) return shotCodes[0]
  if (shotCodes.length > 1) return `${shotCodes.length} shots`
  const trackerNames = uniqueValues(items.map(item => item?.tracker_name || item?.target?.tracker_name || ''))
  if (trackerNames.length === 1) return trackerNames[0]
  return ''
}

function uniqueValues(values) {
  return Array.from(new Set(values.map(value => String(value || '').trim()).filter(Boolean)))
}

function pluralize(noun, count) {
  return count === 1 ? noun : `${noun}s`
}

function displaySummary(item) {
  if (!item?.group_count || item.group_count <= 1) return item?.summary || ''
  const count = item.group_count
  const shotCodes = uniqueSetValues(item._shot_codes)
  const eventType = item.event_type
  const shotLabel = shotCodes.length === 1 ? ` on ${shotCodes[0]}` : ''
  if (eventType === 'comment_added') return `${count} new comments${shotLabel}`
  if (eventType === 'status_changed') {
    const status = item.payload?.new_label || item.payload?.new_value
    return `Changed status ${count} times${shotLabel}${status ? ` to ${status}` : ''}`
  }
  if (eventType === 'assignee_changed') return `Updated assignment ${count} times${shotLabel}`
  if (eventType === 'category_changed') return `Updated tag ${count} times${shotLabel}`
  if (eventType === 'version_added') return `Added ${count} versions${shotLabel}`
  if (eventType === 'brief_changed') return `Updated brief ${count} times${shotLabel}`
  if (eventType === 'brief_file_uploaded') return `Uploaded ${count} brief attachments${shotLabel}`
  return `${count} related updates`
}

function uniqueSetValues(setValue) {
  return Array.from(setValue || []).filter(Boolean)
}

function projectKeyForItem(item) {
  return String(item?.project_id || item?.target?.project_id || item?.project_title || 'project')
}

function projectDetailForItems(items) {
  const bucketCounts = new Map()
  items.forEach((item) => {
    const label = filterLabel(activityFilterForEvent(item.event_type))
    bucketCounts.set(label, (bucketCounts.get(label) || 0) + activityCountForItems([item]))
  })
  return Array.from(bucketCounts.entries())
    .slice(0, 3)
    .map(([label, count]) => `${count} ${label}`)
    .join(' · ')
}

function activityCountForItems(items) {
  return items.reduce((sum, item) => sum + Math.max(1, Number(item?.group_count || 1)), 0)
}

function filterLabel(filterValue) {
  return filters.find(filter => filter.value === filterValue)?.label.toLowerCase() || 'updates'
}

function countLabel(count) {
  return `${count} ${count === 1 ? 'update' : 'updates'}`
}

function primaryShotLabel(item) {
  const shotCodes = uniqueSetValues(item?._shot_codes)
  if (shotCodes.length === 1) return shotCodes[0]
  return item?.payload?.shot_code || item?.target?.shot_code || item?.shot_id || ''
}

function showPrimaryShotChip(item) {
  const shotLabel = primaryShotLabel(item)
  if (!shotLabel) return false
  return !String(displaySummary(item) || '').toLowerCase().includes(String(shotLabel).toLowerCase())
}

function actorLabel(item) {
  if (!item?.group_count || item.group_count <= 1) return item?.actor_name || 'Someone'
  const actorCount = uniqueSetValues(item._actor_names).length
  if (actorCount <= 1) return item.actor_name || 'Someone'
  return `${actorCount} people`
}

function canActivate(item) {
  return Boolean(item?.target?.project_id && (item.target.tracker_ref || item.tracker_name || item.target.tracker_id))
}

function activateProject(project) {
  if (!project?.key) return
  openGlobalActivityTarget({
    id: `project-${project.key}`,
    project_id: project.key,
    project_title: project.title,
    target: {
      type: 'project',
      project_id: project.key,
    },
  })
}

function activateItem(item) {
  if (!canActivate(item)) return
  openGlobalActivityTarget(item.group_items?.[0] || item)
}

function contextText(item) {
  return item?.payload?.body || item?.payload?.comment_body || item?.payload?.comment_preview || ''
}

function startOfToday() {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today
}

function dateGroupLabel(date) {
  if (Number.isNaN(date.getTime())) return 'Earlier'
  const today = startOfToday()
  const target = new Date(date)
  target.setHours(0, 0, 0, 0)
  const diffDays = Math.round((today - target) / 86400000)
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return formatLocaleDate(date, { options: { weekday: 'long' } })
  return formatLocaleDate(date, { options: { month: 'long', day: 'numeric' } })
}

function dateGroupDetail(date) {
  if (Number.isNaN(date.getTime())) return ''
  return formatLocaleDate(date, { options: { month: 'short', day: 'numeric', year: 'numeric' } })
}

function eventIcon(eventType) {
  return getTrackerEventIcon(eventType)
}

function eventBadgeStyle(eventType) {
  const baseColor = PALETTE[activityFilterForEvent(eventType)] || PALETTE.default
  return {
    '--global-activity-event-color': baseColor,
  }
}

function projectThumbnailUrl(item) {
  const projectId = item?.project_id || item?.target?.project_id
  if (!projectId) return ''
  const params = new URLSearchParams({ entity_type: 'project' })
  return `/api/horizons/projects/${encodeURIComponent(projectId)}/thumbnail/resolved?${params.toString()}`
}

function hideBrokenThumbnail(event) {
  event.target.style.display = 'none'
}

function hashString(value) {
  let hash = 0
  const seed = String(value ?? '')
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  }
  return hash
}

function avatarStyle(seed) {
  const hue = AVATAR_HUES[hashString(seed || 'user') % AVATAR_HUES.length]
  return {
    '--global-activity-avatar-color': hue,
  }
}

function initialsFor(name) {
  const source = String(name || '').trim()
  if (!source) return '?'
  return source.split(/\s+/).slice(0, 2).map(part => part.charAt(0).toUpperCase()).join('') || '?'
}

function trimContext(text) {
  const value = String(text || '').trim()
  if (value.length <= 120) return value
  return `${value.slice(0, 120).trimEnd()}...`
}

</script>

<style scoped>
/* ─── Trigger ─────────────────────────────────────────────────────────────── */

.global-activity {
  position: relative;
  flex: 0 0 auto;
}

.global-activity-trigger {
  position: relative;
}

.global-activity-trigger.has-unread {
  color: var(--v-text);
}

.global-activity-badge {
  position: absolute;
  top: 2px;
  right: 1px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--v-accent);
  color: var(--v-bg-black);
  font-size: var(--v-text-3xs);
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

/* ─── Panel ───────────────────────────────────────────────────────────────── */

.global-activity-panel {
  --global-activity-safe-top: env(safe-area-inset-top, 0px);
  --global-activity-safe-bottom: env(safe-area-inset-bottom, 0px);
  --global-activity-top-offset: calc(var(--v-shell-header-height, 56px) + 10px + var(--global-activity-safe-top));
  --global-activity-bottom-offset: calc(24px + var(--global-activity-safe-bottom));
  --global-activity-motion-fast: 140ms;
  --global-activity-motion-med: 220ms;
  --global-activity-motion-ease: var(--v-ease-emphasized);

  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 10020;
  width: min(420px, calc(100vw - 28px));
  max-height: calc(100svh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset));
  display: flex;
  flex-direction: column;
  padding: 14px 6px 6px;
  border: 1px solid var(--v-surface-border-strong);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-modal-shadow);
  color: var(--v-text);
  overflow: hidden;
  overscroll-behavior: contain;
  animation: global-activity-panel-in var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

@supports (height: 100dvh) {
  .global-activity-panel {
    max-height: calc(100dvh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset));
  }
}

/* ─── Header ──────────────────────────────────────────────────────────────── */

.global-activity-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 0 6px 12px;
  flex-shrink: 0;
}

.global-activity-head-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.global-activity-title,
.global-activity-meta,
.global-activity-summary,
.global-activity-scope,
.global-activity-context {
  margin: 0;
}

.global-activity-title {
  color: var(--v-text);
  font-size: var(--v-text-xl);
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.2;
}

.global-activity-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.35;
}

.global-activity-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  margin-top: 2px;
}

.global-activity-head-actions .v-icon-action {
  width: 30px;
  min-width: 30px;
  height: 30px;
  min-height: 30px;
}

.global-activity-head-actions .v-icon-action .icon {
  width: 14px;
  height: 14px;
}

.global-activity-mark-read {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-mark-read .icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.global-activity-mark-read:hover {
  background: var(--v-bg-hover);
  color: var(--v-text);
}

.global-activity-mark-read:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

/* ─── Controls ────────────────────────────────────────────────────────────── */

.global-activity-controls {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: 0 6px 10px;
  flex-shrink: 0;
}

.global-activity-read-toggle {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px;
  width: 100%;
  padding: 3px;
  border-radius: var(--v-button-radius);
  border: 1px solid var(--v-surface-border-soft);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.global-activity-read-option {
  min-width: 0;
  min-height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 700;
  letter-spacing: 0;
  text-transform: none;
  transition: none;
}

.global-activity-read-option:hover:not(.active) {
  color: var(--v-text-secondary);
  background: transparent;
}

.global-activity-read-option.active {
  background: var(--v-surface-raised);
  color: var(--v-text);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.05) inset, 0 1px 6px rgba(0, 0, 0, 0.12);
}

.global-activity-read-option.is-unread-option.active {
  color: var(--v-accent);
}

.global-activity-read-option .v-tab-btn__count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  background: color-mix(in srgb, var(--v-text) 8%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
}

.global-activity-read-option.is-unread-option.active .v-tab-btn__count {
  background: var(--v-accent);
  color: var(--v-bg-black);
}

.global-activity-filters {
  display: flex;
  align-items: center;
  gap: var(--v-space-1);
  margin: 0 -2px;
  padding: 1px 2px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.global-activity-filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  min-height: 26px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  cursor: pointer;
  transition: none;
}

.global-activity-filter:hover:not(.active) {
  color: var(--v-text-secondary);
  background: var(--v-bg-hover);
}

.global-activity-filter.active {
  color: var(--v-text);
  background: var(--v-surface-inline);
}

.global-activity-filter .icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
  opacity: 0.8;
}

.global-activity-filter.active .icon {
  opacity: 1;
}

.global-activity-filter-label {
  white-space: nowrap;
}

.global-activity-filter-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 7%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}

.global-activity-filter.active .global-activity-filter-count {
  background: color-mix(in srgb, var(--v-accent) 18%, transparent);
  color: var(--v-accent);
}

/* ─── Spinners ────────────────────────────────────────────────────────────── */

.global-activity-refresh .icon.spinning,
.global-activity-empty .icon.spinning,
.global-activity-more .icon.spinning {
  animation: global-activity-spin 1s linear infinite;
}

/* ─── Empty state ─────────────────────────────────────────────────────────── */

.global-activity-empty {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-3);
  margin: 0 6px;
  padding: var(--v-space-6);
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  font-weight: 500;
}

.global-activity-empty .icon {
  width: 24px;
  height: 24px;
  padding: 14px;
  box-sizing: content-box;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
  color: color-mix(in srgb, var(--v-text-muted) 80%, transparent);
}

/* ─── List ────────────────────────────────────────────────────────────────── */

.global-activity-list {
  list-style: none;
  margin: 0;
  padding: 0 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  min-height: 0;
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  touch-action: pan-y;
}

.global-activity-day,
.global-activity-project-list,
.global-activity-project,
.global-activity-day-list,
.global-activity-bundle,
.global-activity-bundle-items {
  list-style: none;
  margin: 0;
  padding: 0;
}

.global-activity-day {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  min-width: 0;
  max-width: 100%;
}

/* ─── Day header ──────────────────────────────────────────────────────────── */

.global-activity-day-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--v-space-3);
  margin: 0 -6px;
  padding: 10px 10px 8px;
  background: var(--v-surface-canvas);
  box-shadow: 0 6px 10px -6px var(--v-surface-canvas);
}

/* Recedes behind the day label it annotates. */
.global-activity-day-detail {
  opacity: 0.75;
}

/* ─── Project group ───────────────────────────────────────────────────────── */

.global-activity-project-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  max-width: 100%;
}

.global-activity-project {
  --spine-color: color-mix(in srgb, var(--v-text) 18%, transparent);
  --spine-fade: color-mix(in srgb, var(--v-text) 12%, transparent);

  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  padding: 0;
  background: transparent;
  border: 0;
  min-width: 0;
  max-width: 100%;
  transition:
    opacity var(--global-activity-motion-med) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

.global-activity-project.has-unread {
  --spine-color: var(--v-accent);
  --spine-fade: color-mix(in srgb, var(--v-accent) 28%, transparent);
}

.global-activity-project.is-read-group {
  --spine-color: color-mix(in srgb, var(--v-text) 22%, transparent);
  --spine-fade: color-mix(in srgb, var(--v-text) 10%, transparent);
}

.global-activity-project-head {
  width: 100%;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 6px 4px 6px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  outline: none;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-project-head:hover,
.global-activity-project-head:focus-visible {
  background: var(--v-surface-tint-hover);
}

.global-activity-project-head:focus-visible {
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.global-activity-project-thumb {
  position: relative;
  width: 36px;
  height: 28px;
  border-radius: var(--v-radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(135deg, var(--v-surface-inline-strong), var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 6%, transparent);
  transition: box-shadow var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

.global-activity-project:hover .global-activity-project-thumb {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 9%, transparent), 0 6px 14px rgba(0, 0, 0, 0.16);
}

.global-activity-project-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.global-activity-project-thumb::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 55%, rgba(0, 0, 0, 0.16));
  pointer-events: none;
}

.global-activity-project-thumb-fallback {
  position: relative;
  z-index: 1;
  color: color-mix(in srgb, var(--v-text-muted) 90%, transparent);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1;
}

.global-activity-project-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.global-activity-project-title-row {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.global-activity-project-title {
  min-width: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
}

.global-activity-project-count {
  flex: 0 0 auto;
  min-height: 18px;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  border: 0;
  background: color-mix(in srgb, var(--v-text) 7%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-project.has-unread .global-activity-project-count {
  background: color-mix(in srgb, var(--v-accent) 16%, transparent);
  color: var(--v-accent);
}

.global-activity-project-detail {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  line-height: 1.3;
}

/* ─── Project body (timeline) ─────────────────────────────────────────────── */

.global-activity-day-list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-left: 18px;
  padding-left: 18px;
  border-left: 1.5px solid var(--spine-color);
  transition: border-color var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

.global-activity-day-list::after {
  content: '';
  position: absolute;
  left: -1.5px;
  bottom: -1px;
  width: 1.5px;
  height: 18px;
  background: linear-gradient(180deg, var(--spine-color), transparent);
}

/* ─── Item ────────────────────────────────────────────────────────────────── */

.global-activity-item {
  --global-activity-event-color: var(--v-text-muted);

  position: relative;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
  margin: 0;
  padding: 9px 8px 11px;
  border: 0;
  border-radius: var(--v-radius-md);
  background: transparent;
  box-shadow: none;
  min-width: 0;
  max-width: 100%;
  outline: none;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

/* Hairline dividers between adjacent rows (inset so hover stays rounded) */
.global-activity-item + .global-activity-item::before,
.global-activity-bundle + .global-activity-item::before,
.global-activity-item + .global-activity-bundle > .global-activity-bundle-toggle::before,
.global-activity-bundle + .global-activity-bundle > .global-activity-bundle-toggle::before {
  content: '';
  position: absolute;
  top: 0;
  left: 8px;
  right: 8px;
  height: 1px;
  background: var(--v-divider-subtle);
  pointer-events: none;
}

.global-activity-item.is-actionable {
  cursor: pointer;
}

.global-activity-item.is-actionable:hover {
  background: var(--v-bg-hover);
}

.global-activity-item.is-actionable:focus-visible {
  background: var(--v-bg-hover);
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--v-accent) 50%, transparent);
}


.global-activity-item-icon {
  position: relative;
  width: 22px;
  height: 22px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  grid-column: 1;
  grid-row: 1;
  margin-top: 1px;
  background: color-mix(in srgb, var(--global-activity-event-color) 14%, transparent);
  color: var(--global-activity-event-color);
  box-shadow: 0 0 0 3px var(--v-surface-canvas);
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-item-icon::before {
  content: '';
  position: absolute;
  left: -26px;
  top: 50%;
  width: 24px;
  height: 1.5px;
  background: var(--spine-color);
  transform: translateY(-50%);
  border-radius: var(--v-radius-full);
}

.global-activity-item-icon .icon {
  width: 12px;
  height: 12px;
}

.global-activity-item-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  grid-column: 2;
}

.global-activity-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 600;
  line-height: 1.4;
}

.global-activity-summary span {
  min-width: 0;
}

.global-activity-summary-main {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.global-activity-open-icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
  margin-top: var(--v-space-1);
  color: var(--v-text-muted);
  opacity: 0;
  transform: translateX(-2px);
  transition:
    opacity var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.global-activity-item.is-actionable:hover .global-activity-open-icon,
.global-activity-item.is-actionable:focus-visible .global-activity-open-icon {
  opacity: 1;
  transform: translateX(0);
}

.global-activity-context {
  margin: 2px 0 0;
  padding: 6px 10px;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-text) 4%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 400;
  line-height: 1.45;
}

.global-activity-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin-top: 1px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 500;
}

.global-activity-actor {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 170px;
  color: var(--v-text-secondary);
  font-weight: 600;
}

.global-activity-foot-dot {
  width: 2px;
  height: 2px;
  border-radius: var(--v-radius-full);
  background: var(--v-text-muted);
  opacity: 0.55;
  flex: 0 0 auto;
}

.global-activity-scope {
  min-width: 0;
  max-width: 130px;
}

.global-activity-avatar {
  --global-activity-avatar-color: var(--v-accent);

  width: 16px;
  height: 16px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  font-size: var(--v-text-3xs);
  font-weight: 800;
  border: 0;
  background: color-mix(in srgb, var(--global-activity-avatar-color) 16%, transparent);
  color: var(--global-activity-avatar-color);
}

/* ─── Bundle (collapsible group of similar events) ────────────────────────── */

.global-activity-bundle {
  --global-activity-event-color: var(--v-text-muted);
  position: relative;
  border: 0;
  border-radius: var(--v-radius-md);
  background: transparent;
  box-shadow: none;
  overflow: visible;
}

.global-activity-bundle-toggle {
  position: relative;
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 8px 10px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text);
  font-family: var(--v-font);
  text-align: left;
  cursor: pointer;
  outline: none;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-bundle-toggle:hover {
  background: var(--v-bg-hover);
}

.global-activity-bundle-toggle:focus-visible {
  background: var(--v-bg-hover);
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--v-accent) 50%, transparent);
}

.global-activity-bundle-icon {
  position: relative;
  width: 22px;
  height: 22px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--global-activity-event-color) 14%, transparent);
  color: var(--global-activity-event-color);
  box-shadow: 0 0 0 3px var(--v-surface-canvas);
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-bundle-icon::before {
  content: '';
  position: absolute;
  left: -26px;
  top: 50%;
  width: 24px;
  height: 1.5px;
  background: var(--spine-color);
  transform: translateY(-50%);
  border-radius: var(--v-radius-full);
}

.global-activity-bundle-icon .icon {
  width: 12px;
  height: 12px;
}

.global-activity-bundle-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.global-activity-bundle-title {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 700;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-activity-bundle-meta {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 500;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-activity-bundle-side {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--v-text-muted);
}

.global-activity-bundle-count {
  min-width: 20px;
  height: 18px;
  padding: 0 7px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--global-activity-event-color) 16%, transparent);
  color: color-mix(in srgb, var(--global-activity-event-color) 88%, var(--v-text));
  font-size: var(--v-text-2xs);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-bundle-chevron {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
  transition:
    color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

.global-activity-bundle.is-open .global-activity-bundle-chevron {
  transform: rotate(180deg);
}

.global-activity-bundle-toggle:hover .global-activity-bundle-chevron {
  color: var(--v-text-secondary);
}

.global-activity-bundle-items {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-left: 11px;
  padding: 2px 0 4px 16px;
  border-left: 1px dashed color-mix(in srgb, var(--global-activity-event-color) 30%, var(--v-divider-subtle));
}

.global-activity-bundle-items .global-activity-item {
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 9px;
  padding: 8px 8px 9px;
}

.global-activity-bundle-items .global-activity-item-icon {
  width: 18px;
  height: 18px;
  margin-top: 2px;
  background: transparent;
  box-shadow: none;
  color: var(--global-activity-event-color);
}

.global-activity-bundle-items .global-activity-item-icon::before {
  display: none;
}

.global-activity-bundle-items .global-activity-item-icon .icon {
  width: 11px;
  height: 11px;
}

.global-activity-bundle-expand-enter-active,
.global-activity-bundle-expand-leave-active {
  overflow: hidden;
  transform-origin: top;
  transition:
    opacity var(--global-activity-motion-med) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-med) var(--global-activity-motion-ease),
    max-height var(--global-activity-motion-med) var(--global-activity-motion-ease);
}

.global-activity-bundle-expand-enter-from,
.global-activity-bundle-expand-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-4px) scaleY(0.96);
}

.global-activity-bundle-expand-enter-to,
.global-activity-bundle-expand-leave-from {
  max-height: 420px;
  opacity: 1;
  transform: translateY(0) scaleY(1);
}

/* ─── Load more ───────────────────────────────────────────────────────────── */

.global-activity-more {
  margin: 4px 6px 4px;
  width: calc(100% - 12px);
  flex-shrink: 0;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    border-color var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

@keyframes global-activity-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes global-activity-panel-in {
  from {
    opacity: 0;
    transform: translateY(-5px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .global-activity-panel,
  .global-activity-empty .icon {
    animation: none !important;
  }

  .global-activity-panel *,
  .global-activity-bundle-expand-enter-active,
  .global-activity-bundle-expand-leave-active {
    transition-duration: 1ms !important;
  }

  .global-activity-mark-read:hover,
  .global-activity-read-option.active,
  .global-activity-filter:hover:not(.active),
  .global-activity-filter.active,
  .global-activity-project:hover .global-activity-project-thumb,
  .global-activity-project:hover .global-activity-project-count,
  .global-activity-item.is-actionable:hover,
  .global-activity-item.is-actionable:hover .global-activity-item-icon,
  .global-activity-bundle-toggle:hover,
  .global-activity-bundle-toggle:hover .global-activity-bundle-icon,
  .global-activity-bundle-toggle:hover .global-activity-bundle-count,
  .global-activity-more:hover:not(:disabled) {
    transform: none !important;
  }
}

/* ─── Responsive ──────────────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .global-activity-trigger {
    width: 44px;
    min-width: 44px;
    height: 44px;
    min-height: 44px;
  }

  .global-activity-panel {
    position: fixed;
    --global-activity-top-offset: calc(var(--v-shell-header-height, 56px) + 8px + var(--global-activity-safe-top));
    --global-activity-bottom-offset: calc(8px + var(--global-activity-safe-bottom));
    top: var(--global-activity-top-offset);
    right: max(12px, env(safe-area-inset-right, 0px));
    left: max(12px, env(safe-area-inset-left, 0px));
    width: auto;
    height: auto;
    min-height: 0;
    max-height: min(700px, calc(100svh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset)));
    border-radius: var(--v-radius-lg);
    padding-bottom: calc(6px + var(--global-activity-safe-bottom));
    overflow-x: hidden;
    touch-action: pan-y;
  }

  @supports (height: 100dvh) {
    .global-activity-panel {
      max-height: min(700px, calc(100dvh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset)));
    }
  }

  .global-activity-head-actions .v-icon-action,
  .global-activity-mark-read,
  .global-activity-read-option,
  .global-activity-filter,
  .global-activity-more {
    min-height: 44px;
  }

  .global-activity-head-actions .v-icon-action {
    width: 44px;
    min-width: 44px;
    height: 44px;
  }

  .global-activity-mark-read {
    padding: 0 13px;
  }

  .global-activity-read-toggle {
    border-radius: var(--v-button-radius);
  }

  .global-activity-read-option {
    border-radius: var(--v-button-radius);
  }

  .global-activity-filters {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
    margin: 0;
    padding: 0;
    overflow: visible;
  }

  .global-activity-filter {
    justify-content: flex-start;
    width: 100%;
    padding: 0 10px;
    border: 1px solid transparent;
    background: color-mix(in srgb, var(--v-text) 4%, transparent);
  }

  .global-activity-filter:hover:not(.active) {
    border-color: var(--v-control-border);
  }

  .global-activity-filter.active {
    border-color: var(--v-control-border-active);
  }

  .global-activity-filter-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .global-activity-filter-count {
    margin-left: auto;
  }

  .global-activity-list {
    padding-right: var(--v-space-1);
    overflow-x: hidden;
    touch-action: pan-y;
  }

  .global-activity-project-head,
  .global-activity-bundle-toggle,
  .global-activity-item {
    min-height: 44px;
  }
}

@media (max-width: 430px) {
  .global-activity-panel {
    padding: 14px 4px 4px;
  }

  .global-activity-head {
    padding: 0 6px 10px;
    flex-wrap: wrap;
  }

  .global-activity-head-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .global-activity-controls {
    padding: 0 4px 8px;
  }

  .global-activity-filters {
    grid-template-columns: 1fr;
  }
}
</style>
