<template>
  <section class="admin-section storage-settings-section">
    <AdminSettingsHeader
      :eyebrow="$route.query.setup === 'storage' ? 'Step 2 of 2 · Storage' : 'System'"
      :title="$route.query.setup === 'storage' ? 'Your workspace is ready' : 'Storage & previews'"
      :description="$route.query.setup === 'storage' ? 'Your account is created. Check the storage you chose in the installer, or connect another drive.' : 'Keep media on your own drives. Your accounts, comments and project history stay with this Vueio installation.'"
      icon="#icon-package"
    />

    <div class="storage-settings-body">
      <section class="storage-data v-surface-panel" aria-labelledby="storage-data-title">
        <div class="storage-explainer-icon" aria-hidden="true"><svg class="icon"><use href="#icon-lock" /></svg></div>
        <div class="storage-data-copy">
          <h3 id="storage-data-title">Your Vue data</h3>
          <p>Accounts, comments, projects, members and history live in your database. Keep it safe. Media storage is separate.</p>
          <p v-if="dataLocationLoading" role="status">Checking the data location…</p>
          <template v-else-if="dataLocation">
            <dl>
              <template v-if="dataLocation.folder"><dt>Data folder</dt><dd>{{ dataLocation.folder }}</dd></template>
              <template v-else-if="dataLocation.database_volume"><dt>Database</dt><dd>Docker volume · {{ dataLocation.database_volume }}</dd></template>
            </dl>
            <p v-if="!dataLocation.folder">This installation's database has not been moved. Run <code>vueioctl data</code> on the Vueio computer for its storage details.</p>
          </template>
          <p v-else role="status">The data location could not be checked. Run <code>vueioctl data</code> on the Vueio computer.</p>
          <details>
            <summary>What should I back up?</summary>
            <p>Use <code>vueioctl backup</code> on the Vueio computer for a consistent database backup. Linux installations require <code>sudo</code>. Keep a copy on a different drive.</p>
            <p>Database backups do not include app files, attachments, media or private configuration. Back up those separately. Previews can be rebuilt.</p>
            <p>Stop Vueio before copying the live database folder or disconnecting its drive. Do not move this folder while Vueio is running.</p>
            <dl v-if="dataLocation">
              <template v-if="dataLocation.database"><dt>Database</dt><dd>{{ dataLocation.database }}</dd></template>
              <template v-if="dataLocation.app_files"><dt>App files & previews</dt><dd>{{ dataLocation.app_files }}</dd></template>
              <template v-if="dataLocation.configuration"><dt>Private configuration</dt><dd>{{ dataLocation.configuration }}</dd></template>
              <template v-if="dataLocation.backups"><dt>Database backups</dt><dd>{{ dataLocation.backups }}</dd></template>
            </dl>
          </details>
        </div>
      </section>
      <section class="storage-locations" aria-labelledby="storage-locations-title">
        <header class="storage-locations-head">
          <div>
            <p class="settings-eyebrow">Project storage</p>
            <div class="storage-locations-title-row">
              <h3 id="storage-locations-title">Your storage</h3>
              <span v-if="storageRoots.length" class="storage-location-summary">
                {{ availableRootCount }} of {{ storageRoots.length }} connected
              </span>
            </div>
            <p>Choose a location when you create a project. Adding a drive does not move existing projects or share its files automatically.</p>
          </div>
          <button
            type="button"
            class="v-btn v-btn-secondary v-btn-sm"
            :disabled="storageRootsLoading"
            @click="refreshStorage"
          >
            <svg class="icon" :class="{ spinning: storageRootsLoading }"><use href="#icon-refresh" /></svg>
            {{ storageRootsLoading ? 'Checking' : 'Check again' }}
          </button>
        </header>

        <StorageDevicePicker ref="devicePicker" :secondary="$route.query.setup === 'storage' && storageRoots.length > 0" :has-offline="storageRoots.some(root => !root.available)" @changed="$emit('refresh-storage-roots')" />

        <div v-if="storageRootsLoading && !storageRoots.length" class="storage-location-state" role="status">
          <svg class="icon spinning"><use href="#icon-refresh" /></svg>
          <div>
            <strong>Checking storage locations</strong>
            <span>Vueio is verifying each connected device and its free space.</span>
          </div>
        </div>

        <div v-else-if="storageRootsError" class="storage-location-state is-warning" role="alert">
          <svg class="icon"><use href="#icon-alert" /></svg>
          <div>
            <strong>Storage locations could not be checked</strong>
            <span>{{ storageRootsError }}</span>
          </div>
        </div>

        <div v-else-if="!storageRoots.length" class="storage-location-state">
          <svg class="icon"><use href="#icon-folder" /></svg>
          <div>
            <strong>No storage locations connected</strong>
            <span>Connect a storage location to this Vueio installation before choosing it for a project.</span>
          </div>
        </div>

        <div v-else class="storage-location-grid">
          <article
            v-for="root in storageRoots"
            :key="root.id"
            class="storage-location-card"
            :class="rootClass(root)"
          >
            <div class="storage-location-card-head">
              <div class="storage-location-icon" aria-hidden="true">
                <svg class="icon"><use :href="rootIcon(root)" /></svg>
              </div>
              <div class="storage-location-name">
                <strong>{{ root.label }}</strong>
                <span>Project storage</span>
              </div>
              <span class="storage-location-status">
                <i aria-hidden="true"></i>
                {{ rootStatus(root) }}
              </span>
            </div>

            <template v-if="root.available && hasCapacity(root)">
              <div class="storage-capacity-copy">
                <strong>{{ formatSizeBytes(root.free_bytes, { compact: true }) }} free</strong>
                <span>of {{ formatSizeBytes(root.total_bytes, { compact: true }) }}</span>
              </div>
              <div
                class="v-progress storage-capacity-bar"
                role="progressbar"
                :aria-label="`${root.label} storage used`"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="usedPercent(root)"
              >
                <div class="v-progress-fill" :style="{ width: `${usedPercent(root)}%` }"></div>
              </div>
              <p class="storage-capacity-meta">{{ usedPercent(root) }}% used</p>
            </template>
            <p v-else-if="root.available" class="storage-location-message">Free space is not available right now.</p>
            <p v-else class="storage-location-message">Projects and comments are kept. Plug in the original drive, then reconnect it. Vueio will not use a different drive with the same name.</p>

            <p v-if="root.available && root.read_only" class="storage-location-note">
              Vueio can read this location but cannot create or move project files here.
            </p>
          </article>
        </div>
      </section>

      <div v-if="$route.query.setup === 'storage'" class="storage-setup-finish">
        <p v-if="writableRootCount">Storage is ready for your first project. You can add more drives in Settings at any time.</p>
        <p v-else>You can explore Vueio now and connect writable storage in Settings when you are ready to create projects.</p>
        <RouterLink class="v-btn v-btn-primary v-btn-lg storage-setup-done" :to="{ name: 'home' }">Open workspace</RouterLink>
      </div>

      <MediaProcessingPanel v-if="$route.query.setup !== 'storage'" />

      <div v-if="$route.query.setup !== 'storage'" class="storage-support-grid">
        <div class="storage-explainer">
          <div class="storage-explainer-item">
            <div class="storage-explainer-icon"><svg class="icon"><use href="#icon-lock" /></svg></div>
            <div>
              <strong>Source media stays safe</strong>
              <span>Resetting previews never edits or removes original files.</span>
            </div>
          </div>
          <div class="storage-explainer-item">
            <div class="storage-explainer-icon"><svg class="icon"><use href="#icon-refresh" /></svg></div>
            <div>
              <strong>Previews rebuild automatically</strong>
              <span>Vueio recreates a preview the next time that media is opened.</span>
            </div>
          </div>
        </div>

        <section class="storage-danger-zone">
          <div>
            <p class="settings-eyebrow">Preview cache</p>
            <h3>Reset all transcodes</h3>
            <p>Remove every generated HLS and MP4 preview. Use this when previews are stale, interrupted, or need to be rebuilt cleanly.</p>
          </div>
          <button class="v-btn v-btn-danger" :disabled="transcodesResetting" @click="$emit('reset-transcodes')">
            <svg class="icon" :class="{ spinning: transcodesResetting }"><use href="#icon-refresh" /></svg>
            {{ transcodesResetting ? 'Resetting' : 'Reset transcodes' }}
          </button>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import api from '../../lib/api'
