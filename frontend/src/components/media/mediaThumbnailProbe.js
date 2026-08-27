import api from '../../lib/api'

const thumbnailStateCache = new Map()
const thumbnailProbeRequests = new Map()
const observedThumbnails = new Map()
const visibilitySubscribers = new Set()
let thumbnailObserver = null

export function getThumbnailState(src) {
  return thumbnailStateCache.get(src)
}

export function setThumbnailState(src, state) {
  thumbnailStateCache.set(src, state)
}

export function clearThumbnailState(src) {
  thumbnailStateCache.delete(src)
}

export function probeThumbnail(src) {
  const inFlight = thumbnailProbeRequests.get(src)
  if (inFlight) return inFlight

  const request = api.head(src)
    .then((response) => {
      const contentType = String(response.headers?.['content-type'] || '').toLowerCase()
      const state = contentType.includes('image/svg+xml') ? 'pending' : 'ready'
      setThumbnailState(src, state)
      return state
    })
    .finally(() => {
      if (thumbnailProbeRequests.get(src) === request) thumbnailProbeRequests.delete(src)
    })

  thumbnailProbeRequests.set(src, request)
  return request
}

function getThumbnailObserver() {
  if (thumbnailObserver || typeof IntersectionObserver === 'undefined') return thumbnailObserver
  thumbnailObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => observedThumbnails.get(entry.target)?.(entry.isIntersecting))
  }, { rootMargin: '200px' })
  return thumbnailObserver
}

export function observeThumbnail(element, callback) {
  const observer = getThumbnailObserver()
  if (!observer) {
    callback(true)
    return () => {}
  }
  observedThumbnails.set(element, callback)
  observer.observe(element)
  return () => {
    observer.unobserve(element)
    observedThumbnails.delete(element)
    if (observedThumbnails.size === 0) {
      observer.disconnect()
      thumbnailObserver = null
    }
  }
}

function notifyVisibilitySubscribers() {
  const visible = document.visibilityState !== 'hidden'
  visibilitySubscribers.forEach((callback) => callback(visible))
}

export function subscribeToThumbnailVisibility(callback) {
  if (typeof document === 'undefined') return () => {}
  if (visibilitySubscribers.size === 0) {
    document.addEventListener('visibilitychange', notifyVisibilitySubscribers)
  }
  visibilitySubscribers.add(callback)
  return () => {
    visibilitySubscribers.delete(callback)
    if (visibilitySubscribers.size === 0) {
      document.removeEventListener('visibilitychange', notifyVisibilitySubscribers)
    }
  }
}
