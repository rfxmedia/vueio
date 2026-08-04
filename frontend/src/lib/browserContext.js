function normalizePath(path = '') {
  return String(path || '')
    .replace(/\\/g, '/')
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .filter(Boolean)
    .join('/')
}

function freezeContext(context) {
  if (import.meta.env?.DEV || import.meta.env?.MODE === 'test') return Object.freeze(context)
  return context
}

export function createBrowserContext(input = {}) {
  const kind = input.kind || 'nas-auth'
  const rootPath = normalizePath(input.rootPath || '')
  const path = clampPathToRoot({ rootPath }, input.path ?? rootPath)
  return freezeContext({
    ...input,
    kind,
    rootPath,
    path,
  })
}

export function browserContextKey(context) {
  if (!context) return 'none'
  return [
    context.kind,
    context.projectId || '',
    context.shareId || '',
    context.trackerRef || '',
    context.pageRef || '',
    context.rootPath || '',
    context.path || '',
  ].join(':')
}

export function isPathInsideRoot(path = '', rootPath = '') {
  const cleanPath = normalizePath(path)
  const cleanRoot = normalizePath(rootPath)
  if (!cleanRoot) return true
  return cleanPath === cleanRoot || cleanPath.startsWith(`${cleanRoot}/`)
}

function clampPathToRoot(context = {}, path = '') {
  const cleanPath = normalizePath(path)
  const cleanRoot = normalizePath(context.rootPath || '')
  if (!cleanRoot) return cleanPath
  return isPathInsideRoot(cleanPath, cleanRoot) ? cleanPath : cleanRoot
}

export function isAtRoot(context) {
  if (!context) return true
  return normalizePath(context.path) === normalizePath(context.rootPath)
}

export function parentContext(context) {
  if (!context) return null
  const cleanPath = clampPathToRoot(context, context.path)
  const parts = cleanPath.split('/').filter(Boolean)
  if (parts.length) parts.pop()
  const parentPath = clampPathToRoot(context, parts.join('/'))
  return createBrowserContext({ ...context, path: parentPath })
}
