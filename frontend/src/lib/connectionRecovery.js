import { readonly, ref } from 'vue'

const connectionLost = ref(false)
let retryTimer = null
let interceptorInstalled = false
let updateRecoveryActive = false

function isCanceled(error) {
  return error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED'
}

function isConnectionFailure(error) {
  const status = Number(error?.response?.status || 0)
  return !isCanceled(error) && (!error?.response || [502, 503, 504].includes(status))
}

async function checkReadiness() {
  retryTimer = null
  try {
    const response = await fetch('/api/health/ready', {
      cache: 'no-store',
      credentials: 'same-origin',
    })
    if (updateRecoveryActive) return
    if (response.ok) {
      window.location.reload()
      return
    }
  } catch {
    // The service is still restarting. The next bounded retry will check again.
  }
  if (!updateRecoveryActive) retryTimer = window.setTimeout(checkReadiness, 2000)
}

function beginConnectionRecovery() {
  if (connectionLost.value || updateRecoveryActive) return
  connectionLost.value = true
  checkReadiness()
}

export function installConnectionRecovery(api) {
  if (interceptorInstalled) return
  interceptorInstalled = true
  api.interceptors.response.use(
    response => response,
    (error) => {
      if (!error?.config?.skipConnectionRecovery && isConnectionFailure(error)) beginConnectionRecovery()
      return Promise.reject(error)
    },
  )
}

export function useConnectionRecovery() {
  return { connectionLost: readonly(connectionLost) }
}

// The Updates page owns recovery until the host confirms the new version is healthy.
export function setUpdateRecoveryActive(active) {
  updateRecoveryActive = active
  if (active) {
    if (retryTimer !== null) window.clearTimeout(retryTimer)
    retryTimer = null
    connectionLost.value = false
  }
}
