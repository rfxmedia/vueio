<template>
  <aside v-if="showDesktopSidebar" class="mini-sidebar">
    <button class="sidebar-logo" type="button" @click="activateNav('go-to-home')" aria-label="Go home">
      <span class="logo-mark">V</span>
    </button>

    <nav class="sidebar-nav" aria-label="Primary">
      <button
        v-for="item in navItems"
        :key="item.key"
        class="sidebar-item"
        :class="{ active: activeModule === item.module }"
        :aria-current="activeModule === item.module ? 'page' : undefined"
        :data-tooltip="item.label"
        :title="item.label"
        type="button"
        @click="activateNav(item.action)"
      >
        <svg class="icon"><use :href="item.icon"/></svg>
        <span class="sidebar-item-label">{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-bottom">
      <button
        v-if="updateAvailable"
        class="sidebar-item sidebar-update"
        type="button"
        :aria-label="`Vueio update available: ${latestVersion}`"
        :data-tooltip="`${latestVersion} available`"
        :title="`${latestVersion} available`"
        @click="openUpdates"
      >
        <svg class="icon"><use href="#icon-download" /></svg>
        <span class="sidebar-update-dot" aria-hidden="true"></span>
      </button>
    </div>
  </aside>

  <AppNavigator v-if="showNavigatorToggle" :collapsed="!navigatorOpen" />

  <transition name="v-overlay-fade">
    <button
      v-if="showMobileNavigation && mobileNavOpen"
      class="mobile-nav-backdrop"
      type="button"
      aria-label="Close navigation"
      @click="closeMobileNav"
    ></button>
  </transition>

  <aside
    v-if="showMobileNavigation"
    class="mobile-nav-drawer"
    :class="{ 'is-open': mobileNavOpen }"
    :aria-hidden="mobileNavOpen ? undefined : 'true'"
    :inert="mobileNavOpen ? undefined : ''"
    @click.stop
  >
    <div class="mobile-nav-shell">
      <div class="mobile-nav-header">
        <button class="mobile-nav-brand" type="button" @click="activateNav('go-to-home')">
          <span class="mobile-nav-brand-mark">
            <span class="logo-mark">V</span>
          </span>
          <div class="mobile-nav-brand-copy">
            <span class="mobile-nav-brand-title">vue.io</span>
            <span class="mobile-nav-brand-subtitle">Horizons workspace</span>
          </div>
        </button>
        <button class="v-btn v-btn-quiet v-btn-icon mobile-nav-close" type="button" aria-label="Close navigation" @click="closeMobileNav">
          <svg class="icon"><use href="#icon-close"/></svg>
        </button>
      </div>

      <div class="mobile-nav-body">
        <section class="mobile-nav-section">
          <div class="mobile-nav-section-label">Search</div>
          <div class="mobile-nav-search-shell">
            <slot v-if="mobileNavOpen" name="search" />
          </div>
        </section>

        <section class="mobile-nav-section">
          <div class="mobile-nav-section-label">Navigation</div>
          <nav class="mobile-nav-list" aria-label="Mobile primary">
            <button
              v-for="item in navItems"
              :key="`mobile-${item.key}`"
              class="mobile-nav-item"
              :class="{ active: activeModule === item.module }"
              :aria-current="activeModule === item.module ? 'page' : undefined"
              type="button"
              @click="activateNav(item.action)"
            >
              <span class="mobile-nav-item-icon">
                <svg class="icon"><use :href="item.icon"/></svg>
              </span>
              <span class="mobile-nav-item-copy">
                <span class="mobile-nav-item-label">{{ item.label }}</span>
                <span v-if="activeModule === item.module" class="mobile-nav-item-state">Current</span>
              </span>
            </button>
          </nav>
        </section>

        <section v-if="mobileNavOpen && hasNavigator" class="mobile-nav-section">
          <div class="mobile-nav-section-label">Jump to</div>
          <AppNavigator variant="drawer" @navigate="closeMobileNav" />
        </section>

        <section v-if="updateAvailable" class="mobile-nav-section">
          <div class="mobile-nav-section-label">Vueio</div>
          <button class="mobile-nav-item mobile-nav-update" type="button" @click="openUpdates">
            <span class="mobile-nav-item-icon">
              <svg class="icon"><use href="#icon-download" /></svg>
            </span>
            <span class="mobile-nav-item-copy">
              <span class="mobile-nav-item-label">Update available</span>
              <span class="mobile-nav-item-state">{{ latestVersion }}</span>
            </span>
            <svg class="icon mobile-nav-update-arrow"><use href="#icon-chevron-right" /></svg>
          </button>
        </section>

        <section class="mobile-nav-section mobile-nav-account" v-if="currentUser">
          <div class="mobile-nav-section-label">Signed In</div>
          <div class="mobile-nav-account-card">
            <span class="mobile-nav-account-mark" :style="userIdentityStyle">{{ userInitial }}</span>
            <div class="mobile-nav-account-copy">
              <strong>{{ currentUser.display_name }}</strong>
              <span>{{ userRoleLabel }}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </aside>

  <div class="main-wrapper">
    <header
      class="unified-nav"
      aria-label="Workspace navigation"
      :class="{
        'no-sidebar': !showDesktopSidebar,
        'in-tracker': currentTracker && !currentMedia,
        'in-media': !!currentMedia,
        'has-media-sequence': !!currentMedia && showMediaSequenceNav,
      }"
    >
      <div class="nav-left">
        <button
          v-if="showMobileNavigation"
          class="v-btn v-btn-quiet v-btn-icon nav-menu-toggle"
          :class="{ active: mobileNavOpen }"
          type="button"
          :aria-label="mobileNavOpen ? 'Close navigation' : 'Open navigation'"
          :aria-expanded="mobileNavOpen ? 'true' : 'false'"
          @click="mobileNavOpen ? closeMobileNav() : toggleMobileNav()"
        >
          <svg class="icon"><use href="#icon-menu"/></svg>
        </button>

        <button
          v-if="showNavigatorToggle"
          class="v-btn v-btn-quiet v-btn-icon nav-navigator-toggle"
          :class="{ active: navigatorOpen }"
          type="button"
          :aria-label="navigatorOpen ? 'Hide quick navigation' : 'Show quick navigation'"
          :aria-expanded="navigatorOpen ? 'true' : 'false'"
          :title="navigatorOpen ? 'Hide quick navigation' : 'Show quick navigation'"
          @click="toggleNavigator"
        >
          <svg class="icon"><use href="#icon-sidebar"/></svg>
        </button>

        <button v-if="canGoBack" class="v-btn v-btn-quiet v-btn-icon nav-back" type="button" aria-label="Go back" @click="goBack">
          <svg class="icon"><use href="#icon-back"/></svg>
        </button>

        <div class="nav-context">
          <div v-if="shareMode && showMainContent" class="nav-brand">
            <span class="logo-v small">V</span>
            <span class="v-status v-status-active share-badge">Shared</span>
          </div>

          <span v-else-if="currentMedia" class="nav-media-name">{{ currentMedia.name }}</span>

          <template v-else-if="!shareMode && currentUser">
            <h1 class="nav-title">
              <template v-if="activeModule === 'files'">
                <span v-if="currentPath">{{ breadcrumbs[breadcrumbs.length - 1]?.name || 'Files' }}</span>
                <span v-else>Files</span>
              </template>
              <template v-else-if="activeModule === 'home'">Home</template>
              <template v-else-if="activeModule === 'projects'">
                <span v-if="currentTracker">{{ currentTracker.name }}</span>
                <span v-else-if="currentProject">{{ currentProject.title }}</span>
                <span v-else>Projects</span>
                <span v-if="currentTracker && trackerSaving" class="save-indicator saving" title="Saving changes...">
                  <svg class="icon spinning"><use href="#icon-loader"/></svg>
                </span>
                <span v-else-if="currentTracker && hasPendingChanges" class="save-indicator pending" title="Unsaved changes">
                  <svg class="icon"><use href="#icon-cloud"/></svg>
                </span>
              </template>
              <template v-else-if="activeModule === 'settings'">Settings</template>
            </h1>

            <nav v-if="activeModule === 'files' && currentPath" class="nav-breadcrumbs">
              <template v-for="(crumb, i) in breadcrumbTrail" :key="crumb.path || i">
                <span v-if="i > 0" class="crumb-sep">/</span>
                <span class="crumb" @click="navigateTo(crumb.path)">{{ crumb.name }}</span>
              </template>
            </nav>
          </template>
        </div>

        <div v-if="currentMedia" class="nav-left-trailing">
          <slot name="nav-left-trailing" />
        </div>
      </div>

      <div v-if="showMediaSequenceNav && isMobile" class="nav-center nav-center-overlay">
        <slot name="nav-center" />
      </div>

      <div v-else-if="shareMode && showMainContent && !currentMedia" class="nav-center nav-center-overlay share-origin-center">
        <span class="v-status v-status-active share-origin-badge" :title="shareOriginLabel">
          <span class="share-origin-badge__dot" aria-hidden="true"></span>
          <span class="share-origin-badge__copy">{{ shareOriginLabel }}</span>
        </span>
      </div>

      <div v-else-if="!isMobile && !currentMedia" class="nav-center nav-center-search">
        <slot name="search" />
      </div>

      <div class="nav-right" role="group" aria-label="Workspace utilities">
        <slot v-if="showMediaSequenceNav && !isMobile" name="nav-center" />

        <button
          v-if="canShareFromNav && !shareMode"
          class="v-btn v-btn-quiet v-btn-icon nav-share-action"
          type="button"
          aria-label="Share"
          @click="shareFromNav"
        >
          <svg class="icon"><use href="#icon-share"/></svg>
        </button>

        <button
          v-if="currentMedia && (!shareMode || shareAllowDownload)"
          class="v-btn v-btn-quiet v-btn-icon"
          type="button"
          aria-label="Download"
          @click="downloadCurrentMedia"
        >
          <svg class="icon"><use href="#icon-download"/></svg>
        </button>

        <GlobalActivityTray
          v-if="currentUser && !shareMode"
          class="nav-account-activity"
        >
          <template #trigger="{ open, unreadCount, unreadLabel, triggerAriaLabel, panelId, toggle }">
            <button
              class="v-btn v-btn-quiet v-btn-icon user-avatar-btn"
              :class="{ 'has-unread': unreadCount > 0 }"
              :style="userIdentityStyle"
              type="button"
              aria-haspopup="dialog"
              :aria-expanded="open ? 'true' : 'false'"
              :aria-controls="open ? panelId : undefined"
              :aria-label="`Account and ${triggerAriaLabel.toLowerCase()}`"
              title="Account and notifications"
              @click.stop="toggle"
            >
              <span aria-hidden="true">{{ userInitial }}</span>
              <span v-if="unreadCount > 0" class="user-activity-badge" aria-hidden="true">{{ unreadLabel }}</span>
            </button>
          </template>

          <template #footer="{ close }">
            <footer class="nav-account-panel-footer">
              <div class="nav-account-panel-identity">
                <strong class="v-truncate">{{ currentUser.display_name }}</strong>
                <span>{{ userRoleLabel }}</span>
              </div>
              <div class="nav-account-panel-actions">
                <button class="v-btn v-btn-quiet v-btn-sm" type="button" @click="openChangePassword(close)">
                  <svg class="icon"><use href="#icon-edit"/></svg>
                  <span>Change password</span>
                </button>
                <button class="v-btn v-btn-quiet v-btn-sm" type="button" @click="signOut(close)">
                  <svg class="icon"><use href="#icon-back"/></svg>
                  <span>Sign out</span>
                </button>
              </div>
            </footer>
          </template>
        </GlobalActivityTray>

      </div>
    </header>

    <slot />
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import AppNavigator from './AppNavigator.vue'
import GlobalActivityTray from './GlobalActivityTray.vue'
import { useContextNavigator } from '../../composables/useContextNavigator'
import { useProjectTrackerSelectionStore } from '../../ownership/projectTrackerSelection'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useAppChromeStore } from '../../ownership/appChrome'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useNavigationStore } from '../../ownership/navigation'
import { useShareManagementStore } from '../../ownership/shareManagement'
import { useTrackerStore } from '../../ownership/tracker'
import { useViewerStore } from '../../ownership/viewer'
import { useUpdateStatusStore } from '../../ownership/updateStatus'
import { identityColorStyle } from '../../utils/semanticColors'

