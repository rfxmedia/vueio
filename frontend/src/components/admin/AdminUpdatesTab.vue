<template>
  <section class="admin-section updates-settings-section">
    <AdminSettingsHeader title="Updates" icon="#icon-refresh">
      <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="loading || busy" @click="refreshUpdates">
        <svg class="icon" :class="{ spinning: loading }" aria-hidden="true"><use href="#icon-refresh" /></svg>
        {{ loading ? 'Checking…' : 'Refresh' }}
      </button>
    </AdminSettingsHeader>

    <div class="updates-body">
      <section class="updates-summary" aria-label="Version and update status">
        <dl class="updates-versions">
          <div>
            <dt>Current version</dt>
            <dd>{{ status?.current_version || 'Checking…' }}</dd>
          </div>
          <div>
            <dt>Latest version</dt>
            <dd>{{ status?.latest_version || (loading ? 'Checking…' : 'Unavailable') }}</dd>
          </div>
          <div>
            <dt>Channel</dt>
            <dd>
              <a v-if="status?.source_url" class="updates-link" :href="status.source_url" target="_blank" rel="noreferrer" :aria-label="`View ${channelLabel} branch on GitHub`">
                {{ channelLabel }}
                <svg class="icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
              </a>
              <span v-else>{{ status ? channelLabel : 'Checking…' }}</span>
            </dd>
          </div>
        </dl>

        <div class="updates-action-row">
          <p class="updates-status" :class="{ 'is-current': state === 'current' && !showProgress, 'is-warning': updateFailed }" role="status">
            <svg v-if="state === 'current' && !showProgress" class="icon" aria-hidden="true"><use href="#icon-check" /></svg>
            {{ showProgress ? installTitle : statusTitle }}
          </p>
          <button
            class="v-btn v-btn-primary updates-install-button"
            type="button"
            :disabled="!canOfferUpdate || busy || offline"
            @click="startUpdate"
          >
            <svg class="icon" :class="{ spinning: busy }" aria-hidden="true"><use :href="busy ? '#icon-refresh' : '#icon-download'" /></svg>
            {{ starting ? 'Starting…' : busy ? 'Updating…' : updateFailed ? 'Try again' : 'Update now' }}
          </button>
        </div>
        <p v-if="state === 'error' && showProgress && !busy" class="updates-error" role="status">Could not check for updates. {{ statusDescription }}</p>
        <p v-if="statusDescription && !showProgress" class="updates-muted">{{ statusDescription }}</p>
        <p v-if="canOfferUpdate && !showProgress" class="updates-muted">Backs up the database, then restarts Vueio.</p>

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
          <div v-if="needsHostAttention || progress?.state === 'interrupted'" class="updates-command-row">
            <code>{{ hostStatusCommand }}</code>
            <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy host status command" @click="copyCommand(hostStatusCommand, 'Status command copied.')">Copy</button>
          </div>
        </div>
        <p v-if="updateError && !updating" class="updates-error" role="status">{{ updateError }}</p>
        <p v-if="offline && !busy" class="updates-error" role="status">The updater is not responding. Checking again automatically.</p>
        <details v-if="progress?.supported === false" class="updates-details">
          <summary>Enable one-click updates</summary>
          <div class="updates-detail-content">
            <p>Run this once on your Vueio host to enable the update button.</p>
            <div class="updates-command-row">
              <code>{{ setupCommand }}</code>
              <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy update setup command" @click="copyCommand(setupCommand, 'Setup command copied.')">Copy</button>
            </div>
            <template v-if="status?.update_command">
              <p>Or update directly from the host:</p>
              <div class="updates-command-row">
                <code>{{ status.update_command }}</code>
                <button class="v-btn v-btn-secondary v-btn-sm" type="button" aria-label="Copy update command" @click="copyCommand(status.update_command, 'Update command copied.')">Copy</button>
              </div>
            </template>
          </div>
        </details>
      </section>

      <section class="updates-notes" aria-labelledby="updates-notes-title">
        <header class="updates-notes-heading">
          <h3 id="updates-notes-title">Release notes</h3>
          <a v-if="status?.release_url" class="updates-link" :href="status.release_url" target="_blank" rel="noreferrer">
            View on GitHub
            <svg class="icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
          </a>
        </header>
        <p v-if="!releaseNotes.length" class="updates-muted">{{ loading ? 'Loading release notes…' : 'No release notes available.' }}</p>
        <article v-for="release in releaseNotes" :key="release.version" class="updates-release-note">
          <header>
            <strong>{{ release.version }}</strong>
            <span v-if="release.nightly" class="updates-muted">Nightly</span>
            <time v-if="release.published_at" :datetime="release.published_at">{{ formatReleaseDate(release.published_at) }}</time>
          </header>
          <div class="updates-release-note-content">
            <section v-for="(section, sectionIndex) in release.sections" :key="`${release.version}-${sectionIndex}`">
              <h4 v-if="section.title">{{ section.title }}</h4>
              <ul v-if="section.items.length">
                <li v-for="(item, itemIndex) in section.items" :key="`${release.version}-${sectionIndex}-${itemIndex}`">{{ item }}</li>
              </ul>
              <p v-for="(paragraph, paragraphIndex) in section.paragraphs" :key="`${release.version}-${sectionIndex}-p-${paragraphIndex}`">{{ paragraph }}</p>
            </section>
          </div>
        </article>
      </section>

      <details class="updates-details">
        <summary>Update details</summary>
        <div class="updates-detail-content">
          <div>
            <h4>Backups and restart</h4>
            <p>Each update backs up the database and briefly restarts Vueio. Project files and original media stay in place. This page reconnects automatically; you can leave and return to see progress.</p>
          </div>
          <div>
            <h4>Release channel</h4>
            <p>{{ channelDescription }}</p>
            <p>{{ channelSwitchNote }}</p>
          </div>
          <div class="updates-command-row">
            <code>{{ channelSwitchCommand }}</code>
            <button class="v-btn v-btn-secondary v-btn-sm" type="button" :aria-label="`Copy command to switch to ${otherChannelLabel}`" :disabled="busy" @click="copyCommand(channelSwitchCommand, 'Channel command copied.')">Copy</button>
          </div>
        </div>
      </details>
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
const showProgress = computed(() => busy.value || updateFailed.value)
const canOfferUpdate = computed(() => progress.value?.supported
  && status.value?.update_available && progress.value?.state !== 'interrupted')
