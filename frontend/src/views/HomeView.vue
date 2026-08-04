<template>
  <div class="home-view">
    <header class="v-page-header home-header">
      <div class="home-heading">
        <p class="v-eyebrow home-date">{{ todayLabel }}</p>
        <h1 class="v-page-title">Good {{ daypart }}, {{ firstName }}.</h1>
        <p class="home-intro">{{ introCopy }}</p>
      </div>

      <div v-if="isAdmin" class="v-page-actions">
        <button type="button" class="v-btn v-btn-primary" @click="openCreateProjectModal">
          <svg class="icon" aria-hidden="true"><use href="#icon-plus" /></svg>
          New project
        </button>
      </div>
    </header>

    <main class="home-content">
      <section class="home-stage" aria-labelledby="home-focus-title">
        <div class="home-stage-heading">
          <p class="v-eyebrow">Your workspace</p>
          <h2 id="home-focus-title">Continue where you left off</h2>
        </div>

        <div v-if="recentLoading" class="v-surface-panel home-stage-loading">
          <svg class="icon spinning" aria-hidden="true"><use href="#icon-loader" /></svg>
          Finding your place
        </div>

        <div v-else-if="featuredItem" class="v-surface-panel home-stage-surface">
          <button
            type="button"
            class="home-feature"
            :aria-label="`Continue ${featuredItem.title}`"
            @click="openContinueItem(featuredItem)"
          >
            <span class="home-feature-media" aria-hidden="true">
              <span class="home-feature-fallback">{{ projectInitials(featuredProject) }}</span>
              <img
                v-if="featuredProject?.thumbnail_path"
                :src="getProjectThumbnailUrl(featuredProject.id, featuredProject.thumbnail_path)"
                alt=""
                @error="hideBrokenImage"
              >
              <span class="home-feature-media-tag">
                <svg class="icon"><use :href="featuredItem.type === 'tracker' ? '#icon-project' : '#icon-folder'" /></svg>
                {{ featuredItem.type === 'tracker' ? 'Tracker' : 'Project' }}
              </span>
            </span>

            <span class="home-feature-copy">
              <span class="v-eyebrow home-feature-kicker">{{ featuredKicker }}</span>
              <strong class="home-feature-title">{{ featuredItem.title }}</strong>
              <span class="home-feature-context">{{ featuredContext }}</span>
              <span class="home-feature-description">{{ featuredDescription }}</span>

              <span class="home-feature-meta">
                <span v-if="featuredProject" class="v-status" :class="statusClass(featuredProject.status)">
                  {{ formatStatus(featuredProject.status || 'not_started') }}
                </span>
                <span v-if="featuredProject">{{ featuredProject.shot_count }} shot{{ featuredProject.shot_count === 1 ? '' : 's' }}</span>
                <span v-if="featuredProject?.due_date">Due {{ formatProjectDate(featuredProject.due_date) }}</span>
              </span>

              <span class="home-feature-action">
                Open {{ featuredItem.type === 'tracker' ? 'tracker' : 'project' }}
                <svg class="icon" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
              </span>
            </span>
          </button>

          <aside class="home-recents" aria-label="Other recent work">
            <div class="v-section-label home-recents-head">
              <span>Recent</span>
              <span class="v-section-count">{{ secondaryContinueItems.length }}</span>
            </div>
            <button
              v-for="item in secondaryContinueItems"
              :key="`${item.type}-${item.projectId || ''}-${item.id}`"
              type="button"
              class="home-recent-row"
              :aria-label="`Open ${item.title}`"
              @click="openContinueItem(item)"
            >
              <span class="home-recent-icon" aria-hidden="true">
                <svg class="icon"><use :href="item.type === 'tracker' ? '#icon-project' : '#icon-folder'" /></svg>
              </span>
              <span class="home-recent-copy">
                <strong>{{ item.title }}</strong>
                <span>{{ continueSubtitle(item) }}</span>
              </span>
              <svg class="icon home-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
            </button>
            <div v-if="!secondaryContinueItems.length" class="home-recents-empty">
              More recently opened work will appear here.
            </div>
          </aside>
        </div>

        <div v-else class="v-surface-panel v-empty-state home-stage-empty">
          <svg class="icon v-empty-state-icon" aria-hidden="true"><use href="#icon-play" /></svg>
          <div class="v-empty-state-title">Your next session starts here</div>
          <div class="v-empty-state-copy">Open a project or tracker and Vue will keep your place.</div>
          <button v-if="isAdmin" type="button" class="v-btn v-btn-primary" @click="goToProjects">
            Browse projects
          </button>
        </div>
      </section>

      <section class="home-pulse" aria-label="Workspace pulse">
        <div class="home-pulse-label">
          <span class="home-live-dot" aria-hidden="true"></span>
          Workspace pulse
        </div>
        <div class="home-pulse-metrics">
          <span><strong>{{ activeProjects.length }}</strong> active project{{ activeProjects.length === 1 ? '' : 's' }}</span>
          <span><strong>{{ dueSoonCount }}</strong> due this week</span>
          <button type="button" @click="toggleGlobalActivityTray">
            <strong>{{ globalActivityUnreadCount }}</strong> unread update{{ globalActivityUnreadCount === 1 ? '' : 's' }}
            <svg class="icon" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
          </button>
        </div>
      </section>

      <div class="home-lower">
        <section class="home-section">
          <header class="home-section-header">
            <div>
              <p class="v-eyebrow">In production</p>
              <h2>Active projects</h2>
            </div>
            <button type="button" class="v-btn v-btn-quiet v-btn-sm" @click="goToProjects">
              View all
              <svg class="icon" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
            </button>
          </header>

          <div v-if="activeProjects.length" class="v-surface-panel home-project-list">
            <button
              v-for="project in activeProjects"
              :key="project.id"
              type="button"
              class="home-project-row"
              :aria-label="`Open project ${project.title}`"
              @click="openProject(project.id)"
            >
              <span class="home-project-thumbnail" aria-hidden="true">
                <svg class="icon"><use href="#icon-project" /></svg>
                <img
                  v-if="project.thumbnail_path"
                  :src="getProjectThumbnailUrl(project.id, project.thumbnail_path)"
                  alt=""
                  loading="lazy"
                  decoding="async"
                  @error="hideBrokenImage"
                >
              </span>
              <span class="home-project-copy">
                <strong>{{ project.title }}</strong>
                <span>
                  {{ project.shot_count }} shot{{ project.shot_count === 1 ? '' : 's' }}
                  <template v-if="project.due_date"> · Due {{ formatProjectDate(project.due_date) }}</template>
                </span>
              </span>
              <span class="v-status" :class="statusClass(project.status)">
                {{ formatStatus(project.status || 'not_started') }}
              </span>
              <svg class="icon home-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
            </button>
          </div>

          <div v-else class="v-surface-panel v-empty-state home-empty-state">
            <svg class="icon v-empty-state-icon" aria-hidden="true"><use href="#icon-check" /></svg>
            <div class="v-empty-state-title">Nothing is in production</div>
            <div class="v-empty-state-copy">{{ emptyProjectsCopy }}</div>
          </div>
        </section>

        <aside class="home-section" aria-labelledby="home-activity-title">
          <header class="home-section-header">
            <div>
              <p class="v-eyebrow">Across your work</p>
              <h2 id="home-activity-title">Latest activity</h2>
            </div>
            <button
              type="button"
              class="v-icon-action is-muted is-compact"
              aria-label="Refresh recent activity"
              :disabled="activityLoading"
              @click="loadActivity"
            >
              <svg class="icon" :class="{ spinning: activityLoading }"><use href="#icon-refresh" /></svg>
            </button>
          </header>

          <div v-if="activityLoading && !activityItems.length" class="v-surface-panel home-list-loading">
            <svg class="icon spinning" aria-hidden="true"><use href="#icon-loader" /></svg>
            Loading activity
          </div>

          <div v-else-if="activityItems.length" class="v-surface-panel home-activity-list">
            <button
              v-for="item in activityItems"
              :key="item.id"
              type="button"
              class="home-activity-row"
              :class="{ 'is-disabled': !canOpenActivity(item) }"
              :disabled="!canOpenActivity(item)"
              @click="openActivity(item)"
            >
              <span class="home-activity-icon" aria-hidden="true">
                <svg class="icon"><use :href="getTrackerEventIcon(item.event_type)" /></svg>
              </span>
              <span class="home-activity-copy">
                <strong>{{ activitySummary(item) }}</strong>
                <span>{{ activityContext(item) }}</span>
              </span>
              <time :datetime="activityDateTime(item)">{{ formatActivityRelativeTimestamp(item.created_at) }}</time>
            </button>
            <button type="button" class="home-list-footer" @click="toggleGlobalActivityTray">
              View all activity
              <svg class="icon" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
            </button>
          </div>

          <div v-else class="v-surface-panel v-empty-state home-empty-state">
            <svg class="icon v-empty-state-icon" aria-hidden="true"><use href="#icon-check" /></svg>
            <div class="v-empty-state-title">You’re caught up</div>
            <div class="v-empty-state-copy">Comments, versions, assignments, and status changes will appear here.</div>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../lib/api'
