<template>
  <section class="td-panel" :class="{ 'is-mobile': isMobile }">
    <!-- ─── Header ────────────────────────────────────────────────────── -->
    <header class="td-head">
      <div class="td-head-copy">
        <p class="td-eyebrow v-eyebrow">Tracker pulse</p>
        <h2 class="td-title v-truncate">{{ currentTracker?.name || 'Vue Tracker' }}</h2>
        <p v-if="headerMeta" class="td-meta">{{ headerMeta }}</p>
      </div>
      <button
        v-if="closeable"
        type="button"
        class="v-btn v-btn-secondary v-btn-icon td-close"
        aria-label="Close details"
        @click="$emit('close')"
      >
        <svg class="icon"><use href="#icon-close" /></svg>
      </button>
    </header>

    <!-- ─── Mode tabs (Overview / Activity) ───────────────────────────── -->
    <VTabs
      v-model="panelMode"
      class="td-mode-tabs"
      :tabs="panelTabs"
      variant="segmented"
      full-width
    />

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- OVERVIEW                                                          -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <div v-if="panelMode === 'overview'" class="td-body td-overview">
      <!-- Progress hero ------------------------------------------------ -->
      <section class="td-progress-card v-card">
        <div class="td-progress-row">
          <div class="td-progress-headline">
            <span class="td-progress-pct">{{ completionPercent }}<span class="td-progress-pct-sign">%</span></span>
            <span class="td-progress-label">Delivered</span>
          </div>
          <div class="td-progress-summary">
            <strong class="td-progress-numerator">{{ doneShotsCount.toLocaleString() }}<span>/{{ totalShots.toLocaleString() }}</span></strong>
            <span class="td-progress-caption">{{ progressCaption }}</span>
          </div>
        </div>

        <div class="td-progress-track" :aria-label="`Shot status breakdown — ${completionPercent}% complete`">
          <span
            v-for="segment in progressSegments"
            :key="segment.status"
            class="td-progress-segment"
            :style="{ width: `${segment.percent}%`, background: segment.color }"
            :title="`${segment.label}: ${segment.count}`"
          ></span>
          <span v-if="!totalShots" class="td-progress-empty">No shots yet</span>
        </div>

        <ul class="td-progress-legend" v-if="totalShots">
          <li v-for="segment in statusBreakdown" :key="segment.status">
            <span class="td-progress-legend-dot" :style="{ background: statusColor(segment.status) }" aria-hidden="true"></span>
            <span class="td-progress-legend-label v-truncate">{{ segment.label }}</span>
            <span class="td-progress-legend-count">{{ segment.count }}</span>
          </li>
        </ul>
      </section>

      <!-- Vital stats grid -------------------------------------------- -->
      <section class="td-stats">
        <article class="td-stat-tile v-card">
          <span class="td-stat-icon"><svg class="icon"><use href="#icon-target" /></svg></span>
          <div class="td-stat-copy">
            <span class="td-stat-value">{{ totalShots.toLocaleString() }}</span>
            <span class="td-stat-label">Shots</span>
          </div>
        </article>
        <article class="td-stat-tile v-card">
          <span class="td-stat-icon"><svg class="icon"><use href="#icon-video" /></svg></span>
          <div class="td-stat-copy">
            <span class="td-stat-value">{{ totalVersions.toLocaleString() }}</span>
            <span class="td-stat-label">Versions</span>
          </div>
        </article>
        <article class="td-stat-tile v-card">
          <span class="td-stat-icon"><svg class="icon"><use href="#icon-clock" /></svg></span>
          <div class="td-stat-copy">
            <span class="td-stat-value">{{ totalDurationLabel }}</span>
            <span class="td-stat-label">Runtime</span>
          </div>
        </article>
        <article class="td-stat-tile v-card">
          <span class="td-stat-icon"><svg class="icon"><use href="#icon-trending-up" /></svg></span>
          <div class="td-stat-copy">
            <span class="td-stat-value">{{ averageVersionsPerShotLabel }}<span class="td-stat-suffix">×</span></span>
            <span class="td-stat-label">Versions / shot</span>
          </div>
        </article>
      </section>

      <!-- Status breakdown ------------------------------------------- -->
      <section class="td-section">
        <div class="td-section-head">
          <p class="td-section-eyebrow v-section-label">Status breakdown</p>
          <span class="td-section-meta">{{ totalShots.toLocaleString() }} shots</span>
        </div>
        <div class="td-status-list v-card">
          <div
            v-for="item in statusBreakdown"
            :key="item.status"
            class="td-status-row"
          >
            <span class="td-status-dot" :style="{ background: statusColor(item.status) }" aria-hidden="true"></span>
            <span class="td-status-label v-truncate">{{ item.label }}</span>
            <span class="td-status-bar" aria-hidden="true">
              <span
                class="td-status-bar-fill"
                :style="{ width: `${statusPercent(item.count)}%`, background: statusColor(item.status) }"
              ></span>
            </span>
            <span class="td-status-count">{{ item.count.toLocaleString() }}</span>
          </div>
        </div>
      </section>

      <!-- Recent activity peek --------------------------------------- -->
      <section v-if="recentActivityPeek.length" class="td-section">
        <div class="td-section-head">
          <p class="td-section-eyebrow v-section-label">Recent activity</p>
          <button type="button" class="td-section-link" @click="panelMode = 'activity'">
            <span>View all</span>
            <svg class="icon"><use href="#icon-external-link" /></svg>
          </button>
        </div>
        <ul class="td-peek-list">
          <li v-for="item in recentActivityPeek" :key="`peek-${item.id}`" class="td-peek-row">
            <span class="td-peek-icon" :style="eventBadgeStyle(item.event_type)" aria-hidden="true">
              <svg class="icon"><use :href="eventIcon(item.event_type)" /></svg>
            </span>
            <div class="td-peek-copy">
              <p class="td-peek-summary v-truncate">{{ item.summary }}</p>
              <p class="td-peek-meta v-truncate">
                <span>{{ item.actor_name || 'Someone' }}</span>
                <span aria-hidden="true">·</span>
                <span>{{ relativeTimestamp(item.created_at) }}</span>
              </p>
            </div>
          </li>
        </ul>
      </section>

      <div v-if="!totalShots" class="v-empty-state v-empty-state-compact td-empty">
        <svg class="icon v-empty-state-icon"><use href="#icon-target" /></svg>
        <div class="v-empty-state-title">No shots yet</div>
        <div class="v-empty-state-copy">Import or create shots to unlock tracker insights.</div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- ACTIVITY                                                          -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <div v-else class="td-body td-activity">
      <div class="td-activity-head">
        <div class="td-activity-eyebrow">
          <p class="td-section-eyebrow v-section-label">Activity feed</p>
          <span class="td-section-meta">{{ activityCountLabel }}</span>
        </div>
        <div class="td-filter-rail" role="tablist" aria-label="Activity filters">
          <button
            v-for="filter in activityTabs"
            :key="filter.value"
            type="button"
            class="v-chip v-chip-compact td-filter-chip"
            :class="{ active: activityFilter === filter.value, 'is-active': activityFilter === filter.value }"
            role="tab"
            :aria-selected="activityFilter === filter.value"
            :aria-label="filter.label"
            :title="filter.label"
            @click="activityFilter = filter.value"
          >
            <svg class="icon"><use :href="filter.icon" /></svg>
            <span class="td-filter-chip-label">{{ filter.label }}</span>
            <span v-if="filter.count !== null && filter.count !== undefined" class="td-filter-chip-count">{{ filter.count }}</span>
          </button>
        </div>
      </div>

      <div
        v-if="trackerActivityLoading && !trackerActivity.length"
        class="v-empty-state v-empty-state-compact td-empty"
      >
        <svg class="icon v-empty-state-icon"><use href="#icon-loader" /></svg>
        <div class="v-empty-state-title">Loading activity</div>
        <div class="v-empty-state-copy">Pulling the latest tracker history.</div>
      </div>
      <div
        v-else-if="!filteredActivity.length"
        class="v-empty-state v-empty-state-compact td-empty"
      >
        <svg class="icon v-empty-state-icon"><use href="#icon-activity" /></svg>
        <div class="v-empty-state-title">No matching activity</div>
        <div class="v-empty-state-copy">{{ emptyActivityCopy }}</div>
      </div>

      <ol v-else class="td-timeline">
        <li
          v-for="group in groupedActivity"
          :key="group.key"
          class="td-timeline-group"
        >
          <div class="td-timeline-day">
            <span class="td-timeline-day-label v-section-label">{{ group.label }}</span>
            <span class="td-timeline-day-rule" aria-hidden="true"></span>
            <span class="td-timeline-day-count">{{ group.items.length }}</span>
          </div>

          <ol class="td-timeline-items">
            <li
              v-for="item in group.items"
              :key="item.id"
              class="td-timeline-item"
            >
              <span
                class="td-timeline-badge"
                :style="eventBadgeStyle(item.event_type)"
                aria-hidden="true"
              >
                <svg class="icon"><use :href="eventIcon(item.event_type)" /></svg>
              </span>
              <div class="td-timeline-body">
                <p class="td-timeline-summary">{{ item.summary }}</p>
                <div v-if="item.payload?.body || item.payload?.comment_body" class="td-timeline-context">
                  <p class="td-timeline-context-copy">{{ trimContext(item.payload?.body || item.payload?.comment_body) }}</p>
                </div>
                <div class="td-timeline-foot">
                  <span class="td-timeline-actor">
                    <span
                      class="td-actor-dot"
                      :style="avatarStyle(item.actor_id || item.actor_name)"
                      aria-hidden="true"
                    >{{ initialsFor(item.actor_name) }}</span>
                    <span class="td-actor-name v-truncate">{{ item.actor_name || 'Someone' }}</span>
                    <span v-if="isCurrentUser(item.actor_id)" class="td-actor-you">You</span>
                  </span>
                  <span class="td-timeline-when" :title="absoluteTimestamp(item.created_at)">{{ relativeTimestamp(item.created_at) }}</span>
                  <span v-if="item.payload?.shot_code" class="td-timeline-shot">{{ item.payload.shot_code }}</span>
                </div>
              </div>
            </li>
          </ol>
        </li>
      </ol>

      <button
        v-if="trackerActivityHasMore"
        type="button"
        class="v-btn v-btn-secondary td-load-more"
        :disabled="trackerActivityLoading"
        @click="loadMoreTrackerActivity"
      >
        <svg v-if="trackerActivityLoading" class="icon"><use href="#icon-loader" /></svg>
        <span>{{ trackerActivityLoading ? 'Loading…' : 'Load more activity' }}</span>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { VTabs } from '../primitives'
