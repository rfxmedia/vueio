<template>
  <div class="vueio" :class="{ 'vueio-low-fx': enableLowFx }">
    <!-- SVG Icon Sprite -->
    <AppIcons />

    <AppShell>
      <template #nav-center>
        <TrackerViewerStepper />
      </template>

      <template #nav-left-trailing>
        <TrackerViewerControls />
      </template>

      <template #search>
        <GlobalSearch
          ref="globalSearchRef"
        />
      </template>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <FileBrowserView v-if="filesModuleVisited" />
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- HOME -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <main v-if="activeModule === 'home' && currentUser" v-show="showMainContent" class="projects-view">
      <HomeView />
    </main>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- PROJECT MANAGEMENT MODULE -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <main v-if="activeModule === 'projects' && canAccessProjectManager" v-show="showMainContent" class="projects-view">
          <ProjectListView v-if="!currentProject" />

          <ProjectDetailView
            v-else
          >
            <template #tracker>
              <TrackerSurface v-if="currentTracker" />
            </template>
          </ProjectDetailView>
    </main>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- SETTINGS MODULE -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <main v-if="activeModule === 'settings' && currentUser" v-show="showMainContent" class="projects-view">
          <AdminView />
    </main>

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- UNIFIED MEDIA VIEWER (Videos & Images) -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <MediaViewerContainer v-if="currentMedia" />

    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- MODALS -->
    <!-- ════════════════════════════════════════════════════════════════════ -->

    <SetupWizardModal v-if="setupRequired" />

    <ShareAuthModalCluster />

    <ProjectModalHost />

    </AppShell>

    <VToastViewport />

    <div
      v-if="connectionLost"
      class="connection-recovery"
      role="status"
      aria-live="assertive"
    >
      <div class="connection-recovery__panel">
        <span class="connection-recovery__spinner" aria-hidden="true"></span>
        <div>
          <strong>Vueio is updating or restarting</strong>
          <p>This page will reconnect automatically.</p>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, shallowRef, reactive, computed, defineAsyncComponent, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getApiErrorMessage } from './lib/api'
import { useConnectionRecovery } from './lib/connectionRecovery'
import AppIcons from './components/AppIcons.vue'
import AppShell from './components/shell/AppShell.vue'
import VToastViewport from './components/primitives/VToastViewport.vue'

import GlobalSearch from './components/shell/GlobalSearch.vue'
import ShareAuthModalCluster from './components/modals/ShareAuthModalCluster.vue'
import { useProjectWorkspaceController } from './composables/useProjectWorkspaceController'
import { useMediaViewerController } from './composables/useMediaViewerController'
import { useBrowserSession } from './composables/useBrowserSession'
import TrackerViewerControls from './components/tracker/TrackerViewerControls.vue'
import TrackerViewerStepper from './components/tracker/TrackerViewerStepper.vue'
import ProjectModalHost from './components/modals/ProjectModalHost.vue'

import { useAppRouting } from './composables/useAppRouting'
import { useAppBootstrapLifecycle } from './composables/useAppBootstrapLifecycle'
import { useFileBrowserViewState } from './composables/useFileBrowserViewState'
import { notify } from './utils/toasts'
import {
  TRACKER_STATUS_ORDER,
  TRACKER_STATUS_LABELS,
  TRACKER_STATUS_COLORS,
  getTrackerStatusLabel,
} from './lib/trackerCatalogs'
import { createSessionAuthStore, provideSessionAuthStore } from './ownership/sessionAuth'
import { createShareAccessContext, provideShareAccessContext } from './ownership/shareAccessContext'
import { createProjectTrackerSelectionStore, provideProjectTrackerSelectionStore } from './ownership/projectTrackerSelection'
import { createNavigationStore, provideNavigationStore } from './ownership/navigation'
import { createProjectWorkspaceStore, provideProjectWorkspaceStore } from './ownership/projectWorkspace'
import { createTrackerStore, provideTrackerStore } from './ownership/tracker'
import { createViewerStore, provideViewerStore } from './ownership/viewer'
import { createFileBrowserStore, provideFileBrowserStore } from './ownership/fileBrowser'
import { createProjectSettingsStore, provideProjectSettingsStore } from './ownership/projectSettings'
import { createAppIdentityStore, provideAppIdentityStore } from './ownership/appIdentity'
import { createAppChromeStore, provideAppChromeStore } from './ownership/appChrome'
import { createShareManagementStore, provideShareManagementStore } from './ownership/shareManagement'
import { createActivityStore, provideActivityStore } from './ownership/activity'
import { createUpdateStatusStore, provideUpdateStatusStore } from './ownership/updateStatus'

