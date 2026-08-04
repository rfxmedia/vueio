import { onBeforeUnmount, onMounted, toValue, watch } from 'vue'

export function useOutsideClick(target, onDismiss, { enabled = true, escape = false, isInside } = {}) {
  let listening = false
  let stopEnabledWatch = null

  function handlePointerDown(event) {
    if (!toValue(enabled)) return
    const element = toValue(target)
    const eventIsInside = typeof isInside === 'function'
      ? isInside(event, element)
      : element?.contains(event.target)
    if (eventIsInside) return
    onDismiss(event, 'outside')
  }

  function handleKeydown(event) {
    if (!escape || event.key !== 'Escape' || !toValue(enabled)) return
    onDismiss(event, 'escape')
  }

  function addListeners() {
    if (listening || typeof document === 'undefined') return
    document.addEventListener('pointerdown', handlePointerDown, true)
    if (escape) document.addEventListener('keydown', handleKeydown)
    listening = true
  }

  function removeListeners() {
    if (!listening || typeof document === 'undefined') return
    document.removeEventListener('pointerdown', handlePointerDown, true)
    if (escape) document.removeEventListener('keydown', handleKeydown)
    listening = false
  }

  onMounted(() => {
    stopEnabledWatch = watch(
      () => Boolean(toValue(enabled)),
      isEnabled => (isEnabled ? addListeners() : removeListeners()),
      { immediate: true },
    )
  })

  onBeforeUnmount(() => {
    stopEnabledWatch?.()
    removeListeners()
  })
}