import { getTrackerEventIcon, getTrackerStatusLabel as formatStatus } from '../lib/trackerCatalogs'
import { useActivityStore } from '../ownership/activity'
import { useAppChromeStore } from '../ownership/appChrome'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useTrackerStore } from '../ownership/tracker'
import { useViewerStore } from '../ownership/viewer'
import { formatActivityRelativeTimestamp, formatLocaleDate } from '../utils/formatters'

const { currentUser, isAdmin } = useSessionAuthStore()
const { projects, openProject, openCreateProjectModal } = useProjectWorkspaceStore()
const { openProjectTracker } = useTrackerStore()
const { goToProjects } = useAppChromeStore()
const {
  globalActivityUnreadCount,
  toggleGlobalActivityTray,
  openGlobalActivityTarget,
} = useActivityStore()
const { getProjectThumbnailUrl } = useViewerStore().media.core

const recentItems = ref([])
const recentLoading = ref(true)
const activityItems = ref([])
const activityLoading = ref(true)

const firstName = computed(() => {
  const name = String(currentUser.value?.display_name || currentUser.value?.username || 'there').trim()
  return name.split(/\s+/)[0] || 'there'
})

const now = new Date()
const daypart = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return 'morning'
  if (hour < 18) return 'afternoon'
  return 'evening'
})
const todayLabel = computed(() => now.toLocaleDateString(undefined, {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
}))