import {
  formatActivityAbsoluteTimestamp as absoluteTimestamp,
  formatActivityRelativeTimestamp as relativeTimestamp,
} from '../../utils/formatters'
import {
  TRACKER_ACTIVITY_FILTERS,
  TRACKER_STATUS_ORDER,
  getTrackerEventIcon,
  getTrackerStatusColor,
  getTrackerStatusLabel,
} from '../../lib/trackerCatalogs'

const props = defineProps({
  closeable: { type: Boolean, default: false },
  currentTracker: { type: Object, default: null },
  currentUserId: { type: String, default: '' },
  trackerActivity: { type: Array, default: () => [] },
  trackerActivityHasMore: { type: Boolean, default: false },
  trackerActivityLoading: { type: Boolean, default: false },
  trackerStats: { type: Object, default: () => ({}) },
  isMobile: { type: Boolean, default: false },
  loadMoreTrackerActivity: { type: Function, required: true },
})

defineEmits(['close'])

const STATUS_ORDER = TRACKER_STATUS_ORDER

const PANEL_TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'activity', label: 'Activity' },
]

const ACTIVITY_FILTERS = TRACKER_ACTIVITY_FILTERS

// Calm hues for event badges + actor avatars.
const PALETTE = {
  versions: 'var(--v-info)',
  comments: 'color-mix(in srgb, var(--v-info) 62%, var(--v-text-secondary))',
  assignments: 'var(--v-warning)',
  status: 'var(--v-accent)',
  tags: 'color-mix(in srgb, var(--v-accent) 64%, var(--v-info))',
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

const panelMode = ref('overview')
const activityFilter = ref('all')

watch(
  () => props.currentTracker?.id,
  () => {
    panelMode.value = 'overview'
    activityFilter.value = 'all'
  },
)

// ─── Derived stats ─────────────────────────────────────────────────────
const totalShots = computed(() => Number(props.trackerStats?.totalShots || props.currentTracker?.shots?.length || 0))
const totalVersions = computed(() => Number(props.trackerStats?.totalVersions || 0))
const averageVersionsPerShot = computed(() => Number(props.trackerStats?.averageVersionsPerShot || 0))
const totalDurationSeconds = computed(() => Number(props.trackerStats?.totalDuration || 0))

const rawStatusBreakdown = computed(() => (
  Array.isArray(props.trackerStats?.statusBreakdown) ? props.trackerStats.statusBreakdown : []
))

const statusBreakdown = computed(() => {
  const map = new Map(rawStatusBreakdown.value.map(item => [item.status, item]))
  return STATUS_ORDER.map((status) => {
    const fromMap = map.get(status)
    return {
      status,
      label: fromMap?.label || getTrackerStatusLabel(status),
      count: Number(fromMap?.count || 0),
    }
  })
})

const statusTotal = computed(() => (
  statusBreakdown.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
))

const doneShotsCount = computed(() => {
  const fromStats = Number(props.trackerStats?.doneShots || 0)
  if (fromStats > 0) return fromStats
  const done = statusBreakdown.value.find(item => item.status === 'done')
  return Number(done?.count || 0)
})

const completionPercent = computed(() => {
  if (!totalShots.value) return 0
  return Math.round((doneShotsCount.value / totalShots.value) * 100)
})

const progressCaption = computed(() => {
  if (!totalShots.value) return 'Awaiting first shot'
  if (doneShotsCount.value === 0) return 'No shots delivered yet'
  if (doneShotsCount.value === totalShots.value) return 'All shots delivered — nice'
  const remaining = totalShots.value - doneShotsCount.value
  return `${remaining.toLocaleString()} shot${remaining === 1 ? '' : 's'} remaining`
})

const progressSegments = computed(() => {
  if (!statusTotal.value) return []
  return statusBreakdown.value
    .filter(item => item.count > 0)
    .map((item) => ({
      status: item.status,
      label: item.label,
      count: item.count,
      color: statusColor(item.status),
      percent: (item.count / statusTotal.value) * 100,
    }))
})

const totalDurationLabel = computed(() => formatDurationClock(totalDurationSeconds.value, { allowHours: true }))
const averageVersionsPerShotLabel = computed(() => {
  const value = Number(averageVersionsPerShot.value || 0)
  if (!Number.isFinite(value)) return '0'
  return value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)
})

