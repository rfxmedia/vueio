import { computed, ref, watch } from 'vue'
import api from '../lib/api'

import { readStoredBoolean } from '../utils/storage'
import { notify } from '../utils/toasts'

const PROJECT_SORT_LABELS = {
  updated: 'Last Updated',
  created: 'Created Date',
  title: 'Title',
  due_date: 'Due Date',
}

const PROJECT_GROUP_ORDER = ['in_progress', 'waiting_review', 'edits_requested', 'not_started', 'done']

function normalizedProjectStatus(status) {
  return status === 'active' ? 'in_progress' : (status || 'not_started')
}

function timestampValue(value) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? (value < 1e12 ? value * 1000 : value) : 0
  }
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? timestamp : 0
}

export function useProjectListState({
  projects,
  openShareProjectFromList,
  loadProjects,
}) {
  const projectSort = ref('updated')
  const showSortMenu = ref(false)
  const groupByStatus = ref(readStoredBoolean('vueio_projects_group_by_status', true))
  const projectsListView = ref(readStoredBoolean('vueio_projects_list_view', false))
  const hideDoneProjects = ref(readStoredBoolean('vueio_hide_done_projects', false))

  const projectMenuOpen = ref(null)

  const projectSortLabel = computed(() => PROJECT_SORT_LABELS[projectSort.value] || 'Sort')

  const sortedProjects = computed(() => {
    let filtered = [...projects.value]

    if (hideDoneProjects.value) {
      filtered = filtered.filter(project => project.status !== 'done')
    }

    switch (projectSort.value) {
      case 'updated':
        return filtered.sort((a, b) => timestampValue(b.updated_at) - timestampValue(a.updated_at))
      case 'created':
        return filtered.sort((a, b) => timestampValue(b.created_at) - timestampValue(a.created_at))
      case 'title':
        return filtered.sort((a, b) => (a.title || '').localeCompare(b.title || ''))
      case 'due_date':
        return filtered.sort((a, b) => {
          if (!a.due_date) return 1
          if (!b.due_date) return -1
          return new Date(a.due_date) - new Date(b.due_date)
        })
      default:
        return filtered
    }
  })

  const projectGroups = computed(() => {
    const groups = {}
    for (const project of sortedProjects.value) {
      const status = normalizedProjectStatus(project.status)
      if (!groups[status]) groups[status] = []
      groups[status].push(project)
    }
    const extra = Object.keys(groups).filter(status => !PROJECT_GROUP_ORDER.includes(status)).sort()
    const order = [...PROJECT_GROUP_ORDER, ...extra]
    return order
      .map(status => ({ status, projects: groups[status] || [] }))
      .filter(group => group.projects.length > 0)
  })

  watch(groupByStatus, value => {
    localStorage.setItem('vueio_projects_group_by_status', value ? 'true' : 'false')
  })

  watch(projectsListView, value => {
    localStorage.setItem('vueio_projects_list_view', value ? 'true' : 'false')
  })

  watch(hideDoneProjects, value => {
    localStorage.setItem('vueio_hide_done_projects', value ? 'true' : 'false')
  })

  function setProjectsListView(value) {
    projectsListView.value = value
  }

  function toggleSortMenu() {
    showSortMenu.value = !showSortMenu.value
  }

  function setProjectSort(value) {
    projectSort.value = value
    showSortMenu.value = false
  }

  function toggleGroupByStatus() {
    groupByStatus.value = !groupByStatus.value
    showSortMenu.value = false
  }

  function toggleHideDoneProjects() {
    hideDoneProjects.value = !hideDoneProjects.value
    showSortMenu.value = false
  }

  function resetProjectMenu() {
    projectMenuOpen.value = null
  }

  function toggleProjectMenu(projectId) {
    projectMenuOpen.value = projectMenuOpen.value === projectId ? null : projectId
  }

  function shareProjectFromList(project) {
    projectMenuOpen.value = null
    openShareProjectFromList(project)
  }

  async function deleteProjectConfirm(project) {
    projectMenuOpen.value = null
    if (!confirm(`Delete project "${project.title}"? This cannot be undone.`)) return
    try {
      await api.delete(`/api/projects/${project.id}`)
      await loadProjects()
    } catch {
      notify('Failed to delete project')
    }
  }

  return {
    projectSort,
    showSortMenu,
    projectSortLabel,
    groupByStatus,
    projectsListView,
    hideDoneProjects,
    sortedProjects,
    projectGroups,
    projectMenuOpen,
    setProjectsListView,
    toggleSortMenu,
    setProjectSort,
    toggleGroupByStatus,
    toggleHideDoneProjects,
    resetProjectMenu,
    toggleProjectMenu,
    shareProjectFromList,
    deleteProjectConfirm,
  }
}
