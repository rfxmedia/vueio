<template>
  <div ref="rootEl" class="global-activity" :class="{ 'is-open': open }">
    <slot
      name="trigger"
      :open="open"
      :unread-count="unreadCount"
      :unread-label="unreadLabel"
      :trigger-aria-label="triggerAriaLabel"
      panel-id="global-activity-panel"
      :toggle="toggleGlobalActivityTray"
    >
      <button
        type="button"
        class="v-btn v-btn-quiet v-btn-icon global-activity-trigger"
        :class="{ 'has-unread': unreadCount > 0 }"
        aria-haspopup="dialog"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-controls="open ? 'global-activity-panel' : undefined"
        :aria-label="triggerAriaLabel"
        @click.stop="toggleGlobalActivityTray"
      >
        <svg class="icon"><use href="#icon-bell" /></svg>
        <span v-if="unreadCount > 0" class="global-activity-badge" aria-hidden="true">{{ unreadLabel }}</span>
      </button>
    </slot>

    <Transition name="v-menu-pop">
      <section
        v-if="open"
        id="global-activity-panel"
        class="global-activity-panel"
        role="dialog"
        aria-labelledby="global-activity-title"
        aria-describedby="global-activity-meta"
        :aria-busy="loading ? 'true' : 'false'"
        @click.stop
      >
        <header class="global-activity-head">
          <div class="global-activity-head-text">
            <h2 id="global-activity-title" class="global-activity-title">Notifications</h2>
            <p id="global-activity-meta" class="global-activity-meta">{{ activityMetaLabel }}</p>
          </div>
          <div class="global-activity-head-actions">
            <button
              v-if="readStatus === 'unread' && unreadCount > 0"
              type="button"
              class="global-activity-mark-read"
              :disabled="markingRead"
              :title="unreadCount > 1 ? `Mark all ${unreadCount} as read` : 'Mark as read'"
              aria-label="Mark all unread notifications as read"
              @click="handleMarkAllRead"
            >
              <svg class="icon" :class="{ spinning: markingRead }" aria-hidden="true"><use :href="markingRead ? '#icon-loader' : '#icon-check'" /></svg>
              <span>{{ markingRead ? 'Marking read' : 'Mark all read' }}</span>
            </button>
            <button
              type="button"
              class="v-icon-action is-muted global-activity-refresh"
              :disabled="loading"
              title="Refresh notifications"
              aria-label="Refresh notifications"
              @click="refreshGlobalActivity"
            >
              <svg class="icon" :class="{ spinning: loading }"><use href="#icon-refresh" /></svg>
            </button>
            <button
              type="button"
              class="v-icon-action is-muted global-activity-close"
              title="Close notifications"
              aria-label="Close notifications"
              @click="closeGlobalActivityTray"
            >
              <svg class="icon"><use href="#icon-close" /></svg>
            </button>
          </div>
        </header>

        <div class="global-activity-controls">
          <VTabs
            class="global-activity-read-toggle"
            :tabs="readStatusTabs"
            :model-value="readStatus"
            variant="segmented"
            :full-width="true"
            aria-label="Notification inbox"
            @update:model-value="handleReadStatusChange"
          />

          <label v-if="items.length" class="global-activity-filter-control">
            <span class="v-sr-only">Filter notifications by activity type</span>
            <svg class="icon global-activity-filter-icon" aria-hidden="true"><use :href="activeFilterIcon" /></svg>
            <span class="global-activity-filter-value">{{ activeFilterLabel }}</span>
            <span class="global-activity-filter-count" aria-hidden="true">{{ countForFilter(activeFilter) }}</span>
            <svg class="icon global-activity-filter-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
            <select v-model="activeFilter" class="global-activity-filter-select" aria-label="Filter notifications by activity type">
              <option v-for="filter in visibleFilters" :key="filter.value" :value="filter.value">
                {{ filter.label }} ({{ countForFilter(filter.value) }})
              </option>
            </select>
          </label>
        </div>

        <div v-if="loading && !items.length" class="global-activity-skeleton" role="status" aria-live="polite">
          <span class="v-sr-only">Loading notifications</span>
          <div v-for="index in 3" :key="index" class="global-activity-skeleton-group" :style="{ '--skeleton-index': index }">
            <span class="global-activity-skeleton-thumb"></span>
            <span class="global-activity-skeleton-line is-title"></span>
            <span class="global-activity-skeleton-line is-meta"></span>
            <span class="global-activity-skeleton-row"></span>
            <span class="global-activity-skeleton-row is-short"></span>
          </div>
        </div>

        <div v-else-if="loadError && !items.length" class="global-activity-empty is-error" role="alert">
          <span class="global-activity-empty-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-alert" /></svg>
          </span>
          <div class="global-activity-empty-copy">
            <strong>Notifications could not load</strong>
            <span>Check your connection, then try again.</span>
          </div>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" :disabled="loading" @click="refreshGlobalActivity">
            Try again
          </button>
        </div>

        <div v-else-if="!items.length" class="global-activity-empty">
          <span class="global-activity-empty-icon" aria-hidden="true">
            <svg class="icon"><use :href="readStatus === 'read' ? '#icon-clock' : '#icon-check'" /></svg>
          </span>
          <div class="global-activity-empty-copy">
            <strong>{{ emptyStateTitle }}</strong>
            <span>{{ emptyStateCopy }}</span>
          </div>
        </div>

        <div v-else-if="!filteredItems.length" class="global-activity-empty">
          <span class="global-activity-empty-icon" aria-hidden="true">
            <svg class="icon"><use :href="activeFilterIcon" /></svg>
          </span>
          <div class="global-activity-empty-copy">
            <strong>No {{ activeFilterLabel.toLowerCase() }} here</strong>
            <span>Choose another activity type or return to everything.</span>
          </div>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="activeFilter = 'all'">
            Show all activity
          </button>
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
                              <span class="global-activity-scope v-truncate">{{ item.tracker_name || 'Tracker' }}</span>
                              <span class="global-activity-time" :title="absoluteTimestamp(item.created_at)">{{ relativeTimestamp(item.created_at) }}</span>
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
                          <span class="global-activity-scope v-truncate">{{ entry.item.tracker_name || 'Tracker' }}</span>
                          <span class="global-activity-time" :title="absoluteTimestamp(entry.item.created_at)">{{ relativeTimestamp(entry.item.created_at) }}</span>
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
          v-if="hasMore && items.length"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm global-activity-more"
          :disabled="loading"
          @click="loadMoreGlobalActivity"
        >
          <svg v-if="loading" class="icon spinning"><use href="#icon-loader" /></svg>
          <span>{{ loading ? 'Loading' : 'Load more' }}</span>
        </button>

        <slot v-if="$slots.footer" name="footer" :close="closeGlobalActivityTray" />
      </section>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VTabs } from '../primitives'
