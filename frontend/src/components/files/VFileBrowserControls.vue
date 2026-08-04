<template>
  <div class="v-file-browser-controls">
    <div class="v-view-toggle" role="group" aria-label="File view">
      <button
        type="button"
        class="v-view-toggle-btn"
        :class="{ active: viewMode === 'grid' }"
        :aria-pressed="viewMode === 'grid'"
        aria-label="Grid view"
        title="Grid view"
        @click="$emit('set-view', 'grid')"
      >
        <svg class="icon"><use href="#icon-grid" /></svg>
      </button>
      <button
        type="button"
        class="v-view-toggle-btn"
        :class="{ active: viewMode === 'list' }"
        :aria-pressed="viewMode === 'list'"
        aria-label="List view"
        title="List view"
        @click="$emit('set-view', 'list')"
      >
        <svg class="icon"><use href="#icon-list" /></svg>
      </button>
    </div>

    <label class="v-file-sort-select" title="Sort files">
      <svg class="icon" aria-hidden="true"><use href="#icon-sort" /></svg>
      <span class="v-sr-only">Sort files by</span>
      <select :value="sortKey" aria-label="Sort files by" @change="$emit('choose-sort', $event.target.value)">
        <option v-for="option in sortOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <svg class="icon v-file-sort-select-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
    </label>

    <button
      type="button"
      class="v-icon-action v-file-sort-direction"
      :aria-label="sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
      :title="sortDirection === 'asc' ? 'Sort ascending' : 'Sort descending'"
      @click="$emit('toggle-direction')"
    >
      <svg class="icon"><use :href="sortDirection === 'asc' ? '#icon-chevron-up' : '#icon-chevron-down'" /></svg>
    </button>
  </div>
</template>

<script setup>
import { FILE_SORT_OPTIONS } from '../../utils/fileBrowserItems'

defineProps({
  viewMode: { type: String, default: 'grid' },
  sortKey: { type: String, default: 'name' },
  sortDirection: { type: String, default: 'asc' },
})

defineEmits(['set-view', 'choose-sort', 'toggle-direction'])

const sortOptions = FILE_SORT_OPTIONS
</script>
