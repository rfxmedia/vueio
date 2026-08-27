<template>
  <section class="td-panel" :class="{ 'is-mobile': isMobile }">
    <!-- ─── Header ────────────────────────────────────────────────────── -->
    <header class="td-head">
      <div class="td-head-copy">
        <p class="td-eyebrow v-eyebrow">Tracker details</p>
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

    <!-- ─── Mode tabs (Overview / History) ────────────────────────────── -->
    <VTabs
      v-model="panelMode"
      class="td-mode-tabs"
      :tabs="panelTabs"
      variant="rail"
      full-width
    />

    <Transition name="td-content" mode="out-in">
      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- OVERVIEW                                                       -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <div v-if="panelMode === 'overview'" key="overview" class="td-body td-overview">
        <section class="td-delivery" aria-labelledby="td-delivery-title">
          <div class="td-delivery-primary">
            <span class="td-delivery-number">{{ completionPercent }}<span>%</span></span>
            <div class="td-delivery-copy">
              <h3 id="td-delivery-title">Delivery progress</h3>
              <p>{{ progressCaption }}</p>
            </div>
          </div>

          <div class="td-delivery-detail">
            <div class="td-delivery-count">
              <span>Delivered</span>
              <strong>{{ doneShotsCount.toLocaleString() }} <small>of {{ totalShots.toLocaleString() }}</small></strong>
            </div>

            <div
              class="td-progress-track"
              role="img"
              :aria-label="`Shot status breakdown: ${completionPercent}% complete`"
            >
              <span
                v-for="segment in progressSegments"
                :key="segment.status"
                class="td-progress-segment"
                :style="{ width: `${segment.percent}%`, background: segment.color }"
                :title="`${segment.label}: ${segment.count}`"
              ></span>
              <span v-if="!totalShots" class="td-progress-empty">No shots yet</span>
            </div>

            <div v-if="totalShots" class="td-status-grid" aria-label="Shot counts by status">
              <div
                v-for="item in statusBreakdown"
                :key="item.status"
                class="td-status-cell"
                :class="{ 'is-empty': !item.count }"
              >
                <span class="td-status-mark" :style="{ background: statusColor(item.status) }" aria-hidden="true"></span>
                <strong>{{ item.count.toLocaleString() }}</strong>
                <span>{{ item.label }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="td-metrics" aria-label="Tracker statistics">
          <article class="td-metric">
            <svg class="icon" aria-hidden="true"><use href="#icon-target" /></svg>
            <span class="td-metric-value">{{ totalShots.toLocaleString() }}</span>
            <span class="td-metric-label">Shots</span>
          </article>
          <article class="td-metric">
            <svg class="icon" aria-hidden="true"><use href="#icon-video" /></svg>
            <span class="td-metric-value">{{ totalVersions.toLocaleString() }}</span>
            <span class="td-metric-label">Versions</span>
          </article>
          <article class="td-metric">
            <svg class="icon" aria-hidden="true"><use href="#icon-clock" /></svg>
            <span class="td-metric-value">{{ totalDurationLabel }}</span>
            <span class="td-metric-label">Runtime</span>
          </article>
          <article class="td-metric">
            <svg class="icon" aria-hidden="true"><use href="#icon-trending-up" /></svg>
            <span class="td-metric-value">{{ averageVersionsPerShotLabel }}<small>×</small></span>
            <span class="td-metric-label">Versions per shot</span>
          </article>
        </section>

        <section v-if="recentActivityPeek.length" class="td-section">
          <div class="td-section-head">
            <div>
              <h3 class="td-section-title">Latest activity</h3>
              <p class="td-section-copy">The newest changes across this tracker.</p>
            </div>
            <button type="button" class="td-section-link" @click="panelMode = 'activity'">
              <span>View history</span>
              <svg class="icon"><use href="#icon-chevron-right" /></svg>
            </button>
          </div>
          <ul class="td-peek-list">
            <li v-for="item in recentActivityPeek" :key="`peek-${item.id}`" class="td-peek-row">
              <span class="td-peek-icon" :style="eventBadgeStyle(item.event_type)" aria-hidden="true">
                <svg class="icon"><use :href="eventIcon(item.event_type)" /></svg>
              </span>
              <div class="td-peek-copy">
                <p class="td-peek-summary">{{ item.summary }}</p>
                <p class="td-peek-meta">
                  <span>{{ item.actor_name || 'Someone' }}</span>
                  <span aria-hidden="true">·</span>
                  <span>{{ relativeTimestamp(item.created_at) }}</span>
                </p>
              </div>
              <span v-if="item.payload?.shot_code" class="td-peek-shot">{{ item.payload.shot_code }}</span>
            </li>
          </ul>
        </section>

        <div v-if="!totalShots" class="v-empty-state v-empty-state-compact td-empty">
          <svg class="icon v-empty-state-icon"><use href="#icon-target" /></svg>
          <div class="v-empty-state-title">No shots yet</div>
          <div class="v-empty-state-copy">Import or create shots to unlock tracker insights.</div>
        </div>
      </div>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- HISTORY                                                        -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <div v-else-if="panelMode === 'activity'" key="activity" class="td-body td-activity">
        <div class="td-activity-head">
          <div class="td-activity-intro">
            <div class="td-activity-intro-copy">
              <h3>Tracker history</h3>
              <p>{{ canRestoreHistory ? 'Choose a saved point to restore the entire tracker.' : 'Every tracker change is recorded here.' }}</p>
            </div>
            <span class="td-activity-count">{{ activityCountLabel }} loaded</span>
          </div>
          <div class="td-filter-rail" role="tablist" aria-label="History filters">
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

        <div v-if="trackerActivityError" class="td-activity-error" role="status">
          <svg class="icon" aria-hidden="true"><use href="#icon-alert" /></svg>
          <div>
            <strong>History couldn’t refresh</strong>
            <p>{{ trackerActivityError }}</p>
          </div>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" :disabled="trackerActivityLoading" @click="retryTrackerActivity">
            Try again
          </button>
        </div>

        <div
          v-if="trackerActivityLoading && !trackerActivity.length"
          class="v-empty-state v-empty-state-compact td-empty"
        >
          <svg class="icon v-empty-state-icon"><use href="#icon-loader" /></svg>
          <div class="v-empty-state-title">Loading history</div>
          <div class="v-empty-state-copy">Pulling the latest tracker history.</div>
        </div>
        <div
          v-else-if="!trackerActivityError && !filteredActivity.length"
          class="v-empty-state v-empty-state-compact td-empty"
        >
          <svg class="icon v-empty-state-icon"><use href="#icon-activity" /></svg>
          <div class="v-empty-state-title">No matching history</div>
          <div class="v-empty-state-copy">{{ emptyActivityCopy }}</div>
        </div>

        <ol v-else class="td-timeline">
        <li
          v-for="group in groupedActivity"
          :key="group.key"
          class="td-timeline-group"
        >
          <div class="td-timeline-day">
            <span class="td-timeline-day-label">{{ group.label }}</span>
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
                <div class="td-timeline-topline">
                  <p class="td-timeline-summary">{{ item.summary }}</p>
                  <span v-if="item.current_point && !item.recovery_unavailable" class="td-current-point">
                    <svg class="icon" aria-hidden="true"><use href="#icon-check" /></svg>
                    <span>Current</span>
                  </span>
                  <button
                    v-else-if="canRestoreActivity(item)"
                    type="button"
                    class="v-btn v-btn-ghost v-btn-sm td-restore-action"
                    :disabled="activityRestoreBusyId !== null || activityRestorePreviewBusyId !== null"
                    :aria-busy="activityRestorePreviewBusyId === item.id ? 'true' : 'false'"
                    :title="`Restore: ${item.summary}`"
                    @click="prepareTrackerHistoryRestore(item)"
                  >
                    <svg class="icon" :class="{ 'is-spinning': activityRestorePreviewBusyId === item.id }" aria-hidden="true">
                      <use :href="activityRestorePreviewBusyId === item.id ? '#icon-loader' : '#icon-clock'" />
                    </svg>
                    <span>{{ activityRestorePreviewBusyId === item.id ? 'Checking…' : 'Restore' }}</span>
                  </button>
                  <span
                    v-else-if="canRestoreHistory && item.recovery_unavailable"
                    class="td-recovery-unavailable"
                    :title="recoveryUnavailableCopy(item)"
                    :aria-label="`${recoveryUnavailableLabel(item)}. ${recoveryUnavailableCopy(item)}`"
                  >{{ recoveryUnavailableLabel(item) }}</span>
                </div>
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
          <span>{{ trackerActivityLoading ? 'Loading…' : 'Load more history' }}</span>
        </button>
      </div>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- VIEW HISTORY (ADMIN ONLY)                                      -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <div v-else key="views" class="td-body td-views">
        <div class="td-activity-head td-views-head">
          <div class="td-activity-intro">
            <div>
              <h3>Viewer history</h3>
              <p>{{ viewCountLabel }}</p>
            </div>
            <button
              type="button"
              class="v-btn v-btn-secondary v-btn-icon v-btn-sm td-views-refresh"
              :disabled="trackerViewsLoading"
              aria-label="Refresh viewer history"
              @click="refreshTrackerViews"
            >
              <svg class="icon" :class="{ 'is-spinning': trackerViewsLoading }"><use href="#icon-refresh" /></svg>
            </button>
          </div>
          <div class="td-filter-rail" role="tablist" aria-label="Viewer history filters">
            <button
              v-for="filter in viewFilters"
              :key="filter.value"
              type="button"
              class="v-chip v-chip-compact td-filter-chip"
              :class="{ active: viewFilter === filter.value, 'is-active': viewFilter === filter.value }"
              role="tab"
              :aria-selected="viewFilter === filter.value"
              @click="viewFilter = filter.value"
            >
              <svg class="icon"><use :href="filter.icon" /></svg>
              <span class="td-filter-chip-label">{{ filter.label }}</span>
              <span class="td-filter-chip-count">{{ filter.count }}</span>
            </button>
          </div>
        </div>

        <section v-if="filteredActiveViewers.length" class="td-presence" aria-labelledby="td-presence-title">
          <header class="td-presence-head">
            <span class="td-presence-signal" aria-hidden="true"></span>
            <div>
              <h3 id="td-presence-title">Viewing now</h3>
              <p>{{ activeViewerLabel }}</p>
            </div>
          </header>
          <ul class="td-presence-list">
            <li v-for="viewer in filteredActiveViewers" :key="`active-${viewer.id}`" class="td-presence-row">
              <span class="td-view-avatar" :style="avatarStyle(viewer.viewer_user_id || viewer.share_id || viewer.id)" aria-hidden="true">
                {{ initialsFor(viewer.viewer_name) }}
              </span>
              <span class="td-presence-copy">
                <span class="td-view-person">
                  <strong class="v-truncate">{{ viewer.viewer_name }}</strong>
                  <span v-if="isCurrentViewer(viewer)" class="td-actor-you">You</span>
                </span>
                <span>{{ viewer.summary }}</span>
              </span>
              <span class="td-presence-meta">
                <span>{{ viewPresenceClientLabel(viewer) }}</span>
                <time :datetime="viewDateTime(viewer.last_seen_at)" :title="absoluteTimestamp(viewer.last_seen_at)">
                  {{ relativeTimestamp(viewer.last_seen_at) }}
                </time>
              </span>
            </li>
          </ul>
        </section>

        <div v-if="trackerViewsError" class="td-view-error" role="alert">
          <svg class="icon" aria-hidden="true"><use href="#icon-alert" /></svg>
          <span>{{ trackerViewsError }}</span>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="refreshTrackerViews">Retry</button>
        </div>

        <div
          v-if="trackerViewsLoading && !trackerViews.length"
          class="td-view-skeleton"
          aria-label="Loading viewer history"
        >
          <span v-for="index in 3" :key="index" class="td-view-skeleton-row" aria-hidden="true">
            <span></span><span></span><span></span>
          </span>
        </div>

        <div
          v-else-if="!filteredTrackerViews.length && !trackerViewsError"
          class="v-empty-state v-empty-state-compact td-empty"
        >
          <svg class="icon v-empty-state-icon"><use href="#icon-eye" /></svg>
          <div class="v-empty-state-title">No viewer activity yet</div>
          <div class="v-empty-state-copy">Tracker opens and media views will appear here.</div>
        </div>

        <ol v-else class="td-view-history">
          <li v-for="group in groupedTrackerViews" :key="`views-${group.key}`" class="td-timeline-group">
            <div class="td-timeline-day">
              <span class="td-timeline-day-label">{{ group.label }}</span>
              <span class="td-timeline-day-rule" aria-hidden="true"></span>
              <span class="td-timeline-day-count">{{ group.items.length }}</span>
            </div>
            <ol class="td-view-items">
              <li v-for="view in group.items" :key="view.id" class="td-view-row">
                <span class="td-view-icon" aria-hidden="true">
                  <svg class="icon"><use :href="view.source === 'share' ? '#icon-link' : '#icon-user'" /></svg>
                </span>
                <div class="td-view-body">
                  <div class="td-view-topline">
                    <span class="td-view-person">
                      <strong class="v-truncate">{{ view.viewer_name }}</strong>
                      <span v-if="isCurrentViewer(view)" class="td-actor-you">You</span>
                    </span>
                    <time :datetime="viewDateTime(view.created_at)" :title="absoluteTimestamp(view.created_at)">
                      {{ viewTimestamp(view.created_at) }}
                    </time>
                  </div>
                  <p>{{ view.summary }}</p>
                  <div class="td-view-meta">
                    <span>{{ viewDeviceLabel(view.device_type) }}</span>
                    <span>{{ viewSourceLabel(view) }}</span>
                    <span v-if="viewClientSummary(view)">{{ viewClientSummary(view) }}</span>
                  </div>
                  <details v-if="hasVisitDetails(view)" class="td-view-details">
                    <summary>
                      <span>Visit details</span>
                      <svg class="icon" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
                    </summary>
                    <dl>
                      <div v-if="view.client?.ip_address">
                        <dt>Network</dt>
                        <dd>
                          <code>{{ view.client.ip_address }}</code>
                          <span v-if="view.client.network"> · {{ view.client.network }}</span>
                        </dd>
                      </div>
                      <div v-if="viewLocationLabel(view)">
                        <dt>IP location</dt>
                        <dd>
                          {{ viewLocationLabel(view) }}
                          <span v-if="view.client?.location_source"> · {{ view.client.location_source }}</span>
                        </dd>
                      </div>
                      <div v-if="view.client?.timezone">
                        <dt>Time zone</dt>
                        <dd>{{ view.client.timezone }}</dd>
                      </div>
                      <div v-if="viewClientSummary(view)">
                        <dt>Client</dt>
                        <dd>{{ viewClientSummary(view) }}</dd>
                      </div>
                      <div v-if="view.client?.language">
                        <dt>Language</dt>
                        <dd>{{ view.client.language }}</dd>
                      </div>
                      <div v-if="view.visit_id">
                        <dt>Visit ID</dt>
                        <dd><code :title="view.visit_id">{{ shortVisitId(view.visit_id) }}</code></dd>
                      </div>
                    </dl>
                  </details>
                </div>
              </li>
            </ol>
          </li>
        </ol>

        <button
          v-if="trackerViewsHasMore"
          type="button"
          class="v-btn v-btn-secondary td-load-more"
          :disabled="trackerViewsLoading"
          @click="loadMoreTrackerViews"
        >
          <svg v-if="trackerViewsLoading" class="icon"><use href="#icon-loader" /></svg>
          <span>{{ trackerViewsLoading ? 'Loading…' : 'Load more views' }}</span>
        </button>

        <div class="td-view-privacy">
          <svg class="icon" aria-hidden="true"><use href="#icon-info" /></svg>
          <p>Viewer history stores IP addresses and parsed browser details. IP location appears only from trusted Cloudflare headers. Raw user-agent strings and covert device fingerprints are not stored.</p>
        </div>
      </div>
    </Transition>
  </section>

  <VModal
    :model-value="Boolean(activityRestorePreview)"
    size="sm"
    :presentation="isMobile ? 'sheet' : 'dialog'"
    :mobile-full-height="false"
    :closeable="activityRestoreBusyId === null"
    class="td-recovery-modal"
    @update:model-value="closeTrackerHistoryRestore"
  >
    <template #header="{ titleId }">
      <VModalHeader
        eyebrow="Tracker restore"
        :title="activityRestorePreview?.title || 'Restore this history point?'"
        :title-id="titleId"
        subtitle="Return the entire tracker to this saved point."
        :closeable="activityRestoreBusyId === null"
        @close="closeTrackerHistoryRestore"
      />
    </template>

    <div v-if="activityRestorePreview" class="td-recovery-body">
      <div class="td-recovery-summary">
        <span class="td-recovery-summary-icon" aria-hidden="true">
          <svg class="icon"><use href="#icon-clock" /></svg>
        </span>
        <p>{{ activityRestorePreview.summary }}</p>
      </div>

      <dl class="td-recovery-facts">
        <div>
          <dt>Shots</dt>
          <dd>{{ activityRestorePreview.shot_count }}</dd>
        </div>
        <div>
          <dt>Changes</dt>
          <dd>{{ activityRestorePreview.change_count }}</dd>
        </div>
      </dl>

      <div class="td-recovery-scope">
        <p class="v-eyebrow">What will change</p>
        <div class="td-recovery-chips">
          <span v-for="field in activityRestorePreview.fields" :key="field" class="v-chip v-chip-compact">{{ field }}</span>
        </div>
        <p v-if="activityRestorePreview.shot_codes?.length" class="td-recovery-shots">
          {{ activityRestorePreview.shot_codes.join(', ') }}<template v-if="activityRestorePreview.remaining_shot_count"> +{{ activityRestorePreview.remaining_shot_count }} more</template>
        </p>
      </div>

      <div v-if="activityRestorePreview.error" class="td-recovery-error" role="alert">
        <svg class="icon" aria-hidden="true"><use href="#icon-alert" /></svg>
        <p>{{ activityRestorePreview.error }}</p>
      </div>

      <p class="td-recovery-note">
        Vue saves the current tracker first, so you can safely return to it later.
      </p>
    </div>

    <template #footer>
      <button type="button" class="v-btn v-btn-secondary" :disabled="activityRestoreBusyId !== null" @click="closeTrackerHistoryRestore">
        Cancel
      </button>
      <button
        type="button"
        class="v-btn v-btn-primary td-recovery-confirm"
        :disabled="activityRestoreBusyId !== null || !restoreCanApply"
        :aria-busy="activityRestoreBusyId !== null ? 'true' : 'false'"
        @click="restoreTrackerActivity"
      >
        <svg class="icon" :class="{ 'is-spinning': activityRestoreBusyId !== null }" aria-hidden="true">
          <use :href="activityRestoreBusyId !== null ? '#icon-loader' : '#icon-clock'" />
        </svg>
        <span>{{ activityRestoreBusyId !== null ? 'Restoring…' : !restoreCanApply ? 'Already current' : 'Restore tracker' }}</span>
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VModal, VModalHeader, VTabs } from '../primitives'
import {
  formatActivityAbsoluteTimestamp as absoluteTimestamp,
  formatActivityRelativeTimestamp as relativeTimestamp,
} from '../../utils/formatters'
import {
  TRACKER_ACTIVITY_FILTERS,
  TRACKER_STATUS_ORDER,
  getTrackerEventColor,
  getTrackerEventIcon,
  getTrackerStatusColor,
  getTrackerStatusLabel,
} from '../../lib/trackerCatalogs'
import { getIdentityColor } from '../../utils/semanticColors'