const panelTabs = computed(() => PANEL_TABS)

const activityTabs = computed(() => (
  ACTIVITY_FILTERS.map((filter) => ({
    value: filter.value,
    label: props.isMobile ? filter.mobileLabel : filter.label,
    icon: filter.icon,
    count: countActivityForFilter(filter.value),
  }))
))

const filteredActivity = computed(() => {
  if (activityFilter.value === 'all') return props.trackerActivity
  return props.trackerActivity.filter((item) => activityFilterForEvent(item.event_type) === activityFilter.value)
})

const activityCountLabel = computed(() => {
  const visible = filteredActivity.value.length
  const total = props.trackerActivity.length
  if (visible === total) return `${total.toLocaleString()} event${total === 1 ? '' : 's'}`
  return `${visible.toLocaleString()} of ${total.toLocaleString()}`
})

const groupedActivity = computed(() => {
  const now = new Date()
  const todayBoundary = startOfDay(now)
  const yesterdayBoundary = todayBoundary - 86400
  const weekBoundary = todayBoundary - 86400 * 6
  const groups = [
    { key: 'today', label: 'Today', items: [] },
    { key: 'yesterday', label: 'Yesterday', items: [] },
    { key: 'week', label: 'Earlier this week', items: [] },
    { key: 'older', label: 'Older', items: [] },
  ]

  filteredActivity.value.forEach((item) => {
    const createdAt = Number(item.created_at || 0)
    if (createdAt >= todayBoundary) {
      groups[0].items.push(item)
    } else if (createdAt >= yesterdayBoundary) {
      groups[1].items.push(item)
    } else if (createdAt >= weekBoundary) {
      groups[2].items.push(item)
    } else {
      groups[3].items.push(item)
    }
  })

  return groups.filter(group => group.items.length)
})