const introCopy = computed(() => (
  isAdmin.value
    ? 'A clear view of the work moving across your studio.'
    : 'A clear view of the work shared with you.'
))

const visibleProjectIds = computed(() => new Set(projects.value.map(project => String(project.id))))
const visibleRecentItems = computed(() => recentItems.value.filter((item) => {
  const projectId = item.projectId || (item.type === 'project' ? item.id : null)
  return projectId && visibleProjectIds.value.has(String(projectId))
}))

const fallbackRecentProjects = computed(() => (
  [...projects.value]
    .sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0))
    .slice(0, 4)
    .map(project => ({
      type: 'project',
      id: project.id,
      projectId: project.id,
      title: project.title,
      subtitle: 'Recently updated',
    }))
))

const continueItems = computed(() => (
  visibleRecentItems.value.length
    ? visibleRecentItems.value.slice(0, 4)
    : fallbackRecentProjects.value
))
const featuredItem = computed(() => continueItems.value[0] || null)
const secondaryContinueItems = computed(() => continueItems.value.slice(1, 4))
const featuredProject = computed(() => {
  const projectId = featuredItem.value?.projectId || (
    featuredItem.value?.type === 'project' ? featuredItem.value.id : null
  )
  return projects.value.find(project => String(project.id) === String(projectId)) || null
})
const featuredKicker = computed(() => (
  featuredItem.value?.type === 'tracker' ? 'Resume review' : 'Return to project'
))
const featuredContext = computed(() => {
  if (!featuredItem.value) return ''
  const context = continueSubtitle(featuredItem.value)
  const viewedAt = featuredItem.value.viewedAt
    ? formatActivityRelativeTimestamp(featuredItem.value.viewedAt)
    : ''
  return [context, viewedAt].filter(Boolean).join(' · ')
})
const featuredDescription = computed(() => (
  featuredProject.value?.description
  || 'Pick up the review, files, and conversation exactly where you left them.'
))

const activeProjects = computed(() => (
  projects.value
    .filter(project => project.status === 'in_progress')
    .sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0))
    .slice(0, 6)
))

