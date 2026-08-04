<template>
  <div class="comments-section">
    <div class="comments-list">
      <div v-if="comments.length === 0" class="v-empty-state v-empty-state-compact empty-comments">
        <svg class="icon v-empty-state-icon"><use href="#icon-comment"/></svg>
        <p class="v-empty-state-title">No comments yet</p>
      </div>

      <div
        v-for="(comment, commentIndex) in comments"
        :key="comment.id"
        class="comment comment-thread"
        :class="{ resolved: comment.resolved, 'has-annotation': comment.annotation_data, 'has-replies': comment.replies && comment.replies.length, 'is-activity-focus': isActivityFocusComment(comment) }"
        :data-comment-id="comment.id"
        @click="handleCommentClick(comment)"
      >
        <div
          class="comment-entry comment-main"
        >
          <span class="comment-avatar" :style="getAvatarStyle(comment.user_name)" aria-hidden="true">{{ getInitials(comment.user_name) }}</span>

          <div class="comment-body">
            <div class="comment-header">
              <div class="comment-header-main">
                <span class="author">{{ comment.user_name }}</span>
                <time
                  v-if="formatRelativeTime(comment.created_at)"
                  class="comment-posted-at"
                  :datetime="commentPostedDatetime(comment.created_at)"
                  :title="formatCommentPostedTitle(comment.created_at)"
                >{{ formatRelativeTime(comment.created_at) }}</time>
                <span v-if="isViewingPdf && pdfPageLabel(comment)" class="comment-timecode">{{ pdfPageLabel(comment) }}</span>
                <span v-else-if="!isViewingImage && !isViewingPdf && comment.timestamp != null" class="comment-timecode">{{ formatTimecode(comment.timestamp) }}</span>
                <span v-if="comment.annotation_data" class="comment-annotation-chip" title="Has drawing annotation" aria-label="Has drawing annotation">
                  <svg class="icon"><use href="#icon-pen"/></svg>
                </span>
              </div>
              <div class="comment-header-tools">
                <div class="comment-secondary-actions">
                  <button type="button" class="comment-action-button" @click.stop="toggleResolve(comment.id)" :title="comment.resolved ? 'Unresolve' : 'Resolve'"><svg class="icon"><use :href="comment.resolved ? '#icon-undo' : '#icon-check'"/></svg></button>
                  <button v-if="isAdmin" type="button" class="comment-action-button is-danger" @click.stop="deleteComment(comment.id)" title="Delete Comment"><svg class="icon"><use href="#icon-trash"/></svg></button>
                </div>
                <span class="comment-number">#{{ commentIndex + 1 }}</span>
              </div>
            </div>

            <p class="comment-text">
              <span v-if="comment.text" class="comment-message">
                <template v-for="(segment, segmentIndex) in segmentTextLinks(comment.text)" :key="`${comment.id}-${segmentIndex}`">
                  <a
                    v-if="segment.type === 'link'"
                    class="comment-text-link"
                    :href="segment.href"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                  >{{ segment.text }}</a>
                  <template v-else>{{ segment.text }}</template>
                </template>
              </span>
              <span v-else-if="comment.annotation_data" class="comment-text-placeholder">Drawing annotation</span>
            </p>

            <div v-if="comment.attachments && comment.attachments.length" class="comment-attachments">
              <template v-for="attachment in comment.attachments" :key="attachment.id">
                <CommentVoiceNote
                  v-if="attachment.kind === 'audio'"
                  :attachment="attachment"
                  :url="getCommentAttachmentUrl(comment, attachment)"
                />
                <CommentAttachmentCard
                  v-else
                  :attachment="attachment"
                  :url="attachment.attachment_type === 'reference' ? '' : getCommentAttachmentUrl(comment, attachment)"
                  @open="openAttachmentLightbox(comment, attachment)"
                />
              </template>
            </div>

          </div>
        </div>

        <div v-if="comment.replies && comment.replies.length" class="comment-replies">
          <div
            v-for="reply in comment.replies"
            :key="reply.id"
            class="comment-entry comment-reply"
            :class="{ resolved: reply.resolved, 'has-annotation': reply.annotation_data, 'is-activity-focus': isActivityFocusComment(reply) }"
            :data-comment-id="reply.id"
            @click.stop="handleCommentClick(reply)"
          >
            <span class="comment-avatar" :style="getAvatarStyle(reply.user_name)" aria-hidden="true">{{ getInitials(reply.user_name) }}</span>

            <div class="comment-body">
              <div class="comment-header">
                <div class="comment-header-main">
                  <span class="author">{{ reply.user_name }}</span>
                  <time
                    v-if="formatRelativeTime(reply.created_at)"
                    class="comment-posted-at"
                  :datetime="commentPostedDatetime(reply.created_at)"
                  :title="formatCommentPostedTitle(reply.created_at)"
                >{{ formatRelativeTime(reply.created_at) }}</time>
                  <span v-if="reply.annotation_data" class="comment-annotation-chip" title="Has drawing annotation" aria-label="Has drawing annotation">
                    <svg class="icon"><use href="#icon-pen"/></svg>
                  </span>
                  <span v-if="isViewingPdf && pdfPageLabel(reply)" class="comment-timecode">{{ pdfPageLabel(reply) }}</span>
                </div>
                <div class="comment-secondary-actions">
                  <button type="button" class="comment-action-button" @click.stop="toggleResolve(reply.id)" :title="reply.resolved ? 'Unresolve' : 'Resolve'"><svg class="icon"><use :href="reply.resolved ? '#icon-undo' : '#icon-check'"/></svg></button>
                  <button v-if="isAdmin" type="button" class="comment-action-button is-danger" @click.stop="deleteComment(reply.id)" title="Delete Comment"><svg class="icon"><use href="#icon-trash"/></svg></button>
                </div>
              </div>

              <p class="comment-text">
                <span v-if="reply.text" class="comment-message">
                  <template v-for="(segment, segmentIndex) in segmentTextLinks(reply.text)" :key="`${reply.id}-${segmentIndex}`">
                    <a
                      v-if="segment.type === 'link'"
                      class="comment-text-link"
                      :href="segment.href"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                    >{{ segment.text }}</a>
                    <template v-else>{{ segment.text }}</template>
                  </template>
                </span>
                <span v-else-if="reply.annotation_data" class="comment-text-placeholder">Drawing annotation</span>
              </p>

              <div v-if="reply.attachments && reply.attachments.length" class="comment-attachments">
                <template v-for="attachment in reply.attachments" :key="attachment.id">
                  <CommentVoiceNote
                    v-if="attachment.kind === 'audio'"
                    :attachment="attachment"
                    :url="getCommentAttachmentUrl(reply, attachment)"
                  />
                  <CommentAttachmentCard
                    v-else
                    :attachment="attachment"
                    :url="attachment.attachment_type === 'reference' ? '' : getCommentAttachmentUrl(reply, attachment)"
                    @open="openAttachmentLightbox(reply, attachment)"
                  />
                </template>
              </div>
            </div>
          </div>
        </div>

        <button
          v-if="!isReplyComposerFor(comment)"
          type="button"
          class="comment-reply-button comment-thread-reply-button"
          @click.stop="startReply(comment)"
        >Reply</button>

        <div
          v-if="isReplyComposerFor(comment)"
          class="comment-inline-composer"
          @click.stop
        >
          <input v-if="showNameInput" :value="userNameInput" @input="updateUserNameInput" placeholder="Your name" class="name-input"/>

          <div v-if="pendingAnnotation" class="pending-annotation">
            <svg class="icon"><use href="#icon-pen"/></svg>
            <span>Drawing attached</span>
            <button type="button" @click="clearPendingAnnotation">×</button>
          </div>

          <div v-if="pendingVoiceNote" class="pending-voice-note">
            <CommentVoiceNote
              :attachment="pendingVoiceNote"
              :url="pendingVoiceNote.previewUrl"
              compact
            />
            <button type="button" class="pending-attachment-remove" aria-label="Remove voice note" @click="removePendingVoiceNote">×</button>
          </div>

          <div v-if="pendingCommentAttachments.length" class="pending-attachments">
            <div v-for="attachment in pendingCommentAttachments" :key="attachment.id" class="pending-attachment">
              <img v-if="attachment.kind === 'image' && attachment.previewUrl" :src="attachment.previewUrl" :alt="attachment.name || ''"/>
              <div v-else class="pending-attachment-file">
                <svg class="icon"><use :href="pendingAttachmentIcon(attachment)"/></svg>
                <span class="pending-attachment-name">{{ attachment.name }}</span>
              </div>
              <button type="button" class="pending-attachment-remove" @click="removePendingCommentAttachment(attachment.id)">×</button>
            </div>
          </div>

          <div class="composer composer--inline-reply">
            <div v-if="voiceRecorderState === 'recording' && !!replyTarget" class="voice-recording" role="status" aria-label="Recording voice note">
              <span class="voice-recording__dot" aria-hidden="true"></span>
              <div class="voice-recording__levels" aria-hidden="true">
                <span v-for="(level, index) in voiceRecorderLevels" :key="index" :style="{ height: `${Math.max(12, level * 100)}%` }"></span>
              </div>
              <time class="voice-recording__time">{{ formatVoiceDuration(voiceRecorderElapsed) }}</time>
              <button type="button" class="voice-recording__action" aria-label="Stop recording" title="Stop recording" @click="stopVoiceRecording">
                <span class="voice-recording__stop"></span>
              </button>
              <button type="button" class="voice-recording__action is-cancel" aria-label="Cancel recording" title="Cancel recording" @click="cancelVoiceRecording">
                <svg class="icon"><use href="#icon-close" /></svg>
              </button>
            </div>
            <textarea
              v-else
              ref="commentTextarea"
              class="composer__textarea"
              :value="newComment"
              :placeholder="replyPlaceholder"
              rows="1"
              @input="updateNewComment"
              @keydown.enter.ctrl="postMediaComment"
            ></textarea>
            <input
              v-if="voiceRecorderState !== 'recording'"
              ref="commentAttachmentInput"
              type="file"
              accept="image/*,video/*,audio/*,.mxf,application/mxf"
              multiple
              class="comment-attachment-input"
              @change="handleCommentAttachmentChange"
              hidden
            />
            <div v-if="voiceRecorderState !== 'recording'" class="composer__actions">
              <button type="button" class="comment-inline-cancel" @click="cancelReply">Cancel</button>
              <button type="button" class="composer__action" @click="triggerCommentAttachmentPicker" :disabled="pendingAttachmentCount >= maxAttachments" title="Add attachment">
                <svg class="icon"><use href="#icon-link"/></svg>
              </button>
              <button type="button" class="composer__action" @click="startAnnotationForComment" :disabled="isDrawingMode" title="Add Drawing">
                <svg class="icon"><use href="#icon-pen"/></svg>
              </button>
              <button v-if="voiceRecorderSupported" type="button" class="composer__action" @click="startVoiceRecording" :disabled="pendingAttachmentCount >= maxAttachments || !!pendingVoiceNote" aria-label="Record voice note" title="Record voice note">
                <svg class="icon"><use href="#icon-mic"/></svg>
              </button>
              <button type="button" class="composer__action composer__action--submit" @click="postMediaComment" :disabled="!canSubmitComment" title="Post reply">
                <svg class="icon"><use href="#icon-check"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="isDrawingMode" class="drawing-panel v-card">
      <div class="drawing-panel-hint">{{ drawingHint }}</div>
      <div class="drawing-panel-controls">
        <div class="color-picker">
          <button
            v-for="color in drawingColors"
            :key="color"
            type="button"
            class="color-btn"
            :class="{ active: drawingColor === color }"
            :style="{ backgroundColor: color }"
            @click="setDrawingColor(color)"
          ></button>
        </div>
        <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="clearCanvas">Clear</button>
        <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="cancelDrawing">Cancel</button>
      </div>
    </div>

    <div class="add-comment">
      <input v-if="showNameInput" :value="userNameInput" @input="updateUserNameInput" placeholder="Your name" class="name-input"/>

      <div v-if="pendingAnnotation" class="pending-annotation">
        <svg class="icon"><use href="#icon-pen"/></svg>
        <span>Drawing attached</span>
        <button type="button" @click="clearPendingAnnotation">×</button>
      </div>

      <div v-if="pendingVoiceNote && !replyTarget" class="pending-voice-note">
        <CommentVoiceNote
          :attachment="pendingVoiceNote"
          :url="pendingVoiceNote.previewUrl"
          compact
        />
        <button type="button" class="pending-attachment-remove" aria-label="Remove voice note" @click="removePendingVoiceNote">×</button>
      </div>

      <div v-if="pendingCommentAttachments.length" class="pending-attachments">
        <div v-for="attachment in pendingCommentAttachments" :key="attachment.id" class="pending-attachment">
          <img v-if="attachment.kind === 'image' && attachment.previewUrl" :src="attachment.previewUrl" :alt="attachment.name || ''"/>
          <div v-else class="pending-attachment-file">
            <svg class="icon"><use :href="pendingAttachmentIcon(attachment)"/></svg>
            <span class="pending-attachment-name">{{ attachment.name }}</span>
          </div>
          <button type="button" class="pending-attachment-remove" @click="removePendingCommentAttachment(attachment.id)">×</button>
        </div>
      </div>

      <div class="composer">
        <textarea
          v-if="voiceRecorderState !== 'recording' || !!replyTarget"
          ref="commentTextarea"
          class="composer__textarea"
          :value="replyTarget ? '' : newComment"
          :placeholder="topLevelCommentPlaceholder"
          rows="1"
          @input="updateNewComment"
          @keydown.enter.ctrl="postMediaComment"
        ></textarea>
        <input
          v-if="voiceRecorderState !== 'recording' || !!replyTarget"
          ref="commentAttachmentInput"
          type="file"
          accept="image/*,video/*,audio/*,.mxf,application/mxf"
          multiple
          class="comment-attachment-input"
          @change="handleCommentAttachmentChange"
          hidden
        />
        <div v-if="voiceRecorderState === 'recording' && !replyTarget" class="voice-recording" role="status" aria-label="Recording voice note">
          <span class="voice-recording__dot" aria-hidden="true"></span>
          <div class="voice-recording__levels" aria-hidden="true">
            <span v-for="(level, index) in voiceRecorderLevels" :key="index" :style="{ height: `${Math.max(12, level * 100)}%` }"></span>
          </div>
          <time class="voice-recording__time">{{ formatVoiceDuration(voiceRecorderElapsed) }}</time>
          <button type="button" class="voice-recording__action" aria-label="Stop recording" title="Stop recording" @click="stopVoiceRecording">
            <span class="voice-recording__stop"></span>
          </button>
          <button type="button" class="voice-recording__action is-cancel" aria-label="Cancel recording" title="Cancel recording" @click="cancelVoiceRecording">
            <svg class="icon"><use href="#icon-close" /></svg>
          </button>
        </div>
        <div v-if="voiceRecorderState !== 'recording' || !!replyTarget" class="composer__actions">
          <span v-if="currentUser" class="composer__meta">
            Commenting as <strong>{{ currentUser.display_name }}</strong>
          </span>
          <button type="button" class="composer__action" @click="triggerCommentAttachmentPicker" :disabled="pendingAttachmentCount >= maxAttachments" title="Add attachment">
            <svg class="icon"><use href="#icon-link"/></svg>
          </button>
          <button type="button" class="composer__action" @click="startAnnotationForComment" :disabled="isDrawingMode" title="Add Drawing">
            <svg class="icon"><use href="#icon-pen"/></svg>
          </button>
          <button v-if="voiceRecorderSupported" type="button" class="composer__action" @click="startVoiceRecording" :disabled="pendingAttachmentCount >= maxAttachments || !!pendingVoiceNote || !!replyTarget" aria-label="Record voice note" title="Record voice note">
            <svg class="icon"><use href="#icon-mic"/></svg>
          </button>
          <button type="button" class="composer__action composer__action--submit" @click="postMediaComment" :disabled="!!replyTarget || !canSubmitComment" title="Post comment">
            <svg class="icon"><use href="#icon-check"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, toRefs, watch } from 'vue'
