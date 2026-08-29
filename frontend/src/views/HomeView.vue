<template>
  <div class="home-view">
    <header class="v-page-header home-header">
      <div class="home-heading">
        <p class="v-eyebrow home-date">{{ todayLabel }}</p>
        <h1 class="v-page-title">Good {{ daypart }}, {{ firstName }}.</h1>
        <p class="home-intro">{{ homeIntro }}</p>
      </div>

      <div v-if="isAdmin" class="v-page-actions">
        <button type="button" class="v-btn v-btn-primary" @click="openCreateProjectModal">
          <svg class="icon" aria-hidden="true"><use href="#icon-plus" /></svg>
          New project
        </button>
      </div>
    </header>

    <main class="home-content">
      <div class="home-primary">
        <section class="home-section home-attention" aria-labelledby="home-attention-title">
          <header class="home-section-header home-attention-header">
            <div class="home-title-cluster">
              <span class="home-attention-icon" aria-hidden="true">
                <svg class="icon"><use href="#icon-project" /></svg>
              </span>
              <div>
                <h2 id="home-attention-title">Your work</h2>
                <p>Assigned shots that need changes or are already in progress.</p>
              </div>
            </div>
            <div v-if="assignedWorkTotal" class="home-work-summary" aria-label="Assigned work summary">
              <span v-if="requestedEditCount" class="v-status v-status-hold">
                {{ requestedEditCount }} edit{{ requestedEditCount === 1 ? '' : 's' }} requested
              </span>
              <span v-if="inProgressCount" class="v-status v-status-active">
                {{ inProgressCount }} in progress
              </span>
            </div>
          </header>

          <div v-if="assignedWorkLoading" class="home-edit-skeleton" aria-label="Loading assigned work">
            <div class="v-surface-panel home-edit-skeleton-group">
              <span class="home-skeleton-thumb"></span>
              <span class="home-skeleton-bar is-title"></span>
              <span class="home-skeleton-bar is-meta"></span>
              <span class="home-skeleton-row"></span>
              <span class="home-skeleton-row is-short"></span>
            </div>
          </div>

          <div v-else-if="assignedWorkError" class="v-surface-panel home-attention-state is-error" role="status">
            <span class="home-state-icon" aria-hidden="true">
              <svg class="icon"><use href="#icon-alert" /></svg>
            </span>
            <div>
              <strong>Assigned work could not be loaded</strong>
              <span>Your projects and activity are still available.</span>
            </div>
            <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="loadAssignedWork">
              Try again
            </button>
          </div>

          <div v-else-if="assignedWorkProjects.length" class="home-edit-groups">
            <article
              v-for="project in assignedWorkProjects"
              :key="project.id"
              class="v-surface-panel home-edit-project"
            >
              <button
                type="button"
                class="home-edit-project-header"
                :aria-label="`Open project ${project.title}`"
                @click="openProject(project.id)"
              >
                <span class="home-edit-project-thumb" aria-hidden="true">
                  <svg class="icon"><use href="#icon-project" /></svg>
                  <img
                    :src="getProjectThumbnailUrl(project.id, project.thumbnail_path)"
                    alt=""
                    loading="lazy"
                    decoding="async"
                    @load="showLoadedImage"
                    @error="hideBrokenImage"
                  >
                </span>
                <span class="home-edit-project-copy">
                  <strong>{{ project.title }}</strong>
                  <span>
                    {{ project.shots.length }} assigned shot{{ project.shots.length === 1 ? '' : 's' }}
                    <template v-if="project.due_date"> due {{ formatProjectDate(project.due_date) }}</template>
                  </span>
                </span>
                <span class="home-open-label">Open project</span>
                <svg class="icon home-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
              </button>

              <div class="home-edit-shot-list">
                <button
                  v-for="shot in project.shots"
                  :key="shot.id"
                  type="button"
                  class="home-edit-shot"
                  :aria-label="`Open assigned shot ${shot.shot_id}`"
                  @click="openAssignedEdit(project, shot)"
                >
                  <span class="home-edit-shot-copy">
                    <strong>{{ shot.shot_id }}</strong>
                    <span>{{ shot.description || 'No shot description' }}</span>
                  </span>
                  <span class="v-status home-work-status" :class="statusClass(shot.status)">
                    {{ formatStatus(shot.status || 'in_progress') }}
                  </span>
                  <span class="home-edit-shot-meta">
                    <span>{{ shot.tracker_name }}</span>
                    <span v-if="shot.latest_version_label">{{ formatVersionLabel(shot.latest_version_label) }}</span>
                    <time v-if="shot.updated_at" :datetime="editDateTime(shot.updated_at)">
                      Updated {{ formatActivityRelativeTimestamp(shot.updated_at) }}
                    </time>
                  </span>
                  <svg class="icon home-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
                </button>
              </div>
            </article>
          </div>

          <div v-else class="v-surface-panel home-attention-state is-clear">
            <span class="home-state-icon" aria-hidden="true">
              <svg class="icon"><use href="#icon-check" /></svg>
            </span>
            <div>
              <strong>No assigned work</strong>
              <span>Shots will appear here when they need changes or move into progress.</span>
            </div>
          </div>
        </section>

        <aside class="home-support" aria-label="Workspace shortcuts and overview">
          <section class="home-section" aria-labelledby="home-recent-title">
            <header class="home-section-header">
              <div>
                <h2 id="home-recent-title">Continue working</h2>
                <p>Pick up where you left off.</p>
              </div>
            </header>

            <div v-if="recentLoading" class="v-surface-panel home-recent-skeleton" aria-label="Loading recent work">
              <span v-for="index in 3" :key="index" class="home-skeleton-row"></span>
            </div>

            <div v-else-if="continueItems.length" class="v-surface-panel home-recent-list">
              <button
                v-for="item in continueItems"
                :key="`${item.type}-${item.projectId || ''}-${item.id}`"
                type="button"
                class="home-recent-row"
                :aria-label="`Open ${item.title}`"
                @click="openContinueItem(item)"
              >
                <span
                  class="home-recent-icon"
                  :style="identityColorStyle(item.projectId || item.id, '--home-signal-color')"
                  aria-hidden="true"
                >
                  <svg class="icon"><use :href="item.type === 'tracker' ? '#icon-project' : '#icon-folder'" /></svg>
                </span>
                <span class="home-recent-copy">
                  <strong>{{ item.title }}</strong>
                  <span>{{ continueSubtitle(item) }}</span>
                </span>
                <svg class="icon home-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
              </button>
            </div>

            <div v-else class="v-surface-panel home-compact-empty">
              <svg class="icon" aria-hidden="true"><use href="#icon-play" /></svg>
              <span>Open a project or tracker and Vue will keep your place here.</span>
              <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="goToProjects">
                Browse projects
              </button>
            </div>
          </section>

          <section class="home-section home-overview" aria-labelledby="home-overview-title">
            <header class="home-section-header">
              <div>
                <h2 id="home-overview-title">At a glance</h2>
                <p>A quick pulse across your workspace.</p>
              </div>
            </header>
            <div class="v-surface-panel home-snapshot">
              <div class="home-snapshot-item is-active">
                <strong>{{ activeProjectCount }}</strong>
                <span>Active project{{ activeProjectCount === 1 ? '' : 's' }}</span>
              </div>
              <div class="home-snapshot-item is-due" :class="{ 'has-value': dueSoonCount > 0 }">
                <strong>{{ dueSoonCount }}</strong>
                <span>Due this week</span>
              </div>
              <button type="button" class="home-snapshot-item is-unread" :class="{ 'has-value': globalActivityUnreadCount > 0 }" @click="toggleGlobalActivityTray">
                <strong>{{ globalActivityUnreadCount }}</strong>
                <span>Unread update{{ globalActivityUnreadCount === 1 ? '' : 's' }}</span>
                <svg class="icon" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
              </button>
            </div>
          </section>
        </aside>
      </div>

      <div class="home-lower">
        <section class="home-section" aria-labelledby="home-projects-title">
          <header class="home-section-header">
            <div>
              <h2 id="home-projects-title">Active projects</h2>
              <p>The work currently moving through production.</p>
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
              <span
                class="home-project-thumbnail"
                :style="identityColorStyle(project.id, '--home-signal-color')"
                aria-hidden="true"
              >
                <svg class="icon"><use href="#icon-project" /></svg>
                <img
                  :src="getProjectThumbnailUrl(project.id, project.thumbnail_path)"
                  alt=""
                  loading="lazy"
                  decoding="async"
                  @load="showLoadedImage"
                  @error="hideBrokenImage"
                >
              </span>
              <span class="home-project-copy">
                <strong>{{ project.title }}</strong>
                <span class="home-project-meta">
                  <span>{{ project.shot_count }} shot{{ project.shot_count === 1 ? '' : 's' }}</span>
                  <span v-if="project.due_date" :class="`is-${projectDueState(project)}`">Due {{ formatProjectDate(project.due_date) }}</span>
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
              <h2 id="home-activity-title">Latest activity</h2>
              <p>Recent changes across the work you can access.</p>
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

          <div v-if="activityLoading && !activityItems.length" class="v-surface-panel home-activity-skeleton" aria-label="Loading activity">
            <span v-for="index in 4" :key="index" class="home-skeleton-row"></span>
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
              <span
                class="home-activity-icon"
                :style="{ '--home-signal-color': getTrackerEventColor(item.event_type) }"
                aria-hidden="true"
              >
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
import { getTrackerEventColor, getTrackerEventIcon, getTrackerStatusLabel as formatStatus } from '../lib/trackerCatalogs'
import { useActivityStore } from '../ownership/activity'
import { useAppChromeStore } from '../ownership/appChrome'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useTrackerStore } from '../ownership/tracker'
import { useViewerStore } from '../ownership/viewer'
import { formatActivityRelativeTimestamp, formatLocaleDate } from '../utils/formatters'
import { identityColorStyle } from '../utils/semanticColors'

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

