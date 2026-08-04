import { inject, nextTick, provide } from 'vue'
import { useGlobalTrackerActivity } from '../composables/useGlobalTrackerActivity'

export const activityStoreKey = Symbol('vueio.activityStore')

export function createActivityStore({
  session,
  share,
  selection,
  workspace,
  tracker,
  viewer,
  documentTarget = globalThis.document,
  windowTarget = globalThis.window,
  requestFrame = globalThis.requestAnimationFrame,
}) {
  const feed = useGlobalTrackerActivity({ currentUser: session.currentUser, shareMode: share.shareMode })

  function findShot(target, activity = null) {
    const targetShotId = String(target?.shot_id || '').trim()
    const targetShotCode = String(target?.shot_code || activity?.payload?.shot_code || '').trim()
    return (selection.currentTracker.value?.shots || []).find((shot) => {
      const shotDbId = String(shot?.id || '').trim()
      const shotCode = String(shot?.shot_id || shot?.shot_code || '').trim()
      return (targetShotId && (shotDbId === targetShotId || shotCode === targetShotId)) ||
        (targetShotCode && shotCode === targetShotCode)
    }) || null
  }

  function findVersion(shot, target) {
    if (!shot || !target?.shot_version_id) return null
    const targetVersionId = String(target.shot_version_id)
    return tracker.getShotVersions(shot).find(version => String(version?.id || '') === targetVersionId) || null
  }

  function escapeSelectorValue(value) {
    const text = String(value || '')
    return windowTarget?.CSS?.escape ? windowTarget.CSS.escape(text) : text.replace(/["\\]/g, '\\$&')
  }

  async function focusShot(target, activity) {
    await nextTick()
    const shot = findShot(target, activity)
    if (!shot) return

    const version = findVersion(shot, target)
    if (version?.path || version?.file_path) {
      tracker.openTrackerViewerVersion(shot, version, {
        mode: target.mode || 'latest',
        preserveSidebar: target.type !== 'comment',
      })
      return
    }

    if (target.type === 'comment') {
      tracker.openTrackerViewerShot(shot, target.mode || 'latest')
      return
    }

    requestFrame?.(() => {
      const selector = `[data-tracker-shot-id="${escapeSelectorValue(shot.id)}"], [data-tracker-shot-code="${escapeSelectorValue(shot.shot_id || shot.shot_code)}"]`
      const row = documentTarget?.querySelector?.(selector)
      row?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      row?.classList.add('is-activity-focus')
      windowTarget?.setTimeout?.(() => row?.classList.remove('is-activity-focus'), 1800)
    })
  }

  async function openTarget(activity) {
    const target = activity?.target || {}
    const projectId = target.project_id || activity?.project_id
    if (target.type === 'project') {
      if (!projectId) return
      feed.closeGlobalActivityTray()
      viewer.media.dismissCurrentMedia()
      await workspace.openProject(projectId)
      return
    }

    const trackerRef = target.tracker_id || activity?.tracker_id || target.tracker_ref || activity?.tracker_name
    if (!projectId || !trackerRef) return
    feed.closeGlobalActivityTray()
    viewer.media.dismissCurrentMedia()
    await tracker.openProjectTracker(projectId, trackerRef)
    if (target.type !== 'tracker') await focusShot(target, activity)
    if (target.type === 'comment') await viewer.actions.focusMediaComment(target.comment_id)
  }

  return { ...feed, openGlobalActivityTarget: openTarget }
}

export function provideActivityStore(store) {
  provide(activityStoreKey, store)
  return store
}

export function useActivityStore() {
  const store = inject(activityStoreKey, null)
  if (!store) throw new Error('Activity store has not been provided')
  return store
}
