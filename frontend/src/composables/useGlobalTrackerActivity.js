import { computed, getCurrentScope, onScopeDispose, ref, watch } from 'vue'
import api from '../lib/api'
import { useDocumentVisible } from './useDocumentVisible'

const ACTIVITY_POLL_MS = 15_000
const ACTIVITY_LIMIT = 25
const INITIAL_ACTIVITY_DAYS = 2
const LOAD_MORE_ACTIVITY_DAYS = 1

export function useGlobalTrackerActivity({ currentUser, shareMode }) {
  const documentVisible = useDocumentVisible()
  const items = ref([])
  const loading = ref(false)
  const loadError = ref(false)
  const open = ref(false)
  const nextCursor = ref(null)
  const unreadCount = ref(0)
  const readStatus = ref('unread')
  const loadedCalendarDays = ref(INITIAL_ACTIVITY_DAYS)
  let pollTimer = null

  const canLoadActivity = computed(() => Boolean(currentUser.value && !shareMode.value))
  const hasMore = computed(() => nextCursor.value !== null)

  async function loadActivity({ append = false, before = null, silent = false, calendarDays = loadedCalendarDays.value } = {}) {
    if (!canLoadActivity.value) return false
    if (loading.value && !silent) return false

    if (!silent) loading.value = true
    try {
      const params = {
        limit: ACTIVITY_LIMIT,
        calendar_days: Math.max(1, calendarDays),
        read_status: readStatus.value,
      }
      if (before !== null) {
        params.before_created_at = before.createdAt
        params.before_id = before.id
      }
      const { data } = await api.get('/api/notifications/feed', { params })
      const nextItems = Array.isArray(data?.items) ? data.items : []
      items.value = append ? [...items.value, ...nextItems] : nextItems
      unreadCount.value = Number(data?.unread_count || 0)
      loadError.value = false
      nextCursor.value = data?.next_before_created_at && data?.next_before_id
        ? { createdAt: data.next_before_created_at, id: data.next_before_id }
        : null
      return true
    } catch (error) {
      if (!silent) {
        console.error('Failed to load global tracker activity')
      }
      if (!append && !silent) {
        items.value = []
        nextCursor.value = null
        loadError.value = true
      }
      return false
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function refreshActivity({ silent = false } = {}) {
    await loadActivity({ silent, calendarDays: loadedCalendarDays.value })
  }

  async function loadMoreActivity() {
    if (!hasMore.value || loading.value) return
    const loaded = await loadActivity({ append: true, before: nextCursor.value, calendarDays: LOAD_MORE_ACTIVITY_DAYS })
    if (loaded) loadedCalendarDays.value += LOAD_MORE_ACTIVITY_DAYS
  }

  async function setActivityReadStatus(nextStatus) {
    const normalized = nextStatus === 'read' ? 'read' : 'unread'
    if (readStatus.value === normalized) return
    readStatus.value = normalized
    nextCursor.value = null
    loadedCalendarDays.value = INITIAL_ACTIVITY_DAYS
    await loadActivity({ silent: false })
  }

  async function markActivitySeen() {
    const latest = items.value[0]
    if (!latest?.id) return
    try {
      await api.post('/api/notifications/read', {
        event_id: latest.id,
        scope: 'default',
        filter: 'all',
      })
      unreadCount.value = 0
      loadError.value = false
      if (readStatus.value === 'unread') {
        items.value = []
        nextCursor.value = null
        loadedCalendarDays.value = INITIAL_ACTIVITY_DAYS
      } else {
        await refreshActivity({ silent: true })
      }
    } catch (error) {
      console.error('Failed to mark notifications read')
    }
  }

  function toggleActivityTray() {
    open.value = !open.value
    if (open.value) {
      refreshActivity({ silent: true })
    }
  }

  function closeActivityTray() {
    open.value = false
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling() {
    stopPolling()
    if (!canLoadActivity.value || !documentVisible.value || typeof window === 'undefined') return
    pollTimer = window.setInterval(() => {
      if (!documentVisible.value) return
      refreshActivity({ silent: true })
    }, ACTIVITY_POLL_MS)
  }

  watch([canLoadActivity, documentVisible], ([enabled, visible], previous = []) => {
    if (!enabled) {
      stopPolling()
      items.value = []
      nextCursor.value = null
      unreadCount.value = 0
      loadError.value = false
      readStatus.value = 'unread'
      loadedCalendarDays.value = INITIAL_ACTIVITY_DAYS
      closeActivityTray()
      return
    }

    if (!visible) {
      stopPolling()
      return
    }

    const [wasEnabled, wasVisible] = previous
    const isInitialLoad = !wasEnabled && items.value.length === 0
    const resumed = wasEnabled && wasVisible === false
    if (isInitialLoad || resumed) {
      refreshActivity({ silent: !isInitialLoad })
    }
    startPolling()
  }, { immediate: true })

  if (getCurrentScope()) onScopeDispose(stopPolling)

  return {
    globalActivityItems: items,
    globalActivityLoading: loading,
    globalActivityError: loadError,
    globalActivityOpen: open,
    globalActivityHasMore: hasMore,
    globalActivityUnreadCount: unreadCount,
    globalActivityReadStatus: readStatus,
    setGlobalActivityReadStatus: setActivityReadStatus,
    toggleGlobalActivityTray: toggleActivityTray,
    closeGlobalActivityTray: closeActivityTray,
    refreshGlobalActivity: refreshActivity,
    loadMoreGlobalActivity: loadMoreActivity,
    markGlobalActivitySeen: markActivitySeen,
    stopGlobalActivityPolling: stopPolling,
  }
}
