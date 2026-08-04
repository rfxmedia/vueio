import api from './api'

export function recordRecentlyViewed(item) {
  if (!item?.id || !item?.type) return
  try {
    void Promise.resolve(api.post('/api/recently-viewed', item)).catch(() => {
      // Recent history is helpful, but it must never block primary navigation.
    })
  } catch {
    // Recent history is helpful, but it must never block primary navigation.
  }
}
