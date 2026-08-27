import { computed, inject, provide } from 'vue'

import { createBrowserContext, isAtRoot, parentContext } from '../lib/browserContext'

export const navigationStoreKey = Symbol('vueio.navigationStore')

export function createNavigationStore({
  session,
  share,
  selection,
  activeModule,
  currentMedia,
  currentPath,
  projectPath,
  artistWorkspaceRoot,
  sharedSingleFile,
  canReturnToCommentOrigin,
  returnToCommentOrigin,
  closeViewer,
  closeTracker,
  closePage,
  restoreSharedPageRoot,
  navigateProjectFolder,
  getParentProjectPath,
  goToProjects,
  navigateUp,
}) {
  const activeBrowserContext = computed(() => {
    const shareCredential = share.getShareCredential()
    if (share.shareMode.value && share.sharedItemType.value === 'folder' && selection.currentProject.value) {
      return createBrowserContext({
        kind: 'project-share',
        projectId: selection.currentProject.value?.id || '',
        shareId: share.pendingShareId.value || '',
        credential: shareCredential,
        rootPath: share.shareRoot.value || '',
        path: projectPath.value || share.shareRoot.value || '',
        permissions: { download: share.shareAllowDownload.value, upload: share.shareAllowUpload.value },
        shareKind: 'folder',
      })
    }
    if (share.shareMode.value && share.sharedItemType.value === 'folder') {
      return createBrowserContext({
        kind: 'nas-share',
        shareId: share.pendingShareId.value || '',
        credential: shareCredential,
        rootPath: share.shareRoot.value || '',
        path: currentPath.value || share.shareRoot.value || '',
        permissions: { download: share.shareAllowDownload.value, upload: share.shareAllowUpload.value },
      })
    }
    if (selection.currentProject.value) {
      return createBrowserContext({
        kind: share.shareMode.value ? 'project-share' : 'project-auth',
        projectId: selection.currentProject.value?.id || '',
        shareId: share.shareMode.value ? share.pendingShareId.value || '' : '',
        credential: share.shareMode.value ? shareCredential : null,
        rootPath: share.shareMode.value && share.sharedItemType.value === 'project' ? (share.shareRoot.value || '') : '',
        path: projectPath.value || '',
        permissions: { download: !share.shareMode.value || share.shareAllowDownload.value },
        shareKind: share.sharedItemType.value || '',
      })
    }
    return createBrowserContext({
      kind: share.shareMode.value ? 'nas-share' : 'nas-auth',
      shareId: share.shareMode.value ? share.pendingShareId.value || '' : '',
      credential: share.shareMode.value ? shareCredential : null,
      rootPath: share.shareMode.value ? share.shareRoot.value || '' : '',
      path: currentPath.value || '',
      permissions: { download: !share.shareMode.value || share.shareAllowDownload.value, upload: share.shareAllowUpload.value },
    })
  })

  const backTarget = computed(() => {
    if (canReturnToCommentOrigin?.value) return 'comment-origin'

    if (currentMedia.value) {
      return share.shareMode.value && sharedSingleFile.value ? null : 'viewer'
    }

    if (share.shareMode.value) {
      if (share.sharedItemType.value === 'page') {
        if (selection.currentPage.value) return null
        if (selection.currentTracker.value) return 'tracker'
        if (projectPath.value) return 'shared-page-root'
        return null
      }
      if (share.sharedItemType.value === 'tracker' && selection.currentTracker.value) return null
      if (share.sharedItemType.value === 'file') return null
      if (share.sharedItemType.value === 'project' && selection.currentTracker.value) return 'tracker'
      if (share.sharedItemType.value === 'project' && projectPath.value && !isAtRoot(activeBrowserContext.value)) {
        return 'project-parent'
      }
      if (share.sharedItemType.value === 'project' && !selection.currentTracker.value && !projectPath.value) return null
      if (share.sharedItemType.value === 'folder') {
        if (isAtRoot(activeBrowserContext.value)) return null
        return selection.currentProject.value ? 'shared-folder-parent' : 'files-parent'
      }
      return null
    }

    if (activeModule.value === 'projects') {
      if (selection.currentTracker.value) return 'tracker'
      if (selection.currentPage.value) return 'page'
      if (selection.currentProject.value) return projectPath.value ? 'project-parent' : 'projects'
      return null
    }

    if (activeModule.value === 'files' && currentPath.value) return 'files-parent'
    return null
  })

  const canGoBack = computed(() => Boolean(backTarget.value))

  function goBack() {
    switch (backTarget.value) {
      case 'comment-origin':
        void returnToCommentOrigin?.()
        break
      case 'viewer':
        closeViewer()
        break
      case 'tracker':
        closeTracker()
        break
      case 'page':
        closePage()
        break
      case 'shared-page-root':
        restoreSharedPageRoot()
        break
      case 'shared-folder-parent':
        navigateProjectFolder(parentContext(activeBrowserContext.value)?.path || share.shareRoot.value, { replaceRoute: true })
        break
      case 'project-parent':
        if (session.currentUser.value?.role === 'artist' && artistWorkspaceRoot.value && projectPath.value === artistWorkspaceRoot.value) {
          goToProjects()
          break
        }
        navigateProjectFolder(getParentProjectPath(), { replaceRoute: true })
        break
      case 'projects':
        goToProjects()
        break
      case 'files-parent':
        navigateUp()
        break
      default:
        break
    }
  }

  return { activeBrowserContext, backTarget, canGoBack, goBack }
}

export function provideNavigationStore(store) {
  provide(navigationStoreKey, store)
  return store
}

export function useNavigationStore() {
  const store = inject(navigationStoreKey, null)
  if (!store) throw new Error('Navigation store has not been provided')
  return store
}
