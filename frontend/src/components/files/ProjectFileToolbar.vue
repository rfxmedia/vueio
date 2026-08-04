<template>
  <div class="project-file-toolbar v-toolbar" aria-label="Project content controls">
    <div class="project-file-toolbar-context" :class="{ 'has-breadcrumbs': path }">
      <span class="project-file-toolbar-heading">
        <span class="project-file-toolbar-label">Project contents</span>
        <span class="project-file-toolbar-count">{{ itemCount }}</span>
      </span>
      <nav
        v-if="path"
        ref="breadcrumbNav"
        class="project-file-breadcrumbs"
        aria-label="Folder path"
      >
        <button
          type="button"
          class="project-file-breadcrumb-link v-btn v-btn-quiet v-btn-sm"
          @click="$emit('navigate', homePath)"
        >
          <svg class="icon" aria-hidden="true"><use href="#icon-home" /></svg>
          <span class="v-truncate">Home</span>
        </button>
        <template v-for="(crumb, index) in breadcrumbs.slice(1)" :key="crumb.path || index">
          <svg class="icon project-file-breadcrumb-separator" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
          <span
            v-if="crumb.path === path"
            class="project-file-breadcrumb-current v-truncate"
            aria-current="page"
            :title="crumb.name"
          >
            {{ crumb.name }}
          </span>
          <button
            v-else
            type="button"
            class="project-file-breadcrumb-link v-btn v-btn-quiet v-btn-sm"
            :title="crumb.name"
            @click="$emit('navigate', crumb.path)"
          >
            <span class="v-truncate">{{ crumb.name }}</span>
          </button>
        </template>
      </nav>
    </div>
    <div class="project-file-toolbar-actions">
      <VFileBrowserControls
        :view-mode="viewMode"
        :sort-key="sortKey"
        :sort-direction="sortDirection"
        @set-view="$emit('set-view', $event)"
        @choose-sort="$emit('choose-sort', $event)"
        @toggle-direction="$emit('toggle-direction')"
      />
      <button
        v-if="canDownloadAll"
        type="button"
        class="v-btn v-btn-secondary v-btn-sm project-file-download-all"
        :disabled="downloadBusy"
        :aria-label="downloadBusy ? 'Packaging project folder' : 'Download project folder'"
        :title="downloadBusy ? 'Packaging project folder' : 'Download project folder'"
        @click="$emit('download-all')"
      >
        <svg class="icon"><use href="#icon-download" /></svg>
        <span class="v-file-toolbar-action-label">{{ downloadBusy ? 'Packaging…' : 'Download All' }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import VFileBrowserControls from './VFileBrowserControls.vue'

const props = defineProps({
  viewMode: { type: String, default: 'grid' },
  sortKey: { type: String, default: 'name' },
  sortDirection: { type: String, default: 'asc' },
  itemCount: { type: Number, default: 0 },
  path: { type: String, default: '' },
  breadcrumbs: { type: Array, default: () => [] },
  homePath: { type: String, default: '' },
  canDownloadAll: { type: Boolean, default: false },
  downloadBusy: { type: Boolean, default: false },
})

defineEmits(['set-view', 'choose-sort', 'toggle-direction', 'download-all', 'navigate'])

const breadcrumbNav = ref(null)

watch(
  [() => props.path, () => props.breadcrumbs.length],
  () => nextTick(() => {
    if (breadcrumbNav.value) breadcrumbNav.value.scrollLeft = breadcrumbNav.value.scrollWidth
  }),
  { immediate: true },
)
</script>

<style scoped>
.project-file-toolbar {
  justify-content: space-between;
  min-height: 44px;
  padding: 0 0 14px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.project-file-toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v-space-2);
  min-width: 0;
}

.project-file-toolbar-context {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
}

