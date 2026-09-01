<template>
      <!-- Projects List -->
      <div class="projects-list">
        <!-- Page Header -->
        <header class="v-page-header v-page-header-compact project-browser-header">
          <div class="project-browser-heading">
            <h1 class="v-page-title">Projects</h1>
            <p class="project-browser-summary">
              <span>{{ projectCountLabel }}</span>
              <span class="project-browser-summary__divider" aria-hidden="true"></span>
              <span class="project-browser-summary__active">
                <span class="v-project-status-dot"></span>
                {{ activeProjectCount }} active
              </span>
            </p>
          </div>

          <div class="v-page-actions project-browser-actions">
              <!-- View Toggle -->
              <div class="v-view-toggle" role="group" aria-label="Project view">
                <button
                  class="v-view-toggle-btn"
                  :class="{ active: !projectsListView }"
                  @click="setProjectsListView(false)"
                  title="Grid view"
                  aria-label="Grid view"
                  :aria-pressed="!projectsListView"
                >
                  <svg class="icon"><use href="#icon-grid"/></svg>
                  <span class="project-view-label">Grid</span>
                </button>
                <button
                  class="v-view-toggle-btn"
                  :class="{ active: projectsListView }"
                  @click="setProjectsListView(true)"
                  title="List view"
                  aria-label="List view"
                  :aria-pressed="projectsListView"
                >
                  <svg class="icon"><use href="#icon-list"/></svg>
                  <span class="project-view-label">List</span>
                </button>
              </div>

              <!-- Filter/Sort -->
              <VMenu
                :open="showSortMenu"
                align="start"
                class="projects-sort-menu"
                panel-class="projects-sort-dropdown"
                @update:open="open => !open && closeSortMenu()"
              >
                <template #trigger="{ triggerProps }">
                  <button
                    class="v-filter project-sort-trigger"
                    :class="{ 'has-view-options': activeViewOptionCount > 0 }"
                    aria-label="Sort and filter projects"
                    v-bind="triggerProps"
                    @click="toggleSortMenu()"
                  >
                    <svg class="icon project-sort-icon"><use href="#icon-sort"/></svg>
                    <span class="project-sort-label">{{ projectSortLabel }}</span>
                    <span v-if="activeViewOptionCount" class="project-view-option-count">{{ activeViewOptionCount }}</span>
                    <svg class="icon project-sort-chevron"><use href="#icon-chevron-down"/></svg>
                  </button>
                </template>
                <div class="project-menu-label">Sort projects</div>
                <button
                  v-for="option in projectSortOptions"
                  :key="option.value"
                  class="v-dropdown-item project-sort-option"
                  :class="{ 'is-selected': projectSort === option.value }"
                  @click="setProjectSort(option.value)"
                >
                  <span>{{ option.label }}</span>
                  <svg v-if="projectSort === option.value" class="icon project-sort-check"><use href="#icon-check"/></svg>
                </button>
                <div class="v-dropdown-divider"></div>
                <div class="project-menu-label">Organize view</div>
                <button class="v-dropdown-item project-view-option" :aria-pressed="groupByStatus" @click="toggleGroupByStatus()">
                  <span class="project-menu-check" :class="{ 'is-checked': groupByStatus }">
                    <svg v-if="groupByStatus" class="icon"><use href="#icon-check"/></svg>
                  </span>
                  <span>Group by status</span>
                </button>
                <button class="v-dropdown-item project-view-option" :aria-pressed="hideDoneProjects" @click="toggleHideDoneProjects()">
                  <span class="project-menu-check" :class="{ 'is-checked': hideDoneProjects }">
                    <svg v-if="hideDoneProjects" class="icon"><use href="#icon-check"/></svg>
                  </span>
                  <span>Hide completed</span>
                </button>
              </VMenu>

              <button v-if="canCreateProjects" class="v-btn v-btn-primary" @click="openCreateProjectModal()">
                <svg class="icon"><use href="#icon-plus"/></svg>
                <span>New project</span>
              </button>
          </div>
        </header>

        <div v-if="projects.length === 0" class="v-empty-state">
          <svg class="icon v-empty-state-icon"><use href="#icon-project"/></svg>
          <p class="v-empty-state-title">No projects yet</p>
          <p class="v-empty-state-hint">Create the first project to start building in Horizons.</p>
        </div>

        <div v-else-if="sortedProjects.length === 0" class="v-empty-state">
          <svg class="icon v-empty-state-icon"><use href="#icon-search"/></svg>
          <p class="v-empty-state-title">No projects match this view</p>
          <p class="v-empty-state-hint">Completed projects are currently hidden.</p>
          <button v-if="hideDoneProjects" class="v-btn v-btn-secondary v-btn-sm" @click="toggleHideDoneProjects()">
            Show completed projects
          </button>
        </div>

        <!-- Grid View -->
        <div v-else-if="!projectsListView" class="project-groups">
          <section
            v-for="section in projectSections"
            :key="section.key"
            class="project-group"
          >
            <header
              v-if="section.grouped"
              class="v-section-label v-section-label--ruled project-group-header"
              :class="`is-${projectStatusVariant(section.status)}`"
            >
              <span class="v-dot" :class="`v-dot-${section.status.replace('_', '-')}`"></span>
              <h2 class="project-group-label">{{ section.label }}</h2>
              <span class="v-section-count project-group-count">{{ section.count }}</span>
            </header>

            <div class="file-grid v-projects-grid">
              <div
                v-for="p in section.projects"
                :key="p.id"
                class="v-card v-card-interactive file-card v-project-card"
                :class="{ 'has-open-menu': projectMenuOpen === p.id, 'is-opening': openingProjectId === p.id }"
                role="link"
                tabindex="0"
                :aria-label="`Open project ${p.title}`"
                @click="openProject(p.id)"
                @keydown.enter.self="openProject(p.id)"
                @keydown.space.prevent.self="openProject(p.id)"
              >
                <div class="v-project-thumb">
                  <div class="v-project-thumb-blank" :style="identityColorStyle(p.id)">
                    <span class="v-project-thumb-initials">{{ projectInitials(p) }}</span>
                  </div>
                  <img
                    :src="getProjectThumbnailUrl(p.id, p.thumbnail_path)"
                    alt=""
                    loading="lazy"
                    decoding="async"
                    @load="showProjectThumbnail"
                    @error="$event.target.style.display='none'"
                  />

                  <span
                    v-if="p.storage_read_only"
                    class="v-project-capability-badge v-project-readonly-badge"
                    :title="readOnlyExplanation"
                    :aria-label="readOnlyExplanation"
                  >
                    <svg class="icon"><use href="#icon-lock" /></svg>
                    <span>Read-only</span>
                    <svg class="icon v-project-readonly-badge__info"><use href="#icon-info" /></svg>
                  </span>
                </div>

                <div class="v-project-body">
                  <span
                    class="v-project-status-inline v-project-card-status"
                    :class="`is-${projectStatusVariant(p.status)}`"
                  >
                    <span class="v-project-status-dot"></span>
                    {{ projectStatusLabel(p.status) }}
                  </span>
                  <div class="v-project-title">{{ p.title }}</div>

                  <div class="v-project-meta">
                    <span class="v-project-meta-item" :title="`${p.shot_count} shot${p.shot_count !== 1 ? 's' : ''}`">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/>
                        <line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/>
                        <line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/>
                        <line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/>
                        <line x1="17" y1="17" x2="22" y2="17"/>
                      </svg>
                      {{ p.shot_count }}<span class="v-project-meta-word"> shot{{ p.shot_count !== 1 ? 's' : '' }}</span>
                    </span>
                    <span class="v-project-meta-sep" aria-hidden="true">·</span>
                    <span
                      v-if="p.due_date"
                      class="v-project-meta-item"
                      :class="projectDueClass(p)"
                      :title="`Due ${formatDate(p.due_date)}`"
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/>
                        <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                      </svg>
                      {{ projectDueLabel(p) }}
                    </span>
                    <span v-else class="v-project-meta-item is-updated" :title="projectActivityTitle(p)">
                      <svg class="icon"><use href="#icon-clock" /></svg>
                      {{ formatProjectDate(p.updated_at) }}
                    </span>
                  </div>
                </div>

                <div class="file-menu v-card-overflow v-project-menu" :class="{ 'is-open': projectMenuOpen === p.id }" @click.stop>
                  <VMenu
                    v-if="canShareProjectItem(p) || canDeleteProjectItem(p) || canOpenProjectSettingsItem(p)"
                    :open="projectMenuOpen === p.id"
                    align="end"
                    class="project-menu"
                    panel-class="file-menu-dropdown project-card-menu-dropdown"
                    @update:open="open => !open && resetProjectMenu()"
                  >
                    <template #trigger="{ triggerProps }">
                      <VOverflowButton type="button" floating v-bind="triggerProps" :active="projectMenuOpen === p.id" @click.stop="toggleProjectMenu(p.id)" />
                    </template>
                    <VMenuActionList :actions="projectMenuActions(p)" />
                  </VMenu>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- Flat View - List -->
        <div v-else class="v-projects-list-view">
          <div class="v-column-header v-project-list-header">
            <span class="v-list-col-project">Project</span>
            <span class="v-list-col-status">Status</span>
            <span class="v-list-col-shots">Shots</span>
            <span class="v-list-col-due">Due</span>
            <span class="v-list-col-updated">Updated</span>
            <span class="v-list-col-actions"></span>
          </div>

          <div class="v-projects-list-body">
            <div
              v-for="p in sortedProjects"
              :key="p.id"
              class="v-project-list-item"
              :class="{ 'has-open-menu': projectMenuOpen === p.id, 'is-opening': openingProjectId === p.id }"
              role="link"
              tabindex="0"
              :aria-label="`Open project ${p.title}`"
              @click="openProject(p.id)"
              @keydown.enter.self="openProject(p.id)"
              @keydown.space.prevent.self="openProject(p.id)"
            >
              <!-- Thumbnail -->
              <div class="v-project-list-thumb">
                <div class="v-project-thumb-blank v-project-thumb-blank-sm" :style="identityColorStyle(p.id)">
                  <span class="v-project-thumb-initials">{{ projectInitials(p) }}</span>
                </div>
                <img
                  :src="getProjectThumbnailUrl(p.id, p.thumbnail_path)"
                  alt=""
                  loading="lazy"
                  decoding="async"
                  @load="showProjectThumbnail"
                  @error="$event.target.style.display='none'"
                />
              </div>

              <!-- Title + subtle subtitle -->
              <div class="v-project-list-main">
                <div class="v-project-list-title">{{ p.title }}</div>
                <div class="v-project-list-subtitle">
                  <span v-if="p.storage_read_only" class="v-project-status-inline is-readonly" :title="readOnlyExplanation">
                    <svg class="icon"><use href="#icon-lock" /></svg>
                    Read-only
                    <svg class="icon v-project-readonly-info"><use href="#icon-info" /></svg>
                  </span>
                  <span class="v-project-status-inline v-project-status-mobile" :class="`is-${projectStatusVariant(p.status)}`">
                    <span class="v-project-status-dot"></span>
                    {{ projectStatusLabel(p.status) }}
                  </span>
                  <span v-if="shouldFlagOfflineMedia(p)" class="v-project-capability-inline is-warning">
                    <svg class="icon"><use href="#icon-alert" /></svg>
                    Media offline
                  </span>
                  <span class="v-project-list-meta-mobile">
                    <span>{{ p.shot_count }} shot{{ p.shot_count !== 1 ? 's' : '' }}</span>
                    <template v-if="p.due_date">
                      <span class="v-project-meta-sep" aria-hidden="true">·</span>
                      <span :class="projectDueClass(p)">{{ projectDueSummary(p) }}</span>
                    </template>
                  </span>
                </div>
              </div>

              <!-- Shot Count -->
              <div class="v-project-list-shots">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" opacity="0.55">
                  <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/>
                  <line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/>
                  <line x1="2" y1="12" x2="22" y2="12"/>
                </svg>
                <span class="v-project-list-shots-value">{{ p.shot_count }}</span>
              </div>

              <!-- Status -->
              <div class="v-project-list-status" @click.stop>
                  <span class="v-status v-project-status-chip is-list" :class="`is-${projectStatusVariant(p.status)}`">
                  <span class="v-project-status-dot"></span>
                  <span class="v-project-status-label">{{ projectStatusLabel(p.status) }}</span>
                </span>
              </div>

              <!-- Due Date -->
              <div class="v-project-list-due">
                <template v-if="p.due_date">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" opacity="0.55">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  <span :class="projectDueClass(p)">{{ projectDueLabel(p) }}</span>
                </template>
                <span v-else class="v-project-list-due-empty">Not set</span>
              </div>

              <div class="v-project-list-updated" :title="projectActivityTitle(p)">
                {{ formatProjectDate(p.updated_at) }}
              </div>

              <!-- More Actions -->
              <div class="project-card-actions v-row-overflow" @click.stop>
                <VMenu
                  v-if="canShareProjectItem(p) || canDeleteProjectItem(p) || canOpenProjectSettingsItem(p)"
                  :open="projectMenuOpen === p.id"
                  align="end"
                  class="project-menu"
                  panel-class="project-card-menu-dropdown project-card-menu-dropdown-list"
                  @update:open="open => !open && resetProjectMenu()"
                >
                  <template #trigger="{ triggerProps }">
                    <VOverflowButton type="button" floating v-bind="triggerProps" :active="projectMenuOpen === p.id" @click.stop="toggleProjectMenu(p.id)" />
                  </template>
                  <VMenuActionList :actions="projectMenuActions(p)" />
                </VMenu>
              </div>
            </div>
          </div>
        </div>
      </div>
