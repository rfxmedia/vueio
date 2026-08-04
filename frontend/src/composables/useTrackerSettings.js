import { computed, ref, watch } from 'vue'
import api, { buildShareCredentialQuery, getApiErrorMessage, resolveAccessEndpoint } from '../lib/api'
import { DEFAULT_DELIVERY_MESSAGE, normalizeDeliveryLinks, normalizeTrackerSettings, trackerToolEnabledForContext as trackerToolVisibleForContext } from '../utils/trackerSettings'
import { notify } from '../utils/toasts'
import { useModal } from './useModal'

function createDeliveryPreviewToken() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

export function useTrackerSettings({
  currentProject,
  currentTracker,
  currentTrackerRef,
  currentUser,
  isAdmin,
  shareMode,
  pendingShareId,
  appIdentity,
  route,
  router,
  getShareCredential,
  openDeliveryLogoPicker,
}) {
  const { isOpen: showModal, open: openModal, close: closeModal } = useModal()
  const draft = ref(normalizeTrackerSettings())
  const saving = ref(false)
  const deliveryLogoUploading = ref(false)
  const deliveryPreviewPayload = ref(null)

  const canEdit = computed(() => (
    !shareMode.value &&
    !!currentProject.value &&
    isAdmin.value
  ))

  function toolEnabledForContext(tracker, toolKey) {
    return trackerToolVisibleForContext(tracker, toolKey, {
      shareMode: shareMode.value,
      currentUser: currentUser.value,
      accessRole: isAdmin.value ? 'admin' : currentProject.value?.access_role,
    })
  }

  const canViewDetails = computed(() => toolEnabledForContext(currentTracker.value, 'details'))
  const showBriefPreview = computed(() => normalizeTrackerSettings(currentTracker.value?.settings).brief_preview.enabled)
  const versionReviewEnabled = computed(() => normalizeTrackerSettings(currentTracker.value?.settings).version_review.enabled)
  const showDeliveryMode = computed(() => (
    Boolean(currentTracker.value) &&
    (Boolean(deliveryPreviewPayload.value) || (shareMode.value && toolEnabledForContext(currentTracker.value, 'delivery')))
  ))
  const deliverySettingsSource = computed(() => deliveryPreviewPayload.value?.settings || currentTracker.value?.settings)
  const deliveryTeamName = computed(() => appIdentity.value.team_name || 'Vue')
  const inheritedDeliveryMessage = computed(() => `Thanks for reviewing with ${deliveryTeamName.value}.`)
  const legacyInheritedDeliveryMessages = computed(() => new Set([
    '',
    DEFAULT_DELIVERY_MESSAGE,
    `Thanks for choosing ${deliveryTeamName.value}.`,
    `Thank you for choosing ${deliveryTeamName.value}.`,
  ]))
  const deliveryMessage = computed(() => {
    const message = normalizeTrackerSettings(deliverySettingsSource.value, { preserveDeliveryMessage: true }).delivery.message.trim()
    return legacyInheritedDeliveryMessages.value.has(message) ? inheritedDeliveryMessage.value : message
  })
  const deliveryNotes = computed(() => (
    normalizeTrackerSettings(deliverySettingsSource.value, { preserveDeliveryMessage: true }).delivery.notes.trim()
  ))
  const deliveryLinks = computed(() => normalizeDeliveryLinks([
    ...(appIdentity.value.website_url ? [{ label: 'Website', url: appIdentity.value.website_url }] : []),
    ...normalizeTrackerSettings(deliverySettingsSource.value, { preserveDeliveryMessage: true }).delivery.links,
  ]))

  function getDeliveryLogoUrl(tracker, settingsSource = null) {
    const delivery = normalizeTrackerSettings(settingsSource ?? tracker?.settings, { preserveDeliveryMessage: true }).delivery
    if (!currentProject.value?.id || !tracker || !delivery.logo_upload_name) return appIdentity.value.logo_url || ''

    const trackerRef = tracker.id || tracker.slug || tracker.name
    const shareId = shareMode.value ? pendingShareId.value : null
    const endpoint = resolveAccessEndpoint({
      shareId,
      shared: id => `/api/projects/shared/${id}/tracker/${encodeURIComponent(trackerRef)}/delivery-logo`,
      authenticated: `/api/projects/${encodeURIComponent(currentProject.value.id)}/trackers/${encodeURIComponent(trackerRef)}/delivery-logo`,
    })
    return `${endpoint}${buildShareCredentialQuery(
      { v: delivery.logo_upload_name },
      shareId ? getShareCredential({ shareId }) : {},
    )}`
  }

  const deliveryLogoUrl = computed(() => getDeliveryLogoUrl(currentTracker.value, deliverySettingsSource.value))
  const settingsDeliveryLogoUrl = computed(() => getDeliveryLogoUrl(currentTracker.value, draft.value))

  function openSettings() {
    if (!currentTracker.value || !canEdit.value) return
    draft.value = normalizeTrackerSettings(currentTracker.value.settings, { preserveDeliveryMessage: true })
    openModal()
  }

  async function saveSettings() {
    if (!currentProject.value?.id || !currentTrackerRef.value || !canEdit.value) return
    saving.value = true
    try {
      const settings = normalizeTrackerSettings(draft.value)
      const { data } = await api.put(
        `/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef.value)}`,
        { settings },
      )
      Object.assign(currentTracker.value, data, { settings: normalizeTrackerSettings(data?.settings || settings) })
      draft.value = normalizeTrackerSettings(currentTracker.value.settings, { preserveDeliveryMessage: true })
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to save tracker settings'))
    } finally {
      saving.value = false
    }
  }

  function replaceDraftFromDeliveryLogo(settings) {
    if (!settings || !currentTracker.value) return
    const currentDraft = normalizeTrackerSettings(draft.value, { preserveDeliveryMessage: true })
    const next = normalizeTrackerSettings(settings, { preserveDeliveryMessage: true })
    draft.value = {
      ...next,
      delivery: {
        ...next.delivery,
        message: currentDraft.delivery.message,
        notes: currentDraft.delivery.notes,
        links: currentDraft.delivery.links,
      },
    }
    currentTracker.value.settings = normalizeTrackerSettings(settings)
  }

  function deliveryLogoEndpoint(suffix = '') {
    return `/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef.value)}/delivery-logo${suffix}`
  }

  async function uploadDeliveryLogo(file) {
    if (!file || !canEdit.value) return
    deliveryLogoUploading.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await api.post(deliveryLogoEndpoint(), formData)
      replaceDraftFromDeliveryLogo(data?.settings)
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to upload delivery logo'))
    } finally {
      deliveryLogoUploading.value = false
    }
  }

  async function removeDeliveryLogo() {
    if (!canEdit.value) return
    deliveryLogoUploading.value = true
    try {
      const { data } = await api.delete(deliveryLogoEndpoint())
      replaceDraftFromDeliveryLogo(data?.settings)
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to remove delivery logo'))
    } finally {
      deliveryLogoUploading.value = false
    }
  }

  async function selectDeliveryLogoFromNas(item) {
    if (!item?.path || !canEdit.value) return
    deliveryLogoUploading.value = true
    try {
      const { data } = await api.post(deliveryLogoEndpoint('/select'), { source_path: item.path })
      replaceDraftFromDeliveryLogo(data?.settings)
    } catch (error) {
      notify(getApiErrorMessage(error, 'Failed to choose delivery logo'))
    } finally {
      deliveryLogoUploading.value = false
    }
  }

  function chooseDeliveryLogoFromNas() {
    if (canEdit.value) openDeliveryLogoPicker()
  }

  function openDeliveryPreview() {
    if (!currentProject.value?.id || !currentTracker.value?.name) return
    const token = createDeliveryPreviewToken()
    const settings = normalizeTrackerSettings(draft.value, { preserveDeliveryMessage: true })
    localStorage.setItem(`vueio-delivery-preview:${token}`, JSON.stringify({
      projectId: currentProject.value.id,
      trackerId: currentTrackerRef.value,
      trackerName: currentTracker.value.name,
      expiresAt: Date.now() + (10 * 60 * 1000),
      settings: normalizeTrackerSettings({
        ...settings,
        delivery: { ...settings.delivery, enabled: true },
      }, { preserveDeliveryMessage: true }),
    }))
    const previewRoute = router.resolve({
      path: route.path,
      query: { ...route.query, deliveryPreview: token },
    })
    window.open(previewRoute.href, '_blank', 'noopener')
  }

  function hydrateDeliveryPreview() {
    const token = typeof route.query.deliveryPreview === 'string' ? route.query.deliveryPreview : ''
    if (!token || !currentProject.value?.id || !currentTracker.value?.name) {
      deliveryPreviewPayload.value = null
      return
    }

    const storageKey = `vueio-delivery-preview:${token}`
    let payload
    try {
      payload = JSON.parse(localStorage.getItem(storageKey) || 'null')
    } catch {}

    const isCurrentPreview = (
      payload?.projectId === currentProject.value.id &&
      (payload?.trackerId ? payload.trackerId === currentTrackerRef.value : payload?.trackerName === currentTracker.value.name) &&
      Number(payload?.expiresAt || 0) > Date.now()
    )

    if (!isCurrentPreview) {
      deliveryPreviewPayload.value = null
      if (payload && Number(payload.expiresAt || 0) <= Date.now()) localStorage.removeItem(storageKey)
      return
    }

    deliveryPreviewPayload.value = {
      ...payload,
      settings: normalizeTrackerSettings(payload.settings, { preserveDeliveryMessage: true }),
    }
    localStorage.removeItem(storageKey)
  }

  watch(
    [() => route.query.deliveryPreview, () => currentProject.value?.id, () => currentTracker.value?.name],
    hydrateDeliveryPreview,
    { immediate: true },
  )

  return {
    showModal,
    draft,
    saving,
    deliveryLogoUploading,
    canEdit,
    canViewDetails,
    toolEnabledForContext,
    showBriefPreview,
    versionReviewEnabled,
    showDeliveryMode,
    deliveryTeamName,
    deliveryMessage,
    deliveryNotes,
    deliveryLinks,
    deliveryLogoUrl,
    settingsDeliveryLogoUrl,
    openSettings,
    closeSettings: closeModal,
    saveSettings,
    uploadDeliveryLogo,
    removeDeliveryLogo,
    selectDeliveryLogoFromNas,
    chooseDeliveryLogoFromNas,
    openDeliveryPreview,
  }
}