const AdminView = defineAsyncComponent(() => import('./views/AdminView.vue'))
const FileBrowserView = defineAsyncComponent(() => import('./views/FileBrowserView.vue'))
const HomeView = defineAsyncComponent(() => import('./views/HomeView.vue'))
const MediaViewerContainer = defineAsyncComponent(() => import('./components/media/MediaViewerContainer.vue'))
const ProjectDetailView = defineAsyncComponent(() => import('./views/ProjectDetailView.vue'))
const ProjectListView = defineAsyncComponent(() => import('./views/ProjectListView.vue'))
const SetupWizardModal = defineAsyncComponent(() => import('./components/modals/SetupWizardModal.vue'))
const TrackerSurface = defineAsyncComponent(() => import('./components/tracker/TrackerSurface.vue'))

// ══════════════════════════════════════════════════════════════════════════════
// ROUTER
// ══════════════════════════════════════════════════════════════════════════════

const router = useRouter()
const route = useRoute()

// ══════════════════════════════════════════════════════════════════════════════
// STATE - GENERAL
// ══════════════════════════════════════════════════════════════════════════════

const activeModule = ref('home') // 'home', 'files', 'projects', or 'settings'
const filesModuleVisited = ref(false)
const loading = ref(true)

function isRequestCanceled(error) {
  return error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED'
}

const appIdentityStore = provideAppIdentityStore(createAppIdentityStore())
const { identity: appIdentity, update: updateAppIdentity, load: loadAppIdentity } = appIdentityStore
const shareAccessContext = provideShareAccessContext(createShareAccessContext())
const {
  shareMode,
  shareRoot,
  shareAllowDownload,
  sharePasswordRequired,
  shareAccessToken,
  shareAccessTokenScope,
  pendingShareId,
  pendingShareType,
  shareAccessError,
  sharedItemType,
  getShareCredential,
} = shareAccessContext

const browserSession = useBrowserSession()
let trackerStore
let fileBrowserStore
let projectSettingsStore
let shareManagementStore
let appChromeStore
const trackerStoreRef = shallowRef(null)

const globalSearchRef = ref(null)
const { connectionLost } = useConnectionRecovery()


// ══════════════════════════════════════════════════════════════════════════════
// UNIFIED BACK BUTTON SYSTEM
// ══════════════════════════════════════════════════════════════════════════════
// One consistent back button that works everywhere, easy to disable for shares

// Standardized API error handler
function handleError(message, error) {
  notify(`${message}: ${getApiErrorMessage(error)}`)
}

// ═══════════════════════════════════════════════════════════════════════════
// FILE / MODULE NAV HELPERS
// ═══════════════════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════════════════════
// STATE - VIDEO PLAYER
// ══════════════════════════════════════════════════════════════════════════════

const projectTrackerSelectionStore = provideProjectTrackerSelectionStore(createProjectTrackerSelectionStore())
const {
  currentProject,
  currentTracker,
  currentTrackerRef,
  currentPage,
  openingProjectId,
} = projectTrackerSelectionStore
function mediaMatchesThumbnailTarget(item, target) {
  const shotVersionId = item?.horizons_shot_version_id || item?.version_id || null
  const mediaAssetId = item?.horizons_media_asset_id || item?.media_asset_id || null
  if (!item || !target) return false
  if (target.shotVersionId && shotVersionId === target.shotVersionId) return true
  if (target.mediaAssetId && mediaAssetId === target.mediaAssetId) return true
  const itemPath = item.path || item.file_path || item.source_path || ''
  return Boolean(target.path && itemPath === target.path)
}

function withThumbnailRefreshToken(item, token) {
  return {
    ...item,
    thumbnail_refresh_token: token,
    _thumbnailCacheBust: token,
  }
}