const dueSoonCount = computed(() => {
  const current = new Date()
  const cutoff = new Date(current)
  cutoff.setDate(cutoff.getDate() + 7)
  return projects.value.filter((project) => {
    if (!project.due_date || project.status === 'done') return false
    const due = new Date(`${project.due_date}T23:59:59`)
    return !Number.isNaN(due.getTime()) && due >= current && due <= cutoff
  }).length
})

const emptyProjectsCopy = computed(() => (
  isAdmin.value
    ? 'Start a project when the next job is ready to move.'
    : 'Projects in progress and shared with you will appear here.'
))

function formatProjectDate(value) {
  return formatLocaleDate(value, { options: { month: 'short', day: 'numeric' } }) || value
}

function continueSubtitle(item) {
  const subtitle = String(item?.subtitle || '').trim()
  if (!subtitle || subtitle.toLowerCase() === item.type) {
    const project = projects.value.find(entry => String(entry.id) === String(item?.projectId || item?.id))
    return project?.title || 'Recently viewed'
  }
  return subtitle
}

function projectInitials(project) {
  const words = String(project?.title || featuredItem.value?.title || 'Vue')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  return words.slice(0, 2).map(word => word[0]).join('').toUpperCase() || 'V'
}

function statusClass(status) {
  if (status === 'in_progress') return 'v-status-active'
  if (status === 'waiting_review') return 'v-status-review'
  if (status === 'edits_requested') return 'v-status-hold'
  if (status === 'done') return 'v-status-done'
  return 'v-status-draft'
}

function hideBrokenImage(event) {
  event.target.style.display = 'none'
}

function activityDateTime(item) {
  const value = Number(item?.created_at)
  if (!Number.isFinite(value)) return ''
  return new Date(value * 1000).toISOString()
}

async function loadRecentItems() {
  recentLoading.value = true
  try {
    const { data } = await api.get('/api/recently-viewed', { params: { limit: 6 } })
    recentItems.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    recentItems.value = []
  } finally {
    recentLoading.value = false
  }
}

async function loadActivity() {
  activityLoading.value = true
  try {
    const { data } = await api.get('/api/notifications/feed', {
      params: { limit: 5, calendar_days: 14 },
    })
    activityItems.value = Array.isArray(data?.items) ? data.items.slice(0, 5) : []
  } catch {
    activityItems.value = []
  } finally {
    activityLoading.value = false
  }
}

async function openContinueItem(item) {
  if (item.type === 'tracker' && item.projectId) {
    await openProjectTracker(item.projectId, item.id)
    return
  }
  await openProject(item.projectId || item.id)
}

function canOpenActivity(item) {
  const target = item?.target || {}
  return Boolean(target.type === 'project'
    ? (target.project_id || item.project_id)
    : ((target.project_id || item.project_id) && (
      target.tracker_id || target.tracker_ref || item.tracker_id || item.tracker_name
    )))
}

async function openActivity(item) {
  if (!canOpenActivity(item)) return
  await openGlobalActivityTarget(item)
}

function activitySummary(item) {
  return item?.summary || 'Project activity'
}

function activityContext(item) {
  return [item?.project_title || 'Project', item?.tracker_name].filter(Boolean).join(' · ')
}

onMounted(() => {
  void Promise.all([loadRecentItems(), loadActivity()])
})
</script>

<style scoped>
.home-view {
  flex: 1;
  min-width: 0;
  padding-bottom: var(--v-space-8);
}

.home-header,
.home-content {
  width: 100%;
  max-width: 1420px;
  margin-inline: auto;
}

.home-header {
  align-items: flex-end;
  padding: var(--v-space-8) var(--v-space-6) var(--v-space-5);
}

.home-heading {
  min-width: 0;
}

.home-date {
  margin-bottom: var(--v-space-1);
}

.home-intro {
  margin: var(--v-space-1) 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.5;
}

.home-content {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-6);
  padding: 0 var(--v-space-6);
}

.home-stage,
.home-section {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: var(--v-space-3);
}

.home-stage-heading h2,
.home-section-header h2 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  line-height: 1.2;
}

.home-stage-surface {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(250px, 0.82fr);
  min-height: 290px;
  overflow: hidden;
  border-radius: var(--v-radius-lg);
}