const assignedWorkProjects = ref([])
const assignedWorkLoading = ref(true)
const assignedWorkError = ref(false)
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

const assignedWorkTotal = computed(() => assignedWorkProjects.value.reduce(
  (total, project) => total + (project.shots?.length || 0),
  0,
))
const assignedWorkProjectCount = computed(() => assignedWorkProjects.value.length)
const requestedEditCount = computed(() => assignedWorkProjects.value.reduce(
  (total, project) => total + (project.shots?.filter(shot => shot.status === 'edits_requested').length || 0),
  0,
))
const inProgressCount = computed(() => assignedWorkProjects.value.reduce(
  (total, project) => total + (project.shots?.filter(shot => shot.status === 'in_progress').length || 0),
  0,
))
const homeIntro = computed(() => {
  if (assignedWorkLoading.value) {
    return 'Your assigned work, active projects, and latest updates in one clear view.'
  }
  if (assignedWorkTotal.value) {
    const shotLabel = assignedWorkTotal.value === 1 ? 'shot' : 'shots'
    const projectLabel = assignedWorkProjectCount.value === 1 ? 'project' : 'projects'
    return `${assignedWorkTotal.value} assigned ${shotLabel} across ${assignedWorkProjectCount.value} ${projectLabel}.`
  }
  return 'Your active projects, recent work, and latest updates are ready below.'
})

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