import { useOutsideClick } from '../../composables/useOutsideClick'
import { getTrackerEventColor, getTrackerEventIcon } from '../../lib/trackerCatalogs'
import { identityColorStyle } from '../../utils/semanticColors'
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
  globalActivityError: loadError,
  setGlobalActivityReadStatus,
  toggleGlobalActivityTray,
  closeGlobalActivityTray,
  refreshGlobalActivity,
  loadMoreGlobalActivity,
  markGlobalActivitySeen,
  openGlobalActivityTarget,
} = useActivityStore()

const GROUP_WINDOW_SECONDS = 30 * 60
const rootEl = ref(null)
const activeFilter = ref('all')
const expandedBundles = ref(new Set())
const markingRead = ref(false)

useOutsideClick(rootEl, closeGlobalActivityTray, {
  enabled: open,
  escape: true,
})

const filters = [
  { value: 'all', label: 'All activity', icon: '#icon-activity' },
  { value: 'comments', label: 'Comments', icon: '#icon-comment' },
  { value: 'status', label: 'Status', icon: '#icon-circle' },
  { value: 'assignments', label: 'Assigned', icon: '#icon-user' },
  { value: 'versions', label: 'Versions', icon: '#icon-video' },
  { value: 'downloads', label: 'Downloads', icon: '#icon-download' },
  { value: 'updates', label: 'Updates', icon: '#icon-edit-3' },
]

