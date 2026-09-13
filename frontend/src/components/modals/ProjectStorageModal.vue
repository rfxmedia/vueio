<template>
  <VModal :model-value="show" size="lg" class="project-storage-modal" @update:model-value="close">
    <template #header>
      <VModalHeader
        title="Project folder"
        subtitle="Choose where Vue reads this project's files."
        @close="close"
      />
    </template>

    <div class="v-modal-stack project-storage-modal__body">
      <section v-if="stage === 'choose'" class="v-modal-section">
        <VTabs
          :model-value="actionMode"
          :tabs="folderActions"
          variant="segmented"
          full-width
          aria-label="Project folder action"
          @update:model-value="changeAction"
        />
        <div class="v-modal-section-head">
          <h3 class="v-modal-section-title">{{ isMissingMediaRelink ? 'Choose where to search' : 'Choose the project folder' }}</h3>
          <p class="v-modal-section-copy">
            {{ isMissingMediaRelink
              ? 'Vue will search this folder and its subfolders for exact matches. Your working project folder will not change.'
              : isMigration
              ? 'Choose the existing working folder. Vue will copy only its internal files, without overwriting anything.'
              : 'Choose the folder that contains your files. Vue will only update their location. Read-only folders work too.' }}
          </p>
        </div>
        <StorageFolderPicker
          :key="actionMode"
          :roots="availableRoots"
          :model-root="selectedRoot"
          :model-path="selectedPath"
          :allow-create="isMigration"
          :disabled="busy"
          :base-path="isMissingMediaRelink ? projectBasePath : ''"
          @update:model-root="selectedRoot = $event"
          @update:model-path="selectedPath = $event"
        />
        <VCheckbox
          v-if="project?.uses_internal_storage && !isMissingMediaRelink"
          v-model="copyInternalFiles"
          :disabled="busy"
          label="Copy Vue's internal files into this folder"
          :hint="copyBlocked ? 'This folder is read-only. Turn off copying to use files already here.' : 'Leave this off if you already moved the files. The original copy is kept.'"
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

        <p class="storage-plan-location v-modal-card-soft">
          <span class="v-eyebrow">{{ isMissingMediaRelink ? 'Search folder' : 'Project folder' }}</span>
          <strong>{{ availableRoots.find(root => root.id === plan.root)?.label || plan.root }} / {{ plan.path }}</strong>
        </p>

        <div v-if="!nothingToReconnect" class="storage-plan-grid">
          <div class="storage-plan-stat">
            <span class="v-eyebrow">{{ isMigration ? 'Copy' : isMissingMediaRelink ? 'Found' : 'Matched' }}</span>
            <strong>{{ isMigration ? plan.copy_count : matchedCount }}</strong>
          </div>
          <div class="storage-plan-stat">
            <span class="v-eyebrow">{{ isMigration ? 'Already there' : 'Needs attention' }}</span>
            <strong>{{ isMigration ? plan.adopted_count : missingCount }}</strong>
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

        <p v-if="isRelocation && plan.read_only" class="v-inline-note">Read-only folder. Playback and downloads remain available.</p>
        <div v-if="planIssues.length" class="storage-plan-issues v-modal-card-soft">
          <div class="storage-plan-issues__head">
            <strong>{{ isMigration ? 'Resolve before continuing' : isMissingMediaRelink ? 'Media still offline' : 'Files that will remain offline' }}</strong>
            <span>{{ planIssues.length }}</span>
          </div>
          <div class="storage-plan-issues__list">
            <div v-for="item in planIssues.slice(0, 30)" :key="`${item.asset_id || item.link_index || ''}:${item.path || item.source_path}`" class="storage-plan-issue">
              <span>{{ item.path || item.source_path }}</span>
              <small>{{ formatReason(item.reason) }}</small>
            </div>
          </div>
        </div>

        <p v-if="isRelocation && !relinkBlocked" class="v-inline-note">Your shots, comments, and share links stay with this project.</p>

        <div v-if="result?.old_path" class="storage-old-copy v-modal-card-soft">
          <svg class="icon"><use href="#icon-info" /></svg>
          <div>
            <strong>Original copy retained</strong>
            <p>{{ result.old_path }}</p>
          </div>
        </div>
      </section>

      <p v-if="error" role="alert" class="v-inline-note project-storage-modal__error">{{ error }}</p>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" :disabled="busy" @click="stage === 'choose' || nothingToReconnect ? close() : resetToPicker()">
        {{ stage === 'choose' ? 'Cancel' : nothingToReconnect ? 'Done' : result ? 'Close' : relinkBlocked ? 'Choose another folder' : 'Back' }}
      </button>
      <button
        v-if="stage === 'choose'"
        class="v-btn v-btn-primary"
        :disabled="!selectedRoot || !selectedPath || busy || copyBlocked"
        @click="runDryRun"
      >
        {{ busy ? (isMissingMediaRelink ? 'Searching…' : 'Checking…') : (isMissingMediaRelink ? 'Search folder' : 'Check folder') }}
      </button>
      <button
        v-else-if="!result && !relinkBlocked"
        class="v-btn v-btn-primary"
        :disabled="busy || (isMigration && plan.conflict_count > 0)"
        @click="commit"
      >
        {{ commitLabel }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorDetail, getApiErrorMessage } from '../../lib/api'