function refreshProjectMediaThumbnailCaches(target, token) {
  if (currentTracker.value?.shots?.length) {
    let trackerChanged = false
    const shots = currentTracker.value.shots.map((shot) => {
      let shotChanged = false
      const versions = (shot.versions || []).map((version) => {
        if (!mediaMatchesThumbnailTarget(version, target)) return version
        shotChanged = true
        return withThumbnailRefreshToken(version, token)
      })
      if (!shotChanged) return shot
      trackerChanged = true
      return { ...shot, versions }
    })
    if (trackerChanged) {
      currentTracker.value = { ...currentTracker.value, shots }
    }
  }

  if (projectContents.value?.length) {
    let contentsChanged = false
    const contents = projectContents.value.map((item) => {
      if (!mediaMatchesThumbnailTarget(item, target)) return item
      contentsChanged = true
      return withThumbnailRefreshToken(item, token)
    })
    if (contentsChanged) {
      projectContents.value = contents
    }
  }
}

const viewerController = useMediaViewerController({
  currentProject,
  currentTracker,
  currentUser: () => currentUser.value,
  shareMode,
  shareRoot,
  shareAllowDownload,
  pendingShareId,
  shareAccessToken,
  shareAccessTokenScope,
  getShareCredential,
  getShotVersions: (...args) => trackerStore?.getShotVersions(...args) || [],
  triggerBlobDownload: (...args) => triggerBlobDownload(...args),
  getFallbackFrameSourceName: () => trackerStore?.currentTrackerViewerShot?.value?.shot_id || '',
  onError: handleError,
  onTrackerActivityChanged: async ({ target, count } = {}) => {
    trackerStore?.setTrackerCommentCount(target, count)
    if (currentTrackerRef.value) await trackerStore?.loadTrackerActivity(currentTrackerRef.value)
  },
  onThumbnailUpdated: refreshProjectMediaThumbnailCaches,
  onMediaChanged: () => {
    if (trackerStore?.versionCompareActive.value) trackerStore.exitVersionCompare()
  },
  onMediaDismissed: () => {
    trackerStore?.dismissTrackerViewerVersionSwitcher()
    if (trackerStore?.showStatusPicker) trackerStore.showStatusPicker.value = null
  },
  isCloseLocked: () => shareMode.value && sharedSingleFile.value,
  onViewerClosed: ({ filePath }) => {
    if (!filePath || activeModule.value !== 'files') return
    const parentPath = filePath.split('/').slice(0, -1).join('/')
    if (shareMode.value && shareRoot.value) {
      const insideShare = parentPath.startsWith(shareRoot.value) ||
        parentPath === shareRoot.value || shareRoot.value.startsWith(parentPath)
      void loadFiles(insideShare ? parentPath || shareRoot.value : shareRoot.value)
      return
    }
    void loadFiles(parentPath)
  },
  getCommentReferenceOriginContext: () => ({
    trackerRef: currentTracker.value?.id || currentTracker.value?.slug || currentTracker.value?.name || '',
    pageRef: currentPage.value?.id || currentPage.value?.slug || '',
    projectPath: projectPath.value || '',
    routeFullPath: route.fullPath || '',
  }),
  onOpenProjectReference: async (reference) => {
    if (reference?.target_type === 'folder') {
      const targetPath = String(reference.target_id || '').replace(/^\/+|\/+$/g, '')
      if (!targetPath) return false
      await projectWorkspaceController.navigateProjectFolder(targetPath)
      if (projectPath.value !== targetPath) return false
      currentTracker.value = null
      currentPage.value = null
      activeModule.value = 'projects'
      return true
    } else if (reference?.target_type === 'tracker') {
      return Boolean(await trackerStore?.openTracker(reference.target_id))
    } else if (reference?.target_type === 'shot' && reference.tracker_id) {
      const tracker = await trackerStore?.openTracker(reference.tracker_id, { fresh: true })
      if (!tracker) return false
      const shot = (tracker.shots || []).find(item => (
        String(item?.id || item?._originalId || item?.shot_id || '') === String(reference.target_id)
      ))
      if (!shot) return false
      trackerStore?.openShotVideo(shot)
      return true
    } else if (reference?.target_type === 'page') {
      await projectWorkspaceController.openPage(reference.target_id)
      return [currentPage.value?.id, currentPage.value?.slug]
        .some(value => String(value || '') === String(reference.target_id))
    }
    return false
  },
  onRestoreCommentReferenceOrigin: async ({ context } = {}) => {
    const trackerRef = context?.trackerRef || ''
    const pageRef = context?.pageRef || ''
    if (trackerRef) {
      const activeTrackerRef = currentTracker.value?.id || currentTracker.value?.slug || currentTracker.value?.name || ''
      if (String(activeTrackerRef) === String(trackerRef)) return true
      return Boolean(await trackerStore?.openTracker(trackerRef))
    }
    if (pageRef) {
      const activePageRef = currentPage.value?.id || currentPage.value?.slug || ''
      if (String(activePageRef) === String(pageRef)) return true
      await projectWorkspaceController.openPage(pageRef)
      return [currentPage.value?.id, currentPage.value?.slug]
        .some(value => String(value || '') === String(pageRef))
    }
    if (currentTracker.value) trackerStore?.closeTracker()
    if (currentPage.value) closePage()
    await navigateProjectFolder(context?.projectPath || '', { replaceRoute: true })
    return true
  },
})