const unreadLabel = computed(() => unreadCount.value > 9 ? '9+' : String(unreadCount.value))
const triggerAriaLabel = computed(() => unreadCount.value > 0
  ? `Notifications, ${unreadCount.value} unread`
  : 'Notifications')
const readStatusTabs = computed(() => [
  {
    value: 'unread',
    label: 'Inbox',
    icon: '#icon-inbox',
    count: unreadCount.value > 0 ? unreadLabel.value : undefined,
    disabled: loading.value,
  },
  {
    value: 'read',
    label: 'History',
    icon: '#icon-clock',
    disabled: loading.value,
  },
])
const activeFilterConfig = computed(() => filters.find(filter => filter.value === activeFilter.value) || filters[0])
const activeFilterLabel = computed(() => activeFilterConfig.value.label)
const activeFilterIcon = computed(() => activeFilterConfig.value.icon)
const emptyStateTitle = computed(() => readStatus.value === 'read' ? 'No notification history' : "You're caught up")
const emptyStateCopy = computed(() => readStatus.value === 'read'
  ? 'Notifications you mark as read will appear here.'
  : 'New comments, assignments, and review updates will appear here.')
const visibleFilters = computed(() => filters.filter((filter) => {
  if (filter.value === 'all' || filter.value === activeFilter.value) return true
  return countForFilter(filter.value) > 0
}))
const activityMetaLabel = computed(() => {
  const count = readStatus.value === 'unread'
    ? Math.max(unreadCount.value, items.value.length)
    : items.value.length
  if (!count) {
    return readStatus.value === 'read' ? 'Your read notification history' : 'Updates that need your attention'
  }
  const visibleCount = filteredItems.value.length
  if (activeFilter.value !== 'all' && visibleCount === 0) {
    const destination = readStatus.value === 'read' ? 'history' : 'inbox'
    return `No ${activeFilterLabel.value.toLowerCase()} in ${destination}`
  }
  const projectCount = new Set(filteredItems.value.map(projectKeyForItem)).size || 1
  const stateLabel = readStatus.value === 'read' ? 'read' : 'unread'
  const projectLabel = `${projectCount} ${projectCount === 1 ? 'project' : 'projects'}`
  if (activeFilter.value === 'all') {
    return `${count} ${stateLabel} across ${projectLabel}`
  }
  return `${visibleCount} ${activeFilterLabel.value.toLowerCase()} across ${projectLabel}`
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

async function handleReadStatusChange(nextStatus) {
  if (nextStatus === readStatus.value || loading.value) return
  activeFilter.value = 'all'
  expandedBundles.value = new Set()
  await setGlobalActivityReadStatus(nextStatus)
}

async function handleMarkAllRead() {
  if (markingRead.value) return
  markingRead.value = true
  try {
    await markGlobalActivitySeen()
  } finally {
    markingRead.value = false
  }
}

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
  ].filter(Boolean).join(', ')
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
    const filterValue = activityFilterForEvent(item.event_type)
    bucketCounts.set(filterValue, (bucketCounts.get(filterValue) || 0) + activityCountForItems([item]))
  })
  return Array.from(bucketCounts.entries())
    .slice(0, 3)
    .map(([filterValue, count]) => filterCountLabel(filterValue, count))
    .join(', ')
}

function activityCountForItems(items) {
  return items.reduce((sum, item) => sum + Math.max(1, Number(item?.group_count || 1)), 0)
}

