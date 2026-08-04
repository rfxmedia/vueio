import { computed, ref, unref } from 'vue'

import api from '../lib/api'
import { canvasToPngBlob, renderVideoFrame } from '../lib/frameCapture'
import { getCanonicalMediaRefs } from '../lib/mediaEntity'
import { formatTimecodeWithFrames } from '../utils/formatters'

const FRAME_CAPTURE_COMMENT_MAX_TIME_DRIFT_SECONDS = 0.75

function readSource(source) {
  return typeof source === 'function' ? source() : unref(source)
}

export function flattenViewerComments(items = []) {
  const flattened = []
  items.forEach((comment) => {
    if (!comment) return
    flattened.push(comment)
    if (Array.isArray(comment.replies)) {
      flattened.push(...flattenViewerComments(comment.replies))
    }
  })
  return flattened
}

export function useViewerFrameActions({
  videoEl,
  currentTime,
  currentFrame,
  videoInfo,
  isViewingVideo,
  currentMedia,
  currentProject,
  comments,
  annotationCanvas,
  previewCanvas,
  showAnnotationPreview,
  shareMode,
  getFallbackSourceName = () => '',
  triggerBlobDownload,
  onThumbnailUpdated,
  postThumbnail = (url, formData) => api.post(url, formData),
} = {}) {
  const frameCaptureCommentId = ref(null)

  function findViewerCommentContext(commentId, items = readSource(comments) || []) {
    const targetId = String(commentId || '').trim()
    if (!targetId) return null

    function findInReplies(replies, parent, topLevelIndex) {
      for (const reply of replies || []) {
        if (!reply) continue
        if (String(reply.id || '') === targetId) {
          return { comment: reply, parent, topLevelIndex, isReply: true }
        }
        const nestedMatch = findInReplies(reply.replies, parent, topLevelIndex)
        if (nestedMatch) return nestedMatch
      }
      return null
    }

    for (let index = 0; index < items.length; index += 1) {
      const comment = items[index]
      if (!comment) continue
      const topLevelIndex = index + 1
      if (String(comment.id || '') === targetId) {
        return { comment, parent: null, topLevelIndex, isReply: false }
      }
      const replyMatch = findInReplies(comment.replies, comment, topLevelIndex)
      if (replyMatch) return replyMatch
    }

    return null
  }

  function setFrameCaptureComment(comment) {
    const timestamp = Number(comment?.timestamp)
    if (!readSource(isViewingVideo) || !comment?.id || !Number.isFinite(timestamp)) {
      frameCaptureCommentId.value = null
      return
    }
    frameCaptureCommentId.value = String(comment.id)
  }

  function getCurrentFrameCaptureTime() {
    const videoTime = Number(readSource(videoEl)?.currentTime)
    if (Number.isFinite(videoTime)) return videoTime
    const reactiveTime = Number(readSource(currentTime))
    return Number.isFinite(reactiveTime) ? reactiveTime : 0
  }

  function frameCaptureCommentMatchesTime(comment, time = Number(readSource(currentTime) || 0)) {
    const commentTime = Number(comment?.timestamp)
    if (!readSource(isViewingVideo) || !Number.isFinite(commentTime)) return false
    const captureTime = Number(time)
    if (!Number.isFinite(captureTime)) return false
    const fps = Number(readSource(videoInfo)?.fps || 24)
    const frameTolerance = Number.isFinite(fps) && fps > 0 ? 2 / fps : 0
    const tolerance = Math.max(frameTolerance, FRAME_CAPTURE_COMMENT_MAX_TIME_DRIFT_SECONDS)
    return Math.abs(commentTime - captureTime) <= tolerance
  }

  function getFrameCaptureCommentSnapshot({ requireCurrentFrame = false } = {}) {
    const match = findViewerCommentContext(frameCaptureCommentId.value)
    if (!match?.comment) return null
    if (requireCurrentFrame && !frameCaptureCommentMatchesTime(match.comment, getCurrentFrameCaptureTime())) return null
    const numberLabel = `#${match.topLevelIndex}${match.isReply ? ' reply' : ''}`
    return {
      ...match.comment,
      capture_number_label: numberLabel,
      capture_time_label: formatTimecodeWithFrames(
        Number(match.comment.timestamp || 0),
        readSource(videoInfo)?.fps || 24,
      ),
    }
  }

  function clearFrameCaptureCommentIfStale() {
    if (!frameCaptureCommentId.value) return
    const match = findViewerCommentContext(frameCaptureCommentId.value)
    if (!match?.comment || !frameCaptureCommentMatchesTime(match.comment)) {
      frameCaptureCommentId.value = null
    }
  }

  function renderCurrentVideoFrame({ includeAnnotations = false, includeComment = false } = {}) {
    return renderVideoFrame({
      video: readSource(videoEl),
      annotationCanvas: includeAnnotations ? readSource(annotationCanvas) : null,
      previewCanvas: includeAnnotations && readSource(showAnnotationPreview) ? readSource(previewCanvas) : null,
      includeAnnotations,
      comment: includeComment ? getFrameCaptureCommentSnapshot({ requireCurrentFrame: true }) : null,
    })
  }

  function canWriteImageToClipboard() {
    return Boolean(window.isSecureContext && navigator.clipboard?.write && typeof window.ClipboardItem !== 'undefined')
  }

  function canShareFrameFile(file) {
    if (typeof navigator.share !== 'function') return false
    if (typeof navigator.canShare !== 'function') return true
    try {
      return navigator.canShare({ files: [file] })
    } catch {
      return false
    }
  }

  function getCurrentFrameDownloadName() {
    const media = readSource(currentMedia)
    const sourceName = String(
      media?.name
      || getFallbackSourceName()
      || 'current-frame'
    ).trim()
    const baseName = (sourceName.replace(/\.[^.]+$/, '') || 'current-frame')
      .replace(/[\\/:*?"<>|]+/g, '-')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 80) || 'current-frame'
    const frameLabel = String(readSource(currentFrame) || 0).replace(/[^\dA-Za-z_-]+/g, '')
    return `${baseName}-frame-${frameLabel || '0'}.png`
  }

  async function copyCurrentFrameToClipboard(options = {}) {
    const canvas = renderCurrentVideoFrame(options)
    const blob = await canvasToPngBlob(canvas)
    const type = blob.type || 'image/png'

    if (canWriteImageToClipboard()) {
      await navigator.clipboard.write([
        new window.ClipboardItem({ [type]: blob }),
      ])
      return { mode: 'clipboard' }
    }

    const fileName = getCurrentFrameDownloadName()
    if (typeof File !== 'undefined') {
      const file = new File([blob], fileName, { type })
      if (canShareFrameFile(file)) {
        await navigator.share({
          files: [file],
          title: 'Current frame',
        })
        return { mode: 'share' }
      }
    }

    triggerBlobDownload(blob, fileName)
    return { mode: 'download' }
  }

  async function downloadCurrentFrame(options = {}) {
    const canvas = renderCurrentVideoFrame(options)
    const blob = await canvasToPngBlob(canvas)
    triggerBlobDownload(blob, getCurrentFrameDownloadName())
  }

  function getCurrentFrameThumbnailTarget() {
    const media = readSource(currentMedia)
    const projectId = media?._projectId || readSource(currentProject)?.id
    if (readSource(shareMode) || !projectId || !readSource(isViewingVideo)) return null

    const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
    if (shotVersionId) {
      return {
        url: `/api/horizons/projects/${projectId}/shot-versions/${shotVersionId}/thumbnail`,
        mediaAssetId,
        shotVersionId,
        path: media?.path || '',
      }
    }
    if (mediaAssetId) {
      return {
        url: `/api/horizons/projects/${projectId}/media-assets/${mediaAssetId}/thumbnail`,
        mediaAssetId,
        shotVersionId: null,
        path: media?.path || '',
      }
    }
    return null
  }

  const canSetCurrentFrameAsThumbnail = computed(() => Boolean(getCurrentFrameThumbnailTarget()))
  const frameCaptureComment = computed(() => getFrameCaptureCommentSnapshot())

  async function setCurrentFrameAsThumbnail() {
    const target = getCurrentFrameThumbnailTarget()
    if (!target) {
      throw new Error('Thumbnail target unavailable')
    }

    const canvas = renderCurrentVideoFrame({ includeAnnotations: false })
    const blob = await canvasToPngBlob(canvas)
    const formData = new FormData()
    formData.append('file', blob, getCurrentFrameDownloadName())

    const { data } = await postThumbnail(target.url, formData)
    const token = data?.thumbnail_url_cache_bust || Date.now()
    onThumbnailUpdated?.(target, token)
    return { cacheBustToken: token }
  }

  return {
    frameCaptureCommentId,
    frameCaptureComment,
    canSetCurrentFrameAsThumbnail,
    findViewerCommentContext,
    setFrameCaptureComment,
    getCurrentFrameCaptureTime,
    frameCaptureCommentMatchesTime,
    getFrameCaptureCommentSnapshot,
    clearFrameCaptureCommentIfStale,
    renderCurrentVideoFrame,
    getCurrentFrameDownloadName,
    copyCurrentFrameToClipboard,
    downloadCurrentFrame,
    getCurrentFrameThumbnailTarget,
    setCurrentFrameAsThumbnail,
  }
}