const {
  currentVideo,
  currentMedia,
  videoEl,
  sidebarTab,
} = viewerController.state
const {
  isViewingVideo,
  getThumbnailUrl,
  isProjectRenderPath,
  isProjectScopedPath,
  getProjectThumbnailUrl,
  getProjectFolderThumbnailUrl,
  bumpProjectHeaderThumbnailRefresh,
  currentProjectHeaderThumbnailUrl,
  currentProjectDeliveryThumbnailUrl,
  getProjectFileThumbnailUrl,
  openVideo,
  openImage,
  openPdf,
  closeViewer,
  dismissCurrentMedia: dismissCurrentMediaForNavigation,
} = viewerController.media
const {
  getBriefMediaFile,
  loadTrackerBriefPreviews,
  getBriefPreviewText,
  isBriefPreviewEmpty,
  getLatestPreviewText,
  isLatestPreviewEmpty,
} = viewerController.comments
const { isDrawingMode } = viewerController.annotations
const { formatTimecode } = viewerController.actions


// ══════════════════════════════════════════════════════════════════════════════
// STATE - PROJECT MANAGEMENT (Notion-like folder structure)
// ══════════════════════════════════════════════════════════════════════════════

const fileBrowserViewState = useFileBrowserViewState()
const projectWorkspaceController = useProjectWorkspaceController({
  router,
  route,
  currentProject,
  currentTracker,
  currentPage,
  openingProjectId,
  getCurrentUser: () => currentUser.value,
  shareMode,
  sharedItemType,
  pendingShareId,
  shareAccessToken,
  shareAccessTokenScope,
  fileBrowserViewState,
  browserSession,
  isRequestCanceledError: isRequestCanceled,
  openImage,
  openPdf,
  openVideo,
  dismissCurrentMediaForNavigation,
  closeProjectSettings: () => projectSettingsStore?.closeProjectSettingsModal(),
  closeTrackerSettings: () => projectSettingsStore?.closeTrackerSettingsModal(),
  closeDashboardSettings: () => projectSettingsStore?.closeDashboardSettingsModal(),
  resetProjectTeamState: (...args) => projectSettingsStore?.resetProjectTeamState(...args),
  loadProjectTeamOptions: (...args) => projectSettingsStore?.loadProjectTeamOptions(...args),
  prepareProjectStorageSelection: () => {
    if (!projectSettingsStore) return
    projectSettingsStore.newProjectStorageRoot.value = ''
    projectSettingsStore.newProjectStoragePath.value = null
    projectSettingsStore.loadProjectStorageRoots()
  },
  getProjectStorageSelection: () => ({
    roots: projectSettingsStore?.projectStorageRoots.value || [],
    rootId: projectSettingsStore?.newProjectStorageRoot.value || '',
    path: projectSettingsStore?.newProjectStoragePath.value ?? null,
  }),
  resetProjectStorageSelection: () => {
    if (!projectSettingsStore) return
    projectSettingsStore.newProjectStorageRoot.value = ''
    projectSettingsStore.newProjectStoragePath.value = null
  },
  openShareProjectFromList: project => shareManagementStore?.shareProjectFromList(project),
  handleProjectExternalDragOver: (...args) => fileBrowserStore?.uploads.project.handleExternalDragOver(...args),
  handleProjectExternalDragLeave: (...args) => fileBrowserStore?.uploads.project.handleExternalDragLeave(...args),
  handleProjectExternalDrop: (...args) => fileBrowserStore?.uploads.project.handleProjectExternalDrop(...args),
  handleError,
})

const {
  projects,
  projectContents,
  projectPath,
  artistWorkspaceRoot,
  getParentProjectPath,
  applyProjectContentsSnapshot,
  getProjectContentsAbortController,
  loadProjects,
  openProject,
  navigateProjectFolder,
  closePage,
  savePage,
  clonePageDraft,
  refreshProjectContents,
  newTrackerName,
  showCreateTracker,
  projectMenuOpen,
} = projectWorkspaceController