const props = defineProps({
  closeable: { type: Boolean, default: false },
  currentTracker: { type: Object, default: null },
  currentUserId: { type: String, default: '' },
  isAdmin: { type: Boolean, default: false },
  activityRestoreBusyId: { type: Number, default: null },
  activityRestorePreview: { type: Object, default: null },
  activityRestorePreviewBusyId: { type: Number, default: null },
  canRestoreHistory: { type: Boolean, default: false },
  trackerActivity: { type: Array, default: () => [] },
  trackerActivityError: { type: String, default: '' },
  trackerActivityHasMore: { type: Boolean, default: false },
  trackerActivityLoading: { type: Boolean, default: false },
  trackerStats: { type: Object, default: () => ({}) },
  trackerViews: { type: Array, default: () => [] },
  trackerViewersActive: { type: Array, default: () => [] },
  trackerViewsError: { type: String, default: '' },
  trackerViewsHasMore: { type: Boolean, default: false },
  trackerViewsLoading: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  loadMoreTrackerActivity: { type: Function, required: true },
  retryTrackerActivity: { type: Function, default: async () => {} },
  prepareTrackerHistoryRestore: { type: Function, default: async () => {} },
  closeTrackerHistoryRestore: { type: Function, default: () => {} },
  restoreTrackerActivity: { type: Function, default: async () => {} },
  loadTrackerViews: { type: Function, required: true },
  loadMoreTrackerViews: { type: Function, required: true },
})

