<template>
  <div class="project-header-bar" :class="{ 'is-tracker': currentTracker, 'is-page': currentPage }">
    <div class="project-header-thumb">
      <img v-if="currentProjectHeaderThumbnailUrl" :src="currentProjectHeaderThumbnailUrl" @error="$event.target.style.display='none'"/>
      <svg v-else class="icon"><use href="#icon-project"/></svg>
    </div>

    <div class="project-header-info">
      <div class="project-title-row">
        <h2 class="project-title-readonly">{{ currentProject.title }}</h2>
        <span
          v-if="currentProject.storage_read_only"
          class="project-storage-badge"
          title="Project files are on read-only storage. Change its permissions or relocate the project to make changes."
        >
          <svg class="icon"><use href="#icon-lock" /></svg>
          Read-only
          <svg class="icon project-storage-badge__info"><use href="#icon-info" /></svg>
        </span>
      </div>
      <div class="project-meta-row">
        <span v-if="currentTracker" class="tracker-stats-tag">
          <span class="stat"><strong>{{ currentTracker.shots?.length || 0 }}</strong> shots</span>
          <template v-if="canViewTrackerDetails !== false">
            <span class="stat-divider" aria-hidden="true">·</span>
            <span class="stat"><strong>{{ trackerTotalDuration }}</strong></span>
            <span class="stat-divider" aria-hidden="true">·</span>
            <span class="stat"><strong>{{ trackerTotalFrames.toLocaleString() }}</strong> frames</span>
          </template>
          <span v-if="currentProject.description" class="stat-divider" aria-hidden="true">·</span>
          <span v-if="currentProject.description" class="project-desc-text">{{ currentProject.description }}</span>
        </span>
        <span v-else-if="currentProject.description" class="project-desc-text is-standalone">{{ currentProject.description }}</span>
      </div>
    </div>

    <div class="project-header-actions">
      <div class="project-header-action-row">
        <VMenu
          v-if="!currentTracker && !currentPage && canEditProject && !shareMode"
          :open="showNewMenu"
          align="end"
          class="project-header-action-slot project-header-action-slot-primary"
          @update:open="setNewMenuOpen"
        >
          <template #trigger="{ triggerProps }">
            <button class="v-btn v-btn-primary v-btn-sm" v-bind="triggerProps" @click.stop="toggleProjectNewMenu()">
              <svg class="icon"><use href="#icon-plus"/></svg>
              <span class="project-header-btn-label">New</span>
            </button>
          </template>
          <button v-if="currentUser?.role !== 'artist'" class="v-dropdown-item" @click="openProjectCreatePage()"><svg class="icon"><use href="#icon-file"/></svg> Vue Dashboard</button>
          <button v-if="currentUser?.role !== 'artist'" class="v-dropdown-item" @click="openProjectCreateTracker()"><svg class="icon"><use href="#icon-project"/></svg> Vue Tracker</button>
          <button class="v-dropdown-item" @click="openProjectCreateFolderFromMenu()"><svg class="icon"><use href="#icon-folder"/></svg> Folder</button>
          <div v-if="currentUser?.role !== 'artist'" class="v-dropdown-divider"></div>
          <button class="v-dropdown-item" :disabled="!canUploadToCurrentFolder" :title="projectUploadDisabledReason || ''" @click="openProjectFileImportFromMenu()"><svg class="icon"><use href="#icon-upload"/></svg> Upload Files</button>
          <button v-if="currentUser?.role !== 'artist'" class="v-dropdown-item" @click="openProjectLinkPickerFromMenu()"><svg class="icon"><use href="#icon-link"/></svg> Link from NAS</button>
        </VMenu>

        <VMenu
          v-if="!currentTracker && !currentPage && !canEditProject && currentUser?.role === 'artist' && projectPath"
          :open="showArtistNewMenu"
          align="end"
          class="project-header-action-slot project-header-action-slot-primary"
          @update:open="setNewMenuOpen"
        >
          <template #trigger="{ triggerProps }">
            <button class="v-btn v-btn-primary v-btn-sm" v-bind="triggerProps" @click.stop="toggleArtistNewMenu()">
              <svg class="icon"><use href="#icon-plus"/></svg>
              <span class="project-header-btn-label">New</span>
            </button>
          </template>
          <button class="v-dropdown-item" @click="openProjectCreateFolderFromMenu()">
            <svg class="icon"><use href="#icon-folder"/></svg> Folder
          </button>
          <button class="v-dropdown-item" :disabled="!canUploadToCurrentFolder" :title="projectUploadDisabledReason || ''" @click="openProjectFileImportFromMenu()">
            <svg class="icon"><use href="#icon-upload"/></svg> Upload Files
          </button>
        </VMenu>

        <button v-if="canOpenProjectSettings" class="v-btn v-btn-secondary v-btn-sm project-header-settings-btn project-header-action-slot" @click="openProjectSettings()">
          <svg class="icon"><use href="#icon-settings"/></svg>
          <span class="project-header-btn-label">Settings</span>
        </button>
      </div>
    </div>

    <div
      v-if="showOfflineNotice || (currentProject.uses_internal_storage && isAdmin && !shareMode && !currentTracker && !currentPage)"
      class="project-header-notices"
    >
      <div v-if="showOfflineNotice" class="project-header-notice is-offline" :class="{ 'is-expanded': showOfflineDetails }">
        <span class="project-header-notice__icon" aria-hidden="true"><svg class="icon"><use href="#icon-alert" /></svg></span>
        <p class="project-header-notice__copy">
          <strong>Some media is offline</strong>
          <span>{{ currentProject.unavailable_asset_count }} file{{ currentProject.unavailable_asset_count === 1 ? '' : 's' }} missing at this location</span>
        </p>
        <div v-if="isAdmin" class="project-header-notice__actions">
          <button type="button" class="v-btn v-btn-quiet v-btn-sm" :aria-expanded="showOfflineDetails" @click="toggleOfflineDetails">
            {{ showOfflineDetails ? 'Hide' : 'Details' }}
            <svg class="icon project-header-notice__chevron" :class="{ 'is-open': showOfflineDetails }"><use href="#icon-chevron-down" /></svg>
          </button>
          <button type="button" class="v-btn v-btn-quiet v-btn-sm" @click="openRelocateProject">Relocate</button>
          <button
            type="button"
            class="v-icon-action is-muted is-compact project-header-notice__dismiss"
            aria-label="Dismiss offline media notice"
            title="Dismiss"
            @click="dismissOfflineNotice"
          >
            <svg class="icon" aria-hidden="true"><use href="#icon-close" /></svg>
          </button>
        </div>

        <div v-if="showOfflineDetails" class="project-offline-details">
          <div v-if="offlineDetailsLoading" class="project-offline-details__state">Finding offline media…</div>
          <div v-else-if="offlineDetailsError" class="project-offline-details__state is-error">
            <span>{{ offlineDetailsError }}</span>
            <button type="button" class="v-btn v-btn-quiet v-btn-sm" @click="loadOfflineDetails">Retry</button>
          </div>
          <div v-else-if="!offlineMedia.length" class="project-offline-details__state">No offline media remains.</div>
          <div v-else class="project-offline-details__list">
            <div v-for="item in offlineMedia" :key="item.asset_id" class="project-offline-item">
              <span class="project-offline-item__icon" aria-hidden="true"><svg class="icon"><use :href="item.references?.length ? '#icon-video' : '#icon-file'" /></svg></span>
              <div class="project-offline-item__copy">
                <strong>{{ item.file_name || 'Missing file' }}</strong>
                <span v-if="item.references?.length">
                  {{ formatOfflineReference(item.references[0]) }}
                  <template v-if="item.references.length > 1"> · +{{ item.references.length - 1 }} more</template>
                </span>
                <span v-else>Project files</span>
                <small :title="item.file_path">{{ item.file_path }}</small>
              </div>
            </div>
            <p v-if="offlineDetailsTotal > offlineMedia.length" class="project-offline-details__more">
              Showing {{ offlineMedia.length }} of {{ offlineDetailsTotal }} missing files
            </p>
          </div>
        </div>
      </div>

      <div v-if="currentProject.uses_internal_storage && isAdmin && !shareMode && !currentTracker && !currentPage" class="project-header-notice is-storage-hint">
        <span class="project-header-notice__icon" aria-hidden="true"><svg class="icon"><use href="#icon-folder" /></svg></span>
        <p class="project-header-notice__copy">
          <strong>Legacy internal storage</strong>
          <span>Choose a working project folder</span>
        </p>
        <button type="button" class="v-btn v-btn-quiet v-btn-sm" @click="openMigrateProject">Set folder</button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'
