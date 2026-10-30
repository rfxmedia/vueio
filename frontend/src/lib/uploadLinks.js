// Sends a file to an upload link in parts. The server checks access again for
// each part, so a long upload of a large matte stays safe and can resume.
const RETRIES = 3

async function readError(response) {
  try {
    const data = await response.json()
    return typeof data?.detail === 'string' ? data.detail : `Upload failed (${response.status})`
  } catch {
    return `Upload failed (${response.status})`
  }
}

async function request(link, init) {
  const response = await fetch(link.upload_url, {
    ...init,
    headers: { 'X-Vueio-Upload-Token': link.upload_token, ...(init.headers || {}) },
  })
  if (!response.ok) {
    const error = new Error(await readError(response))
    error.status = response.status
    throw error
  }
  return response.json()
}

export async function uploadWithLink(link, file, { onProgress = () => {}, signal } = {}) {
  // An empty file has no parts; finishing completes it.
  if (!file.size) return request(link, { method: 'POST', signal })
  const chunkSize = Math.max(1, Number(link.chunk_size) || 8 * 1024 * 1024)
  let offset = 0
  let result = null
  while (offset < file.size) {
    const end = Math.min(offset + chunkSize, file.size)
    for (let attempt = 1; ; attempt += 1) {
      try {
        result = await request(link, {
          method: 'PUT',
          signal,
          headers: { 'Content-Range': `bytes ${offset}-${end - 1}/${file.size}` },
          body: file.slice(offset, end),
        })
        break
      } catch (error) {
        // Access and size errors do not get better with another try.
        if (signal?.aborted || attempt >= RETRIES || (error.status && error.status < 500)) throw error
        await new Promise(resolve => setTimeout(resolve, 800 * attempt))
        // The server may have stored the part before the connection broke.
        const progress = await request(link, { method: 'GET', signal }).catch(() => null)
        if (progress?.complete) return progress
        if (Number.isFinite(progress?.received) && progress.received >= end) break
      }
    }
    offset = end
    onProgress(offset / file.size)
    if (result?.complete) return result
  }
  return result?.complete ? result : request(link, { method: 'POST', signal })
}