const { currentProject, currentTracker } = useProjectTrackerSelectionStore()
const { currentUser, canAccessFileBrowser, openChangePassword: openSessionChangePassword, logout } = useSessionAuthStore()
const { shareMode, shareAllowDownload, shareRequestFiles } = useShareAccessContext()
const shareOriginLabel = computed(() => shareRequestFiles.value ? 'File request' : 'Shared review')
const {
  activeModule,
  showMainContent,
  isMobile,
  mobileNavOpen,
  showDesktopSidebar,
  showMobileNavigation,
  closeMobileNav,
  toggleMobileNav,
  goToHome,
  goToProjects,
  goToSettings,
} = useAppChromeStore()
const { canGoBack, goBack } = useNavigationStore()
const fileBrowser = useFileBrowserStore().browser
const { breadcrumbs, currentPath, navigateTo, goToFiles } = fileBrowser
const viewerStore = useViewerStore()
const { currentMedia } = viewerStore.media.state
const { downloadCurrentMedia } = viewerStore.presentation
const {
  trackerSaving,
  hasPendingChanges,
  showTrackerViewerStepper,
  showTrackerViewerKeyboardGuide,
} = useTrackerStore()
const showMediaSequenceNav = computed(() => (
  showTrackerViewerStepper.value || (!isMobile.value && showTrackerViewerKeyboardGuide.value)
))
const { canShareFromNav, shareFromNav } = useShareManagementStore()
const { updateAvailable, latestVersion, check: checkForUpdates } = useUpdateStatusStore()

