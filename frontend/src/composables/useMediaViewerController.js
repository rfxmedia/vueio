import { computed, getCurrentScope, nextTick, onScopeDispose, ref, watch } from 'vue'

import api, { buildShareCredentialQuery, resolveAccessEndpoint } from '../lib/api'
import { getCanonicalMediaRefs, getMediaKind, normalizeMediaEntity } from '../lib/mediaEntity'
import { normalizeVideoColorPreviewMode, VIDEO_COLOR_PREVIEW_OPTIONS } from '../lib/videoColorPreview'
import { formatSizeBytes, formatTimecodeWithFrames } from '../utils/formatters'
import { useMediaComments } from './useMediaComments'
import { useViewerAnnotationOverlay } from './useViewerAnnotationOverlay'
import { flattenViewerComments, useViewerFrameActions } from './useViewerFrameActions'
import { useViewerMediaCore } from './useViewerMediaCore'
import { useViewerStreamEngine } from './useViewerStreamEngine'
import { useViewerTransport } from './useViewerTransport'

const EMPTY_MEDIA_INFO = Object.freeze({
  fps: 24,
  frames: 0,
  duration: 0,
  resolution: '',
  codec: '',
  extension: '',
})

function emptyMediaInfo() {
  return { ...EMPTY_MEDIA_INFO }
}

export function getViewerMediaRequestKey(mediaInput) {
  const media = normalizeMediaEntity(mediaInput)
  const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
  return [media?._projectId || '', shotVersionId || '', mediaAssetId || '', media?.path || ''].join(':')
}

export function resolveViewerMediaInfoRequest(mediaInput, { shareId = null, credential = {} } = {}) {
  const media = normalizeMediaEntity(mediaInput)
  const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
  const useSharedObjectRoute = !!(media?._projectId || media?.is_project_file || media?._openedFromTracker)
  const sharedEndpoint = shotVersionId && useSharedObjectRoute
    ? `/api/projects/shared/${shareId}/shot-versions/${shotVersionId}/file-info`
    : mediaAssetId && useSharedObjectRoute
      ? `/api/projects/shared/${shareId}/media-assets/${mediaAssetId}/file-info`
      : `/api/projects/shared/${shareId}/file-info`
  const authenticatedEndpoint = media?._projectId && shotVersionId
    ? `/api/horizons/projects/${media._projectId}/shot-versions/${shotVersionId}/file-info`
    : media?._projectId && mediaAssetId
      ? `/api/horizons/projects/${media._projectId}/media-assets/${mediaAssetId}/file-info`
      : media?._projectId && media?._projectFile
        ? `/api/projects/${media._projectId}/file-info`
        : '/api/video-info'
  const needsPath = shareId
    ? !(useSharedObjectRoute && (shotVersionId || mediaAssetId))
    : !(media?._projectId && (shotVersionId || mediaAssetId))
  const endpoint = resolveAccessEndpoint({
    shareId,
    shared: sharedEndpoint,
    authenticated: authenticatedEndpoint,
  })
  const query = buildShareCredentialQuery(
    needsPath
      ? { path: media?.path || '', ...(mediaAssetId ? { media_asset_id: mediaAssetId } : {}) }
      : {},
    shareId ? credential : {},
  )
  return `${endpoint}${query}`
}

function readRef(source) {
  return typeof source === 'function' ? source() : source?.value
}

/**
 * Owns the generic media-viewer lifecycle. Tracker stepping and version comparison
 * deliberately stay outside this controller and interact through narrow callbacks.
 */