import { VMenu } from '../components/primitives'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useFileBrowserStore } from '../ownership/fileBrowser'

const { currentProject, currentTracker, currentPage } = useProjectTrackerSelectionStore()
const { currentUser, isAdmin, canEditProject: canEditProjectPermission } = useSessionAuthStore()
const { shareMode } = useShareAccessContext()
const fileBrowserStore = useFileBrowserStore()
const {
  canUploadToProject: canUploadToCurrentFolder,
  projectUploadDisabledReason,
} = fileBrowserStore.uploads.project
const {
  currentProjectHeaderThumbnailUrl,
  canOpenProjectSettings,
  canViewTrackerDetails,
  openProjectSettings,
  openRelocateProject,
  openMigrateProject,
  trackerTotalDuration,
  trackerTotalFrames,
  projectPath,
  showNewMenu,
  toggleProjectNewMenu,
  openProjectCreatePage,
  openProjectCreateTracker,
  openProjectCreateFolderFromMenu,
  closeNewMenu,
  showArtistNewMenu,
  toggleArtistNewMenu,
} = useProjectWorkspaceStore()
const canEditProject = computed(() => canEditProjectPermission.value && !currentProject.value?.storage_read_only)

/* VMenu owns dismissal (outside pointerdown, Escape with focus restore, Tab)
   and only ever reports closing, so this just forwards to the store. */