// Performance: Clean up heavy data when navigating away from views
watch(activeModule, (newModule, oldModule) => {
  if (newModule === 'files') filesModuleVisited.value = true
  // Clear tracker data when leaving projects
  if (oldModule === 'projects' && newModule !== 'projects') {
    currentTracker.value = null
    currentPage.value = null
  }
  // Clear file browser data when leaving files
  if (oldModule === 'files' && newModule !== 'files') {
    files.value = []
  }
})

const showMainContent = computed(() => !currentMedia.value)

function openBriefVideo(shot) {
  trackerStore.openTrackerViewerShot(shot, 'brief')
}

const STATUS_ORDER = TRACKER_STATUS_ORDER
const STATUS_LABELS = TRACKER_STATUS_LABELS
const STATUS_COLOR_MAP = TRACKER_STATUS_COLORS

function formatStatus(status) { return getTrackerStatusLabel(status) }

// ══════════════════════════════════════════════════════════════════════════════
// FILE BROWSER 3-DOT MENU
// ══════════════════════════════════════════════════════════════════════════════

// Close file menu when clicking outside

// ══════════════════════════════════════════════════════════════════════════════
// AUTHENTICATION
// ══════════════════════════════════════════════════════════════════════════════

const sessionAuthStore = provideSessionAuthStore(createSessionAuthStore({
  shareMode,
  shareAllowDownload,
  activeModule,
  currentProject,
  loadFiles: (...args) => fileBrowserStore?.browser.loadFiles(...args),
  loadProjects,
  onSetupComplete: data => {
    if (data?.identity) updateAppIdentity(data.identity)
  },
}))

const {
  currentUser,
  setupRequired,
  isAdmin,
  canAccessProjectManager,
  canEditProject,
  canManageProjectContent,
  canCreateProjects,
  canDeleteProjects,
  canAddShots,
  canEditShotName,
  canEditDescription,
  canDeleteShots,
  canAddVersions,
  canManageVersionPublication,
  showShotDownloads,
} = sessionAuthStore

provideUpdateStatusStore(createUpdateStatusStore({ session: sessionAuthStore }))

const trackerShotsForDisplayRef = computed(() => trackerStoreRef.value?.trackerShotsForDisplay.value || [])
const projectSettingsTargetRef = computed(() => projectSettingsStore?.projectSettingsTarget.value || null)

fileBrowserStore = provideFileBrowserStore(createFileBrowserStore({
  router,
  route,
  browserSession,
  fileBrowserViewState,
  isRequestCanceled,
  shell: { showMainContent, activeModule, loading },
  session: sessionAuthStore,
  share: shareAccessContext,
  selection: projectTrackerSelectionStore,
  workspace: projectWorkspaceController,
  viewer: {
    currentVideo,
    openImage,
    openPdf,
    openVideo,
    dismissCurrentMediaForNavigation,
    isProjectScopedPath,
    getThumbnailUrl,
    getProjectFolderThumbnailUrl,
    bumpProjectHeaderThumbnailRefresh,
    formatTimecode,
  },
  tracker: {
    trackerShotsForDisplay: trackerShotsForDisplayRef,
    getLatestShotFilePath: (...args) => trackerStore?.getLatestShotFilePath(...args),
    refreshCurrentTrackerPreserveState: (...args) => trackerStore?.refreshCurrentTrackerPreserveState(...args),
    openTracker: (...args) => trackerStore?.openTracker(...args),
    loadTrackerStats: (...args) => trackerStore?.loadTrackerStats(...args),
    loadTrackerActivity: (...args) => trackerStore?.loadTrackerActivity(...args),
  },
  settings: {
    projectSettingsTarget: projectSettingsTargetRef,
    selectDeliveryLogoSource: item => projectSettingsStore?.selectTrackerSettingsDeliveryLogoFromNas(item),
  },
  actions: {
    shareFile: (...args) => shareManagementStore?.shareFile(...args),
  },
}))

