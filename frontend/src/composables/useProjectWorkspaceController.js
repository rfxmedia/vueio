import { shallowRef, watch } from 'vue'

import api, { getApiErrorMessage } from '../lib/api'
import { recordRecentlyViewed } from '../lib/recentlyViewed'
import { notify } from '../utils/toasts'
import { useProjectBrowser } from './useProjectBrowser'
import { useProjectContentInteractions } from './useProjectContentInteractions'
import { useProjectListState } from './useProjectListState'
import { useProjectShellChrome } from './useProjectShellChrome'

export function normalizeProjectFolderPath(path) {
  return String(path || '')
    .replace(/\\/g, '/')
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .filter(Boolean)
    .join('/')
}

export function buildProjectFolderRouteLocation(projectId, path) {
  if (!projectId) return null
  const normalizedPath = normalizeProjectFolderPath(path)
  if (!normalizedPath) return { name: 'project-folder', params: { projectId } }
  return {
    name: 'project-folder-path',
    params: { projectId, path: normalizedPath.split('/') },
  }
}

function parentFolderFromVirtualPath(path) {
  const parts = normalizeProjectFolderPath(path).split('/').filter(Boolean)
  parts.pop()
  return parts.join('/')
}

/**
 * Owns the project list, project-folder browser, route coordination, and
 * project-contained resource CRUD. Tracker, viewer, upload, sharing, and
 * settings behavior enter through narrow callbacks so those domains keep
 * their own state and request lifecycles.
 */