const recentActivityPeek = computed(() => props.trackerActivity.slice(0, 3))

const emptyActivityCopy = computed(() => {
  if (activityFilter.value === 'all') {
    return 'Updates, comments, versions, and assignments will show up here as your team works.'
  }
  return `No ${activityFilter.value} events in the loaded history yet.`
})

const headerMeta = computed(() => {
  const parts = []
  if (totalShots.value) {
    parts.push(`${totalShots.value.toLocaleString()} shot${totalShots.value === 1 ? '' : 's'}`)
  }
  const latest = props.trackerActivity[0]?.created_at
  if (latest) {
    parts.push(`Updated ${relativeTimestamp(latest)}`)
  }
  return parts.join(' · ')
})

// ─── Helpers ───────────────────────────────────────────────────────────
function statusColor(status) {
  return getTrackerStatusColor(status)
}

function statusPercent(count) {
  if (!statusTotal.value) return 0
  return Math.max(0, Math.min(100, (Number(count || 0) / statusTotal.value) * 100))
}

function countActivityForFilter(filterValue) {
  if (filterValue === 'all') return props.trackerActivity.length
  return props.trackerActivity.filter((item) => activityFilterForEvent(item.event_type) === filterValue).length
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
  if (['assignee_changed'].includes(eventType)) return 'assignments'
  if (['status_changed'].includes(eventType)) return 'status'
  if (eventType === 'category_changed') return 'tags'
  if (eventType === 'download_started') return 'downloads'
  return 'all'
}

