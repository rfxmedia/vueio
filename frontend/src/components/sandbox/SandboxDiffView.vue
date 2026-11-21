<template>
  <section class="sbd" aria-label="Changes">
    <header class="sbd-head">
      <span class="sbd-title">{{ fromVersion ? `Version ${fromVersion}` : 'Blank page' }} <span aria-hidden="true">→</span> Version {{ toVersion }}</span>
      <span v-if="diff" class="sbd-stats">
        <span class="is-added">+{{ diff.added }}</span>
        <span class="is-removed">−{{ diff.removed }}</span>
        <span>lines</span>
      </span>
    </header>

    <div v-if="loading" class="sbd-state">Comparing versions…</div>
    <div v-else-if="error" class="sbd-state is-error">{{ error }}</div>
    <div v-else-if="diff && !diff.hunks.length" class="sbd-state">These versions are the same.</div>
    <div v-else-if="diff" class="sbd-body">
      <div v-for="(hunk, index) in diff.hunks" :key="index" class="sbd-hunk">
        <div class="sbd-hunk-head">Line {{ hunk.new_start }}</div>
        <div
          v-for="(line, lineIndex) in hunk.lines"
          :key="lineIndex"
          class="sbd-line"
          :class="{ 'is-added': line.kind === '+', 'is-removed': line.kind === '-' }"
        >
          <span class="sbd-num">{{ line.old ?? '' }}</span>
          <span class="sbd-num">{{ line.new ?? '' }}</span>
          <span class="sbd-sign" aria-hidden="true">{{ line.kind === ' ' ? '' : line.kind === '-' ? '−' : '+' }}</span>
          <span class="sbd-text">{{ line.text }}</span>
        </div>
      </div>
      <p v-if="diff.truncated" class="sbd-note">The comparison is long. It shows the first {{ shownLines }} lines.</p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'

const props = defineProps({
  projectId: { type: String, required: true },
  sandboxId: { type: String, required: true },
  fromVersion: { type: Number, required: true },
  toVersion: { type: Number, required: true },
})

const diff = ref(null)
const loading = ref(false)
const error = ref('')
let requestId = 0

const shownLines = computed(() => (diff.value?.hunks || []).reduce((total, hunk) => total + hunk.lines.length, 0))

watch(() => [props.sandboxId, props.fromVersion, props.toVersion], async () => {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/projects/${props.projectId}/sandboxes/${props.sandboxId}/diff`, {
      params: { from_version: props.fromVersion, to_version: props.toVersion },
    })
    if (id === requestId) diff.value = data
  } catch (loadError) {
    if (id === requestId) error.value = getApiErrorMessage(loadError, 'Could not compare the versions.')
  } finally {
    if (id === requestId) loading.value = false
  }
}, { immediate: true })
</script>

<style scoped>
.sbd {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--v-surface-inset);
}

.sbd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--v-divider-subtle);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.sbd-title {
  font-weight: 600;
}

.sbd-stats {
  display: flex;
  gap: 8px;
  color: var(--v-text-dim);
  font-variant-numeric: tabular-nums;
}

.sbd-stats .is-added { color: var(--v-accent); }
.sbd-stats .is-removed { color: var(--v-danger); }

.sbd-state {
  padding: 24px 16px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.sbd-state.is-error { color: var(--v-danger); }

.sbd-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 0 24px;
  font-family: ui-monospace, 'SF Mono', 'Cascadia Code', 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 19px;
}

.sbd-hunk + .sbd-hunk {
  margin-top: 10px;
}

.sbd-hunk-head {
  position: sticky;
  left: 0;
  padding: 4px 16px;
  color: var(--v-text-dim);
  font-family: var(--v-font);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.sbd-line {
  display: grid;
  grid-template-columns: 44px 44px 18px max-content;
  min-width: 100%;
  width: max-content;
  color: var(--v-text-secondary);
}

.sbd-line.is-added { background: color-mix(in srgb, var(--v-accent) 13%, transparent); }
.sbd-line.is-removed { background: color-mix(in srgb, var(--v-danger) 13%, transparent); }

.sbd-num {
  padding-right: 10px;
  color: color-mix(in srgb, var(--v-text-dim) 70%, transparent);
  text-align: right;
  user-select: none;
}

.sbd-sign {
  color: var(--v-text-dim);
  user-select: none;
}

.sbd-line.is-added .sbd-sign { color: var(--v-accent); }
.sbd-line.is-removed .sbd-sign { color: var(--v-danger); }

.sbd-text {
  padding-right: 24px;
  white-space: pre;
}

.sbd-note {
  margin: 12px 16px 0;
  color: var(--v-text-dim);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
}
</style>