</template>

<script setup>
import { computed } from 'vue'
import { VMenu, VMenuActionList, VOverflowButton } from '../components/primitives'
import { getTrackerStatusLabel as formatStatus } from '../lib/trackerCatalogs'
import { useProjectSettingsStore } from '../ownership/projectSettings'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useViewerStore } from '../ownership/viewer'
import { formatDateMMDDYYYY as formatDate } from '../utils/formatters'
import { identityColorStyle } from '../utils/semanticColors'

const {
  projects,
  sortedProjects,
  hideDoneProjects,
  projectsListView,
  setProjectsListView,
  showSortMenu,
  toggleSortMenu,
  projectSort,
  projectSortLabel,
  setProjectSort,
  groupByStatus,
  toggleGroupByStatus,
  toggleHideDoneProjects,
  openCreateProjectModal,
  projectGroups,
  openProject,
  projectMenuOpen,
  resetProjectMenu,
  toggleProjectMenu,
  shareProjectFromList,
  deleteProjectConfirm,
} = useProjectWorkspaceStore()

/* VMenu owns dismissal for both menus; these only forward the close. */
function closeSortMenu() {
  showSortMenu.value = false
}

/* One list, rendered by both the grid and list cards. Dividers mark group
   boundaries; VMenuActionList drops any that end up leading or doubled. */