const { hasNavigator, navigatorOpen, toggleNavigator } = useContextNavigator()
const showNavigatorToggle = computed(() => showDesktopSidebar.value && hasNavigator.value)

const breadcrumbTrail = computed(() => breadcrumbs.value.slice(-3))
const userRoleLabel = computed(() => currentUser.value?.role === 'admin' ? 'Administrator' : 'Member')
const userInitial = computed(() => currentUser.value?.display_name?.charAt(0)?.toUpperCase() || 'U')
const userIdentityStyle = computed(() => identityColorStyle(
  currentUser.value?.id || currentUser.value?.username || currentUser.value?.display_name,
))
const navItems = computed(() => {
  const items = [{
    key: 'home',
    module: 'home',
    label: 'Home',
    icon: '#icon-home',
    action: 'go-to-home',
  }]

  if (currentUser.value?.role === 'admin' && canAccessFileBrowser.value) {
    items.push({
      key: 'files',
      module: 'files',
      label: 'Files',
      icon: '#icon-folder',
      action: 'go-to-files',
    })
  }

  items.push({
    key: 'projects',
    module: 'projects',
    label: 'Projects',
    icon: '#icon-project',
    action: 'go-to-projects',
  })

  items.push({
    key: 'settings',
    module: 'settings',
    label: 'Settings',
    icon: '#icon-settings',
    action: 'go-to-settings',
  })

  return items
})

