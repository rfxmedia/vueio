import api, { getApiErrorMessage } from '../lib/api'
import { copyText } from './clipboard'
import { notify } from './toasts'

// Vue.io gives the network path of a file in three forms. Use the form that
// the file dialogs of this computer understand.
export function networkPathForThisComputer(networkPath) {
  if (!networkPath) return ''
  const platform = String(navigator.userAgentData?.platform || navigator.platform || '').toLowerCase()
  if (platform.startsWith('win')) return networkPath.windows || ''
  if (platform.startsWith('mac')) return networkPath.mac || ''
  return networkPath.smb || ''
}

export function childNetworkPath(networkPath, name) {
  if (!networkPath || !name) return null
  return {
    windows: `${networkPath.windows}\\${name}`,
    mac: `${networkPath.mac}/${name}`,
    smb: `${networkPath.smb}/${name}`,
  }
}

const NOT_ON_NETWORK = 'not-on-network'
const pendingPaths = new Map()

// Loads the network path from a file details URL. Buttons start this when
// the pointer reaches them, so the copy is usually instant.
export function loadNetworkPath(detailsUrl) {
  if (!pendingPaths.has(detailsUrl)) {
    const request = api.get(detailsUrl).then(({ data }) => networkPathForThisComputer(data?.network_path))
    pendingPaths.set(detailsUrl, request)
    request.then(
      () => setTimeout(() => pendingPaths.delete(detailsUrl), 60_000),
      () => pendingPaths.delete(detailsUrl),
    )
  }
  return pendingPaths.get(detailsUrl)
}

export async function copyFilePath(path) {
  const text = Promise.resolve(path).then(value => {
    if (!value) throw new Error(NOT_ON_NETWORK)
    return value
  })
  try {
    await copyText(text)
    notify('Path copied')
  } catch (error) {
    notify(
      error?.message === NOT_ON_NETWORK
        ? 'This file is not in a storage location with a network path.'
        : `Could not copy the path: ${getApiErrorMessage(error)}`,
      { tone: 'error' },
    )
  }
}