function projectMenuActions(project) {
  const canSettings = canOpenProjectSettingsItem(project)
  const canStorage = Boolean(project && isAdmin.value)
  return [
    { label: 'Project Settings', icon: '#icon-settings', show: canSettings, run: () => openProjectSettings(project) },
    { divider: true },
    { label: 'Share Project', icon: '#icon-share', show: canShareProjectItem(project), run: () => shareProjectFromList(project) },
    { divider: true },
    { label: 'Set Project Folder', icon: '#icon-folder', show: canStorage && project.uses_internal_storage, run: () => openProjectStorage(project, 'migrate') },
    { label: 'Relocate Project', icon: '#icon-map-pin', show: canStorage, run: () => openProjectStorage(project, 'relocate') },
    { divider: true },
    { label: 'Delete Project', icon: '#icon-trash', danger: true, show: canDeleteProjectItem(project), run: () => deleteProjectConfirm(project) },
  ]
}

const {
  openProjectSettings,
  openProjectStorage,
} = useProjectSettingsStore()

const { openingProjectId } = useProjectTrackerSelectionStore()
const { currentUser, isAdmin, canCreateProjects, canDeleteProjects } = useSessionAuthStore()
const { getProjectThumbnailUrl } = useViewerStore().media.core

function canDeleteProjectItem(project) {
  return Boolean(project && canDeleteProjects.value && (isAdmin.value || project.access_role === 'owner'))
}

