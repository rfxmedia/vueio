import { readonly, ref } from 'vue'

const connectionLost = ref(false)
let retryTimer = null
let interceptorInstalled = false
let reloadPage = () => window.location.reload()

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
    if (response.ok) {
      reloadPage()
      return
    }
  } catch {
    // The service is still restarting. The next bounded retry will check again.
  }
  retryTimer = window.setTimeout(checkReadiness, 2000)
}

function beginConnectionRecovery() {
  if (connectionLost.value) return
  connectionLost.value = true
  checkReadiness()
}

export function installConnectionRecovery(api) {
  if (interceptorInstalled) return
  interceptorInstalled = true
  api.interceptors.response.use(
    response => response,
    (error) => {
      if (isConnectionFailure(error)) beginConnectionRecovery()
      return Promise.reject(error)
    },
  )
}

export function useConnectionRecovery() {
  return { connectionLost: readonly(connectionLost) }
}

export function resetConnectionRecoveryForTests() {
  if (retryTimer !== null) window.clearTimeout(retryTimer)
  retryTimer = null
  interceptorInstalled = false
  connectionLost.value = false
  reloadPage = () => window.location.reload()
}

export function setConnectionRecoveryReloadForTests(reload) {
  reloadPage = reload
}
