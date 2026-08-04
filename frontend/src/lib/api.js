import axios from 'axios'

export function getApiErrorDetail(error) {
  return error?.response?.data?.detail
    || error?.response?.data?.error
    || error?.response?.data?.message
}

export function getApiErrorMessage(error, fallback = 'Unknown error') {
  const value = getApiErrorDetail(error) || error?.message || fallback
  if (typeof value === 'string') return value
  return value?.message || fallback
}

export function buildShareCredentialQuery(extra = {}, _credential = {}) {
  const params = new URLSearchParams(extra)
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function resolveAccessEndpoint({ shareId = null, shared, authenticated }) {
  const endpoint = shareId ? shared : authenticated
  if (typeof endpoint === 'function') return endpoint(shareId ? encodeURIComponent(shareId) : null)
  return endpoint
}

export default axios.create()