function activateNav(action) {
  const actions = { 'go-to-home': goToHome, 'go-to-files': goToFiles, 'go-to-projects': goToProjects, 'go-to-settings': goToSettings }
  actions[action]?.()
  closeMobileNav()
}

function openChangePassword(closeActivityTray) {
  closeActivityTray?.()
  openSessionChangePassword()
}

function signOut(closeActivityTray) {
  closeActivityTray?.()
  logout()
}

function openUpdates() {
  goToSettings('updates')
  closeMobileNav()
}

watch(
  () => currentUser.value?.role,
  role => {
    if (role === 'admin') checkForUpdates()
  },
  { immediate: true },
)
</script>

<style>
.mini-sidebar {
  width: var(--v-sidebar-width);
  background: color-mix(in srgb, var(--v-shell-topbar-bg) 88%, var(--v-bg-base));
  border-right: 1px solid var(--v-divider);
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  z-index: 50;
}

.sidebar-logo {
  height: var(--v-nav-height);
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 0;
  background: transparent;
  color: var(--v-accent);
}

.sidebar-logo .logo-mark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  transition:
    transform var(--v-duration-fast) var(--v-ease-soft),
    border-color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.sidebar-logo:hover .logo-mark {
  border-color: color-mix(in srgb, var(--v-accent) 18%, var(--v-divider));
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-inline));
}

.sidebar-logo:active .logo-mark {
  transform: scale(0.96);
}

.sidebar-logo:focus-visible {
  outline: none;
}

.sidebar-logo:focus-visible .logo-mark {
  outline: 2px solid var(--v-border-focus);
  outline-offset: 1px;
}

.logo-mark {
  font-size: 20px;
  font-weight: 800;
  color: var(--v-accent);
  letter-spacing: 0;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 10px 8px;
  gap: 5px;
  width: 100%;
}

.sidebar-item {
  position: relative;
  width: 38px;
  height: 38px;
  margin: 0 auto;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v-text-muted);
  transition:
    transform var(--v-duration-fast) var(--v-ease-soft),
    border-color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft),
    color var(--v-duration-fast) var(--v-ease-soft);
}

.sidebar-item:hover {
  color: var(--v-text);
  border-color: color-mix(in srgb, var(--v-surface-border-soft) 72%, transparent);
  background: color-mix(in srgb, var(--v-bg-hover) 78%, transparent);
}

.sidebar-item:active {
  transform: scale(0.96);
}

.sidebar-item:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: 1px;
}

.sidebar-item.active {
  color: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 20%, var(--v-divider));
  background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-raised-strong));
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 4%, transparent);
}

.sidebar-item .icon {
  width: 18px;
  height: 18px;
}

.sidebar-item-label {
  display: none;
}

.sidebar-item[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
  background: var(--v-surface-raised-strong);
  color: var(--v-text);
  padding: 6px 10px;
  border-radius: var(--v-radius-tight);
  font-size: var(--v-text-sm);
  font-weight: 500;
  white-space: nowrap;
  border: 1px solid var(--v-surface-border-soft);
  box-shadow: var(--v-surface-shadow-raised);
  z-index: 100;
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.sidebar-item[data-tooltip]:hover::after {
  opacity: 1;
}

.sidebar-bottom {
  padding: 8px 8px 10px;
  width: 100%;
}

.sidebar-update {
  color: var(--v-info);
  background: var(--v-info-bg);
}

.sidebar-update:hover {
  color: color-mix(in srgb, var(--v-info) 82%, white);
  background: color-mix(in srgb, var(--v-info) 14%, var(--v-bg-hover));
}

.sidebar-update-dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--v-info);
  box-shadow: 0 0 0 2px var(--v-shell-topbar-bg);
}