defineEmits(['close'])

const STATUS_ORDER = TRACKER_STATUS_ORDER

const PANEL_TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'activity', label: 'History' },
]

const VIEW_FILTERS = [
  { value: 'all', label: 'All', icon: '#icon-eye' },
  { value: 'share', label: 'Share links', icon: '#icon-link' },
  { value: 'team', label: 'Team', icon: '#icon-users' },
]

const VIEW_REFRESH_MS = 30_000
const REGION_NAMES = typeof Intl?.DisplayNames === 'function'
  ? new Intl.DisplayNames(undefined, { type: 'region' })
  : null

const ACTIVITY_FILTERS = TRACKER_ACTIVITY_FILTERS

const panelMode = ref('overview')
const activityFilter = ref('all')
const viewFilter = ref('all')
let viewRefreshTimer = null

watch(
  () => props.currentTracker?.id,
  () => {
    panelMode.value = 'overview'
    activityFilter.value = 'all'
    viewFilter.value = 'all'
  },
)

watch(
  () => props.isAdmin,
  (admin) => {
    if (!admin && panelMode.value === 'views') panelMode.value = 'overview'
  },
)

function stopViewRefresh() {
  if (viewRefreshTimer !== null) {
    window.clearInterval(viewRefreshTimer)
    viewRefreshTimer = null
  }
}