import { VCheckbox, VModal, VModalHeader, VTabs } from '../primitives'
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
const actionMode = ref('relocate')
const copyInternalFiles = ref(false)
const plan = ref({})
const result = ref(null)
const migrationProgress = ref(null)
const busy = ref(false)
const error = ref('')

const isMissingMediaRelink = computed(() => actionMode.value === 'relink-media')
const isMigration = computed(() => !isMissingMediaRelink.value && props.project?.uses_internal_storage && copyInternalFiles.value)
const isRelocation = computed(() => !isMigration.value && !isMissingMediaRelink.value)
const folderActions = computed(() => [
  { value: 'relocate', label: 'Change folder', icon: '#icon-folder', disabled: busy.value },
  { value: 'relink-media', label: 'Find moved files', icon: '#icon-search', disabled: busy.value },
])
const copyBlocked = computed(() => isMigration.value && props.roots.find(root => root.id === selectedRoot.value)?.read_only)
const matchedCount = computed(() => Number(plan.value.matched_count || 0) + Number(plan.value.link_matched_count || 0))
const missingCount = computed(() => Number(plan.value.missing_count || 0) + Number(plan.value.link_missing_count || 0))
const totalCount = computed(() => matchedCount.value + missingCount.value)
const planIssues = computed(() => isMigration.value ? plan.value.conflicts || [] : [...(plan.value.missing || []), ...(plan.value.link_missing || [])])
const projectBasePath = computed(() => String(props.project?.storage_path || props.project?.id || '').replace(/^\/+|\/+$/g, ''))
const availableRoots = computed(() => {
  if (!isMissingMediaRelink.value) return props.roots
  const currentRoot = props.project?.storage_root || 'data'
  const configured = props.roots.find(root => root.id === currentRoot)
  if (configured) return [configured]
  if (currentRoot === 'data') {
    return [{ id: 'data', label: 'Vue internal storage', available: true, read_only: false }]
  }
  return []
})
const relinkBlocked = computed(() => !isMigration.value && !plan.value.can_commit)
const nothingToReconnect = computed(() => stage.value === 'review' && isMissingMediaRelink.value && !totalCount.value)
const hasWarnings = computed(() => !nothingToReconnect.value && Boolean(isMigration.value ? plan.value.conflict_count : missingCount.value || relinkBlocked.value))
const migrationPercent = computed(() => {
  const total = Number(migrationProgress.value?.total_files || 0)
  if (!total) return 6
  return Math.min(100, Math.round((Number(migrationProgress.value?.completed_files || 0) / total) * 100))
})
const planTitle = computed(() => {
  if (result.value) {
    if (isMissingMediaRelink.value) return 'Missing media relinked'
    return isMigration.value ? 'Project folder is ready' : 'Project relinked'
  }
  if (isMigration.value) return plan.value.conflict_count ? 'Conflicts need attention' : 'Ready to copy'
  if (isMissingMediaRelink.value) {
    if (!Number(plan.value.total_count || 0)) return 'Nothing to reconnect'
    if (!Number(plan.value.matched_count || 0)) return 'No exact matches found'
    return plan.value.missing_count ? 'Some media found' : 'All missing media found'
  }
  if (!totalCount.value) return 'Ready to use this folder'
  if (!matchedCount.value) return 'No matching files found'
  return missingCount.value ? 'Some files need attention' : 'All tracked media found'
})
const planSummary = computed(() => {
  if (result.value) {
    if (isMissingMediaRelink.value) {
      const count = Number(plan.value.relinked_count || plan.value.matched_count || 0)
      return `${count} file${count === 1 ? '' : 's'} reconnected. The working project folder was not changed.`
    }
    return isMigration.value ? 'Vue is now using the selected working folder.' : 'Vue is now reading this project from the selected folder.'
  }
  if (isMigration.value) return `${plan.value.copy_count || 0} files will be copied and ${plan.value.adopted_count || 0} identical files will be kept in place.`
  if (isMissingMediaRelink.value) {
    if (!Number(plan.value.total_count || 0)) return 'This project no longer has any offline media.'
    if (!Number(plan.value.matched_count || 0)) return `None of the ${plan.value.total_count} missing files could be verified in this folder. Nothing will be changed.`
    const count = Number(plan.value.matched_count || 0)
    const remaining = Number(plan.value.missing_count || 0)
    return `${count} of ${plan.value.total_count} missing files matched by exact media identity.${remaining ? ` ${remaining} will remain offline.` : ''}`
  }
  if (!totalCount.value) return 'There are no registered media files to reconnect. Vue will use this folder without copying or moving its contents.'
  if (!matchedCount.value) return `None of the ${totalCount.value} registered items matched. Your current project folder will not change.`
  return `${matchedCount.value} of ${totalCount.value} registered items verified.${missingCount.value ? ` ${missingCount.value} will remain unavailable.` : ''}`
})

