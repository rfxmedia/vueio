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
import {
  invalidateTrackerPayloads,
  readWorkspacePayload,
  workspaceCacheKey,
  writeWorkspacePayload,
} from '../lib/workspacePayloadCache'

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
  const trackerActivityError = ref('')
  const trackerActivityNextBefore = ref(null)
  const activityRestoreBusyId = ref(null)
  const activityRestorePreview = ref(null)
  const activityRestorePreviewBusyId = ref(null)
  const trackerViews = ref([])
  const trackerViewersActive = ref([])
  const trackerViewsLoading = ref(false)
  const trackerViewsError = ref('')
  const trackerViewsNextBefore = ref(null)
  const trackerViewVisitId = ref('')
  const bulkActionBusy = ref(false)
  const shotActionBusyIds = ref(new Set())
  const trackerDownloadBusy = ref(false)
  const trackerDownloadProgress = ref(null)
  let trackerStatsGeneration = 0
  let trackerActivityGeneration = 0
  let trackerViewsGeneration = 0
  let trackerViewSessionGeneration = 0
  let trackerOpenGeneration = 0
  let trackerOpenController = null
  let trackerStatsController = null
  let trackerActivityController = null
  let trackerViewsController = null
  let trackerCommentsController = null
  let trackerViewOpenPromise = null

  const trackerTotalDuration = computed(() => {
    const seconds = trackerStats.value.totalDuration || 0
    if (seconds === 0) return '0:00'
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
  })
  const trackerTotalFrames = computed(() => trackerStats.value.totalFrames || 0)
  const trackerActivityHasMore = computed(() => trackerActivityNextBefore.value !== null)
  const canRestoreTrackerHistory = computed(() => (
    !ctx.shareMode.value &&
    ctx.canDeleteShots.value &&
    ctx.currentUser?.value?.role !== 'artist'
  ))
  const trackerViewsHasMore = computed(() => trackerViewsNextBefore.value !== null)
  const trackerRef = () => ctx.currentTrackerRef.value
  const list = () => ctx.getListController?.() || {}
  const currentUserScope = () => ctx.currentUser?.value?.id || 'session'

  function isCanceledRequest(error, signal = null) {
    return signal?.aborted
      || error?.name === 'CanceledError'
      || error?.code === 'ERR_CANCELED'
      || error?.name === 'AbortError'
  }

  function linkAbortSignal(signal, controller) {
    if (!signal) return () => {}
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) controller.abort()
    return () => signal.removeEventListener('abort', abort)
  }

  function trackerPayloadKey(
    name,
    projectId = ctx.currentProject.value?.id || '',
    userScope = currentUserScope(),
  ) {
    return workspaceCacheKey('tracker', userScope, projectId, name)
  }

  function cacheTrackerPayload(
    data,
    requestedName,
    projectId = ctx.currentProject.value?.id || '',
    userScope = currentUserScope(),
  ) {
    const refs = new Set([requestedName, data?.id, data?.slug, data?.name].filter(Boolean))
    for (const ref of refs) writeWorkspacePayload(trackerPayloadKey(ref, projectId, userScope), data)
  }

  function invalidateCurrentTrackerPayloads(projectId = ctx.currentProject.value?.id, userScope = currentUserScope()) {
    if (projectId) {
      invalidateTrackerPayloads(userScope, projectId)
    }
  }

  function captureTrackerContext() {
    const projectId = ctx.currentProject.value?.id
    const tracker = ctx.currentTracker.value
    const ref = trackerRef()
    if (!projectId || !tracker?.id || !ref) return null
    return {
      projectId,
      trackerId: tracker.id,
      trackerRef: ref,
      tracker,
      shareId: ctx.shareMode.value ? ctx.pendingShareId.value : null,
      userScope: currentUserScope(),
    }
  }

  function trackerContextIsCurrent(target) {
    return Boolean(
      target &&
      ctx.currentProject.value?.id === target.projectId &&
      ctx.currentTracker.value?.id === target.trackerId &&
      trackerRef() === target.trackerRef &&
      (ctx.shareMode.value ? ctx.pendingShareId.value : null) === target.shareId
    )
  }

  function setShotActionBusy(shotRef, busy) {
    const next = new Set(shotActionBusyIds.value)
    if (busy) next.add(String(shotRef))
    else next.delete(String(shotRef))
    shotActionBusyIds.value = next
  }

  function isShotActionBusy(shotOrId) {
    const shotRef = getShotRequestRef(shotOrId)
    return Boolean(shotRef && shotActionBusyIds.value.has(String(shotRef)))
  }

  async function refreshTrackerSummaries(target, { details = true, counts = false } = {}) {
    const tasks = []
    if (details && trackerContextIsCurrent(target)) {
      tasks.push(loadTrackerStats(target.trackerRef), loadTrackerActivity(target.trackerRef))
    }
    if (counts && ctx.currentProject.value?.id === target.projectId) {
      if (typeof ctx.loadProjects === 'function') tasks.push(ctx.loadProjects())
      if (typeof ctx.refreshProjectContents === 'function') tasks.push(ctx.refreshProjectContents())
    }
    await Promise.allSettled(tasks)
  }

  function hydrateTrackerPayload(data) {
    data?.shots?.forEach(shot => { shot._originalId = shot.shot_id })
    return data
  }

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
      await saveShot(shot, {
        fields: ['assignee_user_ids'],
        expectedValues: { assignee_user_ids: previousIds },
      })
      await Promise.allSettled([ctx.loadProjectTeamOptions(true), ctx.loadProjects(), ctx.refreshProjectContents()])
    } catch (error) {
      if (error?.response?.status === 409) {
        notify(getApiErrorMessage(error, 'This shot changed elsewhere.'), { tone: 'error' })
        await Promise.allSettled([refreshCurrentTrackerPreserveState()])
        return
      }
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
    trackerActivityError.value = ''
    activityRestoreBusyId.value = null
    activityRestorePreview.value = null
    activityRestorePreviewBusyId.value = null
    shotActionBusyIds.value = new Set()
    trackerViews.value = []
    trackerViewersActive.value = []
    trackerViewsNextBefore.value = null
    trackerViewsError.value = ''
  }

  function newTrackerVisitId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
    const random = Math.random().toString(36).slice(2)
    return `${Date.now().toString(36)}-${random}-${Math.random().toString(36).slice(2)}`.slice(0, 64)
  }

  function trackerViewRequestTarget() {
    const projectId = ctx.currentProject.value?.id
    const tracker = ctx.currentTracker.value
    const trackerName = trackerRef()
    if (!projectId || !tracker?.id || !trackerName) return null
    const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(trackerName)}/views`,
      authenticated: `/api/projects/${projectId}/trackers/${encodeURIComponent(trackerName)}/views`,
    })
    const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
    return {
      endpoint: `${endpoint}${query}`,
      projectId,
      trackerId: tracker.id,
    }
  }

  async function postTrackerView(payload, target) {
    if (!target) return null
    try {
      return await api.post(target.endpoint, payload)
    } catch (_error) {
      // Viewing telemetry is deliberately best-effort and must never interrupt review.
      return null
    }
  }

  async function startTrackerViewSession() {
    const target = trackerViewRequestTarget()
    if (!target) return
    const generation = ++trackerViewSessionGeneration
    const visitId = newTrackerVisitId()
    trackerViewVisitId.value = visitId
    trackerViewOpenPromise = postTrackerView({ action: 'open', visit_id: visitId }, target)
    await trackerViewOpenPromise
    if (generation !== trackerViewSessionGeneration || target.trackerId !== ctx.currentTracker.value?.id) return
  }

  function stopTrackerViewSession() {
    trackerViewSessionGeneration += 1
    trackerViewVisitId.value = ''
    trackerViewOpenPromise = null
  }

  async function heartbeatTrackerViewSession() {
    const visitId = trackerViewVisitId.value
    const target = trackerViewRequestTarget()
    if (!visitId || !target) return
    const generation = trackerViewSessionGeneration
    await trackerViewOpenPromise
    if (generation !== trackerViewSessionGeneration || visitId !== trackerViewVisitId.value) return
    await postTrackerView({ action: 'heartbeat', visit_id: visitId }, target)
  }

  async function recordTrackerMediaView(shot, version, mode = 'latest') {
    const visitId = trackerViewVisitId.value
    const target = trackerViewRequestTarget()
    const shotId = shot?.id || shot?._originalId || shot?.shot_id
    if (!visitId || !target || !shotId) return
    const isBrief = mode === 'brief'
    const versionId = version?.id || version?.version_id || version?.horizons_shot_version_id || null
    if (!isBrief && !versionId) return
    const generation = trackerViewSessionGeneration
    await trackerViewOpenPromise
    if (generation !== trackerViewSessionGeneration || visitId !== trackerViewVisitId.value) return
    await postTrackerView({
      action: 'media',
      visit_id: visitId,
      shot_id: shotId,
      version_id: isBrief ? null : versionId,
      media_context: isBrief ? 'brief' : 'version',
    }, target)
  }

  async function loadTrackerViews({ append = false, before = null } = {}) {
    if (!ctx.isAdmin?.value || ctx.shareMode.value || !ctx.currentProject.value || !ctx.currentTracker.value) {
      trackerViews.value = []
      trackerViewersActive.value = []
      trackerViewsNextBefore.value = null
      trackerViewsError.value = ''
      return
    }
    const generation = ++trackerViewsGeneration
    trackerViewsController?.abort()
    const controller = new AbortController()
    trackerViewsController = controller
    trackerViewsLoading.value = true
    trackerViewsError.value = ''
    const projectId = ctx.currentProject.value.id
    const trackerId = ctx.currentTracker.value.id
    const endpoint = `/api/projects/${projectId}/trackers/${encodeURIComponent(trackerRef())}/views`
    const query = buildShareCredentialQuery({ limit: 50, ...(before !== null ? { before } : {}) })
    try {
      const { data } = await api.get(`${endpoint}${query}`, { signal: controller.signal })
      if (generation !== trackerViewsGeneration || trackerId !== ctx.currentTracker.value?.id) return
      const items = Array.isArray(data?.items) ? data.items : []
      trackerViews.value = append ? [...trackerViews.value, ...items] : items
      trackerViewersActive.value = Array.isArray(data?.active) ? data.active : []
      trackerViewsNextBefore.value = data?.next_before ?? null
    } catch (error) {
      if (!isCanceledRequest(error, controller.signal) && generation === trackerViewsGeneration) {
        trackerViewsError.value = getApiErrorMessage(error, 'Unable to load viewer history.')
      }
    } finally {
      if (trackerViewsController === controller) trackerViewsController = null
      if (generation === trackerViewsGeneration) trackerViewsLoading.value = false
    }
  }

  async function loadMoreTrackerViews() {
    if (trackerViewsLoading.value || trackerViewsNextBefore.value === null) return
    await loadTrackerViews({ append: true, before: trackerViewsNextBefore.value })
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
    trackerStatsController?.abort()
    const controller = new AbortController()
    trackerStatsController = controller
    const unlinkAbort = linkAbortSignal(options.signal, controller)
    const projectId = ctx.currentProject.value.id
    const trackerId = ctx.currentTracker.value?.id
    const shareId = ctx.shareMode.value ? (options.shareId || ctx.pendingShareId.value) : null
    const ownsCommit = () => (
      trackerRequestStillOwned(generation, () => trackerStatsGeneration, options.guard)
      && projectId === ctx.currentProject.value?.id
      && trackerId === ctx.currentTracker.value?.id
      && shareId === (ctx.shareMode.value ? ctx.pendingShareId.value : null)
    )
    try {
      const endpoint = resolveAccessEndpoint({
        shareId,
        shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}/stats`,
        authenticated: `/api/projects/${projectId}/trackers/${encodeURIComponent(name)}/stats`,
      })
      const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
      const { data } = await api.get(`${endpoint}${query}`, { signal: controller.signal })
      if (ownsCommit()) trackerStats.value = data
    } catch (error) {
      if (!isCanceledRequest(error, controller.signal) && ownsCommit()) throw error
    } finally {
      unlinkAbort()
      if (trackerStatsController === controller) trackerStatsController = null
    }
  }

  async function loadTrackerActivity(name, {
    append = false,
    before = null,
    guard = null,
    shareId: requestedShareId = null,
    signal = null,
  } = {}) {
    if (!ctx.currentProject.value) return
    if (!ctx.canViewTrackerDetails.value) {
      resetTrackerDetails()
      return
    }
    const generation = ++trackerActivityGeneration
    trackerActivityController?.abort()
    const controller = new AbortController()
    trackerActivityController = controller
    const unlinkAbort = linkAbortSignal(signal, controller)
    const projectId = ctx.currentProject.value.id
    const trackerId = ctx.currentTracker.value?.id
    const shareId = ctx.shareMode.value ? (requestedShareId || ctx.pendingShareId.value) : null
    const ownsCommit = () => (
      trackerRequestStillOwned(generation, () => trackerActivityGeneration, guard)
      && projectId === ctx.currentProject.value?.id
      && trackerId === ctx.currentTracker.value?.id
      && shareId === (ctx.shareMode.value ? ctx.pendingShareId.value : null)
    )
    if (ownsCommit()) {
      trackerActivityLoading.value = true
      trackerActivityError.value = ''
    }
    try {
      const endpoint = resolveAccessEndpoint({
        shareId,
        shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}/activity`,
        authenticated: `/api/projects/${projectId}/trackers/${encodeURIComponent(name)}/activity`,
      })
      const cursor = before && typeof before === 'object'
        ? {
            before: before.createdAt,
            ...(before.id !== null && before.id !== undefined ? { before_id: before.id } : {}),
          }
        : (before !== null ? { before } : {})
      const query = buildShareCredentialQuery(
        { limit: 40, ...cursor },
        shareId ? ctx.getShareCredential({ shareId }) : {},
      )
      const { data } = await api.get(`${endpoint}${query}`, { signal: controller.signal })
      if (!ownsCommit()) return
      const items = data?.items || []
      trackerActivity.value = append ? [...trackerActivity.value, ...items] : items
      trackerActivityNextBefore.value = data?.next_before == null
        ? null
        : { createdAt: data.next_before, id: data?.next_before_id ?? null }
      return true
    } catch (error) {
      if (!isCanceledRequest(error, controller.signal) && ownsCommit()) {
        trackerActivityError.value = getApiErrorMessage(error, 'Unable to load activity history.')
      }
      return false
    } finally {
      unlinkAbort()
      if (trackerActivityController === controller) trackerActivityController = null
      if (ownsCommit()) trackerActivityLoading.value = false
    }
  }

  async function loadMoreTrackerActivity() {
    if (!trackerRef() || trackerActivityLoading.value || trackerActivityNextBefore.value === null) return
    await loadTrackerActivity(trackerRef(), { append: true, before: trackerActivityNextBefore.value })
  }

  function applyTrackerShotPatches(patches) {
    const tracker = ctx.currentTracker.value
    if (!tracker || !Array.isArray(patches) || !patches.length) return
    const shotsById = new Map((tracker.shots || []).map(shot => [String(shot.id || ''), shot]))
    for (const patch of patches) {
      const shot = shotsById.get(String(patch?.id || ''))
      if (!shot) continue
      Object.assign(shot, patch)
      shot._originalId = patch.shot_id || patch.shot_code || shot._originalId
    }
    const activeCount = (tracker.shots || []).filter(shot => !shot.archived_at).length
    tracker.shot_count = activeCount
    tracker.active_shot_count = activeCount
    tracker.archived_shot_count = (tracker.shots || []).length - activeCount
  }

  async function prepareTrackerHistoryRestore(item) {
    const target = captureTrackerContext()
    if (
      !target ||
      !item?.restoreable ||
      item?.current_point ||
      !canRestoreTrackerHistory.value ||
      activityRestorePreviewBusyId.value !== null ||
      activityRestoreBusyId.value !== null
    ) return
    const eventId = Number(item.id)
    if (!Number.isInteger(eventId)) return

    activityRestorePreviewBusyId.value = eventId
    try {
      const { data } = await api.get(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerId)}/activity/${eventId}/restore-preview`,
      )
      if (!trackerContextIsCurrent(target)) return
      activityRestorePreview.value = { ...data, item, target, error: '' }
    } catch (error) {
      if (trackerContextIsCurrent(target)) {
        const message = getApiErrorMessage(error, 'This history point is no longer available to restore.')
        notify(message, { tone: 'error' })
        if ([404, 409].includes(error?.response?.status)) {
          trackerActivity.value = trackerActivity.value.map(activity => (
            activity.id === eventId
              ? {
                  ...activity,
                  restoreable: false,
                  recovery_unavailable: true,
                }
              : activity
          ))
        }
      }
    } finally {
      if (activityRestorePreviewBusyId.value === eventId) activityRestorePreviewBusyId.value = null
    }
  }

  function closeTrackerHistoryRestore() {
    if (activityRestoreBusyId.value !== null) return
    activityRestorePreview.value = null
  }

  async function restoreTrackerActivity() {
    const preview = activityRestorePreview.value
    const target = preview?.target
    const eventId = Number(preview?.event_id)
    if (!target || !Number.isInteger(eventId) || activityRestoreBusyId.value !== null) return

    activityRestoreBusyId.value = eventId
    activityRestorePreview.value = { ...preview, error: '' }
    try {
      let restoreRefreshFailed = false
      const { data } = await api.post(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerId)}/activity/${eventId}/restore`,
        { expected_state_hash: preview.expected_state_hash },
      )
      invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
      if (trackerContextIsCurrent(target)) {
        activityRestorePreview.value = null
        try {
          await refreshCurrentTrackerPreserveState(target, { syncRoute: true })
        } catch (_error) {
          restoreRefreshFailed = true
        }
      }
      notify(data?.message || 'Tracker restored', { tone: 'success' })
      await refreshTrackerSummaries(target, { details: false, counts: true })
      if (restoreRefreshFailed) {
        notify('Tracker restored, but this view could not refresh. Reload the page to see it.', {
          tone: 'info',
          duration: 6500,
        })
      }
    } catch (error) {
      const message = getApiErrorMessage(error, 'Could not restore this history point')
      if (trackerContextIsCurrent(target) && activityRestorePreview.value?.event_id === eventId) {
        activityRestorePreview.value = { ...activityRestorePreview.value, error: message }
      }
      notify(message, { tone: 'error' })
    } finally {
      if (activityRestoreBusyId.value === eventId) activityRestoreBusyId.value = null
    }
  }

  async function loadTrackerCommentCounts(tracker, options = {}) {
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
    trackerCommentsController?.abort()
    const controller = new AbortController()
    trackerCommentsController = controller
    const unlinkAbort = linkAbortSignal(options.signal, controller)
    try {
      const responses = await Promise.all(chunkCommentTargets(targets).map(async (chunk) => {
        const body = { targets: chunk }
        const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
        if (!shareId && ctx.currentProject.value?.id) body.project_id = ctx.currentProject.value.id
        const query = buildShareCredentialQuery(
          shareId ? { share_id: shareId } : {},
          shareId ? ctx.getShareCredential({ shareId }) : {},
        )
        const { data } = await api.post(`/api/comments/counts/batch${query}`, body, {
          signal: controller.signal,
        })
        return data?.items || []
      }))
      for (const items of responses) {
        for (const item of items) {
          if (item?.key) ctx.commentCounts.value[item.key] = item.count || 0
        }
      }
    } catch (error) {
      if (!isCanceledRequest(error, controller.signal)) {
        console.error('Failed to load tracker comment counts')
      }
    } finally {
      unlinkAbort()
      if (trackerCommentsController === controller) trackerCommentsController = null
    }
  }

  function setTrackerCommentCount(target, count) {
    if (!target?.key || !Number.isFinite(count)) return
    ctx.commentCounts.value[target.key] = count
  }

  function normalizeOpenTrackerOptions(options = false) {
    if (options && typeof options === 'object') {
      return {
        skipRouteUpdate: options.skipRouteUpdate === true,
        signal: options.signal || null,
        fresh: options.fresh === true,
      }
    }
    return { skipRouteUpdate: options === true, signal: null, fresh: false }
  }

  function commitOpenedTracker(data, name, skipRouteUpdate) {
    if (ctx.currentTracker.value?.id && ctx.currentTracker.value.id !== data?.id) {
      resetTrackerDetails()
    }
    ctx.currentTracker.value = hydrateTrackerPayload(data)
    ctx.currentPage.value = null
    if (!ctx.shareMode.value) void ctx.loadProjectTeamOptions()
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
  }

  function loadOpenedTrackerDetails(data, signal, { includeCommentCounts = true } = {}) {
    const canonicalRef = data.id || data.slug || data.name
    const tasks = includeCommentCounts ? [loadTrackerCommentCounts(data, { signal })] : []
    if (ctx.canViewTrackerDetails.value) {
      tasks.push(
        loadTrackerStats(canonicalRef, { signal }),
        loadTrackerActivity(canonicalRef, { signal }),
      )
    } else {
      resetTrackerDetails()
    }
    return Promise.allSettled(tasks)
  }

  async function openTracker(name, options = false) {
    if (!ctx.currentProject.value) return
    const { skipRouteUpdate, signal, fresh } = normalizeOpenTrackerOptions(options)
    const projectId = ctx.currentProject.value.id
    const userScope = currentUserScope()
    const generation = ++trackerOpenGeneration
    trackerOpenController?.abort()
    const controller = new AbortController()
    trackerOpenController = controller
    const unlinkAbort = linkAbortSignal(signal, controller)
    const cleanup = () => {
      unlinkAbort()
      if (trackerOpenController === controller) trackerOpenController = null
    }
    const ownsCommit = () => (
      generation === trackerOpenGeneration
      && projectId === ctx.currentProject.value?.id
      && !controller.signal.aborted
    )
    const cacheKey = trackerPayloadKey(name, projectId, userScope)
    const cached = ctx.shareMode.value || fresh ? undefined : readWorkspacePayload(cacheKey)

    let backgroundDetails = null
    if (cached && ownsCommit()) {
      commitOpenedTracker(cached, name, skipRouteUpdate)
      backgroundDetails = loadOpenedTrackerDetails(cached, controller.signal, {
        includeCommentCounts: false,
      })
    }

    const shareId = ctx.shareMode.value ? ctx.pendingShareId.value : null
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(name)}`,
      authenticated: `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}`,
    })
    const query = shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId })) : ''
    const fetchTracker = async () => {
      const { data } = await api.get(`${endpoint}${query}`, { signal: controller.signal })
      if (!shareId) cacheTrackerPayload(data, name, projectId, userScope)
      return data
    }

    if (cached) {
      void (async () => {
        try {
          const data = await fetchTracker()
          if (!ownsCommit()) return
          commitOpenedTracker(data, name, true)
          await Promise.allSettled([
            backgroundDetails,
            loadTrackerCommentCounts(data, { signal: controller.signal }),
          ])
        } catch (error) {
          if (!isCanceledRequest(error, controller.signal)) {
            console.error('Failed to refresh tracker')
          }
          await backgroundDetails
        } finally {
          cleanup()
        }
      })()
      return cached
    }

    try {
      const data = await fetchTracker()
      if (!ownsCommit()) {
        cleanup()
        return
      }
      commitOpenedTracker(data, name, skipRouteUpdate)
      backgroundDetails = loadOpenedTrackerDetails(data, controller.signal)
      void backgroundDetails.finally(cleanup)
      return data
    } catch (error) {
      if (!isCanceledRequest(error, controller.signal)) {
        console.error('Failed to load tracker')
        notify('Failed to load tracker')
      }
      cleanup()
    }
  }

  async function openProjectTracker(projectId, name) {
    if (ctx.currentProject.value?.id !== projectId) {
      await ctx.openProject(projectId, true)
    }
    await openTracker(name, false)
  }

  function closeTracker() {
    trackerOpenGeneration += 1
    trackerOpenController?.abort()
    trackerStatsController?.abort()
    trackerActivityController?.abort()
    trackerViewsController?.abort()
    trackerCommentsController?.abort()
    stopTrackerViewSession()
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
      invalidateCurrentTrackerPayloads()
      ctx.newTrackerName.value = ''
      ctx.showCreateTracker.value = false
      await ctx.refreshProjectContents()
    } catch (error) {
      ctx.handleError('Failed to create tracker', error)
    }
  }

  async function deleteTracker(name) {
    if (!ctx.currentProject.value || !confirm(`Permanently delete tracker "${name}" and all its shots? Comments, attachments, Activity, and tracker share links will be removed. This cannot be undone.`)) return
    try {
      await api.delete(`/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(name)}`)
      invalidateCurrentTrackerPayloads()
      await ctx.refreshProjectContents()
    } catch (_error) {
      notify('Failed to delete tracker')
    }
  }

  async function refreshCurrentTrackerPreserveState(
    target = captureTrackerContext(),
    { syncRoute = false } = {},
  ) {
    if (!target) return null
    const requestRef = target.shareId ? target.trackerRef : target.trackerId
    const endpoint = resolveAccessEndpoint({
      shareId: target.shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(target.trackerRef)}`,
      authenticated: `/api/projects/${target.projectId}/trackers/${encodeURIComponent(requestRef)}`,
    })
    const query = target.shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId: target.shareId })) : ''
    const { data } = await api.get(`${endpoint}${query}`)
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (!target.shareId) cacheTrackerPayload(data, requestRef, target.projectId, target.userScope)
    if (!trackerContextIsCurrent(target)) return data
    ctx.currentTracker.value = hydrateTrackerPayload(data)
    if (syncRoute && !target.shareId) {
      await ctx.router.replace({
        name: 'project-tracker',
        params: {
          projectId: target.projectId,
          tracker: data.slug || data.id || data.name || target.trackerRef,
        },
      })
    }
    await Promise.allSettled([
      loadTrackerCommentCounts(data),
      loadTrackerStats(requestRef),
      loadTrackerActivity(requestRef),
    ])
    return data
  }

  async function saveShot(shot, { fields = ['status'], expectedValues = {} } = {}) {
    const target = captureTrackerContext()
    if (!target) return null
    const originalShotCode = shot._originalId || shot.shot_id
    const shotRef = shot.id || originalShotCode
    if (!shotRef) return
    const requested = new Set(fields)
    const payload = {}
    if (requested.has('status')) payload.status = shot.status
    if (!target.shareId && requested.has('description') && ctx.canEditDescription.value) payload.description = shot.description
    if (!target.shareId && requested.has('shot_code') && ctx.canEditShotName.value) payload.new_shot_id = shot.shot_id
    if (!target.shareId && requested.has('category')) payload.tag = shot.category ?? shot.tag ?? null
    if (!target.shareId && requested.has('assignee_user_ids') && list().canAssignShots?.value) {
      payload.assignee_user_ids = getShotAssigneeIds(shot)
    }
    if (!Object.keys(payload).length) return null
    if (!target.shareId && expectedValues && Object.keys(expectedValues).length) {
      payload.expected_values = expectedValues
    }
    const endpoint = resolveAccessEndpoint({
      shareId: target.shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(target.trackerRef)}/shots/${encodeURIComponent(shotRef)}`,
      authenticated: `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/${encodeURIComponent(shotRef)}`,
    })
    const query = target.shareId ? buildShareCredentialQuery({}, ctx.getShareCredential({ shareId: target.shareId })) : ''
    const { data } = await api.put(`${endpoint}${query}`, payload)
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target) && data && typeof data === 'object' && (data.id || data.shot_id)) {
      Object.assign(shot, data)
    }
    if (!target.shareId) shot._originalId = data?.shot_id || data?.shot_code || shot.shot_id
    await refreshTrackerSummaries(target, { details: true })
    return data
  }

  async function saveShotName(shot) {
    const previous = shot?._originalId || shot?.shot_code || shot?.shot_id
    const next = String(shot?.shot_id || '').trim()
    if (!shot || !next || next === previous) {
      if (shot && !next) shot.shot_id = previous
      return
    }
    try {
      await saveShot(shot, {
        fields: ['shot_code'],
        expectedValues: { shot_code: previous },
      })
    } catch (error) {
      if (error?.response?.status === 409) {
        notify(getApiErrorMessage(error, 'This shot changed elsewhere.'), { tone: 'error' })
        await Promise.allSettled([refreshCurrentTrackerPreserveState()])
        return
      }
      shot.shot_id = previous
      notify(`Failed to rename shot: ${getApiErrorMessage(error)}`, { tone: 'error' })
    }
  }

  async function selectStatus(shot, status) {
    list().showStatusPicker.value = null
    if (!shot || !status || status === shot.status) return
    const previous = shot.status
    shot.status = status
    shot._statusSaving = true
    try {
      await saveShot(shot, {
        fields: ['status'],
        expectedValues: { status: previous },
      })
    } catch (error) {
      if (error?.response?.status === 409) {
        notify(getApiErrorMessage(error, 'This shot changed elsewhere.'), { tone: 'error' })
        await Promise.allSettled([refreshCurrentTrackerPreserveState()])
        return
      }
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

  function getShotActionLabel(shotOrId) {
    if (!shotOrId || typeof shotOrId !== 'object') return 'Shot'
    return shotOrId.shot_id || shotOrId.shot_code || 'Shot'
  }

  async function deleteShot(shotOrId) {
    const target = captureTrackerContext()
    if (!target || !ctx.canDeleteShots.value) return
    if (shotOrId && typeof shotOrId === 'object' && !shotOrId.archived_at) return
    const shotRef = getShotRequestRef(shotOrId)
    const label = getShotActionLabel(shotOrId)
    if (!shotRef || isShotActionBusy(shotRef) || !confirm(`Permanently delete ${label}? Versions, comments, and comment attachments will be removed. Source media files stay in the project.`)) return
    setShotActionBusy(shotRef, true)
    try {
      await api.delete(`/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/${encodeURIComponent(shotRef)}`)
    } catch (error) {
      ctx.handleError('Failed to delete shot', error)
      return
    } finally {
      setShotActionBusy(shotRef, false)
    }
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) {
      ctx.currentTracker.value.shots = (ctx.currentTracker.value.shots || []).filter(shot => getShotRequestRef(shot) !== shotRef)
      removeShotSelection(shotOrId)
    }
    notify(`${label} permanently deleted`, { tone: 'success' })
    await refreshTrackerSummaries(target, { details: true, counts: true })
  }

  function removeShotSelection(shotOrId) {
    const selectionKey = list().getShotSelectionKey(shotOrId)
    if (!selectionKey) return
    const next = new Set(list().selectedShots.value)
    next.delete(selectionKey)
    list().selectedShots.value = next
  }

  async function archiveShot(shotOrId) {
    const target = captureTrackerContext()
    if (!target || !list().canArchiveShots.value) return
    const shotRef = getShotRequestRef(shotOrId)
    if (!shotRef || isShotActionBusy(shotRef)) return
    setShotActionBusy(shotRef, true)
    let response
    try {
      response = await api.post(`/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/${encodeURIComponent(shotRef)}/archive`, {})
    } catch (error) {
      ctx.handleError('Failed to archive shot', error)
      return
    } finally {
      setShotActionBusy(shotRef, false)
    }
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) {
      applyTrackerShotPatches(response?.data?.shot ? [response.data.shot] : [])
      removeShotSelection(shotOrId)
    }
    notify(`${getShotActionLabel(shotOrId)} moved to Archived`, { tone: 'success' })
    await refreshTrackerSummaries(target, { details: true, counts: true })
  }

  async function restoreShot(shotOrId) {
    const target = captureTrackerContext()
    if (!target || !list().canArchiveShots.value) return
    const shotRef = getShotRequestRef(shotOrId)
    if (!shotRef || isShotActionBusy(shotRef)) return
    setShotActionBusy(shotRef, true)
    let response
    try {
      response = await api.post(`/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/${encodeURIComponent(shotRef)}/restore`, {})
    } catch (error) {
      ctx.handleError('Failed to restore shot', error)
      return
    } finally {
      setShotActionBusy(shotRef, false)
    }
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) {
      applyTrackerShotPatches(response?.data?.shot ? [response.data.shot] : [])
      removeShotSelection(shotOrId)
    }
    notify(`${getShotActionLabel(shotOrId)} restored`, { tone: 'success' })
    await refreshTrackerSummaries(target, { details: true, counts: true })
  }

  async function bulkUpdateShotSet(shots, update, failureMessage, onSuccess) {
    const target = captureTrackerContext()
    if (!target || !ctx.canEditProject.value || bulkActionBusy.value) return
    const shotIds = (shots || []).map(getShotRequestRef).filter(Boolean)
    if (!shotIds.length) return
    bulkActionBusy.value = true
    let succeeded = false
    try {
      await api.post(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/bulk-update`,
        { shot_ids: shotIds, ...update },
      )
      succeeded = true
    } catch (error) {
      ctx.handleError(failureMessage, error)
    } finally {
      bulkActionBusy.value = false
    }
    if (!succeeded) return
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) onSuccess?.()
    await Promise.allSettled([refreshCurrentTrackerPreserveState(target)])
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

  async function bulkArchiveShots() {
    const target = captureTrackerContext()
    if (!target || !list().canArchiveShots.value || bulkActionBusy.value) return
    const shots = list().selectedTrackerShots.value
    if (!shots.length) return
    bulkActionBusy.value = true
    let data
    try {
      const response = await api.post(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/bulk-archive`,
        { shot_ids: shots.map(getShotRequestRef).filter(Boolean) },
      )
      data = response.data
    } catch (error) {
      ctx.handleError('Failed to archive selected shots', error)
      return
    } finally {
      bulkActionBusy.value = false
    }
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) {
      applyTrackerShotPatches(data?.shots)
      list().clearActiveSelectedShots()
    }
    const count = Number(data?.updated || 0)
    notify(`${count} shot${count === 1 ? '' : 's'} moved to Archived`, { tone: 'success' })
    await refreshTrackerSummaries(target, { details: true, counts: true })
  }

  async function bulkRestoreArchivedShots() {
    const target = captureTrackerContext()
    if (!target || !list().canArchiveShots.value || bulkActionBusy.value) return
    const shots = list().selectedArchivedShots.value
    if (!shots.length) return
    bulkActionBusy.value = true
    let data
    try {
      const response = await api.post(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/bulk-restore`,
        { shot_ids: shots.map(getShotRequestRef).filter(Boolean) },
      )
      data = response.data
    } catch (error) {
      ctx.handleError('Failed to restore selected archived shots', error)
      return
    } finally {
      bulkActionBusy.value = false
    }
    invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
    if (trackerContextIsCurrent(target)) {
      applyTrackerShotPatches(data?.shots)
      list().clearArchivedSelectedShots()
    }
    const count = Number(data?.updated || 0)
    notify(`${count} shot${count === 1 ? '' : 's'} restored`, { tone: 'success' })
    await refreshTrackerSummaries(target, { details: true, counts: true })
  }

  async function bulkDeleteShots() {
    const target = captureTrackerContext()
    if (!target || !ctx.canDeleteShots.value || bulkActionBusy.value) return
    const shotIds = list().selectedArchivedShots.value.map(getShotRequestRef).filter(Boolean)
    if (!shotIds.length) return
    const count = shotIds.length
    if (!confirm(`Permanently delete ${count} archived shot${count === 1 ? '' : 's'}? Versions, comments, and comment attachments will be removed. Source media files stay in the project.`)) return
    bulkActionBusy.value = true
    try {
      await api.post(
        `/api/projects/${target.projectId}/trackers/${encodeURIComponent(target.trackerRef)}/shots/bulk-delete`,
        { shot_ids: shotIds },
      )
      invalidateCurrentTrackerPayloads(target.projectId, target.userScope)
      if (trackerContextIsCurrent(target)) {
        const deleted = new Set(shotIds.map(String))
        ctx.currentTracker.value.shots = (ctx.currentTracker.value.shots || []).filter(shot => !deleted.has(String(getShotRequestRef(shot))))
        list().clearArchivedSelectedShots()
      }
      notify(`${count} archived shot${count === 1 ? '' : 's'} permanently deleted`, { tone: 'success' })
      await refreshTrackerSummaries(target, { details: true, counts: true })
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
    trackerActivityError,
    trackerActivityHasMore,
    activityRestoreBusyId,
    activityRestorePreview,
    activityRestorePreviewBusyId,
    canRestoreTrackerHistory,
    trackerViews,
    trackerViewersActive,
    trackerViewsLoading,
    trackerViewsError,
    trackerViewsHasMore,
    startTrackerViewSession,
    stopTrackerViewSession,
    heartbeatTrackerViewSession,
    recordTrackerMediaView,
    loadTrackerViews,
    loadMoreTrackerViews,
    trackerTotalDuration,
    trackerTotalFrames,
    bulkActionBusy,
    shotActionBusyIds,
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
    prepareTrackerHistoryRestore,
    closeTrackerHistoryRestore,
    restoreTrackerActivity,
    loadTrackerCommentCounts,
    setTrackerCommentCount,
    invalidateCurrentTrackerPayloads,
    openTracker,
    openProjectTracker,
    closeTracker,
    createTracker,
    deleteTracker,
    refreshCurrentTrackerPreserveState,
    saveShot,
    saveShotName,
    selectStatus,
    deleteShot,
    archiveShot,
    restoreShot,
    isShotActionBusy,
    bulkUpdateShotStatus,
    bulkUpdateShotCategory,
    bulkUpdateShotAssignee,
    bulkUpdateArchivedShotStatus,
    bulkUpdateArchivedShotCategory,
    bulkUpdateArchivedShotAssignee,
    bulkArchiveShots,
    bulkRestoreArchivedShots,
    bulkDeleteShots,
    downloadTrackerLatestVersions,
    downloadSelectedTrackerLatestVersions: () => downloadTrackerLatestVersions({ selectedOnly: true }),
    getAllLatestShotFiles,
    getLatestShotFile,
    downloadShotFile,
  }
}
