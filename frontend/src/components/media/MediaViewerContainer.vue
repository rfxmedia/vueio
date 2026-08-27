<template>
  <MediaViewerHost
    v-if="currentMedia"
    v-model:version-compare-mode="versionCompareMode"
    v-model:sidebar-tab="sidebarTab"
    v-model:new-comment="newComment"
    v-model:user-name-input="userNameInput"
    v-model:drawing-color="drawingColor"
    :current-media="currentMedia"
    :is-viewing-image="isViewingImage"
    :is-viewing-pdf="isViewingPdf"
    :version-compare-active="versionCompareActive"
    :version-compare-primary-media="versionComparePrimaryMedia"
    :version-compare-secondary-media="versionCompareSecondaryMedia"
    :version-compare-primary-label="versionComparePrimaryLabel"
    :version-compare-secondary-label="versionCompareSecondaryLabel"
    :version-compare-options="versionCompareOptions"
    :version-compare-primary-key="versionComparePrimaryKey"
    :version-compare-secondary-key="versionCompareSecondaryKey"
    :resolve-viewer-media-routes="resolveViewerMediaRoutes"
    :format-timecode="formatTimecode"
    :video-frame-rate="videoFrameRate"
    :attachment-lightbox="attachmentLightbox"
    :show-toolbar="showToolbar"
    :surface-props="surfaceProps"
    :toolbar-props="toolbarProps"
    :info-panel-props="infoPanelProps"
    :comments-panel-props="commentsPanelProps"
    :sidebar-tabs="sidebarTabs"
    :sidebar-tab-variant="sidebarTabVariant"
    @update-primary-version="setPrimaryVersion"
    @update-secondary-version="setSecondaryVersion"
    @exit-version-compare="exitVersionCompare"
    @close-attachment-lightbox="closeAttachmentLightbox"
  />
</template>

<script setup>
import { computed } from 'vue'
import MediaViewerHost from './MediaViewerHost.vue'
import { useViewerStore } from '../../ownership/viewer'

const { media, comparison, presentation, sidebar, actions } = useViewerStore()

const {
  state,
  core,
  stream,
  transport,
  annotations,
  frames,
  actions: viewerActions,
} = media

const currentMedia = state.currentMedia
const isViewingImage = core.isViewingImage
const isViewingPdf = core.isViewingPdf
const attachmentLightbox = sidebar.comments.attachmentLightbox

const {
  active: versionCompareActive,
  mode: versionCompareMode,
  primaryMedia: versionComparePrimaryMedia,
  secondaryMedia: versionCompareSecondaryMedia,
  primaryLabel: versionComparePrimaryLabel,
  secondaryLabel: versionCompareSecondaryLabel,
  options: versionCompareOptions,
  primaryKey: versionComparePrimaryKey,
  secondaryKey: versionCompareSecondaryKey,
} = comparison

const resolveViewerMediaRoutes = core.resolveViewerMediaRoutes
const formatTimecode = viewerActions.formatTimecode
const videoFrameRate = computed(() => state.videoInfo.value.fps || 24)
const showToolbar = computed(() => state.canShowToolbar.value && !comparison.active.value)

const {
  comments,
} = sidebar
const sidebarTab = state.sidebarTab
const publicationNeedsAttention = computed(() => (
  presentation.canManageVersionPublication?.value
  && String(state.currentMedia.value?.share_state || '').trim().toLowerCase() === 'pending'
))
const sidebarTabs = computed(() => (
  state.sidebarTabs.value.map(tab => (
    tab.value === 'info'
      ? { ...tab, attention: publicationNeedsAttention.value }
      : tab
  ))
))
const sidebarTabVariant = state.sidebarTabVariant
const newComment = comments.newComment
const userNameInput = comments.userNameInput
const drawingColor = annotations.drawingColor

const {
  setPrimaryVersion,
  setSecondaryVersion,
  exitVersionCompare,
  closeAttachmentLightbox,
} = actions