const allActiveProjects = computed(() => (
  projects.value
    .filter(project => project.status === 'in_progress')
    .sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0))
))
const activeProjects = computed(() => allActiveProjects.value.slice(0, 6))
const activeProjectCount = computed(() => allActiveProjects.value.length)

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

function projectDueState(project) {
  if (!project?.due_date || project.status === 'done') return 'upcoming'
  const due = new Date(`${project.due_date}T23:59:59`)
  if (Number.isNaN(due.getTime())) return 'upcoming'
  const current = new Date()
  if (due < current) return 'overdue'
  const cutoff = new Date(current)
  cutoff.setDate(cutoff.getDate() + 7)
  return due <= cutoff ? 'due-soon' : 'upcoming'
}

const emptyProjectsCopy = computed(() => (
  isAdmin.value
    ? 'Start a project when the next job is ready to move.'
    : 'Projects in progress and shared with you will appear here.'
))

function formatProjectDate(value) {
  return formatLocaleDate(value, { options: { month: 'short', day: 'numeric' } }) || value
}

function formatVersionLabel(value) {
  const label = String(value || '').trim()
  if (!label) return ''
  return /^v/i.test(label) ? label : `V${label}`
}

function continueSubtitle(item) {
  const subtitle = String(item?.subtitle || '').trim()
  if (!subtitle || subtitle.toLowerCase() === item.type) {
    const project = projects.value.find(entry => String(entry.id) === String(item?.projectId || item?.id))
    return project?.title || 'Recently viewed'
  }
  return subtitle
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

function showLoadedImage(event) {
  event.target.style.removeProperty('display')
}

function editDateTime(value) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp)) return ''
  return new Date(timestamp * 1000).toISOString()
}