import { useOutsideClick } from '../../composables/useOutsideClick'
import { getPdfAnnotationTarget } from '../../lib/annotations'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useProjectTrackerSelectionStore } from '../../ownership/projectTrackerSelection'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { getCommentAvatarStyle as getAvatarStyle, getCommentInitials as getInitials } from '../../utils/commentDisplay'
import { formatIsoTimestamp, formatLocaleDateTime, normalizeTimestamp } from '../../utils/formatters'
import { segmentTextLinks } from '../../utils/textSanitization'
import CommentAttachmentCard from './CommentAttachmentCard.vue'
import CommentVoiceNote from './CommentVoiceNote.vue'

const props = defineProps({
  comments: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null },
  userName: { type: String, default: '' },
  userNameInput: { type: String, default: '' },
  newComment: { type: String, default: '' },
  pendingAnnotation: { type: String, default: '' },
  replyTarget: { type: Object, default: null },
  pendingCommentAttachments: { type: Array, default: () => [] },
  pendingVoiceNote: { type: Object, default: null },
  voiceRecorderState: { type: String, default: 'idle' },
  voiceRecorderSupported: { type: Boolean, default: false },
  voiceRecorderElapsed: { type: Number, default: 0 },
  voiceRecorderLevels: { type: Array, default: () => [] },
  drawingColors: { type: Array, default: () => [] },
  drawingColor: { type: String, default: '#ffffff' },
  isDrawingMode: { type: Boolean, default: false },
  isViewingImage: { type: Boolean, default: false },
  isViewingPdf: { type: Boolean, default: false },
  isViewingVideo: { type: Boolean, default: false },
  activityFocusCommentId: { type: [String, Number], default: null },
  isAdmin: { type: Boolean, default: false },
  maxAttachments: { type: Number, default: 3 },
  formatTimecode: { type: Function, required: true },
  getCommentAttachmentUrl: { type: Function, required: true },
  onHandleCommentClick: { type: Function, required: true },
  onToggleResolve: { type: Function, required: true },
  onDeleteComment: { type: Function, required: true },
  onOpenAttachmentLightbox: { type: Function, required: true },
  onClearCanvas: { type: Function, required: true },
  onCancelDrawing: { type: Function, required: true },
  onClearPendingAnnotation: { type: Function, required: true },
  onRemovePendingCommentAttachment: { type: Function, required: true },
  onHandleCommentAttachmentChange: { type: Function, required: true },
  onAddPendingCommentReferences: { type: Function, required: true },
  onStartVoiceRecording: { type: Function, required: true },
  onStopVoiceRecording: { type: Function, required: true },
  onCancelVoiceRecording: { type: Function, required: true },
  onRemovePendingVoiceNote: { type: Function, required: true },
  onStartAnnotationForComment: { type: Function, required: true },
  onStartReply: { type: Function, required: true },
  onCancelReply: { type: Function, required: true },
  onPostMediaComment: { type: Function, required: true }
})