const surfaceProps = computed(() => ({
  isViewingImage: core.isViewingImage.value,
  isViewingPdf: core.isViewingPdf.value,
  isViewingVideo: core.isViewingVideo.value,
  enableImageDesktopNavigation: !presentation.isMobile.value,
  streamPreparing: stream.preparing.value,
  showStreamPreparingOverlay: stream.showPreparingOverlay.value,
  streamProgress: stream.progress.value,
  mediaStreamUrl: core.mediaStreamUrl.value,
  mediaUnavailable: state.mediaUnavailable.value,
  currentMedia: state.currentMedia.value,
  videoPosterUrl: state.currentMedia.value ? core.getThumbnailUrl(state.currentMedia.value) : '',
  comments: comments.comments.value,
  playerMuted: transport.playerMuted.value,
  nativeVideoLoop: transport.nativeVideoLoopEnabled.value,
  isDrawingMode: annotations.isDrawingMode.value,
  showAnnotationPreview: comments.showAnnotationPreview.value,
  pdfFocusRequest: annotations.pdfFocusRequest.value,
  onPdfLoaded: annotations.handlePdfLoaded,
  onPdfAnnotationTargetChange: annotations.handlePdfAnnotationTargetChange,
  onActivateAnnotationCanvas: annotations.activateAnnotationCanvas,
  onDownloadCurrentMedia: presentation.downloadCurrentMedia,
  onPdfCommentSelect: viewerActions.handleCommentClick,
  handleVideoContainerClick: viewerActions.handleVideoContainerClick,
  onImageLoaded: viewerActions.onImageLoaded,
  onTimeUpdate: transport.onTimeUpdate,
  onLoaded: transport.onLoaded,
  onVideoCanPlay: transport.onVideoCanPlay,
  onVideoEnded: transport.onVideoEnded,
  onVideoPlay: transport.onVideoPlay,
  onVideoPause: transport.onVideoPause,
  onVideoSeeked: transport.onVideoSeeked,
  startPointerDrawing: annotations.startPointerDrawing,
  movePointerDrawing: annotations.movePointerDrawing,
  finishPointerDrawing: annotations.finishPointerDrawing,
  setVideoContainerRef: viewerActions.setVideoContainerRef,
  setVideoElRef: viewerActions.setVideoElRef,
  setImageStageRef: viewerActions.setImageStageRef,
  setAnnotationCanvasRef: annotations.setAnnotationCanvasRef,
  setPreviewCanvasRef: annotations.setPreviewCanvasRef,
}))

const toolbarProps = computed(() => ({
  comments: comments.comments.value,
  duration: transport.duration.value,
  // The playback clock is passed as a ref, not a value: reading it here would
  // rebuild these props (and re-render the host + toolbar) 60×/s during
  // playback. The toolbar writes clock-driven DOM imperatively instead.
  currentTimeRef: transport.currentTime,
  frameRate: videoFrameRate.value,
  streamPreparing: stream.preparing.value,
  playerVolume: transport.playerVolume.value,
  loopEnabled: transport.loopEnabled.value,
  isPlaying: transport.isPlaying.value,
  isActuallyMuted: transport.isActuallyMuted.value,
  volumeIconHref: transport.volumeIconHref.value,
  qualityOptions: stream.qualityOptions.value,
  selectedQuality: stream.selectedQuality.value,
  selectedQualityLabel: stream.selectedQualityLabel.value,
  scrubPreviewSourceUrl: stream.scrubPreviewSourceUrl.value,
  formatTimecode,
  onSeekToTime: transport.seekTo,
  onStartTimelinePointer: transport.startTimelinePointer,
  onMoveTimelinePointer: transport.moveTimelinePointer,
  onFinishTimelinePointer: transport.finishTimelinePointer,
  onCancelTimelinePointer: transport.cancelTimelinePointer,
  onSeekToComment: viewerActions.seekToComment,
  onTogglePlay: transport.togglePlay,
  onToggleMute: transport.toggleMute,
  onVolumeSliderInput: transport.onVolumeSliderInput,
  onToggleLoop: transport.toggleLoop,
  onToggleFullscreen: transport.toggleFullscreen,
  onSetStreamQuality: stream.setQuality,
  onCopyCurrentFrame: frames.copyCurrentFrameToClipboard,
  onDownloadCurrentFrame: frames.downloadCurrentFrame,
  onSetCurrentFrameAsThumbnail: frames.setCurrentFrameAsThumbnail,
  canSetCurrentFrameAsThumbnail: frames.canSetCurrentFrameAsThumbnail.value,
  frameCaptureComment: frames.frameCaptureComment.value,
}))

