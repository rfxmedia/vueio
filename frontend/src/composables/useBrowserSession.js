import { createBrowserContext } from '../lib/browserContext'

export function useBrowserSession() {
  let abortController = null

  function abort() {
    abortController?.abort()
    abortController = null
  }

  async function switchContext(context, loader) {
    abort()
    const nextContext = createBrowserContext(context)
    const controller = new AbortController()
    abortController = controller

    try {
      const result = await loader(nextContext, { signal: controller.signal })
      return abortController === controller ? result : null
    } catch (error) {
      if (controller.signal.aborted) return null
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED' || error?.name === 'AbortError') return null
      throw error
    } finally {
      if (abortController === controller) abortController = null
    }
  }

  return {
    switchContext,
    abort,
    invalidate: abort,
    getAbortController: () => abortController,
  }
}
