<template>
  <div class="v-file-list-header" :class="{ 'has-uploader': showUploader }" role="row">
    <button type="button" class="v-file-list-heading is-name" :class="{ active: sortKey === 'name' }" @click="$emit('sort', 'name')">
      Name
      <svg v-if="sortKey === 'name'" class="icon"><use :href="sortIcon" /></svg>
    </button>
    <button type="button" class="v-file-list-heading" :class="{ active: sortKey === 'size' }" @click="$emit('sort', 'size')">
      Size
      <svg v-if="sortKey === 'size'" class="icon"><use :href="sortIcon" /></svg>
    </button>
    <button type="button" class="v-file-list-heading" :class="{ active: sortKey === 'type' }" @click="$emit('sort', 'type')">
      Type
      <svg v-if="sortKey === 'type'" class="icon"><use :href="sortIcon" /></svg>
    </button>
    <button type="button" class="v-file-list-heading" :class="{ active: sortKey === 'date' }" @click="$emit('sort', 'date')">
      Date added
      <svg v-if="sortKey === 'date'" class="icon"><use :href="sortIcon" /></svg>
    </button>
    <button v-if="showUploader" type="button" class="v-file-list-heading" :class="{ active: sortKey === 'uploader' }" @click="$emit('sort', 'uploader')">
      Uploaded by
      <svg v-if="sortKey === 'uploader'" class="icon"><use :href="sortIcon" /></svg>
    </button>
    <span aria-hidden="true"></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sortKey: { type: String, default: 'name' },
  sortDirection: { type: String, default: 'asc' },
  showUploader: { type: Boolean, default: false },
})

defineEmits(['sort'])

const sortIcon = computed(() => props.sortDirection === 'asc' ? '#icon-chevron-up' : '#icon-chevron-down')
</script>