import { formatSizeBytes } from '../../utils/formatters'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import StorageDevicePicker from './StorageDevicePicker.vue'
import MediaProcessingPanel from './MediaProcessingPanel.vue'

const props = defineProps({
  storageRoots: { type: Array, default: () => [] },
  storageRootsError: { type: String, default: '' },
  storageRootsLoading: { type: Boolean, default: false },
  transcodesResetting: { type: Boolean, required: true },
})

const emit = defineEmits(['refresh-storage-roots', 'reset-transcodes'])
const devicePicker = ref(null)
const dataLocation = ref(null)
const dataLocationLoading = ref(true)
const dataRequest = new AbortController()
onMounted(async () => {
  try {
    const { data } = await api.get('/api/admin/storage/data', { signal: dataRequest.signal })
    dataLocation.value = data
  } catch {
    dataLocation.value = null
  } finally {
    dataLocationLoading.value = false
  }
})
onBeforeUnmount(() => dataRequest.abort())

function refreshStorage() {
  emit('refresh-storage-roots')
  devicePicker.value?.refresh()
}

const writableRootCount = computed(() => props.storageRoots.filter(root => root.available && !root.read_only).length)
const availableRootCount = computed(() => props.storageRoots.filter(root => root.available).length)

function hasCapacity(root) {
  return Number.isFinite(Number(root?.free_bytes)) && Number(root?.total_bytes) > 0
}