function canOpenProjectSettingsItem(project) {
  return Boolean(
    project
    && (
      isAdmin.value
      || (
        currentUser.value?.app_access?.manage_project_content === true
        && ['owner', 'editor'].includes(project.access_role)
      )
    )
  )
}

function canShareProjectItem(project) {
  return Boolean(project && (isAdmin.value || project.access_role === 'owner'))
}

const readOnlyExplanation = 'Project files are on read-only storage. Change its permissions or relocate the project to make changes.'

const projectSortOptions = [
  { value: 'updated', label: 'Last updated' },
  { value: 'created', label: 'Created date' },
  { value: 'title', label: 'Project title' },
  { value: 'due_date', label: 'Due date' },
]

function normalizeProjectStatus(status) {
  return status === 'active' ? 'in_progress' : (status || 'not_started')
}

const activeProjectCount = computed(() => (
  projects.value.filter((project) => normalizeProjectStatus(project.status) === 'in_progress').length
))

const projectCountLabel = computed(() => {
  const visibleCount = sortedProjects.value.length
  const totalCount = projects.value.length
  const projectWord = totalCount === 1 ? 'project' : 'projects'

  if (hideDoneProjects.value && visibleCount !== totalCount) {
    return `${visibleCount} visible of ${totalCount} ${projectWord}`
  }

  return `${totalCount} ${projectWord}`
})

const activeViewOptionCount = computed(() => (
  Number(groupByStatus.value) + Number(hideDoneProjects.value)
))

const projectSections = computed(() => {
  if (projectsListView.value) {
    return []
  }
  if (groupByStatus.value) {
    return projectGroups.value.map((group) => ({
      key: group.status,
      label: projectStatusLabel(group.status),
      status: group.status,
      count: group.projects.length,
      projects: group.projects,
      grouped: true,
    }))
  }
  return [
    {
      key: 'all-projects',
      label: 'Projects',
      status: 'all',
      count: sortedProjects.value.length,
      projects: sortedProjects.value,
      grouped: false,
    },
  ]
})

function projectStatusVariant(status) {
  if (normalizeProjectStatus(status) === 'in_progress') return 'active'
  if (status === 'waiting_review') return 'review'
  if (status === 'edits_requested') return 'hold'
  if (status === 'not_started') return 'draft'
  return status || 'draft'
}

function projectStatusLabel(status) {
  return formatStatus(normalizeProjectStatus(status))
}

const projectDateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

const projectCompactDateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
})

function parsedProjectDate(value) {
  if (!value) return null
  if (typeof value === 'number') {
    const milliseconds = value < 1e12 ? value * 1000 : value
    const date = new Date(milliseconds)
    return Number.isNaN(date.getTime()) ? null : date
  }
  const normalizedValue = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value
  const date = new Date(normalizedValue)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatProjectDate(value) {
  const date = parsedProjectDate(value)
  return date ? projectDateFormatter.format(date) : 'Not recorded'
}

function formatCompactProjectDate(value) {
  const date = parsedProjectDate(value)
  return date ? projectCompactDateFormatter.format(date) : 'Not set'
}

function isProjectOverdue(project) {
  if (!project?.due_date || normalizeProjectStatus(project.status) === 'done') return false
  const dueDate = parsedProjectDate(project.due_date)
  if (!dueDate) return false
  dueDate.setHours(23, 59, 59, 999)
  return dueDate.getTime() < Date.now()
}

function isProjectDueSoon(project) {
  if (!project?.due_date || normalizeProjectStatus(project.status) === 'done' || isProjectOverdue(project)) return false
  const dueDate = parsedProjectDate(project.due_date)
  if (!dueDate) return false
  dueDate.setHours(23, 59, 59, 999)
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() + 7)
  cutoff.setHours(23, 59, 59, 999)
  return dueDate.getTime() <= cutoff.getTime()
}

function projectDueClass(project) {
  return {
    'is-overdue': isProjectOverdue(project),
    'is-due-soon': isProjectDueSoon(project),
  }
}

function projectDueLabel(project, includeOverdue = true) {
  const label = formatCompactProjectDate(project?.due_date)
  return includeOverdue && isProjectOverdue(project) ? `Overdue ${label}` : label
}

function projectDueSummary(project) {
  return isProjectOverdue(project) ? projectDueLabel(project) : `Due ${projectDueLabel(project, false)}`
}

function projectActivityTitle(project) {
  const activityDate = formatProjectDate(project?.updated_at)
  return activityDate === 'Not recorded' ? activityDate : `Updated ${activityDate}`
}

function shouldFlagOfflineMedia(project) {
  return Boolean(project?.has_offline_media && normalizeProjectStatus(project.status) !== 'done')
}

function projectInitials(p) {
  const title = String(p?.title || '').trim()
  if (!title) return '?'
  const parts = title.split(/\s+/).filter(Boolean).slice(0, 2)
  const letters = parts.map((part) => part.charAt(0)).join('')
  return (letters || title.charAt(0)).toUpperCase()
}

function showProjectThumbnail(event) {
  event.target.style.removeProperty('display')
  event.target.classList.add('loaded')
}
</script>

<style>
.projects-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--v-bg);
}

