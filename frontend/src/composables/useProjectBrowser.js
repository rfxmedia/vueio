import { computed, getCurrentInstance, getCurrentScope, onScopeDispose, onUnmounted, ref, shallowRef } from 'vue'
import api, { buildShareCredentialQuery, getApiErrorMessage, resolveAccessEndpoint } from '../lib/api'

import { useBrowserSession } from './useBrowserSession'
import { useBrowserRenderWindow } from './useBrowserRenderWindow'
import { useFileBrowserViewState } from './useFileBrowserViewState'
import {
  cloneProjectFolderContext,
  getParentBrowserPath,
  openBrowserMediaItem,
} from '../lib/browserSurface'
import { isFileBrowserFile, isFileBrowserFolder } from '../utils/fileBrowserItems'
import { isRestrictedProjectMember } from '../utils/accountAccess'
import {
  readWorkspacePayload,
  requestWorkspacePayload,
  workspaceCacheKey,
  writeWorkspacePayload,
} from '../lib/workspacePayloadCache'

export function useProjectBrowser({
  currentProject,
  getCurrentUser = () => null,
  shareMode,
  pendingShareId,
  shareAccessToken,
  shareAccessTokenScope,
  isRequestCanceledError = () => false,
  openImage,
  openPdf,
  openVideo,
  fileBrowserViewState: providedFileBrowserViewState = null,
  browserSession: providedBrowserSession = null,
}) {
  const projectContents = shallowRef([])
  const projectRootVueAssets = shallowRef({ projectId: '', items: null })
  const projectPath = ref('')
  const projectBreadcrumbs = ref([])
  const projectFolderContext = ref(cloneProjectFolderContext())
  const artistWorkspaceRoot = ref('')
  const projectContentsLoading = ref(false)
  const projectContentsError = ref('')
  const browserViewState = providedFileBrowserViewState || useFileBrowserViewState()
  const {
    viewMode,
    fileSortKey,
    fileSortDirection,
    setViewMode,
    chooseFileSort,
    toggleFileSort,
    toggleFileSortDirection,
    sortItems,
  } = browserViewState

  function workspaceFoldersFirst(items) {
    return [...items].sort((left, right) => Number(Boolean(right?.is_workspace)) - Number(Boolean(left?.is_workspace)))
  }

  function trackersByLatestActivity(items) {
    return [...items].sort((left, right) => {
      const leftActivity = Number(left?.last_activity_at || left?.updated_at || left?.created_at || 0)
      const rightActivity = Number(right?.last_activity_at || right?.updated_at || right?.created_at || 0)
      return rightActivity - leftActivity || String(left?.name || '').localeCompare(String(right?.name || ''))
    })
  }

  const projectShortcutTrackers = computed(() => trackersByLatestActivity(
    projectContents.value.filter((item) => item.is_shortcut && item.type === 'tracker'),
  ))
  const projectVueAssetItems = computed(() => (
    projectPath.value
      && Array.isArray(projectRootVueAssets.value.items)
      && projectRootVueAssets.value.projectId === currentProject.value?.id
      && !shareMode.value
      ? projectRootVueAssets.value.items
      : projectContents.value
  ))
  const projectPageItems = computed(() => projectVueAssetItems.value.filter((item) => item.type === 'page'))
  const projectFolderItems = computed(() => workspaceFoldersFirst(
    sortItems(projectContents.value.filter(isFileBrowserFolder)),
  ))
  const projectTrackerItems = computed(() => trackersByLatestActivity(
    projectVueAssetItems.value.filter((item) => item.type === 'tracker'),
  ))
  const projectFileItems = computed(() => sortItems(projectContents.value.filter(isFileBrowserFile)))
  const browserSession = providedBrowserSession || useBrowserSession()

  const {
    visibleItems: visibleProjectShortcutTrackers,
    canLoadMore: canLoadMoreProjectShortcutTrackers,
    resetRenderLimit: resetProjectShortcutTrackerRenderLimit,
    loadMoreItems: loadMoreProjectShortcutTrackers,
  } = useBrowserRenderWindow(projectShortcutTrackers, { batchSize: 60 })
  const {
    visibleItems: visibleProjectPageItems,
    canLoadMore: canLoadMoreProjectPages,
    resetRenderLimit: resetProjectPageRenderLimit,
    loadMoreItems: loadMoreProjectPages,
  } = useBrowserRenderWindow(projectPageItems, { batchSize: 60 })
  const {
    visibleItems: visibleProjectTrackerItems,
    canLoadMore: canLoadMoreProjectTrackers,
    resetRenderLimit: resetProjectTrackerRenderLimit,
    loadMoreItems: loadMoreProjectTrackers,
  } = useBrowserRenderWindow(projectTrackerItems, { batchSize: 60 })
  const {
    visibleItems: visibleProjectFileItems,
    canLoadMore: canLoadMoreProjectFiles,
    resetRenderLimit: resetProjectFileRenderLimit,
    loadMoreItems: loadMoreProjectFiles,
  } = useBrowserRenderWindow(projectFileItems, { batchSize: 200 })
  const {
    visibleItems: visibleProjectFolderItems,
    canLoadMore: canLoadMoreProjectFolders,
    resetRenderLimit: resetProjectFolderRenderLimit,
    loadMoreItems: loadMoreProjectFolders,
  } = useBrowserRenderWindow(projectFolderItems, { batchSize: 200 })
  const projectBrowserEntries = computed(() => workspaceFoldersFirst(sortItems([
    ...visibleProjectFolderItems.value,
    ...visibleProjectFileItems.value,
  ])))
  const projectShowUploader = computed(() => projectFileItems.value.some((item) => Boolean(item.uploaded_by || item.uploader_name)))

  let projectLoadToken = 0
  let disposed = false

  function resolveArtistWorkspaceRoot(snapshot) {
    const explicitRoot = snapshot?.artistWorkspaceRoot || ''
    if (explicitRoot) return explicitRoot
    if (isRestrictedProjectMember(getCurrentUser()) && artistWorkspaceRoot.value) {
      return artistWorkspaceRoot.value
    }
    return ''
  }

  function applyProjectContentsSnapshot(snapshot) {
    resetProjectFileRenderLimit()
    resetProjectFolderRenderLimit()
    resetProjectShortcutTrackerRenderLimit()
    resetProjectPageRenderLimit()
    resetProjectTrackerRenderLimit()
    projectContents.value = snapshot?.items || []
    projectPath.value = snapshot?.path || ''
    if (Array.isArray(snapshot?.rootVueAssets)) {
      projectRootVueAssets.value = { projectId: snapshot.projectId || '', items: snapshot.rootVueAssets }
    } else if (
      !shareMode.value
      && (
        !projectPath.value
        || (
          isRestrictedProjectMember(getCurrentUser())
          && projectPath.value === snapshot?.artistWorkspaceRoot
        )
      )
    ) {
      projectRootVueAssets.value = {
        projectId: snapshot?.projectId || '',
        items: projectContents.value.filter((item) => item.type === 'page' || item.type === 'tracker'),
      }
    }
    projectBreadcrumbs.value = snapshot?.breadcrumbs || []
    projectFolderContext.value = {
      ...cloneProjectFolderContext(),
      ...(snapshot?.folderContext || {}),
    }
    artistWorkspaceRoot.value = resolveArtistWorkspaceRoot(snapshot)
  }

  async function resolveProjectContentsSnapshot(projectId, path, controller) {
    const shareId = shareMode.value ? pendingShareId.value : null
    let credential = {}
    if (shareId) {
      const scope = shareAccessTokenScope?.value
      const scopedToken = shareAccessToken?.value && (!scope?.shareId || scope.shareId === pendingShareId.value)
        ? shareAccessToken.value
        : ''
      credential = { shareToken: scopedToken }
    }
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/contents`,
      authenticated: `/api/projects/${projectId}/contents`,
    })
    const query = buildShareCredentialQuery({ path, include_counts: true }, credential)
    const { data } = await api.get(`${endpoint}${query}`, { signal: controller.signal })

    if (!shareMode.value && isRestrictedProjectMember(getCurrentUser()) && !path) {
      const workspaceItem = (data.items || []).find((item) => item?.is_workspace && item.type === 'folder')
      if (workspaceItem?.path && workspaceItem.path !== path) {
        const nestedSnapshot = await resolveProjectContentsSnapshot(projectId, workspaceItem.path, controller)
        return {
          ...nestedSnapshot,
          artistWorkspaceRoot: workspaceItem.path,
        }
      }
    }

    return {
      items: data.items || [],
      projectId,
      path,
      breadcrumbs: data.breadcrumbs || [],
      folderContext: data.folder_context || {},
      artistWorkspaceRoot: '',
    }
  }

  async function loadProjectContents(projectId, path = '', options = {}) {
    const loadToken = ++projectLoadToken
    const userId = getCurrentUser()?.id || ''
    const cacheEnabled = !shareMode.value && Boolean(userId)
    const cacheKey = workspaceCacheKey(
      'contents',
      userId || 'uncached',
      projectId,
      path,
    )

    if (projectRootVueAssets.value.projectId && projectRootVueAssets.value.projectId !== projectId) {
      projectRootVueAssets.value = { projectId: '', items: null }
    }

    if (cacheEnabled && !options.force) {
      const cached = readWorkspacePayload(cacheKey)
      if (cached) {
        if (options.commit !== false) applyProjectContentsSnapshot(cached)
        void loadProjectContents(projectId, path, {
          ...options,
          commit: options.revalidateCommit ?? options.commit,
          force: true,
        })
        return cached
      }
    }

    projectContentsLoading.value = true
    projectContentsError.value = ''

    const abortFromCaller = () => browserSession.abort?.()
    options.signal?.addEventListener('abort', abortFromCaller, { once: true })
    if (options.signal?.aborted) abortFromCaller()
    try {
      const context = {
        kind: shareMode.value ? 'project-share' : 'project-auth',
        projectId: projectId || '',
        shareId: shareMode.value ? pendingShareId.value || '' : '',
        credential: shareMode.value
          ? {
              shareToken: shareAccessToken?.value && (!shareAccessTokenScope?.value?.shareId || shareAccessTokenScope.value.shareId === pendingShareId.value)
                ? shareAccessToken.value
                : '',
            }
          : null,
        path,
        permissions: { download: !shareMode.value },
      }
      const loadSnapshot = () => browserSession.switchContext(context, async (_context, { signal }) => {
        if (!path || shareMode.value || !getCurrentUser()) {
          return resolveProjectContentsSnapshot(projectId, path, { signal })
        }
        const rootAssetsAreCurrent = (
          Array.isArray(projectRootVueAssets.value.items)
          && projectRootVueAssets.value.projectId === projectId
          && !options.refreshRootAssets
        )
        if (rootAssetsAreCurrent) {
          return resolveProjectContentsSnapshot(projectId, path, { signal })
        }
        const [currentSnapshot, rootSnapshot] = await Promise.all([
          resolveProjectContentsSnapshot(projectId, path, { signal }),
          resolveProjectContentsSnapshot(projectId, '', { signal }).catch((error) => {
            if (isRequestCanceledError?.(error)) throw error
            console.warn('Failed to refresh project Vue assets')
            return null
          }),
        ])
        return {
          ...currentSnapshot,
          ...(rootSnapshot ? {
            rootVueAssets: rootSnapshot.items.filter((item) => item.type === 'page' || item.type === 'tracker'),
            artistWorkspaceRoot: currentSnapshot.artistWorkspaceRoot || rootSnapshot.artistWorkspaceRoot || '',
          } : {}),
        }
      })
      const snapshot = await (cacheEnabled
        ? requestWorkspacePayload(cacheKey, loadSnapshot)
        : loadSnapshot())
      if (!snapshot || disposed || loadToken !== projectLoadToken) return
      if (cacheEnabled) writeWorkspacePayload(cacheKey, snapshot)
      if (options.commit !== false) {
        applyProjectContentsSnapshot(snapshot)
      }
      return snapshot
    } catch (error) {
      if (isRequestCanceledError?.(error)) return
      if (disposed || loadToken !== projectLoadToken) return
      console.error('Failed to load project contents')
      if (options.commit !== false) {
        projectContentsError.value = getApiErrorMessage(error, 'Failed to load project folder.')
        return
      }
      throw error
    } finally {
      options.signal?.removeEventListener('abort', abortFromCaller)
      if (!disposed && loadToken === projectLoadToken) {
        projectContentsLoading.value = false
      }
    }
  }

  async function refreshProjectContents() {
    if (!currentProject.value) return
    await loadProjectContents(currentProject.value.id, projectPath.value, { refreshRootAssets: true })
  }

  async function navigateProjectFolder(path) {
    if (!currentProject.value) return
    await loadProjectContents(currentProject.value.id, path)
  }

  function getParentProjectPath() {
    return getParentBrowserPath(projectPath.value)
  }

  function openFileFromProject(item) {
    openBrowserMediaItem(item, {
      openImage,
      openPdf,
      openVideo,
      buildFileData: (value) => {
        return {
          path: value.path,
          name: value.name,
          source_path: value.source_path || null,
          is_linked: value.is_linked || false,
          _commentPath: value.path,
          _commentProjectId: currentProject.value?.id || null,
          needs_transcode: value.needs_transcode || false,
          size_formatted: value.size_formatted,
          is_image: value.is_image,
          is_video: value.is_video,
          is_pdf: value.is_pdf,
          media_asset_id: value.media_asset_id || null,
          horizons_media_asset_id: value.media_asset_id || value.horizons_media_asset_id || null,
          _projectFile: true,
          _projectId: currentProject.value?.id || null,
        }
      },
    })
  }

  function cleanup() {
    disposed = true
    projectLoadToken += 1
    browserSession.invalidate?.()
  }

  if (getCurrentInstance()) onUnmounted(cleanup)
  else if (getCurrentScope()) onScopeDispose(cleanup)

  return {
    projectContents,
    projectPath,
    projectBreadcrumbs,
    projectFolderContext,
    artistWorkspaceRoot,
    projectContentsLoading,
    projectContentsError,
    projectShortcutTrackers,
    projectPageItems,
    projectFolderItems,
    projectTrackerItems,
    projectFileItems,
    projectBrowserEntries,
    projectShowUploader,
    visibleProjectFolderItems,
    visibleProjectShortcutTrackers,
    canLoadMoreProjectShortcutTrackers,
    loadMoreProjectShortcutTrackers,
    visibleProjectPageItems,
    canLoadMoreProjectPages,
    loadMoreProjectPages,
    visibleProjectTrackerItems,
    canLoadMoreProjectTrackers,
    loadMoreProjectTrackers,
    canLoadMoreProjectFolders,
    loadMoreProjectFolders,
    visibleProjectFileItems,
    canLoadMoreProjectFiles,
    loadMoreProjectFiles,
    viewMode,
    fileSortKey,
    fileSortDirection,
    setViewMode,
    chooseFileSort,
    toggleFileSort,
    toggleFileSortDirection,
    loadProjectContents,
    refreshProjectContents,
    navigateProjectFolder,
    getParentProjectPath,
    openFileFromProject,
    applyProjectContentsSnapshot,
    getProjectContentsAbortController: () => browserSession.getAbortController?.(),
  }
}
