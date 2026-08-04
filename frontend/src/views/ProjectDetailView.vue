<template>
  <div class="project-detail">
    <ProjectHeaderBar />
    <ProjectPageView v-if="currentPage" />
    <ProjectFolderView v-else-if="!currentTracker" />
    <slot v-else name="tracker" />
  </div>
</template>

<script setup>
import ProjectHeaderBar from './ProjectHeaderBar.vue'
import ProjectFolderView from './ProjectFolderView.vue'
import ProjectPageView from './ProjectPageView.vue'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'

const { currentTracker, currentPage } = useProjectTrackerSelectionStore()
</script>

<style>
.project-detail { flex: 1; display: flex; flex-direction: column; background: var(--v-bg-base); }
</style>
