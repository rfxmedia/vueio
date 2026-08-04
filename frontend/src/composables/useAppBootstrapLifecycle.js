import { onMounted, onUnmounted, watch } from 'vue'

const LOW_FX_MEDIA_QUERY = '(max-width: 1100px), (prefers-reduced-motion: reduce)'

export function useAppBootstrapLifecycle({
  route,
  loadAppIdentity,
  updateLowFxMode,
  handleRouteChange,
  handleKeydown,
  handleGlobalKeydown,
  handleViewportResize,
  handleWindowDragOver,
  handleWindowDrop,
  handleBeforeUnload,
  getFilesAbortController,
  getProjectContentsAbortController,
}) {
  let lowFxMediaQuery = null

  const windowListeners = [
    ['keydown', handleKeydown],
    ['keydown', handleGlobalKeydown],
    ['resize', handleViewportResize],
    ['dragover', handleWindowDragOver],
    ['drop', handleWindowDrop],
    ['beforeunload', handleBeforeUnload],
  ].filter(([, handler]) => typeof handler === 'function')

  function addWindowListeners() {
    for (const [eventName, handler] of windowListeners) {
      window.addEventListener(eventName, handler)
    }
  }

  function removeWindowListeners() {
    for (const [eventName, handler] of windowListeners) {
      window.removeEventListener(eventName, handler)
    }
  }

  onMounted(async () => {
    loadAppIdentity?.()

    updateLowFxMode()
    handleViewportResize?.()
    if (typeof window !== 'undefined' && window.matchMedia) {
      lowFxMediaQuery = window.matchMedia(LOW_FX_MEDIA_QUERY)
      lowFxMediaQuery.addEventListener?.('change', updateLowFxMode)
    }

    await handleRouteChange()
    addWindowListeners()
  })

  watch(() => route.fullPath, async () => {
    await handleRouteChange()
  }, { immediate: false })

  onUnmounted(() => {
    removeWindowListeners()
    lowFxMediaQuery?.removeEventListener?.('change', updateLowFxMode)
    getFilesAbortController?.()?.abort?.()
    getProjectContentsAbortController?.()?.abort?.()
  })
}
