<template>
  <section class="admin-section settings-stack storage-settings-section">
    <AdminSettingsHeader
      :eyebrow="isSetup ? 'Step 2 of 2 · Storage' : ''"
      :title="isSetup ? 'Your workspace is ready' : 'Storage'"
      :description="isSetup ? 'Your account is created. Check the storage you chose in the installer, or connect another drive.' : 'Connect the drives that hold your media. You choose a drive when you create a project.'"
      icon="#icon-package"
    />

    <section class="settings-card" aria-labelledby="storage-locations-title">
      <header class="settings-card-head">
        <div>
          <h3 id="storage-locations-title">
            Drives
            <span v-if="storageRoots.length" class="settings-count-pill">{{ availableRootCount }} of {{ storageRoots.length }} connected</span>
          </h3>
          <p>Adding a drive does not move existing projects or share its files.</p>
        </div>
        <div class="settings-card-head-actions">
          <button
            type="button"
            class="v-btn v-btn-ghost v-btn-sm"
            :disabled="storageRootsLoading"
            @click="refreshStorage"
          >
            <svg class="icon" :class="{ spinning: storageRootsLoading }"><use href="#icon-refresh" /></svg>
            {{ storageRootsLoading ? 'Checking' : 'Check again' }}
          </button>
        </div>
      </header>

      <div class="settings-card-body">
        <div v-if="storageRootsLoading && !storageRoots.length" class="storage-location-state" role="status">
          <svg class="icon spinning"><use href="#icon-refresh" /></svg>
          <div>
            <strong>Checking storage locations</strong>
            <span>Vueio is checking each connected device and its free space.</span>
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
            <strong>No drives connected</strong>
            <span>Connect a drive to this Vueio installation before you choose it for a project.</span>
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
              </div>
              <span class="storage-location-status">
                <i aria-hidden="true"></i>
                {{ rootStatus(root) }}
              </span>
            </div>

            <template v-if="root.available && hasCapacity(root)">
              <div class="storage-capacity-copy">
                <strong>{{ formatSizeBytes(root.free_bytes, { compact: true }) }} free</strong>
                <span>of {{ formatSizeBytes(root.total_bytes, { compact: true }) }} · {{ usedPercent(root) }}% used</span>
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
            </template>
            <p v-else-if="root.available" class="storage-location-message">Free space is not available right now.</p>
            <p v-else class="storage-location-message">Projects and comments are kept. Plug in the original drive, then reconnect it. Vueio will not use a different drive with the same name.</p>

            <p v-if="root.available && root.read_only" class="storage-location-note">
              Vueio can read this drive but cannot create or move project files on it.
            </p>
          </article>
        </div>

        <StorageDevicePicker ref="devicePicker" :secondary="isSetup && storageRoots.length > 0" :has-offline="storageRoots.some(root => !root.available)" @changed="$emit('refresh-storage-roots')" />
      </div>
    </section>

    <div v-if="isSetup" class="storage-setup-finish">
      <p v-if="writableRootCount">Storage is ready for your first project. You can add more drives in Settings at any time.</p>
      <p v-else>You can explore Vueio now and connect writable storage in Settings when you are ready to create projects.</p>
      <RouterLink class="v-btn v-btn-primary v-btn-lg storage-setup-done" :to="{ name: 'home' }">Open workspace</RouterLink>
    </div>

    <section class="settings-card" aria-labelledby="storage-data-title">
      <header class="settings-card-head">
        <div>
          <h3 id="storage-data-title">Your Vueio data</h3>
          <p>Accounts, projects, comments, members and history are in the Vueio database. Media is stored separately on your drives.</p>
        </div>
      </header>
      <div class="settings-card-body storage-data">
        <p v-if="dataLocationLoading" role="status">Checking the data location…</p>
        <template v-else-if="dataLocation">
          <dl v-if="dataLocation.folder || dataLocation.database_volume">
            <template v-if="dataLocation.folder"><dt>Data folder</dt><dd>{{ dataLocation.folder }}</dd></template>
            <template v-else-if="dataLocation.database_volume"><dt>Database</dt><dd>Docker volume · {{ dataLocation.database_volume }}</dd></template>
          </dl>
          <p v-if="!dataLocation.folder">The database is in its default location. Run <code>vueioctl data</code> on the Vueio computer for details.</p>
        </template>
        <p v-else role="status">The data location could not be checked. Run <code>vueioctl data</code> on the Vueio computer.</p>
        <details>
          <summary>How do I back up Vueio?</summary>
          <p>Run <code>vueioctl backup</code> on the Vueio computer for a consistent database backup. Linux installations require <code>sudo</code>. Keep a copy on a different drive.</p>
          <p>Database backups do not include app files, attachments, media or private configuration. Back up those separately. Previews can be rebuilt.</p>
          <p>Stop Vueio before you copy the live database folder or disconnect its drive. Do not move this folder while Vueio is running.</p>
          <dl v-if="dataLocation">
            <template v-if="dataLocation.database"><dt>Database</dt><dd>{{ dataLocation.database }}</dd></template>
            <template v-if="dataLocation.app_files"><dt>App files and previews</dt><dd>{{ dataLocation.app_files }}</dd></template>
            <template v-if="dataLocation.configuration"><dt>Private configuration</dt><dd>{{ dataLocation.configuration }}</dd></template>
            <template v-if="dataLocation.backups"><dt>Database backups</dt><dd>{{ dataLocation.backups }}</dd></template>
          </dl>
        </details>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../../lib/api'
