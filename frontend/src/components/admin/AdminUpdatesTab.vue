<template>
  <section class="admin-section updates-settings-section">
    <AdminSettingsHeader
      eyebrow="Installation"
      title="Updates"
      description="Keep your Vueio installation up to date with the releases you follow."
      icon="#icon-refresh"
    >
      <button class="v-btn v-btn-secondary v-btn-sm" type="button" :disabled="loading || busy" @click="refreshUpdates">
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
          View on GitHub
          <svg class="icon"><use href="#icon-external-link" /></svg>
        </a>
      </section>

      <section
        v-if="showInstallCard"
        class="updates-install-card"
        :class="{ 'is-failed': updateFailed, 'is-complete': progress?.state === 'succeeded' && !awaitingReload }"
        aria-labelledby="updates-install-title"
      >
        <div class="updates-install-heading">
          <div>
            <h3 id="updates-install-title">{{ installTitle }}</h3>
            <p v-if="!showProgress">A database backup comes first. Vueio will restart briefly during the update.</p>
          </div>
          <button
            v-if="canOfferUpdate"
            class="v-btn v-btn-primary updates-install-button"
            type="button"
            :disabled="busy || offline"
            @click="startUpdate"
          >
            <svg class="icon" :class="{ spinning: busy }" aria-hidden="true"><use :href="busy ? '#icon-refresh' : '#icon-download'" /></svg>
            {{ starting ? 'Starting update' : busy ? 'Updating' : updateFailed ? 'Try update again' : 'Update now' }}
          </button>
        </div>
        <div v-if="showProgress" class="updates-install-progress">
          <div class="updates-progress-label">
            <p role="status" aria-live="polite">{{ progressDescription }}</p>
            <span v-if="!updateFailed" aria-hidden="true">{{ progressPercent }}%</span>
          </div>
          <div
            v-if="!updateFailed"
            class="v-progress"
            role="progressbar"
            aria-label="Installation progress"
            :aria-valuenow="progressPercent"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuetext="progressDescription"
          >
            <div class="v-progress-fill" :style="{ width: `${progressPercent}%` }"></div>
          </div>
          <p v-if="busy && !needsHostAttention" class="updates-install-note">This page will reconnect when the update is ready. You can leave and return to see its progress.</p>
          <div v-if="needsHostAttention || progress?.state === 'interrupted'" class="updates-command-row">
            <code>{{ hostStatusCommand }}</code>
            <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy host status command" @click="copyCommand(hostStatusCommand, 'Status command copied.')">
              <svg class="icon" aria-hidden="true"><use href="#icon-copy" /></svg>
              Copy
            </button>
          </div>
        </div>
        <p v-if="updateError && !updating" class="updates-install-error" role="status">{{ updateError }}</p>
        <p v-if="offline && !busy" class="updates-install-error" role="status">The updater is not responding. Vueio will check again automatically.</p>
      </section>

      <section v-if="progress?.supported === false" class="updates-setup-card" aria-labelledby="updates-setup-title">
        <div>
          <h3 id="updates-setup-title">Enable updates from Settings</h3>
          <p>Run this once on a supported Vueio host. Future updates will be one click away.</p>
        </div>
        <div class="updates-command-row">
          <code>{{ setupCommand }}</code>
          <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy update setup command" @click="copyCommand(setupCommand, 'Setup command copied.')">
            <svg class="icon" aria-hidden="true"><use href="#icon-copy" /></svg>
            Copy
          </button>
        </div>
        <details v-if="status?.update_command" class="updates-command-fallback">
          <summary>Update from the host instead</summary>
          <div class="updates-command-row">
            <code>{{ status.update_command }}</code>
            <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy update command" @click="copyCommand(status.update_command, 'Update command copied.')">
              <svg class="icon" aria-hidden="true"><use href="#icon-copy" /></svg>
              Copy
            </button>
          </div>
        </details>
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

      <section class="updates-channel-card" aria-labelledby="updates-channel-title">
        <div class="updates-channel-copy">
          <p class="settings-eyebrow">Release channel</p>
          <div class="updates-channel-heading">
            <h3 id="updates-channel-title">Following {{ channelLabel }}</h3>
            <a
              v-if="status?.source_url"
              class="updates-branch-link"
              :href="status.source_url"
              target="_blank"
              rel="noreferrer"
            >
              View {{ status.source_branch }} branch
              <svg class="icon"><use href="#icon-external-link" /></svg>
            </a>
          </div>
          <p>{{ channelDescription }}</p>
          <p class="updates-channel-note">{{ channelSwitchNote }}</p>
        </div>
        <div class="updates-command-row">
          <code>{{ channelSwitchCommand }}</code>
          <button
            class="v-btn v-btn-secondary v-btn-sm"
            type="button"
            :aria-label="`Copy command to switch to ${otherChannelLabel}`"
            :disabled="busy"
            @click="copyCommand(channelSwitchCommand, 'Channel command copied.')"
          >
            <svg class="icon"><use href="#icon-copy" /></svg>
            Copy
          </button>
        </div>
      </section>

      <section v-if="releaseNotes.length" class="updates-notes-card" aria-labelledby="updates-notes-title">
        <div class="updates-notes-heading">
          <p class="settings-eyebrow">Release notes</p>
          <h3 id="updates-notes-title">{{ releaseNotesTitle }}</h3>
        </div>
        <article v-for="release in releaseNotes" :key="release.version" class="updates-release-note">
          <header>
            <strong>{{ release.version }}</strong>
            <span v-if="release.nightly" class="updates-nightly-badge">Nightly</span>
            <time v-if="release.published_at" :datetime="release.published_at">{{ formatReleaseDate(release.published_at) }}</time>
          </header>
          <div class="updates-release-note-content">
            <section v-for="(section, sectionIndex) in release.sections" :key="`${release.version}-${sectionIndex}`">
              <h4 v-if="section.title">{{ section.title }}</h4>
              <ul v-if="section.items.length">
                <li v-for="(item, itemIndex) in section.items" :key="`${release.version}-${sectionIndex}-${itemIndex}`">
                  {{ item }}
                </li>
              </ul>
              <p v-for="(paragraph, paragraphIndex) in section.paragraphs" :key="`${release.version}-${sectionIndex}-p-${paragraphIndex}`">
                {{ paragraph }}
              </p>
            </section>
          </div>
        </article>
      </section>

      <section class="updates-safety-panel">
        <div class="updates-safety-icon" aria-hidden="true">
          <svg class="icon"><use href="#icon-lock" /></svg>
        </div>
        <div>
          <strong>Backed up before installation</strong>
          <p>Each update creates a database backup before installation. Project files and original media stay in place.</p>
          <p>If an update needs attention, its status stays here so you can see the next step.</p>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import { useUpdateStatusStore } from '../../ownership/updateStatus'
