import { computed, ref } from 'vue'

export function useBrowserRenderWindow(sourceItems, { batchSize = 200 } = {}) {
  const renderLimit = ref(batchSize)
  const visibleItems = computed(() => sourceItems.value.slice(0, renderLimit.value))
  const canLoadMore = computed(() => sourceItems.value.length > visibleItems.value.length)

  function resetRenderLimit() {
    renderLimit.value = batchSize
  }

  function loadMoreItems() {
    renderLimit.value = Math.min(sourceItems.value.length, renderLimit.value + batchSize)
  }

  return {
    renderLimit,
    visibleItems,
    canLoadMore,
    resetRenderLimit,
    loadMoreItems,
  }
}
