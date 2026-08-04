import { computed, ref, watch } from 'vue'
import { getApiErrorDetail, getApiErrorMessage } from '../lib/api'
import { formatSizeBytes } from '../utils/formatters'
import { clamp } from '../utils/math'

const DEFAULT_UPLOAD_CHUNK_SIZE = 1 * 1024 * 1024
const DEFAULT_UPLOAD_MAX_CHUNK_SIZE = 8 * 1024 * 1024
const UPLOAD_FAST_CHUNK_MS = 4000
const UPLOAD_SLOW_CHUNK_MS = 30000
const UPLOAD_CONCURRENCY = 3
const UPLOAD_MAX_RETRIES = 4
const UPLOAD_DROP_HANDLED_FLAG = '__vueioUploadDropHandled'
const UPLOAD_BATCH_DEDUPE_TTL_MS = 2500

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function normalizeUploadRelPath(relPath) {
  return String(relPath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .split('/')
    .filter(part => part && part !== '.' && part !== '..')
    .join('/')
}

function joinUploadPath(base, subpath) {
  const a = normalizeUploadRelPath(base)
  const b = normalizeUploadRelPath(subpath)
  if (!a && !b) return ''
  if (!a) return b
  if (!b) return a
  return `${a}/${b}`
}

function isExternalFileDrag(event) {
  const types = Array.from(event?.dataTransfer?.types || [])
  return types.includes('Files') || (event?.dataTransfer?.files?.length || 0) > 0
}

function isUploadDropHandled(event) {
  return Boolean(event?.[UPLOAD_DROP_HANDLED_FLAG])
}

function markUploadDropHandled(event) {
  if (!event) return
  event.preventDefault?.()
  event.stopPropagation?.()
  try {
    event[UPLOAD_DROP_HANDLED_FLAG] = true
  } catch (_) {}
}

function containUploadDragEvent(event) {
  if (!event) return
  event.preventDefault?.()
  event.stopPropagation?.()
}

function isJunkUploadName(name) {
  const normalized = String(name || '').toLowerCase()
  if (!normalized) return true
  return normalized === '.ds_store' || normalized === 'thumbs.db' || normalized === 'desktop.ini' || normalized.startsWith('._')
}

async function readDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const entries = []
    const readNext = () => {
      reader.readEntries(batch => {
        if (!batch.length) return resolve(entries)
        entries.push(...batch)
        readNext()
      }, reject)
    }
    readNext()
  })
}

async function walkDataTransferEntry(entry, parentPath = '') {
  if (!entry) return []
  if (entry.isFile) {
    return new Promise((resolve, reject) => {
      entry.file(file => {
        resolve([{ file, relPath: `${parentPath}${entry.name}` }])
      }, reject)
    })
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    const entries = await readDirectoryEntries(reader)
    let results = []
    const dirPath = `${parentPath}${entry.name}/`
    for (const child of entries) {
      const nested = await walkDataTransferEntry(child, dirPath)
      if (nested.length) results = results.concat(nested)
    }
    return results
  }
  return []
}

async function extractDroppedFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || [])
  let results = []

  if (items.length && items.some(item => typeof item.webkitGetAsEntry === 'function')) {
    for (const item of items) {
      const entry = item.webkitGetAsEntry?.()
      if (!entry) continue
      const nested = await walkDataTransferEntry(entry, '')
      if (nested.length) results = results.concat(nested)
    }
  } else {
    const files = Array.from(dataTransfer?.files || [])
    results = files.map(file => ({
      file,
      relPath: normalizeUploadRelPath(file.webkitRelativePath || file.name),
    }))
  }

  return results.filter(({ file, relPath }) => file && !isJunkUploadName(file.name || relPath))
}

function extractSelectedFiles(inputFiles) {
  return Array.from(inputFiles || [])
    .map(file => ({
      file,
      relPath: normalizeUploadRelPath(file.webkitRelativePath || file.name),
    }))
    .filter(({ file, relPath }) => file && relPath && !isJunkUploadName(file.name || relPath))
}

function extractExpectedOffset(error) {
  const detail = getApiErrorDetail(error)
  if (!detail || typeof detail !== 'object') return null
  const value = Number(detail.expected_offset)
  return Number.isFinite(value) ? value : null
}