function filterCountLabel(filterValue, count) {
  const nouns = {
    comments: 'comment',
    status: 'status change',
    assignments: 'assignment',
    versions: 'version',
    downloads: 'download',
    updates: 'update',
  }
  return `${count} ${pluralize(nouns[filterValue] || 'update', count)}`
}

function countLabel(count) {
  return readStatus.value === 'read'
    ? `${count} read`
    : `${count} unread`
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
  return {
    '--global-activity-event-color': getTrackerEventColor(eventType),
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

function avatarStyle(seed) {
  return identityColorStyle(seed || 'user', '--global-activity-avatar-color')
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
  width: var(--v-btn-height);
  min-width: var(--v-btn-height);
  height: var(--v-btn-height);
  min-height: var(--v-btn-height);
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  color: var(--v-text-muted);
}

.global-activity-trigger.has-unread {
  color: var(--v-text);
}

.global-activity-trigger:hover:not(:disabled),
.global-activity.is-open .global-activity-trigger {
  border-color: var(--v-control-border);
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.global-activity.is-open .global-activity-trigger {
  border-color: var(--v-control-border-active);
  background: var(--v-control-bg-active);
  color: var(--v-accent);
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
  width: min(472px, calc(100vw - 28px));
  max-height: calc(100svh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset));
  display: flex;
  flex-direction: column;
  padding: 0;
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
  padding: 16px 16px 14px;
  flex-shrink: 0;
}

.global-activity-head-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
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
  font-size: var(--v-text-2xl);
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
  margin-top: 1px;
}

.global-activity-head-actions .v-icon-action {
  width: 32px;
  min-width: 32px;
  height: 32px;
  min-height: 32px;
}

.global-activity-head-actions .v-icon-action .icon {
  width: 14px;
  height: 14px;
}

.global-activity-mark-read {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
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

.global-activity-mark-read:disabled {
  opacity: 0.55;
  cursor: wait;
}

.global-activity-mark-read:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

/* ─── Controls ────────────────────────────────────────────────────────────── */

.global-activity-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(142px, 0.62fr);
  gap: var(--v-space-2);
  padding: 10px 12px;
  border-top: 1px solid var(--v-divider-subtle);
  border-bottom: 1px solid var(--v-divider-subtle);
  background: color-mix(in srgb, var(--v-surface-panel) 72%, transparent);
  flex-shrink: 0;
}

.global-activity-read-toggle {
  min-width: 0;
  width: 100%;
}

.global-activity-read-toggle :deep(.v-tab-btn) {
  min-height: 36px;
  padding: 0 10px;
  font-size: var(--v-text-sm);
  font-weight: 700;
}

.global-activity-read-toggle :deep(.v-tab-btn.active) {
  color: var(--v-text);
}

.global-activity-read-toggle :deep(.v-tab-btn:first-child.active) {
  color: var(--v-accent);
}

.global-activity-read-toggle :deep(.v-tab-btn:last-child.active) {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inline-strong);
}

.global-activity-read-toggle :deep(.v-tab-btn__count) {
  min-width: 17px;
  height: 17px;
  padding: 0 5px;
  background: color-mix(in srgb, var(--v-accent) 18%, transparent);
  color: var(--v-accent);
  font-size: var(--v-text-2xs);
  font-weight: 800;
}

.global-activity-filter-control {
  position: relative;
  min-width: 0;
  height: 38px;
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto 12px;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-control-bg);
  box-shadow: var(--v-surface-shadow-inset);
  color: var(--v-text-secondary);
  cursor: pointer;
  transition:
    border-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-filter-control:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
}

