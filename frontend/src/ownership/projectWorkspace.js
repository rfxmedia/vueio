import { inject, provide } from 'vue'

export const projectWorkspaceStoreKey = Symbol('vueio.projectWorkspaceStore')

export function createProjectWorkspaceStore(workspace) {
  if (!workspace || typeof workspace !== 'object') {
    throw new TypeError('Project workspace store requires an ownership object')
  }
  return workspace
}

export function provideProjectWorkspaceStore(store) {
  provide(projectWorkspaceStoreKey, store)
  return store
}

export function useProjectWorkspaceStore() {
  const store = inject(projectWorkspaceStoreKey, null)
  if (!store) {
    throw new Error('Project workspace store has not been provided')
  }
  return store
}
