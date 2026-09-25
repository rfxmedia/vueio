// Model thumbnails are rendered in a publisher's browser with the review
// engine. This module stays small; the 3D engine loads only for a render.
const MiB = 1024 * 1024
// Background renders parse the model on the page's main thread. Larger models,
// and Alembic caches that need server processing, get a thumbnail when a
// publisher opens them.
const BACKGROUND_LIMITS = { glb: 64 * MiB, gltf: 64 * MiB, obj: 16 * MiB, stl: 16 * MiB, fbx: 8 * MiB }
// Sources that on-screen thumbnails wait for, with the number of thumbnails.
const wanted = new Map()
const attempted = new Set()
const listeners = new Set()
let current = null
let holds = 0
let working = false

export function fitsBackgroundRender(format, bytes) {
  return bytes <= (BACKGROUND_LIMITS[format] || 0)
}

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

// Without a source, every waiting thumbnail checks for its image again.
export function announceModelThumbnail(source = '') {
  for (const listener of listeners) listener(source)
}

// An open viewer needs the network and graphics processor. Thumbnails wait.
export function holdModelThumbnails() {
  holds++
  current?.controller.abort()
  let released = false
  return () => {
    if (released) return
    released = true
    holds--
  }
}

export function watchModelThumbnails(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function publish(source, signal) {
  try {
    const response = await fetch(modelPreviewUrl(source, 'thumbnail'), { credentials: 'same-origin', signal, priority: 'low' })
    const state = response.ok ? await response.json() : {}
    if (!state.needs_thumbnail || !fitsBackgroundRender(state.format, state.size)) return false
    const { renderModelThumbnail } = await import('./modelStage')
    const result = await renderModelThumbnail(source, signal)
    return Boolean(result) && await uploadModelThumbnail(source, result.generation, result.blob)
  } catch {
    return false
  }
}

// Render only while the page is visible, no viewer is open, and the browser is idle.
async function readyToRender() {
  while (document.hidden || holds) await new Promise(resolve => setTimeout(resolve, 1000))
  await new Promise(resolve => window.requestIdleCallback ? requestIdleCallback(resolve, { timeout: 2000 }) : setTimeout(resolve, 100))
}

// One render at a time, only while a thumbnail for the model is on screen.
async function work() {
  if (working) return
  working = true
  try {
    while (wanted.size) {
      await readyToRender()
      const [next] = wanted
      if (!next) break
      const [source, count] = next
      wanted.delete(source)
      attempted.add(source)
      current = { source, count, controller: new AbortController() }
      const published = await publish(source, current.controller.signal)
      if (current.controller.signal.aborted) {
        // Try again when the thumbnail is on screen and a viewer is not open.
        attempted.delete(source)
        if (current.count > 0) wanted.set(source, current.count)
      } else if (published) announceModelThumbnail(source)
      current = null
    }
  } finally {
    working = false
  }
}

// Returns a release function for when the thumbnail leaves the screen.
export function requestModelThumbnail(thumbnailUrl) {
  const source = modelThumbnailSource(thumbnailUrl)
  if (!source) return () => {}
  if (current?.source === source) current.count++
  else if (attempted.has(source)) return () => {}
  else wanted.set(source, (wanted.get(source) || 0) + 1)
  void work()
  let released = false
  return () => {
    if (released) return
    released = true
    // Stop a render that no thumbnail on screen waits for.
    if (current?.source === source) {
      if (--current.count === 0) current.controller.abort()
      return
    }
    const count = wanted.get(source) || 0
    if (count > 1) wanted.set(source, count - 1)
    else wanted.delete(source)
  }
}
