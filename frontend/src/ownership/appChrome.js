import { computed, inject, provide, ref, watch } from 'vue'

export const appChromeStoreKey = Symbol('vueio.appChromeStore')

export function createAppChromeStore({
  route,
  router,
  activeModule,
  showMainContent,
  session,
  share,
  dismissCurrentMedia,
  focusGlobalSearch,
  windowTarget = globalThis.window,
}) {
  const enableLowFx = ref(false)
  const isMobile = ref(false)
  const mobileNavOpen = ref(false)
  const userMenuOpen = ref(false)

  function updateLowFxMode() {
    if (!windowTarget) return
    const reducedMotion = windowTarget.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    const narrowViewport = windowTarget.matchMedia?.('(max-width: 1100px)')?.matches
    enableLowFx.value = Boolean(reducedMotion || narrowViewport)
  }

  function handleViewportResize() {
    if (!windowTarget) return
    isMobile.value = windowTarget.innerWidth < 768
    if (!isMobile.value) mobileNavOpen.value = false
  }

  function closeMobileNav() {
    mobileNavOpen.value = false
  }

  function openMobileNav({ focusSearch = false } = {}) {
    if (!isMobile.value || share.shareMode.value || !showMainContent.value || !session.currentUser.value) return
    mobileNavOpen.value = true
    userMenuOpen.value = false
    if (focusSearch) focusGlobalSearch?.()
  }

  function toggleMobileNav() {
    if (mobileNavOpen.value) closeMobileNav()
    else openMobileNav()
  }

  function toggleUserMenu() {
    userMenuOpen.value = !userMenuOpen.value
  }

  function handleGlobalKeydown(event) {
    const key = (event.key || '').toLowerCase()
    if (event.key === 'Escape' && mobileNavOpen.value) {
      event.preventDefault()
      closeMobileNav()
      return
    }
    if (!(event.metaKey || event.ctrlKey) || key !== 'k') return
    if (share.shareMode.value || !showMainContent.value || session.currentUser.value?.role !== 'admin') return
    event.preventDefault()
    if (isMobile.value) openMobileNav({ focusSearch: true })
    else focusGlobalSearch?.()
  }

  function goToProjects() {
    dismissCurrentMedia?.()
    if (route.path !== '/projects') router.push('/projects')
  }

  function goToHome() {
    dismissCurrentMedia?.()
    if (route.path !== '/') router.push('/')
  }

  function goToSettings(tab = '') {
    dismissCurrentMedia?.()
    const query = tab ? { tab } : {}
    if (route.path !== '/settings' || (route.query?.tab || '') !== tab) {
      router.push({ path: '/settings', query })
    }
  }

  const showDesktopSidebar = computed(() => Boolean(session.currentUser.value && !share.shareMode.value && !isMobile.value))
  const showMobileNavigation = computed(() => Boolean(
    showMainContent.value && session.currentUser.value && !share.shareMode.value && isMobile.value,
  ))

  watch([isMobile, share.shareMode, showMainContent, session.currentUser], ([mobile, inShareMode, hasMainContent, user]) => {
    if (!mobile || inShareMode || !hasMainContent || !user) closeMobileNav()
  })

  handleViewportResize()

  return {
    activeModule,
    showMainContent,
    enableLowFx,
    isMobile,
    mobileNavOpen,
    userMenuOpen,
    showDesktopSidebar,
    showMobileNavigation,
    updateLowFxMode,
    handleViewportResize,
    closeMobileNav,
    openMobileNav,
    toggleMobileNav,
    toggleUserMenu,
    handleGlobalKeydown,
    goToHome,
    goToProjects,
    goToSettings,
  }
}

export function provideAppChromeStore(store) {
  provide(appChromeStoreKey, store)
  return store
}

export function useAppChromeStore() {
  const store = inject(appChromeStoreKey, null)
  if (!store) throw new Error('App chrome store has not been provided')
  return store
}