function usedPercent(root) {
  if (!hasCapacity(root)) return 0
  return Math.max(0, Math.min(100, Math.round((1 - (Number(root.free_bytes) / Number(root.total_bytes))) * 100)))
}

function rootStatus(root) {
  if (!root.available) return 'Not connected'
  return root.read_only ? 'Read-only' : 'Available'
}

function rootIcon(root) {
  if (!root.available) return '#icon-alert'
  return root.read_only ? '#icon-lock' : '#icon-folder'
}

function rootClass(root) {
  return {
    'is-available': root.available && !root.read_only,
    'is-read-only': root.available && root.read_only,
    'is-unavailable': !root.available,
    'is-low-space': root.available && hasCapacity(root) && (Number(root.free_bytes) / Number(root.total_bytes)) <= 0.1,
  }
}
</script>

<style scoped>
.storage-data {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: var(--v-space-3);
  padding: var(--v-space-4);
}

.storage-data-copy { min-width: 0; }
.storage-data h3 { margin: 0; font-size: var(--v-text-md); }
.storage-data p { margin: var(--v-space-2) 0; color: var(--v-text-secondary); line-height: 1.5; }
.storage-data dl { display: grid; gap: var(--v-space-1); margin: var(--v-space-3) 0; }
.storage-data dt { margin-top: var(--v-space-2); color: var(--v-text-secondary); }
.storage-data dd { margin: 0; overflow-wrap: anywhere; }
.storage-data summary { cursor: pointer; padding: var(--v-space-2) 0; color: var(--v-accent); }
.storage-data summary:focus-visible { outline: 2px solid var(--v-accent); outline-offset: 2px; }
.storage-data code { overflow-wrap: anywhere; }

.storage-setup-finish {
  display: grid;
  justify-items: start;
  gap: var(--v-space-3);
  border-top: 1px solid var(--v-surface-border-soft);
  padding-top: var(--v-space-5);
}

.storage-setup-finish p {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-md);
  line-height: 1.5;
}

.storage-settings-section {
  overflow: hidden;
}

.storage-setup-done {
  align-self: flex-start;
  text-decoration: none;
}

.storage-settings-body {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
  padding-top: var(--v-space-4);
}

.storage-locations {
  display: grid;
  gap: var(--v-space-4);
  padding: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.storage-locations-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.storage-locations-head > div {
  min-width: 0;
}

.storage-locations-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2);
}

