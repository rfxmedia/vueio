import { inject, provide, ref } from 'vue'
import { useShareAccess } from '../composables/useShareAccess'

export const shareAccessContextKey = Symbol('vueio.shareAccessContext')

export function createShareAccessContext(initial = {}) {
  const refs = {
    shareMode: ref(initial.shareMode ?? false),
    shareRoot: ref(initial.shareRoot ?? ''),
    shareAllowDownload: ref(initial.shareAllowDownload ?? false),
    shareAllowUpload: ref(initial.shareAllowUpload ?? false),
    shareRequestFiles: ref(initial.shareRequestFiles ?? false),
    shareTargetLabel: ref(initial.shareTargetLabel ?? ''),
    sharePasswordRequired: ref(initial.sharePasswordRequired ?? false),
    shareAccessToken: ref(initial.shareAccessToken ?? ''),
    shareAccessTokenScope: ref(initial.shareAccessTokenScope ?? null),
    pendingShareId: ref(initial.pendingShareId ?? null),
    pendingShareType: ref(initial.pendingShareType ?? null),
    shareAccessError: ref(initial.shareAccessError ?? ''),
    sharedItemType: ref(initial.sharedItemType ?? null),
  }
  const access = useShareAccess(refs)

  return {
    ...refs,
    ...access,
  }
}

export function provideShareAccessContext(context) {
  provide(shareAccessContextKey, context)
  return context
}

export function useShareAccessContext() {
  const context = inject(shareAccessContextKey, null)
  if (!context) {
    throw new Error('Share access context has not been provided')
  }
  return context
}