const emit = defineEmits(['update:newComment', 'update:userNameInput', 'update:drawingColor'])
const {
  comments,
  currentUser,
  userName,
  userNameInput,
  newComment,
  pendingAnnotation,
  replyTarget,
  pendingCommentAttachments,
  pendingVoiceNote,
  voiceRecorderState,
  voiceRecorderSupported,
  voiceRecorderElapsed,
  voiceRecorderLevels,
  drawingColors,
  drawingColor,
  isDrawingMode,
  isViewingImage,
  isViewingPdf,
  isViewingVideo,
  isAdmin,
  maxAttachments,
  formatTimecode,
  getCommentAttachmentUrl
} = toRefs(props)
const commentAttachmentInput = ref(null)
const commentTextarea = ref(null)
const { picker } = useFileBrowserStore()
const { currentProject } = useProjectTrackerSelectionStore()
const { shareMode } = useShareAccessContext()

const showNameInput = computed(() => !props.currentUser && !props.userName)
const replyPlaceholder = computed(() => `Reply to ${props.replyTarget?.user_name || 'comment'}...`)
const topLevelCommentPlaceholder = computed(() => props.pendingAnnotation ? 'Add a note (optional)...' : 'Leave your comment...')
const pendingAttachmentCount = computed(() => props.pendingCommentAttachments.length + (props.pendingVoiceNote ? 1 : 0))
const canSubmitComment = computed(() => !!props.newComment.trim() || !!props.pendingAnnotation || pendingAttachmentCount.value > 0)
const drawingHint = computed(() => `Drawing on ${props.isViewingVideo ? 'frame' : props.isViewingImage ? 'image' : 'document'} • Post to save`)