import { notify } from '../../utils/toasts'

const {
  status, loading, progress, starting, offline, updateError, updating, awaitingReload, needsHostAttention,
  check, readProgress, startUpdate, setVisible,
} = useUpdateStatusStore()
const setupCommand = 'sudo vueioctl updater enable'
const hostStatusCommand = 'sudo vueioctl updater status'
const busy = computed(() => updating.value || awaitingReload.value)
const updateFailed = computed(() => ['failed', 'interrupted'].includes(progress.value?.state))
const showProgress = computed(() => busy.value || (progress.value && progress.value.state !== 'idle'
  && !(progress.value.state === 'succeeded' && status.value?.update_available)))
const canOfferUpdate = computed(() => progress.value?.supported
  && status.value?.update_available && progress.value?.state !== 'interrupted')
const showInstallCard = computed(() => showProgress.value || canOfferUpdate.value || offline.value)
const progressPercent = computed(() => Math.min(100, Math.max(0, Number(progress.value?.progress) || 0)))
const installTitle = computed(() => {
  if (starting.value) return 'Starting your update'
  if (busy.value) return `Updating to ${progress.value?.version || status.value?.latest_version}`
  if (progress.value?.state === 'interrupted') return 'This update needs attention'
  if (progress.value?.state === 'failed') return 'The update could not finish'
  if (progress.value?.state === 'succeeded' && !canOfferUpdate.value) return `Updated to ${progress.value.version}`
  return 'Ready when you are'
})
const progressDescription = computed(() => {
  if (needsHostAttention.value) return 'Vueio has not reconnected yet. The update may still be running or need attention. Check its status on the host.'
  if (offline.value && busy.value) return 'Vueio is temporarily unavailable. Waiting for the update to reconnect…'
  if (awaitingReload.value) return 'The update is installed. Reconnecting to the new version…'
  if (starting.value) return 'Asking your host to start the update…'
  return progress.value?.message || 'Preparing the update…'
})