function eventIcon(eventType) {
  return getTrackerEventIcon(eventType)
}

function eventBadgeStyle(eventType) {
  const bucket = activityFilterForEvent(eventType)
  const baseColor = PALETTE[bucket] || PALETTE.default
  return {
    color: baseColor,
    background: `color-mix(in srgb, ${baseColor} 14%, transparent)`,
    boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${baseColor} 24%, transparent)`,
  }
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
    background: `color-mix(in srgb, ${hue} 18%, var(--v-surface-inline))`,
    color: hue,
    boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${hue} 32%, transparent)`,
  }
}

function initialsFor(name) {
  const source = String(name || '').trim()
  if (!source) return '?'
  const parts = source.split(/\s+/).slice(0, 2)
  return parts.map(part => part.charAt(0).toUpperCase()).join('') || '?'
}

function isCurrentUser(actorId) {
  if (!props.currentUserId || !actorId) return false
  return String(actorId) === String(props.currentUserId)
}

function trimContext(text) {
  const value = String(text || '').trim()
  if (value.length <= 140) return value
  return `${value.slice(0, 140).trimEnd()}…`
}

function formatDurationClock(seconds, { allowHours = false } = {}) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)))
  if (allowHours && total >= 3600) {
    const hours = Math.floor(total / 3600)
    const mins = Math.floor((total % 3600) / 60)
    return `${hours}h ${mins}m`
  }
  if (total >= 60) {
    const mins = Math.floor(total / 60)
    const secs = total % 60
    return `${mins}:${String(secs).padStart(2, '0')}`
  }
  return `${total}s`
}

function startOfDay(date) {
  const boundary = new Date(date)
  boundary.setHours(0, 0, 0, 0)
  return Math.floor(boundary.getTime() / 1000)
}
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════
   TRACKER DETAILS PANEL
   ─────────────────────────────────────────────────────────────────────── */

.td-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  color: var(--v-text);
}

