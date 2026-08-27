<template>
  <section class="admin-section updates-settings-section">
    <AdminSettingsHeader
      eyebrow="Installation"
      title="Updates"
      description="See what version you are running and check for a newer self-hosted release."
      icon="#icon-refresh"
    >
      <button class="v-btn v-btn-secondary v-btn-sm" type="button" :disabled="loading" @click="check({ refresh: true })">
        <svg class="icon" :class="{ spinning: loading }"><use href="#icon-refresh" /></svg>
        {{ loading ? 'Checking' : 'Check again' }}
      </button>
    </AdminSettingsHeader>

    <div class="updates-body">
      <section class="updates-status-card" :class="`is-${state}`">
        <div class="updates-status-mark" aria-hidden="true">
          <svg class="icon"><use :href="statusIcon" /></svg>
        </div>
        <div class="updates-status-copy">
          <div class="updates-status-kicker">
            <p class="settings-eyebrow">{{ statusEyebrow }}</p>
            <span class="updates-channel-badge">{{ channelLabel }}</span>
          </div>
          <h3>{{ statusTitle }}</h3>
          <p>{{ statusDescription }}</p>
        </div>
        <a
          v-if="status?.release_url"
          class="v-btn v-btn-secondary v-btn-sm updates-release-link"
          :href="status.release_url"
          target="_blank"
          rel="noreferrer"
        >
          Release notes
          <svg class="icon"><use href="#icon-external-link" /></svg>
        </a>
      </section>

      <div class="updates-facts">
        <section class="updates-fact">
          <span class="settings-eyebrow">Installed</span>
          <strong>{{ status?.current_version || 'Checking' }}</strong>
          <span>The version currently running on this server.</span>
        </section>
        <section class="updates-fact">
          <span class="settings-eyebrow">Latest release</span>
          <strong>{{ status?.latest_version || latestLabel }}</strong>
          <span>{{ latestHint }}</span>
        </section>
      </div>

      <section v-if="releaseNotes.length" class="updates-notes-card" aria-labelledby="updates-notes-title">
        <div class="updates-notes-heading">
          <p class="settings-eyebrow">Release history</p>
          <h3 id="updates-notes-title">What’s new</h3>
        </div>
        <article v-for="release in releaseNotes" :key="release.version" class="updates-release-note">
          <header>
            <strong>{{ release.version }}</strong>
            <span v-if="release.nightly" class="updates-nightly-badge">Nightly</span>
            <time v-if="release.published_at" :datetime="release.published_at">{{ formatReleaseDate(release.published_at) }}</time>
          </header>
          <p>{{ release.notes || 'Maintenance and reliability improvements.' }}</p>
        </article>
      </section>

      <section v-if="status?.update_command" class="updates-command-card">
        <div>
          <p class="settings-eyebrow">Update from the host</p>
          <h3>Run one safe command</h3>
          <p>
            Vue.io will verify the release, create a backup, update both services, and check the installation before it finishes.
          </p>
        </div>
        <div class="updates-command-row">
          <code>{{ status.update_command }}</code>
          <button class="v-btn v-btn-primary v-btn-sm" type="button" @click="copyCommand">
            <svg class="icon"><use href="#icon-copy" /></svg>
            Copy
          </button>
        </div>
      </section>

      <section class="updates-safety-panel">
        <div class="updates-safety-icon" aria-hidden="true">
          <svg class="icon"><use href="#icon-lock" /></svg>
        </div>
        <div>
          <strong>Safe by design</strong>
          <p>The updater automatically backs up your database first. Project files and media are never touched.</p>
          <p>Updates run on the Vue.io host, never from the web app. To undo an update, run <code>sudo vueioctl rollback</code>.</p>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import { useUpdateStatusStore } from '../../ownership/updateStatus'
import { notify } from '../../utils/toasts'

const { status, loading, check } = useUpdateStatusStore()

const state = computed(() => status.value?.status || (loading.value ? 'checking' : 'unavailable'))
const channelLabel = computed(() => status.value?.channel === 'nightly' ? 'Nightly' : 'Stable')
const releaseNotes = computed(() => Array.isArray(status.value?.releases_between) ? status.value.releases_between : [])
const statusIcon = computed(() => ({
  available: '#icon-download',
  current: '#icon-check',
  development: '#icon-zap',
  error: '#icon-alert',
}[state.value] || '#icon-info'))
const statusEyebrow = computed(() => ({
  available: 'Update available',
  current: 'Up to date',
  development: 'Development build',
  error: 'Check unavailable',
}[state.value] || 'Version status'))
const statusTitle = computed(() => ({
  available: `${status.value?.latest_version} is ready`,
  current: 'You are running the latest release',
  development: 'This installation is on a development build',
  error: 'Vue.io could not reach the release service',
}[state.value] || (loading.value ? 'Checking for updates' : 'Update checks are not configured')))
const statusDescription = computed(() => ({
  available: 'A newer tested self-hosted release is available when you are ready.',
  current: 'No action is needed.',
  development: 'Tagged release comparisons begin when this installation runs an immutable alpha version.',
  error: 'Your installation is still running normally. Try again when the server has internet access.',
}[state.value] || 'Update notifications will activate after the public release repository is configured.'))
const latestLabel = computed(() => loading.value ? 'Checking' : 'Not available')
const latestHint = computed(() => status.value?.published_at
  ? `Published ${new Date(status.value.published_at).toLocaleDateString()}`
  : 'The newest immutable alpha published for self-hosting.')

