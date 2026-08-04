import { inject, provide } from 'vue'

export const viewerStoreKey = Symbol('vueio.viewerStore')

const REQUIRED_SECTIONS = ['media', 'comparison', 'presentation', 'sidebar', 'actions']

export function createViewerStore(sections) {
  if (!sections || typeof sections !== 'object') {
    throw new TypeError('Viewer store sections are required')
  }

  for (const name of REQUIRED_SECTIONS) {
    if (!sections[name] || typeof sections[name] !== 'object') {
      throw new TypeError(`Viewer store requires a ${name} section`)
    }
  }

  return Object.freeze(Object.fromEntries(
    REQUIRED_SECTIONS.map(name => [name, Object.freeze({ ...sections[name] })]),
  ))
}

export function provideViewerStore(store) {
  provide(viewerStoreKey, store)
  return store
}

export function useViewerStore() {
  const store = inject(viewerStoreKey, null)
  if (!store) {
    throw new Error('Viewer store has not been provided')
  }
  return store
}
