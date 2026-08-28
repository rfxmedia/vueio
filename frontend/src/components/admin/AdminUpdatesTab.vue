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
          View on GitHub
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

      <section class="updates-channel-card" aria-labelledby="updates-channel-title">
        <div class="updates-channel-copy">
          <p class="settings-eyebrow">Release channel</p>
          <h3 id="updates-channel-title">Following {{ channelLabel }}</h3>
          <p>{{ channelDescription }}</p>
          <p class="updates-channel-note">{{ channelSwitchNote }}</p>
        </div>
        <div class="updates-command-row">
          <code>{{ channelSwitchCommand }}</code>
          <button
            class="v-btn v-btn-secondary v-btn-sm"
            type="button"
            :aria-label="`Copy command to switch to ${otherChannelLabel}`"
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
          <button
            class="v-btn v-btn-primary v-btn-sm"
            type="button"
            aria-label="Copy update command"
            @click="copyCommand(status.update_command, 'Update command copied.')"
          >
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
const otherChannelLabel = computed(() => status.value?.channel === 'nightly' ? 'Stable' : 'Nightly')
const channelSwitchCommand = computed(() => `sudo vueioctl channel ${otherChannelLabel.value.toLowerCase()}`)
const channelDescription = computed(() => status.value?.channel === 'nightly'
  ? 'Nightly includes early development builds as well as Stable releases.'
  : 'Stable includes reviewed releases only. Switch to Nightly to receive development builds earlier.')
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
  available: 'A newer tested self-hosted release is available when you are ready.',
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
.updates-command-card h3 {
  margin: 2px 0 4px;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.updates-status-copy p:last-child,
.updates-channel-card p,
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
  .updates-channel-card,
  .updates-command-card {
    grid-template-columns: 1fr;
  }

  .updates-channel-card,
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
