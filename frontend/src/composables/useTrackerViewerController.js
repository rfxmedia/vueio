import { computed, nextTick, ref, watch } from 'vue'
import api, { getApiErrorDetail, getApiErrorMessage } from '../lib/api'
import { getMediaKind, mediaEntitiesMatch } from '../lib/mediaEntity'
import { formatVersionDateLabel, formatVersionDateShortLabel } from '../utils/formatters'
import { formatVersionLabel } from '../utils/versionLabels'
import { notify } from '../utils/toasts'

const versionOrderCache = new WeakMap()

function sortShotVersions(shot) {
  const source = shot?.versions || []
  const cached = shot && versionOrderCache.get(shot)
  if (cached?.source === source && cached.sourceLength === source.length && cached.sorted) {
    return cached.sorted
  }

  const sorted = [...source].sort((a, b) => {
    const labelA = parseVersionOrder(a?.label ?? a?.version)
    const labelB = parseVersionOrder(b?.label ?? b?.version)
    if (labelA !== null && labelB !== null && labelA !== labelB) return labelA - labelB
    const createdA = Number(a?.created_at || 0)
    const createdB = Number(b?.created_at || 0)
    if (createdA !== createdB) return createdA - createdB
    return String(a?.label ?? a?.version ?? '').localeCompare(String(b?.label ?? b?.version ?? ''))
  })

  if (shot) {
    versionOrderCache.set(shot, {
      source,
      sourceLength: source.length,
      sorted,
    })
  }
  return sorted
}

export function orderTrackerViewerVersions(shot, { preserveServerOrder = false } = {}) {
  return preserveServerOrder ? [...(shot?.versions || [])] : sortShotVersions(shot)
}

function parseVersionOrder(value) {
  if (value === null || value === undefined) return null
  const normalized = String(value).trim()
  if (!normalized) return null
  const direct = Number(normalized)
  if (Number.isFinite(direct)) return direct
  const trailingDigits = normalized.match(/(\d+)(?!.*\d)/)
  return trailingDigits ? Number(trailingDigits[1]) : null
}

