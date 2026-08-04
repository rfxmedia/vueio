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
            <span class="mobile-nav-account-mark">{{ userInitial }}</span>
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

      <div class="nav-right">
        <slot v-if="showMediaSequenceNav && !isMobile" name="nav-center" />
        <slot name="nav-right-trailing" />

        <button
          v-if="canShareFromNav && !shareMode"
          class="v-btn v-btn-quiet v-btn-icon"
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

        <VMenu
          v-if="currentUser && !shareMode"
          :open="userMenuOpen"
          min-width="220"
          panel-class="user-dropdown"
          :close-on-select="false"
          @update:open="(open) => { if (open !== userMenuOpen) toggleUserMenu() }"
        >
          <template #trigger="{ triggerProps }">
            <button
              v-bind="triggerProps"
              class="v-btn v-btn-quiet v-btn-icon user-avatar-btn"
              type="button"
              aria-label="Account menu"
              @click="toggleUserMenu"
            >
              {{ currentUser.display_name?.charAt(0)?.toUpperCase() || 'U' }}
            </button>
          </template>
          <div>
            <div class="user-dropdown-header" role="presentation">
              <strong>{{ currentUser.display_name }}</strong>
              <span class="v-text-muted">{{ userRoleLabel }}</span>
            </div>
            <div class="v-dropdown-divider"></div>
            <button class="v-dropdown-item" type="button" role="menuitem" @click="openChangePassword">
              <svg class="icon"><use href="#icon-edit"/></svg> Change Password
            </button>
            <div class="v-dropdown-divider"></div>
            <button class="v-dropdown-item" type="button" role="menuitem" @click="logout">
              <svg class="icon"><use href="#icon-back"/></svg> Sign Out
            </button>
          </div>
        </VMenu>

      </div>
    </header>

    <slot />
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import AppNavigator from './AppNavigator.vue'
import { VMenu } from '../primitives'
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

const { currentProject, currentTracker } = useProjectTrackerSelectionStore()
const { currentUser, canAccessFileBrowser, openChangePassword: openSessionChangePassword, logout } = useSessionAuthStore()
const { shareMode, shareAllowDownload, shareRequestFiles } = useShareAccessContext()
const shareOriginLabel = computed(() => shareRequestFiles.value ? 'File request' : 'Shared review')
const {
  activeModule,
  showMainContent,
  isMobile,
  mobileNavOpen,
  userMenuOpen,
  showDesktopSidebar,
  showMobileNavigation,
  closeMobileNav,
  toggleMobileNav,
  toggleUserMenu,
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
const { trackerSaving, hasPendingChanges, showTrackerViewerStepper: showMediaSequenceNav } = useTrackerStore()
const { canShareFromNav, shareFromNav } = useShareManagementStore()
const { updateAvailable, latestVersion, check: checkForUpdates } = useUpdateStatusStore()

const { hasNavigator, navigatorOpen, toggleNavigator } = useContextNavigator()
const showNavigatorToggle = computed(() => showDesktopSidebar.value && hasNavigator.value)

const breadcrumbTrail = computed(() => breadcrumbs.value.slice(-3))
const userRoleLabel = computed(() => currentUser.value?.role === 'admin' ? 'Administrator' : 'Artist')
const userInitial = computed(() => currentUser.value?.display_name?.charAt(0)?.toUpperCase() || 'U')
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

function openChangePassword() {
  openSessionChangePassword()
  if (userMenuOpen.value) toggleUserMenu()
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
  background: var(--v-shell-topbar-bg);
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
  transition: background var(--v-transition-fast);
}

.sidebar-logo:hover {
  background: var(--v-surface-inline);
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
  padding: var(--v-space-2);
  gap: var(--v-space-1);
  width: 100%;
}

.sidebar-item {
  position: relative;
  width: 40px;
  height: 40px;
  margin: 0 auto;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v-text-muted);
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.sidebar-item:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.sidebar-item.active {
  color: var(--v-text);
  background: var(--v-surface-raised-strong);
  box-shadow: var(--v-surface-shadow-raised);
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
  background: var(--v-surface-panel);
  color: var(--v-text);
  padding: 6px 10px;
  border-radius: var(--v-radius-tight);
  font-size: var(--v-text-sm);
  font-weight: 500;
  white-space: nowrap;
  border: 1px solid var(--v-surface-border-soft);
  z-index: 100;
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.sidebar-item[data-tooltip]:hover::after {
  opacity: 1;
}

.sidebar-bottom {
  padding: var(--v-space-2);
  width: 100%;
}

.sidebar-update {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 8%, transparent);
}

.sidebar-update:hover {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 14%, var(--v-bg-hover));
}

.sidebar-update-dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--v-accent);
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
  padding: 0 16px;
  flex-shrink: 0;
  z-index: 40;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v-shell-topbar-bg);
  border-bottom: 1px solid var(--v-divider);
}

.nav-left,
.nav-right {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.nav-right {
  justify-content: flex-end;
}

.nav-context {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding-left: var(--v-space-1);
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
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 24px;
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
.nav-back {
  color: var(--v-text-muted);
}

.nav-menu-toggle.active {
  color: var(--v-accent);
}

.nav-title {
  margin: 0;
  font-size: var(--v-text-md);
  font-weight: 600;
  letter-spacing: 0;
  color: var(--v-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.unified-nav.in-tracker .nav-title,
.unified-nav.in-media .nav-title {
  font-size: var(--v-text-base);
  font-weight: 600;
  color: var(--v-text-secondary);
  letter-spacing: 0;
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
  color: var(--v-accent);
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
  background: var(--v-control-bg);
  box-shadow: var(--v-surface-shadow-inset);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0;
  text-transform: uppercase;
}

.user-avatar-btn:hover:not(:disabled) {
  background: var(--v-control-bg-hover);
  color: var(--v-text);
}

.user-dropdown {
  right: 0;
}

.user-dropdown-header {
  padding: var(--v-space-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-dropdown-header strong {
  font-size: var(--v-text-md);
  color: var(--v-text);
}

.user-dropdown-header span {
  font-size: var(--v-text-sm);
  color: var(--v-text-dim);
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
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
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
    border-color: color-mix(in srgb, var(--v-accent) 22%, var(--v-control-border));
    background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-raised));
  }

  .mobile-nav-update .mobile-nav-item-icon {
    color: var(--v-accent);
    background: color-mix(in srgb, var(--v-accent) 10%, var(--v-surface-inset));
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
    width: 40px;
    height: 40px;
    flex-shrink: 0;
    border-radius: var(--v-radius-lg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--v-accent-muted);
    border: 1px solid color-mix(in srgb, var(--v-accent-muted) 97%, white);
    color: var(--v-accent-hover);
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
    padding: 0 14px;
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
    font-size: var(--v-text-md);
    font-weight: 500;
    color: var(--v-text-dim);
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
    width: 32px !important;
    height: 32px !important;
    min-width: 32px !important;
    min-height: 32px !important;
    font-size: var(--v-text-sm);
  }

  header.in-tracker .v-dropdown-wrapper > .v-btn-icon,
  header.in-media .v-dropdown-wrapper > .v-btn-icon {
    width: 32px !important;
    height: 32px !important;
    min-width: 32px !important;
    min-height: 32px !important;
    background: var(--v-control-bg) !important;
    border: 1px solid var(--v-control-border) !important;
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
}
</style>
