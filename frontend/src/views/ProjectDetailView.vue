<template>
  <div class="project-detail" :class="{ 'is-sandbox': currentPage?.type === 'sandbox' }">
    <!-- A sandbox page uses the whole height; its own bar names the project. -->
    <ProjectSandboxView v-if="currentPage?.type === 'sandbox'" />
    <template v-else>
      <ProjectHeaderBar />
      <ProjectPageView v-if="currentPage" />
      <ProjectFolderView v-else-if="!currentTracker" />
      <slot v-else name="tracker" />
    </template>
  </div>
</template>

<script setup>
import { defineAsyncComponent } from 'vue'
import ProjectHeaderBar from './ProjectHeaderBar.vue'
import ProjectFolderView from './ProjectFolderView.vue'
import ProjectPageView from './ProjectPageView.vue'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'

const ProjectSandboxView = defineAsyncComponent(() => import('./ProjectSandboxView.vue'))
const { currentTracker, currentPage } = useProjectTrackerSelectionStore()
</script>

<style>
.project-detail { flex: 1; display: flex; flex-direction: column; background: var(--v-bg-base); }
/* A sandbox fills the view exactly; its page and code scroll inside it. */
.project-detail.is-sandbox { min-height: 0; overflow: hidden; }
</style>
