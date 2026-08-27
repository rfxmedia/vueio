const MAX_CACHE_ENTRIES = 48

const payloads = new Map()
const inFlightRequests = new Map()

function clonePayload(value) {
  if (value === undefined) return undefined
  if (typeof structuredClone === 'function') return structuredClone(value)
  return JSON.parse(JSON.stringify(value))
}

function touch(key, value) {
  payloads.delete(key)
  payloads.set(key, value)
  while (payloads.size > MAX_CACHE_ENTRIES) {
    payloads.delete(payloads.keys().next().value)
  }
}

function scopedPart(value) {
  return encodeURIComponent(String(value ?? ''))
}

export function workspaceCacheKey(kind, scope, ...parts) {
  return [kind, scope || 'session', ...parts].map(scopedPart).join(':')
}

export function readWorkspacePayload(key) {
  if (!payloads.has(key)) return undefined
  const value = payloads.get(key)
  touch(key, value)
  return clonePayload(value)
}

export function writeWorkspacePayload(key, value) {
  touch(key, clonePayload(value))
  return value
}

export function invalidateWorkspacePayload(prefix) {
  for (const key of payloads.keys()) {
    if (key.startsWith(prefix)) payloads.delete(key)
  }
}

export function invalidateTrackerPayloads(scope, projectId) {
  invalidateWorkspacePayload(workspaceCacheKey('tracker', scope, projectId))
}

export function requestWorkspacePayload(key, loader) {
  const existing = inFlightRequests.get(key)
  if (existing) return existing

  const request = Promise.resolve()
    .then(loader)
    .finally(() => {
      if (inFlightRequests.get(key) === request) inFlightRequests.delete(key)
    })
  inFlightRequests.set(key, request)
  return request
}

export function resetWorkspacePayloadCache() {
  payloads.clear()
  inFlightRequests.clear()
}
