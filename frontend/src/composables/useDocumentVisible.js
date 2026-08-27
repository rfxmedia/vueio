import { getCurrentScope, onScopeDispose, readonly, ref } from 'vue'

const visibilityStates = new WeakMap()

function createVisibilityState(documentTarget) {
  const visible = ref(documentTarget.visibilityState !== 'hidden')
  const update = () => {
    visible.value = documentTarget.visibilityState !== 'hidden'
  }

  return {
    consumers: 0,
    update,
    visible,
  }
}

export function useDocumentVisible(documentTarget = globalThis.document) {
  if (!documentTarget?.addEventListener) return readonly(ref(true))

  let state = visibilityStates.get(documentTarget)
  if (!state) {
    state = createVisibilityState(documentTarget)
    visibilityStates.set(documentTarget, state)
  }

  state.consumers += 1
  if (state.consumers === 1) {
    state.update()
    documentTarget.addEventListener('visibilitychange', state.update)
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      state.consumers = Math.max(0, state.consumers - 1)
      if (state.consumers === 0) {
        documentTarget.removeEventListener('visibilitychange', state.update)
      }
    })
  }

  return readonly(state.visible)
}