export function useMediaViewerController({
  currentProject,
  currentTracker,
  currentUser,
  shareMode,
  shareRoot,
  shareAllowDownload,
  pendingShareId,
  shareAccessToken,
  shareAccessTokenScope,
  getShareCredential = () => ({}),
  getShotVersions,
  triggerBlobDownload,
  getFallbackFrameSourceName,
  onError,
  onTrackerActivityChanged,
  onThumbnailUpdated,
  onMediaChanged,
  onMediaDismissed,
  onViewerClosed,
  onOpenProjectReference,
  getCommentReferenceOriginContext = () => ({}),
  onRestoreCommentReferenceOrigin,
  isCloseLocked = () => false,
  windowTarget = typeof window === 'undefined' ? null : window,
  documentTarget = typeof document === 'undefined' ? null : document,
} = {}) {
  const currentVideo = ref(null)
  const videoEl = ref(null)
  const videoContainer = ref(null)
  const imageStage = ref(null)
  const suppressViewerAutoplay = ref(false)
  const viewerAutoplayPending = ref(false)
  const videoInfo = ref(emptyMediaInfo())
  const sidebarTab = ref('comments')
  const activityFocusCommentId = ref(null)
  const commentReferenceHistory = ref([])
  const colorPreviewMode = ref('source')
  const colorPreviewAvailable = ref(true)
  const canReturnToCommentOrigin = computed(() => commentReferenceHistory.value.length > 0)
  const commentReferenceOriginContext = computed(() => commentReferenceHistory.value.at(-1)?.context || null)

  let activityFocusCommentTimer = null
  let annotations = null
  let mediaComments = null
  let preserveCommentReferenceHistory = false
  let commentOriginRestoreBusy = false

  const reportError = (message, error) => onError?.(message, error)

  function setColorPreviewMode(mode) {
    const normalized = normalizeVideoColorPreviewMode(mode)
    if (normalized !== 'source' && !colorPreviewAvailable.value) return
    colorPreviewMode.value = normalized
  }

  function handleColorPreviewUnavailable(error) {
    if (!colorPreviewAvailable.value) return
    colorPreviewAvailable.value = false
    colorPreviewMode.value = 'source'
    reportError('Color preview unavailable', error)
  }

  const media = useViewerMediaCore({
    currentVideo,
    videoInfo,
    shareMode,
    pendingShareId,
    shareAccessToken,
    shareAccessTokenScope,
    currentProject,
    currentTracker,
    handleStreamError: error => reportError('Stream preparation failed', error),
  })

  const transport = useViewerTransport({
    videoEl,
    videoInfo,
    suppressViewerAutoplay,
    viewerAutoplayPending,
    isVideoActive: () => media.isViewingVideo.value,
    isSeekBlocked: () => annotations?.isDrawingMode.value || false,
    onPlayingTimeUpdate: () => {
      if (mediaComments?.showAnnotationPreview.value) {
        mediaComments.showAnnotationPreview.value = false
      }
    },
    onLoadedMedia: () => annotations?.setupAnnotationCanvas(),
    onPlaybackStarted: () => {
      if (mediaComments) mediaComments.showAnnotationPreview.value = false
    },
  })

  function createCommentReferenceOrigin(comment) {
    if (!currentVideo.value) return null
    return {
      media: { ...currentVideo.value },
      commentId: comment?.id || null,
      context: getCommentReferenceOriginContext?.() || {},
    }
  }

  function rememberCommentReferenceOrigin(origin) {
    if (origin) commentReferenceHistory.value.push(origin)
  }

  async function openCommentProjectReference(reference, comment) {
    const projectId = readRef(currentProject)?.id
    if (!projectId || !reference?.target_id) return
    if (['folder', 'shot', 'tracker', 'page'].includes(reference.target_type)) {
      const origin = createCommentReferenceOrigin(comment)
      rememberCommentReferenceOrigin(origin)
      preserveCommentReferenceHistory = true
      try {
        dismissCurrentMedia({ preserveCommentHistory: true })
        const opened = await onOpenProjectReference?.(reference)
        if (opened === false) await returnToCommentOrigin()
      } finally {
        preserveCommentReferenceHistory = false
      }
      return
    }
    if (reference.target_type !== 'media_asset') return

    if (reference.kind === 'file') {
      windowTarget?.open?.(
        `/api/horizons/projects/${projectId}/media-assets/${reference.target_id}/file`,
        '_blank',
        'noopener',
      )
      return
    }

    try {
      const { data } = await api.get(`/api/horizons/projects/${projectId}/media-assets/${reference.target_id}/file-info`)
      const item = normalizeMediaEntity({
        ...data,
        name: data.name || reference.name,
        path: data.path || data.file_path,
        file_path: data.file_path || data.path,
        media_asset_id: reference.target_id,
        horizons_media_asset_id: reference.target_id,
        version_id: null,
        horizons_shot_version_id: null,
        media_entity_type: 'media_asset',
        media_entity_id: reference.target_id,
        media_entity_key: `asset:${reference.target_id}`,
        _projectId: projectId,
        _projectFile: true,
      })
      if (item?.is_image || item?.is_pdf || item?.is_video) {
        rememberCommentReferenceOrigin(createCommentReferenceOrigin(comment))
        if (item.is_image) openImage(item)
        else if (item.is_pdf) openPdf(item)
        else await openVideo(item)
      } else {
        windowTarget?.open?.(`/api/horizons/projects/${projectId}/media-assets/${reference.target_id}/file`, '_blank', 'noopener')
      }
    } catch (error) {
      reportError('Failed to open project attachment', error)
    }
  }

  annotations = useViewerAnnotationOverlay({
    videoEl,
    videoContainer,
    imageStage,
    currentTime: transport.currentTime,
    isPlaying: transport.isPlaying,
    isViewingVideo: media.isViewingVideo,
    isViewingImage: media.isViewingImage,
    isViewingPdf: media.isViewingPdf,
    videoInfo,
    onAnnotationPreviewVisibilityChange: visible => {
      if (mediaComments) mediaComments.showAnnotationPreview.value = visible
    },
    windowTarget,
    documentTarget,
  })

  function seekToComment(comment) {
    frames.setFrameCaptureComment(comment)
    void focusViewerCommentCard(comment?.id)
    if (media.isViewingPdf.value) {
      annotations.requestPdfFocus(comment)
      return
    }

    const video = videoEl.value
    if (!video) return
    transport.disableLoopForUserSeek()
    video.currentTime = transport.clampSeekTime(Number(comment?.timestamp))
    video.pause()
    if (comment?.annotation_data) {
      mediaComments.showAnnotationFromData(comment.annotation_data)
    } else {
      annotations.clearAnnotationPreview()
    }
  }

  mediaComments = useMediaComments({
    shareMode,
    shareAllowDownload,
    pendingShareId,
    shareAccessToken,
    shareAccessTokenScope,
    currentVideo,
    currentTime: transport.currentTime,
    isViewingImage: media.isViewingImage,
    isViewingPdf: media.isViewingPdf,
    previewCanvas: annotations.previewCanvas,
    videoEl,
    pendingAnnotation: annotations.pendingAnnotation,
    pendingAnnotationTimestamp: annotations.pendingAnnotationTimestamp,
    pendingAnnotationTarget: annotations.pendingAnnotationTarget,
    currentProject: () => readRef(currentProject),
    currentTracker: () => readRef(currentTracker),
    currentUser: () => readRef(currentUser),
    getShotVersions,
    handleError: reportError,
    onTrackerActivityChanged,
    rememberPausedTime: transport.rememberPausedTime,
    setupAnnotationCanvas: annotations.setupAnnotationCanvas,
    clearAnnotationPreview: annotations.clearAnnotationPreview,
    clearPendingAnnotation: annotations.clearPendingAnnotation,
    seekToComment,
    onOpenProjectReference: openCommentProjectReference,
  })

  const currentFrame = computed(() => (
    Math.floor(transport.currentTime.value * (videoInfo.value.fps || 24))
  ))

  const frames = useViewerFrameActions({
    videoEl,
    currentTime: transport.currentTime,
    currentFrame,
    videoInfo,
    isViewingVideo: media.isViewingVideo,
    currentMedia: media.currentMedia,
    currentProject,
    comments: mediaComments.comments,
    annotationCanvas: annotations.annotationCanvas,
    previewCanvas: annotations.previewCanvas,
    showAnnotationPreview: mediaComments.showAnnotationPreview,
    colorPreviewMode,
    shareMode,
    getFallbackSourceName: getFallbackFrameSourceName,
    triggerBlobDownload,
    onThumbnailUpdated: (target, token) => {
      if (currentVideo.value) {
        currentVideo.value = {
          ...currentVideo.value,
          thumbnail_refresh_token: token,
          _thumbnailCacheBust: token,
        }
      }
      onThumbnailUpdated?.(target, token)
    },
  })

  const mediaUnavailable = computed(() => (
    media.currentMedia.value?.exists === false || videoInfo.value?.exists === false
  ))
  const stream = useViewerStreamEngine({
    videoEl,
    videoManifestUrl: media.videoManifestUrl,
    duration: transport.duration,
    streamPreparing: media.streamPreparing,
    isViewingVideo: media.isViewingVideo,
    mediaUnavailable,
    suppressViewerAutoplay,
    handleStreamError: error => reportError('Playback failed', error),
  })

  const sidebarTabs = computed(() => [
    { value: 'comments', label: 'Comments', icon: '#icon-comment', count: mediaComments.comments.value.length },
    { value: 'info', label: 'File Info', icon: '#icon-info' },
  ])
  const canShowToolbar = computed(() => (
    media.isViewingVideo.value && !mediaUnavailable.value && !media.streamPreparing.value
  ))

  function enrichProjectMedia(mediaInput, kind, { normalize = false } = {}) {
    const source = normalize ? normalizeMediaEntity(mediaInput) : mediaInput
    const projectFile = source?._projectFile ?? media.isProjectScopedPath(source?.path)
    const projectId = source?._projectId ?? (projectFile ? readRef(currentProject)?.id : null)
    return {
      ...source,
      ...(kind === 'video' ? { is_image: false } : {}),
      ...(kind === 'image' ? { is_image: true } : {}),
      ...(kind === 'pdf' ? { is_pdf: true } : {}),
      _projectFile: projectFile,
      _projectId: projectId,
    }
  }

  async function loadMediaInfo(mediaInput) {
    const requestKey = getViewerMediaRequestKey(mediaInput)
    try {
      const shareId = shareMode?.value ? pendingShareId?.value : null
      const url = resolveViewerMediaInfoRequest(mediaInput, {
        shareId,
        credential: shareId ? getShareCredential({ shareId }) : {},
      })
      const { data } = await api.get(url)
      if (requestKey !== getViewerMediaRequestKey(currentVideo.value)) return

      const merged = { ...emptyMediaInfo(), ...data }
      const rawSize = merged.size ?? merged.file_size ?? merged.fileSize ?? merged.file_size_bytes
      if (!merged.size_formatted && Number.isFinite(rawSize) && rawSize > 0) {
        merged.size_formatted = formatSizeBytes(rawSize)
      }

      if (currentVideo.value && !currentVideo.value.size_formatted && merged.size_formatted) {
        currentVideo.value.size_formatted = merged.size_formatted
      }
      if (currentVideo.value) {
        if (!currentVideo.value.media_asset_id && merged.media_asset_id) currentVideo.value.media_asset_id = merged.media_asset_id
        if (!currentVideo.value.horizons_media_asset_id && merged.media_asset_id) currentVideo.value.horizons_media_asset_id = merged.media_asset_id
        if (currentVideo.value.media_entity_type !== 'media_asset') {
          if (!currentVideo.value.version_id && merged.horizons_shot_version_id) currentVideo.value.version_id = merged.horizons_shot_version_id
          if (!currentVideo.value.horizons_shot_version_id && merged.horizons_shot_version_id) currentVideo.value.horizons_shot_version_id = merged.horizons_shot_version_id
        }
      }
      videoInfo.value = merged
    } catch (error) {
      console.error('Failed to load media info')
      if (requestKey === getViewerMediaRequestKey(currentVideo.value)) {
        videoInfo.value = emptyMediaInfo()
      }
    }
  }

  async function openVideo(item) {
    const viewerItem = enrichProjectMedia(item, 'video', { normalize: true })
    if (!viewerItem?.path) {
      console.error('openVideo called with an invalid item')
      return
    }

    mediaComments.resetMediaCommentState()
    annotations.resetPdfAnnotationState()
    transport.resetForMediaOpen()
    currentVideo.value = viewerItem
    media.streamProgress.value = 0
    viewerAutoplayPending.value = true

    await Promise.all([
      media.checkStreamStatus(viewerItem),
      loadMediaInfo(viewerItem),
      mediaComments.loadComments(),
    ])
  }

  function openImage(item) {
    const viewerItem = enrichProjectMedia(item, 'image')
    mediaComments.resetMediaCommentState()
    transport.lastPausedTime.value = null
    media.clearStreamPolling()
    annotations.resetPdfAnnotationState()
    currentVideo.value = viewerItem
    media.streamPreparing.value = false
    media.streamProgress.value = 0
    void loadMediaInfo(item)
    void mediaComments.loadComments()
  }

  function openPdf(item) {
    const viewerItem = enrichProjectMedia(item, 'pdf')
    mediaComments.resetMediaCommentState()
    transport.lastPausedTime.value = null
    media.clearStreamPolling()
    annotations.resetPdfAnnotationState()
    currentVideo.value = viewerItem
    media.streamPreparing.value = false
    media.streamProgress.value = 0
    videoInfo.value = { extension: 'pdf', size_formatted: viewerItem.size_formatted }
    void mediaComments.loadComments()
  }

  function dismissCurrentMedia({ preserveCommentHistory = false } = {}) {
    if (!preserveCommentHistory && !preserveCommentReferenceHistory) {
      commentReferenceHistory.value = []
    }
    media.clearStreamPolling()
    media.streamPreparing.value = false
    media.streamProgress.value = 0
    currentVideo.value = null
    viewerAutoplayPending.value = false
    videoInfo.value = emptyMediaInfo()
    frames.frameCaptureCommentId.value = null
    transport.resetPlaybackState()
    sidebarTab.value = 'comments'
    annotations.resetPdfAnnotationState()
    mediaComments.resetMediaCommentState()
    onMediaDismissed?.()
  }

  async function returnToCommentOrigin() {
    if (commentOriginRestoreBusy) return false
    const origin = commentReferenceHistory.value.at(-1)
    if (!origin?.media) return false

    commentOriginRestoreBusy = true
    preserveCommentReferenceHistory = true
    try {
      const restored = await onRestoreCommentReferenceOrigin?.(origin)
      if (restored === false) throw new Error('The original review context is no longer available')

      const kind = getMediaKind(origin.media)
      if (kind === 'image') openImage(origin.media)
      else if (kind === 'pdf') openPdf(origin.media)
      else if (kind === 'video') await openVideo(origin.media)
      else throw new Error('The original media can no longer be opened')

      sidebarTab.value = 'comments'
      if (origin.commentId) await focusMediaComment(origin.commentId)
      commentReferenceHistory.value.pop()
      return true
    } catch (error) {
      reportError('Failed to return to the original comment', error)
      return false
    } finally {
      preserveCommentReferenceHistory = false
      commentOriginRestoreBusy = false
    }
  }

  function closeViewer() {
    if (isCloseLocked()) return
    const filePath = currentVideo.value?.path || ''
    dismissCurrentMedia()
    onViewerClosed?.({ filePath, shareRoot: shareRoot?.value || '' })
  }

  function handleCommentClick(comment) {
    frames.setFrameCaptureComment(comment)
    mediaComments.handleCommentClick(comment)
  }

  function handleVideoContainerClick() {
    if (annotations.consumeViewerClickSuppression() || annotations.isDrawingMode.value) return
    transport.togglePlay()
  }

  function setVideoElRef(element) {
    videoEl.value = element
  }

  function setVideoContainerRef(element) {
    videoContainer.value = element
  }

  function setImageStageRef(element) {
    imageStage.value = element
  }

  function onImageLoaded() {
    annotations.setupAnnotationCanvas()
  }

  function formatTimecode(seconds) {
    return formatTimecodeWithFrames(seconds, videoInfo.value.fps || 24)
  }

  function handleViewerKeydown(event, { disabled = false } = {}) {
    if (disabled || !currentVideo.value || !videoEl.value) return false
    if (event.target?.tagName === 'TEXTAREA' || event.target?.tagName === 'INPUT') return false
    const oneFrame = 1 / (videoInfo.value.fps || 24)
    if (event.code === 'Space') {
      event.preventDefault()
      transport.togglePlay()
      return true
    }
    if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
      event.preventDefault()
      const direction = event.code === 'ArrowLeft' ? -1 : 1
      const distance = event.shiftKey ? 1 : oneFrame
      transport.seekVideo((videoEl.value.currentTime || 0) + (direction * distance))
      return true
    }
    return false
  }

  function escapeSelectorValue(value) {
    const text = String(value || '')
    return windowTarget?.CSS?.escape ? windowTarget.CSS.escape(text) : text.replace(/["\\]/g, '\\$&')
  }

  async function focusViewerCommentCard(commentId, { scroll = true } = {}) {
    const normalizedCommentId = String(commentId || '').trim()
    if (!normalizedCommentId) return
    sidebarTab.value = 'comments'
    activityFocusCommentId.value = normalizedCommentId

    if (activityFocusCommentTimer) windowTarget?.clearTimeout?.(activityFocusCommentTimer)
    activityFocusCommentTimer = windowTarget?.setTimeout?.(() => {
      if (activityFocusCommentId.value === normalizedCommentId) activityFocusCommentId.value = null
      activityFocusCommentTimer = null
    }, 2600) || null

    if (!scroll) return
    await nextTick()
    const scrollToComment = () => {
      const selector = `[data-comment-id="${escapeSelectorValue(normalizedCommentId)}"]`
      documentTarget?.querySelector?.(selector)?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    }
    if (windowTarget?.requestAnimationFrame) windowTarget.requestAnimationFrame(scrollToComment)
    else scrollToComment()
  }

  async function focusMediaComment(commentId) {
    const normalizedCommentId = String(commentId || '').trim()
    if (!normalizedCommentId || !currentVideo.value?.path) return
    await mediaComments.loadComments()
    await nextTick()
    await new Promise(resolve => {
      if (windowTarget?.requestAnimationFrame) windowTarget.requestAnimationFrame(resolve)
      else resolve()
    })
    const comment = flattenViewerComments(mediaComments.comments.value)
      .find(item => String(item?.id || '') === normalizedCommentId)
    if (comment) handleCommentClick(comment)
    await focusViewerCommentCard(normalizedCommentId)
  }

  function cleanup() {
    if (activityFocusCommentTimer) {
      windowTarget?.clearTimeout?.(activityFocusCommentTimer)
      activityFocusCommentTimer = null
    }
    media.clearStreamPolling()
    annotations.cleanupCanvasResize()
    transport.stopSmoothProgress()
  }

  watch(media.currentMedia, () => {
    frames.frameCaptureCommentId.value = null
    onMediaChanged?.(media.currentMedia.value)
  })
  // The clock ticks 60×/s during playback and the staleness check walks the
  // comment tree, so gate it to ~4Hz — the cadence timeupdate provides anyway.
  let lastFrameCaptureStaleCheck = 0
  watch(transport.currentTime, () => {
    const now = Date.now()
    if (now - lastFrameCaptureStaleCheck < 250) return
    lastFrameCaptureStaleCheck = now
    frames.clearFrameCaptureCommentIfStale()
  })

  if (getCurrentScope()) onScopeDispose(cleanup)

  return Object.freeze({
    state: Object.freeze({
      currentVideo,
      currentMedia: media.currentMedia,
      videoInfo,
      mediaInfo: media.mediaInfo,
      videoEl,
      videoContainer,
      imageStage,
      currentFrame,
      mediaUnavailable,
      sidebarTab,
      sidebarTabs,
      sidebarTabVariant: 'rail',
      activityFocusCommentId,
      canReturnToCommentOrigin,
      commentReferenceOriginContext,
      canShowToolbar,
    }),
    media: Object.freeze({
      isViewingImage: media.isViewingImage,
      isViewingPdf: media.isViewingPdf,
      isViewingVideo: media.isViewingVideo,
      mediaStreamUrl: media.mediaStreamUrl,
      videoManifestUrl: media.videoManifestUrl,
      resolveViewerMediaRoutes: media.resolveViewerMediaRoutes,
      getThumbnailUrl: media.getThumbnailUrl,
      isProjectRenderPath: media.isProjectRenderPath,
      isProjectScopedPath: media.isProjectScopedPath,
      getProjectThumbnailUrl: media.getProjectThumbnailUrl,
      getProjectFolderThumbnailUrl: media.getProjectFolderThumbnailUrl,
      bumpProjectHeaderThumbnailRefresh: media.bumpProjectHeaderThumbnailRefresh,
      currentProjectHeaderThumbnailUrl: media.currentProjectHeaderThumbnailUrl,
      currentProjectDeliveryThumbnailUrl: media.currentProjectDeliveryThumbnailUrl,
      getProjectFileThumbnailUrl: media.getProjectFileThumbnailUrl,
      openVideo,
      openImage,
      openPdf,
      loadMediaInfo,
      dismissCurrentMedia,
      closeViewer,
      returnToCommentOrigin,
    }),
    stream: Object.freeze({
      preparing: media.streamPreparing,
      showPreparingOverlay: media.showStreamPreparingOverlay,
      progress: media.streamProgress,
      clearPolling: media.clearStreamPolling,
      checkStatus: media.checkStreamStatus,
      getInterval: media.getStreamInterval,
      qualityOptions: stream.qualityOptions,
      selectedQuality: stream.selectedQuality,
      selectedQualityLabel: stream.selectedQualityLabel,
      scrubPreviewSourceUrl: stream.scrubPreviewSourceUrl,
      setQuality: stream.setStreamQuality,
    }),
    transport,
    annotations,
    comments: mediaComments,
    frames,
    colorPreview: Object.freeze({
      mode: colorPreviewMode,
      available: colorPreviewAvailable,
      options: VIDEO_COLOR_PREVIEW_OPTIONS,
      setMode: setColorPreviewMode,
      handleUnavailable: handleColorPreviewUnavailable,
    }),
    actions: Object.freeze({
      setVideoElRef,
      setVideoContainerRef,
      setImageStageRef,
      onImageLoaded,
      handleVideoContainerClick,
      handleCommentClick,
      seekToComment,
      focusViewerCommentCard,
      focusMediaComment,
      handleViewerKeydown,
      formatTimecode,
      cleanup,
    }),
  })
}
