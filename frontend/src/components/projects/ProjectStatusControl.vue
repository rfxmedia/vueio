<template>
  <span class="v-project-status-control" :class="[`is-${variant}`, { 'is-editable': editable, 'is-saving': saving }]" :aria-busy="saving" @click.stop @keydown.stop>
    <span class="v-project-status-marker" aria-hidden="true"></span>
    <span>{{ saving ? 'Saving…' : label }}</span>
    <svg v-if="editable" class="icon" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
    <select v-if="editable" :value="value" :disabled="saving" :aria-label="`Status for ${project.title}`" @change="changeStatus">
      <option v-for="option in PROJECT_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useProjectSettingsStore } from '../../ownership/projectSettings'
import { projectStatusVariant } from '../../composables/useContextNavigator'

const props = defineProps({
  project: { type: Object, required: true },
  editable: { type: Boolean, default: false },
})
const { PROJECT_STATUS_OPTIONS, projectStatusSavingIds, setProjectStatus } = useProjectSettingsStore()
const value = computed(() => props.project.status === 'active' ? 'in_progress' : props.project.status || 'not_started')
const variant = computed(() => projectStatusVariant(value.value))
const label = computed(() => PROJECT_STATUS_OPTIONS.find(option => option.value === value.value)?.label || value.value.replaceAll('_', ' '))
const saving = computed(() => projectStatusSavingIds.has(props.project.id))

async function changeStatus(event) {
  await setProjectStatus(props.project, event.target.value)
  event.target.value = value.value
}
</script>

<style scoped>
.v-project-status-control {
  --status-color: var(--v-status-draft);
  position: relative;
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  min-height: 28px;
  max-width: 100%;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-sm);
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
}
.is-active { --status-color: var(--v-status-active); }
.is-review { --status-color: var(--v-status-review); }
.is-hold { --status-color: var(--v-status-hold); }
.is-done { --status-color: var(--v-status-done); }
.is-editable { border-color: var(--v-control-border); background: var(--v-surface-inset); }
.is-editable:hover { border-color: var(--v-control-border-hover); background: var(--v-control-bg-hover); color: var(--v-text); }
.is-saving { opacity: 0.65; }
.v-project-status-marker { width: 6px; height: 6px; flex-shrink: 0; border-radius: 50%; background: var(--status-color); }
.icon { width: 12px; height: 12px; margin-left: 2px; color: var(--v-text-muted); }
select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
select:disabled { cursor: wait; }
.v-project-status-control:has(select:focus-visible) { outline: 2px solid var(--v-border-focus); outline-offset: 2px; }
@media (pointer: coarse) { .v-project-status-control { min-height: 36px; } }
</style>