function isTransientUploadError(error) {
  const status = error?.response?.status
  return !status || [408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 523, 524].includes(status)
}

function normalizeChunkSize(value, minSize, maxSize) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return minSize
  return clamp(Math.round(numeric), minSize, maxSize)
}

function nextAdaptiveChunkSize(currentSize, durationMs, minSize, maxSize) {
  const current = normalizeChunkSize(currentSize, minSize, maxSize)
  if (durationMs <= UPLOAD_FAST_CHUNK_MS && current < maxSize) {
    return normalizeChunkSize(current * 2, minSize, maxSize)
  }
  if (durationMs >= UPLOAD_SLOW_CHUNK_MS && current > minSize) {
    return normalizeChunkSize(Math.ceil(current / 2), minSize, maxSize)
  }
  return current
}

function formatUploadDuration(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0))
  if (value < 1) return '<1s'
  if (value < 60) return `${value}s`
  const minutes = Math.floor(value / 60)
  const remainingSeconds = value % 60
  if (minutes < 60) return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

export function useResumableUploadQueue({
  canUpload,
  getDefaultTargetPath,
  getTargetLabel,
  createSessionRequest,
  getSessionRequest,
  sendChunkRequest,
  cancelItemRequest,
  cancelSessionRequest,
  refreshContents,
  requiresUploaderName = false,
  uploaderNameStorageKey = '',
}) {
  const resolvedUploaderNameStorageKey = computed(() =>
    typeof uploaderNameStorageKey === 'function' ? uploaderNameStorageKey() : (uploaderNameStorageKey || '')
  )
  const showUploadModal = ref(false)
  const uploadQueue = ref([])
  const uploadInFlight = ref(0)
  const uploadDragDepth = ref(0)
  const uploadDragActive = ref(false)
  const uploadDragTarget = ref('')
  const uploadModalDragActive = ref(false)
  const uploaderName = ref('')
  const uploaderNameError = ref('')
  const uploadError = ref('')
  let uploadRefreshTimer = null
  const recentBatchFingerprints = new Map()

  function updateItemTransferLabels(item) {
    if (!item) return
    const uploadedBytes = clamp(item.displayBytesUploaded ?? item.bytesUploaded ?? 0, 0, item.size || 0)
    const totalBytes = item.size || 0
    item.uploadedLabel = `${formatSizeBytes(uploadedBytes)} / ${formatSizeBytes(totalBytes)}`

    const speed = Number(item.speedBytesPerSecond || 0)
    const isActive = ['uploading', 'retrying'].includes(item.status)
    item.speedLabel = isActive && speed > 0 ? `${formatSizeBytes(speed)}/s` : ''

    const remainingBytes = Math.max(0, totalBytes - uploadedBytes)
    item.etaLabel = isActive && speed > 0 && remainingBytes > 0
      ? `${formatUploadDuration(remainingBytes / speed)} left`
      : ''
  }

  function updateItemTransferProgress(item, uploadedBytes, now = performance.now()) {
    if (!item) return
    const clampedUploaded = clamp(uploadedBytes || 0, 0, item.size || 0)
    const previousBytes = Number(item.lastTransferBytes || 0)
    const previousAt = Number(item.lastTransferAt || 0)
    if (previousAt && now > previousAt && clampedUploaded > previousBytes) {
      const instantSpeed = ((clampedUploaded - previousBytes) / (now - previousAt)) * 1000
      item.speedBytesPerSecond = item.speedBytesPerSecond
        ? (item.speedBytesPerSecond * 0.7) + (instantSpeed * 0.3)
        : instantSpeed
    }
    item.lastTransferBytes = clampedUploaded
    item.lastTransferAt = now
    item.displayBytesUploaded = clampedUploaded
    item.progress = item.size ? Math.min(100, Math.round((clampedUploaded / item.size) * 100)) : 100
    updateItemTransferLabels(item)
  }

  const canUploadNow = computed(() => Boolean(canUpload.value))

  const uploadHasActive = computed(() =>
    uploadQueue.value.some(item => ['pending', 'uploading', 'retrying'].includes(item.status))
  )

  const uploadHasRemovable = computed(() =>
    uploadQueue.value.some(item => ['done', 'error', 'canceled'].includes(item.status))
  )

  const uploadSummary = computed(() => {
    const items = uploadQueue.value
    const total = items.length
    const done = items.filter(item => item.status === 'done').length
    const totalBytes = items.reduce((sum, item) => sum + (item.size || 0), 0)
    const uploadedBytes = items.reduce((sum, item) => sum + (item.displayBytesUploaded ?? item.bytesUploaded ?? 0), 0)
    const pct = totalBytes ? Math.round((uploadedBytes / totalBytes) * 100) : 0
    const activeSpeed = items
      .filter(item => ['uploading', 'retrying'].includes(item.status))
      .reduce((sum, item) => sum + (Number(item.speedBytesPerSecond) || 0), 0)
    const remainingBytes = Math.max(0, totalBytes - uploadedBytes)
    return {
      label: total ? `${done}/${total} files` : 'No uploads yet',
      size: totalBytes ? formatSizeBytes(totalBytes) : '0 B',
      progress: total ? `${pct}%` : '0%',
      speed: activeSpeed > 0 ? `${formatSizeBytes(activeSpeed)}/s` : '',
      eta: activeSpeed > 0 && remainingBytes > 0 ? `${formatUploadDuration(remainingBytes / activeSpeed)} left` : '',
    }
  })

  const uploadDropLabel = computed(() => {
    const targetPath = uploadDragTarget.value || getDefaultTargetPath()
    return getTargetLabel ? getTargetLabel(targetPath) : (targetPath || 'Current folder')
  })

  function loadStoredUploaderName() {
    if (typeof localStorage === 'undefined') return
    const storageKey = resolvedUploaderNameStorageKey.value
    uploaderName.value = storageKey ? (localStorage.getItem(storageKey) || '') : ''
  }

  loadStoredUploaderName()
  watch(resolvedUploaderNameStorageKey, () => {
    loadStoredUploaderName()
  })

  function persistUploaderName() {
    if (typeof localStorage === 'undefined') return
    const storageKey = resolvedUploaderNameStorageKey.value
    if (!storageKey) return
    localStorage.setItem(storageKey, uploaderName.value || '')
  }

  function setUploaderName(value) {
    uploaderName.value = String(value || '')
    uploaderNameError.value = ''
    uploadError.value = ''
    persistUploaderName()
  }

  function openUploadModal() {
    if (!canUploadNow.value) return false
    uploadError.value = ''
    showUploadModal.value = true
    return true
  }

  function closeUploadModal() {
    showUploadModal.value = false
  }

  function scheduleRefresh() {
    if (uploadRefreshTimer) return
    uploadRefreshTimer = setTimeout(async () => {
      uploadRefreshTimer = null
      await refreshContents?.()
    }, 600)
  }

  async function syncItemFromServer(item) {
    if (!item?.sessionId || !item?.itemId || typeof getSessionRequest !== 'function') return
    try {
      const data = await getSessionRequest(item.sessionId)
      const serverItem = (data?.items || []).find(entry => entry.id === item.itemId)
      if (!serverItem) return
      item.bytesUploaded = serverItem.bytes_received || 0
      item.displayBytesUploaded = item.bytesUploaded
      item.finalPath = serverItem.final_path || item.finalPath || ''
      item.progress = item.size ? Math.min(100, Math.round((item.bytesUploaded / item.size) * 100)) : 100
      if (serverItem.status === 'complete') {
        item.status = 'done'
        item.progress = 100
        item.bytesUploaded = item.size
        item.displayBytesUploaded = item.size
      }
      updateItemTransferLabels(item)
    } catch {
      // Keep best-effort sync quiet.
    }
  }

  async function uploadQueueItem(item) {
    item.status = 'uploading'
    item.error = ''
    uploadInFlight.value += 1

    try {
      while ((item.bytesUploaded || 0) < (item.size || 0)) {
        if (item.status === 'canceled') return
        const offset = item.bytesUploaded || 0
        const minChunkSize = item.minChunkSize || DEFAULT_UPLOAD_CHUNK_SIZE
        const maxChunkSize = item.maxChunkSize || DEFAULT_UPLOAD_MAX_CHUNK_SIZE
        const chunkSize = normalizeChunkSize(item.chunkSize, minChunkSize, maxChunkSize)
        const nextChunk = item.file?.slice(offset, offset + chunkSize)
        if (!nextChunk) {
          item.status = 'error'
          item.error = 'File handle is no longer available'
          return
        }

        const controller = new AbortController()
        item.controller = controller

        try {
          const chunkStartedAt = performance.now()
          updateItemTransferProgress(item, offset, chunkStartedAt)
          const response = await sendChunkRequest({
            sessionId: item.sessionId,
            itemId: item.itemId,
            offset,
            chunk: nextChunk,
            signal: controller.signal,
            onProgress: (event) => {
              const loaded = Math.min(nextChunk.size, Number(event?.loaded || 0))
              updateItemTransferProgress(item, offset + loaded)
            },
          })
          item.controller = null
          item.bytesUploaded = response?.next_offset ?? response?.item?.bytes_received ?? (offset + nextChunk.size)
          item.displayBytesUploaded = item.bytesUploaded
          item.finalPath = response?.item?.final_path || item.finalPath || ''
          item.progress = item.size ? Math.min(100, Math.round((item.bytesUploaded / item.size) * 100)) : 100
          updateItemTransferProgress(item, item.bytesUploaded)
          item.chunkSize = nextAdaptiveChunkSize(chunkSize, performance.now() - chunkStartedAt, minChunkSize, maxChunkSize)
          item.retries = 0
          item.status = item.bytesUploaded >= item.size ? 'done' : 'uploading'
        } catch (error) {
          item.controller = null
          const isCanceled = controller.signal.aborted || error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError'
          if (isCanceled) {
            item.status = 'canceled'
            item.error = ''
            return
          }

          const expectedOffset = extractExpectedOffset(error)
          if (expectedOffset !== null) {
            item.bytesUploaded = expectedOffset
            item.displayBytesUploaded = expectedOffset
            updateItemTransferProgress(item, expectedOffset)
            continue
          }

          if (isTransientUploadError(error) && item.retries < UPLOAD_MAX_RETRIES) {
            item.retries += 1
            item.status = 'retrying'
            item.error = 'Retrying...'
          item.chunkSize = normalizeChunkSize(Math.ceil(chunkSize / 2), minChunkSize, maxChunkSize)
            await sleep(Math.min(8000, 800 * Math.pow(2, item.retries)))
            await syncItemFromServer(item)
            if (item.status !== 'done') item.status = 'uploading'
            continue
          }

          item.status = 'error'
          item.error = getApiErrorMessage(error, 'Upload failed')
          return
        }
      }

      item.status = 'done'
      item.progress = 100
      item.bytesUploaded = item.size || 0
      item.displayBytesUploaded = item.bytesUploaded
      updateItemTransferLabels(item)
      scheduleRefresh()
    } finally {
      item.controller = null
      uploadInFlight.value = Math.max(0, uploadInFlight.value - 1)
      startUploadWorker()
      if (!uploadHasActive.value) scheduleRefresh()
    }
  }

  function startUploadWorker() {
    while (uploadInFlight.value < UPLOAD_CONCURRENCY) {
      const next = uploadQueue.value.find(item => item.status === 'pending')
      if (!next) break
      uploadQueueItem(next)
    }
  }

  async function enqueueUploads(entries, baseTargetFolder = '') {
    if (!canUploadNow.value) return
    uploadError.value = ''
    if (requiresUploaderName && !String(uploaderName.value || '').trim()) {
      uploaderNameError.value = 'Please enter your name before uploading.'
      showUploadModal.value = true
      return
    }

    const filteredEntries = (entries || []).filter(entry => {
      const relPath = normalizeUploadRelPath(entry?.relPath || entry?.file?.webkitRelativePath || entry?.file?.name)
      return entry?.file && relPath && !isJunkUploadName(relPath)
    })
    if (!filteredEntries.length) return

    const normalizedBaseTargetFolder = normalizeUploadRelPath(baseTargetFolder || getDefaultTargetPath())
    const now = Date.now()
    for (const [fingerprint, expiresAt] of recentBatchFingerprints.entries()) {
      if (expiresAt <= now) recentBatchFingerprints.delete(fingerprint)
    }
    const batchFingerprint = JSON.stringify({
      target: normalizedBaseTargetFolder,
      files: filteredEntries
        .map(entry => ({
          relPath: normalizeUploadRelPath(entry.relPath || entry.file.webkitRelativePath || entry.file.name),
          name: entry.file.name,
          size: entry.file.size || 0,
          modified: entry.file.lastModified || 0,
        }))
        .sort((a, b) => a.relPath.localeCompare(b.relPath) || a.name.localeCompare(b.name)),
    })
    if (recentBatchFingerprints.has(batchFingerprint)) return
    recentBatchFingerprints.set(batchFingerprint, now + UPLOAD_BATCH_DEDUPE_TTL_MS)
    const clientBatchId = `batch_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
    const manifest = filteredEntries.map(entry => ({
      rel_path: normalizeUploadRelPath(entry.relPath || entry.file.webkitRelativePath || entry.file.name),
      original_name: entry.file.name,
      mime_type: entry.file.type || '',
      size_bytes: entry.file.size || 0,
    }))

    let session
    try {
      session = await createSessionRequest({
        uploaderName: uploaderName.value,
        clientBatchId,
        targetPath: normalizedBaseTargetFolder,
        files: manifest,
      })
    } catch (error) {
      showUploadModal.value = true
      uploadError.value = getApiErrorMessage(error, 'Failed to start upload')
      return
    }

    const itemMap = new Map((session?.items || []).map(item => [item.rel_path, item]))
    let added = 0
    for (const entry of filteredEntries) {
      const relPath = normalizeUploadRelPath(entry.relPath || entry.file.webkitRelativePath || entry.file.name)
      const serverItem = itemMap.get(relPath)
      if (!serverItem) continue
      uploadQueue.value.push({
        id: `up_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
        sessionId: session.id,
        itemId: serverItem.id,
        file: entry.file,
        name: entry.file.name,
        size: entry.file.size || 0,
        relPath,
        targetFolder: normalizedBaseTargetFolder,
        finalPath: serverItem.final_path || joinUploadPath(normalizedBaseTargetFolder, relPath),
        minChunkSize: session?.chunk_size || DEFAULT_UPLOAD_CHUNK_SIZE,
        maxChunkSize: session?.max_chunk_size || DEFAULT_UPLOAD_MAX_CHUNK_SIZE,
        chunkSize: session?.chunk_size || DEFAULT_UPLOAD_CHUNK_SIZE,
        status: serverItem.status === 'complete' ? 'done' : 'pending',
        progress: entry.file.size ? Math.min(100, Math.round(((serverItem.bytes_received || 0) / entry.file.size) * 100)) : 100,
        uploadedLabel: `${formatSizeBytes(serverItem.bytes_received || 0)} / ${formatSizeBytes(entry.file.size || 0)}`,
        speedLabel: '',
        etaLabel: '',
        speedBytesPerSecond: 0,
        displayBytesUploaded: serverItem.bytes_received || 0,
        lastTransferBytes: serverItem.bytes_received || 0,
        lastTransferAt: 0,
        error: '',
        retries: 0,
        controller: null,
        bytesUploaded: serverItem.bytes_received || 0,
      })
      added += 1
    }

    if (added > 0) {
      showUploadModal.value = true
      startUploadWorker()
    }
  }

  function cancelUpload(item) {
    if (!item) return
    if (item.status === 'uploading' && item.controller) {
      item.controller.abort()
    }
    if (item.sessionId && item.itemId) {
      cancelItemRequest({ sessionId: item.sessionId, itemId: item.itemId }).catch(() => {})
    }
    item.status = 'canceled'
    item.error = ''
  }

  function cancelAllUploads() {
    const itemsToCancel = uploadQueue.value.filter(item => !['done', 'canceled'].includes(item.status))
    const sessionIds = new Set()

    for (const item of itemsToCancel) {
      if (item.status === 'uploading' && item.controller) {
        item.controller.abort()
      }
      if (item.sessionId) {
        sessionIds.add(item.sessionId)
      }
      item.status = 'canceled'
      item.error = ''
    }

    if (typeof cancelSessionRequest === 'function') {
      for (const sessionId of sessionIds) {
        cancelSessionRequest({ sessionId }).catch(() => {})
      }
      return
    }

    for (const item of itemsToCancel) {
      if (!item.sessionId || !item.itemId) continue
      cancelItemRequest({ sessionId: item.sessionId, itemId: item.itemId }).catch(() => {})
    }
  }

  function retryUpload(item) {
    if (!item || item.status !== 'error') return
    item.status = 'pending'
    item.error = ''
    item.retries = 0
    startUploadWorker()
  }

  function clearCompletedUploads() {
    uploadQueue.value = uploadQueue.value.filter(item => ['pending', 'uploading', 'retrying'].includes(item.status))
  }

  async function handleFileUpload(event, targetFolder = '') {
    const entries = extractSelectedFiles(event?.target?.files)
    if (event?.target) event.target.value = ''
    await enqueueUploads(entries, targetFolder)
  }

  function handleExternalDragEnter(event, targetFolder = '') {
    if (!isExternalFileDrag(event)) return
    containUploadDragEvent(event)
    uploadDragDepth.value += 1
    uploadDragActive.value = true
    uploadDragTarget.value = targetFolder || getDefaultTargetPath()
  }

  function handleExternalDragOver(event, targetFolder = '') {
    if (!isExternalFileDrag(event)) return
    containUploadDragEvent(event)
    event.dataTransfer.dropEffect = canUploadNow.value ? 'copy' : 'none'
    uploadDragActive.value = true
    uploadDragTarget.value = targetFolder || getDefaultTargetPath()
  }

  function handleExternalDragLeave(event) {
    if (isExternalFileDrag(event)) containUploadDragEvent(event)
    uploadDragDepth.value = Math.max(0, uploadDragDepth.value - 1)
    if (uploadDragDepth.value === 0) {
      uploadDragActive.value = false
      uploadDragTarget.value = ''
    }
  }

  async function handleExternalDrop(event, targetFolder = '') {
    if (!isExternalFileDrag(event) || isUploadDropHandled(event)) return
    markUploadDropHandled(event)
    uploadDragDepth.value = 0
    uploadDragActive.value = false
    uploadDragTarget.value = ''
    if (!canUploadNow.value) return
    const entries = await extractDroppedFiles(event?.dataTransfer)
    await enqueueUploads(entries, targetFolder || getDefaultTargetPath())
  }

  function handleWindowDragOver(event) {
    if (!isExternalFileDrag(event)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = canUploadNow.value ? 'copy' : 'none'
  }

  async function handleWindowDrop(event) {
    if (!isExternalFileDrag(event)) return
    if (event?.defaultPrevented || isUploadDropHandled(event)) return
    event.preventDefault?.()
    if (!canUploadNow.value) return
    await handleExternalDrop(event, getDefaultTargetPath())
  }

  function handleModalDragEnter(event) {
    if (!isExternalFileDrag(event)) return
    containUploadDragEvent(event)
    uploadModalDragActive.value = true
  }

  function handleModalDragOver(event) {
    if (!isExternalFileDrag(event)) return
    containUploadDragEvent(event)
    event.dataTransfer.dropEffect = canUploadNow.value ? 'copy' : 'none'
    uploadModalDragActive.value = true
  }

  function handleModalDragLeave(event) {
    if (isExternalFileDrag(event)) containUploadDragEvent(event)
    uploadModalDragActive.value = false
  }

  async function handleModalDrop(event) {
    if (!isExternalFileDrag(event) || isUploadDropHandled(event)) return
    markUploadDropHandled(event)
    uploadModalDragActive.value = false
    if (!canUploadNow.value) return
    const entries = await extractDroppedFiles(event?.dataTransfer)
    await enqueueUploads(entries, getDefaultTargetPath())
  }

  return {
    showUploadModal,
    uploadQueue,
    uploadDragActive,
    uploadDropLabel,
    uploadModalDragActive,
    uploadHasActive,
    uploadHasRemovable,
    uploadSummary,
    uploaderName,
    uploaderNameError,
    uploadError,
    setUploaderName,
    canUploadNow,
    openUploadModal,
    closeUploadModal,
    handleExternalDragEnter,
    handleExternalDragOver,
    handleExternalDragLeave,
    handleExternalDrop,
    handleWindowDragOver,
    handleWindowDrop,
    handleModalDragEnter,
    handleModalDragOver,
    handleModalDragLeave,
    handleModalDrop,
    handleFileUpload,
    retryUpload,
    cancelUpload,
    cancelAllUploads,
    clearCompletedUploads,
  }
}
