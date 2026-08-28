<template>
  <div
    class="v-card v-card-interactive file-card"
    :class="[
      item.type,
      {
        'v-folder-card': isFolder,
        'is-list-row': viewMode === 'list',
        'has-uploader': showUploaderColumn,
        'is-linked': showLinkedState && item.is_linked,
        'workspace-folder': item.is_workspace,
      },
    ]"
  >
    <button
      type="button"
      class="v-file-primary v-file-activation"
      :aria-label="activationLabel"
      @click="$emit('activate', item)"
      @keydown.enter.prevent="$emit('activate', item)"
      @keydown.space.prevent="$emit('activate', item)"
    >
      <div class="thumb">
        <template v-if="isFolder">
          <svg class="icon folder-icon"><use href="#icon-folder" /></svg>
        </template>
        <template v-else>
          <VMediaThumbnail v-if="isMedia && thumbnailUrl" :src="thumbnailUrl" :alt="item.name" />
          <VFileTypeGlyph
            v-else-if="typeVisual"
            :visual="typeVisual"
            :compact="viewMode === 'list'"
          />
          <svg v-else-if="isPdf" class="icon file-icon pdf-icon"><use href="#icon-pdf" /></svg>
          <svg v-else class="icon file-icon"><use href="#icon-file" /></svg>
          <div v-if="item.duration_formatted" class="duration-badge v-media-badge">{{ item.duration_formatted }}</div>
          <div v-if="commentCount" class="comment-badge v-media-badge is-accent"><svg class="icon"><use href="#icon-comment" /></svg>{{ commentCount }}</div>
        </template>

        <div v-if="showLinkedState && item.is_linked && !isFolder" class="link-badge v-media-badge" title="Linked from storage"><svg class="icon"><use href="#icon-link" /></svg></div>
      </div>

      <div class="file-info">
        <div class="v-truncate file-name" :title="item.name">{{ item.name }}</div>
        <div v-if="isFolder" class="v-text-muted file-meta v-folder-meta">
          <span v-if="item.is_workspace" class="v-folder-kind is-workspace">Workspace</span>
          <span v-if="showLinkedState && item.is_linked" class="v-folder-kind">Linked</span>
          <span v-if="countLabel" class="v-folder-count">{{ countLabel }}</span>
        </div>
        <div v-else-if="viewMode === 'grid'" class="v-text-muted file-meta">
          <template v-for="(part, partIndex) in cardMetaParts" :key="part.key">
            <span v-if="partIndex" class="meta-sep">·</span>
            <span :class="part.className">{{ part.label }}</span>
          </template>
        </div>
        <div v-else class="v-file-list-mobile-meta">
          <span>{{ typeLabel }}</span>
          <span v-if="sizeLabel">{{ sizeLabel }}</span>
          <span v-if="dateLabel">{{ dateLabel }}</span>
          <span v-if="uploaderLabel">{{ uploaderLabel }}</span>
        </div>
      </div>
    </button>

    <template v-if="viewMode === 'list'">
      <div class="v-file-list-cell is-size">{{ sizeLabel || '-' }}</div>
      <div class="v-file-list-cell is-type">{{ typeLabel }}</div>
      <div class="v-file-list-cell is-date">{{ dateLabel || '-' }}</div>
      <div v-if="showUploaderColumn" class="v-file-list-cell is-uploader">{{ uploaderLabel || '-' }}</div>
    </template>

    <slot name="actions" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

import VMediaThumbnail from '../media/VMediaThumbnail.vue'
import VFileTypeGlyph from './VFileTypeGlyph.vue'
import { usesGeneratedImagePreview } from '../../lib/mediaEntity'
import { fileCardMetaParts, fileTimestampLabel } from '../../utils/formatters'
import { fileTypeLabel, fileTypeVisual, fileUploaderLabel } from '../../utils/fileBrowserItems'

const props = defineProps({
  item: { type: Object, required: true },
  viewMode: { type: String, default: 'grid' },
  thumbnailUrl: { type: String, default: '' },
  countLabel: { type: String, default: '' },
  commentCount: { type: Number, default: 0 },
  showUploaderColumn: { type: Boolean, default: false },
  showLinkedState: { type: Boolean, default: true },
})

defineEmits(['activate'])

const isFolder = computed(() => props.item?.type === 'folder')
const isMedia = computed(() => Boolean(
  props.item?.is_video
  || props.item?.is_image
  || props.item?.type === 'video'
  || props.item?.type === 'image'
  || usesGeneratedImagePreview(props.item)
))
const isPdf = computed(() => props.item?.is_pdf || String(props.item?.extension || '').toLowerCase() === 'pdf')
const typeVisual = computed(() => fileTypeVisual(props.item))
const cardMetaParts = computed(() => fileCardMetaParts(props.item))
const typeLabel = computed(() => fileTypeLabel(props.item))
const sizeLabel = computed(() => isFolder.value ? '' : String(props.item?.size_formatted || ''))
const dateLabel = computed(() => fileTimestampLabel(props.item))
const uploaderLabel = computed(() => fileUploaderLabel(props.item))
const activationLabel = computed(() => `Open ${props.item?.name || (isFolder.value ? 'folder' : 'file')}`)
</script>
