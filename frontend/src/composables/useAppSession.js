import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api, { getApiErrorMessage } from '../lib/api'
import {
  hasAppAccess,
  isAdminUser,
  isRestrictedProjectMember,
} from '../utils/accountAccess'
import { notify } from '../utils/toasts'

const AUTH_CACHE_TTL_MS = 45_000

export function useAppSession({
  shareMode,
  shareAllowDownload,
  activeModule,
  currentProject,
  loadFiles,
  loadProjects,
  onSetupComplete,
}) {
  const router = useRouter()

  const currentUser = ref(null)
  const showLogin = ref(false)
  const loginUsername = ref('')
  const loginPassword = ref('')
  const loginError = ref('')
  const showChangePassword = ref(false)
  const passwordForm = ref({ current: '', new: '', confirm: '' })
  const passwordError = ref('')
  const setupRequired = ref(false)
  const setupChecked = ref(false)
  const setupStatus = ref(null)
  const setupSubmitting = ref(false)
  const setupError = ref('')
  const setupForm = ref({
    setup_token: '',
    team_name: 'My studio',
    website_url: '',
    username: 'admin',
    display_name: 'Administrator',
    password: '',
    confirm: '',
  })

  let authCacheExpiresAt = 0
  let lastAuthOk = false
  let authCheckInFlight = null
  let setupCheckInFlight = null

  function setLoginUsername(value) {
    loginUsername.value = value
  }

  function setLoginPassword(value) {
    loginPassword.value = value
  }

  function closeChangePassword() {
    showChangePassword.value = false
  }

  function openChangePassword() {
    showChangePassword.value = true
  }

  function setSetupField(field, value) {
    if (!(field in setupForm.value)) return
    setupForm.value = { ...setupForm.value, [field]: value }
  }

  const isAdmin = computed(() => isAdminUser(currentUser.value))

  const canAccessFileBrowser = computed(() => {
    if (shareMode.value) return true
    if (!currentUser.value) return false
    if (isAdmin.value) return true
    return hasAppAccess(currentUser.value, 'file_browser')
  })

  const canAccessProjectManager = computed(() => {
    if (shareMode.value && activeModule.value === 'projects') return true
    if (!currentUser.value) return false
    if (isAdmin.value) return true
    return hasAppAccess(currentUser.value, 'project_manager')
  })

  const ROLE_RANK = { viewer: 1, editor: 2, owner: 3, admin: 4 }
  const currentProjectAccessRole = computed(() => {
    if (isAdmin.value) return 'admin'
    return currentProject?.value?.access_role || null
  })
  const projectRoleMeets = requiredRole => ROLE_RANK[currentProjectAccessRole.value] >= ROLE_RANK[requiredRole]

  const canEditProject = computed(() => isAdmin.value || projectRoleMeets('editor'))
  const isRestrictedMember = computed(() => isRestrictedProjectMember(currentUser.value))
  const canManageProjectContent = computed(() => (
    !shareMode.value
    && hasAppAccess(currentUser.value, 'manage_project_content')
    && projectRoleMeets('editor')
  ))
  const canCreateProjects = computed(() => hasAppAccess(currentUser.value, 'create_projects'))
  const canDeleteProjects = computed(() => hasAppAccess(currentUser.value, 'delete_projects'))
  const canManageMembers = computed(() => hasAppAccess(currentUser.value, 'manage_members'))
  const projectFilesMutable = computed(() => !currentProject?.value?.storage_read_only)
  const canAddShots = computed(() => projectFilesMutable.value && !shareMode.value && (isAdmin.value || canManageProjectContent.value))
  const canEditShotName = computed(() => projectFilesMutable.value && !shareMode.value && (isAdmin.value || canManageProjectContent.value))
  const canEditDescription = computed(() => projectFilesMutable.value && !shareMode.value && (isAdmin.value || canManageProjectContent.value))
  const canDeleteShots = computed(() => projectFilesMutable.value && !shareMode.value && !isRestrictedMember.value && (isAdmin.value || projectRoleMeets('owner')))
  const canAddVersions = computed(() => projectFilesMutable.value && !shareMode.value && (isAdmin.value || projectRoleMeets('editor')))
  const canManageVersionPublication = computed(() => projectFilesMutable.value && !shareMode.value && (isAdmin.value || projectRoleMeets('owner')))
  const showShotDownloads = computed(() => !shareMode.value || shareAllowDownload.value)

  async function changeMyPassword() {
    passwordError.value = ''
    if (passwordForm.value.new !== passwordForm.value.confirm) {
      passwordError.value = 'Passwords do not match'
      return
    }
    try {
      await api.put('/api/me/password', {
        current_password: passwordForm.value.current,
        new_password: passwordForm.value.new,
      })
      showChangePassword.value = false
      passwordForm.value = { current: '', new: '', confirm: '' }
      notify('Password changed successfully!')
    } catch (e) {
      passwordError.value = getApiErrorMessage(e, 'Failed to change password')
    }
  }

  async function checkAuth(force = false) {
    const now = Date.now()
    if (!force && now < authCacheExpiresAt) {
      return lastAuthOk
    }
    if (authCheckInFlight) return authCheckInFlight

    authCheckInFlight = (async () => {
      try {
        const { data } = await api.get('/api/auth/check')
        currentUser.value = data
        lastAuthOk = true
        return true
      } catch {
        currentUser.value = null
        lastAuthOk = false
        return false
      } finally {
        authCacheExpiresAt = Date.now() + AUTH_CACHE_TTL_MS
        authCheckInFlight = null
      }
    })()

    return authCheckInFlight
  }

  async function checkSetupStatus(force = false) {
    if (!force && setupChecked.value) {
      return setupRequired.value
    }
    if (setupCheckInFlight) return setupCheckInFlight

    setupCheckInFlight = (async () => {
      try {
        const { data } = await api.get('/api/setup/status')
        setupStatus.value = data
        setupRequired.value = data?.setup_required === true
        setupChecked.value = true
        return setupRequired.value
      } catch {
        setupRequired.value = false
        setupChecked.value = true
        return false
      } finally {
        setupCheckInFlight = null
      }
    })()

    return setupCheckInFlight
  }

  async function completeSetup() {
    setupError.value = ''
    const form = setupForm.value
    if (form.password !== form.confirm) {
      setupError.value = 'Passwords do not match'
      return
    }
    if (String(form.password || '').length < 8) {
      setupError.value = 'Password must be at least 8 characters'
      return
    }

    setupSubmitting.value = true
    try {
      const { data } = await api.post('/api/setup/complete', {
        setup_token: form.setup_token || null,
        team_name: form.team_name,
        website_url: form.website_url,
        username: form.username,
        display_name: form.display_name,
        password: form.password,
      })
      currentUser.value = data.user
      lastAuthOk = true
      authCacheExpiresAt = Date.now() + AUTH_CACHE_TTL_MS
      setupRequired.value = false
      setupChecked.value = true
      setupStatus.value = data.status || { setup_required: false }
      showLogin.value = false
      setupForm.value = {
        setup_token: '',
        team_name: data.identity?.team_name || form.team_name || 'My studio',
        website_url: data.identity?.website_url || form.website_url || '',
        username: data.user?.username || form.username || 'admin',
        display_name: data.user?.display_name || form.display_name || 'Administrator',
        password: '',
        confirm: '',
      }
      onSetupComplete?.(data)

      activeModule.value = 'home'
      await loadProjects()
      router.push({ name: 'home' })
    } catch (e) {
      setupError.value = getApiErrorMessage(e, 'Setup failed')
    } finally {
      setupSubmitting.value = false
    }
  }

  async function login() {
    loginError.value = ''
    try {
      const { data } = await api.post('/api/login', {
        username: loginUsername.value,
        password: loginPassword.value,
      })
      currentUser.value = data
      lastAuthOk = true
      authCacheExpiresAt = Date.now() + AUTH_CACHE_TTL_MS
      showLogin.value = false
      loginUsername.value = ''
      loginPassword.value = ''

      const canOpenProjects = data.role === 'admin' || data.app_access?.project_manager === true
      const canOpenFiles = data.role === 'admin' || data.app_access?.file_browser === true

      loadProjects()
      activeModule.value = 'home'
      router.push({ name: 'home' })

      if (canOpenProjects && canOpenFiles && data.role === 'admin') {
        loadFiles('')
      }
    } catch (e) {
      loginError.value = getApiErrorMessage(e, 'Login failed')
      if (e.response?.status === 409) {
        await checkSetupStatus(true)
        showLogin.value = false
      }
    }
  }

  async function logout() {
    try {
      await api.post('/api/logout')
    } catch {
      // Server logout failed; clear local state anyway.
    }
    currentUser.value = null
    lastAuthOk = false
    authCacheExpiresAt = 0
    showLogin.value = true
  }

  return {
    currentUser,
    showLogin,
    loginUsername,
    loginPassword,
    loginError,
    showChangePassword,
    passwordForm,
    passwordError,
    setupRequired,
    setupStatus,
    setupSubmitting,
    setupError,
    setupForm,
    isAdmin,
    canAccessFileBrowser,
    canAccessProjectManager,
    canEditProject,
    canManageProjectContent,
    canCreateProjects,
    canDeleteProjects,
    canManageMembers,
    isRestrictedMember,
    canAddShots,
    canEditShotName,
    canEditDescription,
    canDeleteShots,
    canAddVersions,
    canManageVersionPublication,
    showShotDownloads,
    setLoginUsername,
    setLoginPassword,
    setSetupField,
    openChangePassword,
    closeChangePassword,
    changeMyPassword,
    checkAuth,
    checkSetupStatus,
    completeSetup,
    login,
    logout,
  }
}