.storage-locations h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.storage-locations-head > div > p:last-child {
  max-width: 620px;
  margin: 6px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

.storage-location-summary,
.storage-location-status {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  line-height: 1;
}

.storage-location-summary {
  padding: 0 9px;
  color: var(--v-text-secondary);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.storage-location-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--v-space-3);
}

.storage-location-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 176px;
  padding: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-raised);
}

.storage-location-card.is-unavailable {
  background: color-mix(in srgb, var(--v-surface-raised) 54%, var(--v-surface-canvas));
}

.storage-location-card-head {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.storage-location-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-inset));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 17%, transparent);
}

.is-read-only .storage-location-icon,
.is-unavailable .storage-location-icon {
  color: var(--v-warning);
  background: color-mix(in srgb, var(--v-warning) 8%, var(--v-surface-inset));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-warning) 17%, transparent);
}

.storage-location-icon .icon {
  width: 15px;
  height: 15px;
}

.storage-location-name {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.storage-location-name strong {
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-md);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-location-name span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.storage-location-status {
  gap: 6px;
  padding: 0 8px;
  color: var(--v-accent);
  background: var(--v-accent-subtle);
}

.storage-location-status i {
  width: 6px;
  height: 6px;
  border-radius: var(--v-radius-full);
  background: currentColor;
}

.is-read-only .storage-location-status,
.is-unavailable .storage-location-status {
  color: var(--v-warning);
  background: var(--v-warning-bg);
}

.storage-capacity-copy {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin-top: var(--v-space-5);
}

.storage-capacity-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.storage-capacity-copy span,
.storage-capacity-meta,
.storage-location-message {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.storage-capacity-bar {
  height: 5px;
  margin-top: 9px;
}

.is-read-only .storage-capacity-bar .v-progress-fill,
.is-low-space .storage-capacity-bar .v-progress-fill {
  background: var(--v-warning);
}

.storage-capacity-meta,
.storage-location-message {
  margin: 7px 0 0;
  line-height: 1.4;
}

.storage-location-message {
  margin-top: auto;
  padding-top: var(--v-space-3);
}

.storage-location-card > .storage-location-note {
  margin-top: var(--v-space-3);
  padding-top: var(--v-space-3);
  border-top: 1px solid var(--v-divider-subtle);
  color: color-mix(in srgb, var(--v-warning) 75%, var(--v-text-muted));
}

.storage-location-state {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  min-height: 86px;
  padding: var(--v-space-4);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.storage-location-state > .icon {
  width: 18px;
  height: 18px;
  color: var(--v-accent);
  justify-self: center;
}

.storage-location-state.is-warning > .icon {
  color: var(--v-warning);
}

.storage-location-state div {
  display: grid;
  gap: 3px;
}

.storage-location-state strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
}

.storage-location-state span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.storage-support-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 0.8fr);
  gap: var(--v-space-4);
}

.storage-explainer {
  display: grid;
  gap: var(--v-space-1);
  padding: var(--v-space-2);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.storage-explainer-item {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  min-height: 72px;
  padding: var(--v-space-3);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.storage-explainer-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-inline));
}

.storage-explainer-icon .icon {
  width: 15px;
  height: 15px;
}

.storage-explainer-item div:last-child {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.storage-explainer-item strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
}

.storage-explainer-item span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.storage-danger-zone {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-direction: column;
  gap: var(--v-space-4);
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--v-danger) 24%, var(--v-border));
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-danger) 4%, var(--v-surface-canvas));
  box-shadow: var(--v-surface-shadow-raised);
}

.storage-danger-zone h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.storage-danger-zone p:last-child {
  margin: 6px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

@media (max-width: 900px) {
  .storage-support-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .storage-setup-done {
    width: 100%;
  }
  .storage-settings-body {
    gap: var(--v-space-3);
    padding-top: var(--v-space-3);
  }

  .storage-locations {
    padding: var(--v-space-3);
  }

  .storage-locations-head {
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .storage-locations-head .v-btn {
    width: 100%;
    min-height: 40px;
  }

  .storage-location-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 430px) {
  .storage-location-card-head {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .storage-location-status {
    grid-column: 1 / -1;
    justify-self: start;
    margin-top: 2px;
  }
}
</style>