.home-feature {
  display: grid;
  grid-template-columns: minmax(280px, 0.95fr) minmax(300px, 1.05fr);
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.home-feature-media {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 290px;
  overflow: hidden;
  background: var(--v-surface-panel);
}

.home-feature-media::after {
  content: "";
  position: absolute;
  inset: auto 0 0;
  height: 2px;
  background: var(--v-accent);
  opacity: 0.72;
}

.home-feature-fallback {
  margin: auto;
  color: var(--v-text-muted);
  font-size: clamp(38px, 5vw, 68px);
  font-weight: 650;
  letter-spacing: -0.04em;
}

.home-feature-media img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--v-duration-slow) var(--v-ease-emphasized);
}

.home-feature:hover .home-feature-media img {
  transform: scale(1.02);
}

.home-feature:focus-visible,
.home-recent-row:focus-visible,
.home-pulse-metrics > button:focus-visible,
.home-project-row:focus-visible,
.home-activity-row:focus-visible,
.home-list-footer:focus-visible {
  position: relative;
  z-index: 1;
  outline: 2px solid var(--v-border-focus);
  outline-offset: -3px;
}

.home-feature-media-tag {
  position: absolute;
  top: var(--v-space-3);
  left: var(--v-space-3);
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-full);
  background: var(--v-overlay-pill-bg);
  color: var(--v-overlay-pill-text);
  font-size: var(--v-text-xs);
  font-weight: 650;
}

.home-feature-media-tag .icon {
  width: 13px;
  height: 13px;
  color: var(--v-accent);
}

.home-feature-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  padding: var(--v-space-8);
}

/* The one eyebrow that carries accent colour: it marks the featured project. */
.home-feature-kicker {
  margin-bottom: var(--v-space-2);
  color: var(--v-accent);
}

.home-feature-title {
  max-width: 18ch;
  color: var(--v-text);
  font-size: clamp(24px, 3vw, 36px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.08;
}

.home-feature-context {
  margin-top: var(--v-space-2);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.home-feature-description {
  display: -webkit-box;
  max-width: 52ch;
  margin-top: var(--v-space-5);
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.home-feature-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-3);
  margin-top: auto;
  padding-top: var(--v-space-5);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-feature-meta .v-status {
  border-radius: var(--v-radius-full);
}

.home-feature-action {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  margin-top: var(--v-space-4);
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 700;
}

.home-feature-action .icon,
.home-chevron {
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
}

.home-recents {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-left: 1px solid var(--v-divider-subtle);
  background: color-mix(in srgb, var(--v-surface-inset) 42%, transparent);
}

.home-recents-head {
  justify-content: space-between;
  min-height: 48px;
  padding: 0 var(--v-space-4);
  border-bottom: 1px solid var(--v-divider-subtle);
}

.home-recent-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 74px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-recent-row:hover {
  background: var(--v-surface-inline);
}

.home-recent-icon,
.home-activity-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-md);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.home-recent-icon .icon,
.home-activity-icon .icon {
  width: 15px;
  height: 15px;
}

.home-recent-copy,
.home-project-copy,
.home-activity-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
}