.projects-sort-menu {
  position: relative;
}
.project-groups {
  display: flex;
  flex-direction: column;
  gap: 34px;
  padding: 24px 24px 44px;
}

.project-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  min-width: 0;
}

.project-group-header {
  min-height: 22px;
  padding-inline: 1px;
}

.project-group-label {
  white-space: nowrap;
}

.project-group-header.is-active {
  color: color-mix(in srgb, var(--v-status-active) 76%, var(--v-text));
}


/* ─── Project Cards ───────────────────────────────────────────────────────── */

.v-project-card {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  isolation: isolate;
  overflow: hidden;
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-surface-panel) 94%, black);
  border-color: var(--v-surface-border-soft);
  box-shadow: none;
  content-visibility: auto;
  contain-intrinsic-size: 250px 210px;
  transition:
    border-color var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized);
}

.v-project-card:hover {
  border-color: var(--v-surface-border-strong);
  background: color-mix(in srgb, var(--v-surface-panel) 97%, white);
}

.v-project-card:focus-visible,
.v-project-list-item:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.v-project-card:focus-visible {
  border-color: var(--v-border-focus);
}

.v-project-card.is-opening {
  opacity: 0.88;
  pointer-events: none;
}

.v-project-thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: var(--v-radius-lg) var(--v-radius-lg) 0 0;
  overflow: hidden;
  background: var(--v-surface-panel-soft);
}

.v-project-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 1;
  opacity: 0;
  transform: scale(1.005);
  transition: opacity var(--v-duration-normal) var(--v-ease-emphasized),
              transform var(--v-duration-slow) var(--v-ease-emphasized);
}

.v-project-thumb img.loaded { opacity: 1; }

.v-project-card:hover .v-project-thumb img {
  transform: scale(1.018);
}

/* Soft inner vignette to anchor the status pill regardless of image content */
.v-project-thumb::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.025);
  z-index: 2;
}

.v-project-thumb-blank {
  --v-identity-color: var(--v-accent);
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--v-identity-color) 8%, var(--v-surface-panel-soft));
  color: color-mix(in srgb, var(--v-identity-color) 38%, var(--v-text-muted));
}

.v-project-thumb-blank::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: color-mix(in srgb, var(--v-identity-color) 35%, transparent);
  opacity: 1;
  pointer-events: none;
}

.v-project-thumb-initials {
  position: relative;
  font-family: var(--v-font);
  font-size: 28px;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: inherit;
}

/* Storage capability stays left; workflow status stays right. */
.v-project-capability-badge {
  position: absolute;
  top: 8px;
  bottom: auto;
  left: 8px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-1);
  min-height: 22px;
  height: 22px;
  padding: 0 7px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 25%, rgba(255, 255, 255, 0.12));
  border-radius: var(--v-radius-full);
  color: color-mix(in srgb, var(--v-accent) 86%, white);
  background: rgba(11, 13, 13, 0.9);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  line-height: 1.5;
}

.v-project-readonly-badge .icon,
.v-project-readonly-info { width: 11px; height: 11px; }
.v-project-readonly-badge__info,
.v-project-readonly-info { opacity: 0.72; }

/* Status chip — overlaid on the thumbnail (top-right) for grid cards */
.v-project-status-chip {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 3;
  gap: 5px;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  color: rgba(255, 255, 255, 0.9);
  background: rgba(8, 12, 15, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: none;
  white-space: nowrap;
  pointer-events: none;
}

.v-project-status-chip.is-list {
  position: static;
  background: var(--v-surface-inline);
  border: 1px solid var(--v-control-border);
  box-shadow: none;
  color: var(--v-text);
  font-weight: 650;
}

.v-project-status-inline.is-readonly {
  color: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 24%, var(--v-control-border));
}

.v-project-status-inline.is-readonly .icon {
  width: 11px;
  height: 11px;
}

.v-project-status-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--v-radius-full);
  background: var(--v-status-draft);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-draft) 22%, transparent);
}

.v-project-status-chip.is-active .v-project-status-dot,
.v-project-status-inline.is-active .v-project-status-dot { background: var(--v-status-active); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-active) 24%, transparent); }
.v-project-status-chip.is-review .v-project-status-dot,
.v-project-status-inline.is-review .v-project-status-dot { background: var(--v-status-review); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-review) 24%, transparent); }
.v-project-status-chip.is-done .v-project-status-dot,
.v-project-status-inline.is-done .v-project-status-dot { background: var(--v-status-done); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-done) 24%, transparent); }
.v-project-status-chip.is-hold .v-project-status-dot,
.v-project-status-inline.is-hold .v-project-status-dot { background: var(--v-status-hold); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-hold) 24%, transparent); }
.v-project-status-chip.is-draft .v-project-status-dot,
.v-project-status-inline.is-draft .v-project-status-dot { background: var(--v-status-draft); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-draft) 20%, transparent); }

.v-project-status-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 600;
  color: var(--v-text-secondary);
}

/* ─── Project body (title + meta) ─────────────────────────────────────────── */

.v-project-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 7px;
  min-height: 94px;
  padding: 12px 42px 13px 13px;
  min-width: 0;
}

.v-project-title {
  font-family: var(--v-font);
  font-size: var(--v-text-md);
  font-weight: 650;
  letter-spacing: 0;
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.v-project-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px 7px;
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  color: var(--v-text-secondary);
  min-width: 0;
}

.v-project-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  min-width: 0;
}

.v-project-meta-item svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  opacity: 0.48;
}