const progressPercent = computed(() => Math.min(100, Math.max(0, Number(progress.value?.progress) || 0)))
const installTitle = computed(() => {
  if (starting.value) return 'Starting your update'
  if (busy.value) return `Updating to ${progress.value?.version || status.value?.latest_version}`
  if (progress.value?.state === 'interrupted') return 'This update needs attention'
  if (progress.value?.state === 'failed') return 'The update could not finish'
  return 'Update available'
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
const statusTitle = computed(() => ({
  available: 'Update available',
  current: 'Up to date',
  ahead: `Ahead of ${channelLabel.value}`,
  development: 'Development build',
  error: 'Could not check for updates',
}[state.value] || (loading.value ? 'Checking for updates…' : 'Update checks are not configured')))
const statusDescription = computed(() => ({
  ahead: `This version stays installed until a newer ${channelLabel.value} release is available.`,
  development: 'Version comparisons are available for published releases.',
  error: 'Try refreshing when the server has internet access.',
  unavailable: 'Configure the public release repository to check for updates.',
}[state.value] || ''))

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
.updates-body {
  display: grid;
  gap: var(--v-space-6);
  padding-top: var(--v-space-4);
  min-width: 0;
}

.updates-summary {
  display: grid;
  gap: var(--v-space-3);
  min-width: 0;
  padding: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-canvas);
}

.updates-versions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: var(--v-space-4);
  margin: 0;
  padding-bottom: var(--v-space-4);
  border-bottom: 1px solid var(--v-surface-border-soft);
}