function setNewMenuOpen(open) {
  if (!open) closeNewMenu()
}

function openProjectFileImportFromMenu() {
  fileBrowserStore.uploads.project.openUpload()
  closeNewMenu()
}

function openProjectLinkPickerFromMenu() {
  fileBrowserStore.picker.openProjectLinkPicker()
  closeNewMenu()
}

const showOfflineDetails = ref(false)
const offlineDetailsLoading = ref(false)
const offlineDetailsError = ref('')
const offlineDetailsProjectId = ref('')
const offlineMedia = ref([])
const offlineDetailsTotal = ref(0)
const dismissedOfflineNoticeSignature = ref('')

const offlineNoticeSignature = computed(() => {
  const project = currentProject.value
  if (!project?.has_offline_media) return ''
  return [
    project.storage_root || '',
    project.storage_path || '',
    Number(project.unavailable_asset_count || 0),
  ].join(':')
})

const offlineNoticeStorageKey = computed(() => {
  const projectId = currentProject.value?.id
  if (!projectId) return ''
  return `vueio:offline-notice-dismissed:${currentUser.value?.id || 'session'}:${projectId}`
})

const showOfflineNotice = computed(() => (
  Boolean(offlineNoticeSignature.value)
  && dismissedOfflineNoticeSignature.value !== offlineNoticeSignature.value
  && !shareMode.value
))

function syncOfflineNoticeDismissal() {
  const key = offlineNoticeStorageKey.value
  const signature = offlineNoticeSignature.value
  if (!key || typeof window === 'undefined') {
    dismissedOfflineNoticeSignature.value = ''
    return
  }
  try {
    if (!signature) {
      window.localStorage.removeItem(key)
      dismissedOfflineNoticeSignature.value = ''
      return
    }
    dismissedOfflineNoticeSignature.value = window.localStorage.getItem(key) === signature ? signature : ''
  } catch {
    dismissedOfflineNoticeSignature.value = ''
  }
}

function dismissOfflineNotice() {
  const key = offlineNoticeStorageKey.value
  const signature = offlineNoticeSignature.value
  if (!key || !signature || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, signature)
    dismissedOfflineNoticeSignature.value = signature
    showOfflineDetails.value = false
  } catch {
    // Browsers may deny storage in hardened private contexts; the notice remains visible.
  }
}

async function loadOfflineDetails() {
  const projectId = currentProject.value?.id
  if (!projectId || !isAdmin.value) return
  offlineDetailsLoading.value = true
  offlineDetailsError.value = ''
  try {
    const { data } = await api.get(`/api/projects/${encodeURIComponent(projectId)}/offline-media`)
    offlineMedia.value = data.items || []
    offlineDetailsTotal.value = Number(data.total || 0)
    offlineDetailsProjectId.value = projectId
  } catch (error) {
    offlineDetailsError.value = getApiErrorMessage(error, 'Unable to load offline media details.')
  } finally {
    offlineDetailsLoading.value = false
  }
}

