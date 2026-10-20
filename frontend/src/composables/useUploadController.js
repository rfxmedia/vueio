import { ref, watch } from 'vue'
import api from '../lib/api'

import { useResumableUploadQueue } from './useResumableUploadQueue'

const DEFAULT_UPLOAD_TITLE = 'Upload files'
const DEFAULT_UPLOAD_DESCRIPTION = 'Upload files or drop folders from your device into this folder.'

export function useUploadController({
  canUpload,
  disabledReason = ref(''),
  getDefaultTargetPath,
  getTargetLabel,
  getUploadScope = () => '',
  getUploadEndpoint,
  missingTargetMessage = 'Upload destination is unavailable',
  getUploaderName = value => value,
  refreshContents,
  requiresUploaderName = false,
  uploaderNameStorageKey = '',
}) {
  const uploadTargetOverride = ref('')
  const uploadCompleteHandler = ref(null)
  const uploadModalTitle = ref(DEFAULT_UPLOAD_TITLE)
  const uploadModalDescription = ref(DEFAULT_UPLOAD_DESCRIPTION)
  const notifiedCompletedItems = new WeakSet()
  // Each session keeps the project or share it started in, so navigating away
  // mid-upload cannot send its remaining chunks somewhere else.
  const sessionScopes = new Map()

  function getActiveTargetPath() {
    return uploadTargetOverride.value || getDefaultTargetPath() || ''
  }

  function resolveEndpoint(suffix = '', scope = getUploadScope(), required = true) {
    const endpoint = getUploadEndpoint(suffix, scope)
    if (endpoint || !required) return endpoint
    throw new Error(missingTargetMessage)
  }

  function sessionEndpoint(sessionId, suffix = '', required = true) {
    const scope = sessionScopes.has(sessionId) ? sessionScopes.get(sessionId) : getUploadScope()
    return resolveEndpoint(`/${sessionId}${suffix}`, scope, required)
  }

  const upload = useResumableUploadQueue({
    canUpload,
    getDefaultTargetPath: getActiveTargetPath,
    getTargetLabel,
    createSessionRequest: async ({ uploaderName, clientBatchId, targetPath, files }) => {
      const scope = getUploadScope()
      const { data } = await api.post(resolveEndpoint('', scope), {
        uploader_name: getUploaderName(uploaderName),
        client_batch_id: clientBatchId,
        target_path: targetPath || '',
        files,
      })
      if (data?.id) sessionScopes.set(data.id, scope)
      return data
    },
    getSessionRequest: async (sessionId) => {
      const { data } = await api.get(sessionEndpoint(sessionId))
      return data
    },
    sendChunkRequest: async ({ sessionId, itemId, offset, chunk, signal, onProgress }) => {
      const { data } = await api.patch(
        sessionEndpoint(sessionId, `/items/${itemId}`),
        chunk,
        {
          signal,
          headers: {
            'Content-Type': 'application/offset+octet-stream',
            'Upload-Offset': offset,
          },
          onUploadProgress: onProgress,
        },
      )
      return data
    },
    cancelItemRequest: async ({ sessionId, itemId }) => {
      const endpoint = sessionEndpoint(sessionId, `/items/${itemId}`, false)
      if (endpoint) await api.delete(endpoint)
    },
    cancelSessionRequest: async ({ sessionId }) => {
      const endpoint = sessionEndpoint(sessionId, '', false)
      if (endpoint) await api.delete(endpoint)
    },
    refreshContents,
    requiresUploaderName,
    uploaderNameStorageKey,
  })

  function openUpload({
    targetPath = '',
    title = DEFAULT_UPLOAD_TITLE,
    description = DEFAULT_UPLOAD_DESCRIPTION,
    onCompleted = null,
  } = {}) {
    uploadTargetOverride.value = String(targetPath || '')
    uploadCompleteHandler.value = typeof onCompleted === 'function' ? onCompleted : null
    uploadModalTitle.value = title || DEFAULT_UPLOAD_TITLE
    uploadModalDescription.value = description || DEFAULT_UPLOAD_DESCRIPTION
    return upload.openUploadModal()
  }

  function handleFileUpload(event, targetPath = getActiveTargetPath()) {
    return upload.handleFileUpload(event, targetPath)
  }

  function handleExternalDrop(event, targetPath = getActiveTargetPath()) {
    return upload.handleExternalDrop(event, targetPath)
  }

  watch(() => upload.uploadQueue.value.filter(item => item.status === 'done'), (items) => {
    const onCompleted = uploadCompleteHandler.value
    if (!onCompleted) return
    const completed = []
    for (const item of items || []) {
      if (notifiedCompletedItems.has(item)) continue
      notifiedCompletedItems.add(item)
      completed.push({
        path: item.finalPath || [item.targetFolder, item.relPath].filter(Boolean).join('/'),
        name: item.name || item.relPath,
        relPath: item.relPath,
      })
    }
    if (completed.length) onCompleted(completed)
  })

  return {
    ...upload,
    uploadModalTitle,
    uploadModalDescription,
    uploadDisabledReason: disabledReason,
    requiresUploaderName,
    openUpload,
    handleFileUpload,
    handleExternalDrop,
  }
}