function activityDateTime(item) {
  return editDateTime(item?.created_at)
}

async function loadAssignedWork() {
  assignedWorkLoading.value = true
  assignedWorkError.value = false
  try {
    const { data } = await api.get('/api/home/assigned-edits')
    assignedWorkProjects.value = Array.isArray(data?.projects) ? data.projects : []
  } catch {
    assignedWorkProjects.value = []
    assignedWorkError.value = true
  } finally {
    assignedWorkLoading.value = false
  }
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

async function openAssignedEdit(project, shot) {
  await openGlobalActivityTarget({
    project_id: project.id,
    tracker_id: shot.tracker_id,
    payload: { shot_code: shot.shot_id },
    target: {
      type: 'shot',
      project_id: project.id,
      tracker_id: shot.tracker_id,
      shot_id: shot.id,
      shot_code: shot.shot_id,
      shot_version_id: shot.latest_version_id || undefined,
      mode: 'latest',
    },
  })
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
  void Promise.all([loadAssignedWork(), loadRecentItems(), loadActivity()])
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
  max-width: 1380px;
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

.home-primary {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(320px, 0.85fr);
  align-items: start;
  gap: var(--v-space-6);
}

.home-support {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: var(--v-space-6);
}

.home-section {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: var(--v-space-3);
}

.home-section-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--v-space-4);
  min-height: 42px;
}

.home-section-header h2 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  line-height: 1.2;
}

.home-section-header p {
  margin: 4px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.home-attention-header {
  align-items: center;
}

.home-title-cluster {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v-space-3);
}

.home-attention-icon,
.home-state-icon,
.home-recent-icon,
.home-activity-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border-radius: var(--v-radius-md);
}

.home-attention-icon {
  width: 38px;
  height: 38px;
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.home-attention-icon .icon {
  width: 17px;
  height: 17px;
}

.home-work-summary {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--v-space-2);
}

.home-edit-groups,
.home-edit-skeleton {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: var(--v-space-4);
}

.home-edit-project,
.home-edit-skeleton-group,
.home-project-list,
.home-activity-list,
.home-recent-list,
.home-recent-skeleton,
.home-activity-skeleton {
  overflow: hidden;
  border-radius: var(--v-radius-lg);
}

.home-edit-project-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
  min-height: 66px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: color-mix(in srgb, var(--v-surface-inline) 28%, transparent);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-edit-project-header:hover {
  background: var(--v-surface-tint-hover);
}

.home-edit-project-thumb,
.home-project-thumbnail {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inset);
  color: var(--v-text-muted);
}

.home-edit-project-thumb {
  width: 50px;
  height: 34px;
}

.home-edit-project-thumb .icon,
.home-project-thumbnail .icon {
  width: 16px;
  height: 16px;
}

.home-edit-project-thumb img,
.home-project-thumbnail img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.home-edit-project-copy,
.home-edit-shot-copy,
.home-recent-copy,
.home-project-copy,
.home-activity-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
}

.home-edit-project-copy strong,
.home-edit-shot-copy strong,
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