.v-project-card-status {
  align-self: flex-start;
  font-size: var(--v-text-2xs);
  font-weight: 750;
  letter-spacing: 0.08em;
  line-height: 1;
  text-transform: uppercase;
}

.v-project-meta-item.is-overdue,
.v-project-list-due .is-overdue,
.v-project-list-meta-mobile .is-overdue {
  color: var(--v-danger);
  font-weight: 600;
}

.v-project-meta-item.is-due-soon,
.v-project-list-due .is-due-soon,
.v-project-list-meta-mobile .is-due-soon {
  color: var(--v-status-review-text);
}

.v-project-meta-item.is-updated {
  color: var(--v-text-muted);
}

.v-project-meta-sep {
  opacity: 0.4;
}

/* ─── Projects Grid ───────────────────────────────────────────────────────── */

.v-projects-grid {
  isolation: isolate;
  grid-template-columns: repeat(auto-fill, minmax(272px, 1fr));
  gap: 16px;
}

/* Project card menu positioning */
.v-project-card .project-menu {
  position: relative;
}

.projects-sort-dropdown {
  top: 40px;
  right: 0;
}

.project-card-menu-dropdown {
  min-width: 210px;
}

.project-card-menu-dropdown-list {
  top: 36px;
}

.v-project-card .v-project-menu {
  position: absolute;
  right: 7px;
  bottom: 7px;
  z-index: 3;
  opacity: 0.72;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.v-project-card:hover .v-project-menu,
.v-project-card:focus-within .v-project-menu,
.v-project-card .v-project-menu.is-open {
  opacity: 1;
}

.v-project-card.has-open-menu {
  z-index: 40;
  overflow: visible;
}

/* ─── Projects List View ──────────────────────────────────────────────────── */

.v-projects-list-view {
  display: flex;
  flex-direction: column;
  margin: 24px 24px 44px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-surface-panel) 72%, transparent);
  overflow: visible;
}

.v-project-list-header {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr) 76px 126px 126px 118px 36px;
  gap: 14px;
  align-items: center;
  min-height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid var(--v-surface-border-soft);
  background: var(--v-surface-panel-soft);
  border-radius: var(--v-radius-lg) var(--v-radius-lg) 0 0;
}

.v-project-list-header > * { grid-row: 1; }
.v-list-col-project { grid-column: 2; }
.v-list-col-status { grid-column: 4; }
.v-list-col-shots { grid-column: 3; }
.v-list-col-due { grid-column: 5; }
.v-list-col-updated { grid-column: 6; }
.v-list-col-actions { grid-column: 7; }

.v-projects-list-body {
  display: flex;
  flex-direction: column;
}

.v-project-list-item {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr) 76px 126px 126px 118px 36px;
  gap: 14px;
  align-items: center;
  min-height: 64px;
  padding: 9px 10px;
  background: transparent;
  cursor: pointer;
  transition: background var(--v-duration-fast) var(--v-ease-emphasized);
  position: relative;
}

.v-project-list-item + .v-project-list-item {
  border-top: 1px solid var(--v-surface-border-soft);
}

.v-project-list-item:hover {
  background: var(--v-surface-tint-hover);
}

.v-project-list-item.is-opening {
  background: var(--v-surface-inline);
  pointer-events: none;
  opacity: 0.88;
}

.v-project-list-thumb {
  position: relative;
  width: 68px;
  height: 42px;
  border-radius: var(--v-radius-md);
  overflow: hidden;
  background: var(--v-surface-panel-soft);
  flex-shrink: 0;
}

.v-project-list-thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity var(--v-duration-normal) var(--v-ease-emphasized);
}

.v-project-list-thumb img.loaded { opacity: 1; }

.v-project-thumb-blank-sm .v-project-thumb-initials {
  font-size: var(--v-text-md);
}

.v-project-list-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.v-project-list-title {
  font-family: var(--v-font);
  font-size: var(--v-text-md);
  font-weight: 650;
  letter-spacing: 0;
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.v-project-list-subtitle {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 14px;
  font-size: var(--v-text-xs);
  color: var(--v-text-secondary);
}

.v-project-status-mobile {
  display: none;
}

.v-project-capability-inline {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--v-text-secondary);
  white-space: nowrap;
}

.v-project-capability-inline .icon {
  width: 11px;
  height: 11px;
}

.v-project-capability-inline.is-warning {
  color: var(--v-status-hold);
}

.v-project-list-shots {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  color: var(--v-text-secondary);
  font-variant-numeric: tabular-nums;
}

.v-project-list-shots-value {
  color: var(--v-text);
  font-weight: 500;
}

.v-project-list-status {
  display: flex;
  align-items: center;
  min-width: 0;
}

.v-project-list-status .v-project-status-chip {
  justify-content: flex-start;
  min-width: 0;
  max-width: 118px;
  height: 26px;
  padding: 0 9px;
  background: transparent;
}