const infoPanelProps = computed(() => ({
  currentMedia: state.currentMedia.value,
  currentShot: presentation.currentShot.value,
  mediaInfo: state.mediaInfo.value,
  isViewingVideo: core.isViewingVideo.value,
  isViewingPdf: core.isViewingPdf.value,
  canEditVersionSummary: presentation.canEditVersionSummary.value,
  updateVersionSummary: presentation.updateVersionSummary,
  canManageVersionPublication: presentation.canManageVersionPublication?.value ?? false,
  versionReviewEnabled: presentation.versionReviewEnabled?.value ?? false,
  updateVersionPublication: presentation.updateVersionPublication,
  formatTimecode,
}))

const commentsPanelProps = computed(() => ({
  comments: comments.comments.value,
  commentPosting: comments.commentPosting?.value ?? false,
  userName: comments.userName.value,
  pendingAnnotation: annotations.pendingAnnotation.value,
  replyTarget: comments.replyTarget.value,
  pendingCommentAttachments: comments.pendingCommentAttachments.value,
  mentionContext: comments.mentionContext?.value ?? { enabled: false, projectId: '', trackerId: '', shots: [] },
  pendingVoiceNote: comments.pendingVoiceNote?.value ?? null,
  voiceRecorderState: comments.voiceRecorderState?.value ?? 'idle',
  voiceRecorderSupported: comments.voiceRecorderSupported?.value ?? false,
  voiceRecorderElapsed: comments.voiceRecorderElapsed?.value ?? 0,
  voiceRecorderLevels: comments.voiceRecorderLevels?.value ?? [],
  drawingColors: annotations.drawingColors,
  drawingColor: annotations.drawingColor.value,
  isDrawingMode: annotations.isDrawingMode.value,
  isViewingImage: core.isViewingImage.value,
  isViewingPdf: core.isViewingPdf.value,
  isViewingVideo: core.isViewingVideo.value,
  activityFocusCommentId: state.activityFocusCommentId.value,
  formatTimecode,
  getCommentAttachmentUrl: comments.getCommentAttachmentUrl,
  onHandleCommentClick: viewerActions.handleCommentClick,
  onToggleResolve: comments.toggleResolve,
  onDeleteComment: comments.deleteComment,
  onOpenAttachmentLightbox: comments.openAttachmentLightbox,
  onClearCanvas: annotations.clearCanvas,
  onCancelDrawing: annotations.cancelDrawing,
  onClearPendingAnnotation: annotations.clearPendingAnnotation,
  onRemovePendingCommentAttachment: comments.removePendingCommentAttachment,
  onHandleCommentAttachmentChange: comments.handleCommentAttachmentChange,
  onAddPendingCommentReferences: comments.addPendingCommentReferences,
  onAddPendingInlineMention: comments.addPendingInlineMention,
  onStartVoiceRecording: comments.startVoiceRecording,
  onStopVoiceRecording: comments.stopVoiceRecording,
  onCancelVoiceRecording: comments.cancelVoiceRecording,
  onRemovePendingVoiceNote: comments.removePendingVoiceNote,
  onStartAnnotationForComment: annotations.startAnnotationForComment,
  onStartReply: comments.startReply,
  onCancelReply: comments.cancelReply,
  onPostMediaComment: comments.postMediaComment,
}))
</script>
