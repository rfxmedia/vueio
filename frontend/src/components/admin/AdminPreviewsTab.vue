<template>
  <section class="admin-section settings-stack">
    <AdminSettingsHeader
      title="Previews"
      description="Control how Vueio makes the previews your team and clients watch. Original media never changes."
      icon="#icon-video"
    />

    <MediaProcessingPanel>
      <template #cache>
        <div class="settings-row">
          <div class="settings-row-copy">
            <strong>Reset all previews</strong>
            <span>Remove every video preview now. Use this when previews look wrong or stopped. Each preview is rebuilt the next time someone opens it.</span>
          </div>
          <div class="settings-row-control">
            <button class="v-btn v-btn-danger v-btn-sm" type="button" :disabled="transcodesResetting" @click="$emit('reset-transcodes')">
              <svg class="icon" :class="{ spinning: transcodesResetting }"><use href="#icon-refresh" /></svg>
              {{ transcodesResetting ? 'Resetting' : 'Reset previews' }}
            </button>
          </div>
        </div>
      </template>
    </MediaProcessingPanel>
  </section>
</template>

<script setup>
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import MediaProcessingPanel from './MediaProcessingPanel.vue'

defineProps({
  transcodesResetting: { type: Boolean, required: true },
})

defineEmits(['reset-transcodes'])
</script>
