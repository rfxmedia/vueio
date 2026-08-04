<template>
  <VModal
    :modelValue="show"
    size="sm"
    class="dashboard-settings-modal-shell"
    :presentation="isMobile ? 'sheet' : 'dialog'"
    @update:modelValue="close"
  >
    <template #header>
      <VModalHeader @close="close">
        <div class="ds-head">
          <span class="v-eyebrow">Dashboard Settings</span>
          <strong class="v-truncate">{{ page?.title || 'Dashboard' }}</strong>
        </div>
      </VModalHeader>
    </template>

    <section class="ds-section">
      <div class="ds-section-copy">
        <h3 class="v-section-label">Presentation</h3>
        <p>Set the title and introduction shown at the top of this dashboard and its share links.</p>
      </div>
      <label class="ds-field">
        <span>Dashboard name</span>
        <input
          :value="draftTitle"
          class="v-input"
          :disabled="saving"
          placeholder="Untitled dashboard"
          @input="$emit('update:draftTitle', $event.target.value)"
        />
      </label>
      <label class="ds-field">
        <span>Description</span>
        <textarea
          :value="draftDescription"
          class="v-input ds-textarea"
          :disabled="saving"
          rows="4"
          placeholder="Add a short client-facing introduction…"
          @input="$emit('update:draftDescription', $event.target.value)"
        ></textarea>
      </label>
    </section>

    <template #footer>
      <button type="button" class="v-btn v-btn-secondary" @click="close">Close</button>
      <button
        type="button"
        class="v-btn v-btn-primary"
        :disabled="saving || !draftTitle.trim()"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save Changes' }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { VModal, VModalHeader } from '../primitives'

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

.ds-head {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.ds-head > strong {
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  font-weight: 700;
}

.ds-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
  box-shadow: var(--v-surface-shadow-raised);
}

.ds-section-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ds-section-copy p {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.ds-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ds-field > span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 650;
}

.ds-field .v-input {
  color: var(--v-text);
  font-size: var(--v-text-md);
}

.ds-textarea {
  min-height: 96px;
  padding-block: 10px;
  line-height: 1.45;
  resize: vertical;
}

@media (max-width: 768px) {
  .ds-section {
    padding: var(--v-space-3);
  }
}
</style>