async function toggleOfflineDetails() {
  showOfflineDetails.value = !showOfflineDetails.value
  if (showOfflineDetails.value && offlineDetailsProjectId.value !== currentProject.value?.id) {
    await loadOfflineDetails()
  }
}

function formatOfflineReference(reference) {
  return [reference.tracker_name, reference.shot_code, reference.version_label].filter(Boolean).join(' · ')
}

watch(() => currentProject.value?.id, () => {
  showOfflineDetails.value = false
  offlineDetailsProjectId.value = ''
  offlineMedia.value = []
  offlineDetailsTotal.value = 0
  offlineDetailsError.value = ''
})

watch([offlineNoticeSignature, offlineNoticeStorageKey], syncOfflineNoticeDismissal, { immediate: true })
</script>

<style>
/* ── Project Header Bar ───────────────────────────────────────────── */
.project-header-bar {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 0 16px;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid color-mix(in srgb, var(--v-surface-panel) 91%, white);
  background: var(--v-bg-base);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  min-height: 78px;
}

.project-header-bar.is-tracker {
  min-height: 76px;
  border-bottom-color: color-mix(in srgb, var(--v-surface-panel) 94%, white);
}

/* ── Thumbnail (uniform across modes) ─────────────────────────────── */
.project-header-thumb {
  width: 64px;
  height: 64px;
  border-radius: var(--v-radius-lg);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-surface-inline) 90%, white);
  background: color-mix(in srgb, var(--v-surface-inline) 82%, var(--v-bg-base));
  box-shadow: 0 12px 26px rgba(0, 0, 0, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-header-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.project-header-thumb .icon {
  width: 22px;
  height: 22px;
  color: var(--v-text-muted);
}

/* ── Info block ───────────────────────────────────────────────────── */
.project-header-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.project-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.project-title-readonly {
  margin: 0;
  font-size: var(--v-text-2xl);
  font-weight: 720;
  line-height: 1.2;
  letter-spacing: 0;
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-storage-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 8px;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--v-accent) 24%, var(--v-control-border));
  border-radius: var(--v-radius-full);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-inline));
  font-size: var(--v-text-2xs);
  font-weight: 700;
}

.project-storage-badge .icon { width: 11px; height: 11px; }
.project-storage-badge__info { opacity: 0.72; }

.project-header-notices {
  grid-column: 2 / 4;
  grid-row: 2;
  display: flex;
  gap: var(--v-space-3);
  flex-wrap: wrap;
  align-items: flex-start;
  min-width: 0;
  margin-top: var(--v-space-2);
}