import { formatSizeBytes } from '../../utils/formatters'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import StorageDevicePicker from './StorageDevicePicker.vue'

const props = defineProps({
  storageRoots: { type: Array, default: () => [] },
  storageRootsError: { type: String, default: '' },
  storageRootsLoading: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh-storage-roots'])
const route = useRoute()
const isSetup = computed(() => route.query.setup === 'storage')
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
#storage-locations-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.storage-data {
  gap: var(--v-space-3);
}

.storage-data p {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.5;
}

.storage-data dl {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 16px;
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  font-size: var(--v-text-sm);
}

.storage-data dt {
  color: var(--v-text-muted);
}

.storage-data dd {
  margin: 0;
  color: var(--v-text-secondary);
  overflow-wrap: anywhere;
}

.storage-data details > p + p,
.storage-data details > dl {
  margin-top: var(--v-space-2);
}

.storage-data summary {
  width: fit-content;
  color: var(--v-accent-hover);
  font-size: var(--v-text-sm);
  font-weight: 600;
  cursor: pointer;
}

.storage-data summary:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: 2px;
}

.storage-data summary + p {
  margin-top: var(--v-space-2);
}

.storage-data code {
  overflow-wrap: anywhere;
}

.storage-setup-finish {
  display: grid;
  justify-items: start;
  gap: var(--v-space-3);
  padding: var(--v-space-2) 2px;
}

.storage-setup-finish p {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-md);
  line-height: 1.5;
}

.storage-setup-done {
  text-decoration: none;
}

.storage-location-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.storage-location-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-raised);
}

.storage-location-card.is-unavailable {
  background: transparent;
}

.storage-location-card-head {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.storage-location-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-sm);
  color: var(--v-accent);
  background: var(--v-accent-muted);
}

.is-read-only .storage-location-icon,
.is-unavailable .storage-location-icon {
  color: var(--v-warning);
  background: var(--v-warning-bg);
}

.storage-location-icon .icon {
  width: 15px;
  height: 15px;
}

.storage-location-name {
  min-width: 0;
}

.storage-location-name strong {
  display: block;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-location-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  color: var(--v-accent);
  background: var(--v-accent-subtle);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
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
  flex-wrap: wrap;
  gap: 4px 6px;
  margin-top: 16px;
}

.storage-capacity-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.storage-capacity-copy span,
.storage-location-message {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.storage-capacity-bar {
  height: 5px;
  margin-top: 8px;
}

.is-read-only .storage-capacity-bar .v-progress-fill,
.is-low-space .storage-capacity-bar .v-progress-fill {
  background: var(--v-warning);
}

.storage-location-message {
  margin: 12px 0 0;
  line-height: 1.45;
}

.storage-location-note {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--v-divider-subtle);
  color: color-mix(in srgb, var(--v-warning) 75%, var(--v-text-muted));
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.storage-location-state {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  padding: 16px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
}

.storage-location-state > .icon {
  justify-self: center;
  width: 18px;
  height: 18px;
  color: var(--v-accent);
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
  font-weight: 600;
}

.storage-location-state span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

@media (max-width: 768px) {
  .storage-setup-done {
    width: 100%;
  }

  .storage-location-grid {
    grid-template-columns: 1fr;
  }

  .storage-data dl {
    grid-template-columns: 1fr;
    gap: 2px;
  }

  .storage-data dd + dt {
    margin-top: 8px;
  }
}
</style>
