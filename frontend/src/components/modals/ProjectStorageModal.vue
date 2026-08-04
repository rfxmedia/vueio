<template>
  <VModal :model-value="show" size="lg" class="project-storage-modal" @update:model-value="close">
    <template #header>
      <VModalHeader
        eyebrow="Project storage"
        :title="isMigration ? 'Set project folder' : 'Relocate project'"
        :subtitle="isMigration ? 'Merge Vue-owned files into your working project folder.' : 'Tell Vue where the project folder lives now.'"
        @close="close"
      />
    </template>

    <div class="v-modal-stack project-storage-modal__body">
      <section v-if="stage === 'choose'" class="v-modal-section">
        <div class="v-modal-section-head">
          <h3 class="v-modal-section-title">Choose the project folder</h3>
          <p class="v-modal-section-copy">
            {{ isMigration
              ? 'Choose the existing working folder. Vue will copy only its internal files, without overwriting anything.'
              : 'Choose the folder after moving it yourself. Vue will only verify files and update its location.' }}
          </p>
        </div>
        <StorageFolderPicker
          :roots="availableRoots"
          :model-root="selectedRoot"
          :model-path="selectedPath"
          :allow-create="isMigration"
          @update:model-root="selectedRoot = $event"
          @update:model-path="selectedPath = $event"
        />
      </section>

      <section v-else class="v-modal-section">
        <div class="storage-plan-heading">
          <span class="storage-plan-heading__icon" :class="{ 'has-warning': hasWarnings }">
            <svg class="icon"><use :href="hasWarnings ? '#icon-alert' : '#icon-check'" /></svg>
          </span>
          <div>
            <h3>{{ planTitle }}</h3>
            <p>{{ planSummary }}</p>
          </div>
        </div>

        <div class="storage-plan-grid">
          <div class="storage-plan-stat">
            <span class="v-eyebrow">{{ isMigration ? 'Copy' : 'Matched' }}</span>
            <strong>{{ isMigration ? plan.copy_count : plan.matched_count }}</strong>
          </div>
          <div class="storage-plan-stat">
            <span class="v-eyebrow">{{ isMigration ? 'Already there' : 'Missing' }}</span>
            <strong>{{ isMigration ? plan.adopted_count : plan.missing_count }}</strong>
          </div>
          <div v-if="isMigration" class="storage-plan-stat" :class="{ 'is-danger': plan.conflict_count }">
            <span class="v-eyebrow">Conflicts</span>
            <strong>{{ plan.conflict_count }}</strong>
          </div>
        </div>

        <div v-if="isMigration && busy && migrationProgress" class="storage-copy-progress v-modal-card-soft">
          <div class="storage-copy-progress__label">
            <strong>{{ migrationProgress.total_files ? 'Copying & verifying' : 'Preparing migration' }}</strong>
            <span v-if="migrationProgress.total_files">{{ migrationProgress.completed_files }} / {{ migrationProgress.total_files }}</span>
          </div>
          <div class="v-progress"><div class="v-progress-fill" :style="{ width: `${migrationPercent}%` }"></div></div>
        </div>

        <div v-if="plan.conflicts?.length || plan.missing?.length" class="storage-plan-issues v-modal-card-soft">
          <div class="storage-plan-issues__head">
            <strong>{{ isMigration ? 'Resolve before continuing' : 'Files that will remain offline' }}</strong>
            <span>{{ (plan.conflicts || plan.missing || []).length }}</span>
          </div>
          <div class="storage-plan-issues__list">
            <div v-for="item in (plan.conflicts || plan.missing || []).slice(0, 30)" :key="`${item.asset_id || ''}:${item.path}`" class="storage-plan-issue">
              <span>{{ item.path }}</span>
              <small>{{ formatReason(item.reason) }}</small>
            </div>
          </div>
        </div>

        <VCheckbox
          v-if="!isMigration && !relinkBlocked"
          v-model="revokeShares"
          label="Deactivate all existing share links"
          hint="Optional cleanup when wrapping a project. Existing links stop working; you can still create new share links afterwards."
        />

        <div v-if="result?.old_path" class="storage-old-copy v-modal-card-soft">
          <svg class="icon"><use href="#icon-info" /></svg>
          <div>
            <strong>Original copy retained</strong>
            <p>{{ result.old_path }}</p>
          </div>
        </div>
      </section>

      <p v-if="error" class="v-inline-note project-storage-modal__error">{{ error }}</p>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" :disabled="busy" @click="stage === 'choose' ? close() : resetToPicker()">
        {{ stage === 'choose' ? 'Cancel' : result ? 'Close' : relinkBlocked ? 'Choose another folder' : 'Back' }}
      </button>
      <button
        v-if="stage === 'choose'"
        class="v-btn v-btn-primary"
        :disabled="!selectedRoot || !selectedPath || busy"
        @click="runDryRun"
      >
        {{ busy ? 'Checking…' : 'Verify location' }}
      </button>
      <button
        v-else-if="!result && !relinkBlocked"
        class="v-btn v-btn-primary"
        :disabled="busy || (isMigration && plan.conflict_count > 0)"
        @click="commit"
      >
        {{ busy ? (isMigration ? 'Copying & verifying…' : 'Relinking…') : (isMigration ? 'Migrate project' : 'Relink project') }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorDetail, getApiErrorMessage } from '../../lib/api'