.project-file-toolbar-label {
  color: var(--v-text-secondary);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.project-file-toolbar-heading {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
}

.project-file-toolbar-count {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.project-file-breadcrumbs {
  display: flex;
  align-items: center;
  flex: 0 1 auto;
  gap: var(--v-space-1);
  min-width: 0;
  max-width: min(54vw, 720px);
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

.project-file-breadcrumb-link {
  flex: 0 0 auto;
  min-height: 30px;
  max-width: 180px;
  padding: 0 var(--v-space-2);
  border-radius: var(--v-button-radius);
  color: var(--v-text-muted);
  font-weight: 550;
}

.project-file-breadcrumb-link:hover:not(:disabled) {
  color: var(--v-text-secondary);
}

.project-file-breadcrumb-link .icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.project-file-breadcrumb-current {
  flex: 0 0 auto;
  max-width: 260px;
  padding: 0 var(--v-space-1);
  color: var(--v-text);
  font-size: var(--v-text-xs);
  font-weight: 650;
  line-height: 30px;
}

.project-file-breadcrumb-separator {
  width: 10px;
  height: 10px;
  flex: 0 0 auto;
  color: var(--v-text-muted);
  opacity: 0.5;
}

.project-file-download-all {
  flex: 0 0 auto;
  min-height: 36px;
}

.project-file-toolbar-actions :deep(.v-file-sort-select) {
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast);
}

.project-file-toolbar-actions :deep(.v-file-sort-select:hover),
.project-file-toolbar-actions :deep(.v-file-sort-select:focus-within) {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
}

.project-file-toolbar-actions :deep(.v-view-toggle-btn:hover:not(.active)) {
  background: var(--v-control-bg-hover);
}

@media (max-width: 768px) {
  .project-file-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--v-space-2);
    min-height: 0;
    padding-bottom: 10px;
  }

  .project-file-toolbar-actions {
    justify-content: flex-end;
    gap: 6px;
    width: auto;
  }

  .project-file-toolbar-context {
    overflow: hidden;
    gap: var(--v-space-2);
  }

  .project-file-toolbar-heading {
    flex: 0 0 auto;
  }

  .project-file-breadcrumbs {
    flex: 1 1 auto;
    max-width: none;
  }

  .project-file-breadcrumb-link {
    min-height: 32px;
  }

  .project-file-breadcrumb-current {
    line-height: 32px;
  }

  .project-file-toolbar-actions :deep(.v-file-browser-controls) {
    gap: 4px;
  }

  .project-file-toolbar-actions :deep(.v-view-toggle),
  .project-file-toolbar-actions :deep(.v-file-sort-select),
  .project-file-toolbar-actions :deep(.v-file-sort-direction) {
    height: 32px;
  }

  .project-file-toolbar-actions :deep(.v-view-toggle) {
    padding: 2px;
  }

  .project-file-toolbar-actions :deep(.v-view-toggle-btn) {
    width: 26px;
    height: 26px;
  }

  .project-file-toolbar-actions :deep(.v-file-sort-select) {
    width: 110px;
  }

  .project-file-toolbar-actions :deep(.v-file-sort-direction) {
    width: 32px;
    min-width: 32px;
    min-height: 32px;
  }

  .project-file-download-all {
    min-width: 32px;
    min-height: 32px;
  }

  .project-file-download-all .icon {
    width: 14px;
    height: 14px;
  }
}

@media (max-width: 520px) {
  .project-file-toolbar-actions {
    flex-wrap: nowrap;
  }

  .project-file-download-all {
    width: 32px;
    min-width: 32px;
    min-height: 32px;
    padding: 0;
  }

  .project-file-download-all .v-file-toolbar-action-label {
    display: none;
  }

  .project-file-toolbar-context.has-breadcrumbs .project-file-toolbar-label {
    display: none;
  }

  .project-file-toolbar-context.has-breadcrumbs .project-file-toolbar-count::after {
    content: ' items';
  }
}

@media (max-width: 420px) {
  .project-file-toolbar-label {
    display: none;
  }

  .project-file-toolbar-count::after {
    content: ' items';
  }
}
</style>
