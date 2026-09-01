import { computed, ref } from 'vue'
import api, { getApiErrorDetail, getApiErrorMessage } from '../lib/api'
import { notify } from '../utils/toasts'

export function useProjectTeamManagement({
  activeProject,
  currentProject,
  shareMode,
  canAssignShots,
  canManageProjectTeam,
  loadProjects,
  refreshProjectContents,
}) {
  const options = ref([])
  const optionsProjectId = ref('')
  const loading = ref(false)
  const saving = ref(false)
  const addUserId = ref('')
  const addRole = ref('viewer')

  const members = computed(() => options.value.filter(candidate => candidate?.is_member))
  const assignmentCandidates = computed(() => options.value.filter(candidate => candidate?.id))

  function resetAddMemberDraft() {
    addUserId.value = ''
    addRole.value = 'viewer'
  }

  function resetForProject(projectId = '') {
    resetAddMemberDraft()
    if (optionsProjectId.value === projectId) return
    options.value = []
    optionsProjectId.value = ''
  }

  async function loadOptions(force = false) {
    const project = activeProject.value
    if (shareMode.value || !project) return []
    if (!canAssignShots.value && !canManageProjectTeam.value) {
      options.value = []
      optionsProjectId.value = project.id || ''
      return []
    }
    if (!force && optionsProjectId.value === project.id && options.value.length) return options.value

    loading.value = true
    try {
      const { data } = await api.get(`/api/horizons/projects/${project.id}/grant-candidates`)
      options.value = data.candidates || []
      optionsProjectId.value = project.id || ''
      return options.value
    } catch (error) {
      console.error('Failed to load project team options')
      options.value = []
      optionsProjectId.value = project.id || ''
      return []
    } finally {
      loading.value = false
    }
  }

  async function refreshProjectTeam(project) {
    await Promise.all([
      loadOptions(true),
      loadProjects(),
      currentProject.value?.id === project.id ? refreshProjectContents() : Promise.resolve(),
    ])
  }

  async function addMember() {
    const project = activeProject.value
    if (!canManageProjectTeam.value || !project || !addUserId.value) return
    saving.value = true
    try {
      await api.post(`/api/horizons/projects/${project.id}/grants`, {
        subject_type: 'user_id',
        subject_id: addUserId.value,
        role: addRole.value,
      })
      resetAddMemberDraft()
      await refreshProjectTeam(project)
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to add project member'))
    } finally {
      saving.value = false
    }
  }

  async function updateMemberRole(member, nextRole) {
    const project = activeProject.value
    if (!canManageProjectTeam.value || !project || !member?.id) return
    if (!['viewer', 'editor', 'owner'].includes(nextRole || '')) return
    if ((member.project_role || 'viewer') === nextRole) return

    saving.value = true
    try {
      await api.post(`/api/horizons/projects/${project.id}/grants`, {
        subject_type: 'user_id',
        subject_id: member.id,
        role: nextRole,
      })
      await refreshProjectTeam(project)
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to update project role'))
    } finally {
      saving.value = false
    }
  }

  async function removeMember(member) {
    const project = activeProject.value
    if (!canManageProjectTeam.value || !project || !member?.id) return
    if (!confirm(`Remove ${member.display_name || member.username} from this project?`)) return

    saving.value = true
    try {
      await api.delete(`/api/horizons/projects/${project.id}/members/${member.id}`)
      await refreshProjectTeam(project)
    } catch (error) {
      const detail = getApiErrorDetail(error)
      if (detail && typeof detail === 'object' && detail.code === 'member_has_assigned_shots') {
        const codes = Array.isArray(detail.assigned_shot_codes) && detail.assigned_shot_codes.length
          ? `\nAssigned shots: ${detail.assigned_shot_codes.join(', ')}`
          : ''
        notify(`Can't remove ${member.display_name || member.username || 'this member'} yet — ${detail.assigned_shot_count || 0} assigned shots still belong to them.${codes}`)
      } else {
        notify((typeof detail === 'string' && detail) || error?.message || 'Failed to remove project member')
      }
    } finally {
      saving.value = false
    }
  }

  return {
    options,
    loading,
    saving,
    addUserId,
    addRole,
    members,
    assignmentCandidates,
    resetAddMemberDraft,
    resetForProject,
    loadOptions,
    addMember,
    updateMemberRole,
    removeMember,
  }
}