/* ─── Header ─────────────────────────────────────────────────────────── */
.td-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--v-divider-subtle);
  flex-shrink: 0;
}

.td-head-copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1 1 auto;
}


.td-title {
  margin: 0;
  color: var(--v-text);
  font-size: 24px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.1;
  min-width: 0;
}

.td-meta {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 500;
  letter-spacing: 0;
}

.td-close {
  flex-shrink: 0;
}

/* ─── Mode tabs ──────────────────────────────────────────────────────── */
.td-mode-tabs {
  width: 100%;
  flex-shrink: 0;
}

.td-mode-tabs :deep(.v-tabs--segmented) {
  width: 100%;
}

/* ─── Body shell ─────────────────────────────────────────────────────── */
.td-body {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: var(--v-space-1);
  margin-right: -4px;
}

.td-overview {
  gap: 18px;
}

.td-activity {
  gap: 14px;
}

/* ─── Section primitives ─────────────────────────────────────────────── */
.td-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.td-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 0 2px;
}

.td-section-eyebrow {
  margin: 0;
}

.td-section-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.td-section-link {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-1);
  padding: 2px 6px;
  border-radius: var(--v-button-radius);
  border: 0;
  background: transparent;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: color var(--v-duration-fast) var(--v-ease-emphasized), background var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-section-link .icon {
  width: 11px;
  height: 11px;
}

.td-section-link:hover {
  color: var(--v-text);
  background: var(--v-control-bg-hover);
}

/* ─── Progress hero ──────────────────────────────────────────────────── */
.td-progress-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-radius: var(--v-radius-lg);
  background: linear-gradient(170deg, color-mix(in srgb, var(--v-accent) 5%, var(--v-surface-raised)), var(--v-surface-raised));
  border: 1px solid color-mix(in srgb, var(--v-accent) 12%, var(--v-surface-border-soft));
  box-shadow: var(--v-surface-shadow-raised);
}

.td-progress-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.td-progress-headline {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  min-width: 0;
}

.td-progress-pct {
  display: inline-flex;
  align-items: baseline;
  color: var(--v-text);
  font-size: 44px;
  font-weight: 650;
  letter-spacing: 0;
  line-height: 0.96;
  font-variant-numeric: tabular-nums;
}

.td-progress-pct-sign {
  margin-left: 2px;
  color: var(--v-text-secondary);
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0;
}

.td-progress-label {
  color: var(--v-accent);
  font-size: var(--v-text-xs);
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.td-progress-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--v-space-1);
  min-width: 0;
  text-align: right;
}

.td-progress-numerator {
  color: var(--v-text);
  font-size: var(--v-text-xl);
  font-weight: 650;
  letter-spacing: 0;
  font-variant-numeric: tabular-nums;
}

.td-progress-numerator span {
  color: var(--v-text-muted);
  font-weight: 500;
}

.td-progress-caption {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
}

.td-progress-track {
  position: relative;
  display: flex;
  width: 100%;
  height: 10px;
  border-radius: var(--v-radius-full);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
  overflow: hidden;
}

.td-progress-segment {
  height: 100%;
  transition: width var(--v-duration-normal) var(--v-ease-emphasized);
}

.td-progress-segment + .td-progress-segment {
  border-left: 1px solid color-mix(in srgb, var(--v-surface-inset) 60%, transparent);
}

.td-progress-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.td-progress-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 6px 14px;
}

.td-progress-legend li {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 500;
}

.td-progress-legend-dot {
  width: 7px;
  height: 7px;
  border-radius: var(--v-radius-full);
  flex-shrink: 0;
}

.td-progress-legend-label {
  min-width: 0;
}

.td-progress-legend-count {
  margin-left: auto;
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

/* ─── Stat grid ──────────────────────────────────────────────────────── */
.td-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.td-stat-tile {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  padding: 14px 14px;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  border: 1px solid var(--v-surface-border-soft);
  box-shadow: var(--v-surface-shadow-raised);
  min-width: 0;
}

.td-stat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-accent) 12%, transparent);
  color: var(--v-accent);
  flex-shrink: 0;
}

.td-stat-icon .icon {
  width: 17px;
  height: 17px;
}