import { VCheckbox, VModal, VModalHeader } from '../primitives'
import StorageFolderPicker from '../files/StorageFolderPicker.vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  project: { type: Object, default: null },
  roots: { type: Array, default: () => [] },
  mode: { type: String, default: 'relocate' },
})

const emit = defineEmits(['close', 'updated'])
const stage = ref('choose')
const selectedRoot = ref('')
const selectedPath = ref(null)
const revokeShares = ref(false)
const plan = ref({})
const result = ref(null)
const migrationProgress = ref(null)
const busy = ref(false)
const error = ref('')

const isMigration = computed(() => props.mode === 'migrate')
const availableRoots = computed(() => props.roots)
const relinkBlocked = computed(() => !isMigration.value && (
  plan.value.can_commit === false ||
  Number(plan.value.total_count || 0) === 0 ||
  Number(plan.value.matched_count || 0) === 0
))
const hasWarnings = computed(() => Boolean(isMigration.value ? plan.value.conflict_count : plan.value.missing_count || relinkBlocked.value))
const migrationPercent = computed(() => {
  const total = Number(migrationProgress.value?.total_files || 0)
  if (!total) return 6
  return Math.min(100, Math.round((Number(migrationProgress.value?.completed_files || 0) / total) * 100))
})
const planTitle = computed(() => {
  if (result.value) return isMigration.value ? 'Project folder is ready' : 'Project relinked'
  if (isMigration.value) return plan.value.conflict_count ? 'Conflicts need attention' : 'Safe to migrate'
  if (!Number(plan.value.total_count || 0)) return 'No tracked files to verify'
  if (!Number(plan.value.matched_count || 0)) return 'No matching files found'
  return plan.value.missing_count ? 'Location found with missing files' : 'All project files found'
})
const planSummary = computed(() => {
  if (result.value) return isMigration.value ? 'Vue is now using the selected working folder.' : 'Vue is now reading this project from the selected folder.'
  if (isMigration.value) return `${plan.value.copy_count || 0} files will be copied and ${plan.value.adopted_count || 0} identical files will be kept in place.`
  if (!Number(plan.value.total_count || 0)) return 'Vue did not find any tracked project files it can safely verify. Nothing will be changed.'
  if (!Number(plan.value.matched_count || 0)) return `None of the ${plan.value.total_count} tracked files matched this folder by path and size.`
  const summary = `${plan.value.matched_count || 0} of ${plan.value.total_count || 0} tracked files matched by relative path and size.`
  return plan.value.legacy_rebased_count
    ? `${summary} Vue safely resolved ${plan.value.legacy_rebased_count} legacy path${plan.value.legacy_rebased_count === 1 ? '' : 's'} from the previous folder hierarchy.`
    : summary
})

function reset() {
  stage.value = 'choose'
  plan.value = {}
  result.value = null
  migrationProgress.value = null
  error.value = ''
  revokeShares.value = false
  const roots = availableRoots.value
  const currentRoot = props.project?.storage_root
  selectedRoot.value = roots.some(root => root.id === currentRoot) ? currentRoot : (roots[0]?.id || '')
  selectedPath.value = null
}

function resetToPicker() {
  if (result.value) return close()
  stage.value = 'choose'
  error.value = ''
}

function close() {
  if (!busy.value) emit('close')
}

function endpoint() {
  return `/api/projects/${props.project.id}/${isMigration.value ? 'migrate-storage' : 'relocate'}`
}

function payload(dryRun) {
  if (isMigration.value) return { root: selectedRoot.value, path: selectedPath.value, dry_run: dryRun }
  return { root: selectedRoot.value, path: selectedPath.value, dry_run: dryRun, revoke_shares: revokeShares.value }
}

async function runDryRun() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await api.post(endpoint(), payload(true))
    plan.value = data
    stage.value = 'review'
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Unable to verify this project folder.')
  } finally {
    busy.value = false
  }
}