.mobile-nav-backdrop,
.mobile-nav-drawer {
  display: none;
}

.nav-navigator-toggle .icon {
  opacity: 0.75;
}

.nav-navigator-toggle.active .icon {
  opacity: 1;
  color: var(--v-accent);
}

.main-wrapper {
  --v-tracker-masthead-bg: color-mix(in srgb, var(--v-surface-panel) 36%, var(--v-shell-topbar-bg));
  --v-tracker-masthead-divider: var(--v-divider);
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  background: transparent;
}

.unified-nav {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--v-shell-header-height);
  padding: 0 18px;
  flex-shrink: 0;
  z-index: 40;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: color-mix(in srgb, var(--v-surface-panel) 42%, var(--v-shell-topbar-bg));
  border-bottom: 1px solid var(--v-surface-border-strong);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.026);
}

.unified-nav.in-tracker {
  background: var(--v-tracker-masthead-bg);
  border-bottom-color: var(--v-tracker-masthead-divider);
  box-shadow: none;
}

.nav-left,
.nav-right {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}

.nav-left {
  flex: 1 1 0;
}

.nav-right {
  flex: 1 1 0;
  justify-content: flex-end;
}

.nav-context {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-left: 5px;
  padding-left: 12px;
  border-left: 1px solid var(--v-divider-subtle);
  overflow: hidden;
}

.nav-left-trailing {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding-left: 6px;
  margin-left: 2px;
  border-left: 1px solid var(--v-divider);
}

.nav-left-trailing:empty {
  display: none;
}

.nav-center {
  min-width: 0;
}

.nav-center-search {
  width: min(400px, 34vw);
  flex: 0 1 min(400px, 34vw);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 18px;
}

.nav-center-search:empty {
  display: none;
}

.nav-center-search > * {
  min-width: 0;
}

.nav-center-overlay {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.nav-center-overlay > * {
  pointer-events: auto;
}

.nav-menu-toggle,
.nav-back,
.nav-navigator-toggle {
  color: var(--v-text-muted);
}

.unified-nav .nav-left > .v-btn-icon,
.unified-nav .nav-right > .v-btn-icon,
.unified-nav .nav-account-activity > .v-btn-icon {
  width: var(--v-btn-height);
  min-width: var(--v-btn-height);
  height: var(--v-btn-height);
  min-height: var(--v-btn-height);
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
}

.unified-nav .nav-left > .v-btn-icon:hover:not(:disabled),
.unified-nav .nav-right > .v-btn-icon:hover:not(:disabled),
.unified-nav .nav-account-activity > .v-btn-icon:hover:not(:disabled) {
  border-color: var(--v-control-border);
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.unified-nav .nav-left > .v-btn-icon:active:not(:disabled),
.unified-nav .nav-right > .v-btn-icon:active:not(:disabled),
.unified-nav .nav-account-activity > .v-btn-icon:active:not(:disabled) {
  transform: scale(0.98);
}

.nav-menu-toggle.active {
  color: var(--v-accent);
  border-color: var(--v-control-border-active);
  background: var(--v-control-bg-active);
}

.nav-title {
  margin: 0;
  font-size: var(--v-text-md);
  font-weight: 680;
  letter-spacing: -0.01em;
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.unified-nav.in-tracker .nav-title,
.unified-nav.in-media .nav-title {
  font-size: var(--v-text-md);
  font-weight: 680;
  color: var(--v-text);
  letter-spacing: -0.012em;
}

.save-indicator {
  display: inline-flex;
  align-items: center;
  margin-left: var(--v-space-2);
  opacity: 0.6;
}

.save-indicator .icon {
  width: 14px;
  height: 14px;
}

.save-indicator.saving .icon {
  animation: v-spin 1s linear infinite;
  color: var(--v-info);
}

.save-indicator.pending .icon {
  color: var(--v-warning);
}

.nav-media-name {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--v-text-base);
  font-weight: 550;
  letter-spacing: 0;
  color: var(--v-text);
}

.nav-breadcrumbs {
  display: flex;
  align-items: center;
  gap: var(--v-space-1);
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
}

.nav-breadcrumbs .crumb {
  cursor: pointer;
  transition: color var(--v-transition-fast);
}

.nav-breadcrumbs .crumb:hover {
  color: var(--v-text);
}

.crumb-sep {
  opacity: 0.4;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
}

.share-badge {
  background: var(--v-accent-muted);
  color: var(--v-accent);
  padding: 2px 8px;
  border-radius: var(--v-radius-tight);
  font-size: var(--v-text-xs);
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
}

.share-origin-badge {
  min-width: 0;
  max-width: min(58vw, 520px);
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px 0 8px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 18%, var(--v-control-border));
  border-radius: var(--v-radius-full);
  background: var(--v-surface-tint-strong);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
  font-weight: 550;
  letter-spacing: 0;
  text-transform: none;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
}

.share-origin-center {
  max-width: calc(100vw - 340px);
}

.share-origin-badge__dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: color-mix(in srgb, var(--v-accent) 82%, var(--v-text));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 12%, transparent);
}

