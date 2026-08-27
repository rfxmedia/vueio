<template>
  <main
    v-if="currentMedia"
    class="player-view"
    :class="{
      'image-mode': isViewingImage,
      'pdf-mode': isViewingPdf,
      'compare-mode': versionCompareActive,
    }"
    :aria-label="hostAriaLabel"
  >
    <section class="player-stage">
      <MediaVersionCompareSurface
        v-if="versionCompareActive && versionComparePrimaryMedia && versionCompareSecondaryMedia"
        :mode="versionCompareMode"
        :primary-media="versionComparePrimaryMedia"
        :secondary-media="versionCompareSecondaryMedia"
        :primary-label="versionComparePrimaryLabel"
        :secondary-label="versionCompareSecondaryLabel"
        :version-options="versionCompareOptions"
        :primary-version-key="versionComparePrimaryKey"
        :secondary-version-key="versionCompareSecondaryKey"
        :resolve-media-routes="resolveViewerMediaRoutes"
        :format-timecode="formatTimecode"
        :frame-rate="videoFrameRate"
        @update:mode="$emit('update:versionCompareMode', $event)"
        @update-primary-version="$emit('update-primary-version', $event)"
        @update-secondary-version="$emit('update-secondary-version', $event)"
        @exit="$emit('exit-version-compare')"
      />
      <MediaViewerSurface v-else v-bind="surfaceProps" />

      <Transition name="v-attachment-lightbox-fade">
        <div
          v-if="attachmentLightbox"
          class="v-attachment-lightbox"
          role="dialog"
          aria-modal="true"
          @pointerdown.self="$emit('close-attachment-lightbox')"
          @click="$emit('close-attachment-lightbox')"
        >
          <div class="v-attachment-lightbox-panel" @click.stop>
            <div class="v-attachment-lightbox-header">
              <div class="v-attachment-lightbox-title">
                <svg class="icon"><use :href="attachmentLightbox.kind === 'video' ? '#icon-video' : '#icon-image'"/></svg>
                <span class="v-truncate">{{ attachmentLightbox.name || 'Attachment' }}</span>
              </div>
              <a
                v-if="attachmentLightbox.downloadUrl"
                class="v-icon-action is-muted"
                :href="attachmentLightbox.downloadUrl"
                :download="attachmentLightbox.name || 'attachment'"
                title="Download attachment"
                @pointerdown.stop
                @click.stop
              >
                <svg class="icon"><use href="#icon-download"/></svg>
              </a>
              <button
                type="button"
                class="v-icon-action is-muted"
                title="Close attachment"
                @pointerdown.stop.prevent="$emit('close-attachment-lightbox')"
                @click.stop="$emit('close-attachment-lightbox')"
              >
                <svg class="icon"><use href="#icon-close"/></svg>
              </button>
            </div>

            <div class="v-attachment-lightbox-body">
              <img
                v-if="attachmentLightbox.kind === 'image'"
                :src="attachmentLightbox.url"
                :alt="attachmentLightbox.name || ''"
                class="v-attachment-lightbox-media"
              />
              <video
                v-else
                :src="attachmentLightbox.url"
                class="v-attachment-lightbox-media"
                controls
                autoplay
                playsinline
                webkit-playsinline
                preload="metadata"
              ></video>
            </div>
          </div>
        </div>
      </Transition>

      <MediaViewerToolbar
        v-if="showToolbar && !versionCompareActive"
        v-bind="toolbarProps"
      />
    </section>
    <aside v-if="!versionCompareActive" class="viewer-sidebar">
      <div class="sidebar-tabs">
        <VTabs
          :model-value="sidebarTab"
          :variant="sidebarTabVariant"
          :tabs="sidebarTabs"
          :full-width="true"
          @update:model-value="$emit('update:sidebarTab', $event)"
        />
      </div>

      <MediaViewerInfoPanel
        v-if="sidebarTab === 'info'"
        v-bind="infoPanelProps"
        :is-admin="isAdmin && !shareMode"
      />

      <MediaViewerCommentsPanel
        v-if="sidebarTab === 'comments'"
        :new-comment="newComment"
        :user-name-input="userNameInput"
        :drawing-color="drawingColor"
        :current-user="currentUser"
        :is-admin="isAdmin"
        v-bind="commentsPanelProps"
        @update:new-comment="$emit('update:newComment', $event)"
        @update:user-name-input="$emit('update:userNameInput', $event)"
        @update:drawing-color="$emit('update:drawingColor', $event)"
      />
    </aside>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { VTabs } from '../primitives'
import MediaViewerToolbar from './MediaViewerToolbar.vue'
import MediaViewerSurface from './MediaViewerSurface.vue'
import MediaVersionCompareSurface from './MediaVersionCompareSurface.vue'
import MediaViewerInfoPanel from './MediaViewerInfoPanel.vue'
import MediaViewerCommentsPanel from './MediaViewerCommentsPanel.vue'
import { useProjectTrackerSelectionStore } from '../../ownership/projectTrackerSelection'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'

const props = defineProps({
  currentMedia: { type: Object, default: null },
  isViewingImage: { type: Boolean, default: false },
  isViewingPdf: { type: Boolean, default: false },
  versionCompareActive: { type: Boolean, default: false },
  versionCompareMode: { type: String, default: 'wipe' },
  versionComparePrimaryMedia: { type: Object, default: null },
  versionCompareSecondaryMedia: { type: Object, default: null },
  versionComparePrimaryLabel: { type: String, default: '' },
  versionCompareSecondaryLabel: { type: String, default: '' },
  versionCompareOptions: { type: Array, default: () => [] },
  versionComparePrimaryKey: { type: String, default: '' },
  versionCompareSecondaryKey: { type: String, default: '' },
  resolveViewerMediaRoutes: { type: Function, required: true },
  formatTimecode: { type: Function, required: true },
  videoFrameRate: { type: Number, default: 24 },
  attachmentLightbox: { type: Object, default: null },
  showToolbar: { type: Boolean, default: false },
  surfaceProps: { type: Object, required: true },
  toolbarProps: { type: Object, required: true },
  infoPanelProps: { type: Object, required: true },
  commentsPanelProps: { type: Object, required: true },
  sidebarTab: { type: String, default: 'comments' },
  sidebarTabs: { type: Array, default: () => [] },
  sidebarTabVariant: { type: String, default: 'rail' },
  newComment: { type: String, default: '' },
  userNameInput: { type: String, default: '' },
  drawingColor: { type: String, default: '#ff3b30' },
})

defineEmits([
  'update:versionCompareMode',
  'update-primary-version',
  'update-secondary-version',
  'exit-version-compare',
  'close-attachment-lightbox',
  'update:sidebarTab',
  'update:newComment',
  'update:userNameInput',
  'update:drawingColor',
])

const { currentProject, currentTracker } = useProjectTrackerSelectionStore()
const { currentUser, isAdmin } = useSessionAuthStore()
const { shareMode } = useShareAccessContext()

const hostAriaLabel = computed(() => {
  if (shareMode.value) return 'Shared media viewer'
  return currentTracker.value?.name || currentProject.value?.title || props.currentMedia?.name || 'Media viewer'
})
</script>
