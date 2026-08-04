import { computed, inject, provide, ref } from 'vue'
import api from '../lib/api'

export const updateStatusStoreKey = Symbol('vueio.updateStatusStore')

export function createUpdateStatusStore({ session, apiClient = api }) {
  const status = ref(null)
  const loading = ref(false)

  const updateAvailable = computed(() => Boolean(status.value?.update_available))
  const latestVersion = computed(() => status.value?.latest_version || '')

  async function check({ refresh = false } = {}) {
    if (session.currentUser.value?.role !== 'admin') return null
    if (loading.value || (status.value && !refresh)) return status.value

    loading.value = true
    try {
      const response = await apiClient.get('/api/admin/update-status', {
        params: refresh ? { refresh: true } : undefined,
      })
      status.value = response.data
    } catch (error) {
      const unsupported = error?.response?.status === 404
      status.value = {
        current_version: status.value?.current_version || (unsupported ? 'development' : 'Unknown'),
        latest_version: status.value?.latest_version || null,
        update_available: false,
        configured: unsupported ? false : (status.value?.configured ?? true),
        status: unsupported ? 'unavailable' : 'error',
      }
    } finally {
      loading.value = false
    }
    return status.value
  }

  return {
    status,
    loading,
    updateAvailable,
    latestVersion,
    check,
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
