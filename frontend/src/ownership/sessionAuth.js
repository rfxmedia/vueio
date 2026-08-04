import { inject, provide } from 'vue'
import { useAppSession } from '../composables/useAppSession'

export const sessionAuthStoreKey = Symbol('vueio.sessionAuthStore')

export function createSessionAuthStore(options) {
  return useAppSession(options)
}

export function provideSessionAuthStore(store) {
  provide(sessionAuthStoreKey, store)
  return store
}

export function useSessionAuthStore() {
  const store = inject(sessionAuthStoreKey, null)
  if (!store) {
    throw new Error('Session/auth store has not been provided')
  }
  return store
}