const {
  files,
  breadcrumbs,
  currentPath,
  sharedSingleFile,
  commentCounts,
  navigateUp,
  loadFiles,
  loadSharedContent,
  loadSharedProjectContent,
  navigateTo,
  goHome,
  goToFiles,
  clearFileMenu,
  getFilesAbortController,
} = fileBrowserStore.browser
const {
  getPackageErrorMessage,
  buildDownloadUrl,
  triggerBrowserDownload,
  getDownloadFilename,
  triggerBlobDownload,
  downloadZip,
  downloadFile,
} = fileBrowserStore.downloads
const {
  handleWindowDragOver,
  handleWindowDrop,
} = fileBrowserStore.uploads.project
const {
  getMediaDurationLabel,
  fetchBatchMediaInfo,
  prepareVersionPicker,
  openShotImportPicker,
  openDeliveryLogoPicker,
  getShotDurationLabel,
} = fileBrowserStore.picker

provideNavigationStore(createNavigationStore({
  session: sessionAuthStore,
  share: shareAccessContext,
  selection: projectTrackerSelectionStore,
  activeModule,
  currentMedia,
  currentPath,
  projectPath,
  artistWorkspaceRoot,
  sharedSingleFile,
  canReturnToCommentOrigin: viewerController.state.canReturnToCommentOrigin,
  returnToCommentOrigin: viewerController.media.returnToCommentOrigin,
  closeViewer,
  closeTracker: (...args) => trackerStore?.closeTracker(...args),
  closePage,
  restoreSharedPageRoot: () => {
    currentPage.value = currentProject.value?.page || currentPage.value
    applyProjectContentsSnapshot({ items: [], path: '', breadcrumbs: [], folderContext: {}, artistWorkspaceRoot: '' })
  },
  navigateProjectFolder,
  getParentProjectPath,
  goToProjects: () => appChromeStore?.goToProjects(),
  navigateUp,
}))

shareManagementStore = provideShareManagementStore(createShareManagementStore({
  route,
  activeModule,
  currentPath,
  currentProject,
  currentTracker,
  currentPage,
  projectPath,
  currentMedia,
  isAdmin,
  shareMode,
  sharePasswordRequired,
  shareAccessError,
  pendingShareId,
  pendingShareType,
  loadSharedContent,
  loadSharedProjectContent,
  handleError,
}))
const {
  shareProjectContent,
  shareProjectPage,
  canShareProjectItem,
} = shareManagementStore

appChromeStore = provideAppChromeStore(createAppChromeStore({
  route,
  router,
  activeModule,
  showMainContent,
  session: sessionAuthStore,
  share: shareAccessContext,
  dismissCurrentMedia: dismissCurrentMediaForNavigation,
  focusGlobalSearch: () => nextTick(() => globalSearchRef.value?.focusInput?.()),
}))
const {
  enableLowFx,
  isMobile,
  handleGlobalKeydown,
  handleViewportResize,
  updateLowFxMode,
} = appChromeStore

const trackerCanAssignShots = computed(() => Boolean(trackerStoreRef.value?.canAssignShots?.value))
const trackerControllerContext = {
  list: {
    statusOrder: STATUS_ORDER,
    statusColorMap: STATUS_COLOR_MAP,
    currentProject,
    currentTracker,
    currentUser,
    isAdmin,
    shareMode,
    canEditProject,
    canDeleteShots,
    showShotDownloads,
    assignmentCandidates: computed(() => projectSettingsStore?.assignmentCandidates?.value || []),
    loadProjectTeamOptions: (...args) => projectSettingsStore?.loadProjectTeamOptions?.(...args),
    getThumbnailUrl,
    loadTrackerBriefPreviews,
    formatStatus,
  },
}

projectSettingsStore = provideProjectSettingsStore(createProjectSettingsStore({
  currentProject,
  currentTracker,
  currentTrackerRef,
  currentPage,
  currentUser,
  isAdmin,
  canManageProjectContent,
  canCreateProjects,
  canDeleteProjects,
  shareMode,
  pendingShareId,
  appIdentity,
  route,
  router,
  projects,
  projectMenuOpen,
  canAssignShots: trackerCanAssignShots,
  getShareCredential,
  getProjectThumbnailUrl,
  loadProjects,
  refreshProjectContents,
  savePage,
  clonePageDraft,
  openDeliveryLogoPicker: () => openDeliveryLogoPicker(),
}))