function formatReleaseDate(value) {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function copyCommand() {
  try {
    await navigator.clipboard.writeText(status.value.update_command)
    notify('Update command copied.')
  } catch {
    notify('Could not copy the update command.')
  }
}

onMounted(() => check())
</script>

<style scoped>
.updates-settings-section {
  overflow: hidden;
}

.updates-body {
  display: grid;
  gap: var(--v-space-3);
  padding-top: var(--v-space-4);
}

.updates-status-card {
  --updates-status-color: var(--v-text-secondary);
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.updates-status-card.is-available {
  --updates-status-color: var(--v-info);
}

.updates-status-card.is-current {
  --updates-status-color: var(--v-accent);
}

.updates-status-card.is-development {
  --updates-status-color: var(--v-warning);
}

.updates-status-card.is-error {
  --updates-status-color: var(--v-danger);
}

.updates-status-card.is-available,
.updates-status-card.is-current,
.updates-status-card.is-development,
.updates-status-card.is-error {
  border-color: color-mix(in srgb, var(--updates-status-color) 28%, var(--v-surface-border-soft));
  background: color-mix(in srgb, var(--updates-status-color) 7%, var(--v-surface-inline));
}

.updates-status-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-text-secondary);
  background: var(--v-surface-raised);
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
}

.updates-status-card.is-available .updates-status-mark,
.updates-status-card.is-current .updates-status-mark,
.updates-status-card.is-development .updates-status-mark,
.updates-status-card.is-error .updates-status-mark {
  color: var(--updates-status-color);
  background: color-mix(in srgb, var(--updates-status-color) 10%, var(--v-surface-raised));
}

.updates-status-mark .icon {
  width: 18px;
  height: 18px;
}

.updates-status-copy {
  min-width: 0;
}

.updates-status-kicker,
.updates-release-note header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.updates-status-kicker .settings-eyebrow {
  margin: 0;
}

.updates-channel-badge,
.updates-nightly-badge {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 7px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: 999px;
  color: var(--v-text-secondary);
  background: var(--v-surface-raised);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.updates-status-copy h3,
.updates-command-card h3 {
  margin: 2px 0 4px;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.updates-status-copy p:last-child,
.updates-command-card p:last-child,
.updates-fact > span:last-child,
.updates-safety-note {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.updates-release-link .icon,
.updates-command-row .icon {
  width: 14px;
  height: 14px;
}

.updates-settings-section .icon.spinning {
  animation: v-spin 0.8s linear infinite;
}

.updates-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.updates-fact {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.updates-fact strong {
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-md);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.updates-command-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
  align-items: center;
  gap: 18px;
  padding: 16px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.updates-notes-card {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.updates-notes-heading {
  padding: 15px 16px 12px;
  border-bottom: 1px solid var(--v-surface-border-soft);
}

.updates-notes-heading h3 {
  margin: 2px 0 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.updates-release-note {
  padding: 14px 16px;
}

.updates-release-note + .updates-release-note {
  border-top: 1px solid var(--v-surface-border-soft);
}

.updates-release-note header strong {
  color: var(--v-text);
  font-size: var(--v-text-sm);
}

.updates-release-note time {
  margin-left: auto;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.updates-release-note p {
  margin: 8px 0 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.55;
  white-space: pre-wrap;
}

.updates-nightly-badge {
  color: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 25%, var(--v-surface-border-soft));
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-raised));
}

.updates-command-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-control-bg);
}

.updates-command-row code {
  min-width: 0;
  flex: 1;
  overflow-x: auto;
  padding: 0 8px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  white-space: nowrap;
}

.updates-safety-panel {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: start;
  gap: var(--v-space-3);
  padding: 14px 16px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.updates-safety-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-inline));
}

.updates-safety-icon .icon {
  width: 14px;
  height: 14px;
}

.updates-safety-panel strong {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
}

.updates-safety-panel p {
  margin: 4px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.updates-safety-panel code {
  color: var(--v-text-secondary);
}

@media (max-width: 768px) {
  .updates-body {
    gap: 10px;
    padding-top: var(--v-space-3);
  }

  .updates-status-card {
    grid-template-columns: 38px minmax(0, 1fr);
    gap: 11px;
    padding: 13px;
  }

  .updates-status-mark {
    width: 38px;
    height: 38px;
  }

  .updates-release-link {
    grid-column: 1 / -1;
    width: 100%;
  }

  .updates-facts,
  .updates-command-card {
    grid-template-columns: 1fr;
  }

  .updates-command-card {
    gap: 13px;
    padding: 13px;
  }

  .updates-command-row {
    align-items: stretch;
    flex-direction: column;
  }

  .updates-command-row code {
    padding: 7px 8px;
  }
}
</style>
