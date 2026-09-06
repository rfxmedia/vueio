import { computed, inject, onScopeDispose, provide, ref, watch } from 'vue'
import api from '../lib/api'
import { setUpdateRecoveryActive } from '../lib/connectionRecovery'

export const updateStatusStoreKey = Symbol('vueio.updateStatusStore')

export function createUpdateStatusStore({ session, apiClient = api }) {
  const status = ref(null)
  const loading = ref(false)
  const progress = ref(null)
  const starting = ref(false)
  const pendingChannel = ref(null)
  const offline = ref(false)
  const offlineFor = ref(0)
  const updateError = ref('')
  const visible = ref(false)
  const isAdmin = computed(() => session.currentUser.value?.role === 'admin')
  const updateAvailable = computed(() => Boolean(status.value?.update_available))
  const latestVersion = computed(() => status.value?.latest_version || '')
  const awaitingConfirmation = ref(false)
  const updating = computed(() => starting.value || awaitingConfirmation.value || progress.value?.state === 'running')
  const awaitingReload = ref(false)
  const switchingChannel = computed(() => (updating.value || awaitingReload.value)
    && (starting.value || awaitingConfirmation.value
      ? Boolean(pendingChannel.value) : progress.value?.operation === 'channel'))
  const needsHostAttention = computed(() => offlineFor.value >= 120000 && (updating.value || awaitingReload.value))
  let controller = new AbortController()
  let pollTimer = null
  let polling = false
  let observedOperation = null
  let requestedOperation = null
  let progressRevision = 0
  let offlineSince = 0

  function requestOptions() {
    return { signal: controller.signal, timeout: 10000, skipConnectionRecovery: true }
  }

  async function check({ refresh = false } = {}) {
    if (!isAdmin.value) return null
    if (loading.value || (status.value && !refresh)) return status.value
    const options = requestOptions()
    loading.value = true
    try {
      const response = await apiClient.get('/api/admin/update-status', {
        ...options,
        params: refresh ? { refresh: true } : undefined,
      })
      if (!options.signal.aborted) status.value = response.data
    } catch (error) {
      if (options.signal.aborted) return null
      const unsupported = error?.response?.status === 404
      status.value = {
        ...status.value,
        current_version: status.value?.current_version || (unsupported ? 'development' : 'Unknown'),
        update_available: false,
        configured: unsupported ? false : (status.value?.configured ?? true),
        status: unsupported ? 'unavailable' : 'error',
      }
    } finally {
      if (!options.signal.aborted) loading.value = false
    }
    return status.value
  }

  function schedulePoll() {
    window.clearTimeout(pollTimer)
    pollTimer = null
    if (isAdmin.value && (visible.value || updating.value || awaitingReload.value)) {
      pollTimer = window.setTimeout(readProgress, 2000)
    }
  }

  function markOffline() {
    offline.value = true
    offlineSince ||= Date.now()
    offlineFor.value = Date.now() - offlineSince
  }

  async function readProgress() {
    if (!isAdmin.value || polling) return
    const options = requestOptions()
    const revision = progressRevision
    polling = true
    try {
      const response = await apiClient.get('/api/admin/update-progress', options)
      if (options.signal.aborted || revision !== progressRevision) return
      if (!response.data.supported && (updating.value || awaitingReload.value)) {
        markOffline()
        return
      }
      progress.value = response.data
      // A restart can lose the POST response and complete between progress polls.
      // Match the new operation to our request, never to a historical success.
      if (requestedOperation && progress.value.operation_id
        && progress.value.operation_id !== requestedOperation.previousId
        && (progress.value.operation || 'update') === requestedOperation.kind
        && (requestedOperation.kind === 'channel'
          ? progress.value.target_channel === requestedOperation.target
          : progress.value.version === requestedOperation.target)) {
        observedOperation = progress.value.operation_id
        requestedOperation = null
        updateError.value = ''
      }
      offline.value = false
      offlineSince = 0
      offlineFor.value = 0
      // A poll made while the start request is pending cannot rule out its acceptance.
      if (!starting.value) {
        awaitingConfirmation.value = false
        pendingChannel.value = null
      }
      if (progress.value.state === 'running') {
        observedOperation = progress.value.operation_id
        updateError.value = ''
      }
      if (progress.value.state === 'succeeded' && observedOperation
        && progress.value.operation_id === observedOperation) {
        awaitingReload.value = true
        const release = await check({ refresh: true })
        if (!options.signal.aborted && release?.current_version === progress.value.version
          && (progress.value.operation !== 'channel' || release?.channel === progress.value.target_channel)) {
          // Reconnect only after the API serves the verified target version and channel.
          window.location.reload()
        }
      } else {
        awaitingReload.value = false
      }
    } catch (error) {
      if (options.signal.aborted || revision !== progressRevision) return
      if ([401, 403].includes(error?.response?.status)) {
        const authenticated = await session.checkAuth(true)
        if (!authenticated) session.showLogin.value = true
      } else if (error?.response?.status === 404 && !updating.value && !awaitingReload.value) {
        progress.value = { supported: false, state: 'idle' }
      } else {
        markOffline()
      }
    } finally {
      if (!options.signal.aborted) {
        polling = false
        schedulePoll()
      }
    }
  }

  function canStartOperation() {
    return isAdmin.value && !updating.value && !awaitingReload.value && progress.value?.supported
      && !offline.value && progress.value?.state !== 'interrupted'
  }

  async function startUpdate() {
    if (!canStartOperation() || !updateAvailable.value) return
    await startOperation('/api/admin/update', { version: latestVersion.value })
  }

  async function switchChannel(channel) {
    if (!canStartOperation() || !progress.value?.channel_switch_supported
      || !['stable', 'nightly'].includes(channel)) return
    if (channel === status.value?.channel && progress.value?.state !== 'failed') return
    await startOperation('/api/admin/update-channel', { channel })
  }

  async function startOperation(endpoint, payload) {
    pendingChannel.value = payload.channel || null
    requestedOperation = {
      kind: payload.channel ? 'channel' : 'update',
      target: payload.channel || payload.version,
      previousId: progress.value?.operation_id,
    }
    const options = requestOptions()
    progressRevision += 1
    starting.value = true
    awaitingConfirmation.value = true
    updateError.value = ''
    try {
      const response = await apiClient.post(endpoint, payload, options)
      if (!options.signal.aborted) {
        progress.value = response.data
        awaitingConfirmation.value = false
        observedOperation = response.data.operation_id
      }
    } catch (error) {
      if (options.signal.aborted) return
      if (error?.response?.status >= 400 && error?.response?.status < 500) requestedOperation = null
      const detail = error?.response?.data?.detail
      updateError.value = typeof detail === 'string' ? detail
        : 'Could not confirm that the host operation started. Checking its status before you try again.'
      await readProgress()
    } finally {
      if (!options.signal.aborted) {
        progressRevision += 1
        starting.value = false
        schedulePoll()
      }
    }
  }

  function setVisible(value) {
    visible.value = value
    if (value) {
      check({ refresh: true })
      readProgress()
    } else {
      if (!updating.value && !awaitingReload.value) {
        controller.abort()
        controller = new AbortController()
        loading.value = false
        polling = false
      }
      schedulePoll()
    }
  }

  function reset() {
    controller.abort()
    controller = new AbortController()
    window.clearTimeout(pollTimer)
    pollTimer = null
    polling = false
    observedOperation = null
    requestedOperation = null
    status.value = null
    progress.value = null
    loading.value = false
    starting.value = false
    pendingChannel.value = null
    awaitingConfirmation.value = false
    offline.value = false
    offlineSince = 0
    offlineFor.value = 0
    updateError.value = ''
    awaitingReload.value = false
    setUpdateRecoveryActive(false)
  }

  watch([() => session.currentUser.value?.id, isAdmin], () => {
    reset()
    if (visible.value && isAdmin.value) setVisible(true)
  }, { flush: 'sync' })
  watch([updating, awaitingReload], ([active, reconnecting]) => {
    setUpdateRecoveryActive(active || reconnecting)
  }, { flush: 'sync' })
  onScopeDispose(reset)

  return {
    status, loading, progress, starting, offline, updateError, updating, awaitingReload, needsHostAttention,
    updateAvailable, latestVersion, check, readProgress, startUpdate, switchChannel, switchingChannel, pendingChannel, setVisible,
  }
}

export function provideUpdateStatusStore(store) {
  provide(updateStatusStoreKey, store)
  return store
}

export function useUpdateStatusStore() {
  const store = inject(updateStatusStoreKey, null)
  if (!store) throw new Error('Update status store has not been provided')
  return store
}
