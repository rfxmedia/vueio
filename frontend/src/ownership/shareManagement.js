import { inject, provide } from 'vue'
import { useShareAuthModalCluster } from '../composables/useShareAuthModalCluster'

export const shareManagementStoreKey = Symbol('vueio.shareManagementStore')

export function createShareManagementStore(options) {
  return useShareAuthModalCluster(options)
}

export function provideShareManagementStore(store) {
  provide(shareManagementStoreKey, store)
  return store
}

export function useShareManagementStore() {
  const store = inject(shareManagementStoreKey, null)
  if (!store) throw new Error('Share management store has not been provided')
  return store
}
