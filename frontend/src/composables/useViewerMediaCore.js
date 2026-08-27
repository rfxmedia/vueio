import { computed, ref, watch } from 'vue'
import api, { buildShareCredentialQuery } from '../lib/api'
import { appendCanonicalMediaRefs, getCanonicalMediaRefs, getMediaKind, hasCanonicalObjectRefs, normalizeMediaEntity, usesGeneratedImagePreview } from '../lib/mediaEntity'
import { useDocumentVisible } from './useDocumentVisible'

const STREAM_PREPARING_OVERLAY_DELAY_MS = 650
const STREAM_POLL_DELAYS_MS = [1000, 2000, 5000]

function normalizeMediaInput(input) {
  return normalizeMediaEntity(input)
}

function getSharedObjectRoute(shareId, media, suffix = 'file') {
  if (!shareId || !media) return ''
  if (!media._projectId && !media.is_project_file && !media._openedFromTracker) return ''
  const extra = {}
  if (media._cachedThumbnailOnly) extra.cached_only = 'true'
  const cacheBustToken = resolveThumbnailCacheBustToken(media)
  if (cacheBustToken !== null) extra.t = String(cacheBustToken === true ? Date.now() : cacheBustToken)
  const query = buildShareCredentialQuery(extra, {
    shareToken: media._shareToken || '',
  })
  const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
  if (shotVersionId) {
    return `/api/projects/shared/${shareId}/shot-versions/${shotVersionId}/${suffix}${query}`
  }
  if (mediaAssetId) {
    return `/api/projects/shared/${shareId}/media-assets/${mediaAssetId}/${suffix}${query}`
  }
  return ''
}

function hasProjectObjectRefs(media) {
  return hasCanonicalObjectRefs(media)
}

function shouldUseProjectScopedRoute(media) {
  return !!media?._projectId && (!!media?._projectFile || hasProjectObjectRefs(media))
}

function resolveThumbnailCacheBustToken(media, options = {}) {
  const token = options?.cacheBustToken
    ?? options?.thumbnailCacheBustToken
    ?? media?._thumbnailCacheBust
    ?? media?.thumbnail_refresh_token
    ?? media?.thumbnailRefreshToken
    ?? null
  if (token === null || token === undefined || token === false || token === '') return null
  return token
}