async function commit() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await api.post(endpoint(), payload(false))
    if (isMigration.value && data.job_id) {
      migrationProgress.value = data
      while (true) {
        await new Promise(resolve => window.setTimeout(resolve, 700))
        const { data: status } = await api.get(`${endpoint()}/status`, { params: { job_id: data.job_id } })
        migrationProgress.value = status
        if (status.status === 'error') {
          const message = typeof status.error === 'string' ? status.error : status.error?.message
          throw new Error(message || 'Project migration failed.')
        }
        if (status.status === 'complete') {
          result.value = status.result
          plan.value = status.result
          emit('updated', status.project)
          break
        }
      }
    } else {
      result.value = data
      plan.value = data
      emit('updated', data.project)
    }
  } catch (requestError) {
    const detail = getApiErrorDetail(requestError)
    error.value = typeof detail === 'string' ? detail : detail?.message || 'Project storage could not be updated.'
    if (detail?.plan) plan.value = detail.plan
  } finally {
    busy.value = false
  }
}

function formatReason(reason) {
  return ({ not_found: 'Not found', size_mismatch: 'Size differs', different_file: 'Different file exists', invalid_path: 'Invalid path' })[reason] || 'Needs attention'
}

watch(() => [props.show, props.mode, props.project?.id, props.roots.length], ([show]) => {
  if (show) reset()
}, { immediate: true })
</script>

<style scoped>
.project-storage-modal__body { min-height: 0; }
.storage-plan-heading { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: var(--v-space-3); align-items: center; }
.storage-plan-heading__icon { width: 42px; height: 42px; display: grid; place-items: center; border-radius: var(--v-radius-md); color: var(--v-accent); background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-raised)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 22%, transparent); }
.storage-plan-heading__icon.has-warning { color: var(--v-warning); background: color-mix(in srgb, var(--v-warning) 8%, var(--v-surface-raised)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-warning) 22%, transparent); }
.storage-plan-heading__icon .icon { width: 19px; height: 19px; }
.storage-plan-heading h3 { margin: 0; color: var(--v-text); font-size: var(--v-text-lg); }
.storage-plan-heading p { margin: 4px 0 0; color: var(--v-text-muted); font-size: var(--v-text-sm); line-height: 1.45; }
.storage-plan-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
.storage-plan-stat { padding: var(--v-space-3); border: 1px solid var(--v-surface-border-soft); border-radius: var(--v-radius-md); background: var(--v-surface-raised); box-shadow: var(--v-surface-shadow-raised); }
.storage-plan-stat span { display: block; }
.storage-plan-stat strong { display: block; margin-top: 5px; color: var(--v-text); font-size: 20px; font-variant-numeric: tabular-nums; }
.storage-plan-stat.is-danger strong { color: var(--v-danger); }
.storage-copy-progress { display: grid; gap: 9px; padding: var(--v-space-3); }
.storage-copy-progress__label { display: flex; align-items: center; justify-content: space-between; gap: var(--v-space-3); color: var(--v-text-muted); font-size: var(--v-text-xs); }
.storage-copy-progress__label strong { color: var(--v-text); font-size: var(--v-text-sm); }
.storage-copy-progress .v-progress-fill { min-width: 6%; transition: width 180ms ease; }
.storage-plan-issues { padding: 0; overflow: hidden; }
.storage-plan-issues__head { min-height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 12px; border-bottom: 1px solid var(--v-modal-divider); font-size: var(--v-text-sm); }
.storage-plan-issues__head span { color: var(--v-warning); font-variant-numeric: tabular-nums; }
.storage-plan-issues__list { max-height: 190px; overflow-y: auto; }
.storage-plan-issue { min-height: 38px; display: flex; align-items: center; justify-content: space-between; gap: var(--v-space-3); padding: 7px 12px; border-bottom: 1px solid var(--v-modal-divider); }
.storage-plan-issue:last-child { border-bottom: 0; }
.storage-plan-issue span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--v-text); font-size: var(--v-text-xs); }
.storage-plan-issue small { flex: 0 0 auto; color: var(--v-warning); font-size: var(--v-text-2xs); }
.storage-old-copy { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; padding: var(--v-space-3); color: var(--v-info); }
.storage-old-copy .icon { width: 17px; height: 17px; }
.storage-old-copy strong { color: var(--v-text); font-size: var(--v-text-sm); }
.storage-old-copy p { margin: 4px 0 0; overflow-wrap: anywhere; color: var(--v-text-muted); font-size: var(--v-text-xs); }
.project-storage-modal__error { color: var(--v-danger); }
@media (max-width: 548px) {
  .storage-plan-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .storage-plan-stat:nth-child(3) { grid-column: 1 / -1; }
}
</style>
