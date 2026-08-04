import { computed, reactive } from 'vue'

import { browserContextKey, createBrowserContext } from '../lib/browserContext'

export function useBrowserSession() {
  let generation = 0
  let abortController = null
  let activeLoader = null
  const state = reactive({
    context: null,
    entries: [],
    loading: false,
    error: '',
    permissions: {},
  })

  function abort() {
    abortController?.abort()
    abortController = null
  }

  function invalidate() {
    generation += 1
    abort()
    state.loading = false
  }

  function isCurrent(requestGeneration, contextKey = browserContextKey(state.context)) {
    return requestGeneration === generation && contextKey === browserContextKey(state.context)
  }

  async function switchContext(context, loader) {
    abort()
    const nextContext = createBrowserContext(context)
    state.context = nextContext
    state.loading = true
    state.error = ''
    activeLoader = loader
    const requestGeneration = ++generation
    const contextKey = browserContextKey(nextContext)
    abortController = new AbortController()

    try {
      const result = await loader(nextContext, { signal: abortController.signal, generation: requestGeneration })
      if (!isCurrent(requestGeneration, contextKey)) return null
      state.entries = result?.entries || result?.items || []
      state.permissions = result?.permissions || state.permissions || {}
      return result
    } catch (error) {
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED' || error?.name === 'AbortError') return null
      if (isCurrent(requestGeneration, contextKey)) state.error = error?.message || 'Failed to load browser contents'
      throw error
    } finally {
      if (isCurrent(requestGeneration, contextKey)) {
        state.loading = false
        abortController = null
      }
    }
  }

  function reload() {
    if (!state.context || !activeLoader) return null
    return switchContext(state.context, activeLoader)
  }

  function navigate(path) {
    if (!state.context || !activeLoader) return null
    return switchContext({ ...state.context, path }, activeLoader)
  }

  return {
    state,
    contextKey: computed(() => browserContextKey(state.context)),
    switchContext,
    reload,
    navigate,
    isCurrent,
    abort,
    invalidate,
    getAbortController: () => abortController,
  }
}
