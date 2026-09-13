import { onMounted, onScopeDispose, watch } from 'vue'
import { invalidateWorkspacePayload, workspaceCacheKey } from '../lib/workspacePayloadCache'

// The folder view and navigation share streams. Only visible, subscribed folders
// reach the server; closing the last view releases its filesystem watches.
const channels = new Map()
let reconcileTimer = null
let listening = false
let lastFocusRefresh = 0

function closeStream(stream) {
  stream.source?.close()
  stream.source = null
  window.clearTimeout(stream.retryTimer)
}

function dispatch(channel, paths) {
  if (channel.scope.userId) {
    for (const path of paths) {
      const { userId, projectId } = channel.scope
      invalidateWorkspacePayload(projectId
        ? workspaceCacheKey('contents', userId, projectId, path)
        : workspaceCacheKey('files', userId, path))
    }
  }
  for (const subscription of channel.subscriptions) subscription.notify(paths)
}

function connectStream(channel, paths) {
  const key = JSON.stringify(paths)
  const params = new URLSearchParams()
  if (channel.scope.projectId) params.set('project_id', channel.scope.projectId)
  if (channel.scope.shareId) params.set('share_id', channel.scope.shareId)
  for (const path of paths) params.append('path', path)
  const stream = { source: null, retryTimer: null, retryDelay: 2000 }

  function connect() {
    if (document.hidden || channel.streams.get(key) !== stream) return
    const source = new EventSource(`/api/folder-events?${params}`)
    stream.source = source
    const receive = event => {
      if (stream.source !== source) return
      stream.retryDelay = 2000
      try {
        const payload = JSON.parse(event.data)
        if (Array.isArray(payload.paths)) dispatch(channel, payload.paths)
      } catch {
        // A reconnect resynchronizes the authorized listings after a bad event.
      }
    }
    source.addEventListener('ready', receive)
    source.addEventListener('change', receive)
    source.addEventListener('denied', () => {
      if (stream.source !== source) return
      closeStream(stream)
      // The authorized listing clears revoked content and shows its normal error.
      dispatch(channel, paths)
      stream.retryTimer = window.setTimeout(connect, 30000)
    })
    source.onerror = () => {
      if (stream.source !== source) return
      source.close()
      stream.source = null
      stream.retryTimer = window.setTimeout(connect, stream.retryDelay)
      stream.retryDelay = Math.min(30000, stream.retryDelay * 2)
    }
  }

  // Register before connecting so synchronous teardown always sees the stream.
  channel.streams.set(key, stream)
  connect()
}

function reconcile() {
  reconcileTimer = null
  for (const channel of channels.values()) {
    const paths = [...new Set([...channel.subscriptions].flatMap(item => [...item.paths]))].sort()
    const batches = []
    let batch = []
    let length = 0
    for (const path of paths) {
      const size = encodeURIComponent(path).length + 6
      if (batch.length && (batch.length === 64 || length + size > 6000)) {
        batches.push(batch)
        batch = []
        length = 0
      }
      batch.push(path)
      length += size
    }
    if (batch.length) batches.push(batch)
    const wanted = new Set(document.hidden ? [] : batches.map(items => JSON.stringify(items)))
    for (const [key, stream] of channel.streams) {
      if (wanted.has(key)) continue
      closeStream(stream)
      channel.streams.delete(key)
    }
    if (typeof EventSource === 'undefined') continue
    for (const paths of batches) {
      if (!document.hidden && !channel.streams.has(JSON.stringify(paths))) connectStream(channel, paths)
    }
  }
}

function scheduleReconcile() {
  window.clearTimeout(reconcileTimer)
  reconcileTimer = window.setTimeout(reconcile, 100)
}

function pause() {
  window.clearTimeout(reconcileTimer)
  reconcileTimer = null
  for (const channel of channels.values()) {
    for (const stream of channel.streams.values()) closeStream(stream)
    channel.streams.clear()
  }
}

function resume() {
  if (!document.hidden) scheduleReconcile()
}

function visibilityChanged() {
  if (document.hidden) pause()
  else resume()
}

function focus() {
  if (document.hidden || Date.now() - lastFocusRefresh < 2000) return
  lastFocusRefresh = Date.now()
  for (const channel of channels.values()) {
    dispatch(channel, [...new Set([...channel.subscriptions].flatMap(item => [...item.paths]))])
  }
  resume()
}

function setListening(enabled) {
  if (listening === enabled) return
  listening = enabled
  const method = enabled ? 'addEventListener' : 'removeEventListener'
  document[method]('visibilitychange', visibilityChanged)
  window[method]('focus', focus)
  window[method]('online', resume)
  window[method]('pageshow', resume)
  window[method]('pagehide', pause)
  if (!enabled) {
    window.clearTimeout(reconcileTimer)
    reconcileTimer = null
  }
}

function subscribe(scope, paths, refresh) {
  const key = JSON.stringify(scope)
  let channel = channels.get(key)
  if (!channel) {
    channel = { scope, subscriptions: new Set(), streams: new Map() }
    channels.set(key, channel)
  }
  const controller = new AbortController()
  const dirty = new Set()
  let timer = null
  let running = false

  function schedule() {
    if (!running && timer === null && !controller.signal.aborted) timer = window.setTimeout(flush, 100)
  }

  async function flush() {
    timer = null
    if (controller.signal.aborted || document.hidden || !dirty.size) return
    const changed = [...dirty]
    dirty.clear()
    running = true
    try {
      await refresh(changed, { signal: controller.signal })
    } catch {
      // Keep the last listing during connection loss. Reconnect/focus retries it.
    } finally {
      running = false
      if (dirty.size) schedule()
    }
  }

  const subscription = {
    paths: new Set(paths),
    notify(changed) {
      for (const path of changed) if (this.paths.has(path)) dirty.add(path)
      if (dirty.size) schedule()
    },
  }
  channel.subscriptions.add(subscription)
  setListening(true)
  scheduleReconcile()
  return () => {
    controller.abort()
    window.clearTimeout(timer)
    dirty.clear()
    channel.subscriptions.delete(subscription)
    if (!channel.subscriptions.size) {
      for (const stream of channel.streams.values()) closeStream(stream)
      channels.delete(key)
    }
    if (channels.size) scheduleReconcile()
    else setListening(false)
  }
}

export function useFolderChanges(source, refresh) {
  let unsubscribe = null
  // Some App controllers receive lazy session getters before the session exists.
  onMounted(() => {
    watch(() => {
      const value = source()
      if (!value || (!value.userId && !value.shareId) || !value.paths?.length) return ''
      return JSON.stringify({
        scope: {
          userId: value.userId || '', projectId: value.projectId || '', shareId: value.shareId || '',
          authRevision: value.authRevision || value.shareToken || '',
        },
        paths: [...new Set(value.paths)].sort(),
      })
    }, serialized => {
      unsubscribe?.()
      unsubscribe = null
      if (serialized) {
        const { scope, paths } = JSON.parse(serialized)
        unsubscribe = subscribe(scope, paths, refresh)
      }
    }, { immediate: true, flush: 'post' })
  })
  onScopeDispose(() => unsubscribe?.())
}