.home-edit-project-copy span,
.home-edit-shot-copy span,
.home-recent-copy span,
.home-project-copy > span,
.home-activity-copy span {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-open-label {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.home-chevron {
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
}

.home-edit-shot-list {
  display: flex;
  flex-direction: column;
}

.home-edit-shot {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) auto auto auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
  min-height: 70px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-edit-shot:last-child {
  border-bottom: 0;
}

.home-edit-shot:hover {
  background: var(--v-surface-inline-strong);
}

.home-work-status {
  justify-self: end;
  border-radius: var(--v-radius-full);
}

.home-edit-shot-meta {
  display: grid;
  grid-auto-flow: column;
  align-items: center;
  justify-content: end;
  gap: var(--v-space-3);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  white-space: nowrap;
}

.home-edit-shot-meta > * + * {
  padding-left: var(--v-space-3);
  border-left: 1px solid var(--v-divider-subtle);
}

.home-attention-state {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 86px;
  padding: var(--v-space-4);
  border-radius: var(--v-radius-lg);
}

.home-attention-state > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.home-attention-state strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
}

.home-attention-state span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-state-icon {
  width: 36px;
  height: 36px;
  background: var(--v-accent-subtle);
  color: var(--v-accent);
}

.home-attention-state.is-error .home-state-icon {
  background: var(--v-warning-bg);
  color: var(--v-warning);
}

.home-state-icon .icon {
  width: 16px;
  height: 16px;
}

.home-edit-skeleton-group {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px var(--v-space-3);
  min-height: 204px;
  padding: var(--v-space-4);
}

.home-skeleton-thumb,
.home-skeleton-bar,
.home-skeleton-row {
  display: block;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  opacity: 0.74;
}

.home-skeleton-thumb {
  grid-row: span 2;
  width: 50px;
  height: 34px;
}

.home-skeleton-bar {
  height: 9px;
  align-self: center;
}

.home-skeleton-bar.is-title {
  width: min(190px, 70%);
}

.home-skeleton-bar.is-meta {
  width: min(130px, 52%);
}

.home-skeleton-row {
  grid-column: 1 / -1;
  height: 54px;
  margin-top: var(--v-space-3);
}

.home-skeleton-row.is-short {
  margin-top: 0;
}

.home-snapshot {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
  border-radius: var(--v-radius-lg);
}

.home-snapshot-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: baseline;
  gap: var(--v-space-2);
  min-height: 58px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
}

