<template>
  <section class="admin-section storage-settings-section">
    <AdminSettingsHeader
      eyebrow="System"
      title="Storage & previews"
      description="See where Vueio can keep projects, then manage generated previews without touching source media."
      icon="#icon-package"
    />

    <div class="storage-settings-body">
      <section class="storage-locations" aria-labelledby="storage-locations-title">
        <header class="storage-locations-head">
          <div>
            <p class="settings-eyebrow">Project storage</p>
            <div class="storage-locations-title-row">
              <h3 id="storage-locations-title">Available locations</h3>
              <span v-if="storageRoots.length" class="storage-location-summary">
                {{ writableRootCount }} of {{ storageRoots.length }} ready
              </span>
            </div>
            <p>Vueio only shows storage locations connected to this installation. It verifies the expected device before using it.</p>
          </div>
          <button
            type="button"
            class="v-btn v-btn-secondary v-btn-sm"
            :disabled="storageRootsLoading"
            @click="$emit('refresh-storage-roots')"
          >
            <svg class="icon" :class="{ spinning: storageRootsLoading }"><use href="#icon-refresh" /></svg>
            {{ storageRootsLoading ? 'Checking' : 'Check again' }}
          </button>
        </header>

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
            <p v-else class="storage-location-message">Vueio cannot verify this location. Check that the expected storage device is connected and mounted.</p>

            <p v-if="root.available && root.read_only" class="storage-location-note">
              Vueio can read this location but cannot create or move project files here.
            </p>
          </article>
        </div>
      </section>

      <div class="storage-support-grid">
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
import { computed } from 'vue'
import { formatSizeBytes } from '../../utils/formatters'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

const props = defineProps({
  storageRoots: { type: Array, default: () => [] },
  storageRootsError: { type: String, default: '' },
  storageRootsLoading: { type: Boolean, default: false },
  transcodesResetting: { type: Boolean, required: true },
})

defineEmits(['refresh-storage-roots', 'reset-transcodes'])

const writableRootCount = computed(() => props.storageRoots.filter(root => root.available && !root.read_only).length)

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
.storage-settings-section {
  overflow: hidden;
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
