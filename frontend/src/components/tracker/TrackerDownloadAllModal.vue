<template>
  <VModal :model-value="Boolean(trackerDownloadDialog)" :title="title" size="md" @update:model-value="value => !value && close()">
    <template #header>
      <VModalHeader :title="title" :subtitle="subtitle" @close="close" />
    </template>

    <div v-if="trackerDownloadDialog" class="v-modal-stack download-all">
      <div class="download-all-option">
        <VSwitch v-model="includeExtras" label="Include extras" :hint="extrasHint" />
      </div>

      <section class="download-all-tree" aria-label="In the ZIP">
        <div class="download-all-tree-label v-section-label">In the ZIP</div>
        <div class="download-all-row is-zip">
          <svg class="icon" aria-hidden="true"><use href="#icon-package" /></svg>
          <span>{{ zipName }}</span>
        </div>
        <ul class="download-all-entries">
          <li v-for="entry in tree" :key="entry.key">
            <div class="download-all-row" :class="{ 'is-folder': entry.files }" :title="entry.name">
              <svg class="icon" aria-hidden="true"><use :href="entry.files ? '#icon-folder' : '#icon-file'" /></svg>
              <span>{{ entry.name }}</span>
            </div>
            <ul v-if="entry.files" class="download-all-entries">
              <li v-for="file in entry.files" :key="file.name">
                <div class="download-all-row" :class="{ 'is-extra': file.extra }" :title="file.name">
                  <svg class="icon" aria-hidden="true"><use :href="file.extra ? '#icon-layers' : '#icon-file'" /></svg>
                  <span>{{ file.name }}</span>
                </div>
              </li>
            </ul>
          </li>
        </ul>
      </section>
    </div>

    <template #footer>
      <span class="download-all-count">{{ fileCountLabel }}</span>
      <button type="button" class="v-btn v-btn-secondary" @click="close">Cancel</button>
      <button type="button" class="v-btn v-btn-primary" :disabled="trackerDownloadBusy" @click="start">
        <svg class="icon"><use href="#icon-download" /></svg>Download ZIP
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'
import { VModal, VModalHeader, VSwitch } from '../primitives'

const {
  currentTracker,
  downloadTrackerLatestVersions,
  trackerDownloadBusy,
  trackerDownloadDialog,
  trackerDownloadPlan,
  trackerDownloadZipName,
} = useTrackerStore()

const includeExtras = ref(true)
watch(trackerDownloadDialog, value => { if (value) includeExtras.value = true })

const selectedOnly = computed(() => Boolean(trackerDownloadDialog.value?.selectedOnly))
const plan = computed(() => (trackerDownloadDialog.value ? trackerDownloadPlan({ selectedOnly: selectedOnly.value }) : []))
const zipName = computed(() => trackerDownloadZipName({ selectedOnly: selectedOnly.value }))
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

const title = computed(() => (selectedOnly.value ? 'Download selected' : 'Download all'))
const subtitle = computed(() => [currentTracker.value?.name, `latest version of ${plural(plan.value.length, 'shot')}`].filter(Boolean).join(' · '))

const extraCount = computed(() => plan.value.reduce((total, entry) => total + entry.extras.length, 0))
const shotsWithExtras = computed(() => plan.value.filter(entry => entry.extras.length).length)
const extrasHint = computed(() => (
  includeExtras.value
    ? `${plural(extraCount.value, 'extra')} from ${plural(shotsWithExtras.value, 'shot')}. Each of those shots gets its own folder.`
    : 'Only the latest versions.'
))

// The same layout as the server: a shot with extras gets a folder named
// after its plate. A shot without extras stays at the top.
const tree = computed(() => plan.value.map(entry => {
  const name = entry.plate || entry.shot?.shot_id || 'Shot'
  if (!includeExtras.value || !entry.extras.length) return { key: entry.shot?.id || name, name }
  return {
    key: entry.shot?.id || name,
    name: `${name.replace(/\.[^./]+$/, '')}/`,
    files: [{ name }, ...entry.extras.map(extra => ({ name: extra, extra: true }))],
  }
}))

const fileCountLabel = computed(() => plural(plan.value.length + (includeExtras.value ? extraCount.value : 0), 'file'))

function close() {
  trackerDownloadDialog.value = null
}

function start() {
  const options = { selectedOnly: selectedOnly.value, includeExtras: includeExtras.value }
  close()
  void downloadTrackerLatestVersions(options)
}
</script>

<style scoped>
.download-all-option {
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-modal-card-bg, var(--v-surface-raised));
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
}

.download-all-tree {
  max-height: min(46vh, 380px);
  overflow-y: auto;
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inline);
}

.download-all-tree-label {
  margin-bottom: 8px;
}

.download-all-entries {
  margin: 0;
  padding: 0 0 0 7px;
  list-style: none;
}

.download-all-entries .download-all-entries {
  margin-left: 7px;
  border-left: 1px solid var(--v-divider-subtle);
}

.download-all-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 3px 0 3px 8px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.download-all-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-all-row .icon {
  width: 13px;
  height: 13px;
  flex: none;
  opacity: 0.75;
}

.download-all-row.is-zip {
  padding-left: 0;
  color: var(--v-text);
  font-weight: 650;
}

.download-all-row.is-folder {
  color: var(--v-text);
  font-weight: 600;
}

.download-all-row.is-extra {
  color: var(--v-accent);
}

.download-all-row.is-extra .icon {
  opacity: 1;
}

.download-all-count {
  margin-right: auto;
  color: var(--v-text-dim);
  font-size: var(--v-text-sm);
}
</style>