const {
  projectSettingsTarget,
  canOpenProjectSettings,
  projectStorageRoots,
  newProjectStorageRoot,
  newProjectStoragePath,
  assignmentCandidates,
  canViewTrackerDetails,
  trackerToolEnabledForContext,
  showTrackerBriefPreview,
  versionReviewEnabled,
  showTrackerDeliveryMode,
  trackerDeliveryLinks,
  trackerDeliveryLogoUrl,
  trackerDeliveryMessage,
  trackerDeliveryNotes,
  deliveryTeamName,
  openProjectSettings,
  closeProjectSettingsModal,
  openProjectStorage,
  closeTrackerSettingsModal,
  selectTrackerSettingsDeliveryLogoFromNas,
  closeDashboardSettingsModal,
  openContextSettings,
  resetProjectTeamState,
  loadProjectTeamOptions,
} = projectSettingsStore

trackerControllerContext.workspace = {
  currentProject,
  currentTracker,
  currentPage,
  currentUser,
  isAdmin,
  currentTrackerRef,
  shareMode,
  pendingShareId,
  sharedItemType,
  canViewTrackerDetails,
  canEditDescription,
  canEditShotName,
  canDeleteShots,
  showShotDownloads,
  canEditProject,
  assignmentCandidates,
  getShareCredential,
  loadProjectTeamOptions,
  loadProjects,
  refreshProjectContents,
  commentCounts,
  router,
  openProject,
  closeTrackerSettingsModal,
  newTrackerName,
  showCreateTracker,
  handleError,
  getPackageErrorMessage,
  triggerBrowserDownload,
  buildDownloadUrl,
  getDownloadFilename,
  downloadZip,
  isProjectRenderPath,
}

trackerControllerContext.viewer = {
  getCurrentProject: () => currentProject.value,
  getCurrentTracker: () => currentTracker.value,
  getCurrentMedia: () => currentMedia.value,
  isShareMode: () => shareMode.value,
  canAddVersions: () => canAddVersions.value,
  canManageVersionPublication,
  buildDownloadUrl: (...args) => buildDownloadUrl(...args),
  dismissCurrentMedia: () => dismissCurrentMediaForNavigation(),
  openVideo,
  openImage,
  openPdf,
  prepareVersionPicker: (...args) => prepareVersionPicker(...args),
  currentProjectRef: currentProject,
  currentTrackerRef: currentTracker,
  currentMediaRef: currentMedia,
  shareModeRef: shareMode,
  isAdmin,
  isMobile,
  isViewingVideo,
  trackerToolEnabledForContext,
  getBriefMediaFile,
  sidebarTab,
  videoEl,
  isDrawingMode,
}

trackerControllerContext.presentation = {
  assignmentCandidates,
  canAddShots,
  canAddVersions,
  canDeleteShots,
  canEditShotName,
  canViewTrackerDetails,
  commentCounts,
  currentProject,
  currentTracker,
  deliveryLinks: trackerDeliveryLinks,
  deliveryLogoUrl: trackerDeliveryLogoUrl,
  deliveryMessage: trackerDeliveryMessage,
  deliveryNotes: trackerDeliveryNotes,
  deliveryTeamName,
  fetchBatchMediaInfo: (...args) => fetchBatchMediaInfo(...args),
  formatStatus,
  getBriefPreviewText,
  getLatestPreviewText,
  getMediaDurationLabel: (...args) => getMediaDurationLabel(...args),
  getShotDurationLabel,
  getThumbnailUrl,
  isAdmin,
  isBriefPreviewEmpty,
  isLatestPreviewEmpty,
  isMobile,
  openBriefVideo,
  openShotImportPicker: (...args) => openShotImportPicker(...args),
  projectThumbnailUrl: currentProjectDeliveryThumbnailUrl,
  shareMode,
  showBriefPreview: showTrackerBriefPreview,
  publicationControlsEnabled: computed(() => (
    canManageVersionPublication.value
    && (
      versionReviewEnabled.value
      || (currentTracker.value?.shots || []).some(shot => (
        (shot?.versions || []).some(version => ['pending', 'internal'].includes(
          String(version?.share_state || '').trim().toLowerCase(),
        ))
      ))
    )
  )),
  showDeliveryMode: showTrackerDeliveryMode,
  showShotDownloads,
}

trackerStore = provideTrackerStore(createTrackerStore(trackerControllerContext))
trackerStoreRef.value = trackerStore

provideActivityStore(createActivityStore({
  session: sessionAuthStore,
  share: shareAccessContext,
  selection: projectTrackerSelectionStore,
  workspace: projectWorkspaceController,
  tracker: trackerStore,
  viewer: viewerController,
}))

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