function reset() {
  stage.value = 'choose'
  plan.value = {}
  result.value = null
  migrationProgress.value = null
  error.value = ''
  actionMode.value = props.mode === 'relink-media' ? 'relink-media' : 'relocate'
  copyInternalFiles.value = props.mode === 'migrate'
  resetSelection()
}

function resetSelection() {
  const roots = availableRoots.value
  const currentRoot = props.project?.storage_root
  selectedRoot.value = roots.some(root => root.id === currentRoot) ? currentRoot : (roots[0]?.id || '')
  selectedPath.value = isMissingMediaRelink.value ? projectBasePath.value : null
}

function changeAction(mode) {
  if (busy.value) return
  actionMode.value = mode
  error.value = ''
  plan.value = {}
  resetSelection()
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
  if (isMissingMediaRelink.value) return `/api/projects/${props.project.id}/relink-media`
  return `/api/projects/${props.project.id}/${isMigration.value ? 'migrate-storage' : 'relocate'}`
}

function payload(dryRun) {
  return { root: selectedRoot.value, path: selectedPath.value, dry_run: dryRun,
    ...(!dryRun && plan.value.plan_id ? { plan_id: plan.value.plan_id } : {}) }
}

async function runDryRun() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await api.post(endpoint(), payload(true))
    plan.value = data
    stage.value = 'review'
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, isMissingMediaRelink.value ? 'Unable to search for missing media.' : 'Unable to verify this project folder.')
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
    error.value = typeof detail === 'string' ? detail : detail?.message || (isMissingMediaRelink.value ? 'Missing media could not be relinked.' : 'Project storage could not be updated.')
    if (detail?.plan) plan.value = detail.plan
    else if (!isMigration.value) stage.value = 'choose'
  } finally {
    busy.value = false
  }
}

function formatReason(reason) {
  return ({
    not_found: 'Not found',
    size_mismatch: 'Size differs',
    content_mismatch: 'File contents differ',
    different_file: 'Different file exists',
    invalid_path: 'Invalid path',
    ambiguous_match: 'Multiple exact copies',
    identity_unavailable: 'No identity on record',
    generated_media: 'Regenerated automatically',
    destination_already_matched: 'Match is not unique',
    destination_already_registered: 'Already linked elsewhere',
  })[reason] || 'Needs attention'
}

const commitLabel = computed(() => {
  if (busy.value) {
    if (isMigration.value) return 'Copying & verifying…'
    return isMissingMediaRelink.value ? 'Relinking media…' : 'Relinking…'
  }
  if (isMigration.value) return 'Copy files & set folder'
  return isMissingMediaRelink.value ? 'Reconnect files' : 'Use this folder'
})

watch(() => [props.show, props.mode, props.project?.id, props.roots.length], ([show]) => {
  if (show && !busy.value) reset()
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
.storage-plan-location { display: grid; gap: var(--v-space-1); margin: 0; padding: var(--v-space-3); }
.storage-plan-location strong { overflow-wrap: anywhere; font-size: var(--v-text-sm); }
.storage-plan-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(0, 1fr)); grid-auto-flow: column; gap: 9px; }
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
.storage-plan-issue span { min-width: 0; overflow-wrap: anywhere; color: var(--v-text); font-size: var(--v-text-xs); }
.storage-plan-issue small { flex: 0 0 auto; color: var(--v-warning); font-size: var(--v-text-2xs); }
.storage-old-copy { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; padding: var(--v-space-3); color: var(--v-info); }
.storage-old-copy .icon { width: 17px; height: 17px; }
.storage-old-copy strong { color: var(--v-text); font-size: var(--v-text-sm); }
.storage-old-copy p { margin: 4px 0 0; overflow-wrap: anywhere; color: var(--v-text-muted); font-size: var(--v-text-xs); }
.project-storage-modal__error { color: var(--v-danger); }
@media (max-width: 548px) {
  .storage-plan-issue { align-items: flex-start; flex-direction: column; gap: var(--v-space-1); }
  .storage-plan-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-flow: row; }
  .storage-plan-stat:nth-child(3) { grid-column: 1 / -1; }
}
</style>