async function refreshTrackerViews() {
  if (!props.isAdmin) return
  await props.loadTrackerViews()
}

watch(
  [panelMode, () => props.isAdmin],
  ([mode, admin]) => {
    stopViewRefresh()
    if (mode !== 'views' || !admin) return
    void refreshTrackerViews()
    viewRefreshTimer = window.setInterval(() => void refreshTrackerViews(), VIEW_REFRESH_MS)
  },
)

onBeforeUnmount(stopViewRefresh)

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
  if (doneShotsCount.value === totalShots.value) return 'All shots delivered'
  if (doneShotsCount.value === 0) {
    const phrases = {
      in_progress: 'in progress',
      waiting_review: 'in review',
      edits_requested: 'requesting edits',
    }
    const moving = statusBreakdown.value
      .filter(item => ['in_progress', 'waiting_review', 'edits_requested'].includes(item.status) && item.count)
      .map(item => `${item.count.toLocaleString()} ${phrases[item.status]}`)
    return moving.length ? moving.join(', ') : 'Ready for the first delivery'
  }
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

const panelTabs = computed(() => (
  props.isAdmin ? [...PANEL_TABS, { value: 'views', label: 'Views' }] : PANEL_TABS
))

const activityTabs = computed(() => (
  ACTIVITY_FILTERS.map((filter) => ({
    value: filter.value,
    label: props.isMobile ? filter.mobileLabel : filter.label,
    icon: filter.icon,
    count: countActivityForFilter(filter.value),
  }))
))

const viewFilters = computed(() => VIEW_FILTERS.map(filter => ({
  ...filter,
  count: countViewsForFilter(filter.value),
})))

const filteredTrackerViews = computed(() => {
  if (viewFilter.value === 'all') return props.trackerViews
  if (viewFilter.value === 'share') return props.trackerViews.filter(item => item.source === 'share')
  return props.trackerViews.filter(item => item.source !== 'share')
})

const filteredActiveViewers = computed(() => {
  if (viewFilter.value === 'all') return props.trackerViewersActive
  if (viewFilter.value === 'share') return props.trackerViewersActive.filter(item => item.source === 'share')
  return props.trackerViewersActive.filter(item => item.source !== 'share')
})

const groupedTrackerViews = computed(() => groupItemsByDay(filteredTrackerViews.value))

const viewCountLabel = computed(() => {
  const count = filteredTrackerViews.value.length
  return `${count.toLocaleString()} view${count === 1 ? '' : 's'} loaded`
})

const activeViewerLabel = computed(() => {
  const count = filteredActiveViewers.value.length
  return `${count.toLocaleString()} active session${count === 1 ? '' : 's'}`
})

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
  return groupItemsByDay(filteredActivity.value)
})