function handleKeydown(e) {
  if (e.code === 'Escape' && trackerStore.trackerViewerVersionSwitcherOpen.value) {
    trackerStore.dismissTrackerViewerVersionSwitcher()
    return
  }

  // Global: Escape key closes context menu
  if (e.code === 'Escape' && trackerStore.contextMenu.show) {
    trackerStore.closeContextMenu()
    return
  }

  const comparisonActive = trackerStore.versionCompareActive.value
  if (trackerStore.handleTrackerViewerKeydown(e, { disabled: comparisonActive })) return
  viewerController.actions.handleViewerKeydown(e, { disabled: comparisonActive })
}

const { handleRouteChange } = useAppRouting({
  route,
  router,
  shell: { loading, activeModule },
  session: sessionAuthStore,
  share: shareAccessContext,
  shareManagement: shareManagementStore,
  selection: projectTrackerSelectionStore,
  fileBrowser: fileBrowserStore,
  workspace: projectWorkspaceController,
  tracker: trackerStore,
  viewer: viewerController,
})

useAppBootstrapLifecycle({
  route,
  loadAppIdentity,
  updateLowFxMode,
  handleRouteChange,
  handleKeydown,
  handleGlobalKeydown,
  handleViewportResize,

  handleWindowDragOver: (event) => handleWindowDragOver(event),
  handleWindowDrop: (event) => handleWindowDrop(event),
  handleBeforeUnload: trackerStore.handleBeforeUnload,
  getFilesAbortController,
  getProjectContentsAbortController,
})

provideProjectWorkspaceStore(createProjectWorkspaceStore({
  ...projectWorkspaceController,
  currentProjectHeaderThumbnailUrl,
  canOpenProjectSettings,
  canViewTrackerDetails,
  openProjectSettings: openContextSettings,
  openRelocateProject: () => openProjectStorage(currentProject.value, 'relocate'),
  openRelinkMedia: () => openProjectStorage(currentProject.value, 'relink-media'),
  openMigrateProject: () => openProjectStorage(currentProject.value, 'migrate'),
  trackerTotalDuration: trackerStore.trackerTotalDuration,
  trackerTotalFrames: trackerStore.trackerTotalFrames,
  openTracker: trackerStore.openTracker,
  canShareProject: computed(() => canShareProjectItem(currentProject.value)),
  shareProjectContent,
  shareProjectPage,
  deleteTracker: trackerStore.deleteTracker,
  isMobile,
}))

provideViewerStore(createViewerStore({
  media: {
    state: viewerController.state,
    core: viewerController.media,
    stream: viewerController.stream,
    transport: viewerController.transport,
    annotations: viewerController.annotations,
    frames: viewerController.frames,
    colorPreview: viewerController.colorPreview,
    actions: viewerController.actions,
  },
  comparison: {
    active: trackerStore.versionCompareActive,
    mode: trackerStore.versionCompareMode,
    primaryMedia: trackerStore.versionComparePrimaryMedia,
    secondaryMedia: trackerStore.versionCompareSecondaryMedia,
    primaryLabel: trackerStore.versionComparePrimaryLabel,
    secondaryLabel: trackerStore.versionCompareSecondaryLabel,
    options: trackerStore.versionCompareOptions,
    primaryKey: trackerStore.versionComparePrimaryKey,
    secondaryKey: trackerStore.versionCompareSecondaryKey,
  },
  presentation: {
    isMobile,
    currentShot: trackerStore.currentTrackerViewerShot,
    canEditVersionSummary: trackerStore.canEditVersionSummaries,
    updateVersionSummary: trackerStore.updateCurrentTrackerViewerVersionSummary,
    canManageVersionPublication,
    versionReviewEnabled,
    updateVersionPublication: trackerStore.updateCurrentTrackerViewerVersionPublication,
    downloadCurrentMedia: () => downloadFile(currentMedia.value),
  },
  sidebar: {
    comments: viewerController.comments,
  },
  actions: {
    setPrimaryVersion: trackerStore.setVersionComparePrimary,
    setSecondaryVersion: trackerStore.setVersionCompareSecondary,
    exitVersionCompare: trackerStore.exitVersionCompare,
    closeAttachmentLightbox: viewerController.comments.closeAttachmentLightbox,
  },
}))


</script>

<style src="./assets/app.css"></style>
<style src="./assets/file-browser.css"></style>
