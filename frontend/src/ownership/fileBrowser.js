import { computed, inject, provide } from 'vue'

import { useBrowserDownloads } from '../composables/useBrowserDownloads'
import { useFileBrowser } from '../composables/useFileBrowser'
import { useFilePickerModal } from '../composables/useFilePickerModal'
import { usePageResourceController } from '../composables/usePageResourceController'
import { useThumbnailEditor } from '../composables/useThumbnailEditor'
import { useUploadController } from '../composables/useUploadController'
import { buildShareCredentialQuery } from '../lib/api'

export const fileBrowserStoreKey = Symbol('vueio.fileBrowserStore')

export function createFileBrowserStore(ctx) {
  if (!ctx?.shell || !ctx?.session || !ctx?.share || !ctx?.selection || !ctx?.workspace || !ctx?.viewer || !ctx?.tracker || !ctx?.settings || !ctx?.actions) {
    throw new TypeError('File browser shell, session, share, selection, workspace, viewer, tracker, settings, and action contexts are required')
  }

  const { shell, session, share, selection, workspace, viewer, tracker } = ctx

  const browser = useFileBrowser({
    fileBrowserViewState: ctx.fileBrowserViewState,
    browserSession: ctx.browserSession,
    router: ctx.router,
    route: ctx.route,
    loading: shell.loading,
    activeModule: shell.activeModule,
    shareMode: share.shareMode,
    shareRoot: share.shareRoot,
    shareAllowDownload: share.shareAllowDownload,
    shareAllowUpload: share.shareAllowUpload,
    shareRequestFiles: share.shareRequestFiles,
    shareTargetLabel: share.shareTargetLabel,
    sharePasswordRequired: share.sharePasswordRequired,
    shareAccessToken: share.shareAccessToken,
    shareAccessTokenScope: share.shareAccessTokenScope,
    rememberShareAccessToken: share.rememberShareAccessToken,
    pendingShareId: share.pendingShareId,
    pendingShareType: share.pendingShareType,
    shareAccessError: share.shareAccessError,
    sharedItemType: share.sharedItemType,
    currentVideo: viewer.currentVideo,
    currentProject: selection.currentProject,
    currentTracker: selection.currentTracker,
    currentPage: selection.currentPage,
    projectContents: workspace.projectContents,
    projectPath: workspace.projectPath,
    isRequestCanceled: ctx.isRequestCanceled,
    loadProjectContents: workspace.loadProjectContents,
    applyProjectContentsSnapshot: workspace.applyProjectContentsSnapshot,
    loadTrackerStats: (...args) => tracker.loadTrackerStats(...args),
    loadTrackerActivity: (...args) => tracker.loadTrackerActivity(...args),
    openImage: viewer.openImage,
    openPdf: viewer.openPdf,
    openVideo: viewer.openVideo,
    dismissCurrentMediaForNavigation: viewer.dismissCurrentMediaForNavigation,
    setShowLogin: value => { session.showLogin.value = value },
    canAccessFileBrowser: () => session.canAccessFileBrowser.value,
    canAccessProjectManager: () => session.canAccessProjectManager.value,
  })

  const downloads = useBrowserDownloads({
    shareMode: share.shareMode,
    pendingShareId: share.pendingShareId,
    shareAllowDownload: share.shareAllowDownload,
    sharedItemType: share.sharedItemType,
    shareRoot: share.shareRoot,
    currentPath: browser.currentPath,
    files: browser.files,
    currentProject: selection.currentProject,
    projectPath: workspace.projectPath,
    projectFolderItems: workspace.projectFolderItems,
    projectFileItems: workspace.projectFileItems,
    isProjectScopedPath: viewer.isProjectScopedPath,
    getShareCredential: share.getShareCredential,
  })

  const projectUploadDisabledReason = computed(() => {
    if (share.shareMode.value) return 'Uploads are disabled while viewing a share.'
    if (!selection.currentProject.value) return 'Select a project before uploading files.'
    if (selection.currentProject.value.storage_read_only) return 'This project storage location is read-only.'
    if (workspace.projectFolderContext.value?.is_linked_folder) {
      return workspace.projectFolderContext.value?.upload_disabled_reason || 'Uploads are disabled inside linked NAS folders.'
    }
    if (workspace.projectFolderContext.value?.can_upload) return ''
    if (!session.canEditProject.value) return 'You can only upload inside your workspace on this project.'
    return ''
  })
  const canUploadToProject = computed(() => !projectUploadDisabledReason.value)

  const projectUpload = useUploadController({
    canUpload: canUploadToProject,
    disabledReason: projectUploadDisabledReason,
    getDefaultTargetPath: () => workspace.projectPath.value || '',
    getTargetLabel: targetPath => String(targetPath || '').split('/').filter(Boolean).at(-1) || 'Project root',
    getUploadEndpoint: (suffix = '') => selection.currentProject.value?.id
      ? `/api/projects/${selection.currentProject.value.id}/uploads${suffix}`
      : '',
    missingTargetMessage: 'No project selected',
    getUploaderName: () => (
      session.currentUser.value?.display_name
      || session.currentUser.value?.username
      || session.currentUser.value?.name
      || 'Project uploader'
    ),
    refreshContents: workspace.refreshProjectContents,
  })

  let picker
  let sharedUpload
  const pageResources = usePageResourceController({
    currentProject: selection.currentProject,
    currentPage: selection.currentPage,
    clonePageDraft: workspace.clonePageDraft,
    savePage: workspace.savePage,
    openPicker: () => picker.openPageResourcePicker(),
    openProjectUpload: (targetPath, options) => projectUpload.openUpload({ ...options, targetPath }),
    openSharedUpload: () => sharedUpload.openUploadModal(),
  })

  const isSharedPageUpload = computed(() => (
    share.shareMode.value && shell.activeModule.value === 'projects' && share.sharedItemType.value === 'page'
  ))
  const isFileRequestUpload = computed(() => share.shareMode.value && share.shareRequestFiles.value)
  function getSharedUploadTargetPath() {
    return isSharedPageUpload.value
      ? pageResources.sharedPageUploadTarget.value || ''
      : browser.currentPath.value || share.shareRoot.value || ''
  }
  const sharedUploadDisabledReason = computed(() => {
    if (!share.shareMode.value) return 'Uploads are only available inside shared folders.'
    if (shell.activeModule.value !== 'files' && !isSharedPageUpload.value && !isFileRequestUpload.value) return 'Uploads are only available inside shared folders.'
    if (!share.pendingShareId.value) return 'Missing share link.'
    if (!share.shareAllowUpload.value) return 'Uploads are disabled for this share.'
    return ''
  })
  const canUploadToSharedFolder = computed(() => !sharedUploadDisabledReason.value)

  sharedUpload = useUploadController({
    canUpload: canUploadToSharedFolder,
    disabledReason: sharedUploadDisabledReason,
    getDefaultTargetPath: getSharedUploadTargetPath,
    getTargetLabel: targetPath => (
      String(targetPath || '').split('/').filter(Boolean).at(-1)
      || (isSharedPageUpload.value ? 'Upload inbox' : 'Shared folder')
    ),
    getUploadEndpoint: (suffix = '') => share.pendingShareId.value
      ? `/api/share/${share.pendingShareId.value}/uploads${suffix}${buildShareCredentialQuery({}, share.getShareCredential())}`
      : '',
    missingTargetMessage: 'Missing share link',
    refreshContents: async () => {
      if (isFileRequestUpload.value) return
      if (isSharedPageUpload.value) {
        await workspace.refreshCurrentPage()
        return
      }
      await browser.loadFiles(browser.currentPath.value || share.shareRoot.value || '')
    },
    requiresUploaderName: true,
    uploaderNameStorageKey: () => share.pendingShareId.value
      ? `vueio-share-upload-name:${share.pendingShareId.value}`
      : '',
  })

  const thumbnails = useThumbnailEditor({
    currentProject: selection.currentProject,
    currentPath: browser.currentPath,
    projectSettingsTarget: ctx.settings.projectSettingsTarget,
    getThumbnailUrl: viewer.getThumbnailUrl,
    getProjectFolderThumbnailUrl: viewer.getProjectFolderThumbnailUrl,
    bumpProjectHeaderThumbnailRefresh: viewer.bumpProjectHeaderThumbnailRefresh,
    loadProjects: workspace.loadProjects,
    refreshProjectContents: workspace.refreshProjectContents,
    loadFiles: browser.loadFiles,
    openThumbnailPicker: () => picker.openThumbnailPicker(),
  })

  picker = useFilePickerModal({
    canAddShots: session.canAddShots,
    canAddVersions: session.canAddVersions,
    currentUser: session.currentUser,
    currentProject: selection.currentProject,
    currentTracker: selection.currentTracker,
    trackerShotsForDisplay: tracker.trackerShotsForDisplay,
    projectPath: workspace.projectPath,
    getLatestShotFilePath: tracker.getLatestShotFilePath,
    formatTimecode: viewer.formatTimecode,
    refreshCurrentTrackerPreserveState: (...args) => tracker.refreshCurrentTrackerPreserveState(...args),
    refreshProjectContents: workspace.refreshProjectContents,
    onPageResourcePicked: pageResources.handlePageResourcePicked,
    onThumbnailSourcePicked: thumbnails.selectThumbnailSource,
    onDeliveryLogoSourcePicked: item => ctx.settings.selectDeliveryLogoSource(item),
  })

  function handleProjectExternalDrop(event, targetFolder = '') {
    return projectUpload.handleExternalDrop(event, targetFolder || workspace.projectPath.value || '')
  }

  function handleSharedExternalDrop(event) {
    return sharedUpload.handleExternalDrop(event, getSharedUploadTargetPath())
  }

  function openBrowserFolderThumb(item) {
    browser.clearFileMenu()
    thumbnails.openBrowserFolderThumb(item)
  }

  return Object.freeze({
    shell: Object.freeze({
      showMainContent: shell.showMainContent,
      activeModule: shell.activeModule,
      loading: shell.loading,
    }),
    browser,
    downloads,
    uploads: Object.freeze({
      project: {
        ...projectUpload,
        canUploadToProject,
        projectUploadDisabledReason,
        handleProjectExternalDrop,
      },
      shared: {
        ...sharedUpload,
        canUploadToSharedFolder,
        sharedUploadDisabledReason,
        handleSharedExternalDrop,
      },
    }),
    picker: {
      ...picker,
      getShotDurationLabel: shot => picker.getMediaDurationLabel(tracker.getLatestShotFilePath(shot)),
    },
    thumbnails: { ...thumbnails, openBrowserFolderThumb },
    pageResources,
    actions: Object.freeze({
      shareFile: (...args) => ctx.actions.shareFile(...args),
    }),
  })
}

export function provideFileBrowserStore(store) {
  provide(fileBrowserStoreKey, store)
  return store
}

export function useFileBrowserStore() {
  const store = inject(fileBrowserStoreKey, null)
  if (!store) throw new Error('File browser store has not been provided')
  return store
}