const recentActivityPeek = computed(() => props.trackerActivity.slice(0, 3))
const restoreCanApply = computed(() => props.activityRestorePreview?.can_restore !== false)

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

function countActivityForFilter(filterValue) {
  if (filterValue === 'all') return props.trackerActivity.length
  return props.trackerActivity.filter((item) => activityFilterForEvent(item.event_type) === filterValue).length
}

function countViewsForFilter(filterValue) {
  if (filterValue === 'all') return props.trackerViews.length
  if (filterValue === 'share') return props.trackerViews.filter(item => item.source === 'share').length
  return props.trackerViews.filter(item => item.source !== 'share').length
}

function isCurrentViewer(view) {
  return Boolean(props.currentUserId && view?.viewer_user_id && String(view.viewer_user_id) === String(props.currentUserId))
}

function viewDeviceLabel(deviceType) {
  const labels = { mobile: 'Mobile', tablet: 'Tablet', desktop: 'Desktop' }
  return labels[deviceType] || 'Device unknown'
}

function viewClientSummary(view) {
  return [view?.client?.browser, view?.client?.operating_system].filter(Boolean).join(' · ')
}

function viewPresenceClientLabel(view) {
  return [viewDeviceLabel(view?.device_type), view?.client?.browser].filter(Boolean).join(' · ')
}

function viewCountryLabel(countryCode) {
  const code = String(countryCode || '').trim().toUpperCase()
  if (!code) return ''
  if (code === 'T1') return 'Tor network'
  if (code === 'XX') return 'Unknown country'
  try {
    return REGION_NAMES?.of(code) || code
  } catch (_error) {
    return code
  }
}

function viewLocationLabel(view) {
  return [
    view?.client?.city,
    view?.client?.region,
    viewCountryLabel(view?.client?.country),
  ].filter(Boolean).join(', ')
}