.global-activity-filter-control:focus-within {
  border-color: var(--v-border-focus);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.global-activity-filter-icon,
.global-activity-filter-chevron {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
}

.global-activity-filter-value {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-activity-filter-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.global-activity-filter-select {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  opacity: 0;
  cursor: pointer;
}

/* ─── Feedback states ─────────────────────────────────────────────────────── */

.global-activity-close {
  display: none;
}

.global-activity-refresh .icon.spinning,
.global-activity-mark-read .icon.spinning,
.global-activity-more .icon.spinning {
  animation: global-activity-spin 1s linear infinite;
}

.global-activity-skeleton {
  min-height: 300px;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  overflow: hidden;
}

.global-activity-skeleton-group {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  grid-template-rows: 16px 12px 34px 34px;
  align-items: center;
  gap: 5px 10px;
  padding: 11px 12px 8px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-panel);
  animation: global-activity-skeleton 1.4s ease-in-out infinite alternate;
  animation-delay: calc(var(--skeleton-index) * 90ms);
}

.global-activity-skeleton-thumb,
.global-activity-skeleton-line,
.global-activity-skeleton-row {
  display: block;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text) 7%, transparent);
}

.global-activity-skeleton-thumb {
  grid-row: 1 / span 2;
  width: 42px;
  height: 32px;
}

.global-activity-skeleton-line.is-title {
  width: min(180px, 64%);
  height: 11px;
}

.global-activity-skeleton-line.is-meta {
  width: min(132px, 45%);
  height: 8px;
}

.global-activity-skeleton-row {
  grid-column: 1 / -1;
  height: 28px;
  margin-top: 2px;
  background: color-mix(in srgb, var(--v-text) 4%, transparent);
}

.global-activity-skeleton-row.is-short {
  width: 78%;
}

.global-activity-empty {
  min-height: 300px;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-3);
  padding: var(--v-space-6);
  color: var(--v-text-muted);
  text-align: center;
}

.global-activity-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--v-radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--v-accent) 12%, transparent);
  color: var(--v-accent);
}

.global-activity-empty.is-error .global-activity-empty-icon {
  background: color-mix(in srgb, var(--v-danger) 12%, transparent);
  color: var(--v-danger);
}

.global-activity-empty-icon .icon {
  width: 20px;
  height: 20px;
}

.global-activity-empty-copy {
  max-width: 32ch;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.global-activity-empty-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 700;
  line-height: 1.3;
}

.global-activity-empty-copy span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.45;
}

/* ─── Notification groups ─────────────────────────────────────────────────── */

.global-activity-list {
  width: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 16px;
  margin: 0;
  padding: 0 12px 12px;
  list-style: none;
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
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.global-activity-day {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
}

.global-activity-day-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--v-space-3);
  margin: 0 -2px;
  padding: 12px 2px 8px;
  background: var(--v-surface-canvas);
  box-shadow: 0 8px 10px -8px var(--v-surface-canvas);
}

.global-activity-day-detail {
  opacity: 0.72;
}

.global-activity-project-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.global-activity-project {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-panel);
  overflow: hidden;
  transition:
    border-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-project:hover {
  border-color: var(--v-surface-border-strong);
}

.global-activity-project-head {
  width: 100%;
  min-height: 54px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 0;
  border-radius: 0;
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

.global-activity-project-head:hover {
  background: var(--v-surface-tint-hover);
}

.global-activity-project-head:active {
  transform: scale(0.995);
}

.global-activity-project-head:focus-visible {
  box-shadow: inset 0 0 0 2px var(--v-border-focus);
}

.global-activity-project-thumb {
  position: relative;
  width: 42px;
  height: 32px;
  border-radius: var(--v-radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--v-surface-inline-strong);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 6%, transparent);
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
  background: linear-gradient(180deg, transparent 62%, rgba(0, 0, 0, 0.18));
  pointer-events: none;
}

.global-activity-project-thumb-fallback {
  position: relative;
  z-index: 1;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1;
}

.global-activity-project-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
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
  line-height: 1.25;
}

.global-activity-project-count {
  min-height: 19px;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  margin-left: auto;
  padding: 0 7px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 7%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 750;
  font-variant-numeric: tabular-nums;
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

.global-activity-day-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--v-divider-subtle);
}

/* ─── Notification rows ───────────────────────────────────────────────────── */

