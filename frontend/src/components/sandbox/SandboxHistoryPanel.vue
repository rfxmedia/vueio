<template>
  <aside class="sbh" aria-label="Version history">
    <header class="sbh-head">
      <div>
        <h3 class="sbh-title">History</h3>
        <p class="sbh-sub">{{ subtitle }}</p>
      </div>
      <button type="button" class="v-icon-action is-muted" aria-label="Close history" title="Close" @click="$emit('close')">
        <svg class="icon" aria-hidden="true"><use href="#icon-close" /></svg>
      </button>
    </header>

    <div v-if="error" class="sbh-state is-error">
      <span>{{ error }}</span>
      <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="load()">Try again</button>
    </div>
    <div v-else-if="!versions.length && loading" class="sbh-state">Loading versions…</div>
    <div v-else-if="!versions.length" class="sbh-state">No saved versions yet. Each save adds one here.</div>

    <ol v-else class="sbh-list">
      <template v-for="group in groups" :key="group.label">
        <li class="sbh-day v-section-label">{{ group.label }}</li>
        <li v-for="version in group.versions" :key="version.number">
          <button
            type="button"
            class="sbh-item"
            :class="{ 'is-selected': version.number === selectedNumber, 'is-current': version.number === latestVersion }"
            :aria-current="version.number === selectedNumber ? 'true' : undefined"
            @click="$emit('select', version.number)"
          >
            <span class="sbh-dot" aria-hidden="true"></span>
            <span class="sbh-main">
              <span class="sbh-line">
                <strong class="sbh-number">Version {{ version.number }}</strong>
                <span v-if="version.number === latestVersion" class="sbh-badge">Current</span>
                <time class="sbh-time" :datetime="isoTime(version.created_at)" :title="absoluteTime(version.created_at)">{{ clockTime(version.created_at) }}</time>
              </span>
              <span class="sbh-message">{{ describe(version) }}</span>
              <span class="sbh-meta">
                {{ version.author_name || 'Someone' }}<template v-if="version.agent_name"> · <span class="sbh-agent"><svg class="icon" aria-hidden="true"><use href="#icon-sparkles" /></svg>{{ version.agent_name }}</span></template>
                · {{ formatSize(version.size_bytes) }}
              </span>
            </span>
          </button>
        </li>
      </template>
    </ol>

    <div v-if="nextBefore" class="sbh-more">
      <button type="button" class="v-btn v-btn-quiet v-btn-sm" :disabled="loading" @click="load({ more: true })">Show older versions</button>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'
import { formatActivityAbsoluteTimestamp, formatIsoTimestamp, formatLocaleDate, formatLocaleTime, formatSizeBytes } from '../../utils/formatters'

const props = defineProps({
  projectId: { type: String, required: true },
  sandboxId: { type: String, required: true },
  latestVersion: { type: Number, default: 0 },
  selectedNumber: { type: Number, default: null },
})
defineEmits(['select', 'close'])

const versions = ref([])
const nextBefore = ref(null)
const loading = ref(false)
const error = ref('')
let requestId = 0

async function load({ more = false } = {}) {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/projects/${props.projectId}/sandboxes/${props.sandboxId}/versions`, {
      params: { limit: 100, ...(more && nextBefore.value ? { before: nextBefore.value } : {}) },
    })
    if (id !== requestId) return
    versions.value = more ? [...versions.value, ...data.versions] : data.versions
    nextBefore.value = data.next_before
  } catch (loadError) {
    if (id === requestId) error.value = getApiErrorMessage(loadError, 'Could not load the history.')
  } finally {
    if (id === requestId) loading.value = false
  }
}

watch(() => [props.sandboxId, props.latestVersion], () => load(), { immediate: true })

const subtitle = computed(() => {
  if (!props.latestVersion) return 'Nothing saved yet'
  return `${props.latestVersion} version${props.latestVersion === 1 ? '' : 's'}. Restoring one never deletes another.`
})

function dayLabel(seconds) {
  const date = new Date(seconds * 1000)
  const today = new Date()
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return 'Today'
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  const sameYear = date.getFullYear() === today.getFullYear()
  return formatLocaleDate(seconds, { unit: 'seconds', options: { weekday: 'short', month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) } })
}

const groups = computed(() => {
  const result = []
  for (const version of versions.value) {
    const label = dayLabel(version.created_at)
    if (result.at(-1)?.label !== label) result.push({ label, versions: [] })
    result.at(-1).versions.push(version)
  }
  return result
})

function describe(version) {
  if (version.message) return version.message
  if (version.restored_from) return `Restored version ${version.restored_from}`
  if (version.number === 1) return 'First version'
  return 'Saved changes'
}

const clockTime = seconds => formatLocaleTime(seconds, { unit: 'seconds', options: { hour: 'numeric', minute: '2-digit' } })
const absoluteTime = seconds => formatActivityAbsoluteTimestamp(seconds)
const isoTime = seconds => formatIsoTimestamp(seconds, { unit: 'seconds' })
const formatSize = bytes => formatSizeBytes(bytes, { compact: true })
</script>

<style scoped>
.sbh {
  display: flex;
  flex-direction: column;
  width: min(360px, 100%);
  height: 100%;
  min-height: 0;
  border-left: 1px solid var(--v-divider);
  background: var(--v-surface-panel);
}

.sbh-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 14px 12px 18px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.sbh-title {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-md, 15px);
  font-weight: 650;
}

.sbh-sub {
  margin: 3px 0 0;
  color: var(--v-text-dim);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.sbh-state {
  display: grid;
  gap: 10px;
  justify-items: start;
  padding: 18px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.sbh-state.is-error {
  color: var(--v-danger);
}

.sbh-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 6px 8px 12px;
  overflow-y: auto;
  list-style: none;
}

.sbh-day {
  padding: 14px 10px 6px;
}

.sbh-item {
  position: relative;
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--v-radius-md);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.sbh-item:hover {
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
}

.sbh-item.is-selected {
  background: color-mix(in srgb, var(--v-sandbox) 13%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-sandbox) 34%, transparent);
}

.sbh-dot {
  width: 9px;
  height: 9px;
  margin-top: 5px;
  margin-left: 2px;
  border: 2px solid color-mix(in srgb, var(--v-text-dim) 70%, transparent);
  border-radius: 50%;
}

.sbh-item.is-current .sbh-dot {
  border-color: var(--v-sandbox);
  background: var(--v-sandbox);
}

.sbh-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.sbh-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.sbh-number {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.sbh-badge {
  padding: 1px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--v-sandbox) 18%, transparent);
  color: color-mix(in srgb, var(--v-sandbox) 80%, white);
  font-size: 11px;
  font-weight: 600;
}

.sbh-time {
  margin-left: auto;
  color: var(--v-text-dim);
  font-size: 12px;
  white-space: nowrap;
}

.sbh-message {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sbh-meta {
  color: var(--v-text-dim);
  font-size: 12px;
}

.sbh-agent {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: color-mix(in srgb, var(--v-sandbox) 78%, white);
}

.sbh-agent .icon {
  width: 11px;
  height: 11px;
}

.sbh-more {
  padding: 8px 14px 16px;
  border-top: 1px solid var(--v-divider-subtle);
}
</style>