function pdfPageLabel(comment) {
  const target = getPdfAnnotationTarget(comment)
  return target ? `Page ${target.page}` : ''
}

function isReplyComposerFor(comment) {
  return !!props.replyTarget?.id && props.replyTarget.id === comment?.id
}

function isActivityFocusComment(comment) {
  return String(props.activityFocusCommentId || '') === String(comment?.id || '')
}

function updateNewComment(event) {
  emit('update:newComment', event.target.value)
  resizeCommentTextarea(event.target)
}

function updateUserNameInput(event) {
  emit('update:userNameInput', event.target.value)
}

function setDrawingColor(color) {
  emit('update:drawingColor', color)
}

function handleCommentClick(comment) {
  props.onHandleCommentClick(comment)
}

function toggleResolve(commentId) {
  props.onToggleResolve(commentId)
}

function deleteComment(commentId) {
  props.onDeleteComment(commentId)
}

function openAttachmentLightbox(comment, attachment) {
  props.onOpenAttachmentLightbox(comment, attachment)
}

function clearCanvas() {
  props.onClearCanvas()
}

function cancelDrawing() {
  props.onCancelDrawing()
}

function clearPendingAnnotation() {
  props.onClearPendingAnnotation()
}

function removePendingCommentAttachment(id) {
  props.onRemovePendingCommentAttachment(id)
}