function refreshUpdates() {
  check({ refresh: true })
  readProgress()
}

const state = computed(() => status.value?.status || (loading.value ? 'checking' : 'unavailable'))
const channelLabel = computed(() => status.value?.channel === 'nightly' ? 'Nightly' : 'Stable')
const otherChannelLabel = computed(() => status.value?.channel === 'nightly' ? 'Stable' : 'Nightly')
const channelSwitchCommand = computed(() => `sudo vueioctl channel ${otherChannelLabel.value.toLowerCase()}`)
const channelDescription = computed(() => status.value?.channel === 'nightly'
  ? 'Nightly follows published test builds from the public nightly branch and includes Stable releases.'
  : 'Stable follows reviewed releases from the public stable branch. Switch to Nightly to receive test builds earlier.')
const channelSwitchNote = computed(() => status.value?.channel === 'nightly'
  ? 'Returning to Stable never downgrades Vue.io. If Nightly is ahead, Vue.io stays on it until a newer Stable release is available.'
  : state.value === 'ahead'
    ? 'Vue.io is following Stable now. The installed Nightly stays in place until Stable catches up.'
  : 'Switching channels changes which releases Vue.io offers. It does not install an update by itself.')
const releaseNotes = computed(() => {
  const pending = Array.isArray(status.value?.releases_between) ? status.value.releases_between : []
  const releases = pending.length ? pending : status.value?.current_release ? [status.value.current_release] : []
  return releases.map(release => ({
    ...release,
    sections: parseReleaseNotes(release.notes),
  }))
})
const releaseNotesTitle = computed(() => state.value === 'available' ? 'What’s new' : 'Current release')
const statusIcon = computed(() => ({
  available: '#icon-download',
  current: '#icon-check',
  ahead: '#icon-clock',
  development: '#icon-zap',
  error: '#icon-alert',
}[state.value] || '#icon-info'))
const statusEyebrow = computed(() => ({
  available: 'Update available',
  current: 'Up to date',
  ahead: `${channelLabel.value} catching up`,
  development: 'Development build',
  error: 'Check unavailable',
}[state.value] || 'Version status'))
const statusTitle = computed(() => ({
  available: `${status.value?.latest_version} is ready`,
  current: 'You are running the latest release',
  ahead: `This version is ahead of ${channelLabel.value}`,
  development: 'This installation is on a development build',
  error: 'Vue.io could not reach the release service',
}[state.value] || (loading.value ? 'Checking for updates' : 'Update checks are not configured')))
const statusDescription = computed(() => ({
  available: 'A newer release is available for this installation.',
  current: 'No action is needed.',
  ahead: `Vue.io will stay on this version until a newer ${channelLabel.value} release is published.`,
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

function parseReleaseNotes(value) {
  const sections = []
  let section = { title: '', items: [], paragraphs: [] }
  const commitSection = () => {
    if (section.title || section.items.length || section.paragraphs.length) sections.push(section)
  }

  for (const rawLine of String(value || 'Maintenance and reliability improvements.').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const heading = line.match(/^#{1,6}\s+(.+)$/)
    if (heading) {
      commitSection()
      section = { title: cleanMarkdownText(heading[1]), items: [], paragraphs: [] }
      continue
    }
    const item = line.match(/^[-*]\s+(.+)$/)
    if (item) section.items.push(cleanMarkdownText(item[1]))
    else section.paragraphs.push(cleanMarkdownText(line))
  }
  commitSection()
  return sections
}

function cleanMarkdownText(value) {
  return String(value || '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`(.+?)`/g, '$1')
}

async function copyCommand(command, successMessage) {
  try {
    await navigator.clipboard.writeText(command)
    notify(successMessage)
  } catch {
    notify('Could not copy the command.')
  }
}

onMounted(() => setVisible(true))
onUnmounted(() => setVisible(false))
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

.updates-status-card.is-ahead,
.updates-status-card.is-development {
  --updates-status-color: var(--v-warning);
}

.updates-status-card.is-error {
  --updates-status-color: var(--v-danger);
}

.updates-status-card.is-available,
.updates-status-card.is-current,
.updates-status-card.is-ahead,
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
.updates-status-card.is-ahead .updates-status-mark,
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
.updates-channel-card h3,
.updates-install-card h3,
.updates-setup-card h3 {
  margin: 2px 0 4px;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.updates-status-copy p:last-child,
.updates-channel-card p,
.updates-install-card p,
.updates-setup-card p,
.updates-fact > span:last-child {
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

.updates-install-card,
.updates-setup-card {
  display: grid;
  gap: var(--v-space-3);
  padding: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.updates-install-card.is-failed {
  border-color: color-mix(in srgb, var(--v-warning) 35%, var(--v-surface-border-soft));
}

.updates-install-card.is-complete {
  border-color: color-mix(in srgb, var(--v-accent) 28%, var(--v-surface-border-soft));
}

.updates-install-heading,
.updates-progress-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.updates-install-heading > div {
  min-width: 0;
}

.updates-install-heading h3 {
  overflow-wrap: anywhere;
}

.updates-install-button {
  flex: none;
}

.updates-install-button .icon {
  width: var(--v-space-4);
  height: var(--v-space-4);
}

.updates-install-progress {
  display: grid;
  gap: var(--v-space-2);
}

.updates-progress-label {
  align-items: baseline;
}

.updates-progress-label p {
  color: var(--v-text-secondary);
}

.updates-progress-label > span {
  color: var(--v-accent);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.updates-install-card .updates-install-note {
  margin-top: var(--v-space-1);
}

.updates-install-card .updates-install-error {
  color: var(--v-warning);
}

.updates-command-fallback {
  border-top: 1px solid var(--v-surface-border-soft);
  padding-top: var(--v-space-3);
}

.updates-command-fallback summary {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  cursor: pointer;
}

.updates-command-fallback[open] summary {
  margin-bottom: var(--v-space-3);
}

.updates-command-fallback summary:focus-visible {
  outline: 2px solid var(--v-accent);
  outline-offset: var(--v-space-1);
}

.updates-channel-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
  align-items: center;
  gap: 18px;
  padding: 16px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.updates-channel-card h3 {
  margin: 2px 0 4px;
}

.updates-channel-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.updates-branch-link {
  display: inline-flex;
  align-items: center;
  flex: none;
  gap: 5px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  text-decoration: none;
}

.updates-branch-link:hover {
  color: var(--v-text);
}

.updates-branch-link:focus-visible {
  border-radius: var(--v-radius-sm);
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.updates-branch-link .icon {
  width: 12px;
  height: 12px;
}

.updates-channel-card .updates-channel-note {
  margin-top: 7px;
  color: var(--v-text-secondary);
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

.updates-release-note-content {
  display: grid;
  gap: var(--v-space-3);
  margin-top: 10px;
}

.updates-release-note-content section {
  display: grid;
  gap: 6px;
}

.updates-release-note-content h4 {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.updates-release-note-content ul {
  display: grid;
  gap: 5px;
  margin: 0;
  padding-left: 18px;
}

.updates-release-note-content li,
.updates-release-note-content p {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.55;
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
  .updates-channel-card {
    grid-template-columns: 1fr;
  }

  .updates-channel-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .updates-channel-card,
  .updates-install-card,
  .updates-setup-card {
    gap: var(--v-space-3);
    padding: var(--v-space-3);
  }

  .updates-install-heading {
    align-items: stretch;
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .updates-install-button {
    min-height: 44px;
  }

  .updates-command-row {
    align-items: stretch;
    flex-direction: column;
  }

  .updates-command-row code {
    padding: 7px 8px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .updates-install-progress .v-progress-fill {
    transition: none;
  }

  .updates-settings-section .icon.spinning {
    animation: none;
  }
}
</style>
