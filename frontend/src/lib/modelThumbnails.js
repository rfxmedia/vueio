// Model thumbnails are rendered in a publisher's browser with the review
// engine. This module stays small; the 3D engine loads only for a render.
const MAX_SOURCE_BYTES = 64 * 1024 * 1024
const wanted = new Map()
const attempted = new Set()
const listeners = new Set()
let working = false

export function modelPreviewUrl(source, resource = 'manifest', extra = {}) {
  const url = new URL(source, location.origin)
  url.pathname = url.pathname.replace(/\/(file|stream)$/, '/model')
  url.searchParams.set('resource', resource)
  for (const [key, value] of Object.entries(extra)) url.searchParams.set(key, String(value))
  return url.pathname + url.search
}

// The model source for a thumbnail route. Shared links never publish thumbnails.
export function modelThumbnailSource(thumbnailUrl) {
  const url = new URL(thumbnailUrl, location.origin)
  if (url.searchParams.has('share_id') || url.searchParams.has('share_token')) return ''
  for (const key of ['t', 'cached_only', 'variant']) url.searchParams.delete(key)
  const legacy = url.pathname.match(/^\/api\/project-thumbnail\/([^/]+)\/file$/)
  if (legacy) {
    url.pathname = '/api/stream'
    url.searchParams.set('project_id', decodeURIComponent(legacy[1]))
  } else if (url.pathname === '/api/thumbnail') {
    url.pathname = '/api/stream'
  } else if (/^\/api\/horizons\/projects\/[^/]+\/(media-assets|shot-versions)\/[^/]+\/thumbnail$/.test(url.pathname)) {
    url.pathname = url.pathname.replace(/thumbnail$/, 'file')
  } else {
    return ''
  }
  return url.pathname + url.search
}

export async function uploadModelThumbnail(source, generation, blob) {
  const body = new FormData()
  body.append('file', blob, 'thumbnail.jpg')
  const response = await fetch(modelPreviewUrl(source, 'thumbnail', { generation }), { method: 'PUT', body, credentials: 'same-origin' })
  return response.ok
}

export function announceModelThumbnail() {
  for (const listener of listeners) listener()
}

export function watchModelThumbnails(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function publish(source) {
  try {
    const response = await fetch(modelPreviewUrl(source, 'thumbnail'), { credentials: 'same-origin' })
    const state = response.ok ? await response.json() : {}
    // Alembic caches need server processing. Their viewer publishes the thumbnail.
    if (!state.needs_thumbnail || state.format === 'abc' || state.size > MAX_SOURCE_BYTES) return false
    const { renderModelThumbnail } = await import('./modelStage')
    const result = await renderModelThumbnail(source)
    return Boolean(result) && await uploadModelThumbnail(source, result.generation, result.blob)
  } catch {
    return false
  }
}

// One render at a time, only while a thumbnail for the model is on screen.
async function work() {
  if (working) return
  working = true
  try {
    while (wanted.size) {
      const [source] = wanted.keys()
      wanted.delete(source)
      attempted.add(source)
      if (await publish(source)) announceModelThumbnail()
    }
  } finally {
    working = false
  }
}

// Returns a release function for when the thumbnail leaves the screen.
export function requestModelThumbnail(thumbnailUrl) {
  const source = modelThumbnailSource(thumbnailUrl)
  if (!source || attempted.has(source)) return () => {}
  wanted.set(source, (wanted.get(source) || 0) + 1)
  void work()
  let released = false
  return () => {
    if (released) return
    released = true
    const count = wanted.get(source) || 0
    if (count > 1) wanted.set(source, count - 1)
    else wanted.delete(source)
  }
}
