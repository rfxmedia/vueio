import { inject, provide, ref } from 'vue'
import api from '../lib/api'
import { normalizeExternalHttpUrl } from '../utils/textSanitization'

export const appIdentityStoreKey = Symbol('vueio.appIdentityStore')

function normalizeIdentity(value = {}) {
  return {
    team_name: String(value?.team_name || '').trim() || 'Vue',
    website_url: normalizeExternalHttpUrl(value?.website_url),
    logo_upload_name: String(value?.logo_upload_name || '').trim(),
    logo_url: String(value?.logo_url || '').trim(),
  }
}

export function createAppIdentityStore({ client = api, logger = console } = {}) {
  const identity = ref(normalizeIdentity())

  function update(value) {
    identity.value = normalizeIdentity(value)
  }

  async function load() {
    try {
      const { data } = await client.get('/api/identity')
      update(data)
    } catch (error) {
      logger.warn('Failed to load app identity:', error)
    }
  }

  return { identity, update, load }
}

export function provideAppIdentityStore(store) {
  provide(appIdentityStoreKey, store)
  return store
}

export function useAppIdentityStore() {
  const store = inject(appIdentityStoreKey, null)
  if (!store) throw new Error('App identity store has not been provided')
  return store
}