.share-origin-badge__copy {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-avatar-btn {
  --v-identity-color: var(--v-accent);
  position: relative;
  overflow: visible;
  background: color-mix(in srgb, var(--v-identity-color) 10%, var(--v-surface-inline)) !important;
  border-color: color-mix(in srgb, var(--v-identity-color) 24%, var(--v-control-border)) !important;
  box-shadow: var(--v-surface-shadow-inset);
  color: color-mix(in srgb, var(--v-identity-color) 72%, white) !important;
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0;
  text-transform: uppercase;
}

.user-avatar-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--v-identity-color) 16%, var(--v-surface-inline-strong)) !important;
  border-color: color-mix(in srgb, var(--v-identity-color) 36%, var(--v-control-border-hover)) !important;
  color: var(--v-text) !important;
}

.nav-account-activity {
  margin-left: 5px;
  padding-left: 8px;
  border-left: 1px solid var(--v-divider-subtle);
}

.nav-account-activity.is-open .user-avatar-btn {
  background: color-mix(in srgb, var(--v-identity-color) 16%, var(--v-surface-inline-strong)) !important;
  border-color: color-mix(in srgb, var(--v-accent) 45%, var(--v-control-border-hover)) !important;
  box-shadow: 0 0 0 2px var(--v-accent-muted), var(--v-surface-shadow-inset);
  color: var(--v-text) !important;
}

.user-activity-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--v-accent);
  box-shadow: 0 0 0 2px var(--v-shell-topbar-bg);
  color: var(--v-on-accent);
  font-size: var(--v-text-3xs);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  letter-spacing: 0;
  text-transform: none;
}

.nav-account-panel-footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  padding: 10px 12px;
  flex: 0 0 auto;
  border-top: 1px solid var(--v-divider-subtle);
  background: color-mix(in srgb, var(--v-surface-panel) 88%, var(--v-bg-base));
}

.nav-account-panel-identity {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-account-panel-identity strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
}

.nav-account-panel-identity span {
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
}

.nav-account-panel-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-1);
}

.nav-account-panel-actions .v-btn {
  padding-inline: 9px;
  color: var(--v-text-muted);
  white-space: nowrap;
}

.nav-account-panel-actions .v-btn:hover {
  color: var(--v-text);
}

.nav-account-panel-actions .icon {
  width: 13px;
  height: 13px;
}