export function useViewerMediaCore(ctx) {
  const documentVisible = useDocumentVisible()
  const currentMedia = computed(() => ctx.currentVideo.value)
  const currentMediaKind = computed(() => getMediaKind(ctx.currentVideo.value))
  const isViewingImage = computed(() => currentMediaKind.value === 'image')
  const isViewingPdf = computed(() => currentMediaKind.value === 'pdf')
  const isViewingVideo = computed(() => currentMediaKind.value === 'video')
  const mediaInfo = computed(() => ctx.videoInfo.value)

  function getScopedShareAccessToken() {
    const token = ctx.shareAccessToken?.value || ''
    if (!token) return ''
    const scope = ctx.shareAccessTokenScope?.value
    if (!scope?.shareId) return token
    return scope.shareId === ctx.pendingShareId.value ? token : ''
  }

  function getShareCredential() {
    return {
      shareToken: getScopedShareAccessToken(),
    }
  }

  function buildViewerQuery(params, { includeShareId = false } = {}) {
    if (includeShareId && ctx.shareMode.value && ctx.pendingShareId.value) {
      params.set('share_id', ctx.pendingShareId.value)
    }
    return buildShareCredentialQuery(
      params,
      ctx.shareMode.value && ctx.pendingShareId.value ? getShareCredential() : {},
    )
  }

  function buildMediaParams(mediaInput) {
    const media = normalizeMediaInput(mediaInput)
    const params = new URLSearchParams()
    if (media?.path) params.set('path', media.path)
    appendCanonicalMediaRefs(params, media)

    if (!ctx.shareMode.value && shouldUseProjectScopedRoute(media) && media?._projectId) {
      params.set('project_id', media._projectId)
    }
    return params
  }

  function resolveViewerMediaRoutes(mediaInput) {
    const media = normalizeMediaInput(mediaInput)
    if (!media?.path) {
      return {
        fileUrl: '',
        manifestUrl: '',
        statusUrl: '',
      }
    }

    if (!ctx.shareMode.value && shouldUseProjectScopedRoute(media) && media._projectId) {
      const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
      if (shotVersionId) {
        const base = `/api/horizons/projects/${media._projectId}/shot-versions/${shotVersionId}`
        return {
          fileUrl: `${base}/file`,
          manifestUrl: `${base}/hls/manifest`,
          statusUrl: `${base}/hls/status`,
        }
      }
      if (mediaAssetId) {
        const base = `/api/horizons/projects/${media._projectId}/media-assets/${mediaAssetId}`
        return {
          fileUrl: `${base}/file`,
          manifestUrl: `${base}/hls/manifest`,
          statusUrl: `${base}/hls/status`,
        }
      }
    }

    if (ctx.shareMode.value && ctx.pendingShareId.value) {
      const shareToken = getScopedShareAccessToken()
      const sharedMedia = {
        ...media,
        _shareToken: shareToken,
      }
      const sharedFileUrl = getSharedObjectRoute(ctx.pendingShareId.value, sharedMedia, 'file')
      if (sharedFileUrl) {
        return {
          fileUrl: sharedFileUrl,
          manifestUrl: getSharedObjectRoute(ctx.pendingShareId.value, sharedMedia, 'hls/manifest'),
          statusUrl: getSharedObjectRoute(ctx.pendingShareId.value, sharedMedia, 'hls/status'),
        }
      }
      const query = buildViewerQuery(buildMediaParams(media))
      const base = `/api/projects/shared/${ctx.pendingShareId.value}`
      return {
        fileUrl: `${base}/file${query}`,
        manifestUrl: `${base}/hls/manifest${query}`,
        statusUrl: `${base}/hls/status${query}`,
      }
    }

    const query = buildViewerQuery(buildMediaParams(media))
    return {
      fileUrl: `/api/stream${query}`,
      manifestUrl: `/api/hls/manifest${query}`,
      statusUrl: `/api/hls/status${query}`,
    }
  }

  const currentViewerMediaRoutes = computed(() => resolveViewerMediaRoutes(ctx.currentVideo.value))
  const mediaStreamUrl = computed(() => {
    const media = normalizeMediaInput(ctx.currentVideo.value)
    if (usesGeneratedImagePreview(media)) {
      return getThumbnailUrl(media)
    }
    return currentViewerMediaRoutes.value.fileUrl
  })
  const videoManifestUrl = computed(() => (isViewingVideo.value ? currentViewerMediaRoutes.value.manifestUrl : ''))
  function isProjectRenderPath(path) {
    return !!ctx.currentProject.value?.id && typeof path === 'string' && path.startsWith('renders/')
  }

  function isProjectScopedPath(path) {
    if (!path || !ctx.currentProject.value?.id) return false
    if (isProjectRenderPath(path)) return true
    return !!ctx.currentTracker.value
  }

  function isHorizonsProject() {
    return ctx.currentProject.value?.source === 'horizons_db'
  }

  function maybeSetCachedThumbnailParam(params, options = {}) {
    if (options?.cachedOnly) params.set('cached_only', 'true')
    if (options?.variant) params.set('variant', String(options.variant))
    return params
  }

  function maybeSetThumbnailRouteParams(params, media, options = {}) {
    maybeSetCachedThumbnailParam(params, options)
    const cacheBustToken = resolveThumbnailCacheBustToken(media, options)
    if (cacheBustToken !== null) {
      params.set('t', String(cacheBustToken === true ? Date.now() : cacheBustToken))
    }
    return params
  }

  function getProjectThumbnailUrl(projectId, thumbnailPath, cacheBustToken = null, options = {}) {
    if (!projectId) return ''
    const params = new URLSearchParams({ entity_type: 'project' })
    if (cacheBustToken !== null && cacheBustToken !== undefined && cacheBustToken !== false) {
      params.set('t', String(cacheBustToken === true ? Date.now() : cacheBustToken))
    }
    maybeSetCachedThumbnailParam(params, options)
    return `/api/horizons/projects/${projectId}/thumbnail/resolved${buildViewerQuery(params, { includeShareId: true })}`
  }

  function getProjectFolderThumbnailUrl(folderPath, cacheBustToken = null) {
    const projectId = ctx.currentProject.value?.id
    if (!projectId || !folderPath) return ''
    const params = new URLSearchParams({ entity_type: 'folder', path: folderPath })
    if (cacheBustToken !== null && cacheBustToken !== undefined && cacheBustToken !== false) {
      params.set('t', String(cacheBustToken === true ? Date.now() : cacheBustToken))
    }
    return `/api/horizons/projects/${projectId}/thumbnail/resolved${buildViewerQuery(params, { includeShareId: true })}`
  }

  const projectHeaderThumbnailRefreshToken = ref(Date.now())

  function bumpProjectHeaderThumbnailRefresh() {
    projectHeaderThumbnailRefreshToken.value = Date.now()
  }

  const currentProjectHeaderThumbnailUrl = computed(() => {
    const projectId = ctx.currentProject.value?.id
    const thumbnailPath = ctx.currentProject.value?.thumbnail_path
    if (!projectId) return ''
    return getProjectThumbnailUrl(projectId, thumbnailPath, projectHeaderThumbnailRefreshToken.value)
  })

  const currentProjectDeliveryThumbnailUrl = computed(() => {
    const projectId = ctx.currentProject.value?.id
    const thumbnailPath = ctx.currentProject.value?.thumbnail_path
    if (!projectId || !thumbnailPath) return ''
    return getProjectThumbnailUrl(projectId, thumbnailPath, projectHeaderThumbnailRefreshToken.value, { variant: 'delivery' })
  })

  function getProjectFileThumbnailUrl(mediaInput, options = {}) {
    const projectId = ctx.currentProject.value?.id
    const media = normalizeMediaInput(mediaInput)
    if (!media?.path || !projectId) return ''
    const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
    if (ctx.shareMode.value && ctx.pendingShareId.value) {
      const shareToken = getScopedShareAccessToken()
      const sharedObjectUrl = getSharedObjectRoute(ctx.pendingShareId.value, {
        ...media,
        _projectId: projectId,
        _shareToken: shareToken,
        _cachedThumbnailOnly: !!options?.cachedOnly,
        _thumbnailCacheBust: resolveThumbnailCacheBustToken(media, options),
      }, 'thumbnail')
      if (sharedObjectUrl) return sharedObjectUrl
      if (media.is_linked) {
        const params = new URLSearchParams({ path: media.path })
        maybeSetThumbnailRouteParams(params, media, options)
        appendCanonicalMediaRefs(params, media)
        return `/api/projects/shared/${ctx.pendingShareId.value}/thumbnail${buildViewerQuery(params)}`
      }
    }
    if (media.is_linked && media.source_path && media.storage_scope !== 'project') {
      const params = maybeSetThumbnailRouteParams(new URLSearchParams({ path: media.source_path }), media, options)
      return `/api/thumbnail?${params.toString()}`
    }
    if (shotVersionId) {
      const params = maybeSetThumbnailRouteParams(new URLSearchParams(), media, options)
      const query = params.toString()
      return `/api/horizons/projects/${projectId}/shot-versions/${shotVersionId}/thumbnail${query ? `?${query}` : ''}`
    }
    if (mediaAssetId) {
      const params = maybeSetThumbnailRouteParams(new URLSearchParams(), media, options)
      const query = params.toString()
      return `/api/horizons/projects/${projectId}/media-assets/${mediaAssetId}/thumbnail${query ? `?${query}` : ''}`
    }
    if (isHorizonsProject()) return ''
    const params = new URLSearchParams({ path: media.path })
    maybeSetThumbnailRouteParams(params, media, options)
    appendCanonicalMediaRefs(params, media)
    return `/api/project-thumbnail/${projectId}/file${buildViewerQuery(params, { includeShareId: true })}`
  }

  function shouldUseProjectThumbnailRoute(mediaInput) {
    const media = normalizeMediaInput(mediaInput)
    if (!media?.path || !ctx.currentProject.value?.id) return false
    if (hasProjectObjectRefs(media)) return true
    if (media?._projectFile) return true
    if (media?._pickerSource && media._pickerSource !== 'project') return false
    return isProjectRenderPath(media.path)
  }

  function getThumbnailUrl(mediaInput, options = {}) {
    const media = normalizeMediaInput(mediaInput)
    if (!media?.path) return ''
    if (ctx.shareMode.value && ctx.pendingShareId.value) {
      const shareToken = getScopedShareAccessToken()
      const sharedObjectUrl = getSharedObjectRoute(ctx.pendingShareId.value, {
        ...media,
        _openedFromTracker: media._openedFromTracker || !!ctx.currentTracker.value,
        _shareToken: shareToken,
        _cachedThumbnailOnly: !!options?.cachedOnly,
        _thumbnailCacheBust: resolveThumbnailCacheBustToken(media, options),
      }, 'thumbnail')
      if (sharedObjectUrl) return sharedObjectUrl
      const params = new URLSearchParams({ path: media.path })
      maybeSetThumbnailRouteParams(params, media, options)
      appendCanonicalMediaRefs(params, media)
      return `/api/projects/shared/${ctx.pendingShareId.value}/thumbnail${buildViewerQuery(params)}`
    }
    if (shouldUseProjectThumbnailRoute(media)) {
      return getProjectFileThumbnailUrl(media, options)
    }
    if (media.is_linked && media.source_path) {
      const params = maybeSetThumbnailRouteParams(new URLSearchParams({ path: media.source_path }), media, options)
      appendCanonicalMediaRefs(params, media)
      return `/api/thumbnail?${params.toString()}`
    }
    const params = maybeSetThumbnailRouteParams(new URLSearchParams({ path: media.path }), media, options)
    appendCanonicalMediaRefs(params, media)
    return `/api/thumbnail?${params.toString()}`
  }

  const streamPreparing = ref(false)
  const showStreamPreparingOverlay = ref(false)
  const streamProgress = ref(0)
  let streamPollTimer = null
  let streamPollAttempt = 0
  let activeStreamStatusUrl = ''
  const completedStreamStatusUrls = new Set()
  let streamOverlayDelayTimer = null

  function clearStreamOverlayDelay() {
    if (!streamOverlayDelayTimer) return
    clearTimeout(streamOverlayDelayTimer)
    streamOverlayDelayTimer = null
  }

  function scheduleStreamOverlay() {
    clearStreamOverlayDelay()
    showStreamPreparingOverlay.value = false
    streamOverlayDelayTimer = setTimeout(() => {
      streamOverlayDelayTimer = null
      if (streamPreparing.value) {
        showStreamPreparingOverlay.value = true
      }
    }, STREAM_PREPARING_OVERLAY_DELAY_MS)
  }

  function clearStreamPolling({ resetActiveUrl = true, resetBackoff = true } = {}) {
    if (resetActiveUrl) activeStreamStatusUrl = ''
    if (resetBackoff) streamPollAttempt = 0
    if (!streamPollTimer) return
    clearTimeout(streamPollTimer)
    streamPollTimer = null
  }

  function resetStreamState() {
    clearStreamPolling()
    clearStreamOverlayDelay()
    streamPreparing.value = false
    showStreamPreparingOverlay.value = false
    streamProgress.value = 0
  }

  async function checkStreamStatus(mediaInput) {
    const media = normalizeMediaInput(mediaInput)
    if (!media?.path || media?.is_image || media?.is_pdf || media?.exists === false) {
      resetStreamState()
      return
    }

    const statusUrl = resolveViewerMediaRoutes(media).statusUrl
    if (!statusUrl) {
      resetStreamState()
      return
    }

    // A packaged stream never un-packages, so once a status URL has reported
    // complete the round-trip (and the preparing gate) is skipped on revisits.
    if (completedStreamStatusUrls.has(statusUrl)) {
      clearStreamPolling()
      clearStreamOverlayDelay()
      activeStreamStatusUrl = statusUrl
      streamPreparing.value = false
      showStreamPreparingOverlay.value = false
      streamProgress.value = 100
      return
    }

    clearStreamPolling()
    activeStreamStatusUrl = statusUrl
    streamPreparing.value = true
    scheduleStreamOverlay()
    streamProgress.value = 0

    try {
      const { data } = await api.get(statusUrl)
      if (activeStreamStatusUrl !== statusUrl) return
      const status = String(data?.status || '').toLowerCase()

      if (status === 'complete') {
        completedStreamStatusUrls.add(statusUrl)
        clearStreamPolling()
        clearStreamOverlayDelay()
        streamPreparing.value = false
        showStreamPreparingOverlay.value = false
        streamProgress.value = data?.progress || 100
        return
      }

      if (status === 'error') {
        clearStreamPolling()
        clearStreamOverlayDelay()
        streamPreparing.value = false
        showStreamPreparingOverlay.value = false
        streamProgress.value = 0
        ctx.handleStreamError?.(data)
        return
      }

      streamProgress.value = data?.progress || 0
      startStreamPolling(statusUrl, { resetBackoff: true })
    } catch (error) {
      console.warn('Stream status check failed')
      resetStreamState()
      ctx.handleStreamError?.(error)
    }
  }

  async function pollStreamStatus(statusUrl) {
    if (!documentVisible.value || activeStreamStatusUrl !== statusUrl) return

    try {
      const { data } = await api.get(statusUrl)
      if (activeStreamStatusUrl !== statusUrl) return
      streamProgress.value = data?.progress || 0
      const status = String(data?.status || '').toLowerCase()
      if (status === 'complete') {
        completedStreamStatusUrls.add(statusUrl)
        clearStreamPolling()
        clearStreamOverlayDelay()
        streamPreparing.value = false
        showStreamPreparingOverlay.value = false
        streamProgress.value = data?.progress || 100
        return
      }
      if (status === 'error') {
        clearStreamPolling()
        clearStreamOverlayDelay()
        streamPreparing.value = false
        showStreamPreparingOverlay.value = false
        streamProgress.value = 0
        ctx.handleStreamError?.(data)
        return
      }
    } catch {
      if (activeStreamStatusUrl !== statusUrl) return
      console.warn('Stream status poll failed')
    }

    streamPollAttempt = Math.min(streamPollAttempt + 1, STREAM_POLL_DELAYS_MS.length - 1)
    startStreamPolling(statusUrl)
  }

  function startStreamPolling(statusUrl, { resetBackoff = false } = {}) {
    clearStreamPolling({ resetActiveUrl: false, resetBackoff })
    activeStreamStatusUrl = statusUrl
    if (!documentVisible.value) return
    const delay = STREAM_POLL_DELAYS_MS[streamPollAttempt]
    streamPollTimer = setTimeout(() => {
      streamPollTimer = null
      void pollStreamStatus(statusUrl)
    }, delay)
  }

  watch(documentVisible, (visible) => {
    if (!activeStreamStatusUrl || !streamPreparing.value) return
    if (!visible) {
      clearStreamPolling({ resetActiveUrl: false, resetBackoff: false })
      return
    }
    void pollStreamStatus(activeStreamStatusUrl)
  })

  return {
    currentMedia,
    isViewingImage,
    isViewingPdf,
    isViewingVideo,
    mediaInfo,
    mediaStreamUrl,
    videoManifestUrl,
    resolveViewerMediaRoutes,
    getThumbnailUrl,
    isProjectRenderPath,
    isProjectScopedPath,
    getProjectThumbnailUrl,
    getProjectFolderThumbnailUrl,
    bumpProjectHeaderThumbnailRefresh,
    currentProjectHeaderThumbnailUrl,
    currentProjectDeliveryThumbnailUrl,
    getProjectFileThumbnailUrl,
    streamPreparing,
    showStreamPreparingOverlay,
    streamProgress,
    clearStreamPolling,
    checkStreamStatus,
    getStreamInterval: () => streamPollTimer,
  }
}