.home-recent-copy strong,
.home-project-copy strong,
.home-activity-copy strong {
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-recent-copy span,
.home-project-copy span,
.home-activity-copy span {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-recents-empty {
  margin: auto;
  padding: var(--v-space-5);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.5;
  text-align: center;
}

.home-stage-loading,
.home-list-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-stage-loading {
  min-height: 290px;
}

.home-stage-loading .icon,
.home-list-loading .icon {
  width: 16px;
  height: 16px;
}

.home-stage-empty {
  min-height: 290px;
}

.home-pulse {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-5);
  padding: var(--v-space-3) 0;
  border-block: 1px solid var(--v-divider-subtle);
}

.home-pulse-label,
.home-pulse-metrics,
.home-pulse-metrics > span,
.home-pulse-metrics > button {
  display: inline-flex;
  align-items: center;
}

.home-pulse-label {
  gap: var(--v-space-2);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.home-live-dot {
  width: 7px;
  height: 7px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
  box-shadow: 0 0 0 3px var(--v-accent-subtle);
}

.home-pulse-metrics {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-pulse-metrics > span,
.home-pulse-metrics > button {
  min-height: 28px;
  gap: 5px;
  padding-inline: var(--v-space-4);
  border: 0;
  border-left: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
}

.home-pulse-metrics > button {
  min-height: 36px;
  cursor: pointer;
}

.home-pulse-metrics > button:hover {
  color: var(--v-text);
}

.home-pulse-metrics strong {
  color: var(--v-text);
  font-variant-numeric: tabular-nums;
}

.home-pulse-metrics .icon {
  width: 12px;
  height: 12px;
}

.home-lower {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
  align-items: start;
  gap: var(--v-space-6);
}

.home-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-height: 38px;
}

.home-project-list,
.home-activity-list {
  overflow: hidden;
  border-radius: var(--v-radius-lg);
}

.home-project-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
  min-height: 68px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-project-row:last-child {
  border-bottom: 0;
}

.home-project-row:hover,
.home-activity-row:hover,
.home-list-footer:hover {
  background: var(--v-surface-inline-strong);
}

.home-project-thumbnail {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 62px;
  height: 40px;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inset);
  color: var(--v-text-muted);
}

.home-project-thumbnail .icon {
  width: 16px;
  height: 16px;
}

.home-project-thumbnail img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.home-project-row .v-status {
  border-radius: var(--v-radius-full);
}

.home-activity-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
  min-height: 62px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-activity-row time {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  white-space: nowrap;
}

.home-activity-row.is-disabled {
  cursor: default;
  opacity: 0.64;
}

.home-activity-row.is-disabled:hover {
  background: transparent;
}

.home-list-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 44px;
  padding: 0 var(--v-space-4);
  border: 0;
  background: var(--v-surface-inset);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
  cursor: pointer;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.home-list-footer .icon {
  width: 12px;
  height: 12px;
}

.home-empty-state {
  min-height: 210px;
}

@media (max-width: 1120px) {
  .home-stage-surface {
    grid-template-columns: 1fr;
  }

  .home-recents {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    border-top: 1px solid var(--v-divider-subtle);
    border-left: 0;
  }

  .home-recents-head {
    display: none;
  }

  .home-recent-row {
    border-right: 1px solid var(--v-divider-subtle);
    border-bottom: 0;
  }

  .home-recent-row:last-of-type {
    border-right: 0;
  }
}

@media (max-width: 900px) {
  .home-lower {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .home-header {
    align-items: flex-start;
    padding: var(--v-space-5) var(--v-space-4) var(--v-space-4);
  }

  .home-header .v-page-actions {
    width: auto;
  }

  .home-content {
    gap: var(--v-space-5);
    padding: 0 var(--v-space-4);
  }

  .home-feature {
    grid-template-columns: 1fr;
  }

  .home-feature-media {
    min-height: auto;
    aspect-ratio: 16 / 8;
  }

  .home-feature-copy {
    min-height: 250px;
    padding: var(--v-space-5);
  }

  .home-feature-title {
    font-size: clamp(24px, 8vw, 32px);
  }

  .home-recents {
    grid-template-columns: 1fr;
  }

  .home-recent-row {
    min-height: 66px;
    border-right: 0;
    border-bottom: 1px solid var(--v-divider-subtle);
  }

  .home-pulse {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-2);
  }

  .home-pulse-metrics {
    justify-content: flex-start;
    width: 100%;
  }

  .home-pulse-metrics > span,
  .home-pulse-metrics > button {
    padding-inline: 0 var(--v-space-4);
    border-left: 0;
  }

  .home-project-row .v-status {
    display: none;
  }
}

@media (max-width: 430px) {
  .home-header {
    flex-direction: column;
  }

  .home-header .v-page-actions,
  .home-header .v-btn {
    width: 100%;
  }

  .home-pulse-metrics {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--v-space-1);
  }

  .home-pulse-metrics > span,
  .home-pulse-metrics > button {
    justify-content: flex-start;
    min-height: 24px;
    padding: 0;
  }

  .home-pulse-metrics > button {
    min-height: 36px;
  }

  .home-project-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .home-project-thumbnail {
    width: 48px;
    height: 34px;
  }

  .home-activity-row {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .home-activity-row time {
    grid-column: 2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-feature-media img {
    transition: none;
  }
}
</style>