function triggerCommentAttachmentPicker() {
  if (pendingAttachmentCount.value >= props.maxAttachments) return
  if (props.currentUser && currentProject.value?.id && !shareMode.value) {
    void picker.openCommentReferencePicker({
      limit: props.maxAttachments - pendingAttachmentCount.value,
      onApply: props.onAddPendingCommentReferences,
      onUpload: triggerLocalCommentAttachmentPicker,
    })
    return
  }
  triggerLocalCommentAttachmentPicker()
}

function triggerLocalCommentAttachmentPicker() {
  const input = Array.isArray(commentAttachmentInput.value)
    ? commentAttachmentInput.value[0]
    : commentAttachmentInput.value
  input?.click()
}

function pendingAttachmentIcon(attachment) {
  if (attachment?.target_type === 'tracker') return '#icon-project'
  if (attachment?.target_type === 'page') return '#icon-layout'
  if (attachment?.kind === 'pdf') return '#icon-pdf'
  if (attachment?.kind === 'image') return '#icon-image'
  if (attachment?.kind === 'video') return '#icon-video'
  if (attachment?.kind === 'audio') return '#icon-mic'
  return '#icon-file'
}

function resizeCommentTextarea(target) {
  if (!target) return
  target.style.height = 'auto'
  target.style.height = `${target.scrollHeight}px`
}

function resizeActiveCommentTextareas() {
  const textareas = Array.isArray(commentTextarea.value)
    ? commentTextarea.value
    : [commentTextarea.value]
  textareas.forEach(resizeCommentTextarea)
}

watch(() => props.newComment, () => {
  nextTick(resizeActiveCommentTextareas)
})

useOutsideClick(null, cancelReply, {
  enabled: computed(() => Boolean(props.replyTarget) && !props.isDrawingMode),
  isInside: event => event.target instanceof Element
    && Boolean(event.target.closest('.comment-inline-composer, .comment-thread-reply-button')),
})

function startReply(comment) {
  props.onStartReply(comment)
}

function cancelReply() {
  props.onCancelReply()
}

function handleCommentAttachmentChange(event) {
  props.onHandleCommentAttachmentChange(event)
}

function startAnnotationForComment() {
  props.onStartAnnotationForComment()
}

function startVoiceRecording() {
  props.onStartVoiceRecording()
}

function stopVoiceRecording() {
  props.onStopVoiceRecording()
}

function cancelVoiceRecording() {
  props.onCancelVoiceRecording()
}

function removePendingVoiceNote() {
  props.onRemovePendingVoiceNote()
}

function formatVoiceDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function postMediaComment() {
  props.onPostMediaComment()
}

