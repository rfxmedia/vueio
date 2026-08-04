import { computed, ref, watch } from 'vue'
import api, {
  buildShareCredentialQuery,
  getApiErrorMessage,
  resolveAccessEndpoint,
} from '../lib/api'
import { buildCommentBatchTarget, chunkCommentTargets } from '../lib/commentTargets'
import { getCanonicalMediaRefs, normalizeMediaEntity } from '../lib/mediaEntity'
import { recordRecentlyViewed } from '../lib/recentlyViewed'
import { formatSizeBytes } from '../utils/formatters'
import { zipNameFromParts } from '../utils/filenames'
import { notify } from '../utils/toasts'
import { BULK_UNASSIGNED_VALUE, BULK_UNCATEGORIZED_VALUE } from './useTrackerListController'

const EMPTY_STATS = Object.freeze({
  totalDuration: 0,
  totalFrames: 0,
  totalShots: 0,
  totalVersions: 0,
  averageVersionsPerShot: 0,
  averageShotDuration: 0,
  statusBreakdown: [],
})

export function useTrackerWorkspaceController(ctx) {
  const trackerStats = ref({ ...EMPTY_STATS })
  const trackerActivity = ref([])
  const trackerActivityLoading = ref(false)
  const trackerActivityNextBefore = ref(null)
  const bulkActionBusy = ref(false)
  const trackerDownloadBusy = ref(false)
  const trackerDownloadProgress = ref(null)
  let trackerStatsGeneration = 0
  let trackerActivityGeneration = 0

  const trackerTotalDuration = computed(() => {
    const seconds = trackerStats.value.totalDuration || 0
    if (seconds === 0) return '0:00'
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
  })
  const trackerTotalFrames = computed(() => trackerStats.value.totalFrames || 0)
  const trackerActivityHasMore = computed(() => trackerActivityNextBefore.value !== null)
  const trackerRef = () => ctx.currentTrackerRef.value
  const list = () => ctx.getListController?.() || {}

  watch(ctx.canViewTrackerDetails, (available) => {
    if (!ctx.currentTracker.value) return
    if (!available) {
      resetTrackerDetails()
      return
    }
    void Promise.all([
      loadTrackerStats(ctx.currentTrackerRef.value),
      loadTrackerActivity(ctx.currentTrackerRef.value),
    ])
  })

  function getShotAssigneeIds(shot) {
    const ids = Array.isArray(shot?.assignee_user_ids) ? shot.assignee_user_ids : []
    const fallbackId = shot?.assignee_user_id || shot?.assignee?.id || null
    return Array.from(new Set([...ids, fallbackId].filter(Boolean)))
  }

  function getShotAssignees(shot) {
    const assignees = Array.isArray(shot?.assignees) ? shot.assignees : []
    if (assignees.length) return assignees
    return shot?.assignee ? [shot.assignee] : []
  }

  function getShotAssigneeLabel(shot) {
    const assignees = getShotAssignees(shot)
    if (!assignees.length) return 'Unassigned'
    const primary = assignees[0]?.display_name || assignees[0]?.username || 'Assigned'
    return assignees.length === 1 ? primary : `${primary} +${assignees.length - 1}`
  }

  function isShotAssignedTo(shot, assigneeUserId) {
    return getShotAssigneeIds(shot).includes(assigneeUserId)
  }

  function applyShotAssignees(shot, assigneeIds) {
    const nextIds = Array.from(new Set((assigneeIds || []).filter(Boolean)))
    shot.assignee_user_ids = nextIds
    shot.assignee_user_id = nextIds[0] || null
    shot.assignees = nextIds.map(id => {
      const candidate = ctx.assignmentCandidates.value.find(item => item.id === id)
      return candidate ? {
        id: candidate.id,
        username: candidate.username,
        display_name: candidate.display_name,
        role: candidate.role,
      } : null
    }).filter(Boolean)
    shot.assignee = shot.assignees[0] || null
  }

  async function selectShotAssignee(shot, assigneeUserId) {
    if (!list().canAssignShots?.value || !shot) return
    await ctx.loadProjectTeamOptions()
    const previousIds = getShotAssigneeIds(shot)
    const previousAssignee = shot.assignee ? { ...shot.assignee } : null
    const previousAssignees = getShotAssignees(shot).map(item => ({ ...item }))
    const nextIds = assigneeUserId
      ? (previousIds.includes(assigneeUserId) ? previousIds.filter(id => id !== assigneeUserId) : [...previousIds, assigneeUserId])
      : []
    if (nextIds.length === previousIds.length && nextIds.every((id, index) => id === previousIds[index])) return
    applyShotAssignees(shot, nextIds)
    try {
      await saveShot(shot)
      await Promise.all([ctx.loadProjectTeamOptions(true), ctx.loadProjects(), ctx.refreshProjectContents()])
    } catch (error) {
      shot.assignee_user_ids = previousIds
      shot.assignee_user_id = previousIds[0] || null
      shot.assignees = previousAssignees
      shot.assignee = previousAssignee
      notify(getApiErrorMessage(error, 'Failed to assign shot'))
    }
  }

  function resetTrackerDetails() {
    trackerStats.value = { ...EMPTY_STATS }
    trackerActivity.value = []
    trackerActivityNextBefore.value = null
  }

  function trackerRequestStillOwned(generation, latestGeneration, guard) {
    return generation === latestGeneration() && (!guard || guard())
  }

  async function loadTrackerStats(name, options = {}) {
    if (!ctx.currentProject.value) return
    if (!ctx.canViewTrackerDetails.value) {
      resetTrackerDetails()
      return
    }
    const generation = ++trackerStatsGeneration
    const ownsCommit = () => trackerRequestStillOwned(generation, () => trackerStatsGeneration, options.guard)
    try {
      const shareId = ctx.shareMode.value ? (options.shareId || ctx.pendingShareId.value) : null
      const endpoint = resolveAccessEndpoint({
        shareId,
        shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}/stats`,
        authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}/stats`,
      })
      const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
      const { data } = await api.get(`${endpoint}${query}`)
      if (ownsCommit()) trackerStats.value = data
    } catch (error) {
      if (ownsCommit()) throw error
    }
  }

  async function loadTrackerActivity(name, { append = false, before = null, guard = null, shareId: requestedShareId = null } = {}) {
    if (!ctx.currentProject.value) return
    if (!ctx.canViewTrackerDetails.value) {
      resetTrackerDetails()
      return
    }
    const generation = ++trackerActivityGeneration
    const ownsCommit = () => trackerRequestStillOwned(generation, () => trackerActivityGeneration, guard)
    if (ownsCommit()) trackerActivityLoading.value = true
    try {
      const shareId = ctx.shareMode.value ? (requestedShareId || ctx.pendingShareId.value) : null
      const endpoint = resolveAccessEndpoint({
        shareId,
        shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}/activity`,
        authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}/activity`,
      })
      const query = buildShareCredentialQuery(
        { limit: 40, ...(before !== null ? { before } : {}) },
        shareId ? ctx.getShareCredential({ shareId }) : {},
      )
      const { data } = await api.get(`${endpoint}${query}`)
      if (!ownsCommit()) return
      const items = data?.items || []
      trackerActivity.value = append ? [...trackerActivity.value, ...items] : items
      trackerActivityNextBefore.value = data?.next_before ?? null
    } catch (error) {
      if (ownsCommit()) throw error
    } finally {
      if (ownsCommit()) trackerActivityLoading.value = false
    }
  }

  async function loadMoreTrackerActivity() {
    if (!trackerRef() || trackerActivityLoading.value || trackerActivityNextBefore.value === null) return
    await loadTrackerActivity(trackerRef(), { append: true, before: trackerActivityNextBefore.value })
  }

  async function loadTrackerCommentCounts(tracker) {
    const targets = []
    for (const shot of tracker.shots || []) {
      const latest = (shot.versions || []).at(-1)
      if (!latest?.file_path) continue
      targets.push(buildCommentBatchTarget({
        path: latest.file_path,
        horizons_media_asset_id: latest.media_asset_id || null,
        horizons_shot_version_id: latest.id || null,
      }))
    }
    if (!targets.length) return
    try {
      const merged = {}
      for (const chunk of chunkCommentTargets(targets)) {
        const body = { targets: chunk }
        const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
        if (!shareId && ctx.currentProject.value?.id) body.project_id = ctx.currentProject.value.id
        const query = buildShareCredentialQuery(
          shareId ? { share_id: shareId } : {},
          shareId ? ctx.getShareCredential({ shareId }) : {},
        )
        const { data } = await api.post(`/api/comments/counts/batch${query}`, body)
        for (const item of data?.items || []) if (item?.key) merged[item.key] = item.count || 0
      }
      ctx.commentCounts.value = { ...ctx.commentCounts.value, ...merged }
    } catch (error) {
      console.error('Failed to load tracker comment counts')
    }
  }

  function setTrackerCommentCount(target, count) {
    if (!target?.key || !Number.isFinite(count)) return
    ctx.commentCounts.value = { ...ctx.commentCounts.value, [target.key]: count }
  }

  async function openTracker(name, skipRouteUpdate = false) {
    if (!ctx.currentProject.value) return
    try {
      const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
      const endpoint = resolveAccessEndpoint({
        shareId,
        shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}`,
        authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}`,
      })
      const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
      const { data } = await api.get(`${endpoint}${query}`)
      data.shots.forEach(shot => { shot._originalId = shot.shot_id })
      ctx.currentTracker.value = data
      ctx.currentPage.value = null
      if (!ctx.shareMode.value) void ctx.loadProjectTeamOptions()
      const canonicalRef = data.id || data.slug || name
      const details = ctx.canViewTrackerDetails.value
        ? [loadTrackerStats(canonicalRef), loadTrackerActivity(canonicalRef)]
        : [resetTrackerDetails()]
      await Promise.all([loadTrackerCommentCounts(data), ...details])
      if (!ctx.shareMode.value) {
        recordRecentlyViewed({
          type: 'tracker',
          id: data.slug || data.id || name,
          projectId: ctx.currentProject.value.id,
          title: data.name || name,
          subtitle: ctx.currentProject.value.title || 'Tracker',
        })
      }
      if (!skipRouteUpdate && !ctx.shareMode.value) {
        ctx.router.push({
          name: 'project-tracker',
          params: { projectId: ctx.currentProject.value.id, tracker: data.slug || data.id || name },
        })
      }
    } catch (error) {
      console.error('Failed to load tracker')
      notify('Failed to load tracker')
    }
  }

  async function openProjectTracker(projectId, name) {
    await ctx.openProject(projectId, true)
    await openTracker(name, false)
  }

  function closeTracker() {
    ctx.closeTrackerSettingsModal()
    ctx.currentTracker.value = null
    resetTrackerDetails()
    if (ctx.shareMode.value && ctx.sharedItemType.value === 'page' && ctx.currentProject.value?.page) {
      ctx.currentPage.value = ctx.currentProject.value.page
      return
    }
    if (!ctx.shareMode.value && ctx.currentProject.value) {
      ctx.router.push({ name: 'project-folder', params: { projectId: ctx.currentProject.value.id } })
    }
  }

  async function createTracker() {
    if (!ctx.newTrackerName.value.trim() || !ctx.currentProject.value) return
    try {
      await api.post(`/api/projects/${ctx.currentProject.value.id}/trackers`, { name: ctx.newTrackerName.value })
      ctx.newTrackerName.value = ''
      ctx.showCreateTracker.value = false
      await ctx.refreshProjectContents()
    } catch (error) {
      ctx.handleError('Failed to create tracker', error)
    }
  }

  async function deleteTracker(name) {
    if (!ctx.currentProject.value || !confirm(`Delete tracker "${name}" and all its shots?`)) return
    try {
      await api.delete(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}`)
      await ctx.refreshProjectContents()
    } catch (_error) {
      notify('Failed to delete tracker')
    }
  }

  async function refreshCurrentTrackerPreserveState() {
    if (!ctx.currentProject.value || !ctx.currentTracker.value) return
    const name = trackerRef()
    const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}`,
      authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}`,
    })
    const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
    const { data } = await api.get(`${endpoint}${query}`)
    data.shots?.forEach(shot => { shot._originalId = shot.shot_id })
    ctx.currentTracker.value = data
    await Promise.all([loadTrackerCommentCounts(data), loadTrackerStats(name), loadTrackerActivity(name)])
  }

  async function saveShot(shot) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value) return
    const originalShotCode = shot._originalId || shot.shot_id
    const shotRef = shot.id || originalShotCode
    if (!shotRef) return
    const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    const payload = { status: shot.status }
    if (!shareId && ctx.canEditDescription.value) payload.description = shot.description
    if (!shareId && shot.shot_id !== originalShotCode && ctx.canEditShotName.value) payload.new_shot_id = shot.shot_id
    if (!shareId && list().canAssignShots?.value) payload.assignee_user_ids = getShotAssigneeIds(shot)
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}`,
      authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}`,
    })
    const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
    await api.put(`${endpoint}${query}`, payload)
    if (!shareId) shot._originalId = shot.shot_id
    await loadTrackerActivity(trackerRef())
  }

  async function selectStatus(shot, status) {
    list().showStatusPicker.value = null
    if (!shot || !status || status === shot.status) return
    const previous = shot.status
    shot.status = status
    shot._statusSaving = true
    try {
      await saveShot(shot)
    } catch (error) {
      shot.status = previous
      notify(`Failed to update status: ${getApiErrorMessage(error)}`)
    } finally {
      shot._statusSaving = false
    }
  }

  function getShotRequestRef(shotOrId) {
    return shotOrId && typeof shotOrId === 'object'
      ? shotOrId.id || shotOrId._originalId || shotOrId.shot_id
      : shotOrId
  }

  async function deleteShot(shotOrId) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !ctx.canDeleteShots.value) return
    const shotRef = getShotRequestRef(shotOrId)
    if (!shotRef || !confirm('Delete this shot?')) return
    try {
      await api.delete(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}`)
      await openTracker(trackerRef())
    } catch (error) {
      ctx.handleError('Failed to delete shot', error)
    }
  }

  function removeShotSelection(shotOrId) {
    const selectionKey = list().getShotSelectionKey(shotOrId)
    if (!selectionKey) return
    const next = new Set(list().selectedShots.value)
    next.delete(selectionKey)
    list().selectedShots.value = next
  }

  async function archiveShot(shotOrId) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !list().canArchiveShots.value) return
    const shotRef = getShotRequestRef(shotOrId)
    if (!shotRef || !confirm('Archive this shot? It will move out of the active tracker but keep its versions, notes, and history.')) return
    try {
      await api.post(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}/archive`, {})
      removeShotSelection(shotOrId)
      await refreshCurrentTrackerPreserveState()
    } catch (error) {
      ctx.handleError('Failed to archive shot', error)
    }
  }

  async function restoreShot(shotOrId) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !list().canArchiveShots.value) return
    const shotRef = getShotRequestRef(shotOrId)
    if (!shotRef) return
    try {
      await api.post(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}/restore`, {})
      removeShotSelection(shotOrId)
      await refreshCurrentTrackerPreserveState()
    } catch (error) {
      ctx.handleError('Failed to restore shot', error)
    }
  }

  async function bulkUpdateShotSet(shots, update, failureMessage, onSuccess) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !ctx.canEditProject.value || bulkActionBusy.value) return
    const shotIds = (shots || []).map(getShotRequestRef).filter(Boolean)
    if (!shotIds.length) return
    bulkActionBusy.value = true
    try {
      await api.post(
        `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/bulk-update`,
        { shot_ids: shotIds, ...update },
      )
      onSuccess?.()
      await refreshCurrentTrackerPreserveState()
    } catch (error) {
      ctx.handleError(failureMessage, error)
    } finally {
      bulkActionBusy.value = false
    }
  }

  const bulkUpdateSelectedShots = (update) => bulkUpdateShotSet(
    list().selectedTrackerShots.value, update, 'Failed to update selected shots', list().clearActiveSelectedShots,
  )
  const bulkUpdateArchivedShots = (update) => bulkUpdateShotSet(
    list().selectedArchivedShots.value, update, 'Failed to update selected archived shots', list().clearArchivedSelectedShots,
  )
  const bulkUpdateShotStatus = status => list().canBulkUpdateStatus.value && status
    ? bulkUpdateSelectedShots({ status }) : undefined
  const bulkUpdateShotCategory = category => list().canBulkUpdateCategory.value && category
    ? bulkUpdateSelectedShots({ tag: category === BULK_UNCATEGORIZED_VALUE ? null : category }) : undefined
  const bulkUpdateShotAssignee = assignee => list().canBulkUpdateAssignee.value && assignee
    ? bulkUpdateSelectedShots({ assignee_user_ids: assignee === BULK_UNASSIGNED_VALUE ? [] : [assignee] }) : undefined
  const bulkUpdateArchivedShotStatus = status => list().canBulkUpdateStatus.value && status
    ? bulkUpdateArchivedShots({ status }) : undefined
  const bulkUpdateArchivedShotCategory = category => list().canBulkUpdateCategory.value && category
    ? bulkUpdateArchivedShots({ tag: category === BULK_UNCATEGORIZED_VALUE ? null : category }) : undefined
  const bulkUpdateArchivedShotAssignee = assignee => list().canBulkUpdateAssignee.value && assignee
    ? bulkUpdateArchivedShots({ assignee_user_ids: assignee === BULK_UNASSIGNED_VALUE ? [] : [assignee] }) : undefined

  async function bulkRestoreArchivedShots() {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !list().canArchiveShots.value || bulkActionBusy.value) return
    const shots = list().selectedArchivedShots.value
    if (!shots.length) return
    bulkActionBusy.value = true
    try {
      await Promise.all(shots.map(shot => {
        const shotRef = getShotRequestRef(shot)
        return shotRef
          ? api.post(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/${encodeURIComponent(shotRef)}/restore`, {})
          : Promise.resolve()
      }))
      list().clearArchivedSelectedShots()
      await refreshCurrentTrackerPreserveState()
    } catch (error) {
      ctx.handleError('Failed to restore selected archived shots', error)
    } finally {
      bulkActionBusy.value = false
    }
  }

  async function bulkDeleteShots() {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || !ctx.canDeleteShots.value || bulkActionBusy.value) return
    const shotIds = list().selectedTrackerShots.value.map(getShotRequestRef).filter(Boolean)
    if (!shotIds.length) return
    const count = shotIds.length
    if (!confirm(`Delete ${count} shot${count === 1 ? '' : 's'}? This removes the selected shot rows and version history from this tracker. Source files on disk will not be deleted.`)) return
    bulkActionBusy.value = true
    try {
      await api.post(
        `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/shots/bulk-delete`,
        { shot_ids: shotIds },
      )
      list().clearActiveSelectedShots()
      await openTracker(trackerRef())
    } catch (error) {
      ctx.handleError('Failed to delete selected shots', error)
    } finally {
      bulkActionBusy.value = false
    }
  }

  function describePackageJob(job) {
    if (!job) return 'Queued'
    if (job.status === 'queued') return `Scanning ${job.file_count || 0} files`
    if (job.status === 'packaging') {
      return `Packaging ${formatSizeBytes(job.packaged_bytes, { compact: true })} / ${formatSizeBytes(job.total_bytes, { compact: true })}`
    }
    if (job.status === 'ready') return 'Package ready'
    if (job.status === 'failed') return 'Package failed'
    return job.message || 'Packaging'
  }

  async function waitForPackageJob(jobId, accessQuery = '') {
    let lastJob = null
    for (let index = 0; index < 720; index += 1) {
      const { data: job } = await api.get(`/api/package-jobs/${jobId}${accessQuery}`)
      lastJob = job
      trackerDownloadProgress.value = { ...job, message: describePackageJob(job) }
      if (job.status === 'ready') return job
      if (job.status === 'failed') throw new Error(job.error || 'Package failed')
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
    throw new Error(lastJob?.message || 'Package timed out')
  }

  async function postTrackerLatestZip(url, payload, accessQuery = '') {
    const { data: job } = await api.post(url, payload)
    trackerDownloadProgress.value = { ...job, message: describePackageJob(job) }
    const ready = await waitForPackageJob(job.id, accessQuery)
    trackerDownloadProgress.value = { ...ready, progress: 100, message: 'Starting download' }
    ctx.triggerBrowserDownload(
      `/api/package-jobs/${ready.id}/download${accessQuery}`,
      ready.filename || payload?.filename || 'tracker-latest-versions.zip',
    )
  }

  async function downloadTrackerLatestVersions({ selectedOnly = false } = {}) {
    if (!ctx.currentProject.value || !ctx.currentTracker.value || trackerDownloadBusy.value) return
    if (!ctx.showShotDownloads.value) {
      notify('Downloads are disabled for this tracker.')
      return
    }
    const shots = selectedOnly ? list().selectedTrackerShots.value : list().trackerShotsForDisplay.value
    const shotIds = shots.map(getShotRequestRef).filter(Boolean)
    if (!shotIds.length) {
      notify(selectedOnly ? 'Select at least one shot with a latest version first.' : 'No visible shots with latest versions to download.')
      return
    }
    const zipName = zipNameFromParts([
      ctx.currentProject.value.title || ctx.currentProject.value.slug || 'project',
      ctx.currentTracker.value.name || 'tracker',
      selectedOnly ? 'selected-latest-versions' : 'latest-versions',
    ], 'tracker-latest-versions')
    const payload = { shot_ids: shotIds, filename: zipName }
    const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(trackerRef())}/download-latest-zip-job`,
      authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(trackerRef())}/download-latest-zip-job`,
    })
    const accessQuery = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
    const url = `${endpoint}${accessQuery}`
    trackerDownloadBusy.value = true
    trackerDownloadProgress.value = { status: 'queued', progress: 0, message: 'Scanning files' }
    try {
      await postTrackerLatestZip(url, payload, accessQuery)
    } catch (error) {
      notify(`Download All failed: ${await ctx.getPackageErrorMessage(error)}`)
    } finally {
      setTimeout(() => { trackerDownloadProgress.value = null }, 3000)
      trackerDownloadBusy.value = false
    }
  }

  function getAllLatestShotFiles(shot) {
    const latest = (shot?.versions || []).at(-1)
    if (!latest?.file_path) return []
    return [normalizeMediaEntity({
      ...latest,
      path: latest.path || latest.file_path,
      name: latest.name || latest.file_path.split('/').pop() || `${shot?.shot_id || 'shot'} latest version`,
      version_id: latest.id || null,
      horizons_shot_version_id: latest.id || null,
      media_asset_id: latest.media_asset_id || null,
      horizons_media_asset_id: latest.media_asset_id || null,
    })]
  }

  function getLatestShotFile(shot) {
    return list().getLatestShotFilePath(shot)
  }

  async function downloadShotFile(shot) {
    const files = getAllLatestShotFiles(shot)
    if (!files.length) return
    const zipName = `${String(shot?.shot_id || 'shot').trim() || 'shot'}-latest-version.zip`
    try {
      const direct = []
      const zipPaths = []
      for (const file of files) {
        const media = normalizeMediaEntity(file)
        const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
        if (shotVersionId || mediaAssetId || ctx.isProjectRenderPath(media?.path || '')) direct.push(media)
        else if (media?.path) zipPaths.push(media.path)
      }
      direct.forEach(media => ctx.triggerBrowserDownload(ctx.buildDownloadUrl(media), ctx.getDownloadFilename(media)))
      if (zipPaths.length) await ctx.downloadZip(zipPaths, zipName)
    } catch (error) {
      notify(`Download failed: ${getApiErrorMessage(error)}`)
    }
  }

  return {
    trackerStats,
    trackerActivity,
    trackerActivityLoading,
    trackerActivityHasMore,
    trackerTotalDuration,
    trackerTotalFrames,
    bulkActionBusy,
    trackerDownloadBusy,
    trackerDownloadProgress,
    getShotAssigneeIds,
    getShotAssignees,
    getShotAssigneeLabel,
    isShotAssignedTo,
    selectShotAssignee,
    resetTrackerDetails,
    loadTrackerStats,
    loadTrackerActivity,
    loadMoreTrackerActivity,
    loadTrackerCommentCounts,
    setTrackerCommentCount,
    openTracker,
    openProjectTracker,
    closeTracker,
    createTracker,
    deleteTracker,
    refreshCurrentTrackerPreserveState,
    saveShot,
    selectStatus,
    deleteShot,
    archiveShot,
    restoreShot,
    bulkUpdateShotStatus,
    bulkUpdateShotCategory,
    bulkUpdateShotAssignee,
    bulkUpdateArchivedShotStatus,
    bulkUpdateArchivedShotCategory,
    bulkUpdateArchivedShotAssignee,
    bulkRestoreArchivedShots,
    bulkDeleteShots,
    downloadTrackerLatestVersions,
    downloadSelectedTrackerLatestVersions: () => downloadTrackerLatestVersions({ selectedOnly: true }),
    getAllLatestShotFiles,
    getLatestShotFile,
    downloadShotFile,
  }
}