function shortVisitId(visitId) {
  const compact = String(visitId || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase()
  return compact ? compact.slice(-8) : ''
}

function hasVisitDetails(view) {
  return Boolean(
    view?.visit_id
    || view?.client?.ip_address
    || view?.client?.browser
    || view?.client?.operating_system
    || view?.client?.language
    || view?.client?.city
    || view?.client?.region
    || view?.client?.country
    || view?.client?.timezone
  )
}

function viewSourceLabel(view) {
  if (view?.source !== 'share') return 'Vueio workspace'
  const shareId = String(view?.share_id || '').trim()
  return shareId ? `Share link ${shareId.slice(-6)}` : 'Share link'
}

function viewDateTime(timestamp) {
  const value = Number(timestamp || 0)
  return value ? new Date(value * 1000).toISOString() : ''
}

function viewTimestamp(timestamp) {
  const value = Number(timestamp || 0)
  if (!value) return ''
  const date = new Date(value * 1000)
  const today = new Date()
  const sameDay = startOfDay(date) === startOfDay(today)
  const sameYear = date.getFullYear() === today.getFullYear()
  return date.toLocaleString(undefined, {
    ...(sameDay ? {} : { month: 'short', day: 'numeric' }),
    ...(!sameYear ? { year: 'numeric' } : {}),
    hour: 'numeric',
    minute: '2-digit',
  })
}

function groupItemsByDay(items) {
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
  items.forEach((item) => {
    const createdAt = Number(item.created_at || 0)
    if (createdAt >= todayBoundary) groups[0].items.push(item)
    else if (createdAt >= yesterdayBoundary) groups[1].items.push(item)
    else if (createdAt >= weekBoundary) groups[2].items.push(item)
    else groups[3].items.push(item)
  })
  return groups.filter(group => group.items.length)
}

function activityFilterForEvent(eventType) {
  if ([
    'version_added',
    'versions_bulk_updated',
    'versions_updated',
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

function canRestoreActivity(item) {
  return Boolean(props.canRestoreHistory && item?.restoreable && !item?.current_point)
}

function recoveryUnavailableLabel(item) {
  if (item?.recovery_unavailable_reason === 'expired') return 'Expired'
  if (item?.recovery_unavailable_reason === 'too_large') return 'Not saved'
  if (item?.recovery_unavailable_reason === 'legacy') return 'Older record'
  return 'Unavailable'
}

function recoveryUnavailableCopy(item) {
  if (item?.recovery_unavailable_reason === 'expired') {
    return 'This older recovery point expired after the tracker reached its protected History storage limit. The activity record remains.'
  }
  if (item?.recovery_unavailable_reason === 'too_large') {
    return 'This tracker state was too large to save safely. The activity record remains.'
  }
  if (item?.recovery_unavailable_reason === 'legacy') {
    return 'This change was recorded before full tracker History was available.'
  }
  return 'This recovery point is no longer available.'
}

function eventBadgeStyle(eventType) {
  const baseColor = getTrackerEventColor(eventType)
  return {
    color: baseColor,
    background: `color-mix(in srgb, ${baseColor} 14%, transparent)`,
    boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${baseColor} 24%, transparent)`,
  }
}

function avatarStyle(seed) {
  const hue = getIdentityColor(seed || 'user')
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
  gap: 0;
  min-height: 0;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  color: var(--v-text);
}

.td-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-4);
  padding: 24px 26px 18px;
  flex-shrink: 0;
}

.td-head-copy {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  min-width: 0;
  flex: 1 1 auto;
}

.td-title {
  margin: 0;
  color: var(--v-text);
  font-size: 28px;
  font-weight: 680;
  letter-spacing: -0.025em;
  line-height: 1.05;
  min-width: 0;
  text-wrap: balance;
}

.td-meta {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.td-close {
  flex-shrink: 0;
  width: var(--v-btn-height);
  min-width: var(--v-btn-height);
  height: var(--v-btn-height);
}

.td-mode-tabs {
  width: 100%;
  padding: 0 26px;
  flex-shrink: 0;
}

.td-mode-tabs :deep(.v-tabs--rail) {
  width: 100%;
  gap: 0;
  padding: 0;
  border-bottom-color: var(--v-divider-subtle);
}

.td-mode-tabs :deep(.v-tab-btn) {
  min-height: 42px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
}

.td-mode-tabs :deep(.v-tab-btn:hover:not(:disabled)) {
  background: var(--v-surface-tint);
  color: var(--v-text);
}

.td-mode-tabs :deep(.v-tab-btn.active) {
  background: transparent;
  color: var(--v-text);
  box-shadow: inset 0 -2px 0 var(--v-accent);
}

.td-body {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 26px 30px;
}

.td-overview {
  gap: 24px;
}

.td-activity {
  gap: var(--v-space-4);
}

.td-views {
  gap: var(--v-space-4);
}

.td-section {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  flex-shrink: 0;
}

.td-section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.td-section-title {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 650;
  letter-spacing: -0.01em;
}

.td-section-copy {
  margin: 3px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.td-section-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: var(--v-btn-height-sm);
  padding: 0 9px;
  border-radius: var(--v-button-radius);
  border: 1px solid var(--v-control-border);
  background: var(--v-control-bg);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized),
    color var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-section-link .icon {
  width: 12px;
  height: 12px;
}

.td-section-link:hover {
  color: var(--v-text);
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border-hover);
}

.td-section-link:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.td-delivery {
  display: grid;
  grid-template-columns: minmax(148px, 0.68fr) minmax(290px, 1.32fr);
  min-height: 224px;
  overflow: hidden;
  border: 1px solid var(--v-surface-border-strong);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  box-shadow: var(--v-surface-shadow-raised);
  flex-shrink: 0;
}

.td-delivery-primary {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--v-space-5);
  min-width: 0;
  padding: 24px 22px 22px;
  border-right: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-tint);
}

.td-delivery-number {
  display: inline-flex;
  align-items: baseline;
  color: var(--v-text);
  font-size: 72px;
  font-weight: 620;
  letter-spacing: -0.065em;
  line-height: 0.84;
  font-variant-numeric: tabular-nums;
}

.td-delivery-number > span {
  margin-left: 5px;
  color: var(--v-accent);
  font-size: 27px;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.td-delivery-copy h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
}

.td-delivery-copy p {
  margin: 5px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
  text-wrap: pretty;
}

.td-delivery-detail {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--v-space-4);
  min-width: 0;
  padding: 20px;
}

.td-delivery-count {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.td-delivery-count > span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.td-delivery-count strong {
  color: var(--v-text);
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.025em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.td-delivery-count small {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 550;
  letter-spacing: 0;
}

.td-progress-track {
  position: relative;
  display: flex;
  width: 100%;
  height: 7px;
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

.td-status-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  padding-top: var(--v-space-3);
  border-top: 1px solid var(--v-divider-subtle);
}

.td-status-cell {
  display: grid;
  grid-template-columns: 6px minmax(0, 1fr);
  align-content: start;
  column-gap: 7px;
  row-gap: 3px;
  min-width: 0;
  padding: 0 8px;
  border-left: 1px solid var(--v-divider-subtle);
}

.td-status-cell:first-child {
  padding-left: 0;
  border-left: 0;
}

.td-status-cell:last-child {
  padding-right: 0;
}

.td-status-cell.is-empty {
  opacity: 0.48;
}

.td-status-mark {
  width: 6px;
  height: 6px;
  margin-top: 5px;
  border-radius: var(--v-radius-full);
}

.td-status-cell strong {
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 650;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.td-status-cell > span:last-child {
  grid-column: 1 / -1;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 550;
  line-height: 1.25;
  text-wrap: balance;
}

/* ─── Tracker metrics ────────────────────────────────────────────────── */
.td-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: var(--v-space-1) 0;
  border-top: 1px solid var(--v-divider-subtle);
  border-bottom: 1px solid var(--v-divider-subtle);
  flex-shrink: 0;
}

.td-metric {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  min-width: 0;
  min-height: 74px;
  padding: 12px 15px;
  border-left: 1px solid var(--v-divider-subtle);
}

.td-metric:first-child {
  padding-left: 2px;
  border-left: 0;
}

.td-metric:last-child {
  padding-right: 2px;
}

.td-metric > .icon {
  position: absolute;
  top: 14px;
  right: 15px;
  width: 13px;
  height: 13px;
  color: var(--v-accent);
  opacity: 0.82;
}

.td-metric-value {
  display: inline-flex;
  align-items: baseline;
  color: var(--v-text);
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.025em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.td-metric-value small {
  margin-left: 3px;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  font-weight: 600;
  letter-spacing: 0;
}

.td-metric-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 550;
  line-height: 1.25;
  text-wrap: balance;
}

.td-peek-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--v-divider-subtle);
  display: flex;
  flex-direction: column;
}

.td-peek-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
  min-height: 58px;
  padding: 11px 2px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.td-peek-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--v-radius-md);
  flex-shrink: 0;
}

.td-peek-icon .icon {
  width: 13px;
  height: 13px;
}

.td-peek-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.td-peek-summary {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 570;
  line-height: 1.35;
  min-width: 0;
  text-wrap: pretty;
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
  font-variant-numeric: tabular-nums;
}

.td-peek-meta > span:nth-child(2) {
  opacity: 0.55;
}

.td-peek-shot {
  max-width: 120px;
  padding: 4px 7px;
  border-radius: var(--v-radius-sm);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.035em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.td-activity-head {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  flex-shrink: 0;
  position: sticky;
  top: -22px;
  z-index: 2;
  margin-top: -22px;
  padding: 22px 0 13px;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-canvas);
}

.td-activity-intro {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.td-activity-intro-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.td-activity-intro h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-xl);
  font-weight: 650;
  letter-spacing: -0.015em;
}

.td-activity-intro p {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
  text-wrap: pretty;
}

.td-activity-count {
  flex-shrink: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.td-filter-rail {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  overflow-x: visible;
  padding: 1px 0 3px;
  overscroll-behavior-x: contain;
}

.td-filter-chip {
  gap: 6px;
  flex-shrink: 0;
  min-height: 32px;
  padding: 0 9px;
  border-radius: var(--v-radius-md);
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized),
    border-color var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-activity-error {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--v-danger-border);
  border-radius: var(--v-radius-lg);
  background: var(--v-danger-bg);
  color: var(--v-danger-text);
}

.td-activity-error > .icon {
  width: 17px;
  height: 17px;
}

.td-activity-error strong,
.td-activity-error p {
  margin: 0;
}

.td-activity-error strong {
  display: block;
  font-size: var(--v-text-sm);
}

.td-activity-error p {
  margin-top: 2px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  line-height: 1.35;
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
  color: var(--v-accent);
  background: var(--v-control-bg-active);
  border-color: var(--v-control-border-active);
  box-shadow: var(--v-control-ring-selected);
}

.td-filter-chip-label {
  white-space: nowrap;
  font-size: var(--v-text-xs);
  font-weight: 650;
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
  background: var(--v-accent-muted);
  color: var(--v-accent);
}

.td-filter-chip:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

/* ─── Viewer history ─────────────────────────────────────────────────── */
.td-views-refresh {
  width: var(--v-btn-height-sm);
  min-width: var(--v-btn-height-sm);
  height: var(--v-btn-height-sm);
  flex-shrink: 0;
}

.td-views-refresh .icon {
  width: 13px;
  height: 13px;
}

.td-views-refresh .icon.is-spinning {
  animation: td-spin 850ms linear infinite;
}

.td-presence {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-strong);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  box-shadow: var(--v-surface-shadow-raised);
  flex-shrink: 0;
}

.td-presence-head {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 14px 15px 12px;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-tint);
}

.td-presence-signal {
  width: 8px;
  height: 8px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
  box-shadow: 0 0 0 4px var(--v-accent-muted);
}

.td-presence-head h3,
.td-presence-head p {
  margin: 0;
}

.td-presence-head h3 {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  line-height: 1.25;
}

.td-presence-head p {
  margin-top: 2px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-variant-numeric: tabular-nums;
}

.td-presence-list,
.td-view-history,
.td-view-items {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.td-presence-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 11px 14px;
}

.td-presence-row + .td-presence-row {
  border-top: 1px solid var(--v-divider-subtle);
}

.td-view-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--v-radius-md);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.td-presence-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
}

.td-view-person {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.td-view-person strong {
  min-width: 0;
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 620;
}

.td-presence-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.td-view-error {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--v-danger-border);
  border-radius: var(--v-radius-md);
  background: var(--v-danger-bg);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.td-view-error > .icon {
  width: 16px;
  height: 16px;
  color: var(--v-danger);
}

.td-view-skeleton {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--v-divider-subtle);
}

.td-view-skeleton-row {
  display: grid;
  grid-template-columns: 32px minmax(120px, 0.72fr) minmax(90px, 0.28fr);
  align-items: center;
  gap: 12px;
  min-height: 72px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.td-view-skeleton-row > span {
  display: block;
  height: 10px;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-tint-strong);
}

.td-view-skeleton-row > span:first-child {
  width: 32px;
  height: 32px;
  border-radius: var(--v-radius-md);
}

.td-view-skeleton-row > span:last-child {
  width: 70%;
  justify-self: end;
}

.td-view-history {
  gap: 18px;
  min-width: 0;
}

.td-view-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: flex-start;
  gap: 11px;
  min-width: 0;
  padding: 13px 2px 13px 0;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.td-view-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  color: var(--v-text-muted);
  box-shadow: var(--v-surface-shadow-inset);
}

.td-view-icon .icon {
  width: 13px;
  height: 13px;
}

.td-view-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  padding-top: 1px;
}

.td-view-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-width: 0;
}

.td-view-topline time {
  flex-shrink: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.td-view-body > p {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-md);
  font-weight: 560;
  line-height: 1.4;
  text-wrap: pretty;
}

.td-view-meta {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 13px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.td-view-meta > span + span {
  position: relative;
}

.td-view-meta > span + span::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -8px;
  width: 3px;
  height: 3px;
  border-radius: var(--v-radius-full);
  background: var(--v-text-muted);
  opacity: 0.55;
  transform: translateY(-50%);
}

.td-view-details {
  min-width: 0;
  margin-top: 2px;
}

.td-view-details summary {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
  color: var(--v-text-muted);
  cursor: pointer;
  font-size: var(--v-text-xs);
  font-weight: 680;
  list-style: none;
  transition: color var(--v-transition-fast);
}

.td-view-details summary::-webkit-details-marker {
  display: none;
}

.td-view-details summary:hover {
  color: var(--v-text-secondary);
}

.td-view-details summary .icon {
  width: 12px;
  height: 12px;
  transition: transform var(--v-transition-fast);
}

.td-view-details[open] summary .icon {
  transform: rotate(180deg);
}

.td-view-details dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px 18px;
  margin: 3px 0 2px;
  padding: 11px 12px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.td-view-details dl > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.td-view-details dt {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 680;
}

.td-view-details dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  line-height: 1.4;
}

.td-view-details code {
  font-family: var(--v-font-mono);
  font-size: inherit;
}

.td-view-privacy {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 9px;
  align-items: flex-start;
  padding-top: var(--v-space-3);
  border-top: 1px solid var(--v-divider-subtle);
  color: var(--v-text-muted);
  flex-shrink: 0;
}

.td-view-privacy .icon {
  width: 15px;
  height: 15px;
  margin-top: 1px;
}

.td-view-privacy p {
  margin: 0;
  font-size: var(--v-text-xs);
  line-height: 1.5;
  text-wrap: pretty;
}

/* ─── Timeline ───────────────────────────────────────────────────────── */
.td-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
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
  padding: 0;
}

.td-timeline-day-label {
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 650;
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
  gap: 0;
  position: relative;
}

.td-timeline-items::before {
  content: '';
  position: absolute;
  top: 22px;
  bottom: 14px;
  left: 17px;
  width: 1px;
  background: var(--v-divider-subtle);
  pointer-events: none;
}

.td-timeline-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: var(--v-space-3);
  padding: 12px 4px 12px 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  align-items: flex-start;
  position: relative;
}

.td-timeline-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--v-radius-md);
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

.td-timeline-topline {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.td-timeline-summary {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 570;
  line-height: 1.4;
  word-break: break-word;
}

.td-restore-action,
.td-current-point {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  gap: 5px;
  min-height: 28px;
  padding-inline: 8px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-xs);
  font-weight: 650;
  white-space: nowrap;
}

.td-recovery-unavailable {
  flex-shrink: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 28px;
}

.td-recovery-body {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
}

.td-recovery-summary {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--v-border);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
}

.td-recovery-summary-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--v-radius-md);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.td-recovery-summary-icon .icon {
  width: 18px;
  height: 18px;
}

.td-recovery-summary p,
.td-recovery-shots,
.td-recovery-note,
.td-recovery-error p {
  margin: 0;
}

.td-recovery-summary p {
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 600;
  line-height: 1.45;
  text-wrap: pretty;
}

.td-recovery-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.td-recovery-facts > div {
  padding: 11px 12px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-tint-strong);
}

.td-recovery-facts dt {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.td-recovery-facts dd {
  margin: 3px 0 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 680;
  font-variant-numeric: tabular-nums;
}

.td-recovery-scope {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.td-recovery-scope > p:first-child {
  margin: 0;
}

.td-recovery-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.td-recovery-shots,
.td-recovery-note {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.td-recovery-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 11px;
  border: 1px solid var(--v-danger-border);
  border-radius: var(--v-radius-md);
  background: var(--v-danger-bg);
  color: var(--v-danger-text);
}

.td-recovery-error .icon {
  flex: 0 0 auto;
  width: 15px;
  height: 15px;
  margin-top: 2px;
}

.td-recovery-error p {
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.td-recovery-confirm .icon.is-spinning {
  animation: td-spin 1s linear infinite;
}

.td-restore-action {
  color: var(--v-text-secondary);
  transition:
    color var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-restore-action:hover:not(:disabled) {
  color: var(--v-accent);
  background: var(--v-accent-subtle);
  transform: translateY(-1px);
}

.td-restore-action:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}

.td-restore-action:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.td-restore-action .icon,
.td-current-point .icon {
  width: 12px;
  height: 12px;
}

.td-restore-action .icon.is-spinning {
  animation: td-spin 1s linear infinite;
}

.td-current-point {
  border: 1px solid color-mix(in srgb, var(--v-accent) 22%, transparent);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.td-current-point {
  background: color-mix(in srgb, var(--v-accent) 9%, transparent);
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
  border-radius: var(--v-radius-sm);
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
  display: inline-flex;
  align-items: center;
  color: var(--v-accent);
  font-size: var(--v-text-3xs);
  font-weight: 650;
  letter-spacing: 0.02em;
  text-transform: lowercase;
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
  border-radius: var(--v-radius-sm);
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

.td-content-enter-active,
.td-content-leave-active {
  transition:
    opacity var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.td-content-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.td-content-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ─── Empty states ───────────────────────────────────────────────────── */
.td-empty {
  margin-top: var(--v-space-1);
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .td-close {
    width: var(--v-btn-height-lg);
    min-width: var(--v-btn-height-lg);
    height: var(--v-btn-height-lg);
  }

  .td-head {
    padding: 18px 16px 14px;
  }

  .td-title {
    font-size: 22px;
  }

  .td-mode-tabs {
    padding: 0 16px;
  }

  .td-body {
    padding: 16px 16px calc(22px + env(safe-area-inset-bottom, 0px));
  }

  .td-overview {
    gap: var(--v-space-5);
  }

  .td-delivery {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .td-delivery-primary {
    min-height: 148px;
    padding: var(--v-space-5);
    border-right: 0;
    border-bottom: 1px solid var(--v-divider-subtle);
  }

  .td-delivery-number {
    font-size: 58px;
  }

  .td-delivery-number > span {
    font-size: 23px;
  }

  .td-delivery-detail {
    padding: var(--v-space-4);
  }

  .td-status-cell {
    padding-inline: 6px;
  }

  .td-status-cell > span:last-child {
    font-size: 9px;
  }

  .td-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .td-metric:nth-child(odd) {
    padding-left: 2px;
    border-left: 0;
  }

  .td-metric:nth-child(even) {
    padding-right: 2px;
  }

  .td-metric:nth-child(n + 3) {
    border-top: 1px solid var(--v-divider-subtle);
  }

  .td-section-head {
    align-items: flex-start;
  }

  .td-section-link,
  .td-filter-chip {
    min-height: var(--v-btn-height-lg);
  }

  .td-views-refresh {
    width: var(--v-btn-height-lg);
    min-width: var(--v-btn-height-lg);
    height: var(--v-btn-height-lg);
  }

  .td-presence-row {
    grid-template-columns: 30px minmax(0, 1fr);
    align-items: start;
    padding-block: 12px;
  }

  .td-presence-meta {
    grid-column: 2;
    flex-direction: row;
    align-items: center;
    gap: 10px;
    margin-top: -4px;
  }

  .td-peek-row {
    grid-template-columns: 32px minmax(0, 1fr);
  }

  .td-peek-shot {
    grid-column: 2;
    justify-self: start;
  }

  .td-activity-head {
    top: -16px;
    margin-top: -16px;
    padding-top: 16px;
    background: var(--v-modal-bg);
  }

  .td-filter-rail {
    flex-wrap: nowrap;
    overflow-x: auto;
  }

  .td-activity-error {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .td-activity-error .v-btn {
    grid-column: 2;
    justify-self: start;
    min-height: var(--v-btn-height-lg);
  }

  .td-timeline-item {
    grid-template-columns: 32px minmax(0, 1fr);
    gap: 10px;
  }

  .td-timeline-badge {
    width: 30px;
    height: 30px;
  }

  .td-restore-action,
  .td-current-point {
    min-height: var(--v-btn-height-lg);
    padding-inline: 10px;
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

  .td-view-row {
    grid-template-columns: 30px minmax(0, 1fr);
    gap: 10px;
  }

  .td-view-icon {
    width: 30px;
    height: 30px;
  }

  .td-view-details summary {
    min-height: var(--v-btn-height-lg);
  }

  .td-recovery-confirm {
    min-height: var(--v-btn-height-lg);
  }
}

@media (max-width: 420px) {
  .td-head {
    padding-inline: 14px;
  }

  .td-mode-tabs {
    padding-inline: 14px;
  }

  .td-body {
    padding-inline: 14px;
  }

  .td-recovery-summary {
    grid-template-columns: 36px minmax(0, 1fr);
    padding: 12px;
  }

  .td-recovery-summary-icon {
    width: 36px;
    height: 36px;
  }

  .td-delivery-primary {
    min-height: 132px;
  }

  .td-delivery-number {
    font-size: 52px;
  }

  .td-status-cell {
    padding-inline: 4px;
  }

  .td-section-copy {
    max-width: 190px;
  }

  .td-activity-intro {
    align-items: center;
  }

  .td-view-topline {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .td-view-details dl {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .td-content-enter-active,
  .td-content-leave-active,
  .td-progress-segment,
  .td-load-more .icon,
  .td-restore-action,
  .td-restore-action .icon.is-spinning,
  .td-recovery-confirm .icon.is-spinning,
  .td-views-refresh .icon.is-spinning {
    transition: none;
    animation: none;
  }

  .td-view-details summary .icon {
    transition: none;
  }
}
</style>
