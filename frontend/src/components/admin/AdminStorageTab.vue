<template>
  <section class="admin-section storage-settings-section">
    <AdminSettingsHeader
      eyebrow="System"
      title="Storage & previews"
      description="Manage generated media without touching the source files on your storage."
      icon="#icon-package"
    />

    <div class="storage-settings-body">
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
          {{ transcodesResetting ? 'Resetting' : 'Reset Transcodes' }}
        </button>
      </section>
    </div>
  </section>
</template>

<script setup>
import AdminSettingsHeader from './AdminSettingsHeader.vue'

defineProps({
  transcodesResetting: { type: Boolean, required: true },
})

defineEmits(['reset-transcodes'])
</script>

<style scoped>
.storage-settings-section {
  overflow: hidden;
}

.storage-settings-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 0.8fr);
  gap: var(--v-space-4);
  padding: 18px;
}

.storage-explainer {
  display: grid;
  gap: var(--v-space-2);
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
  background: color-mix(in srgb, var(--v-danger) 4%, var(--v-surface-inline));
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
  .storage-settings-body {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .storage-settings-body {
    gap: var(--v-space-3);
    padding: 12px;
  }
}
</style>