button.home-snapshot-item {
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

button.home-snapshot-item:hover {
  background: var(--v-surface-tint);
}

.home-snapshot-item:last-child {
  border-bottom: 0;
}

.home-snapshot-item strong {
  color: var(--v-text);
  font-size: var(--v-text-xl);
  font-variant-numeric: tabular-nums;
}

.home-snapshot-item.is-active strong {
  color: var(--v-status-active-text);
}

.home-snapshot-item.is-due.has-value strong {
  color: var(--v-status-review-text);
}

.home-snapshot-item.is-unread.has-value strong,
.home-snapshot-item.is-unread.has-value .icon {
  color: var(--v-info);
}

.home-snapshot-item span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-snapshot-item .icon {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
}

.home-recent-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

.home-recent-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 70px;
  padding: var(--v-space-3) var(--v-space-4);
  border: 0;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.home-recent-row:last-child {
  border-bottom: 0;
}

.home-recent-row:hover,
.home-project-row:hover,
.home-activity-row:hover,
.home-list-footer:hover {
  background: var(--v-surface-inline-strong);
}

.home-recent-icon,
.home-activity-icon {
  --home-signal-color: var(--v-accent);
  width: 34px;
  height: 34px;
  background: color-mix(in srgb, var(--home-signal-color) 10%, transparent);
  color: var(--home-signal-color);
}

.home-recent-icon .icon,
.home-activity-icon .icon {
  width: 15px;
  height: 15px;
}

.home-recent-skeleton,
.home-activity-skeleton {
  display: grid;
  gap: 1px;
  padding: var(--v-space-3);
}

.home-recent-skeleton {
  grid-template-columns: minmax(0, 1fr);
}

.home-recent-skeleton .home-skeleton-row,
.home-activity-skeleton .home-skeleton-row {
  height: 46px;
  margin: 0;
}

.home-compact-empty {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 70px;
  padding: var(--v-space-3) var(--v-space-4);
  border-radius: var(--v-radius-lg);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.home-compact-empty > .icon {
  width: 16px;
  height: 16px;
  color: var(--v-accent);
}

.home-compact-empty > span {
  min-width: 0;
  flex: 1;
}

.home-lower {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.85fr);
  align-items: start;
  gap: var(--v-space-6);
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

.home-project-thumbnail {
  --home-signal-color: var(--v-accent);
  width: 62px;
  height: 40px;
  background: color-mix(in srgb, var(--home-signal-color) 9%, var(--v-surface-inset));
  color: color-mix(in srgb, var(--home-signal-color) 72%, var(--v-text-muted));
}

.home-project-meta {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
}

.home-project-meta > span + span {
  padding-left: var(--v-space-3);
  border-left: 1px solid var(--v-divider-subtle);
}

.home-project-meta .is-due-soon {
  color: var(--v-status-review-text);
}

.home-project-meta .is-overdue {
  color: var(--v-danger-text);
  font-weight: 600;
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

.home-edit-project-header:focus-visible,
.home-edit-shot:focus-visible,
.home-snapshot-item:focus-visible,
.home-recent-row:focus-visible,
.home-project-row:focus-visible,
.home-activity-row:focus-visible,
.home-list-footer:focus-visible {
  position: relative;
  z-index: 2;
  outline: 2px solid var(--v-border-focus);
  outline-offset: -3px;
}

@media (max-width: 1120px) {
  .home-primary {
    grid-template-columns: 1fr;
  }

  .home-support {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
    align-items: start;
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

  .home-support {
    grid-template-columns: 1fr;
    gap: var(--v-space-5);
  }

  .home-attention-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .home-work-summary {
    justify-content: flex-start;
    padding-left: 50px;
  }

  .home-edit-shot {
    grid-template-columns: minmax(0, 1fr) auto auto;
  }

  .home-edit-shot-meta {
    grid-column: 1 / -1;
    grid-row: 2;
    justify-content: start;
  }

  .home-edit-shot > .home-chevron {
    grid-column: 3;
    grid-row: 1;
  }

  .home-project-row .v-status {
    display: none;
  }
}

@media (max-width: 548px) {
  .home-section-header {
    align-items: flex-start;
  }

  .home-snapshot {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .home-snapshot-item {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: auto auto;
    align-content: center;
    gap: 2px var(--v-space-1);
    min-height: 64px;
    padding-inline: var(--v-space-3);
    border-right: 1px solid var(--v-divider-subtle);
    border-bottom: 0;
  }

  .home-snapshot-item:last-child {
    border-right: 0;
    border-bottom: 0;
  }

  .home-snapshot-item strong,
  .home-snapshot-item span {
    grid-column: 1;
  }

  .home-snapshot-item .icon {
    grid-column: 2;
    grid-row: 1 / -1;
    align-self: center;
  }

  .home-recent-list {
    grid-template-columns: 1fr;
  }

  .home-recent-row {
    border-bottom: 1px solid var(--v-divider-subtle);
  }

  .home-recent-row:last-child {
    border-bottom: 0;
  }

  .home-edit-project-header {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .home-open-label {
    display: none;
  }

  .home-edit-shot-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px var(--v-space-2);
    white-space: normal;
  }

  .home-edit-shot-meta > * + * {
    padding-left: var(--v-space-2);
  }

  .home-compact-empty {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .home-compact-empty > span {
    flex-basis: calc(100% - 32px);
  }

  .home-compact-empty .v-btn {
    width: 100%;
  }
}

@media (max-width: 430px) {
  .home-header {
    flex-direction: column;
  }

  .home-header .v-page-actions,
  .home-header .v-btn {
    width: auto;
  }

  .home-title-cluster {
    align-items: flex-start;
  }

  .home-attention-icon {
    width: 36px;
    height: 36px;
  }

  .home-work-summary {
    padding-left: 48px;
  }

  .home-attention-state {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .home-attention-state .v-btn {
    grid-column: 1 / -1;
    width: 100%;
  }

  .home-edit-project-header {
    padding: var(--v-space-3);
  }

  .home-edit-project-thumb {
    width: 44px;
    height: 32px;
  }

  .home-edit-shot {
    padding-inline: var(--v-space-3);
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
</style>
