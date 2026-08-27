import { computed, getCurrentScope, markRaw, onScopeDispose, reactive, ref, shallowRef } from 'vue'
import api, { buildShareCredentialQuery, getApiErrorMessage } from '../lib/api'

import { isSafePngDataUrl } from '../lib/annotations'
import { buildCommentBatchTarget, chunkCommentTargets } from '../lib/commentTargets'
import { readStoredString } from '../utils/storage'
import { sanitizeUiText, textRendersMentionMarker } from '../utils/textSanitization'
import { notify } from '../utils/toasts'
import { useVoiceNoteRecorder } from './useVoiceNoteRecorder'

const EMPTY_BRIEF_PREVIEW = 'No Instructions Yet'
const LEGACY_EMPTY_COMMENT_PREVIEW = 'No comments yet.'
const PENDING_TRANSCRIPTION_STATUSES = new Set(['queued', 'processing'])
const INLINE_MENTION_LIMIT = 20

function getOptionalRefValue(source) {
  if (typeof source === 'function') return source()
  return source?.value
}

function getShareCredential(ctx) {
  if (ctx.shareMode?.value && ctx.pendingShareId?.value) {
    const scope = ctx.shareAccessTokenScope?.value
    const shareToken = ctx.shareAccessToken?.value && (!scope?.shareId || scope.shareId === ctx.pendingShareId.value)
      ? ctx.shareAccessToken.value
      : ''
    return { shareToken }
  }
  return {}
}

function getCommentProjectId(ctx) {
  const currentVideo = getOptionalRefValue(ctx.currentVideo)
  if (currentVideo && Object.prototype.hasOwnProperty.call(currentVideo, '_commentProjectId')) {
    return currentVideo._commentProjectId || null
  }
  if (currentVideo?._projectId) return currentVideo._projectId
  if (currentVideo && currentVideo._projectFile === false) return null

  const currentProject = getOptionalRefValue(ctx.currentProject)
  return currentProject?.id || null
}

function getCommentPath(ctx) {
  const currentVideo = getOptionalRefValue(ctx.currentVideo)
  return currentVideo?._commentPath || currentVideo?.path || ''
}

function getCommentTargetRefs(ctx) {
  const currentVideo = getOptionalRefValue(ctx.currentVideo)
  if (!currentVideo) return {}
  return {
    horizons_media_asset_id: currentVideo.media_asset_id || currentVideo.horizons_media_asset_id || null,
    horizons_shot_version_id: currentVideo.version_id || currentVideo.horizons_shot_version_id || null,
  }
}

function buildCommentParams(ctx, target = {}) {
  const params = { ...target }
  if (ctx.shareMode?.value && ctx.pendingShareId?.value) {
    params.share_id = ctx.pendingShareId.value
  } else {
    const projectId = getCommentProjectId(ctx)
    if (projectId) params.project_id = projectId
  }
  const refs = getCommentTargetRefs(ctx)
  if (refs.horizons_media_asset_id) params.horizons_media_asset_id = refs.horizons_media_asset_id
  if (refs.horizons_shot_version_id) params.horizons_shot_version_id = refs.horizons_shot_version_id
  return params
}

function buildAttachmentDownloadUrl(url) {
  if (!url) return ''
  return `${url}${url.includes('?') ? '&' : '?'}download=1`
}

function normalizeStoredCommenterName(value) {
  const name = String(value || '').trim()
  if (!name) return ''
  if (name.includes('\n') || (name.length > 48 && name.includes(' '))) return ''
  return name
}

function parseCommentAttachments(comment) {
  let attachments = []
  const raw = comment?.attachments_data
  if (Array.isArray(raw)) {
    attachments = raw
  } else if (typeof raw === 'string' && raw.trim()) {
    try {
      attachments = JSON.parse(raw)
    } catch {
      attachments = []
    }
  }
  const replies = Array.isArray(comment?.replies)
    ? comment.replies.map(parseCommentAttachments)
    : []
  return { ...comment, attachments, replies }
}

function hasPendingVoiceTranscription(commentThreads) {
  return (commentThreads || []).some(comment => (
    comment.attachments?.some(attachment => (
      attachment?.kind === 'audio'
      && PENDING_TRANSCRIPTION_STATUSES.has(attachment.transcription_status)
    ))
    || hasPendingVoiceTranscription(comment.replies)
  ))
}