export function useProjectWorkspaceController({
  router,
  route,
  currentProject,
  currentTracker,
  currentPage,
  openingProjectId,
  getCurrentUser = () => null,
  shareMode,
  sharedItemType,
  pendingShareId,
  shareAccessToken,
  shareAccessTokenScope,
  fileBrowserViewState,
  browserSession,
  isRequestCanceledError,
  openImage,
  openPdf,
  openVideo,
  dismissCurrentMediaForNavigation = () => {},
  closeProjectSettings = () => {},
  closeTrackerSettings = () => {},
  closeDashboardSettings = () => {},
  resetProjectTeamState = () => {},
  loadProjectTeamOptions = () => {},
  prepareProjectStorageSelection = () => {},
  getProjectStorageSelection = () => ({ roots: [], rootId: '', path: null }),
  resetProjectStorageSelection = () => {},
  openShareProjectFromList = () => {},
  handleProjectExternalDragOver,
  handleProjectExternalDragLeave,
  handleProjectExternalDrop,
  handleError = (message, error) => notify(`${message}: ${getApiErrorMessage(error)}`),
} = {}) {
  const projects = shallowRef([])
  const pageSaving = shallowRef(false)
  let projectOpenRequestId = 0

  const browser = useProjectBrowser({
    currentProject,
    getCurrentUser,
    shareMode,
    pendingShareId,
    shareAccessToken,
    shareAccessTokenScope,
    isRequestCanceledError,
    openImage,
    openPdf,
    openVideo,
    fileBrowserViewState,
    browserSession,
  })

  const chrome = useProjectShellChrome()
  const list = useProjectListState({
    projects,
    openShareProjectFromList,
    loadProjects,
  })
  const interactions = useProjectContentInteractions({
    currentProject,
    projectPath: browser.projectPath,
    refreshProjectContents: browser.refreshProjectContents,
    handleProjectExternalDragOver,
    handleProjectExternalDragLeave,
    handleProjectExternalDrop,
  })

  watch(chrome.showCreateProject, (show) => {
    if (show) prepareProjectStorageSelection()
  })

  async function loadProjects() {
    try {
      const { data } = await api.get('/api/projects')
      projects.value = data
    } catch (error) {
      console.error('Failed to load projects')
    }
  }

  async function createProject() {
    if (!chrome.newProjectTitle.value.trim()) return
    const storage = getProjectStorageSelection()
    const workingRoot = storage.roots.find(root => root.id === storage.rootId)
    if (!workingRoot?.available || workingRoot.read_only) {
      notify('Choose an available, writable project storage location')
      return
    }
    try {
      await api.post('/api/projects', {
        title: chrome.newProjectTitle.value,
        description: chrome.newProjectDesc.value,
        due_date: chrome.newProjectDue.value || null,
        storage_root: storage.rootId,
        storage_path: storage.path,
      })
      chrome.newProjectTitle.value = ''
      chrome.newProjectDesc.value = ''
      chrome.newProjectDue.value = ''
      resetProjectStorageSelection()
      chrome.closeCreateProjectModal()
      loadProjects()
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to create project'))
    }
  }

  function normalizeOpenProjectOptions(options = false) {
    if (options && typeof options === 'object') {
      return {
        skipRouteUpdate: options.skipRouteUpdate === true,
        contentsPath: normalizeProjectFolderPath(options.contentsPath || options.initialPath || ''),
      }
    }
    return {
      skipRouteUpdate: options === true,
      contentsPath: '',
    }
  }

  async function openProject(id, options = false) {
    if (openingProjectId.value === id) return
    const { skipRouteUpdate, contentsPath } = normalizeOpenProjectOptions(options)
    const requestId = ++projectOpenRequestId
    openingProjectId.value = id
    try {
      const [projectResponse, projectSnapshot] = await Promise.all([
        api.get(`/api/projects/${id}`),
        browser.loadProjectContents(id, contentsPath, { commit: false }),
      ])
      if (requestId !== projectOpenRequestId || !projectSnapshot) return

      currentProject.value = projectResponse.data
      currentTracker.value = null
      currentPage.value = null
      browser.applyProjectContentsSnapshot(projectSnapshot)
      closeProjectSettings()
      closeTrackerSettings()
      closeDashboardSettings()
      resetProjectTeamState(id)

      if (!shareMode.value) void loadProjectTeamOptions()
      if (!shareMode.value) {
        recordRecentlyViewed({
          type: 'project',
          id: projectResponse.data.id,
          projectId: projectResponse.data.id,
          title: projectResponse.data.title,
          subtitle: 'Project',
        })
      }
      if (!skipRouteUpdate && !shareMode.value) {
        router.push({ name: 'project-folder', params: { projectId: id } })
      }
    } catch {
      notify('Failed to load project')
    } finally {
      if (requestId === projectOpenRequestId && openingProjectId.value === id) {
        openingProjectId.value = null
      }
    }
  }

  async function navigateProjectFolder(path, options = {}) {
    if (!currentProject.value) return
    const normalizedPath = normalizeProjectFolderPath(path)
    await browser.navigateProjectFolder(normalizedPath)
    if (shareMode.value || options.updateRoute === false) return

    const location = buildProjectFolderRouteLocation(currentProject.value.id, normalizedPath)
    if (!location) return
    const targetFullPath = router.resolve(location).fullPath
    if (targetFullPath === route.fullPath) return
    await router[options.replaceRoute ? 'replace' : 'push'](location)
  }

  function closePage() {
    closeDashboardSettings()
    currentPage.value = null
    if (!shareMode.value && currentProject.value) {
      router.push({ name: 'project-folder', params: { projectId: currentProject.value.id } })
    }
  }

  async function openPage(pageRef, skipRouteUpdate = false) {
    if (!currentProject.value || !pageRef) return
    try {
      const { data } = await api.get(
        `/api/projects/${currentProject.value.id}/pages/${encodeURIComponent(pageRef)}`,
      )
      currentPage.value = data
      currentTracker.value = null
      dismissCurrentMediaForNavigation()
      if (!skipRouteUpdate && !shareMode.value) {
        router.push({
          name: 'project-page',
          params: { projectId: currentProject.value.id, page: data.slug || data.id },
        })
      }
    } catch (error) {
      console.error('Failed to load page')
      notify('Failed to load page')
    }
  }

  async function createPage() {
    if (!chrome.newPageTitle.value.trim() || !currentProject.value) return
    try {
      const { data } = await api.post(`/api/projects/${currentProject.value.id}/pages`, {
        title: chrome.newPageTitle.value.trim(),
        description: chrome.newPageDesc.value,
      })
      chrome.newPageTitle.value = ''
      chrome.newPageDesc.value = ''
      chrome.closeCreatePageModal()
      await browser.refreshProjectContents()
      await openPage(data.slug || data.id)
    } catch (error) {
      handleError('Failed to create page', error)
    }
  }

  async function savePage(pageDraft) {
    if (!currentProject.value || !pageDraft?.id) return
    pageSaving.value = true
    try {
      const { data } = await api.put(
        `/api/projects/${currentProject.value.id}/pages/${encodeURIComponent(pageDraft.id)}`,
        {
          title: pageDraft.title,
          description: pageDraft.description || '',
          cover_path: pageDraft.cover_path || null,
          blocks: pageDraft.blocks || [],
        },
      )
      currentPage.value = data
      await browser.refreshProjectContents()
    } catch (error) {
      handleError('Failed to save page', error)
      throw error
    } finally {
      pageSaving.value = false
    }
  }

  function clonePageDraft(page = currentPage.value) {
    return JSON.parse(JSON.stringify(page || { blocks: [] }))
  }

  async function refreshCurrentPage() {
    if (!currentProject.value || !currentPage.value) return
    if (shareMode.value && sharedItemType?.value === 'page') return
    const pageRef = currentPage.value.slug || currentPage.value.id
    if (pageRef) await openPage(pageRef, true)
  }

  async function openPageResourceFolder(path) {
    if (!path) return
    currentPage.value = null
    await navigateProjectFolder(path)
  }

  async function deletePage(page) {
    if (!currentProject.value || !page?.id) return
    if (!confirm(`Delete page "${page.title || page.name}"?`)) return
    try {
      await api.delete(`/api/projects/${currentProject.value.id}/pages/${encodeURIComponent(page.id)}`)
      if (currentPage.value?.id === page.id) {
        currentPage.value = null
        if (!shareMode.value) {
          router.push({ name: 'project-folder', params: { projectId: currentProject.value.id } })
        }
      }
      await browser.refreshProjectContents()
    } catch (error) {
      handleError('Failed to delete page', error)
    }
  }

  async function createProjectFolder() {
    if (!chrome.newFolderName.value.trim() || !currentProject.value) return
    try {
      await api.post(`/api/projects/${currentProject.value.id}/folders`, {
        name: chrome.newFolderName.value,
        parent_path: browser.projectPath.value,
      })
      chrome.newFolderName.value = ''
      chrome.closeCreateFolderModal()
      await browser.refreshProjectContents()
    } catch (error) {
      handleError('Failed to create folder', error)
    }
  }

  async function deleteProjectFolder(path) {
    if (!currentProject.value || !confirm('Delete this folder and all its contents?')) return
    try {
      await api.delete(`/api/projects/${currentProject.value.id}/folders`, { params: { path } })
      await browser.refreshProjectContents()
    } catch {
      notify('Failed to delete folder')
    }
  }

  async function unlinkProjectItem(item) {
    if (!currentProject.value || !confirm('Remove this linked item from the project?')) return
    try {
      await api.delete(`/api/projects/${currentProject.value.id}/link`, {
        params: {
          source_path: item?.source_path || item?.path,
          target_folder: parentFolderFromVirtualPath(item?.path),
        },
      })
      await browser.refreshProjectContents()
    } catch (error) {
      notify(`Failed to unlink item: ${getApiErrorMessage(error)}`)
    }
  }

  async function deleteProjectFile(item) {
    if (!currentProject.value || !item?.path || !confirm('Delete this file?')) return
    try {
      await api.delete(`/api/projects/${currentProject.value.id}/files`, { params: { path: item.path } })
      await browser.refreshProjectContents()
    } catch {
      notify('Failed to delete file')
    }
  }

  async function duplicateItem(item) {
    if (!currentProject.value) return
    try {
      if (item.type === 'tracker') {
        const trackerRef = item.id || item.path || item.slug || item.name
        await api.post(
          `/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(trackerRef)}/duplicate`,
        )
      } else {
        await api.post(`/api/projects/${currentProject.value.id}/duplicate`, {
          path: item.path,
          type: item.type,
          is_linked: item.is_linked || false,
          target_folder: browser.projectPath.value,
        })
      }
      await browser.refreshProjectContents()
    } catch (error) {
      notify(`Failed to duplicate: ${getApiErrorMessage(error)}`)
    }
  }

  return {
    projects,
    pageSaving,
    ...browser,
    ...chrome,
    ...list,
    ...interactions,
    loadProjects,
    createProject,
    openProject,
    navigateProjectFolder,
    closePage,
    openPage,
    createPage,
    savePage,
    clonePageDraft,
    refreshCurrentPage,
    openPageResourceFolder,
    deletePage,
    createProjectFolder,
    deleteProjectFolder,
    unlinkProjectItem,
    deleteProjectFile,
    duplicateItem,
  }
}
