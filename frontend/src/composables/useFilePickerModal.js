import { ref, reactive, computed, watch } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'
import { normalizeMediaEntity } from '../lib/mediaEntity'
import { notify } from '../utils/toasts'

const TRACKER_IMPORT_MEDIA_EXTS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'heic', 'heif',
  'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'mxf', 'r3d', 'braw', 'prores',
])

const PROJECT_PICKER_MODES = new Set(['shot-import', 'shot', 'bulk-version-update', 'comment-reference'])

export function useFilePickerModal({
  canAddShots,
  canAddVersions,
  currentUser,
  currentProject,
  currentTracker,
  trackerShotsForDisplay,
  projectPath,
  getLatestShotFilePath,
  formatTimecode,
  refreshCurrentTrackerPreserveState,
  openTracker,
  refreshProjectContents,
  onThumbnailSourcePicked,
  onDeliveryLogoSourcePicked,
  onPageResourcePicked,
}) {
  const showFilePicker = ref(false)
  const pickerPath = ref('')
  const pickerFiles = ref([])
  const pickerShot = ref(null)
  const pickerMode = ref('shot')
  const pickerSource = ref('nas')
  const pickerSelectedItems = ref([])
  const mediaQuickInfo = reactive({})
  const versionPickerFileSearch = ref('')
  const versionPickerTargetShotId = ref('')
  const versionPickerSelectedCandidatePath = ref('')
  const versionPickerNotes = ref('')
  const versionPickerVisibleCount = ref(36)
  const versionPickerApplyBusy = ref(false)
  const shotImportApplyBusy = ref(false)
  const projectLinkApplyBusy = ref(false)
  const commentReferenceLimit = ref(3)
  let commentReferenceApplyHandler = null
  let commentUploadHandler = null
  const versionPickerCurrentInfo = ref(null)
  let versionPickerCurrentInfoToken = 0

  const currentTrackerRef = () => (
    currentTracker.value?.id || currentTracker.value?.slug || currentTracker.value?.name || ''
  )

  const isVersionPickerMode = computed(() => ['shot', 'bulk-version-update'].includes(pickerMode.value))
  const showTrackerImportModeToggle = computed(() => (
    !!currentTracker.value && ['shot-import', 'bulk-version-update'].includes(pickerMode.value)
  ))
  const trackerImportMode = computed(() => (
    pickerMode.value === 'bulk-version-update' ? 'bulk-version-update' : 'shot-import'
  ))
  const trackerImportModeTabs = computed(() => ([
    { value: 'shot-import', label: 'Add Shots', disabled: !canAddShots.value },
    { value: 'bulk-version-update', label: 'Bulk Update', disabled: !canAddVersions.value || !versionPickerShots.value.length },
  ]))
  const canUseProjectPicker = computed(() => (
    !!currentProject.value?.id &&
    PROJECT_PICKER_MODES.has(pickerMode.value)
  ))
  const isArtistUser = computed(() => currentUser?.value?.role === 'artist')
  const canUseNasPicker = computed(() => !isArtistUser.value)
  const effectivePickerSource = computed(() => {
    if (pickerMode.value === 'comment-reference') return 'project'
    if (!canUseProjectPicker.value) return 'nas'
    if (!canUseNasPicker.value) return 'project'
    return pickerSource.value
  })
  const pickerSourceTabs = computed(() => {
    if (!canUseProjectPicker.value) return []
    if (pickerMode.value === 'comment-reference') return [{ value: 'project', label: 'Project Files' }]
    const tabs = [{ value: 'project', label: 'Project Files' }]
    if (canUseNasPicker.value) tabs.push({ value: 'nas', label: 'NAS' })
    return tabs
  })

  const filePickerTitle = computed(() => {
    if (showTrackerImportModeToggle.value || pickerMode.value === 'bulk-version-update' || pickerMode.value === 'shot-import') return 'Import'
    if (pickerMode.value === 'delivery-logo-source') return 'Choose Delivery Logo'
    if (pickerMode.value === 'thumbnail-source') return 'Choose from NAS'
    if (pickerMode.value === 'page-resource') return 'Add Resource from NAS'
    if (pickerMode.value === 'project-link') return 'Link from NAS'
    if (pickerMode.value === 'comment-reference') return 'Add attachment'
    return 'Add Version'
  })

  const versionPickerShots = computed(() => {
    const allShots = trackerShotsForDisplay.value || []
    if (!allShots.length) return []
    if (pickerMode.value === 'shot') return pickerShot.value ? [pickerShot.value] : []
    return allShots
  })

  const selectedVersionPickerShot = computed(() => {
    const shotRef = versionPickerTargetShotId.value
    if (!shotRef) return null
    return (currentTracker.value?.shots || []).find(shot => getShotPickerRef(shot) === shotRef || shot.shot_id === shotRef) || null
  })

  const selectedVersionPickerCurrentMedia = computed(() => {
    const shot = selectedVersionPickerShot.value
    if (!shot) return null
    const versions = shot.versions || []
    const latest = versions[versions.length - 1]
    if (latest) return normalizeMediaEntity(latest)
    const path = getLatestShotFilePath(shot)
    return path ? normalizeMediaEntity({ path, file_path: path }) : null
  })

  const selectedVersionPickerCurrentPath = computed(() => selectedVersionPickerCurrentMedia.value?.path || '')
  function isTrackerImportMediaItem(item) {
    if (!item) return false
    if (item.type === 'image' || item.type === 'video') return true
    const ext = String(item.extension || item.name || '').split('.').pop()?.toLowerCase?.() || ''
    return TRACKER_IMPORT_MEDIA_EXTS.has(ext)
  }

  const versionPickerBrowserItems = computed(() => {
    const query = versionPickerFileSearch.value.trim().toLowerCase()
    const filteredItems = pickerFiles.value.filter(item => {
      if (item.type !== 'folder' && !isTrackerImportMediaItem(item)) return false
      if (!query) return true
      return String(item.name || '').toLowerCase().includes(query)
    })
    const folders = filteredItems.filter(item => item.type === 'folder')
    const files = filteredItems.filter(item => item.type !== 'folder')
    return [...folders, ...files.slice(0, versionPickerVisibleCount.value)]
  })

  const versionPickerCandidates = computed(() => {
    const query = versionPickerFileSearch.value.trim().toLowerCase()
    return pickerFiles.value.filter(item => {
      if (item.type === 'folder') return false
      if (!isTrackerImportMediaItem(item)) return false
      if (!query) return true
      return String(item.name || '').toLowerCase().includes(query)
    })
  })

  const visibleVersionPickerCandidates = computed(() => versionPickerCandidates.value.slice(0, versionPickerVisibleCount.value))
  const canLoadMoreVersionPickerCandidates = computed(() => versionPickerCandidates.value.length > visibleVersionPickerCandidates.value.length)
  const remainingVersionPickerCandidateCount = computed(() => Math.max(0, versionPickerCandidates.value.length - visibleVersionPickerCandidates.value.length))

  const selectedVersionPickerCandidate = computed(() => {
    const targetPath = versionPickerSelectedCandidatePath.value
    if (!targetPath) return null
    return pickerFiles.value.find(item => item.path === targetPath) || null
  })

  const canApplyVersionPickerSelection = computed(() => (
    !!selectedVersionPickerShot.value && !!selectedVersionPickerCandidate.value && !versionPickerApplyBusy.value
  ))
  const selectedShotImportItems = computed(() => pickerSelectedItems.value.filter(item => isTrackerImportMediaItem(item)))
  const selectedShotImportCount = computed(() => selectedShotImportItems.value.length)
  const canApplyShotImportSelection = computed(() => (
    pickerMode.value === 'shot-import' &&
    !!currentProject.value &&
    !!currentTracker.value &&
    selectedShotImportCount.value > 0 &&
    !shotImportApplyBusy.value
  ))
  const shotImportApplyLabel = computed(() => {
    const count = selectedShotImportCount.value
    if (shotImportApplyBusy.value) return 'Importing...'
    if (count === 1) return 'Import 1 file'
    return `Import ${count} files`
  })
  const selectedProjectLinkCount = computed(() => pickerSelectedItems.value.length)
  const canApplyProjectLinkSelection = computed(() => (
    ['project-link', 'comment-reference'].includes(pickerMode.value) &&
    selectedProjectLinkCount.value > 0 &&
    !projectLinkApplyBusy.value
  ))
  const projectLinkApplyLabel = computed(() => {
    const count = selectedProjectLinkCount.value
    if (projectLinkApplyBusy.value) return 'Linking...'
    if (pickerMode.value === 'comment-reference') return count === 1 ? 'Attach 1 item' : `Attach ${count} items`
    if (count === 1) return 'Link 1 file'
    return `Link ${count} files`
  })

  const versionPickerFooterText = computed(() => {
    const shot = selectedVersionPickerShot.value
    const candidate = selectedVersionPickerCandidate.value
    if (!shot) return 'Choose a shot.'
    if (!candidate) return `Choose an existing file for ${shot.shot_id}.`
    const nextVersion = (shot.versions?.length || 0) + 1
    return `Ready to add V${nextVersion} to ${shot.shot_id} · ${candidate.name}`
  })

  function mergeCanonicalMediaInfo(baseMediaInput, extraInfo = null) {
    const canonicalMedia = normalizeMediaEntity(baseMediaInput)
    if (!canonicalMedia && !extraInfo) return null
    return normalizeMediaEntity({
      ...(extraInfo || {}),
      ...(canonicalMedia || {}),
      path: canonicalMedia?.path || extraInfo?.path || '',
      file_path: canonicalMedia?.file_path || extraInfo?.file_path || canonicalMedia?.path || extraInfo?.path || '',
    })
  }

  function closeFilePicker() {
    showFilePicker.value = false
  }

  function setVersionPickerFileSearch(value) {
    versionPickerFileSearch.value = value
  }

  function setVersionPickerNotes(value) {
    versionPickerNotes.value = value
  }

  function loadMoreVersionPickerCandidates() {
    versionPickerVisibleCount.value += 36
  }

  function getQuickMediaInfo(path) {
    return path ? mediaQuickInfo[path] || null : null
  }

  function getMediaDurationLabel(mediaInput, info = null) {
    const media = typeof mediaInput === 'string' ? { path: mediaInput } : normalizeMediaEntity(mediaInput)
    const source = info || getQuickMediaInfo(media?.path)
    if (!source) return ''
    if (source.duration_formatted) return source.duration_formatted
    if (Number.isFinite(source.duration) && source.duration > 0) return formatTimecode(source.duration)
    return ''
  }

  function getShotVersionCount(shot) {
    return shot?.versions?.length || 0
  }

  function getPickerItemMedia(item) {
    if (!item?.path) return null
    const pickerSourceForItem = item._pickerSource || effectivePickerSource.value
    const path = pickerSourceForItem === 'project' && item.is_linked && item.source_path ? item.source_path : item.path
    return normalizeMediaEntity({
      ...(getQuickMediaInfo(path) || getQuickMediaInfo(item.path) || {}),
      ...item,
      path,
      file_path: path,
      name: item.name,
      _pickerSource: pickerSourceForItem,
      _projectFile: pickerSourceForItem === 'project' && !item.is_linked,
      storage_scope: pickerSourceForItem === 'project' && !item.is_linked ? 'project' : item.storage_scope,
    })
  }

  function setVersionPickerTarget(shot) {
    versionPickerTargetShotId.value = getShotPickerRef(shot)
  }

  function getShotPickerRef(shot) {
    return shot?.id || shot?.shot_id || ''
  }

  function resetVersionPickerState() {
    versionPickerFileSearch.value = ''
    versionPickerTargetShotId.value = ''
    versionPickerSelectedCandidatePath.value = ''
    versionPickerNotes.value = ''
    versionPickerVisibleCount.value = 36
    versionPickerApplyBusy.value = false
    versionPickerCurrentInfo.value = null
  }

  function resetPickerSource() {
    pickerSource.value = canUseProjectPicker.value ? 'project' : 'nas'
  }

  async function setPickerSource(source) {
    const nextSource = source === 'project' || !canUseNasPicker.value
      ? (canUseProjectPicker.value ? 'project' : 'nas')
      : 'nas'
    if (pickerSource.value === nextSource && pickerPath.value === '') return
    pickerSource.value = nextSource
    pickerPath.value = ''
    pickerSelectedItems.value = []
    versionPickerSelectedCandidatePath.value = ''
    await loadPickerFiles('')
  }

  function normalizePickerItems(items = []) {
    if (effectivePickerSource.value !== 'project') return items || []
    return (items || [])
      .filter(item => ['folder', 'file', 'tracker', 'page'].includes(item?.type))
      .map(item => {
        if (item.type === 'folder') return { ...item, _pickerSource: 'project' }
        if (item.type === 'tracker') return { ...item, _pickerSource: 'project' }
        if (item.type === 'page') return { ...item, _pickerSource: 'project' }
        return {
          ...item,
          type: item.is_video ? 'video' : item.is_image ? 'image' : 'file',
          project_item_type: 'file',
          _pickerSource: 'project',
          _projectFile: !item.is_linked,
        }
      })
  }

  function getTrackerImportFilePath(item) {
    if (!item) return ''
    if (item._pickerSource === 'project' && item.is_linked && item.source_path) return item.source_path
    return item.path || ''
  }

  function shouldUseProjectScopedPickerMediaInfo() {
    return !!currentProject.value?.id && currentProject.value?.source === 'horizons_db'
  }

  async function fetchBatchMediaInfo(paths) {
    const uniquePaths = [...new Set((paths || []).filter(Boolean))].filter(path => {
      const cached = mediaQuickInfo[path]
      return !cached || (!cached._loading && !cached._loaded)
    })
    if (!uniquePaths.length) return

    uniquePaths.forEach(path => {
      mediaQuickInfo[path] = { ...(mediaQuickInfo[path] || {}), path, _loading: true, _loaded: false }
    })

    try {
      let data
      if (shouldUseProjectScopedPickerMediaInfo()) {
        const response = await api.post(`/api/horizons/projects/${currentProject.value.id}/media-info/batch`, { paths: uniquePaths })
        data = response.data
      } else {
        const response = await api.post('/api/media-info/batch', {
          paths: uniquePaths,
          project_id: currentProject.value?.id || null,
        })
        data = response.data
      }

      for (const item of data.items || []) {
        mediaQuickInfo[item.path] = { ...(mediaQuickInfo[item.path] || {}), ...item, _loading: false, _loaded: true }
      }
    } catch (error) {
      console.warn('Failed to load batch media info')
      uniquePaths.forEach(path => {
        mediaQuickInfo[path] = { ...(mediaQuickInfo[path] || {}), path, _loading: false, _loaded: false }
      })
    }
  }

  async function fetchDetailedMediaInfo(mediaInput) {
    const media = normalizeMediaEntity(mediaInput)
    const path = media?.path || ''
    if (!path) return null
    const quick = getQuickMediaInfo(path)

    if (shouldUseProjectScopedPickerMediaInfo()) {
      const { data } = await api.post(`/api/horizons/projects/${currentProject.value.id}/media-info/batch`, { paths: [path] })
      return { ...(quick || {}), ...(data.items?.[0] || {}) }
    }

    if (currentProject.value?.id) {
      const { data } = await api.get(`/api/projects/${currentProject.value.id}/file-info`, { params: { path } })
      return { ...(quick || {}), ...(data || {}) }
    }

    const { data } = await api.get('/api/video-info', { params: { path } })
    return { ...(quick || {}), ...(data || {}) }
  }

  async function loadVersionPickerCurrentInfo(mediaInput) {
    const token = ++versionPickerCurrentInfoToken
    const media = normalizeMediaEntity(mediaInput)
    if (!media?.path) {
      versionPickerCurrentInfo.value = null
      return
    }
    try {
      const info = await fetchDetailedMediaInfo(media)
      if (token !== versionPickerCurrentInfoToken) return
      versionPickerCurrentInfo.value = mergeCanonicalMediaInfo(media, info)
    } catch (error) {
      console.warn('Failed to load current shot media info')
      if (token !== versionPickerCurrentInfoToken) return
      versionPickerCurrentInfo.value = mergeCanonicalMediaInfo(media, getQuickMediaInfo(media.path) || null)
    }
  }

  async function prepareVersionPicker(mode, shot = null) {
    pickerMode.value = mode
    pickerShot.value = shot
    pickerPath.value = ''
    resetPickerSource()
    resetVersionPickerState()
    if (shot) setVersionPickerTarget(shot)
    await loadPickerFiles('')
    if (!shot && mode === 'bulk-version-update' && versionPickerShots.value.length) {
      setVersionPickerTarget(versionPickerShots.value[0])
    }
    showFilePicker.value = true
  }

  async function openTrackerImportPicker(mode = 'shot-import') {
    const requestedMode = mode === 'bulk-version-update' ? 'bulk-version-update' : 'shot-import'
    const allowedMode = requestedMode === 'bulk-version-update' && canAddVersions.value ? 'bulk-version-update' : 'shot-import'
    const nextPath = pickerPath.value || ''

    pickerMode.value = allowedMode
    pickerShot.value = null
    pickerSelectedItems.value = []
    resetPickerSource()
    resetVersionPickerState()

    await loadPickerFiles(pickerSource.value === 'project' ? '' : nextPath)

    if (allowedMode === 'bulk-version-update' && versionPickerShots.value.length) {
      setVersionPickerTarget(versionPickerShots.value[0])
    }

    showFilePicker.value = true
  }

  async function setTrackerImportMode(mode) {
    if (!['shot-import', 'bulk-version-update'].includes(mode)) return
    if (mode === 'shot-import' && !canAddShots.value) return
    if (mode === 'bulk-version-update' && (!canAddVersions.value || !versionPickerShots.value.length)) return
    await openTrackerImportPicker(mode)
  }

  async function openShotImportPicker() {
    await openTrackerImportPicker('shot-import')
  }

  async function openProjectLinkPicker() {
    pickerMode.value = 'project-link'
    pickerSource.value = 'nas'
    pickerPath.value = ''
    pickerSelectedItems.value = []
    await loadPickerFiles('')
    showFilePicker.value = true
  }

  async function openCommentReferencePicker({ limit = 3, onApply, onUpload } = {}) {
    if (!currentProject.value?.id || typeof onApply !== 'function') return
    pickerMode.value = 'comment-reference'
    pickerSource.value = 'project'
    pickerPath.value = ''
    pickerSelectedItems.value = []
    commentReferenceLimit.value = Math.max(1, Number(limit) || 3)
    commentReferenceApplyHandler = onApply
    commentUploadHandler = typeof onUpload === 'function' ? onUpload : null
    await loadPickerFiles('')
    showFilePicker.value = true
  }

  function uploadCommentFiles() {
    if (pickerMode.value !== 'comment-reference') return
    const handler = commentUploadHandler
    showFilePicker.value = false
    handler?.()
  }

  async function openPageResourcePicker() {
    pickerMode.value = 'page-resource'
    pickerSource.value = 'nas'
    pickerPath.value = ''
    await loadPickerFiles('')
    showFilePicker.value = true
  }

  async function openThumbnailPicker() {
    pickerMode.value = 'thumbnail-source'
    pickerSource.value = 'nas'
    pickerPath.value = ''
    await loadPickerFiles('')
    showFilePicker.value = true
  }

  async function openDeliveryLogoPicker() {
    pickerMode.value = 'delivery-logo-source'
    pickerSource.value = 'nas'
    pickerPath.value = ''
    await loadPickerFiles('')
    showFilePicker.value = true
  }

  async function openFolderThumbPickerFromNas() {
    await openThumbnailPicker()
  }

  function getPickerSelectionKey(item) {
    if (pickerMode.value === 'comment-reference') {
      if (item?.type === 'tracker' || item?.type === 'page') {
        return item.id ? `${item.type}:${item.id}` : ''
      }
      const mediaId = item?.media_asset_id || item?.path
      return mediaId ? `media_asset:${mediaId}` : ''
    }
    return item?.path || ''
  }

  function isPickerSelected(item) {
    const key = getPickerSelectionKey(item)
    if (!key) return false
    if (isVersionPickerMode.value) return versionPickerSelectedCandidatePath.value === item.path
    return pickerSelectedItems.value.some(selected => getPickerSelectionKey(selected) === key)
  }

  function togglePickerSelectedItem(item) {
    const key = getPickerSelectionKey(item)
    if (!key || item.type === 'folder') return
    const existingIndex = pickerSelectedItems.value.findIndex(selected => getPickerSelectionKey(selected) === key)
    if (existingIndex >= 0) {
      pickerSelectedItems.value = pickerSelectedItems.value.filter((_, index) => index !== existingIndex)
      return
    }
    if (pickerMode.value === 'comment-reference' && pickerSelectedItems.value.length >= commentReferenceLimit.value) {
      notify(`You can attach up to ${commentReferenceLimit.value} items.`)
      return
    }
    pickerSelectedItems.value = [...pickerSelectedItems.value, item]
  }

  function selectVersionPickerShot(shot) {
    setVersionPickerTarget(shot)
  }

  function selectVersionPickerCandidate(item) {
    versionPickerSelectedCandidatePath.value = item?.path || ''
  }

  async function applyVersionPickerSelection() {
    if (!currentProject.value || !currentTracker.value) return

    const shot = selectedVersionPickerShot.value
    const candidate = selectedVersionPickerCandidate.value
    if (!shot || !candidate?.path) return

    const shotRef = getShotPickerRef(shot)
    const shotIndex = versionPickerShots.value.findIndex(item => getShotPickerRef(item) === shotRef || item.shot_id === shot.shot_id)
    const nextBulkShot = shotIndex >= 0 ? versionPickerShots.value[shotIndex + 1] : null
    const nextShotRef = pickerMode.value === 'bulk-version-update'
      ? getShotPickerRef(nextBulkShot) || shotRef
      : shotRef

    versionPickerApplyBusy.value = true

    try {
      if (!shotRef) throw new Error('Shot reference missing')
      await api.put(`/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}/shots/${encodeURIComponent(shotRef)}`, {
        file_path: getTrackerImportFilePath(candidate),
        version_notes: versionPickerNotes.value.trim() || null,
      })

      await refreshCurrentTrackerPreserveState()
      const refreshedShot = (currentTracker.value?.shots || []).find(item => getShotPickerRef(item) === nextShotRef || item.shot_id === nextShotRef)
      if (refreshedShot) setVersionPickerTarget(refreshedShot)
      versionPickerSelectedCandidatePath.value = ''
      versionPickerNotes.value = ''
    } catch (error) {
      notify('Failed to add version: ' + (getApiErrorMessage(error, 'Unknown error')))
    } finally {
      versionPickerApplyBusy.value = false
    }
  }

  async function importFolder(folder) {
    if (!currentProject.value || !currentTracker.value) return

    try {
      const items = await fetchPickerItems(folder.path)
      const mediaFiles = items
        .filter(item => isTrackerImportMediaItem(item))
        .map(getTrackerImportFilePath)
        .filter(Boolean)

      if (mediaFiles.length === 0) {
        notify('No image or video files found in this folder')
        return
      }

      await api.post(`/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}/shots/bulk`, {
        files: mediaFiles,
      })

      showFilePicker.value = false
      openTracker(currentTrackerRef())
    } catch (error) {
      notify('Failed to import shots: ' + (getApiErrorMessage(error)))
    }
  }

  async function applyShotImportSelection() {
    if (!canApplyShotImportSelection.value) return
    const mediaFiles = selectedShotImportItems.value
      .map(getTrackerImportFilePath)
      .filter(Boolean)

    if (!mediaFiles.length || !currentProject.value || !currentTracker.value) return

    shotImportApplyBusy.value = true
    try {
      await api.post(`/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}/shots/bulk`, {
        files: mediaFiles,
      })

      pickerSelectedItems.value = []
      showFilePicker.value = false
      openTracker(currentTrackerRef())
    } catch (error) {
      notify('Failed to import shots: ' + (getApiErrorMessage(error)))
    } finally {
      shotImportApplyBusy.value = false
    }
  }

  async function linkFolderToProject(folderPath) {
    if (!currentProject.value) return
    try {
      await api.post(`/api/projects/${currentProject.value.id}/link`, {
        source_path: folderPath,
        target_folder: projectPath.value,
      })
      showFilePicker.value = false
      await refreshProjectContents()
    } catch (error) {
      notify('Failed to link folder: ' + (getApiErrorMessage(error)))
    }
  }

  async function applyProjectLinkSelection() {
    if (!currentProject.value || !canApplyProjectLinkSelection.value) return
    if (pickerMode.value === 'comment-reference') {
      const selected = pickerSelectedItems.value.slice(0, commentReferenceLimit.value)
      commentReferenceApplyHandler?.(selected)
      pickerSelectedItems.value = []
      showFilePicker.value = false
      return
    }
    const sourcePaths = pickerSelectedItems.value
      .filter(item => item?.type !== 'folder')
      .map(item => item.path)
      .filter(Boolean)
    if (!sourcePaths.length) return

    projectLinkApplyBusy.value = true
    try {
      await api.post(`/api/projects/${currentProject.value.id}/links`, {
        source_paths: sourcePaths,
        target_folder: projectPath.value,
      })
      pickerSelectedItems.value = []
      showFilePicker.value = false
      await refreshProjectContents()
    } catch (error) {
      notify('Failed to link files: ' + (getApiErrorMessage(error)))
    } finally {
      projectLinkApplyBusy.value = false
    }
  }

  async function loadPickerFiles(path) {
    try {
      const items = await fetchPickerItems(path)
      const isTrackerMediaMode = ['shot-import', 'shot', 'bulk-version-update'].includes(pickerMode.value)
      pickerFiles.value = isTrackerMediaMode
        ? items.filter(item => item.type === 'folder' || isTrackerImportMediaItem(item))
        : items
      pickerPath.value = path
      versionPickerVisibleCount.value = 36
      if (versionPickerSelectedCandidatePath.value && !items.some(item => item.path === versionPickerSelectedCandidatePath.value)) {
        versionPickerSelectedCandidatePath.value = ''
      }
    } catch (error) {
      console.warn('Failed to load picker files')
    }
  }

  async function fetchPickerItems(path) {
    if (effectivePickerSource.value === 'project' && currentProject.value?.id) {
      const { data } = await api.get(`/api/projects/${currentProject.value.id}/contents`, {
        params: { path, include_counts: true },
      })
      return normalizePickerItems(data.items || [])
    }

    const { data } = await api.get('/api/files', { params: { path } })
    return normalizePickerItems(data.items || [])
  }

  function pickerGoUp() {
    const parts = pickerPath.value.split('/')
    parts.pop()
    loadPickerFiles(parts.join('/'))
  }

  async function pickerSelect(item) {
    if (pickerMode.value === 'page-resource' && item?._selectFolder) {
      await onPageResourcePicked?.(item)
      showFilePicker.value = false
      return
    }

    if (item.type === 'folder') {
      loadPickerFiles(item.path)
      return
    }

    if (isVersionPickerMode.value) {
      selectVersionPickerCandidate(item)
      return
    }

    if (pickerMode.value === 'shot-import') {
      if (!isTrackerImportMediaItem(item)) {
        notify('Choose an image or video file')
        return
      }
      togglePickerSelectedItem(item)
      return
    }

    if (pickerMode.value === 'thumbnail-source') {
      if (item.type !== 'image' && item.type !== 'video') {
        notify('Choose an image or video file')
        return
      }
      await onThumbnailSourcePicked?.({ ...item, ...(getQuickMediaInfo(item.path) || {}) })
      showFilePicker.value = false
      return
    }

    if (pickerMode.value === 'delivery-logo-source') {
      if (item.type !== 'image') {
        notify('Choose an image file')
        return
      }
      await onDeliveryLogoSourcePicked?.({ ...item, ...(getQuickMediaInfo(item.path) || {}) })
      showFilePicker.value = false
      return
    }

    if (pickerMode.value === 'page-resource') {
      await onPageResourcePicked?.({ ...item, ...(getQuickMediaInfo(item.path) || {}) })
      showFilePicker.value = false
      return
    }

    if (pickerMode.value === 'comment-reference' && item.type !== 'tracker' && item.type !== 'page' && !item.media_asset_id) {
      notify('This file is not available as a project attachment yet.')
      return
    }

    if (['project-link', 'comment-reference'].includes(pickerMode.value)) {
      togglePickerSelectedItem(item)
    }
  }

  watch(showFilePicker, (value) => {
    if (!value) {
      pickerSelectedItems.value = []
      pickerShot.value = null
      shotImportApplyBusy.value = false
      projectLinkApplyBusy.value = false
      commentReferenceApplyHandler = null
      commentUploadHandler = null
      resetVersionPickerState()
    }
  })

  watch(versionPickerShots, (shots) => {
    if (!isVersionPickerMode.value) return
    if (!shots.length) {
      setVersionPickerTarget(null)
      return
    }
    if (!shots.some(shot => getShotPickerRef(shot) === versionPickerTargetShotId.value || shot.shot_id === versionPickerTargetShotId.value)) {
      setVersionPickerTarget(shots[0])
    }
  })

  watch(isVersionPickerMode, (enabled) => {
    if (!enabled || !showFilePicker.value) return
    const shots = versionPickerShots.value
    if (!shots.length) return
    if (!shots.some(shot => getShotPickerRef(shot) === versionPickerTargetShotId.value || shot.shot_id === versionPickerTargetShotId.value)) {
      setVersionPickerTarget(shots[0])
    }
  })

  watch(versionPickerFileSearch, () => {
    versionPickerVisibleCount.value = 36
  })

  watch(
    () => {
      if (!showFilePicker.value) return []
      const items = isVersionPickerMode.value ? versionPickerBrowserItems.value : pickerFiles.value
      return items
        .filter(item => !['folder', 'tracker', 'page'].includes(item?.type))
        .map(item => getPickerItemMedia(item)?.path || item.path)
        .filter(Boolean)
    },
    (paths) => {
      if (!paths.length) return
      fetchBatchMediaInfo(paths)
    },
    { deep: true }
  )

  watch(
    () => trackerShotsForDisplay.value.map(shot => getLatestShotFilePath(shot)).filter(Boolean),
    (paths) => {
      if (!currentProject.value?.id || !paths.length) return
      fetchBatchMediaInfo(paths)
    },
    { deep: true, immediate: true }
  )

  watch(
    () => selectedVersionPickerCurrentMedia.value?.media_entity_key || selectedVersionPickerCurrentPath.value,
    () => {
      if (!showFilePicker.value || !isVersionPickerMode.value) return
      loadVersionPickerCurrentInfo(selectedVersionPickerCurrentMedia.value)
    },
    { immediate: true }
  )

  return {
    showFilePicker,
    pickerPath,
    pickerFiles,
    pickerShot,
    pickerMode,
    pickerSource,
    canUseProjectPicker,
    pickerSourceTabs,
    isVersionPickerMode,
    showTrackerImportModeToggle,
    trackerImportMode,
    trackerImportModeTabs,
    filePickerTitle,
    selectedVersionPickerShot,
    selectedVersionPickerCurrentMedia,
    selectedVersionPickerCurrentPath,
    versionPickerCurrentInfo,
    versionPickerShots,
    versionPickerTargetShotId,
    versionPickerFileSearch,
    versionPickerNotes,
    versionPickerBrowserItems,
    versionPickerSelectedCandidatePath,
    canLoadMoreVersionPickerCandidates,
    remainingVersionPickerCandidateCount,
    versionPickerFooterText,
    canApplyVersionPickerSelection,
    versionPickerApplyBusy,
    selectedShotImportCount,
    canApplyShotImportSelection,
    shotImportApplyBusy,
    shotImportApplyLabel,
    selectedProjectLinkCount,
    canApplyProjectLinkSelection,
    projectLinkApplyBusy,
    projectLinkApplyLabel,
    closeFilePicker,
    setVersionPickerFileSearch,
    setVersionPickerNotes,
    setPickerSource,
    loadMoreVersionPickerCandidates,
    getMediaDurationLabel,
    fetchBatchMediaInfo,
    getShotVersionCount,
    getPickerItemMedia,
    selectVersionPickerShot,
    applyVersionPickerSelection,
    importFolder,
    applyShotImportSelection,
    linkFolderToProject,
    applyProjectLinkSelection,
    pickerGoUp,
    pickerSelect,
    isPickerSelected,
    prepareVersionPicker,
    setTrackerImportMode,
    openShotImportPicker,
    openProjectLinkPicker,
    openCommentReferencePicker,
    uploadCommentFiles,
    openPageResourcePicker,
    openThumbnailPicker,
    openDeliveryLogoPicker,
    openFolderThumbPickerFromNas,
  }
}
