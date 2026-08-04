import { computed, getCurrentInstance, getCurrentScope, onScopeDispose, onUnmounted, ref, shallowRef, watch } from 'vue'
import api, { buildShareCredentialQuery, getApiErrorMessage } from '../lib/api'

import { useBrowserSession } from './useBrowserSession'
import { useBrowserRenderWindow } from './useBrowserRenderWindow'
import { useFileBrowserViewState } from './useFileBrowserViewState'
import { useShareAccess } from './useShareAccess'
import { buildCommentBatchTarget, chunkCommentTargets } from '../lib/commentTargets'
import { formatCountLabel, getParentBrowserPath, openBrowserMediaItem } from '../lib/browserSurface'
import { isFileBrowserEntry } from '../utils/fileBrowserItems'
import { notify } from '../utils/toasts'

const SHARED_IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'heic', 'heif', 'exr', 'dpx']
const SHARED_PDF_EXTS = ['pdf']
const SHARED_WEB_PLAYABLE_EXTS = ['mp4', 'webm', 'm4v']
const SHARED_VIDEO_EXTS = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'mxf', 'r3d', 'braw', 'prores', 'm4v']
const SHARED_PROJECT_IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'svg', 'exr', 'dpx']
const SHARED_PROJECT_VIDEO_EXTS = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'mxf', 'r3d', 'braw', 'prores']