function normalizeCommentTime(value) {
  return normalizeTimestamp(value)
}

function formatCommentPostedAt(value) {
  const timestamp = normalizeCommentTime(value)
  if (!timestamp) return ''
  return formatLocaleDateTime(timestamp, {
    unit: 'milliseconds',
    options: { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' },
  })
}

function formatRelativeTime(value) {
  const timestamp = normalizeCommentTime(value)
  if (!timestamp) return ''
  const diff = Date.now() - timestamp
  if (diff < 0) return 'Just now'
  const sec = Math.floor(diff / 1000)
  if (sec < 45) return 'Just now'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h`
  const day = Math.floor(hr / 24)
  if (day < 7) return `${day}d`
  const wk = Math.floor(day / 7)
  if (wk < 5) return `${wk}w`
  const mo = Math.floor(day / 30)
  if (mo < 12) return `${mo}mo`
  const yr = Math.floor(day / 365)
  return `${yr}y`
}

function formatCommentPostedTitle(value) {
  const timestamp = normalizeCommentTime(value)
  if (!timestamp) return ''
  return formatLocaleDateTime(timestamp, {
    unit: 'milliseconds',
    options: { year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' },
  })
}

function commentPostedDatetime(value) {
  const timestamp = normalizeCommentTime(value)
  if (!timestamp) return ''
  return formatIsoTimestamp(timestamp, { unit: 'milliseconds' })
}
</script>

<style>
.comments-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.comments-list {
  --comment-avatar-size: 24px;
  --comment-gutter: 9px;
  flex: 1;
  overflow-y: auto;
  padding: 4px 6px 12px;
}

.empty-comments {
  min-height: 140px;
}

/* Borderless rows: a thread reads as a conversation rather than a stack of
   boxes, and drops the ~20px of border + card gap each comment used to cost. */
.comment {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 9px 9px 10px;
  border-radius: var(--v-radius-md);
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.comment + .comment {
  box-shadow: inset 0 1px 0 var(--v-divider-subtle);
}

.comment:hover {
  background: color-mix(in srgb, var(--v-bg-hover) 55%, transparent);
}

.comment.is-activity-focus,
.comment-reply.is-activity-focus {
  background: color-mix(in srgb, var(--v-accent) 9%, transparent);
}

/* Accent rail marks the comment the activity tray sent you to. */
.comment.is-activity-focus::before {
  content: '';
  position: absolute;
  inset: 6px auto 6px -2px;
  width: 2px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
}

.comment.resolved {
  opacity: 0.55;
}

.comment-entry {
  position: relative;
  display: grid;
  grid-template-columns: var(--comment-avatar-size) minmax(0, 1fr);
  column-gap: var(--comment-gutter);
  align-items: start;
}

.comment-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--comment-avatar-size);
  height: var(--comment-avatar-size);
  margin-top: 0;
  border-radius: var(--v-radius-full);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
  font-family: var(--v-font);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1;
  color: #fff;
  flex-shrink: 0;
  user-select: none;
}

.comment-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 2px;
}

.comment-replies {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 1px 0 0 calc(var(--comment-avatar-size) / 2);
  padding: 1px 0 0 calc(var(--comment-avatar-size) / 2 + var(--comment-gutter) - 1px);
  border-left: 1px solid color-mix(in srgb, var(--v-control-border) 48%, transparent);
}

/* A smaller avatar is all the de-emphasis a reply needs. */
.comment-reply {
  --comment-avatar-size: 19px;
}

.comment-reply.resolved {
  opacity: 0.55;
}

.comment-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  min-height: 16px;
  position: relative;
}

/* Never wraps — a long name truncates instead of pushing the row to two lines,
   so every comment in the list keeps the same rhythm. */
.comment-header-main {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1 1 auto;
}

.comment-header-tools {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: 0 0 auto;
  align-self: center;
}

.author {
  min-width: 0;
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  color: var(--v-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comment-posted-at {
  flex: 0 0 auto;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 500;
  white-space: nowrap;
}

/* The index is reference material, not something you scan for — it and the
   row actions both surface only when you're actually on the comment. */
.comment-number,
.comment-secondary-actions {
  flex: 0 0 auto;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--v-transition-fast);
}

.comment-number {
  color: color-mix(in srgb, var(--v-text-muted) 62%, transparent);
  font-size: var(--v-text-2xs);
  font-weight: 550;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.comment-secondary-actions {
  display: flex;
  align-items: center;
  gap: 1px;
}

.comment:hover .comment-number,
.comment:hover > .comment-main .comment-secondary-actions,
.comment-reply:hover .comment-secondary-actions,
.comment:focus-within .comment-number,
.comment-secondary-actions:focus-within {
  opacity: 1;
  pointer-events: auto;
}

.comment-action-button {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: color var(--v-transition-fast), background var(--v-transition-fast);
}

.comment-action-button:hover {
  background: color-mix(in srgb, var(--v-surface-inline-strong) 70%, transparent);
  color: var(--v-text);
}

.comment-action-button.is-danger:hover {
  background: var(--v-danger-bg);
  color: var(--v-danger);
}

.comment-action-button .icon {
  width: 12px;
  height: 12px;
}

.comment-text {
  margin: 0;
  display: block;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.42;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.comment-message {
  min-width: 0;
}

/* Clicking a comment seeks to it, so the timecode is a destination, not a
   warning — it stays quiet until you hover the row that will take you there. */
.comment-timecode {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  height: 16px;
  padding: 0 5px;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text-muted) 14%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.comment:hover .comment-timecode {
  background: color-mix(in srgb, var(--v-accent) 16%, transparent);
  color: color-mix(in srgb, var(--v-accent) 82%, var(--v-text));
}

.comment-annotation-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-annotation) 14%, transparent);
  color: var(--v-annotation);
}

.comment-annotation-chip .icon {
  width: 9px;
  height: 9px;
}

.comment-text-placeholder {
  color: var(--v-text-muted);
  font-style: italic;
}

.comment-text-link {
  color: var(--v-info);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  text-decoration-color: color-mix(in srgb, var(--v-info) 68%, transparent);
  transition: color var(--v-transition-fast);
}

.comment-text-link:hover {
  color: color-mix(in srgb, var(--v-info) 76%, white);
}

.comment-reply-button {
  align-self: flex-start;
  margin: 0;
  min-height: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 600;
  letter-spacing: 0;
  cursor: pointer;
  transition: color var(--v-transition-fast);
}

.comment-reply-button:hover {
  color: var(--v-accent);
  background: transparent;
  border-color: transparent;
}

/* Reply is the primary action on a thread, so it stays visible — hiding it
   until hover would both bury it and shift every row below on mouseover. */
.comment-thread-reply-button {
  align-self: flex-start;
  margin-left: calc(var(--comment-avatar-size) + var(--comment-gutter));
  line-height: 1;
}

.comment-inline-composer {
  margin: 4px 0 0 calc(var(--comment-avatar-size) + var(--comment-gutter));
  padding: 0;
  border: 0;
  background: transparent;
  cursor: default;
}

.comment-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.drawing-panel {
  margin: 0 8px 8px;
  padding: 8px 10px;
  border: 1px solid var(--v-warning-border);
  border-radius: var(--v-radius-sm);
  background: var(--v-warning-bg);
}

.drawing-panel-hint {
  margin-bottom: 8px;
  color: var(--v-annotation);
  font-size: var(--v-text-xs);
  text-align: center;
}

.drawing-panel-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.color-picker {
  display: flex;
  gap: 5px;
}

.color-btn {
  width: 22px;
  height: 22px;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
}

.color-btn.active {
  border-color: white;
  box-shadow: 0 0 0 1px var(--v-accent);
}

.add-comment {
  padding: 8px 8px 10px;
  padding-bottom: calc(10px + env(safe-area-inset-bottom, 0));
  border-top: 1px solid var(--v-divider);
  background: transparent;
}

.name-input {
  width: 100%;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inline);
  color: var(--v-text);
  font-size: var(--v-text-sm);
}

.name-input:focus {
  outline: none;
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.pending-annotation {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding: 6px 8px;
  border: 1px solid color-mix(in srgb, var(--v-warning-border) 70%, transparent);
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-warning-bg) 80%, transparent);
  color: var(--v-annotation);
  font-size: var(--v-text-xs);
}

.pending-annotation .icon {
  width: 13px;
  height: 13px;
}

.pending-annotation button {
  margin-left: auto;
  padding: 0 4px;
  border: none;
  background: none;
  color: inherit;
  font-size: var(--v-text-lg);
  line-height: 1;
  cursor: pointer;
}

.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.pending-voice-note {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  margin-bottom: 8px;
  padding: 2px 4px 2px 2px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 70%, transparent);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-tint-strong);
}

.pending-voice-note .pending-attachment-remove {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-md);
}

.pending-voice-note .pending-attachment-remove:hover {
  background: var(--v-danger-bg);
}

.pending-attachment {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 70%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-tint-strong);
}

.pending-attachment img {
  width: 36px;
  height: 28px;
  border-radius: 4px;
  background: var(--v-bg-black);
  object-fit: cover;
}

.pending-attachment-file {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--v-text-xs);
  color: var(--v-text-secondary);
}

.pending-attachment-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-attachment-remove {
  padding: 2px 4px;
  border: none;
  background: none;
  color: var(--v-text-muted);
  cursor: pointer;
}

.pending-attachment-remove:hover,
.pending-annotation button:hover {
  color: var(--v-danger);
}

/* ── Composer ───────────────────────────────────────────────────────
   Single integrated card. Meta label sits inside, textarea is flat,
   actions anchor bottom-right. Focus ring lives on the card, not the
   textarea, so "Commenting as" feels part of the same surface. */
.composer {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 8px 7px 11px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-inline) 88%, var(--v-bg-base));
  transition: border-color var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.composer:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inline-strong);
}

.composer:focus-within {
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

/* Rides the action row's empty left half rather than owning a line of its own. */
.composer__meta {
  margin-right: auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--v-text-2xs);
  font-weight: 500;
  color: var(--v-text-muted);
}

.composer__meta strong {
  color: var(--v-text-secondary);
  font-weight: 600;
}

.composer__textarea {
  width: 100%;
  min-height: 26px;
  max-height: 160px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--v-text);
  resize: none;
  overflow: hidden;
  font-family: var(--v-font);
  font-size: var(--v-text-base);
  line-height: 1.45;
  field-sizing: content;
}

.composer__textarea:focus {
  outline: none;
}

.composer__textarea::placeholder {
  color: var(--v-text-muted);
}

/* Actions sit on their own row under the field. The old absolute placement
   needed a hand-tuned right padding on the textarea that broke as soon as the
   button count or font size changed — worst on mobile at 16px. */
.composer__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  margin-top: 1px;
}

/* Cancel is the odd one out — it belongs on the opposite end. */
.comment-inline-cancel {
  margin-right: auto;
}

.composer__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
  transition: background var(--v-transition-fast), color var(--v-transition-fast), transform var(--v-transition-fast);
}

.composer__action:hover:not(:disabled) {
  background: var(--v-bg-hover);
  color: var(--v-text);
}

.composer__action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.composer__action .icon {
  width: 13px;
  height: 13px;
}

.composer__action--submit {
  background: var(--v-accent);
  color: var(--v-on-accent);
}

.composer__action--submit:hover:not(:disabled) {
  background: var(--v-accent-hover);
  color: var(--v-on-accent);
}

.composer__action--submit:disabled {
  background: color-mix(in srgb, var(--v-accent) 28%, transparent);
  color: color-mix(in srgb, var(--v-on-accent) 70%, var(--v-text-muted));
  opacity: 1;
}

.composer--inline-reply {
  width: 100%;
}

.voice-recording {
  display: grid;
  grid-template-columns: 8px minmax(64px, 1fr) auto 28px 28px;
  align-items: center;
  gap: 6px;
  min-height: 40px;
}

.voice-recording__dot {
  width: 7px;
  height: 7px;
  border-radius: var(--v-radius-full);
  background: var(--v-danger);
  animation: voice-recording-pulse 1.2s var(--v-ease-soft) infinite;
}

.voice-recording__levels {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 24px;
  min-width: 0;
}

.voice-recording__levels span {
  flex: 1 1 2px;
  max-width: 4px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent) 74%, var(--v-text-muted));
  transition: height 90ms linear;
}

.voice-recording__time {
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-variant-numeric: tabular-nums;
}

.voice-recording__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inline);
  color: var(--v-text-secondary);
  cursor: pointer;
}

.voice-recording__action:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
}

.voice-recording__action.is-cancel:hover {
  border-color: var(--v-danger-border-hover);
  background: var(--v-danger-bg-hover);
  color: var(--v-danger);
}

.voice-recording__action .icon {
  width: 12px;
  height: 12px;
}

.voice-recording__stop {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--v-accent);
}

@keyframes voice-recording-pulse {
  50% { opacity: 0.35; }
}

.comment-inline-cancel {
  height: 28px;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 600;
  cursor: pointer;
  transition: color var(--v-transition-fast);
}

.comment-inline-cancel:hover {
  color: var(--v-text);
}

@media (max-width: 768px) {
  .comments-section {
    --comments-safe-bottom: max(8px, calc(env(safe-area-inset-bottom, 0px) + 4px));
  }

  .comments-list {
    padding: 4px var(--v-viewer-mobile-content-gutter) 12px;
  }

  .empty-comments {
    min-height: 120px;
  }

  /* No hover on touch, so the row actions and index stay put. */
  .comment-number,
  .comment-secondary-actions {
    opacity: 0.7;
    pointer-events: auto;
  }

  .comment-action-button {
    width: 30px;
    height: 30px;
  }

  .comment-text {
    font-size: var(--v-text-base);
    line-height: 1.45;
  }

  .comment-thread-reply-button {
    min-height: 30px;
  }

  .add-comment {
    position: sticky;
    bottom: 0;
    z-index: 3;
    margin-top: auto;
    padding: 8px var(--v-viewer-mobile-content-gutter) var(--comments-safe-bottom);
    border-top-color: var(--v-divider);
    background: var(--v-bg-base);
  }

  .composer {
    padding: 10px 10px 9px 12px;
  }

  /* 16px keeps iOS from zooming the viewport on focus. */
  .composer__textarea {
    min-height: 30px;
    font-size: var(--v-text-xl);
    line-height: 1.4;
  }

  .composer__action {
    width: 34px;
    height: 34px;
  }

  .composer__action .icon {
    width: 14px;
    height: 14px;
  }

  .voice-recording {
    min-height: 44px;
  }
}

@media (max-width: 430px) {
  .voice-recording {
    grid-template-columns: 8px minmax(48px, 1fr) auto 28px 28px;
    gap: 5px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .voice-recording__dot {
    animation: none;
  }
}
</style>