function flattenCommentThreads(comments) {
  const flat = []
  const seen = new Set()

  const visit = (comment) => {
    if (!comment?.id || seen.has(comment.id)) return
    seen.add(comment.id)
    const { replies, ...rest } = comment
    flat.push({ ...rest, replies: [] })
    for (const reply of replies || []) visit(reply)
  }

  for (const comment of comments || []) visit(comment)
  return flat
}

function nestCommentThreads(rawComments) {
  const flat = flattenCommentThreads(rawComments || []).map((comment) => parseCommentAttachments(comment))
  if (!flat.length) return []

  const byId = new Map(flat.map((comment) => [comment.id, comment]))
  const knownIds = new Set(byId.keys())
  const repliesByRoot = new Map()
  const roots = []

  for (const comment of flat) {
    const rootId = comment.root_comment_id || comment.parent_comment_id
    if (rootId && knownIds.has(rootId) && comment.id !== rootId) {
      if (!repliesByRoot.has(rootId)) repliesByRoot.set(rootId, [])
      repliesByRoot.get(rootId).push(comment)
      continue
    }
    roots.push(comment)
  }

  const sortByCreated = (a, b) => {
    const aCreated = Number(a.created_at) || 0
    const bCreated = Number(b.created_at) || 0
    if (aCreated !== bCreated) return aCreated - bCreated
    return (Number(a.id) || 0) - (Number(b.id) || 0)
  }

  const sortByTimestamp = (a, b) => {
    const aTs = Number(a.timestamp) || 0
    const bTs = Number(b.timestamp) || 0
    if (aTs !== bTs) return aTs - bTs
    return sortByCreated(a, b)
  }

  for (const root of roots) {
    root.replies = (repliesByRoot.get(root.id) || []).sort(sortByCreated)
  }

  return roots.sort(sortByTimestamp)
}

function countCommentThreads(threads) {
  if (!Array.isArray(threads)) return 0
  return threads.reduce((total, comment) => total + 1 + (comment.replies?.length || 0), 0)
}

function attachmentKindFromFile(file) {
  const type = String(file?.type || '')
  if (type.startsWith('image/')) return 'image'
  if (type.startsWith('video/')) return 'video'
  if (type.startsWith('audio/')) return 'audio'
  const name = String(file?.name || '')
  const ext = name.split('.').pop()?.toLowerCase()
  const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'heic', 'heif']
  const videoExts = ['mp4', 'webm', 'm4v', 'mov', 'avi', 'mkv', 'mxf', 'r3d', 'prores']
  const audioExts = ['weba', 'm4a', 'mp3', 'wav', 'ogg', 'opus']
  if (ext && imageExts.includes(ext)) return 'image'
  if (ext && videoExts.includes(ext)) return 'video'
  if (ext && audioExts.includes(ext)) return 'audio'
  return ''
}

function clearPendingAnnotationDraft(ctx) {
  if (typeof ctx.clearPendingAnnotation === 'function') {
    ctx.clearPendingAnnotation({ exitDrawingMode: true })
    return
  }
  if (ctx.pendingAnnotation) ctx.pendingAnnotation.value = null
  if (ctx.pendingAnnotationTimestamp) ctx.pendingAnnotationTimestamp.value = null
  if (ctx.pendingAnnotationTarget) ctx.pendingAnnotationTarget.value = null
}

function resolveCommentTimestamp(ctx, { hasAnnotation = false } = {}) {
  if (ctx.isViewingImage?.value || ctx.isViewingPdf?.value) return 0
  const lockedAnnotationTimestamp = Number(getOptionalRefValue(ctx.pendingAnnotationTimestamp))
  if (hasAnnotation && Number.isFinite(lockedAnnotationTimestamp)) {
    return lockedAnnotationTimestamp
  }
  const currentTimestamp = Number(getOptionalRefValue(ctx.currentTime))
  return Number.isFinite(currentTimestamp) ? currentTimestamp : 0
}

