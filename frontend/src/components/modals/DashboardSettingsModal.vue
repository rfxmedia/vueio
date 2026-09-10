<template>
  <VModal
    :modelValue="show"
    size="sm"
    class="dashboard-settings-modal-shell"
    :presentation="isMobile ? 'sheet' : 'dialog'"
    @update:modelValue="close"
  >
    <template #header>
      <VModalHeader title="Dashboard settings" :subtitle="page?.title" @close="close" />
    </template>

    <VField label="Dashboard name">
      <input
        :value="draftTitle"
        class="v-input"
        :disabled="saving"
        placeholder="Untitled dashboard"
        @input="$emit('update:draftTitle', $event.target.value)"
      />
    </VField>
    <VField label="Description" hint="Shown on this dashboard and its share links.">
      <textarea
        :value="draftDescription"
        class="v-input ds-textarea"
        :disabled="saving"
        rows="4"
        placeholder="Add a short client-facing introduction…"
        @input="$emit('update:draftDescription', $event.target.value)"
      ></textarea>
    </VField>

    <template #footer>
      <button type="button" class="v-btn v-btn-secondary" @click="close">Close</button>
      <button
        type="button"
        class="v-btn v-btn-primary"
        :disabled="saving || !draftTitle.trim()"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save changes' }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { VField, VModal, VModalHeader } from '../primitives'

defineProps({
  show: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  page: { type: Object, default: null },
  saving: { type: Boolean, default: false },
  draftTitle: { type: String, default: '' },
  draftDescription: { type: String, default: '' },
  close: { type: Function, required: true },
  save: { type: Function, required: true },
})

defineEmits(['update:draftTitle', 'update:draftDescription'])
</script>

<style scoped>
:global(.dashboard-settings-modal-shell.v-modal-sm) {
  max-width: 480px;
}

.ds-textarea {
  min-height: 96px;
  line-height: 1.45;
  resize: vertical;
}
</style>
