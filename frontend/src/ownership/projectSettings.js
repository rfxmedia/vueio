import { computed, inject, provide, ref } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'
import { useModal } from '../composables/useModal'
import { useProjectTeamManagement } from '../composables/useProjectTeamManagement'
import { useTrackerSettings } from '../composables/useTrackerSettings'
import { notify } from '../utils/toasts'

export const projectSettingsStoreKey = Symbol('vueio.projectSettingsStore')

const PROJECT_STATUS_OPTIONS = [
  { value: 'not_started', label: 'Not Started' },
  { value: 'in_progress', label: 'Active' },
  { value: 'waiting_review', label: 'Review' },
  { value: 'edits_requested', label: 'Edits Requested' },
  { value: 'done', label: 'Done' },
]

export function createProjectSettingsStore(ctx) {
  const projectModal = useModal()
  const storageModal = useModal()
  const dashboardModal = useModal()

  const projectTarget = ref(null)
  const projectSaving = ref(false)
  const projectDraftTitle = ref('')
  const projectDraftDescription = ref('')
  const projectDraftDueDate = ref('')
  const projectDraftStatus = ref('not_started')

  const storageMode = ref('relocate')
  const storageTarget = ref(null)
  const storageRoots = ref([])
  const newProjectStorageRoot = ref('')
  const newProjectStoragePath = ref(null)

  const dashboardSaving = ref(false)
  const dashboardDraftTitle = ref('')
  const dashboardDraftDescription = ref('')

  const activeProject = computed(() => projectTarget.value || ctx.currentProject.value || null)
  const canOpenProjectSettings = computed(() => (
    !ctx.shareMode.value && !!ctx.currentProject.value && ctx.isAdmin.value
  ))
  const canEditActiveProject = computed(() => (
    Boolean(activeProject.value) && !ctx.shareMode.value && ctx.isAdmin.value
  ))
  const canManageProjectTeam = computed(() => (
    Boolean(activeProject.value) && !ctx.shareMode.value && ctx.isAdmin.value
  ))
  const projectThumbnailUrl = computed(() => {
    const target = activeProject.value
    if (!target?.id || !target?.thumbnail_path) return ''
    return ctx.getProjectThumbnailUrl(target.id, target.thumbnail_path)
  })

  const team = useProjectTeamManagement({
    activeProject,
    currentProject: ctx.currentProject,
    shareMode: ctx.shareMode,
    canAssignShots: ctx.canAssignShots,
    canManageProjectTeam,
    loadProjects: ctx.loadProjects,
    refreshProjectContents: ctx.refreshProjectContents,
  })

  const tracker = useTrackerSettings({
    currentProject: ctx.currentProject,
    currentTracker: ctx.currentTracker,
    currentTrackerRef: ctx.currentTrackerRef,
    currentUser: ctx.currentUser,
    isAdmin: ctx.isAdmin,
    shareMode: ctx.shareMode,
    pendingShareId: ctx.pendingShareId,
    appIdentity: ctx.appIdentity,
    route: ctx.route,
    router: ctx.router,
    getShareCredential: ctx.getShareCredential,
    openDeliveryLogoPicker: ctx.openDeliveryLogoPicker,
  })

  function hydrateProjectDraft(project) {
    projectDraftTitle.value = project?.title || ''
    projectDraftDescription.value = project?.description || ''
    projectDraftDueDate.value = project?.due_date || ''
    projectDraftStatus.value = project?.status || 'not_started'
  }

  async function openProjectSettings(project = null) {
    const requestedProject = project || ctx.currentProject.value
    if (!requestedProject || ctx.shareMode.value || !ctx.isAdmin.value) return

    const targetProjectId = requestedProject.id || ctx.currentProject.value?.id
    if (!targetProjectId) return
    ctx.projectMenuOpen.value = null

    let targetProject = requestedProject
    try {
      const { data } = await api.get(`/api/projects/${targetProjectId}`)
      if (ctx.currentProject.value?.id === targetProjectId) {
        Object.assign(ctx.currentProject.value, data)
        targetProject = ctx.currentProject.value
      } else {
        const listProject = ctx.projects.value.find(projectItem => projectItem.id === targetProjectId)
        if (listProject) {
          Object.assign(listProject, data)
          targetProject = listProject
        } else {
          targetProject = data
        }
      }
    } catch (error) {
      console.warn('Failed to hydrate project settings target')
    }

    projectTarget.value = targetProject
    hydrateProjectDraft(targetProject)
    team.resetAddMemberDraft()
    projectModal.open()
    await team.loadOptions(true)
  }

  function closeProjectSettings() {
    projectModal.close()
    projectTarget.value = null
    team.resetAddMemberDraft()
  }

  async function saveProjectSettings() {
    const target = activeProject.value
    if (!target || !canEditActiveProject.value) return

    projectSaving.value = true
    try {
      const payload = {
        title: projectDraftTitle.value.trim(),
        description: projectDraftDescription.value,
        due_date: projectDraftDueDate.value || null,
        status: projectDraftStatus.value,
        thumbnail_path: target.thumbnail_path || null,
      }
      const { data } = await api.put(`/api/projects/${target.id}`, payload)
      if (data && typeof data === 'object') {
        Object.assign(target, data)
        if (ctx.currentProject.value?.id === data.id) Object.assign(ctx.currentProject.value, data)
        const listed = ctx.projects.value.find(project => project.id === data.id)
        if (listed) Object.assign(listed, data)
      } else {
        Object.assign(target, {
          title: payload.title,
          description: payload.description,
          due_date: payload.due_date,
          status: payload.status,
        })
      }
      hydrateProjectDraft(target)
      await ctx.loadProjects()
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to save project settings'))
    } finally {
      projectSaving.value = false
    }
  }

  async function loadStorageRoots() {
    if (!ctx.isAdmin.value) return
    try {
      const { data } = await api.get('/api/storage/roots')
      storageRoots.value = data || []
      if (!storageRoots.value.some(root => root.id === newProjectStorageRoot.value)) {
        newProjectStorageRoot.value = storageRoots.value.find(root => root.available && !root.read_only)?.id || storageRoots.value[0]?.id || ''
        newProjectStoragePath.value = null
      }
    } catch (error) {
      storageRoots.value = []
      console.warn('Failed to load project storage roots')
    }
  }

  async function openProjectStorage(project, mode = 'relocate') {
    if (!project || !ctx.isAdmin.value) return
    await loadStorageRoots()
    ctx.projectMenuOpen.value = null
    closeProjectSettings()
    storageTarget.value = project
    storageMode.value = mode
    storageModal.open()
  }

  function closeProjectStorage() {
    storageModal.close()
    storageTarget.value = null
  }

  async function handleProjectStorageUpdated(project) {
    if (!project?.id) return
    const listed = ctx.projects.value.find(item => item.id === project.id)
    if (listed) Object.assign(listed, project)
    if (ctx.currentProject.value?.id === project.id) {
      Object.assign(ctx.currentProject.value, project)
      await ctx.refreshProjectContents()
    }
  }

  function openDashboardSettings() {
    if (!ctx.currentPage.value || !tracker.canEdit.value) return
    dashboardDraftTitle.value = ctx.currentPage.value.title || ''
    dashboardDraftDescription.value = ctx.currentPage.value.description || ''
    dashboardModal.open()
  }

  async function saveDashboardSettings() {
    if (!ctx.currentPage.value || !dashboardDraftTitle.value.trim()) return
    dashboardSaving.value = true
    try {
      await ctx.savePage({
        ...ctx.clonePageDraft(),
        title: dashboardDraftTitle.value.trim(),
        description: dashboardDraftDescription.value,
      })
      dashboardDraftTitle.value = ctx.currentPage.value?.title || ''
      dashboardDraftDescription.value = ctx.currentPage.value?.description || ''
    } finally {
      dashboardSaving.value = false
    }
  }

  function openContextSettings() {
    if (ctx.currentTracker.value) return tracker.openSettings()
    if (ctx.currentPage.value) return openDashboardSettings()
    return openProjectSettings()
  }

  function closeAll() {
    closeProjectSettings()
    tracker.closeSettings()
    dashboardModal.close()
  }

  return Object.freeze({
    PROJECT_STATUS_OPTIONS,
    showProjectSettingsModal: projectModal.isOpen,
    showProjectStorageModal: storageModal.isOpen,
    showDashboardSettingsModal: dashboardModal.isOpen,
    projectSettingsTarget: projectTarget,
    projectSettingsSaving: projectSaving,
    projectSettingsDraftTitle: projectDraftTitle,
    projectSettingsDraftDescription: projectDraftDescription,
    projectSettingsDraftDueDate: projectDraftDueDate,
    projectSettingsDraftStatus: projectDraftStatus,
    activeProjectSettingsTarget: activeProject,
    canOpenProjectSettings,
    canEditActiveProjectSettings: canEditActiveProject,
    canManageActiveProjectTeam: canManageProjectTeam,
    projectSettingsThumbnailUrl: projectThumbnailUrl,
    projectStorageMode: storageMode,
    projectStorageTarget: storageTarget,
    projectStorageRoots: storageRoots,
    newProjectStorageRoot,
    newProjectStoragePath,
    dashboardSettingsSaving: dashboardSaving,
    dashboardSettingsDraftTitle: dashboardDraftTitle,
    dashboardSettingsDraftDescription: dashboardDraftDescription,
    projectTeamOptions: team.options,
    projectTeamLoading: team.loading,
    projectTeamSaving: team.saving,
    projectTeamAddUserId: team.addUserId,
    projectTeamAddRole: team.addRole,
    projectTeamMembers: team.members,
    assignmentCandidates: team.assignmentCandidates,
    showTrackerSettingsModal: tracker.showModal,
    trackerSettingsDraft: tracker.draft,
    trackerSettingsSaving: tracker.saving,
    trackerSettingsDeliveryLogoUploading: tracker.deliveryLogoUploading,
    canEditTrackerSettings: tracker.canEdit,
    canViewTrackerDetails: tracker.canViewDetails,
    trackerToolEnabledForContext: tracker.toolEnabledForContext,
    showTrackerBriefPreview: tracker.showBriefPreview,
    versionReviewEnabled: tracker.versionReviewEnabled,
    showTrackerDeliveryMode: tracker.showDeliveryMode,
    trackerDeliveryLinks: tracker.deliveryLinks,
    trackerDeliveryLogoUrl: tracker.deliveryLogoUrl,
    trackerDeliveryMessage: tracker.deliveryMessage,
    trackerDeliveryNotes: tracker.deliveryNotes,
    deliveryTeamName: tracker.deliveryTeamName,
    trackerSettingsDeliveryLogoUrl: tracker.settingsDeliveryLogoUrl,
    openProjectSettingsModal: openProjectSettings,
    openProjectSettings,
    closeProjectSettingsModal: closeProjectSettings,
    saveProjectSettings,
    loadProjectStorageRoots: loadStorageRoots,
    openProjectStorage,
    closeProjectStorage,
    handleProjectStorageUpdated,
    openTrackerSettingsModal: tracker.openSettings,
    closeTrackerSettingsModal: tracker.closeSettings,
    saveTrackerSettings: tracker.saveSettings,
    uploadTrackerSettingsDeliveryLogo: tracker.uploadDeliveryLogo,
    removeTrackerSettingsDeliveryLogo: tracker.removeDeliveryLogo,
    selectTrackerSettingsDeliveryLogoFromNas: tracker.selectDeliveryLogoFromNas,
    chooseTrackerSettingsDeliveryLogoFromNas: tracker.chooseDeliveryLogoFromNas,
    openTrackerSettingsDeliveryPreview: tracker.openDeliveryPreview,
    openDashboardSettingsModal: openDashboardSettings,
    closeDashboardSettingsModal: dashboardModal.close,
    saveDashboardSettings,
    openContextSettings,
    resetProjectTeamState: team.resetForProject,
    loadProjectTeamOptions: team.loadOptions,
    addProjectTeamMember: team.addMember,
    updateProjectTeamMemberRole: team.updateMemberRole,
    removeProjectTeamMember: team.removeMember,
    closeAll,
  })
}

export function provideProjectSettingsStore(store) {
  provide(projectSettingsStoreKey, store)
  return store
}

export function useProjectSettingsStore() {
  const store = inject(projectSettingsStoreKey, null)
  if (!store) throw new Error('Project settings store has not been provided')
  return store
}