.global-activity-item,
.global-activity-bundle {
  --global-activity-event-color: var(--v-text-muted);
  position: relative;
}

.global-activity-item {
  min-width: 0;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 11px;
  margin: 0;
  padding: 11px 12px;
  border: 0;
  border-radius: 0;
  background: transparent;
  outline: none;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-item + .global-activity-item::before,
.global-activity-bundle + .global-activity-item::before,
.global-activity-item + .global-activity-bundle > .global-activity-bundle-toggle::before,
.global-activity-bundle + .global-activity-bundle > .global-activity-bundle-toggle::before {
  content: '';
  position: absolute;
  top: 0;
  left: 51px;
  right: 12px;
  height: 1px;
  background: var(--v-divider-subtle);
  pointer-events: none;
}

.global-activity-item.is-actionable {
  cursor: pointer;
}

.global-activity-item.is-actionable:hover,
.global-activity-bundle-toggle:hover {
  background: color-mix(in srgb, var(--global-activity-event-color) 5%, transparent);
}

.global-activity-item.is-actionable:active,
.global-activity-bundle-toggle:active {
  transform: scale(0.995);
}

.global-activity-item.is-actionable:focus-visible,
.global-activity-bundle-toggle:focus-visible {
  box-shadow: inset 0 0 0 2px var(--v-border-focus);
}

.global-activity-item-icon,
.global-activity-bundle-icon {
  position: relative;
  width: 28px;
  height: 28px;
  border-radius: var(--v-radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  background: color-mix(in srgb, var(--global-activity-event-color) 14%, transparent);
  color: var(--global-activity-event-color);
}

.global-activity-item-icon {
  grid-column: 1;
  grid-row: 1;
}

.global-activity-item-icon .icon,
.global-activity-bundle-icon .icon {
  width: 13px;
  height: 13px;
}

.global-activity-project.is-read-group .global-activity-item-icon,
.global-activity-project.is-read-group .global-activity-bundle-icon {
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
}

.global-activity-item-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  grid-column: 2;
}

.global-activity-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
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
  margin-top: 3px;
  color: var(--v-text-muted);
  opacity: 0.35;
  transform: translateX(-2px);
  transition:
    opacity var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-item.is-actionable:hover .global-activity-open-icon,
.global-activity-item.is-actionable:focus-visible .global-activity-open-icon {
  opacity: 1;
  transform: translateX(0);
}

.global-activity-context {
  margin: 1px 0 0;
  padding: 7px 9px;
  border-left: 2px solid color-mix(in srgb, var(--global-activity-event-color) 35%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 400;
  line-height: 1.45;
}

.global-activity-foot {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 10px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 500;
}

.global-activity-actor {
  min-width: 0;
  max-width: 150px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--v-text-secondary);
  font-weight: 650;
}

.global-activity-scope {
  min-width: 0;
  max-width: 130px;
}

.global-activity-time {
  margin-left: auto;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.global-activity-avatar {
  --global-activity-avatar-color: var(--v-accent);
  width: 18px;
  height: 18px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border: 0;
  background: color-mix(in srgb, var(--global-activity-avatar-color) 16%, transparent);
  color: var(--global-activity-avatar-color);
  font-size: var(--v-text-3xs);
  font-weight: 800;
}

/* ─── Bundled rows ────────────────────────────────────────────────────────── */

.global-activity-bundle {
  border: 0;
  background: transparent;
}

.global-activity-bundle-toggle {
  position: relative;
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  padding: 11px 12px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--v-text);
  font-family: var(--v-font);
  text-align: left;
  cursor: pointer;
  outline: none;
  transition:
    background-color var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    box-shadow var(--global-activity-motion-fast) var(--global-activity-motion-ease),
    transform var(--global-activity-motion-fast) var(--global-activity-motion-ease);
}

.global-activity-bundle-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.global-activity-bundle-title {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 700;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-activity-bundle-meta {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-activity-bundle-side {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--v-text-muted);
}

.global-activity-bundle-count {
  min-width: 22px;
  height: 20px;
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
  display: flex;
  flex-direction: column;
  margin: 0 8px 8px 50px;
  padding: 4px;
  border: 1px solid var(--v-divider-subtle);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  overflow: hidden;
}

.global-activity-bundle-items .global-activity-item {
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 9px;
  padding: 9px 8px;
  border-radius: var(--v-radius-sm);
}

.global-activity-bundle-items .global-activity-item + .global-activity-item::before {
  left: 37px;
  right: 8px;
}

.global-activity-bundle-items .global-activity-item-icon {
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: var(--v-radius-sm);
  background: transparent;
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
  transform: translateY(-4px) scaleY(0.97);
}

.global-activity-bundle-expand-enter-to,
.global-activity-bundle-expand-leave-from {
  max-height: 480px;
  opacity: 1;
  transform: translateY(0) scaleY(1);
}

.global-activity-more {
  width: calc(100% - 24px);
  min-height: 36px;
  flex-shrink: 0;
  margin: 0 12px 12px;
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

@keyframes global-activity-skeleton {
  from { opacity: 0.48; }
  to { opacity: 0.88; }
}

@media (prefers-reduced-motion: reduce) {
  .global-activity-panel,
  .global-activity-skeleton-group,
  .global-activity-refresh .icon.spinning,
  .global-activity-mark-read .icon.spinning,
  .global-activity-more .icon.spinning {
    animation: none !important;
  }

  .global-activity-panel *,
  .global-activity-bundle-expand-enter-active,
  .global-activity-bundle-expand-leave-active {
    transition-duration: 1ms !important;
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
    max-height: min(700px, calc(100svh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset)));
    touch-action: pan-y;
  }

  @supports (height: 100dvh) {
    .global-activity-panel {
      max-height: min(700px, calc(100dvh - var(--global-activity-top-offset) - var(--global-activity-bottom-offset)));
    }
  }

  .global-activity-close {
    display: inline-flex;
  }

  .global-activity-head-actions .v-icon-action,
  .global-activity-mark-read {
    min-height: 44px;
  }

  .global-activity-head-actions .v-icon-action {
    width: 44px;
    min-width: 44px;
    height: 44px;
  }

  .global-activity-mark-read {
    height: 44px;
    padding: 0 13px;
  }

  .global-activity-read-toggle :deep(.v-tab-btn),
  .global-activity-filter-control,
  .global-activity-more {
    min-height: 44px;
  }

  .global-activity-filter-control {
    height: 44px;
  }

  .global-activity-project-head,
  .global-activity-bundle-toggle,
  .global-activity-item {
    min-height: 44px;
  }
}

@media (max-width: 430px) {
  .global-activity-head {
    align-items: center;
    padding: 13px 12px 12px;
  }

  .global-activity-title {
    font-size: var(--v-text-xl);
  }

  .global-activity-meta {
    font-size: var(--v-text-xs);
  }

  .global-activity-controls {
    grid-template-columns: minmax(0, 1fr);
    padding: 8px 10px;
  }

  .global-activity-list {
    padding: 0 8px 10px;
  }

  .global-activity-day-head {
    margin: 0;
  }

  .global-activity-project-head,
  .global-activity-item,
  .global-activity-bundle-toggle {
    padding-right: 10px;
    padding-left: 10px;
  }

  .global-activity-bundle-items {
    margin-right: 6px;
    margin-left: 47px;
  }

  .global-activity-skeleton {
    padding: 10px;
  }
}

@media (max-width: 390px) {
  .global-activity-head-actions {
    gap: 4px;
  }

  .global-activity-mark-read {
    width: 40px;
    min-width: 40px;
    padding: 0;
    justify-content: center;
  }

  .global-activity-mark-read span {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .global-activity-head-actions .v-icon-action {
    width: 40px;
    min-width: 40px;
  }

  .global-activity-scope {
    max-width: 104px;
  }
}
</style>