.v-project-list-due {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  color: var(--v-text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.v-project-list-updated {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.v-project-list-due-empty {
  color: var(--v-text-muted);
  font-style: normal;
}

.v-project-list-item .project-card-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  opacity: 0.58;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.v-project-list-item:hover .project-card-actions,
.v-project-list-item:focus-within .project-card-actions,
.v-project-list-item.has-open-menu .project-card-actions {
  opacity: 1;
}

.v-project-list-item .project-menu {
  position: relative;
}

.v-project-list-item.has-open-menu {
  z-index: 20;
  overflow: visible;
}

/* Hide the mobile-only inline subtitle row on desktop */
.v-project-list-meta-mobile { display: none; }

@media (max-width: 1200px) and (min-width: 769px) {
  .v-project-list-header,
  .v-project-list-item {
    grid-template-columns: 60px minmax(0, 1fr) 66px 118px 114px 36px;
    gap: 12px;
  }

  .v-project-list-thumb {
    width: 60px;
    height: 38px;
  }

  .v-list-col-project { grid-column: 2; }
  .v-list-col-shots { grid-column: 3; }
  .v-list-col-status { grid-column: 4; }
  .v-list-col-due { grid-column: 5; }
  .v-list-col-actions { grid-column: 6; }
  .v-list-col-updated,
  .v-project-list-updated { display: none; }
}

/* ─── Mobile Responsive ───────────────────────────────────────────────────── */

@media (max-width: 768px) {
  /* Page Header */
  .projects-list .v-page-header {
    flex-wrap: wrap;
    padding: var(--v-space-3) var(--v-space-4);
    gap: var(--v-space-3);
  }

  .projects-list .v-page-title {
    font-size: var(--v-text-lg);
  }

  .projects-list .v-page-actions {
    width: 100%;
    margin-top: 0;
    justify-content: space-between;
  }

  /* Touch targets */
  .projects-list .v-btn {
    min-height: 44px;
    padding: var(--v-space-3) var(--v-space-4);
  }

  .projects-list .v-btn-icon {
    min-width: 44px;
    min-height: 44px;
  }

  .v-project-list-item .project-card-actions {
    opacity: 1;
  }

  .projects-list .v-btn-sm {
    min-height: 36px;
  }

  .projects-list .v-dropdown-item {
    min-height: 44px;
  }

  .projects-list .v-filter {
    min-height: 44px;
  }

  .projects-list .v-view-toggle-btn {
    padding: var(--v-space-3);
  }

  .v-project-status-mobile {
    display: inline-flex;
  }
}

/* ── Projects List View — collapses to rich card-rows at narrow widths ── */

@media (max-width: 768px) {
  .v-projects-list-view {
    margin: 16px 14px 28px;
    border-radius: var(--v-radius-lg);
  }

  .v-project-list-header { display: none; }

  .v-project-list-item {
    grid-template-columns: 52px minmax(0, 1fr) auto;
    grid-template-rows: auto auto;
    grid-template-areas:
      "thumb main actions"
      "thumb subtitle actions";
    column-gap: var(--v-space-3);
    row-gap: 2px;
    padding: 12px 14px;
    align-items: center;
  }

  .v-project-list-item + .v-project-list-item {
    box-shadow: 0 -1px 0 var(--v-border);
  }

  .v-project-list-thumb {
    grid-area: thumb;
    width: 52px;
    height: 52px;
    border-radius: var(--v-radius-md);
  }

  .v-project-list-main {
    grid-area: main;
  }

  .v-project-list-main .v-project-list-subtitle {
    grid-area: subtitle;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .v-project-list-meta-mobile {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--v-text-secondary);
  }

  .v-project-list-title {
    font-size: var(--v-text-md);
    line-height: 1.2;
  }

  /* Hide redundant columns on mobile — info is in the subtitle row */
  .v-project-list-shots,
  .v-project-list-status,
  .v-project-list-due,
  .v-project-list-updated { display: none; }

  .v-project-list-item .project-card-actions {
    grid-area: actions;
    align-self: center;
  }

  .v-project-list-item .v-dropdown {
    z-index: 9990;
  }
}

@media (max-width: 640px) {
  .v-projects-grid,
  .project-group,
  .v-projects-list-view {
    overflow: visible;
  }

  /* 2-column portrait grid on mobile */
  .v-projects-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--v-space-3);
  }

  .v-project-card { border-radius: var(--v-radius-lg); }
  .v-project-card .v-project-thumb {
    border-radius: var(--v-radius-lg) var(--v-radius-lg) 0 0;
    aspect-ratio: 4 / 3;
  }
  .v-project-status-chip {
    top: 8px;
    right: 8px;
    height: 22px;
    font-size: var(--v-text-2xs);
    padding: 0 8px 0 7px;
  }
  .v-project-status-chip .v-project-status-label { display: none; }
  .v-project-body {
    padding: 10px 10px 12px;
    gap: var(--v-space-1);
  }
  .v-project-title { font-size: var(--v-text-base); }
  .v-project-meta {
    font-size: var(--v-text-xs);
    gap: 3px 5px;
  }
  .v-project-meta-word { display: none; }

  .v-project-card .v-project-menu {
    right: 6px;
    bottom: 6px;
  }

  .v-project-card.has-open-menu {
    overflow: visible;
    z-index: 50;
  }

  .v-project-card .v-dropdown {
    z-index: 9990;
  }

  .projects-list {
    padding: 0;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   END DESIGN SYSTEM v1.0
   ═══════════════════════════════════════════════════════════════════════════ */

@media (max-width: 768px) {
  .projects-list { padding: 0; }
}

.v-page-header.project-browser-header {
  --project-control-size: 36px;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-5);
  min-height: 88px;
  padding: 19px 24px 18px;
  border-bottom: 1px solid var(--v-surface-border-soft);
}

.project-browser-heading {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.project-browser-heading .v-page-title {
  margin: 0;
  font-size: 25px;
  line-height: 1.1;
  letter-spacing: 0;
}

.project-browser-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
  font-variant-numeric: tabular-nums;
}

.project-browser-summary__divider {
  width: 1px;
  height: 11px;
  background: var(--v-surface-border-strong);
}

.project-browser-summary__active {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--v-text-secondary);
}

.project-browser-summary__active .v-project-status-dot {
  width: 5px;
  height: 5px;
  background: var(--v-status-active);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-active) 18%, transparent);
}