@media (max-width: 768px) {
  .vueio {
    flex-direction: column;
  }

  .mobile-nav-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    border: 0;
    padding: 0;
    background: var(--v-overlay-scrim-strong);
    z-index: 88;
  }

  .mobile-nav-drawer {
    display: flex;
    position: fixed;
    top: 0;
    left: 0;
    bottom: auto;
    width: min(332px, calc(100vw - 28px));
    height: 100svh;
    flex-direction: column;
    padding: 0;
    background: var(--v-surface-canvas);
    border-right: 1px solid var(--v-surface-border-strong);
    box-shadow: var(--v-modal-shadow);
    transform: translateX(calc(-100% - 24px));
    transition: transform var(--v-duration-normal) var(--v-ease-emphasized), opacity var(--v-duration-fast) var(--v-ease-emphasized);
    z-index: 89;
    overflow-y: auto;
    opacity: 0;
  }

  @supports (height: 100dvh) {
    .mobile-nav-drawer {
      height: 100dvh;
    }
  }

  .mobile-nav-shell {
    position: relative;
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background: transparent;
  }

  .mobile-nav-drawer.is-open {
    transform: translateX(0);
    opacity: 1;
  }

  .mobile-nav-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--v-space-3);
    padding: max(18px, env(safe-area-inset-top, 0px) + 10px) 16px 14px;
    border-bottom: 1px solid var(--v-surface-border-soft);
  }

  .mobile-nav-brand {
    min-width: 0;
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    gap: var(--v-space-3);
    border: 0;
    padding: 0;
    background: transparent;
    color: var(--v-text);
    text-align: left;
  }

  .mobile-nav-brand-mark {
    width: 42px;
    height: 42px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--v-radius-lg);
    background: var(--v-surface-raised);
    border: 1px solid var(--v-surface-border-soft);
    box-shadow: var(--v-surface-shadow-raised);
  }

  .mobile-nav-brand-copy {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .mobile-nav-brand-title {
    font-size: var(--v-text-lg);
    font-weight: 700;
    letter-spacing: 0;
  }

  .mobile-nav-brand-subtitle {
    font-size: var(--v-text-xs);
    color: var(--v-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }

  .mobile-nav-close {
    width: 44px;
    height: 44px;
    min-width: 44px;
    min-height: 44px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--v-control-border);
    border-radius: var(--v-button-radius);
    background: var(--v-control-bg);
    box-shadow: var(--v-surface-shadow-inset);
    color: var(--v-text-dim);
  }

  .mobile-nav-close .icon {
    width: 16px;
    height: 16px;
  }

  .mobile-nav-body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--v-space-4);
    padding: 14px 14px calc(18px + env(safe-area-inset-bottom, 0px));
  }

  .mobile-nav-section {
    display: flex;
    flex-direction: column;
    gap: var(--v-space-2);
  }

  .mobile-nav-section-label {
    padding: 0 2px;
    color: var(--v-text-muted);
    font-size: var(--v-text-2xs);
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .mobile-nav-search-shell {
    width: 100%;
  }

  .mobile-nav-search-shell > * {
    width: 100%;
    max-width: none;
  }

  .mobile-nav-list {
    display: flex;
    flex-direction: column;
    gap: var(--v-space-2);
  }

  .mobile-nav-item {
    display: flex;
    align-items: center;
    gap: var(--v-space-3);
    width: 100%;
    padding: 11px 12px;
    border: 1px solid var(--v-control-border);
    border-radius: var(--v-button-radius);
    background: var(--v-surface-raised);
    box-shadow: var(--v-surface-shadow-raised);
    color: var(--v-text-dim);
    text-align: left;
    transition: background var(--v-transition-fast), border-color var(--v-transition-fast), color var(--v-transition-fast), transform var(--v-transition-fast);
  }

  .mobile-nav-item:active,
  .mobile-nav-item:hover {
    color: var(--v-text);
    border-color: var(--v-control-border-hover);
    background: var(--v-surface-raised-strong);
    transform: none;
  }

  .mobile-nav-item.active {
    color: var(--v-text);
    border-color: var(--v-control-border-active);
    background: var(--v-control-bg-active);
  }

  .mobile-nav-update {
    color: var(--v-text);
    border-color: color-mix(in srgb, var(--v-info) 22%, var(--v-control-border));
    background: color-mix(in srgb, var(--v-info) 7%, var(--v-surface-raised));
  }

  .mobile-nav-update .mobile-nav-item-icon {
    color: var(--v-info);
    background: color-mix(in srgb, var(--v-info) 10%, var(--v-surface-inset));
  }

  .mobile-nav-update-arrow {
    width: 15px;
    height: 15px;
    flex: 0 0 auto;
    color: var(--v-text-muted);
  }

  .mobile-nav-item-icon {
    width: 42px;
    height: 42px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--v-radius-lg);
    background: var(--v-surface-inset);
    box-shadow: var(--v-surface-shadow-inset);
    border: 1px solid var(--v-control-border);
  }

  .mobile-nav-item.active .mobile-nav-item-icon {
    --mobile-nav-item-icon-bg: color-mix(in srgb, var(--v-accent) 10%, var(--v-surface-inset));
    color: var(--v-accent);
    border-color: color-mix(in srgb, var(--mobile-nav-item-icon-bg) 97%, white);
    background: var(--mobile-nav-item-icon-bg);
  }

  .mobile-nav-item-icon .icon {
    width: 18px;
    height: 18px;
  }

  .mobile-nav-item-copy {
    min-width: 0;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .mobile-nav-item-label {
    min-width: 0;
    font-size: var(--v-text-md);
    font-weight: 600;
    letter-spacing: 0;
  }

  .mobile-nav-item-state {
    flex-shrink: 0;
    min-height: 22px;
    padding: 0 8px;
    border-radius: var(--v-radius-full);
    border: 1px solid color-mix(in srgb, var(--v-accent-muted) 97%, white);
    background: var(--v-accent-muted);
    color: var(--v-accent-hover);
    font-size: var(--v-text-2xs);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    display: inline-flex;
    align-items: center;
  }

  .mobile-nav-account {
    margin-top: auto;
  }

  .mobile-nav-account-card {
    display: flex;
    align-items: center;
    gap: var(--v-space-3);
    padding: var(--v-space-3);
    border: 1px solid var(--v-control-border);
    border-radius: var(--v-radius-lg);
    background: var(--v-surface-raised);
    box-shadow: var(--v-surface-shadow-raised);
  }

  .mobile-nav-account-mark {
    --v-identity-color: var(--v-accent);
    width: 40px;
    height: 40px;
    flex-shrink: 0;
    border-radius: var(--v-radius-lg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, var(--v-identity-color) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--v-identity-color) 24%, transparent);
    color: color-mix(in srgb, var(--v-identity-color) 72%, white);
    font-size: var(--v-text-md);
    font-weight: 700;
  }

  .mobile-nav-account-copy {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .mobile-nav-account-copy strong {
    font-size: var(--v-text-base);
    font-weight: 600;
    color: var(--v-text);
  }

  .mobile-nav-account-copy span {
    font-size: var(--v-text-xs);
    color: var(--v-text-muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .unified-nav {
    padding: 0 12px;
    gap: 2px;
  }

  .unified-nav:not(.in-media) .nav-left {
    flex: 1 1 auto;
    max-width: none;
  }

  .unified-nav:not(.in-media) .nav-right {
    flex: 0 0 auto;
    max-width: none;
  }

  .nav-context {
    margin-left: 2px;
    padding-left: 8px;
  }

  .unified-nav.in-media .nav-left {
    max-width: calc(100% - 160px);
  }

  .unified-nav.in-media .nav-right {
    max-width: calc(50% - 58px);
  }

  .unified-nav.in-media .nav-center-overlay {
    z-index: 1;
  }

  .unified-nav.in-media .nav-left,
  .unified-nav.in-media .nav-right {
    position: relative;
    z-index: 2;
  }

  .nav-title {
    font-size: var(--v-text-base);
    font-weight: 650;
    color: var(--v-text-secondary);
  }

  .nav-brand {
    gap: 7px;
  }

  .unified-nav:has(.share-origin-center) .nav-brand {
    display: none;
  }

  .share-origin-center {
    max-width: calc(100vw - 28px);
    width: calc(100vw - 28px);
  }

  .share-origin-badge {
    max-width: 100%;
    height: 26px;
    padding-inline: var(--v-space-2);
    font-size: var(--v-text-2xs);
  }

  .nav-breadcrumbs {
    display: none;
  }

  .nav-media-name {
    max-width: 15ch;
    font-size: var(--v-text-base);
    text-overflow: ellipsis;
    -webkit-mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 12px), transparent 100%);
    mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 12px), transparent 100%);
  }

  .unified-nav.in-media.has-media-sequence .nav-media-name {
    display: none;
  }

  .unified-nav.in-media.has-media-sequence .nav-left {
    max-width: calc(50% - 58px);
  }

  .nav-left-trailing {
    padding-left: 6px;
    margin-left: 0;
    border-left: 0;
    gap: var(--v-space-1);
  }

  .user-avatar-btn {
    width: var(--v-btn-height-lg) !important;
    height: var(--v-btn-height-lg) !important;
    min-width: var(--v-btn-height-lg) !important;
    min-height: var(--v-btn-height-lg) !important;
    font-size: var(--v-text-sm);
  }

  header.in-tracker .v-dropdown-wrapper > .v-btn-icon,
  header.in-media .v-dropdown-wrapper > .v-btn-icon {
    width: var(--v-btn-height-lg) !important;
    height: var(--v-btn-height-lg) !important;
    min-width: var(--v-btn-height-lg) !important;
    min-height: var(--v-btn-height-lg) !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: var(--v-button-radius) !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: var(--v-text-dim);
  }

  header.in-tracker .v-dropdown-wrapper > .v-btn-icon .icon,
  header.in-media .v-dropdown-wrapper > .v-btn-icon .icon {
    width: 14px !important;
    height: 14px !important;
  }

  .unified-nav .nav-left > .v-btn-icon,
  .unified-nav .nav-right > .v-btn-icon {
    width: var(--v-btn-height-lg);
    min-width: var(--v-btn-height-lg);
    height: var(--v-btn-height-lg);
    min-height: var(--v-btn-height-lg);
  }

  .nav-account-activity {
    margin-left: 1px;
    padding-left: 3px;
  }
}

@media (max-width: 430px) {
  .unified-nav {
    padding-inline: 8px;
  }

  .nav-left,
  .nav-right {
    gap: 0;
  }

  .nav-context {
    margin-left: 0;
    padding-left: 6px;
    border-left: 0;
  }

  .unified-nav.in-tracker .nav-title,
  .unified-nav.in-media .nav-title {
    font-size: var(--v-text-base);
  }

  .nav-account-activity {
    margin-left: 0;
    padding-left: 0;
    border-left: 0;
  }

  .nav-account-panel-footer {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--v-space-2);
  }

  .nav-account-panel-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .nav-account-panel-actions .v-btn {
    min-height: 40px;
    justify-content: center;
  }
}
</style>