.updates-versions dt {
  margin-bottom: var(--v-space-1);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.updates-versions dd {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.updates-action-row,
.updates-progress-label,
.updates-notes-heading,
.updates-release-note header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.updates-status,
.updates-link {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
}

.updates-status {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
  min-width: 0;
}

.updates-status.is-current { color: var(--v-accent); }
.updates-status.is-warning,
.updates-error { color: var(--v-warning); }

.updates-install-button { flex: none; }

.updates-link {
  color: var(--v-text-secondary);
  text-decoration: none;
  font-size: var(--v-text-sm);
}

.updates-link:hover { color: var(--v-text); }
.updates-link:focus-visible,
.updates-details summary:focus-visible {
  outline: 2px solid var(--v-accent);
  outline-offset: var(--v-space-1);
  border-radius: var(--v-radius-sm);
}

.updates-link .icon { width: var(--v-space-3); height: var(--v-space-3); }
.updates-status .icon { width: var(--v-space-4); height: var(--v-space-4); flex: none; }

.updates-muted,
.updates-release-note time {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.updates-summary p,
.updates-notes p,
.updates-detail-content p { margin: 0; line-height: 1.55; }

.updates-install-progress,
.updates-release-note-content,
.updates-detail-content { display: grid; gap: var(--v-space-3); }

.updates-progress-label { align-items: baseline; color: var(--v-text-secondary); }
.updates-progress-label > span { flex: none; font-variant-numeric: tabular-nums; }

.updates-notes-heading { margin-bottom: var(--v-space-4); }
.updates-notes-heading h3 { margin: 0; font-size: var(--v-text-lg); }

.updates-release-note + .updates-release-note {
  margin-top: var(--v-space-5);
  padding-top: var(--v-space-5);
  border-top: 1px solid var(--v-surface-border-soft);
}

.updates-release-note header {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-bottom: var(--v-space-4);
  font-size: var(--v-text-sm);
}
.updates-release-note header strong { overflow-wrap: anywhere; min-width: 0; }
.updates-release-note time { margin-left: auto; }
.updates-release-note-content section { display: grid; gap: var(--v-space-1); }
.updates-release-note-content h4,
.updates-detail-content h4 {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
}
.updates-release-note-content ul {
  display: grid;
  gap: var(--v-space-1);
  padding-left: var(--v-space-4);
  margin: 0;
}
.updates-release-note-content li,
.updates-release-note-content p,
.updates-detail-content {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.updates-details {
  border-top: 1px solid var(--v-surface-border-soft);
  padding-top: var(--v-space-2);
}
.updates-details summary {
  padding-block: var(--v-space-3);
  color: var(--v-text-secondary);
  cursor: pointer;
  font-size: var(--v-text-sm);
}
.updates-detail-content { padding-top: var(--v-space-2); }
.updates-detail-content p + p { margin-top: var(--v-space-2); }

.updates-command-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
  padding: var(--v-space-2);
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-control-bg);
}
.updates-command-row code {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}
.updates-command-row .v-btn { flex: none; }
.updates-settings-section .icon.spinning { animation: v-spin 0.8s linear infinite; }

@media (max-width: 548px) {
  .updates-versions { grid-template-columns: minmax(0, 1fr); gap: var(--v-space-3); }
  .updates-versions > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); align-items: baseline; gap: var(--v-space-2); }
  .updates-versions dt { margin: 0; }
  .updates-action-row { flex-wrap: wrap; }
  .updates-install-button { width: 100%; min-height: var(--v-btn-height-lg); }
  .updates-notes-heading { flex-wrap: wrap; }
  .updates-summary { padding: var(--v-space-3); }
}

@media (prefers-reduced-motion: reduce) {
  .updates-install-progress .v-progress-fill { transition: none; }
  .updates-settings-section .icon.spinning { animation: none; }
}
</style>