export function useFileBrowser(ctx) {
  const files = shallowRef([])
  const breadcrumbs = ref([])
  const currentPath = ref('')
  const browserViewState = ctx.fileBrowserViewState || useFileBrowserViewState()
  const {
    viewMode,
    fileSortKey,
    fileSortDirection,
    setViewMode,
    toggleViewMode,
    chooseFileSort,
    toggleFileSort,
    toggleFileSortDirection,
    sortItems,
  } = browserViewState
  const sortedFiles = computed(() => sortItems(files.value))
  const fileMenuOpen = ref(null)
  const {
    visibleItems: visibleFiles,
    canLoadMore: canLoadMoreFiles,
    resetRenderLimit,
    loadMoreItems: loadMoreFiles,
  } = useBrowserRenderWindow(sortedFiles, { batchSize: 200 })
  const sharedSingleFile = ref(null)
  const commentCounts = ref({})
  const filesError = ref('')
  const browserSession = ctx.browserSession || useBrowserSession()
  const shareAccess = useShareAccess({
    shareAccessToken: ctx.shareAccessToken,
    pendingShareId: ctx.pendingShareId,
    pendingShareType: ctx.pendingShareType,
    shareAccessTokenScope: ctx.shareAccessTokenScope,
  })

  let filesLoadToken = 0
  let shareLoadToken = 0
  let disposed = false

  function normalizeBrowserPath(path) {
    return String(path || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').split('/').filter(Boolean).join('/')
  }

  function isPathInsideRoot(path, root) {
    const cleanPath = normalizeBrowserPath(path)
    const cleanRoot = normalizeBrowserPath(root)
    if (!cleanRoot) return true
    return cleanPath === cleanRoot || cleanPath.startsWith(`${cleanRoot}/`)
  }

  const canNavigateUp = computed(() => {
    if (ctx.shareMode.value) return currentPath.value && currentPath.value !== ctx.shareRoot.value
    return currentPath.value !== ''
  })

  function getParentPath() {
    return getParentBrowserPath(currentPath.value)
  }

  function navigateUp() {
    const parentPath = getParentPath()
    if (ctx.shareMode.value && ctx.shareRoot.value) {
      const cleanParent = normalizeBrowserPath(parentPath)
      const cleanRoot = normalizeBrowserPath(ctx.shareRoot.value)
      if (!isPathInsideRoot(cleanParent, cleanRoot)) {
        loadFiles(ctx.shareRoot.value)
        return
      }
    }
    loadFiles(parentPath)
  }

  function getScopedShareAccessToken(shareId = ctx.pendingShareId.value) {
    return shareAccess.scopedShareAccessToken(shareId)
  }

  function clearShareAccessToken() {
    shareAccess.clearShareAccessToken()
  }

  function resetCredentialsForShareRoute(shareId, password = null) {
    ctx.shareRequestFiles.value = false
    ctx.shareTargetLabel.value = ''
    if (password || (ctx.shareAccessToken?.value && !getScopedShareAccessToken(shareId))) {
      clearShareAccessToken()
    }
  }

  function getShareCredential(shareId = ctx.pendingShareId.value) {
    return shareAccess.getShareCredential({ shareId })
  }

  function isCurrentShareLoad(loadToken, shareId = ctx.pendingShareId.value) {
    return !disposed && loadToken === shareLoadToken && ctx.pendingShareId.value === shareId
  }

  function rememberShareAccessToken(payload, shareId = ctx.pendingShareId.value) {
    shareAccess.rememberShareAccessToken(payload, {
      shareId,
      shareType: ctx.pendingShareType.value || '',
    })
  }

  async function unlockShare(shareId, password, loadToken) {
    if (!password) return true
    const { data } = await api.post(
      `/api/share/${encodeURIComponent(shareId)}/unlock`,
      { password },
    )
    if (!isCurrentShareLoad(loadToken, shareId)) return false
    if (!data?.access_granted) {
      throw new Error('Share unlock did not establish access')
    }
    rememberShareAccessToken(data, shareId)
    return true
  }

  async function loadFiles(path = '') {
    const loadToken = ++filesLoadToken
    const expectedShareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    let commentCountsStarted = false
    ctx.loading.value = true
    filesError.value = ''

    try {
      const context = {
        kind: ctx.shareMode.value ? 'nas-share' : 'nas-auth',
        shareId: ctx.shareMode.value ? ctx.pendingShareId.value || '' : '',
        credential: ctx.shareMode.value ? getShareCredential() : null,
        rootPath: ctx.shareMode.value ? ctx.shareRoot.value || '' : '',
        path,
        permissions: {
          download: !ctx.shareMode.value || ctx.shareAllowDownload.value,
          upload: ctx.shareAllowUpload.value,
        },
      }
      const result = await browserSession.switchContext(context, async (_context, { signal }) => {
        const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
        const query = buildShareCredentialQuery(
          { path, include_counts: true, ...(shareId ? { share_id: shareId } : {}) },
          shareId ? getShareCredential(shareId) : {},
        )
        const response = await api.get(`/api/files${query}`, { signal })
        return {
          ...response.data,
          entries: response.data?.items || [],
          permissions: {
            download: !ctx.shareMode.value || ctx.shareAllowDownload.value,
            upload: response.data?._share_allow_upload ?? ctx.shareAllowUpload.value,
          },
        }
      })
      if (!result || disposed || loadToken !== filesLoadToken) return
      if (expectedShareId && ctx.pendingShareId.value !== expectedShareId) return

      resetRenderLimit()
      files.value = (result.items || result.entries || []).filter(isFileBrowserEntry)
      breadcrumbs.value = result.breadcrumbs || []
      currentPath.value = path
      if (ctx.shareMode.value) {
        ctx.shareAllowUpload.value = result._share_allow_upload || false
      }
      commentCounts.value = {}
      ctx.loading.value = false
      commentCountsStarted = true
      void loadCommentCounts(visibleFiles.value, browserSession.getAbortController?.(), loadToken)
    } catch (e) {
      if (ctx.isRequestCanceled?.(e)) return
      if (disposed || loadToken !== filesLoadToken) return
      console.error('Failed to load files')
      filesError.value = getApiErrorMessage(e, 'Failed to load files.')
    } finally {
      if (!disposed && loadToken === filesLoadToken) {
        ctx.loading.value = false
        if (!commentCountsStarted) browserSession.abort?.()
      }
    }
  }

  async function loadSharedContent(shareId, type, password = null, subPath = '') {
    const loadToken = ++shareLoadToken
    resetCredentialsForShareRoute(shareId, password)
    ctx.pendingShareId.value = shareId
    ctx.pendingShareType.value = type
    ctx.setShowLogin?.(false)
    try {
      if (!await unlockShare(shareId, password, loadToken)) return
    } catch (e) {
      if (!isCurrentShareLoad(loadToken, shareId)) return
      ctx.sharePasswordRequired.value = true
      ctx.shareAccessError.value = getApiErrorMessage(e, 'Invalid password')
      return
    }
    void browserSession.switchContext({
      kind: type === 'project' ? 'project-share' : 'nas-share',
      shareId,
      credential: getShareCredential(shareId),
      rootPath: '',
      path: subPath || '',
      shareKind: type,
    }, async () => ({ entries: [] })).catch(() => null)

    try {
      const query = buildShareCredentialQuery({}, getShareCredential(shareId))

      if (type === 'project') {
        const { data } = await api.get(`/api/projects/shared/${shareId}${query}`)
        if (!isCurrentShareLoad(loadToken, shareId)) return
        rememberShareAccessToken(data, shareId)
        ctx.shareMode.value = true
        ctx.shareRoot.value = ''
        ctx.sharePasswordRequired.value = false
        ctx.shareAllowDownload.value = data._share_allow_download || false
        ctx.shareAllowUpload.value = data._share_allow_upload || false
        ctx.activeModule.value = 'projects'
        ctx.currentProject.value = data

        if (data.shots) {
          data.shots.forEach(shot => { shot._originalId = shot.shot_id })
        }

        if (data._open_page && data.page) {
          ctx.sharedItemType.value = 'page'
          ctx.currentPage.value = data.page
          ctx.currentTracker.value = null
          ctx.applyProjectContentsSnapshot?.({ items: [], path: '', breadcrumbs: [], folderContext: {}, artistWorkspaceRoot: '' })
        } else if (data._open_tracker && data._current_tracker) {
          ctx.sharedItemType.value = 'tracker'
          ctx.currentPage.value = null
          ctx.currentTracker.value = {
            id: data._current_tracker_id || data._share_tracker_id || null,
            slug: data._current_tracker_slug || null,
            name: data._current_tracker,
            shots: data.shots || [],
            categories: data.categories || [],
            tags: data.tags || data.categories || [],
            nodeViewLayout: data.nodeViewLayout || {},
            settings: data.settings || {},
          }
          const trackerLoadContext = {
            shareId,
            guard: () => isCurrentShareLoad(loadToken, shareId),
          }
          await Promise.all([
            ctx.loadTrackerStats?.(data._current_tracker_id || data._current_tracker_slug || data._current_tracker, trackerLoadContext),
            ctx.loadTrackerActivity?.(data._current_tracker_id || data._current_tracker_slug || data._current_tracker, trackerLoadContext),
          ])
          if (!isCurrentShareLoad(loadToken, shareId)) return
        } else {
          ctx.sharedItemType.value = 'project'
          ctx.currentPage.value = null
          ctx.currentTracker.value = null
          await ctx.loadProjectContents?.(data.id, '')
          if (!isCurrentShareLoad(loadToken, shareId)) return
        }
        return
      }

      const { data } = await api.get(`/api/share/${shareId}${query}`)
      if (!isCurrentShareLoad(loadToken, shareId)) return
      rememberShareAccessToken(data, shareId)
      ctx.shareMode.value = true
      ctx.sharePasswordRequired.value = false
      ctx.shareRoot.value = data.path
      ctx.shareAllowDownload.value = data.allow_download || false
      ctx.shareAllowUpload.value = data.allow_upload || false
      ctx.shareRequestFiles.value = data.request_files || false
      ctx.shareTargetLabel.value = data.path?.split('/').filter(Boolean).at(-1) || 'Shared folder'

      if (data.is_folder) {
        ctx.sharedItemType.value = 'folder'
        sharedSingleFile.value = null
        if (ctx.shareRequestFiles.value) {
          ctx.activeModule.value = 'files'
          files.value = []
          currentPath.value = data.path
          return
        }
        const targetPath = subPath ? `${data.path}/${subPath}`.replace(/\/+/g, '/') : data.path
        await loadFiles(targetPath)
        if (!isCurrentShareLoad(loadToken, shareId)) return
        return
      }

      ctx.sharedItemType.value = 'file'
      sharedSingleFile.value = data.path
      const fileName = data.path.split('/').pop()
      const fileExt = fileName.split('.').pop().toLowerCase()
      const sharedMedia = {
        path: data.path,
        name: fileName,
        media_asset_id: data.media_asset_id || null,
        horizons_media_asset_id: data.media_asset_id || null,
      }

      if (SHARED_IMAGE_EXTS.includes(fileExt)) {
        ctx.openImage({ ...sharedMedia, is_image: true })
      } else if (SHARED_PDF_EXTS.includes(fileExt)) {
        ctx.openPdf({ ...sharedMedia, is_pdf: true })
      } else if (SHARED_VIDEO_EXTS.includes(fileExt)) {
        ctx.openVideo({
          ...sharedMedia,
          type: 'video',
          needs_transcode: !SHARED_WEB_PLAYABLE_EXTS.includes(fileExt)
        })
      } else {
        window.open(
          `/api/projects/shared/${encodeURIComponent(shareId)}/download${buildShareCredentialQuery({ path: data.path }, getShareCredential(shareId))}`,
          '_blank',
          'noopener,noreferrer',
        )
      }
    } catch (e) {
      if (!isCurrentShareLoad(loadToken, shareId)) return
      if (e.response?.status === 401) {
        ctx.sharePasswordRequired.value = true
        ctx.shareAccessError.value = getApiErrorMessage(e, 'Password required')
      } else if (e.response?.status === 403) {
        ctx.shareAccessError.value = getApiErrorMessage(e, 'This share link is no longer valid')
        ctx.sharePasswordRequired.value = true
      } else {
        console.error('Failed to load shared content')
        ctx.shareAccessError.value = 'Failed to load shared content'
        ctx.sharePasswordRequired.value = true
      }
    }
  }

  async function loadSharedProjectContent(shareId, subPath = '', password = null) {
    const loadToken = ++shareLoadToken
    resetCredentialsForShareRoute(shareId, password)
    ctx.pendingShareId.value = shareId
    ctx.pendingShareType.value = 'project-file'
    try {
      if (!await unlockShare(shareId, password, loadToken)) return
    } catch (e) {
      if (!isCurrentShareLoad(loadToken, shareId)) return
      ctx.sharePasswordRequired.value = true
      ctx.shareAccessError.value = getApiErrorMessage(e, 'Invalid password')
      return
    }
    void browserSession.switchContext({
      kind: 'project-share',
      shareId,
      credential: getShareCredential(shareId),
      rootPath: subPath || '',
      path: subPath || '',
      shareKind: 'folder',
    }, async () => ({ entries: [] })).catch(() => null)

    try {
      const query = buildShareCredentialQuery({}, getShareCredential(shareId))
      const { data: info } = await api.get(`/api/projects/shared/${shareId}/info${query}`)
      if (!isCurrentShareLoad(loadToken, shareId)) return
      rememberShareAccessToken(info, shareId)

      ctx.shareMode.value = true
      ctx.sharePasswordRequired.value = false
      ctx.shareAllowDownload.value = info.allow_download || false
      ctx.shareAllowUpload.value = info.allow_upload || false
      ctx.shareRequestFiles.value = info.request_files || false
      ctx.shareTargetLabel.value = info.path?.split('/').filter(Boolean).at(-1) || info.project_title || 'Shared folder'
      ctx.shareRoot.value = info.is_folder ? (info.path || '') : ''
      ctx.currentProject.value = {
        id: info.project_id,
        title: info.project_title,
        thumbnail_path: info.thumbnail_path || null,
        source: info.project_source || null,
        _shared: true,
      }
      ctx.currentTracker.value = null
      ctx.currentPage.value = null
      ctx.activeModule.value = ctx.shareRequestFiles.value ? 'files' : 'projects'

      if (info.is_folder) {
        const targetPath = subPath || info.path
        ctx.sharedItemType.value = 'folder'
        sharedSingleFile.value = null
        if (ctx.shareRequestFiles.value) {
          files.value = []
          currentPath.value = targetPath
          return
        }
        await ctx.loadProjectContents?.(info.project_id, targetPath)
        if (!isCurrentShareLoad(loadToken, shareId)) return
        return
      }

      ctx.sharedItemType.value = 'file'
      sharedSingleFile.value = info.path
      const fileName = info.path.split('/').pop()
      const fileExt = fileName.split('.').pop().toLowerCase()

      const sharedProjectMedia = {
        path: info.path,
        name: fileName,
        is_project_file: true,
        project_share_id: shareId,
        media_asset_id: info.media_asset_id || null,
        horizons_media_asset_id: info.media_asset_id || null,
        horizons_shot_version_id: info.horizons_shot_version_id || null,
        version_id: info.horizons_shot_version_id || null,
      }

      if (SHARED_PROJECT_IMAGE_EXTS.includes(fileExt)) {
        ctx.openImage({
          ...sharedProjectMedia,
          is_image: true,
        })
      } else if (SHARED_PDF_EXTS.includes(fileExt)) {
        ctx.openPdf({
          ...sharedProjectMedia,
          is_pdf: true,
        })
      } else if (SHARED_PROJECT_VIDEO_EXTS.includes(fileExt)) {
        ctx.openVideo({
          ...sharedProjectMedia,
          type: 'video',
          needs_transcode: !SHARED_WEB_PLAYABLE_EXTS.includes(fileExt)
        })
      } else {
        if (info.horizons_shot_version_id) {
          window.open(
            `/api/projects/shared/${encodeURIComponent(shareId)}/shot-versions/${encodeURIComponent(info.horizons_shot_version_id)}/download${buildShareCredentialQuery({}, getShareCredential(shareId))}`,
            '_blank',
            'noopener,noreferrer',
          )
        } else if (info.media_asset_id) {
          window.open(
            `/api/projects/shared/${encodeURIComponent(shareId)}/media-assets/${encodeURIComponent(info.media_asset_id)}/download${buildShareCredentialQuery({}, getShareCredential(shareId))}`,
            '_blank',
            'noopener,noreferrer',
          )
        } else {
          window.open(
            `/api/projects/shared/${encodeURIComponent(shareId)}/download${buildShareCredentialQuery({ path: info.path }, getShareCredential(shareId))}`,
            '_blank',
            'noopener,noreferrer',
          )
        }
      }
    } catch (e) {
      if (!isCurrentShareLoad(loadToken, shareId)) return
      if (e.response?.status === 401) {
        ctx.sharePasswordRequired.value = true
        ctx.shareAccessError.value = getApiErrorMessage(e, 'Password required')
      } else if (e.response?.status === 403) {
        ctx.shareAccessError.value = getApiErrorMessage(e, 'This share link is no longer valid')
        ctx.sharePasswordRequired.value = true
      } else {
        console.error('Failed to load shared project content')
        ctx.shareAccessError.value = 'Failed to load shared content'
        ctx.sharePasswordRequired.value = true
      }
    }
  }

  async function loadCommentCounts(items, controller = null, loadToken = null) {
    const targets = items
      .filter(item => !item.is_folder && (item.type === 'video' || item.type === 'image'))
      .map(item => buildCommentBatchTarget({
        path: item.path,
        horizons_media_asset_id: item.media_asset_id || item.horizons_media_asset_id || null,
        horizons_shot_version_id: item.horizons_shot_version_id || item.version_id || null,
      }))
      .filter(target => target.path && commentCounts.value[target.key] === undefined)

    if (targets.length === 0) {
      return
    }

    try {
      const merged = {}
      for (const chunk of chunkCommentTargets(targets)) {
        const body = { targets: chunk }
        const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
        const query = buildShareCredentialQuery(
          shareId ? { share_id: shareId } : {},
          shareId ? getShareCredential(shareId) : {},
        )
        const requestOptions = controller ? { signal: controller.signal } : {}
        const { data } = await api.post(`/api/comments/counts/batch${query}`, body, requestOptions)
        if (controller && browserSession.getAbortController?.() !== controller) return
        if (loadToken !== null && loadToken !== filesLoadToken) return
        for (const item of data?.items || []) {
          if (!item?.key) continue
          merged[item.key] = item.count || 0
        }
      }
      if (controller && browserSession.getAbortController?.() !== controller) return
      if (loadToken !== null && loadToken !== filesLoadToken) return
      commentCounts.value = { ...commentCounts.value, ...merged }
    } catch (e) {
      if (ctx.isRequestCanceled?.(e)) return
      console.error('Failed to load comment counts')
    } finally {
      if (controller && browserSession.getAbortController?.() === controller) browserSession.abort?.()
    }
  }

  function handleClick(item) {
    if (item.type === 'folder') {
      navigateTo(item.path)
      return
    }

    openBrowserMediaItem(item, {
      openImage: ctx.openImage,
      openPdf: ctx.openPdf,
      openVideo: ctx.openVideo,
      buildFileData: (value) => ({
        ...value,
        is_image: value.type === 'image' || value.is_image,
        is_pdf: value.is_pdf || value.extension?.toLowerCase() === 'pdf',
      }),
    })
  }

  function navigateTo(path) {
    if (ctx.shareMode.value) {
      if (ctx.shareRoot.value && !isPathInsideRoot(path, ctx.shareRoot.value)) return
      const cleanPath = normalizeBrowserPath(path)
      const cleanRoot = normalizeBrowserPath(ctx.shareRoot.value)
      const relativePath = cleanRoot && cleanPath.startsWith(`${cleanRoot}/`) ? cleanPath.slice(cleanRoot.length + 1) : (cleanPath === cleanRoot ? '' : cleanPath)
      ctx.router.push({ name: 'shared-nas', params: { shareId: ctx.pendingShareId.value, path: relativePath.split('/').filter(Boolean) } })
      return
    }

    ctx.router.push({ name: 'files', params: { path: path.split('/').filter(Boolean) } })
  }

  function goHome() {
    if (ctx.shareMode.value) {
      if (ctx.currentProject.value && ctx.pendingShareId.value) {
        ctx.router.push({ name: 'shared-project', params: { shareId: ctx.pendingShareId.value } })
      } else if (ctx.shareRoot.value && ctx.pendingShareId.value) {
        ctx.router.push({ name: 'shared-nas', params: { shareId: ctx.pendingShareId.value, path: [] } })
      }
      return
    }

    ctx.dismissCurrentMediaForNavigation?.()
    if (ctx.canAccessFileBrowser?.()) {
      ctx.router.push('/files')
    } else if (ctx.canAccessProjectManager?.()) {
      ctx.router.push('/projects')
    }
  }

  function goToFiles() {
    ctx.dismissCurrentMediaForNavigation?.()
    if (ctx.route.path !== '/files') {
      ctx.router.push('/files')
    }
  }

  function clearFileMenu() {
    fileMenuOpen.value = null
  }

  function toggleFileMenu(item) {
    fileMenuOpen.value = fileMenuOpen.value === item.path ? null : item.path
  }

  async function regenerateThumbnail(item) {
    fileMenuOpen.value = null
    try {
      const { data } = await api.delete('/api/thumbnail', { params: { path: item.path } })

      if (data.status === 'regenerated') {
        loadFiles(currentPath.value)
        notify('Thumbnail regenerated successfully!')
      } else if (data.status === 'deleted_but_regeneration_failed') {
        notify('Old thumbnail deleted, but regeneration failed.\n\nThe video file may be:\n• Still rendering/exporting\n• Corrupted or incomplete\n• In an unsupported format\n\nTry again after the export completes.')
      } else {
        notify('No thumbnail found to delete. The video may not have been thumbnailed yet.')
      }
    } catch (e) {
      notify(`Failed to regenerate thumbnail: ${getApiErrorMessage(e)}`)
    }
  }

  watch(
    visibleFiles,
    (items) => {
      if (!items?.length || browserSession.getAbortController?.()) return
      void loadCommentCounts(items, null, filesLoadToken)
    },
    { flush: 'post' },
  )

  function cleanup() {
    disposed = true
    filesLoadToken += 1
    shareLoadToken += 1
    browserSession.invalidate?.()
  }

  if (getCurrentInstance()) onUnmounted(cleanup)
  else if (getCurrentScope()) onScopeDispose(cleanup)

  return {
    files,
    breadcrumbs,
    currentPath,
    viewMode,
    fileSortKey,
    fileSortDirection,
    fileMenuOpen,
    visibleFiles,
    canLoadMoreFiles,
    sharedSingleFile,
    commentCounts,
    filesError,
    canNavigateUp,
    loadMoreFiles,
    setViewMode,
    toggleViewMode,
    chooseFileSort,
    toggleFileSort,
    toggleFileSortDirection,
    formatCountLabel,
    navigateUp,
    loadFiles,
    loadSharedContent,
    loadSharedProjectContent,
    handleClick,
    navigateTo,
    goHome,
    goToFiles,
    clearFileMenu,
    toggleFileMenu,
    regenerateThumbnail,
    getFilesAbortController: () => browserSession.getAbortController?.(),
  }
}