export function useTrackerViewerController({
  getCurrentProject,
  getCurrentTracker,
  getCurrentMedia,
  isShareMode,
  canAddVersions,
  canManageVersionPublication,
  buildDownloadUrl,
  dismissCurrentMedia,
  openVideo,
  openImage,
  openPdf,
  openTracker,
  recordTrackerMediaView = () => {},
  invalidateTrackerPayloads = () => {},
  prepareVersionPicker,
  currentProjectRef,
  currentTrackerRef,
  currentMediaRef,
  shareModeRef,
  isAdmin,
  isMobile,
  isViewingVideo,
  trackerShotsForDisplay,
  trackerStatusOptions,
  trackerToolEnabledForContext,
  getBriefMediaFile,
  sidebarTab,
  showStatusPicker,
  videoEl,
  isDrawingMode,
}) {
  const currentProject = () => getCurrentProject?.() || null
  const currentTracker = () => getCurrentTracker?.() || null
  const currentMedia = () => getCurrentMedia?.() || null
  const shareMode = () => Boolean(isShareMode?.())
  const canAddShotVersions = () => Boolean(canAddVersions?.())
  const canManagePublication = () => Boolean(canManageVersionPublication?.value)
  const trackerRef = tracker => tracker?.id || tracker?.slug || tracker?.name || ''

  function getShotVersions(shot) {
    // Shared payloads are already ordered by publication time. Preserve that
    // order so republishing an older label can intentionally make it current.
    return orderTrackerViewerVersions(shot, { preserveServerOrder: shareMode() })
  }

  function formatVersionDate(timestamp) {
    return formatVersionDateLabel(timestamp)
  }

  function formatVersionDateShort(timestamp) {
    return formatVersionDateShortLabel(timestamp)
  }

  function getShotLatestCreatedAt(shot) {
    const versions = getShotVersions(shot)
    const latest = versions[versions.length - 1]
    return latest?.created_at || null
  }

  function formatShotLatestAdded(shot) {
    const ts = getShotLatestCreatedAt(shot)
    return ts ? formatVersionDateShort(ts) : '-'
  }

  function openTrackerVersionMedia(version, name) {
    if (!(version?.path || version?.file_path)) return
    const payload = buildTrackerVersionPayload(version, name)
    const mediaKind = getMediaKind(payload)
    if (mediaKind === 'image') {
      openImage({
        ...payload,
        is_image: true,
      })
      return
    }
    if (mediaKind === 'pdf') {
      openPdf?.({
        ...payload,
        is_pdf: true,
      })
      return
    }
    if (mediaKind === 'video') {
      openVideo(payload)
    }
  }

  function versionMatchesMedia(version, media = currentMedia()) {
    return mediaEntitiesMatch(version, media)
  }

  function getVersionDisplayLabel(version, fallbackIndex = null) {
    return formatVersionLabel(version, fallbackIndex, {
      emptyLabel: 'this version',
      uppercaseVPrefix: true,
      fallbackIndexAsRaw: true,
    })
  }

  async function saveShotVersions(shot) {
    const project = currentProject()
    const tracker = currentTracker()
    if (!project || !tracker) return

    const shotRef = shot.id || shot._originalId || shot.shot_id
    if (!shotRef) return

    try {
      await api.put(`/api/projects/${project.id}/trackers/${encodeURIComponent(trackerRef(tracker))}/shots/${encodeURIComponent(shotRef)}`, {
        description: shot.description,
        status: shot.status,
        versions: getShotVersions(shot).map((version, index) => ({
          ...version,
          label: String(version.label || version.version || index + 1),
        })),
      })
      invalidateTrackerPayloads()
      shot._originalId = shot.shot_id
    } catch (error) {
      console.error('Failed to save shot')
      if (getApiErrorDetail(error)) notify(getApiErrorMessage(error))
    }
  }

  function openVersionUpload(shot) {
    if (shareMode()) {
      notify('Share link viewers cannot add versions.')
      return
    }

    if (!canAddShotVersions()) {
      return
    }

    linkFileToShot(shot)
  }

  async function deleteShotVersion(shot, version) {
    if (!shot || !version) return false

    const versions = getShotVersions(shot)
    const versionIndex = versions.findIndex(item => item?.id === version.id)
    const fallbackIndex = versionIndex >= 0 ? versionIndex + 1 : null
    const versionLabel = getVersionDisplayLabel(version, fallbackIndex)
    if (!confirm(`Remove ${versionLabel} from this shot's tracker history?\n\nThis only updates the tracker and does not delete the source media file.`)) {
      return false
    }

    const media = currentMedia()
    const deletingCurrentTrackerMedia = Boolean(media?._openedFromTracker && versionMatchesMedia(version, media))
    const nextVersionIndex = Math.max(0, Math.min(versionIndex, versions.length - 2))

    shot.versions = versions.filter(item => item.id !== version.id)
    shot.versions = shot.versions.map((item, index) => ({
      ...item,
      label: String(index + 1),
      version: index + 1,
    }))

    await saveShotVersions(shot)

    const tracker = currentTracker()
    if (tracker) {
      await openTracker(trackerRef(tracker))
    }

    if (deletingCurrentTrackerMedia) {
      const refreshedTracker = currentTracker()
      const refreshedShot = (refreshedTracker?.shots || []).find(item => item?.shot_id === shot.shot_id) || null
      const refreshedVersions = getShotVersions(refreshedShot || shot)
      const fallbackVersion = refreshedVersions[nextVersionIndex] || refreshedVersions[refreshedVersions.length - 1] || null

      if (fallbackVersion && typeof openTrackerViewerVersion === 'function') {
        openTrackerViewerVersion(refreshedShot || shot, fallbackVersion, {
          mode: media?._trackerViewerMode || 'latest',
          preserveSidebar: true,
        })
      } else if (typeof dismissCurrentMedia === 'function') {
        dismissCurrentMedia()
      }
    }

    return true
  }

  async function linkFileToShot(shot) {
    await prepareVersionPicker('shot', shot)
  }

  function openShotVideo(shot) {
    const versions = getShotVersions(shot)
    const latest = versions[versions.length - 1]
    if (!(latest?.path || latest?.file_path)) return

    if (typeof openTrackerViewerVersion === 'function') {
      openTrackerViewerVersion(shot, latest, { mode: 'latest' })
      return
    }

    openTrackerVersionMedia(latest, `${shot.shot_id} V${latest.label || versions.length}`)
  }

  function playShotVersion(shot, version, label) {
    if (!(version?.path || version?.file_path)) return

    if (typeof openTrackerViewerVersion === 'function' && shot) {
      openTrackerViewerVersion(shot, version, { mode: 'latest' })
      return
    }
    openTrackerVersionMedia(version, `V${label}`)
  }

  function downloadVersion(version) {
    const versionPath = version?.path || version?.file_path
    if (!versionPath || version?.exists === false) return
    const downloadTarget = buildTrackerVersionPayload(
      version,
      versionPath.split('/').pop() || `V${version.label || version.version || ''}`,
    )
    const url = buildDownloadUrl(downloadTarget)
    const link = document.createElement('a')
    link.href = url
    link.download = downloadTarget.name
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  function buildTrackerVersionPayload(version, name) {
    return {
      ...version,
      path: version.path || version.file_path,
      name,
      size_formatted: version.size_formatted || '',
      version_id: version.id || null,
      horizons_shot_version_id: version.id || null,
      media_asset_id: version.media_asset_id || null,
      horizons_media_asset_id: version.media_asset_id || null,
    }
  }

  const trackerViewerVersionSwitcherOpen = ref(false)
  const versionCompareActive = ref(false)
  const versionCompareMode = ref('side-by-side')
  const versionComparePrimaryVersion = ref(null)
  const versionCompareSecondaryVersion = ref(null)
  const compareImageExtensions = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'heic', 'heif', 'exr', 'dpx'])

  function getTrackerPlaybackVersion(shot, mode = 'latest') {
    if (!shot) return null
    if (mode === 'brief') return getBriefMediaFile(shot)
    const versions = getShotVersions(shot)
    return versions[versions.length - 1] || null
  }

  function formatTrackerVersionLabel(version, fallbackIndex = null) {
    return formatVersionLabel(version, fallbackIndex)
  }

  function versionMatchesCurrentMedia(version, media = currentMediaRef.value) {
    return versionMatchesMedia(version, media)
  }

  function findTrackerViewerVersionIndex(versions, media = currentMediaRef.value) {
    if (!versions?.length || !media) return -1
    return versions.findIndex(version => versionMatchesCurrentMedia(version, media))
  }

  function resolveTrackerViewerShot(media = currentMediaRef.value) {
    if (!currentTrackerRef.value || !media?._openedFromTracker) return null
    const shots = currentTrackerRef.value.shots || []
    if (media._trackerShotId) {
      const match = shots.find(shot => shot?.shot_id === media._trackerShotId)
      if (match) return match
    }
    return shots.find(shot => getShotVersions(shot).some(version => versionMatchesCurrentMedia(version, media))) || null
  }

  function buildTrackerViewerItem(shot, mode = 'latest', versionOverride = null) {
    const version = versionOverride || getTrackerPlaybackVersion(shot, mode)
    const path = version?.path || version?.file_path
    if (!path) return null
    const versions = getShotVersions(shot)
    const index = versions.findIndex(item => item?.id === version.id)
    const label = formatTrackerVersionLabel(version, index >= 0 ? index + 1 : versions.length || 1)
    return {
      ...version,
      path,
      name: `${shot.shot_id} ${label}`,
      size_formatted: version.size_formatted || '',
      version_id: version.id || null,
      horizons_shot_version_id: version.id || null,
      media_asset_id: version.media_asset_id || null,
      horizons_media_asset_id: version.media_asset_id || null,
      _projectId: currentProjectRef.value?.id || null,
      _projectFile: true,
      _openedFromTracker: true,
      _trackerShotId: shot.shot_id,
      _trackerViewerMode: mode,
    }
  }

  function dismissTrackerViewerVersionSwitcher() {
    trackerViewerVersionSwitcherOpen.value = false
  }

  function openTrackerViewerVersion(shot, version, { mode = 'latest', preserveSidebar = false } = {}) {
    const item = buildTrackerViewerItem(shot, mode, version)
    if (!item) return
    dismissTrackerViewerVersionSwitcher()
    showStatusPicker.value = null
    if (!preserveSidebar) sidebarTab.value = 'comments'
    if (item.is_image === true) openImage(item)
    else if (item.is_pdf === true) openPdf(item)
    else openVideo(item)
    void recordTrackerMediaView(shot, version, mode)
  }

  function openTrackerViewerShot(shot, mode = 'latest', options = {}) {
    const version = getTrackerPlaybackVersion(shot, mode)
    if (version?.path || version?.file_path) openTrackerViewerVersion(shot, version, { mode, ...options })
  }

  function openTrackerShotVideo(shot) {
    openTrackerViewerShot(shot, 'latest')
  }

  const trackerViewerMode = computed(() => (
    currentMediaRef.value?._openedFromTracker ? currentMediaRef.value._trackerViewerMode || 'latest' : null
  ))
  const currentTrackerViewerShot = computed(() => resolveTrackerViewerShot())
  const currentTrackerViewerVersions = computed(() => (
    currentTrackerViewerShot.value ? getShotVersions(currentTrackerViewerShot.value) : []
  ))
  const currentTrackerViewerVersionsDescending = computed(() => [...currentTrackerViewerVersions.value].reverse())
  const currentTrackerViewerCurrentVersionIndex = computed(() => (
    findTrackerViewerVersionIndex(currentTrackerViewerVersions.value, currentMediaRef.value)
  ))
  const currentTrackerViewerCurrentVersion = computed(() => {
    if (!currentTrackerViewerShot.value) return null
    if (currentTrackerViewerCurrentVersionIndex.value >= 0) {
      return currentTrackerViewerVersions.value[currentTrackerViewerCurrentVersionIndex.value] || null
    }
    return getTrackerPlaybackVersion(currentTrackerViewerShot.value, trackerViewerMode.value || 'latest')
  })
  const currentTrackerViewerVersionLabel = computed(() => {
    const fallback = currentTrackerViewerCurrentVersionIndex.value >= 0
      ? currentTrackerViewerCurrentVersionIndex.value + 1
      : currentTrackerViewerVersions.value.length || null
    return formatTrackerVersionLabel(currentTrackerViewerCurrentVersion.value, fallback)
  })

  function getComparableVersionFamily(version) {
    if (!version || version.is_pdf) return 'unsupported'
    if (version.is_image === true) return 'image'
    const path = version.path || version.file_path || ''
    const extension = path.split('.').pop()?.toLowerCase?.() || ''
    if (compareImageExtensions.has(extension)) return 'image'
    return path ? 'video' : 'unsupported'
  }

  function getComparableShotVersions(shot, anchorVersion = null) {
    const versions = getShotVersions(shot)
    const anchor = anchorVersion || versions[versions.length - 1] || null
    const family = getComparableVersionFamily(anchor)
    return family === 'unsupported'
      ? []
      : versions.filter(version => getComparableVersionFamily(version) === family)
  }

  function canCompareShotVersions(shot, anchorVersion = null) {
    return Boolean(
      !isMobile.value
      && trackerToolEnabledForContext(currentTrackerRef.value, 'comparison')
      && getComparableShotVersions(shot, anchorVersion).length >= 2
    )
  }

  const currentTrackerViewerComparableVersions = computed(() => {
    return getComparableShotVersions(
      currentTrackerViewerShot.value,
      currentTrackerViewerCurrentVersion.value,
    )
  })
  const canCompareTrackerViewerVersions = computed(() => (
    currentMediaRef.value?._openedFromTracker &&
    currentTrackerViewerShot.value &&
    canCompareShotVersions(
      currentTrackerViewerShot.value,
      currentTrackerViewerCurrentVersion.value,
    )
  ))

  function getTrackerVersionCompareLabel(version) {
    const index = currentTrackerViewerVersions.value.findIndex(item => item?.id === version?.id)
    return formatTrackerVersionLabel(version, index >= 0 ? index + 1 : currentTrackerViewerVersions.value.length || 1)
  }

  function getTrackerVersionCompareKey(version) {
    return String(version?.id || version?.version_id || version?.horizons_shot_version_id ||
      version?.media_asset_id || version?.path || version?.file_path || '')
  }

  const versionCompareOptions = computed(() => [...currentTrackerViewerComparableVersions.value]
    .reverse()
    .map(version => ({ value: getTrackerVersionCompareKey(version), label: getTrackerVersionCompareLabel(version) }))
    .filter(option => option.value))
  const versionComparePrimaryMedia = computed(() => (
    currentTrackerViewerShot.value && versionComparePrimaryVersion.value
      ? buildTrackerViewerItem(currentTrackerViewerShot.value, trackerViewerMode.value || 'latest', versionComparePrimaryVersion.value)
      : null
  ))
  const versionCompareSecondaryMedia = computed(() => (
    currentTrackerViewerShot.value && versionCompareSecondaryVersion.value
      ? buildTrackerViewerItem(currentTrackerViewerShot.value, trackerViewerMode.value || 'latest', versionCompareSecondaryVersion.value)
      : null
  ))
  const versionComparePrimaryLabel = computed(() => getTrackerVersionCompareLabel(versionComparePrimaryVersion.value))
  const versionCompareSecondaryLabel = computed(() => getTrackerVersionCompareLabel(versionCompareSecondaryVersion.value))
  const versionComparePrimaryKey = computed(() => getTrackerVersionCompareKey(versionComparePrimaryVersion.value))
  const versionCompareSecondaryKey = computed(() => getTrackerVersionCompareKey(versionCompareSecondaryVersion.value))

  function findCompareVersionIndex(version) {
    const key = getTrackerVersionCompareKey(version)
    return currentTrackerViewerComparableVersions.value.findIndex(item => getTrackerVersionCompareKey(item) === key)
  }
  function findAdjacentCompareVersion(version, direction) {
    const index = findCompareVersionIndex(version)
    return index < 0 ? null : currentTrackerViewerComparableVersions.value[index + direction] || null
  }
  function findCompareVersionByKey(key) {
    const normalized = String(key || '')
    return normalized
      ? currentTrackerViewerComparableVersions.value.find(version => getTrackerVersionCompareKey(version) === normalized) || null
      : null
  }
  function setVersionComparePrimary(key) {
    const next = findCompareVersionByKey(key)
    if (!next) return
    const newer = findAdjacentCompareVersion(next, 1)
    if (!newer) {
      versionComparePrimaryVersion.value = findAdjacentCompareVersion(next, -1) || versionComparePrimaryVersion.value
      versionCompareSecondaryVersion.value = next
      void recordTrackerMediaView(currentTrackerViewerShot.value, versionComparePrimaryVersion.value, 'latest')
      void recordTrackerMediaView(currentTrackerViewerShot.value, versionCompareSecondaryVersion.value, 'latest')
      return
    }
    const sameOrNewer = getTrackerVersionCompareKey(next) === getTrackerVersionCompareKey(versionCompareSecondaryVersion.value) ||
      findCompareVersionIndex(next) >= findCompareVersionIndex(versionCompareSecondaryVersion.value)
    versionComparePrimaryVersion.value = next
    if (sameOrNewer) versionCompareSecondaryVersion.value = newer
    void recordTrackerMediaView(currentTrackerViewerShot.value, versionComparePrimaryVersion.value, 'latest')
    void recordTrackerMediaView(currentTrackerViewerShot.value, versionCompareSecondaryVersion.value, 'latest')
  }
  function setVersionCompareSecondary(key) {
    const next = findCompareVersionByKey(key)
    if (!next) return
    const older = findAdjacentCompareVersion(next, -1)
    if (!older) {
      versionComparePrimaryVersion.value = next
      versionCompareSecondaryVersion.value = findAdjacentCompareVersion(next, 1) || versionCompareSecondaryVersion.value
      void recordTrackerMediaView(currentTrackerViewerShot.value, versionComparePrimaryVersion.value, 'latest')
      void recordTrackerMediaView(currentTrackerViewerShot.value, versionCompareSecondaryVersion.value, 'latest')
      return
    }
    const sameOrOlder = getTrackerVersionCompareKey(next) === getTrackerVersionCompareKey(versionComparePrimaryVersion.value) ||
      findCompareVersionIndex(versionComparePrimaryVersion.value) >= findCompareVersionIndex(next)
    versionCompareSecondaryVersion.value = next
    if (sameOrOlder) versionComparePrimaryVersion.value = older
    void recordTrackerMediaView(currentTrackerViewerShot.value, versionComparePrimaryVersion.value, 'latest')
    void recordTrackerMediaView(currentTrackerViewerShot.value, versionCompareSecondaryVersion.value, 'latest')
  }
  async function startTrackerVersionCompare(shot = null) {
    const targetShot = shot || currentTrackerViewerShot.value
    const currentShotId = currentTrackerViewerShot.value?.id || currentTrackerViewerShot.value?.shot_id
    const targetShotId = targetShot?.id || targetShot?.shot_id
    const anchorVersion = currentShotId && currentShotId === targetShotId
      ? currentTrackerViewerCurrentVersion.value
      : null
    const versions = getComparableShotVersions(targetShot, anchorVersion)
    const primaryVersion = versions[versions.length - 2] || null
    const secondaryVersion = versions[versions.length - 1] || null
    if (!canCompareShotVersions(targetShot, anchorVersion) || !primaryVersion || !secondaryVersion) return
    if (!currentMediaRef.value?._openedFromTracker || currentShotId !== targetShotId) {
      openTrackerViewerVersion(targetShot, secondaryVersion, { mode: 'latest' })
      await nextTick()
    }
    videoEl.value?.pause?.()
    dismissTrackerViewerVersionSwitcher()
    showStatusPicker.value = null
    isDrawingMode.value = false
    versionComparePrimaryVersion.value = primaryVersion
    versionCompareSecondaryVersion.value = secondaryVersion
    versionCompareMode.value = 'side-by-side'
    versionCompareActive.value = true
    void recordTrackerMediaView(targetShot, primaryVersion, 'latest')
    void recordTrackerMediaView(targetShot, secondaryVersion, 'latest')
  }
  function exitVersionCompare() {
    versionCompareActive.value = false
    versionComparePrimaryVersion.value = null
    versionCompareSecondaryVersion.value = null
  }

  const trackerViewerShots = computed(() => {
    if (!currentTrackerRef.value || !currentMediaRef.value?._openedFromTracker) return []
    const mode = trackerViewerMode.value || 'latest'
    return trackerShotsForDisplay.value.filter(shot => Boolean(buildTrackerViewerItem(shot, mode)))
  })
  const currentTrackerViewerIndex = computed(() => currentTrackerViewerShot.value
    ? trackerViewerShots.value.findIndex(shot => shot?.shot_id === currentTrackerViewerShot.value?.shot_id)
    : -1)
  const showTrackerViewerStepper = computed(() => !versionCompareActive.value && Boolean(
    currentTrackerRef.value && currentMediaRef.value?._openedFromTracker &&
    trackerViewerShots.value.length > 1 && currentTrackerViewerIndex.value >= 0,
  ))
  const showTrackerViewerKeyboardGuide = computed(() => !versionCompareActive.value && Boolean(
    currentMediaRef.value?._openedFromTracker && currentTrackerViewerShot.value,
  ))
  const trackerViewerSequenceLabel = computed(() => currentTrackerViewerIndex.value < 0
    ? ''
    : `${currentTrackerViewerIndex.value + 1} of ${trackerViewerShots.value.length}`)
  const currentTrackerViewerStatusOption = computed(() => currentTrackerViewerShot.value
    ? trackerStatusOptions.value.find(option => option.value === currentTrackerViewerShot.value.status) || null
    : null)
  const showTrackerViewerVersionSwitcher = computed(() => Boolean(
    !versionCompareActive.value && currentMediaRef.value?._openedFromTracker &&
    currentTrackerViewerShot.value && currentTrackerViewerVersions.value.length,
  ))
  const showTrackerViewerStatusControl = computed(() => (
    !isMobile.value && !versionCompareActive.value && isViewingVideo.value &&
    Boolean(currentTrackerViewerShot.value && currentTrackerViewerStatusOption.value)
  ))
  const canEditVersionSummaries = computed(() => Boolean(isAdmin.value && !shareModeRef.value && currentProjectRef.value))
  const canStepToPreviousTrackerMedia = computed(() => showTrackerViewerStepper.value && currentTrackerViewerIndex.value > 0)
  const canStepToNextTrackerMedia = computed(() => (
    showTrackerViewerStepper.value && currentTrackerViewerIndex.value < trackerViewerShots.value.length - 1
  ))

  watch([showTrackerViewerVersionSwitcher, isMobile], ([visible, mobile], previousValues = []) => {
    if (!visible || mobile !== previousValues[1]) dismissTrackerViewerVersionSwitcher()
  })
  watch(isMobile, (mobile) => {
    if (mobile && versionCompareActive.value) exitVersionCompare()
  })
  watch(canCompareTrackerViewerVersions, (available) => {
    if (!available && versionCompareActive.value) exitVersionCompare()
  })

  function stepTrackerMedia(direction) {
    const index = currentTrackerViewerIndex.value + direction
    if (index >= 0 && index < trackerViewerShots.value.length) {
      openTrackerViewerShot(trackerViewerShots.value[index], trackerViewerMode.value || 'latest')
      return true
    }
    return false
  }
  function stepTrackerViewerVersion(direction) {
    if (!currentTrackerViewerShot.value || !currentTrackerViewerVersions.value.length) return false
    const currentIndex = currentTrackerViewerCurrentVersionIndex.value >= 0
      ? currentTrackerViewerCurrentVersionIndex.value
      : currentTrackerViewerVersions.value.length - 1
    const version = currentTrackerViewerVersions.value[currentIndex + direction]
    if (!(version?.path || version?.file_path)) return false
    openTrackerViewerVersion(currentTrackerViewerShot.value, version, {
      mode: trackerViewerMode.value || 'latest',
      preserveSidebar: true,
    })
    return true
  }
  function isTrackerNavigationTarget(target) {
    const tagName = String(target?.tagName || '').toUpperCase()
    if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A'].includes(tagName)) return true
    if (target?.isContentEditable) return true
    return Boolean(target?.closest?.('input, textarea, select, button, a, [contenteditable], [role="dialog"], [role="menu"], [role="listbox"], [role="slider"], [role="tab"], [role="option"]'))
  }
  function handleTrackerViewerKeydown(event, { disabled = false } = {}) {
    if (
      disabled
      || versionCompareActive.value
      || !currentMediaRef.value?._openedFromTracker
      || event.defaultPrevented
      || event.ctrlKey
      || event.metaKey
      || event.altKey
      || event.shiftKey
      || isTrackerNavigationTarget(event.target)
    ) return false

    const shotDirection = {
      BracketLeft: -1,
      BracketRight: 1,
      Numpad4: -1,
      Numpad6: 1,
    }[event.code]
    if (shotDirection) {
      event.preventDefault()
      stepTrackerMedia(shotDirection)
      return true
    }

    const versionDirection = {
      ArrowDown: -1,
      ArrowUp: 1,
      Numpad2: -1,
      Numpad8: 1,
    }[event.code]
    if (versionDirection) {
      event.preventDefault()
      stepTrackerViewerVersion(versionDirection)
      return true
    }
    return false
  }
  function toggleTrackerViewerVersionSwitcher() {
    if (!showTrackerViewerVersionSwitcher.value) return
    showStatusPicker.value = null
    trackerViewerVersionSwitcherOpen.value = !trackerViewerVersionSwitcherOpen.value
  }
  function selectTrackerViewerVersion(version) {
    if (!currentTrackerViewerShot.value || !(version?.path || version?.file_path) || versionMatchesCurrentMedia(version)) return
    openTrackerViewerVersion(currentTrackerViewerShot.value, version, {
      mode: trackerViewerMode.value || 'latest',
      preserveSidebar: true,
    })
  }
  async function deleteTrackerViewerVersion(version) {
    if (!currentTrackerViewerShot.value) return
    dismissTrackerViewerVersionSwitcher()
    await deleteShotVersion(currentTrackerViewerShot.value, version)
  }
  async function updateTrackerVersionSummary(shot, version, notes) {
    if (!canEditVersionSummaries.value || !currentProjectRef.value || !shot || !version) return
    const versionId = version.id || version.version_id || version.horizons_shot_version_id
    if (!versionId) return
    const { data } = await api.put(
      `/api/horizons/projects/${encodeURIComponent(currentProjectRef.value.id)}/shots/${encodeURIComponent(shot.id || shot.shot_id)}/versions/${encodeURIComponent(versionId)}`,
      { notes: String(notes || '').trim() || null },
    )
    const nextNotes = String(data?.notes || notes || '').trim()
    invalidateTrackerPayloads()
    const localVersion = (shot.versions || []).find(item => item?.id === versionId)
    if (localVersion) localVersion.notes = nextNotes
    version.notes = nextNotes
    if ([currentMediaRef.value?.horizons_shot_version_id, currentMediaRef.value?.version_id].includes(versionId)) {
      currentMediaRef.value.notes = nextNotes
    }
  }

  const updateCurrentTrackerViewerVersionSummary = (version, notes) => (
    updateTrackerVersionSummary(currentTrackerViewerShot.value, version, notes)
  )
  async function updateTrackerVersionPublication(shot, version, state) {
    if (!canManagePublication() || !currentProjectRef.value || !shot || !version) return
    const projectId = currentProjectRef.value.id
    const tracker = currentTrackerRef.value
    const trackerId = trackerRef(tracker)
    const shotId = shot.id || shot.shot_id
    const versionId = version.id || version.version_id || version.horizons_shot_version_id
    if (!projectId || !trackerId || !shotId || !versionId) return
    const previousShareState = String(version?.share_state || '').trim().toLowerCase()
    const versionLabel = getVersionDisplayLabel(version)

    const { data } = await api.post(
      `/api/projects/${encodeURIComponent(projectId)}/trackers/${encodeURIComponent(trackerId)}/shots/${encodeURIComponent(shotId)}/versions/${encodeURIComponent(versionId)}/publication`,
      { state },
    )
    const changedVersions = data?.versions || []
    invalidateTrackerPayloads()
    if (data?.shot_status) shot.status = data.shot_status
    for (const changed of changedVersions) {
      const localVersion = (shot.versions || []).find(item => item?.id === changed.id)
      if (localVersion) {
        localVersion.share_state = changed.share_state
        localVersion.published_at = changed.published_at
        localVersion.updated_at = changed.updated_at
      }
      if ([currentMediaRef.value?.horizons_shot_version_id, currentMediaRef.value?.version_id].includes(changed.id)) {
        currentMediaRef.value.share_state = changed.share_state
        currentMediaRef.value.published_at = changed.published_at
        currentMediaRef.value.updated_at = changed.updated_at
      }
    }
    const autoInternalizedCount = changedVersions.filter(changed => (
      changed?.id !== versionId && changed?.share_state === 'internal'
    )).length
    let publicationMessage = 'Version kept internal.'
    if (state === 'published') {
      if (data?.shot_status_changed) {
        publicationMessage = `${versionLabel} published. ${shot.shot_id || shot.shot_code || 'Shot'} moved to Review.`
      } else if (data?.is_latest_version === false && previousShareState !== 'published') {
        publicationMessage = `${versionLabel} published. Shot status stayed unchanged because a newer version exists.`
      } else {
        publicationMessage = `${versionLabel} published to shares.`
      }
    }
    notify(
      `${publicationMessage}${autoInternalizedCount ? ` ${autoInternalizedCount} older pending version${autoInternalizedCount === 1 ? '' : 's'} kept internal.` : ''}`,
    )
  }

  const updateCurrentTrackerViewerVersionPublication = (version, state) => (
    updateTrackerVersionPublication(currentTrackerViewerShot.value, version, state)
  )
  function openViewerVersionUpload() {
    if (!currentTrackerViewerShot.value) return
    dismissTrackerViewerVersionSwitcher()
    openVersionUpload(currentTrackerViewerShot.value)
  }

  return {
    getShotVersions,
    formatVersionDate,
    formatVersionDateShort,
    getShotLatestCreatedAt,
    formatShotLatestAdded,
    openVersionUpload,
    deleteShotVersion,
    openShotVideo,
    playShotVersion,
    downloadVersion,
    trackerViewerVersionSwitcherOpen,
    trackerViewerMode,
    currentTrackerViewerShot,
    currentTrackerViewerVersions,
    currentTrackerViewerVersionsDescending,
    currentTrackerViewerCurrentVersion,
    currentTrackerViewerVersionLabel,
    versionCompareActive,
    versionCompareMode,
    versionCompareOptions,
    versionComparePrimaryMedia,
    versionCompareSecondaryMedia,
    versionComparePrimaryLabel,
    versionCompareSecondaryLabel,
    versionComparePrimaryKey,
    versionCompareSecondaryKey,
    canCompareTrackerViewerVersions,
    canCompareShotVersions,
    trackerViewerSequenceLabel,
    showTrackerViewerStepper,
    showTrackerViewerKeyboardGuide,
    currentTrackerViewerStatusOption,
    showTrackerViewerVersionSwitcher,
    showTrackerViewerStatusControl,
    canEditVersionSummaries,
    canStepToPreviousTrackerMedia,
    canStepToNextTrackerMedia,
    formatTrackerVersionLabel,
    openTrackerViewerVersion,
    openTrackerViewerShot,
    openTrackerShotVideo,
    startTrackerVersionCompare,
    exitVersionCompare,
    setVersionComparePrimary,
    setVersionCompareSecondary,
    stepTrackerMedia,
    stepTrackerViewerVersion,
    handleTrackerViewerKeydown,
    dismissTrackerViewerVersionSwitcher,
    toggleTrackerViewerVersionSwitcher,
    selectTrackerViewerVersion,
    downloadTrackerViewerVersion: downloadVersion,
    deleteTrackerViewerVersion,
    updateTrackerVersionPublication,
    updateCurrentTrackerViewerVersionSummary,
    updateCurrentTrackerViewerVersionPublication,
    openViewerVersionUpload,
  }
}
