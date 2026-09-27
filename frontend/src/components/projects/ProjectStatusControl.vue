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
import { canonicalProjectStatus, projectStatusLabel, useProjectSettingsStore } from '../../ownership/projectSettings'
import { projectStatusVariant } from '../../composables/useContextNavigator'

const props = defineProps({
  project: { type: Object, required: true },
  editable: { type: Boolean, default: false },
})
const { PROJECT_STATUS_OPTIONS, projectStatusSavingIds, setProjectStatus } = useProjectSettingsStore()
const value = computed(() => canonicalProjectStatus(props.project.status))
const variant = computed(() => projectStatusVariant(value.value))
const label = computed(() => projectStatusLabel(value.value))
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
  min-height: 26px;
  max-width: 100%;
  padding: 0 8px 0 9px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
}
.is-active { --status-color: var(--v-status-active); }
.is-review { --status-color: var(--v-status-review); }
.is-hold { --status-color: var(--v-status-hold); }
.is-done { --status-color: var(--v-status-done); }
/* A tinted pill reads as status first and control second. */
.v-project-status-control { background: color-mix(in srgb, var(--status-color) 11%, transparent); color: color-mix(in srgb, var(--status-color) 42%, var(--v-text)); }
.is-editable { cursor: pointer; transition: background var(--v-duration-fast) var(--v-ease-soft), border-color var(--v-duration-fast) var(--v-ease-soft); }
.is-editable:hover { border-color: color-mix(in srgb, var(--status-color) 30%, transparent); background: color-mix(in srgb, var(--status-color) 17%, transparent); color: var(--v-text); }
.is-saving { opacity: 0.65; }
.v-project-status-marker { width: 6px; height: 6px; flex-shrink: 0; border-radius: 50%; background: var(--status-color); }
.icon { width: 11px; height: 11px; margin-left: 1px; opacity: 0.7; }
select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
select:disabled { cursor: wait; }
.v-project-status-control:has(select:focus-visible) { outline: 2px solid var(--v-border-focus); outline-offset: 2px; }
@media (pointer: coarse) { .v-project-status-control { min-height: 36px; } }
</style>