.td-stat-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.td-stat-value {
  display: inline-flex;
  align-items: baseline;
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}

.td-stat-suffix {
  margin-left: 2px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
}

.td-stat-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  letter-spacing: 0.02em;
}

/* ─── Status breakdown list ──────────────────────────────────────────── */
.td-status-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 4px 14px;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  border: 1px solid var(--v-surface-border-soft);
  box-shadow: var(--v-surface-shadow-raised);
}

.td-status-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(0, 2.2fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 36px;
  padding: 6px 0;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.td-status-row:last-child {
  border-bottom: 0;
}

.td-status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v-radius-full);
}

.td-status-label {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  font-weight: 500;
  letter-spacing: 0;
  min-width: 0;
}

.td-status-bar {
  position: relative;
  display: block;
  width: 100%;
  height: 4px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-surface-inline-strong) 78%, transparent);
  overflow: hidden;
}

.td-status-bar-fill {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  height: 100%;
  border-radius: inherit;
  min-width: 4px;
  transition: width var(--v-duration-normal) var(--v-ease-emphasized);
}

.td-status-count {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

/* ─── Recent activity peek (overview) ────────────────────────────────── */
.td-peek-list {
  list-style: none;
  margin: 0;
  padding: var(--v-space-1);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  border: 1px solid var(--v-surface-border-soft);
  box-shadow: var(--v-surface-shadow-raised);
  display: flex;
  flex-direction: column;
  gap: 0;
}

.td-peek-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  padding: 10px 12px;
  border-bottom: 1px solid var(--v-divider-subtle);
  min-width: 0;
}

.td-peek-row:last-child {
  border-bottom: 0;
}

.td-peek-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--v-radius-full);
  flex-shrink: 0;
}

.td-peek-icon .icon {
  width: 13px;
  height: 13px;
}

.td-peek-copy {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.td-peek-summary {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 500;
  letter-spacing: 0;
  min-width: 0;
}

.td-peek-meta {
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  min-width: 0;
}

.td-peek-meta > span:nth-child(2) {
  opacity: 0.55;
}

/* ─── Activity head + filter chips ───────────────────────────────────── */
.td-activity-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
  padding-bottom: var(--v-space-1);
  background: linear-gradient(to bottom, var(--v-surface-canvas) 75%, transparent);
}

.td-activity-eyebrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 0 2px;
}

.td-filter-rail {
  position: relative;
  display: flex;
  align-items: center;
  gap: 5px;
  overflow-x: auto;
  padding: 2px 2px 4px;
  margin: 0 -2px;
}

.td-filter-chip {
  gap: 5px;
  flex-shrink: 0;
  height: 28px;
  cursor: pointer;
  transition: color var(--v-duration-fast) var(--v-ease-emphasized), background var(--v-duration-fast) var(--v-ease-emphasized), border-color var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-filter-chip .icon {
  width: 12px;
  height: 12px;
}

.td-filter-chip:hover:not(.is-active) {
  color: var(--v-text);
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border);
}

.td-filter-chip.active {
  color: var(--v-text);
  background: var(--v-control-bg-active);
  border-color: var(--v-control-border-active);
}

.td-filter-chip-label {
  white-space: nowrap;
  /* Collapsed by default; only the active chip reveals its label. */
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  margin-left: 0;
  transition: max-width var(--v-duration-fast) var(--v-ease-emphasized), opacity var(--v-duration-fast) var(--v-ease-emphasized), margin var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-filter-chip.active .td-filter-chip-label {
  max-width: 140px;
  opacity: 1;
  margin-left: 1px;
}

.td-filter-chip-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 8%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.td-filter-chip.active .td-filter-chip-count {
  background: color-mix(in srgb, var(--v-accent) 22%, transparent);
  color: var(--v-text);
}

/* ─── Timeline ───────────────────────────────────────────────────────── */
.td-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
  min-width: 0;
}

.td-timeline-group {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
}

.td-timeline-day {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 2px;
}


.td-timeline-day-rule {
  flex: 1 1 auto;
  height: 1px;
  background: var(--v-divider-subtle);
}