export function useMediaComments(ctx) {
  const comments = shallowRef([])
  const newComment = ref('')
  const commentPosting = ref(false)
  const userNameInput = ref('')
  const userName = ref(normalizeStoredCommenterName(readStoredString('vueio_user', '')))
  const pendingCommentAttachments = shallowRef([])
  const pendingInlineMentions = shallowRef([])
  const attachmentLightbox = ref(null)
  const showAnnotationPreview = ref(false)
  const replyTarget = ref(null)
  const voiceRecorder = useVoiceNoteRecorder()

  const briefPreviewCache = reactive({})
  const briefPreviewLoading = reactive({})
  let briefPreviewRequestId = 0
  let commentRequestId = 0
  let voiceTranscriptRefreshTimer = 0
  let commentAbortController = null
  let briefPreviewAbortController = null

  const mentionContext = computed(() => {
    const projectId = getCommentProjectId(ctx)
    const tracker = getOptionalRefValue(ctx.currentTracker)
    return {
      enabled: Boolean(getOptionalRefValue(ctx.currentUser)) && !ctx.shareMode?.value && Boolean(projectId),
      projectId,
      trackerId: tracker?.id || tracker?.slug || tracker?.name || '',
      shots: tracker?.shots || [],
    }
  })

  function isCanceledRequest(error, signal = null) {
    return signal?.aborted
      || error?.name === 'CanceledError'
      || error?.code === 'ERR_CANCELED'
      || error?.name === 'AbortError'
  }

  function clearVoiceTranscriptRefresh() {
    if (voiceTranscriptRefreshTimer) window.clearTimeout(voiceTranscriptRefreshTimer)
    voiceTranscriptRefreshTimer = 0
  }

  function scheduleVoiceTranscriptRefresh() {
    clearVoiceTranscriptRefresh()
    if (!hasPendingVoiceTranscription(comments.value)) return
    const path = getCommentPath(ctx)
    voiceTranscriptRefreshTimer = window.setTimeout(() => {
      voiceTranscriptRefreshTimer = 0
      if (path === getCommentPath(ctx)) void loadComments()
    }, 2000)
  }

  function resetCommentDraft() {
    newComment.value = ''
    replyTarget.value = null
    clearPendingAnnotationDraft(ctx)
    clearPendingCommentAttachments()
    clearPendingInlineMentions()
    voiceRecorder.removeVoiceNote()
  }

  function resetMediaCommentState() {
    commentRequestId += 1
    commentAbortController?.abort()
    commentAbortController = null
    clearVoiceTranscriptRefresh()
    comments.value = []
    resetCommentDraft()
    closeAttachmentLightbox()
    showAnnotationPreview.value = false
  }

  function getCommentAttachmentUrl(comment, attachment) {
    if (!comment?.id || !attachment?.id) return ''
    const extra = ctx.shareMode?.value && ctx.pendingShareId?.value
      ? { share_id: ctx.pendingShareId.value }
      : {}
    return `/api/comments/${comment.id}/attachments/${attachment.id}${buildShareCredentialQuery(extra, getShareCredential(ctx))}`
  }

  function handleCommentAttachmentChange(event) {
    const files = Array.from(event?.target?.files || [])
    if (!files.length) return
    const current = pendingCommentAttachments.value
    const maxLeft = Math.max(0, 3 - current.length - (voiceRecorder.pendingVoiceNote.value ? 1 : 0))
    if (maxLeft <= 0) {
      event.target.value = ''
      return
    }

    const newAttachments = []
    for (const file of files.slice(0, maxLeft)) {
      const kind = attachmentKindFromFile(file)
      if (!kind) {
        notify('Only image, video, or audio attachments are allowed.')
        continue
      }
      const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
      const previewUrl = kind === 'image' ? URL.createObjectURL(file) : ''
      const attachment = markRaw({
        id,
        file,
        name: file.name,
        kind,
        previewUrl,
        size: file.size
      })
      newAttachments.push(attachment)
    }

    if (newAttachments.length) {
      pendingCommentAttachments.value = [...current, ...newAttachments]
    }
    event.target.value = ''
  }

  function addPendingCommentReferences(items = []) {
    const current = pendingCommentAttachments.value
    const maxLeft = Math.max(0, 3 - current.length - (voiceRecorder.pendingVoiceNote.value ? 1 : 0))
    if (!maxLeft) return

    const existing = new Set(current
      .filter(item => item?.attachment_type === 'reference')
      .map(item => `${item.target_type}:${item.target_id}`))
    const references = []
    for (const item of items) {
      const targetType = item?.type === 'folder'
        ? 'folder'
        : item?.type === 'tracker'
          ? 'tracker'
          : item?.type === 'page'
            ? 'page'
            : 'media_asset'
      const targetId = targetType === 'media_asset'
        ? item?.media_asset_id
        : targetType === 'folder'
          ? item?.path
          : item?.id
      const key = `${targetType}:${targetId || ''}`
      if (!targetId || existing.has(key)) continue
      existing.add(key)
      references.push(markRaw({
        id: `reference_${targetType}_${targetId}`,
        attachment_type: 'reference',
        target_type: targetType,
        target_id: targetId,
        kind: targetType === 'media_asset'
          ? (item.is_image || item.type === 'image' ? 'image' : item.is_video || item.type === 'video' ? 'video' : item.is_pdf ? 'pdf' : 'file')
          : targetType,
        name: item.name || item.title || 'Project asset',
      }))
      if (references.length >= maxLeft) break
    }
    if (references.length) pendingCommentAttachments.value = [...current, ...references]
  }

  function addPendingInlineMention(item, rawMarker) {
    if (!mentionContext.value.enabled) return false
    const marker = sanitizeUiText(rawMarker).trim()
    if (!marker.startsWith('@') || marker.includes('\n') || marker.includes('\r') || marker.length > 120) return false
    const targetType = item?.target_type || (
      item?.type === 'shot'
        ? 'shot'
        : item?.type === 'folder'
          ? 'folder'
          : item?.type === 'tracker'
            ? 'tracker'
            : item?.type === 'page'
              ? 'page'
              : 'media_asset'
    )
    if (!['shot', 'media_asset', 'folder', 'tracker', 'page'].includes(targetType)) return false
    const targetId = item?.target_id || (
      targetType === 'media_asset'
        ? item?.media_asset_id || item?.horizons_media_asset_id
        : targetType === 'folder'
          ? item?.path
        : targetType === 'shot'
          ? item?.id || item?._originalId || item?.shot_id
          : item?.id
    )
    if (!targetId) return false
    const key = `${marker}:${targetType}:${targetId}`
    if (pendingInlineMentions.value.some(mention => mention.key === key)) return true
    if (pendingInlineMentions.value.length >= INLINE_MENTION_LIMIT) {
      notify(`A comment can include up to ${INLINE_MENTION_LIMIT} mentions.`)
      return false
    }

    pendingInlineMentions.value = [...pendingInlineMentions.value, markRaw({
      key,
      id: `mention_${pendingInlineMentions.value.length}_${targetType}_${targetId}`,
      attachment_type: 'reference',
      target_type: targetType,
      target_id: targetId,
      marker,
      name: item?.label || item?.name || item?.title || marker.slice(1),
      kind: item?.kind || targetType,
      tracker_id: item?.tracker_id || '',
    })]
    return true
  }

  function removePendingCommentAttachment(id) {
    const current = pendingCommentAttachments.value
    const idx = current.findIndex(att => att.id === id)
    if (idx === -1) return
    const removed = current[idx]
    if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
    pendingCommentAttachments.value = current.filter((_, i) => i !== idx)
  }

  function clearPendingCommentAttachments() {
    pendingCommentAttachments.value.forEach(att => {
      if (att?.previewUrl) URL.revokeObjectURL(att.previewUrl)
    })
    pendingCommentAttachments.value = []
  }

  function clearPendingInlineMentions() {
    pendingInlineMentions.value = []
  }

  async function startVoiceRecording() {
    if (voiceRecorder.pendingVoiceNote.value) {
      notify('Remove the current voice note before recording another.')
      return false
    }
    if (pendingCommentAttachments.value.length >= 3) {
      notify('Remove an attachment before adding a voice note.')
      return false
    }
    return voiceRecorder.startRecording()
  }

  function openAttachmentLightbox(comment, attachment) {
    if (attachment?.attachment_type === 'reference') {
      void ctx.onOpenProjectReference?.(attachment, comment)
      return
    }
    const url = getCommentAttachmentUrl(comment, attachment)
    if (!url) return
    const canDownload = !ctx.shareMode?.value || !!ctx.shareAllowDownload?.value
    attachmentLightbox.value = {
      url,
      downloadUrl: canDownload ? buildAttachmentDownloadUrl(url) : '',
      kind: attachment?.kind || 'image',
      name: attachment?.name || ''
    }
  }

  function closeAttachmentLightbox() {
    attachmentLightbox.value = null
  }

  function showAnnotationFromData(annotationData) {
    const preview = ctx.previewCanvas?.value
    if (!preview || !isSafePngDataUrl(annotationData)) return

    ctx.setupAnnotationCanvas?.()

    const img = new Image()
    img.onload = () => {
      const previewCtx = preview.getContext('2d')
      if (!previewCtx) return
      previewCtx.clearRect(0, 0, preview.width, preview.height)
      previewCtx.drawImage(img, 0, 0, preview.width, preview.height)
      showAnnotationPreview.value = true
    }
    img.src = annotationData
  }

  async function loadComments() {
    const path = getCommentPath(ctx)
    if (!path) {
      clearVoiceTranscriptRefresh()
      return
    }
    const requestId = ++commentRequestId
    commentAbortController?.abort()
    const controller = new AbortController()
    commentAbortController = controller
    const query = buildShareCredentialQuery(buildCommentParams(ctx, { path }), getShareCredential(ctx))
    try {
      const { data } = await api.get(`/api/comments${query}`, { signal: controller.signal })
      if (requestId !== commentRequestId || path !== getCommentPath(ctx)) return
      comments.value = nestCommentThreads(data)
      scheduleVoiceTranscriptRefresh()
    } catch (error) {
      if (requestId !== commentRequestId || path !== getCommentPath(ctx)) return
      if (isCanceledRequest(error, controller.signal)) return
      console.error('Failed to load comments')
      comments.value = []
    } finally {
      if (commentAbortController === controller) commentAbortController = null
    }
  }

  function getCurrentMediaPreviewTarget() {
    const path = getCommentPath(ctx)
    if (!path) return null
    const refs = getCommentTargetRefs(ctx)
    return buildCommentBatchTarget({
      path,
      horizons_media_asset_id: refs.horizons_media_asset_id || null,
      horizons_shot_version_id: refs.horizons_shot_version_id || null,
    })
  }

  async function requestCommentPreviews(targets, signal = null) {
    const body = { targets }
    const shareId = ctx.shareMode?.value ? ctx.pendingShareId?.value : null
    if (!shareId) {
      const projectId = getCommentProjectId(ctx)
      if (projectId) body.project_id = projectId
    }
    const query = buildShareCredentialQuery(
      shareId ? { share_id: shareId } : {},
      getShareCredential(ctx),
    )
    const { data } = await api.post(`/api/comments/previews/batch${query}`, body, { signal })
    return data?.items || []
  }

  function normalizeCommentPreview(value) {
    const previewText = sanitizeUiText(value || EMPTY_BRIEF_PREVIEW)
    return previewText && previewText !== LEGACY_EMPTY_COMMENT_PREVIEW
      ? previewText
      : EMPTY_BRIEF_PREVIEW
  }

  async function refreshCurrentMediaPreview(target = getCurrentMediaPreviewTarget()) {
    if (!target?.key) return
    const requestId = ++briefPreviewRequestId
    briefPreviewLoading[target.key] = true
    try {
      const items = await requestCommentPreviews([target])
      if (requestId !== briefPreviewRequestId) return
      const item = items.find(candidate => candidate?.key === target.key)
      briefPreviewCache[target.key] = normalizeCommentPreview(item?.preview)
    } catch (error) {
      console.error('Failed to refresh tracker comment preview')
    } finally {
      delete briefPreviewLoading[target.key]
    }
  }

  async function notifyTrackerActivityChanged() {
    const target = getCurrentMediaPreviewTarget()
    const tracker = getOptionalRefValue(ctx.currentTracker)
    const trackerTargets = getTrackerPreviewTargets(tracker)
    if (target?.key && trackerTargets.some(candidate => candidate.key === target.key)) {
      await loadTrackerBriefPreviews(tracker)
    } else {
      await refreshCurrentMediaPreview(target)
    }
    if (typeof ctx.onTrackerActivityChanged !== 'function') return
    try {
      await ctx.onTrackerActivityChanged({
        target,
        count: countCommentThreads(comments.value),
      })
    } catch (error) {
      console.error('Failed to refresh tracker activity after comment update')
    }
  }

  async function toggleResolve(id) {
    const query = buildShareCredentialQuery(
      ctx.shareMode?.value && ctx.pendingShareId?.value ? { share_id: ctx.pendingShareId.value } : {},
      getShareCredential(ctx),
    )
    await api.post(`/api/comments/${id}/resolve${query}`, null)
    await loadComments()
    await notifyTrackerActivityChanged()
  }

  async function deleteComment(id) {
    if (!confirm('Delete this comment?')) return
    try {
      await api.delete(`/api/comments/${id}`)
      await loadComments()
      await notifyTrackerActivityChanged()
    } catch (e) {
      ctx.handleError?.('Failed to delete comment', e)
    }
  }

  function startReply(comment) {
    if (!comment?.id) return
    const rootId = comment.root_comment_id || comment.parent_comment_id || comment.id
    const root = comments.value.find(item => item.id === rootId) || comment
    replyTarget.value = {
      id: root.id,
      user_name: comment.user_name || root.user_name || 'comment',
    }
  }

  function cancelReply() {
    replyTarget.value = null
  }

  async function postMediaComment() {
    const currentUser = getOptionalRefValue(ctx.currentUser)
    const name = currentUser?.display_name || normalizeStoredCommenterName(userName.value || userNameInput.value)
    if (!name) return notify('Please enter your name')

    const hasText = !!newComment.value.trim()
    const hasAnnotation = !!ctx.pendingAnnotation?.value
    const hasVoiceNote = !!voiceRecorder.pendingVoiceNote.value
    const activeInlineMentions = mentionContext.value.enabled
      ? pendingInlineMentions.value.filter(mention => textRendersMentionMarker(newComment.value, mention))
      : []
    pendingInlineMentions.value = activeInlineMentions
    const hasAttachments = pendingCommentAttachments.value.length > 0 || activeInlineMentions.length > 0 || hasVoiceNote
    if (!hasText && !hasAnnotation && !hasAttachments) return
    if (!ctx.currentVideo?.value) return

    if (!currentUser) {
      localStorage.setItem('vueio_user', name)
      userName.value = name
    }

    const query = buildShareCredentialQuery(
      ctx.shareMode?.value && ctx.pendingShareId?.value ? { share_id: ctx.pendingShareId.value } : {},
      getShareCredential(ctx),
    )
    const projectId = getCommentProjectId(ctx)
    const commentPath = getCommentPath(ctx)
    const targetRefs = getCommentTargetRefs(ctx)
    const annotationTarget = getOptionalRefValue(ctx.pendingAnnotationTarget)
    const parentCommentId = replyTarget.value?.id || null
    if (commentPosting.value) return
    commentPosting.value = true
    try {
      if (hasAttachments) {
        const voiceNote = voiceRecorder.pendingVoiceNote.value
        if (!hasText && !hasAnnotation && !pendingCommentAttachments.value.length && !voiceNote) return
        const commentTimestamp = resolveCommentTimestamp(ctx, { hasAnnotation })
        const formData = new FormData()
        formData.append('path', commentPath)
        formData.append('user_name', name)
        formData.append('text', newComment.value || '')
        formData.append('timestamp', String(commentTimestamp))
        if (parentCommentId) {
          formData.append('parent_comment_id', String(parentCommentId))
        }
        if (ctx.pendingAnnotation?.value) {
          formData.append('annotation_data', ctx.pendingAnnotation.value)
        }
        if (annotationTarget) {
          formData.append('annotation_target', annotationTarget)
        }

        if (projectId) {
          formData.append('project_id', projectId)
        }
        if (targetRefs.horizons_media_asset_id) {
          formData.append('horizons_media_asset_id', targetRefs.horizons_media_asset_id)
        }
        if (targetRefs.horizons_shot_version_id) {
          formData.append('horizons_shot_version_id', targetRefs.horizons_shot_version_id)
        }

        for (const att of pendingCommentAttachments.value) {
          const file = att?.file
          if (!file) {
            continue
          }
          const isValidFile = file instanceof File || file instanceof Blob
          if (isValidFile) {
            const filename = file.name || att?.name || 'attachment'
            formData.append('files', file, filename)
          }
        }
        if (voiceNote?.blob) {
          formData.append('files', voiceNote.blob, voiceNote.name)
          formData.append('voice_note', JSON.stringify({
            filename: voiceNote.name,
            duration: voiceNote.duration,
            peaks: voiceNote.peaks,
          }))
        }
        const references = pendingCommentAttachments.value
          .filter(att => att?.attachment_type === 'reference')
          .map(att => ({ target_type: att.target_type, target_id: att.target_id }))
        references.push(...activeInlineMentions.map(mention => ({
          target_type: mention.target_type,
          target_id: mention.target_id,
          marker: mention.marker,
        })))
        if (references.length) {
          formData.append('linked_attachments', JSON.stringify(references))
        }

        await api.post(`/api/comments/with-attachments${query}`, formData)
      } else {
        const commentTimestamp = resolveCommentTimestamp(ctx, { hasAnnotation })
        await api.post(`/api/comments${query}`, {
          path: commentPath,
          project_id: projectId || undefined,
          horizons_media_asset_id: targetRefs.horizons_media_asset_id || undefined,
          horizons_shot_version_id: targetRefs.horizons_shot_version_id || undefined,
          user_name: name,
          text: newComment.value,
          timestamp: commentTimestamp,
          annotation_data: ctx.pendingAnnotation?.value || null,
          annotation_target: annotationTarget || null,
          parent_comment_id: parentCommentId || undefined
        })
      }
    } catch (e) {
      console.error('Failed to post comment')
      const status = e?.response?.status
      const msg = getApiErrorMessage(e)
      notify(`Failed to post comment${status ? ` (${status})` : ''}: ${msg}`)
      return
    } finally {
      commentPosting.value = false
    }

    resetCommentDraft()
    notify(parentCommentId ? 'Reply posted.' : 'Comment posted.', { tone: 'success' })
    await loadComments()
    await notifyTrackerActivityChanged()
  }

  function handleCommentClick(comment) {
    if (ctx.isViewingImage?.value) {
      if (comment.annotation_data) {
        showAnnotationFromData(comment.annotation_data)
      } else {
        ctx.clearAnnotationPreview?.()
      }
    } else {
      ctx.seekToComment?.(comment)
    }
  }

  function getSortedShotVersions(shot) {
    if (typeof ctx.getShotVersions === 'function') return ctx.getShotVersions(shot) || []
    return [...(shot?.versions || [])].sort((a, b) => {
      const vA = Number(a?.version || a?.label || 0)
      const vB = Number(b?.version || b?.label || 0)
      if (Number.isFinite(vA) && Number.isFinite(vB) && vA !== vB) return vA - vB
      const tA = Number(a?.created_at || 0)
      const tB = Number(b?.created_at || 0)
      if (tA !== tB) return tA - tB
      return String(a?.label ?? a?.version ?? '').localeCompare(String(b?.label ?? b?.version ?? ''))
    })
  }

  function getBriefMediaFile(shot) {
    if (!shot) return null
    const versions = getSortedShotVersions(shot)
    return versions[0] || null
  }

  function getLatestMediaFile(shot) {
    if (!shot) return null
    const versions = getSortedShotVersions(shot)
    return versions[versions.length - 1] || null
  }

  function getVersionPreviewTarget(version) {
    const path = version?.file_path || version?.path || ''
    if (!path) return null
    return buildCommentBatchTarget({
      path,
      horizons_media_asset_id: version.media_asset_id || null,
      horizons_shot_version_id: version.id || null,
    })
  }

  function getBriefPreviewTarget(shot) {
    return getVersionPreviewTarget(getBriefMediaFile(shot))
  }

  function getLatestPreviewTarget(shot) {
    return getVersionPreviewTarget(getLatestMediaFile(shot))
  }

  function getTrackerPreviewTargets(tracker) {
    const targetMap = new Map()
    for (const shot of tracker?.shots || []) {
      for (const target of [getBriefPreviewTarget(shot), getLatestPreviewTarget(shot)]) {
        if (target?.key && !targetMap.has(target.key)) targetMap.set(target.key, target)
      }
    }
    return Array.from(targetMap.values())
  }

  async function loadTrackerBriefPreviews(tracker) {
    const targets = getTrackerPreviewTargets(tracker)
    if (!targets.length) return

    for (const target of targets) {
      briefPreviewLoading[target.key] = true
    }

    const requestId = ++briefPreviewRequestId
    const targetChunks = chunkCommentTargets(targets)
    briefPreviewAbortController?.abort()
    const controller = new AbortController()
    briefPreviewAbortController = controller
    try {
      const merged = {}
      const responses = await Promise.all(
        targetChunks.map(chunk => requestCommentPreviews(chunk, controller.signal)),
      )
      if (requestId !== briefPreviewRequestId) return
      for (const items of responses) {
        for (const item of items) {
          if (!item?.key) continue
          merged[item.key] = normalizeCommentPreview(item.preview)
        }
      }

      for (const target of targets) {
        briefPreviewCache[target.key] = merged[target.key] || EMPTY_BRIEF_PREVIEW
      }
    } catch (error) {
      if (isCanceledRequest(error, controller.signal)) return
      console.error('Failed to load tracker brief previews')
      for (const target of targets) {
        briefPreviewCache[target.key] = EMPTY_BRIEF_PREVIEW
      }
    } finally {
      if (briefPreviewAbortController === controller) briefPreviewAbortController = null
      for (const target of targets) {
        delete briefPreviewLoading[target.key]
      }
    }
  }

  function getBriefPreviewText(shot) {
    const target = getBriefPreviewTarget(shot)
    if (!target?.path) return 'No V1 uploaded yet.'
    const cached = briefPreviewCache[target.key]
    return cached === undefined ? 'Loading comments...' : cached
  }

  function isBriefPreviewEmpty(shot) {
    const target = getBriefPreviewTarget(shot)
    if (!target?.path) return true
    const cached = briefPreviewCache[target.key]
    return cached === undefined || cached === EMPTY_BRIEF_PREVIEW
  }

  function getLatestPreviewText(shot) {
    const target = getLatestPreviewTarget(shot)
    if (!target?.path) return 'No latest version yet.'
    const cached = briefPreviewCache[target.key]
    return cached === undefined ? 'Loading comments...' : cached
  }

  function isLatestPreviewEmpty(shot) {
    const target = getLatestPreviewTarget(shot)
    if (!target?.path) return true
    const cached = briefPreviewCache[target.key]
    return cached === undefined || cached === EMPTY_BRIEF_PREVIEW
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      commentAbortController?.abort()
      briefPreviewAbortController?.abort()
      clearVoiceTranscriptRefresh()
    })
  }

  return {
    comments,
    newComment,
    commentPosting,
    userNameInput,
    userName,
    pendingCommentAttachments,
    pendingInlineMentions,
    mentionContext,
    pendingVoiceNote: voiceRecorder.pendingVoiceNote,
    voiceRecorderState: voiceRecorder.state,
    voiceRecorderSupported: voiceRecorder.isSupported,
    voiceRecorderElapsed: voiceRecorder.elapsedSeconds,
    voiceRecorderLevels: voiceRecorder.levels,
    attachmentLightbox,
    showAnnotationPreview,
    replyTarget,
    resetCommentDraft,
    resetMediaCommentState,
    getCommentAttachmentUrl,
    handleCommentAttachmentChange,
    addPendingCommentReferences,
    addPendingInlineMention,
    removePendingCommentAttachment,
    clearPendingCommentAttachments,
    clearPendingInlineMentions,
    startVoiceRecording,
    stopVoiceRecording: voiceRecorder.stopRecording,
    cancelVoiceRecording: voiceRecorder.cancelRecording,
    removePendingVoiceNote: voiceRecorder.removeVoiceNote,
    openAttachmentLightbox,
    closeAttachmentLightbox,
    showAnnotationFromData,
    loadComments,
    toggleResolve,
    deleteComment,
    startReply,
    cancelReply,
    postMediaComment,
    handleCommentClick,
    getBriefMediaFile,
    loadTrackerBriefPreviews,
    getBriefPreviewText,
    isBriefPreviewEmpty,
    getLatestPreviewText,
    isLatestPreviewEmpty,
    countCommentThreads,
  }
}
