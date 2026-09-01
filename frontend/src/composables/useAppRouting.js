import { isRestrictedProjectMember } from '../utils/accountAccess'

const SHARE_ROUTE_NAMES = ['shared-nas', 'shared-project', 'shared-tracker', 'shared-project-file', 'shared-project-file-root']

function getPathParamValue(pathParam) {
  if (Array.isArray(pathParam)) return pathParam.join('/')
  return pathParam || ''
}

function getShareType(routeName, routeMeta) {
  if (routeMeta?.shareType) return routeMeta.shareType
  if (routeName?.includes('nas')) return 'nas'
  if (routeName?.includes('tracker')) return 'tracker'
  if (routeName?.includes('project-file')) return 'project-file'
  return 'project'
}

function routeRefMatches(entity, routeRef, keys) {
  if (!entity || routeRef === null || routeRef === undefined) return false
  const expected = String(routeRef)
  return keys.some((key) => {
    const value = entity[key]
    return value !== null && value !== undefined && String(value) === expected
  })
}

export function useAppRouting({
  route,
  router,
  shell,
  session,
  share,
  shareManagement,
  selection,
  fileBrowser,
  workspace,
  tracker,
  viewer,
}) {
  const { loading, activeModule } = shell
  const {
    shareMode,
    shareAllowUpload,
    shareRequestFiles,
    shareTargetLabel,
    pendingShareId,
    shareAccessToken,
    shareAccessTokenScope,
    sharePasswordRequired,
  } = share
  const { sharePasswordInput } = shareManagement
  const {
    showLogin,
    currentUser,
    checkAuth,
    checkSetupStatus,
  } = session
  const { currentProject, currentTracker, currentPage } = selection
  const { currentPath, loadSharedContent, loadFiles, loadSharedProjectContent } = fileBrowser.browser
  const {
    projectPath,
    loadProjects,
    openProject,
    openPage,
    navigateProjectFolder,
  } = workspace
  const { openTracker } = tracker
  const {
    dismissCurrentMedia: dismissCurrentMediaForNavigation,
    returnToCommentOrigin,
  } = viewer.media
  const {
    canReturnToCommentOrigin,
    commentReferenceOriginContext,
  } = viewer.state || {}
  let currentNavigationId = 0
  let currentNavigationController = null

  function isCommentOriginRoute() {
    const originPath = commentReferenceOriginContext?.value?.routeFullPath || ''
    return Boolean(canReturnToCommentOrigin?.value && originPath && originPath === route.fullPath)
  }

  function reuseHydratedProjectRoute(routeName, params) {
    if (!routeRefMatches(currentProject.value, params.projectId, ['id'])) return false

    if (routeName === 'project-folder' || routeName === 'project-folder-path') {
      const folderPath = routeName === 'project-folder-path' ? getPathParamValue(params.path) : ''
      if ((projectPath?.value || '') !== folderPath) return false
      currentTracker.value = null
      if (currentPage) currentPage.value = null
      return true
    }

    if (routeName === 'project-tracker') {
      return routeRefMatches(currentTracker.value, params.tracker, ['id', 'slug', 'name'])
    }

    if (routeName === 'project-page') {
      return routeRefMatches(currentPage?.value, params.page, ['id', 'slug'])
    }

    return false
  }

  function resetAuthenticatedNavigationState() {
    shareMode.value = false
    if (shareAllowUpload) shareAllowUpload.value = false
    if (shareRequestFiles) shareRequestFiles.value = false
    if (shareTargetLabel) shareTargetLabel.value = ''
    pendingShareId.value = null
    if (shareAccessToken) shareAccessToken.value = ''
    if (shareAccessTokenScope) shareAccessTokenScope.value = null
    sharePasswordInput.value = ''
    sharePasswordRequired.value = false
    showLogin.value = false
  }

  async function handleShareRoute(routeName, params, routeMeta) {
    const shareId = params.shareId
    const shareType = getShareType(routeName, routeMeta)
    const sharePath = getPathParamValue(params.path)

    if (shareType === 'nas') {
      await loadSharedContent(shareId, 'file', null, sharePath)
      return
    }

    if (shareType === 'project' || shareType === 'tracker') {
      await loadSharedContent(shareId, 'project')
      if (shareType === 'project' && params.tracker && !currentTracker.value) {
        openTracker(params.tracker)
      }
      return
    }

    if (shareType === 'project-file') {
      await loadSharedProjectContent(shareId, sharePath)
    }
  }

  async function handleProtectedHomeRoute(signal) {
    activeModule.value = 'home'
    currentProject.value = null
    currentTracker.value = null
    if (currentPage) currentPage.value = null
    await loadProjects({ signal })
    loading.value = false
  }

  async function handleProtectedRoute(routeName, params, isStale, signal) {
    if (routeName === 'files') {
      if (!session.canAccessFileBrowser.value) {
        router.replace('/projects')
        return
      }
      activeModule.value = 'files'
      const filePath = getPathParamValue(params.path)
      currentPath.value = filePath
      await loadFiles(filePath)
      if (isStale()) return
      loading.value = false
      return
    }

    if (routeName === 'projects') {
      activeModule.value = 'projects'
      currentProject.value = null
      currentTracker.value = null
      if (currentPage) currentPage.value = null
      await loadProjects({ signal })
      if (isStale()) return
      loading.value = false
      return
    }

    if (routeName === 'project-folder' || routeName === 'project-folder-path') {
      const folderPath = routeName === 'project-folder-path' ? getPathParamValue(params.path) : ''
      activeModule.value = 'projects'
      if (
        routeName === 'project-folder-path' &&
        currentProject.value?.id === params.projectId &&
        (projectPath?.value || '') === folderPath
      ) {
        currentTracker.value = null
        if (currentPage) currentPage.value = null
        loading.value = false
        return
      }
      await loadProjects({ signal })
      if (isStale()) return
      await openProject(params.projectId, {
        skipRouteUpdate: true,
        contentsPath: folderPath,
        signal,
      })
      if (isStale()) return
      if (!folderPath && isRestrictedProjectMember(currentUser.value) && projectPath?.value) {
        await router.replace({
          name: 'project-folder-path',
          params: { projectId: params.projectId, path: projectPath.value.split('/').filter(Boolean) },
        })
        if (isStale()) return
      }
      if (currentPage) currentPage.value = null
      loading.value = false
      return
    }

    if (routeName === 'project-tracker') {
      activeModule.value = 'projects'
      if (routeRefMatches(currentProject.value, params.projectId, ['id'])) {
        await openTracker(params.tracker, { skipRouteUpdate: true, signal })
      } else {
        await loadProjects({ signal })
        if (isStale()) return
        await openProject(params.projectId, { skipRouteUpdate: true, signal })
        if (isStale()) return
        await openTracker(params.tracker, { skipRouteUpdate: true, signal })
      }
      if (isStale()) return
      loading.value = false
      return
    }

    if (routeName === 'project-page') {
      activeModule.value = 'projects'
      await loadProjects({ signal })
      if (isStale()) return
      await openProject(params.projectId, { skipRouteUpdate: true, signal })
      if (isStale()) return
      await openPage(params.page, { skipRouteUpdate: true, signal })
      if (isStale()) return
      loading.value = false
      return
    }

    if (routeName === 'settings') {
      activeModule.value = 'settings'
      currentProject.value = null
      currentTracker.value = null
      if (currentPage) currentPage.value = null
      loading.value = false
      return
    }

    loading.value = false
  }

  async function handleRouteChange() {
    const navId = ++currentNavigationId
    currentNavigationController?.abort()
    const navigationController = new AbortController()
    currentNavigationController = navigationController
    const { signal } = navigationController
    const isStale = () => navId !== currentNavigationId

    const routeName = route.name
    const params = route.params
    const query = route.query
    const returningToCommentOrigin = isCommentOriginRoute()
    const preservingCommentOrigin = Boolean(
      canReturnToCommentOrigin?.value
      && String(params.projectId || '') === String(currentProject.value?.id || ''),
    )

    loading.value = true

    if (query.share) {
      router.replace({ name: 'shared-nas', params: { shareId: query.share, path: [] } })
      return
    }

    if (query.project) {
      router.replace({ name: 'shared-project', params: { shareId: query.project } })
      return
    }

    const isShareRoute = route.meta?.public && route.meta?.shareType
    const isShareRouteName = SHARE_ROUTE_NAMES.includes(routeName)

    if (!returningToCommentOrigin) {
      dismissCurrentMediaForNavigation?.(
        preservingCommentOrigin ? { preserveCommentHistory: true } : undefined,
      )
    }

    if (isShareRoute || isShareRouteName) {
      await handleShareRoute(routeName, params, route.meta)
      if (isStale()) return
      loading.value = false
      return
    }

    if (typeof checkSetupStatus === 'function') {
      const needsSetup = await checkSetupStatus()
      if (isStale()) return
      if (needsSetup) {
        showLogin.value = false
        loading.value = false
        return
      }
    }

    if (routeName === 'login') {
      showLogin.value = true
      loading.value = false
      return
    }

    const isAuthed = await checkAuth()
    if (isStale()) return

    if (!isAuthed) {
      showLogin.value = true
      loading.value = false
      return
    }

    resetAuthenticatedNavigationState()

    if (returningToCommentOrigin) {
      const restored = await returnToCommentOrigin?.()
      if (isStale()) return
      if (restored) {
        activeModule.value = 'projects'
        loading.value = false
        return
      }
    }

    if (reuseHydratedProjectRoute(routeName, params)) {
      activeModule.value = 'projects'
      loading.value = false
      return
    }

    if (routeName === 'home' || !routeName) {
      await handleProtectedHomeRoute(signal)
      return
    }

    await handleProtectedRoute(routeName, params, isStale, signal)
  }

  return {
    handleRouteChange,
  }
}