.td-timeline-day-count {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.td-timeline-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  position: relative;
}

/* Vertical rail behind the badges, giving the feed a chronological spine. */
.td-timeline-items::before {
  content: '';
  position: absolute;
  top: 22px;
  bottom: 14px;
  left: 17px;
  width: 1px;
  background: linear-gradient(to bottom, var(--v-divider-subtle) 0%, transparent 100%);
  pointer-events: none;
}

.td-timeline-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: var(--v-space-3);
  padding: 10px 4px 10px 0;
  align-items: flex-start;
  position: relative;
}

.td-timeline-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--v-radius-full);
  border: 1px solid var(--v-control-border);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
  flex-shrink: 0;
  z-index: 1;
}

.td-timeline-badge .icon {
  width: 14px;
  height: 14px;
}

.td-timeline-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding-top: 2px;
}

.td-timeline-summary {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 500;
  line-height: 1.45;
  word-break: break-word;
}

.td-timeline-context {
  padding: 8px 10px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-tint-strong);
  border-left: 2px solid color-mix(in srgb, var(--v-text-muted) 40%, transparent);
}

.td-timeline-context-copy {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.5;
  word-break: break-word;
}

.td-timeline-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.td-timeline-actor {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  color: var(--v-text-secondary);
  font-weight: 500;
}

.td-actor-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.td-actor-name {
  min-width: 0;
  max-width: 180px;
}

.td-actor-you {
  height: 16px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  border-radius: var(--v-radius-full);
  background: var(--v-accent-muted);
  color: var(--v-accent);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.td-timeline-when {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.td-timeline-shot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 18px;
  padding: 0 7px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent) 12%, transparent);
  color: var(--v-accent);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
  margin-left: auto;
}

.td-load-more {
  width: 100%;
  margin-top: var(--v-space-1);
  flex-shrink: 0;
}

.td-load-more .icon {
  width: 14px;
  height: 14px;
  animation: td-spin 1s linear infinite;
}

@keyframes td-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ─── Empty states ───────────────────────────────────────────────────── */
.td-empty {
  margin-top: var(--v-space-1);
}

/* ═══════════════════════════════════════════════════════════════════════
   MOBILE OVERRIDES
   ─────────────────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .td-panel {
    gap: var(--v-space-4);
  }

  .td-head {
    margin: -2px -2px 0;
    padding: 2px 2px 12px;
    border-bottom: 1px solid var(--v-divider-subtle);
  }

  .td-title {
    font-size: 22px;
  }

  .td-body {
    padding-right: 0;
    margin-right: 0;
  }

  .td-overview {
    gap: var(--v-space-4);
  }

  .td-progress-card {
    padding: var(--v-space-4);
  }

  .td-progress-pct {
    font-size: 38px;
  }

  .td-progress-pct-sign {
    font-size: var(--v-text-2xl);
  }

  .td-progress-legend {
    grid-template-columns: 1fr;
  }

  .td-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--v-space-2);
  }

  .td-stat-tile {
    padding: var(--v-space-3);
    border-radius: var(--v-radius-lg);
  }

  .td-stat-value {
    font-size: var(--v-text-xl);
  }

  .td-status-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .td-status-bar {
    display: none;
  }

  .td-activity-head {
    background: linear-gradient(to bottom, var(--v-modal-bg) 75%, transparent);
  }

  .td-activity-eyebrow {
    padding: 0;
  }

  .td-timeline-item {
    grid-template-columns: 32px minmax(0, 1fr);
    gap: 10px;
  }

  .td-timeline-badge {
    width: 30px;
    height: 30px;
  }

  .td-timeline-items::before {
    left: 15px;
  }

  .td-timeline-foot {
    gap: 6px;
    font-size: var(--v-text-xs);
  }

  .td-actor-name {
    max-width: 140px;
  }

  .td-timeline-shot {
    margin-left: 0;
  }
}

/* Wider desktop rails get a little more breathing room for stat tiles. */
@media (min-width: 1400px) {
  .td-stats {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .td-stat-tile {
    padding: 14px 14px;
  }
}
</style>