.project-browser-actions {
  flex: 0 0 auto;
  flex-wrap: nowrap;
  gap: var(--v-space-2);
}

.project-browser-header .v-view-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  height: var(--project-control-size);
  padding: 3px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-control-bg);
  box-sizing: border-box;
}

.project-browser-header .v-view-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: auto;
  min-width: 65px;
  height: 28px;
  min-height: 0;
  padding: 0 9px;
  gap: 6px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-xs);
  font-weight: 650;
}

.project-browser-header .v-view-toggle-btn .icon,
.project-browser-header .project-sort-trigger .icon {
  width: 15px;
  height: 15px;
}

.project-browser-header .project-sort-trigger {
  height: var(--project-control-size);
  min-height: var(--project-control-size);
  padding: 0 11px;
  gap: 7px;
  border-radius: var(--v-button-radius);
  box-sizing: border-box;
}

.project-view-label {
  line-height: 1;
}

.project-view-option-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent-muted);
  color: var(--v-accent);
  font-size: var(--v-text-2xs);
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.project-sort-label {
  max-width: 112px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-sort-chevron {
  width: 13px !important;
  height: 13px !important;
  color: var(--v-text-muted);
}

.project-browser-header .v-btn-primary {
  height: var(--project-control-size);
  min-height: var(--project-control-size);
  padding: 0 13px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-sm);
}

.project-menu-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-right: 3px;
  border: 1px solid var(--v-control-border-hover);
  border-radius: var(--v-radius-sm);
  color: var(--v-accent);
  flex: 0 0 auto;
}

.project-menu-check.is-checked {
  border-color: color-mix(in srgb, var(--v-accent) 48%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-accent) 10%, transparent);
}

.project-menu-check .icon {
  width: 12px;
  height: 12px;
}

.projects-sort-dropdown {
  min-width: 220px;
  padding-block: 7px;
}

.project-menu-label {
  padding: 6px 11px 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.12em;
  line-height: 1;
  text-transform: uppercase;
}

.project-sort-option,
.project-view-option {
  gap: 9px;
}

.project-sort-option {
  justify-content: space-between;
}

.project-sort-option.is-selected {
  color: var(--v-text);
  background: var(--v-surface-tint-hover);
}

.project-sort-check {
  width: 14px;
  height: 14px;
  color: var(--v-accent);
}

@media (max-width: 768px) {
  .v-page-header.project-browser-header {
    --project-control-size: 44px;
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-3);
    padding: 15px 14px 12px;
  }

  .project-browser-heading .v-page-title {
    font-size: 20px;
  }

  .project-browser-summary {
    font-size: var(--v-text-xs);
  }

  .project-browser-actions {
    width: 100%;
    margin-left: 0;
    gap: var(--v-space-2);
  }

  .project-browser-header .v-view-toggle {
    flex: 0 0 auto;
    height: var(--project-control-size);
    border-radius: var(--v-button-radius);
  }

  .project-browser-header .v-view-toggle-btn {
    width: 36px;
    min-width: 36px;
    height: 36px;
    padding: 0;
    border-radius: var(--v-button-radius);
  }

  .project-browser-header .project-view-label,
  .project-browser-header .project-view-option-count {
    display: none;
  }

  .project-browser-header .projects-sort-menu {
    flex: 0 0 var(--project-control-size);
    width: var(--project-control-size);
    height: var(--project-control-size);
  }

  .project-browser-header .project-sort-trigger {
    width: 100%;
    height: var(--project-control-size);
    min-height: var(--project-control-size);
    padding: 0;
    justify-content: center;
    border-radius: var(--v-button-radius);
  }

  .project-browser-header .project-sort-label,
  .project-browser-header .project-sort-chevron {
    display: none;
  }

  .project-browser-header .v-btn-primary {
    flex: 1 1 0;
    min-width: 0;
    height: var(--project-control-size);
    min-height: var(--project-control-size);
    justify-content: center;
    border-radius: var(--v-button-radius);
  }

  .projects-sort-dropdown {
    top: 48px;
  }

  .project-groups {
    gap: var(--v-space-6);
    padding: 16px 14px 28px;
  }

  .project-group {
    gap: 10px;
  }

  .v-projects-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .v-project-card {
    border-radius: var(--v-radius-md);
  }

  .v-project-card .v-project-thumb {
    aspect-ratio: 4 / 3;
    border-radius: var(--v-radius-md) var(--v-radius-md) 0 0;
  }

  .v-project-body {
    min-height: 86px;
    padding: 10px 38px 11px 10px;
  }

  .v-project-card .v-project-menu {
    right: 5px;
    bottom: 6px;
    opacity: 1;
  }

  .v-projects-list-view {
    margin: 16px 14px 28px;
    border-radius: 0;
  }
}

@media (max-width: 420px) {
  .v-project-card .v-project-meta-sep {
    display: none;
  }

  .v-project-status-chip {
    width: 22px;
    padding: 0;
    justify-content: center;
  }

  .v-project-status-chip .v-project-status-label {
    display: none;
  }

  .v-project-title {
    font-size: var(--v-text-sm);
  }

  .v-project-meta {
    font-size: var(--v-text-2xs);
  }
}
</style>