.project-header-notice {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 320px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.project-header-notice__icon {
  display: grid;
  place-items: center;
  color: var(--v-warning);
  opacity: 0.9;
}
.project-header-notice__icon .icon { width: 13px; height: 13px; }
.project-header-notice__copy {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
}
.project-header-notice__copy strong {
  flex: 0 0 auto;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
}
.project-header-notice__copy span {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  text-overflow: ellipsis;
}
.project-header-notice .v-btn {
  min-height: 28px;
  height: 28px;
  padding: 0 8px;
  font-size: var(--v-text-xs);
  font-weight: 600;
}
.project-header-notice.is-expanded { flex-basis: 100%; }
.project-header-notice__actions { display: flex; align-items: center; gap: 2px; }
.project-header-notice__actions .icon { width: 11px; height: 11px; }
.project-header-notice__dismiss { color: var(--v-text-muted); }
.project-header-notice__dismiss:hover { color: var(--v-text); }
.project-header-notice__chevron { transition: transform var(--v-transition-fast); }
.project-header-notice__chevron.is-open { transform: rotate(180deg); }

.project-offline-details {
  grid-column: 1 / -1;
  min-width: 0;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--v-divider-subtle);
}
.project-offline-details__list { display: grid; gap: 2px; max-height: 230px; overflow-y: auto; }
.project-offline-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
  padding: 6px 2px;
  border: none;
  border-radius: 0;
  background: transparent;
}
.project-offline-item + .project-offline-item {
  border-top: 1px solid var(--v-divider-subtle);
}
.project-offline-item__icon {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  color: var(--v-text-muted);
  background: transparent;
}
.project-offline-item__icon .icon { width: 12px; height: 12px; }
.project-offline-item__copy {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
  align-items: baseline;
  gap: 1px 8px;
}
.project-offline-item__copy strong {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-offline-item__copy span {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-offline-item__copy small {
  grid-column: 1 / -1;
  overflow: hidden;
  color: var(--v-text-dim);
  font-size: var(--v-text-2xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-offline-details__state {
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}
.project-offline-details__state.is-error { color: var(--v-danger); }
.project-offline-details__more {
  margin: 6px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
}

.project-header-notice.is-storage-hint .project-header-notice__icon {
  color: var(--v-accent);
}

.project-meta-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
  overflow: hidden;
}

/* ── Tracker stats (in-tracker mode only) ─────────────────────────── */
.tracker-stats-tag {
  display: inline-flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 7px;
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tracker-stats-tag .stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}

.tracker-stats-tag strong {
  color: var(--v-text);
  font-weight: 700;
  letter-spacing: 0;
}

.tracker-stats-tag .stat-divider {
  flex-shrink: 0;
  color: var(--v-text-muted);
  opacity: 0.45;
}

/* ── Description ─────────────────────────────────────────────────── */
.project-desc-text {
  min-width: 0;
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-desc-text.is-standalone {
  flex: 1;
}

/* ── Actions (shared shell) ──────────────────────────────────────── */
.project-header-actions {
  grid-column: 3;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.project-header-action-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.project-header-action-slot {
  flex-shrink: 0;
}

/* Unify primary + settings buttons so they share the same compact shape */
.project-header-action-row .v-btn {
  min-height: 32px;
  height: 32px;
  gap: 6px;
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  background: color-mix(in srgb, var(--v-surface-inset) 86%, var(--v-surface-panel));
  border: 1px solid var(--v-control-border);
  color: var(--v-text-secondary);
  box-shadow: var(--v-surface-shadow-inset);
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.project-header-action-row .v-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border-hover);
  color: var(--v-text);
}

.project-header-action-row .v-btn .icon {
  width: 14px;
  height: 14px;
  opacity: 0.9;
}

.project-header-action-row .v-btn-primary {
  padding: 0 14px 0 12px;
  background: color-mix(in srgb, var(--v-accent) 72%, var(--v-surface-panel));
  border-color: color-mix(in srgb, var(--v-accent) 52%, white);
  color: #07100b;
  box-shadow: none;
}

.project-header-action-row .v-btn-primary:hover:not(:disabled) {
  background: var(--v-accent-hover);
  color: #07100b;
}

/* ── Mobile ───────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .project-header-bar,
  .project-header-bar.is-tracker {
    grid-template-columns: 44px minmax(0, 1fr) auto;
    gap: 0 12px;
    padding: 10px 14px;
    min-height: 0;
  }

  .project-header-thumb {
    width: 44px;
    height: 44px;
    border-radius: var(--v-radius-md);
  }

  .project-header-thumb .icon {
    width: 18px;
    height: 18px;
  }

  .project-title-readonly {
    font-size: var(--v-text-md);
  }

  .project-meta-row {
    margin-top: 2px;
    gap: 6px;
  }

  .tracker-stats-tag {
    font-size: var(--v-text-xs);
    gap: var(--v-space-1);
  }

  .project-desc-text {
    display: none;
  }

  /* Actions sit inline next to the title, compact and right-aligned */
  .project-header-actions {
    grid-column: 3;
    grid-row: 1;
    flex-direction: row;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    margin-top: 0;
  }

  .project-header-action-row {
    gap: 6px;
  }

  .project-header-action-row .v-btn {
    min-height: 30px;
    height: 30px;
    padding: 0 10px;
  }

  /* Settings becomes icon-only on mobile to save horizontal room */
  .project-header-action-row .project-header-settings-btn {
    width: 30px;
    min-width: 30px;
    padding: 0;
    justify-content: center;
  }

  .project-header-action-row .project-header-settings-btn .project-header-btn-label {
    display: none;
  }

  .project-header-notices {
    grid-column: 1 / -1;
    flex-direction: column;
    gap: 6px;
    margin-top: var(--v-space-2);
  }

  .project-header-notice { width: 100%; flex-basis: auto; }
}

@media (max-width: 430px) {
  .project-header-notice__copy { display: grid; gap: 0; }
}
</style>
