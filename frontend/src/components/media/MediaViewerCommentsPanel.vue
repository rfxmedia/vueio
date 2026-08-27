<template>
  <div class="comments-section" :class="{ 'is-empty': commentsWithSegments.length === 0 }">
    <div class="comments-list">
      <div v-if="commentsWithSegments.length === 0" class="v-empty-state v-empty-state-compact empty-comments">
        <svg class="icon v-empty-state-icon"><use href="#icon-comment"/></svg>
        <p class="v-empty-state-title">No comments yet</p>
        <p class="v-empty-state-copy">Add the first review note below.</p>
      </div>

      <div
        v-for="(comment, commentIndex) in commentsWithSegments"
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
                <template v-for="(segment, segmentIndex) in comment.textSegments" :key="`${comment.id}-${segmentIndex}`">
                  <a
                    v-if="segment.type === 'link'"
                    class="comment-text-link"
                    :href="segment.href"
                    target="_blank"
                    rel="noopener noreferrer"
                    @click.stop
                  >{{ segment.text }}</a>
                  <button
                    v-else-if="segment.type === 'mention'"
                    type="button"
                    class="comment-mention-chip"
                    :title="`Open ${segment.reference.name || segment.text}`"
                    @click.stop="openInlineMention(comment, segment.reference)"
                  >
                    <svg class="icon"><use :href="pendingAttachmentIcon(segment.reference)"/></svg>
                    <span>{{ segment.text }}</span>
                  </button>
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
                  <template v-for="(segment, segmentIndex) in reply.textSegments" :key="`${reply.id}-${segmentIndex}`">
                    <a
                      v-if="segment.type === 'link'"
                      class="comment-text-link"
                      :href="segment.href"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                    >{{ segment.text }}</a>
                    <button
                      v-else-if="segment.type === 'mention'"
                      type="button"
                      class="comment-mention-chip"
                      :title="`Open ${segment.reference.name || segment.text}`"
                      @click.stop="openInlineMention(reply, segment.reference)"
                    >
                      <svg class="icon"><use :href="pendingAttachmentIcon(segment.reference)"/></svg>
                      <span>{{ segment.text }}</span>
                    </button>
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

          <div
            ref="replyComposer"
            class="composer composer--inline-reply"
            @dragenter="handleCommentDragEnter($event, 'reply')"
            @dragover="handleCommentDragOver($event, 'reply')"
            @dragleave="handleCommentDragLeave($event, 'reply')"
            @drop="handleCommentDrop($event, 'reply')"
          >
            <div
              v-if="projectDragComposer === 'reply'"
              class="composer__drop-hint"
              :class="{ 'is-blocked': Boolean(projectDragBlockedReason) }"
              role="status"
              aria-live="polite"
            >
              <svg class="icon" aria-hidden="true"><use :href="projectDragBlockedReason ? '#icon-close' : '#icon-link'"/></svg>
              <strong>{{ projectDragTitle }}</strong>
              <span>{{ projectDragBlockedReason || 'Release to add inline mentions.' }}</span>
            </div>
            <VoiceRecordingStatus
              v-if="voiceRecorderState === 'recording' && !!replyTarget"
              :levels="voiceRecorderLevels"
              :elapsed="voiceRecorderElapsed"
              @stop="stopVoiceRecording"
              @cancel="cancelVoiceRecording"
            />
            <textarea
              v-else
              ref="replyCommentTextarea"
              class="composer__textarea"
              :value="newComment"
              :placeholder="replyPlaceholder"
              :role="mentionContext?.enabled ? 'combobox' : undefined"
              :aria-autocomplete="mentionContext?.enabled ? 'list' : undefined"
              :aria-expanded="mentionContext?.enabled ? String(mentionOpenFor('reply')) : undefined"
              :aria-controls="mentionOpenFor('reply') ? mentionListboxId : undefined"
              :aria-activedescendant="mentionOpenFor('reply') ? mentionActiveDescendant : undefined"
              rows="1"
              :disabled="commentPosting"
              @input="updateNewComment($event, 'reply')"
              @click="syncMentionFromTextarea($event, 'reply')"
              @select="syncMentionFromTextarea($event, 'reply')"
              @keyup="handleCommentKeyup($event, 'reply')"
              @blur="handleMentionBlur"
              @keydown="handleCommentKeydown($event, 'reply')"
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
              <button type="button" class="composer__action" @click="triggerCommentAttachmentPicker" :disabled="commentPosting || pendingAttachmentCount >= maxAttachments" title="Add attachment">
                <svg class="icon"><use href="#icon-link"/></svg>
              </button>
              <button type="button" class="composer__action" @click="startAnnotationForComment" :disabled="commentPosting || isDrawingMode" title="Add Drawing">
                <svg class="icon"><use href="#icon-pen"/></svg>
              </button>
              <button v-if="voiceRecorderSupported" type="button" class="composer__action" @click="startVoiceRecording" :disabled="commentPosting || pendingAttachmentCount >= maxAttachments || !!pendingVoiceNote" aria-label="Record voice note" title="Record voice note">
                <svg class="icon"><use href="#icon-mic"/></svg>
              </button>
              <button type="button" class="composer__action composer__action--submit" @click="postMediaComment" :disabled="commentPosting || !canSubmitComment" :title="commentPosting ? 'Posting reply' : 'Post reply'">
                <svg class="icon" :class="{ 'is-spinning': commentPosting }"><use :href="commentPosting ? '#icon-loader' : '#icon-check'"/></svg>
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

      <div
        ref="topLevelComposer"
        class="composer"
        @dragenter="handleCommentDragEnter($event, 'top')"
        @dragover="handleCommentDragOver($event, 'top')"
        @dragleave="handleCommentDragLeave($event, 'top')"
        @drop="handleCommentDrop($event, 'top')"
      >
        <div
          v-if="projectDragComposer === 'top'"
          class="composer__drop-hint"
          :class="{ 'is-blocked': Boolean(projectDragBlockedReason) }"
          role="status"
          aria-live="polite"
        >
          <svg class="icon" aria-hidden="true"><use :href="projectDragBlockedReason ? '#icon-close' : '#icon-link'"/></svg>
          <strong>{{ projectDragTitle }}</strong>
          <span>{{ projectDragBlockedReason || 'Release to add inline mentions.' }}</span>
        </div>
        <textarea
          v-if="voiceRecorderState !== 'recording' || !!replyTarget"
          ref="topLevelCommentTextarea"
          class="composer__textarea"
          :value="replyTarget ? '' : newComment"
          :placeholder="topLevelCommentPlaceholder"
          :role="mentionContext?.enabled ? 'combobox' : undefined"
          :aria-autocomplete="mentionContext?.enabled ? 'list' : undefined"
          :aria-expanded="mentionContext?.enabled ? String(mentionOpenFor('top')) : undefined"
          :aria-controls="mentionOpenFor('top') ? mentionListboxId : undefined"
          :aria-activedescendant="mentionOpenFor('top') ? mentionActiveDescendant : undefined"
          rows="1"
          :disabled="commentPosting"
          @input="updateNewComment($event, 'top')"
          @click="syncMentionFromTextarea($event, 'top')"
          @select="syncMentionFromTextarea($event, 'top')"
          @keyup="handleCommentKeyup($event, 'top')"
          @blur="handleMentionBlur"
          @keydown="handleCommentKeydown($event, 'top')"
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
        <VoiceRecordingStatus
          v-if="voiceRecorderState === 'recording' && !replyTarget"
          :levels="voiceRecorderLevels"
          :elapsed="voiceRecorderElapsed"
          @stop="stopVoiceRecording"
          @cancel="cancelVoiceRecording"
        />
        <div v-if="voiceRecorderState !== 'recording' || !!replyTarget" class="composer__actions">
          <span v-if="currentUser" class="composer__meta">
            Commenting as <strong>{{ currentUser.display_name }}</strong>
          </span>
          <button type="button" class="composer__action" @click="triggerCommentAttachmentPicker" :disabled="commentPosting || pendingAttachmentCount >= maxAttachments" title="Add attachment">
            <svg class="icon"><use href="#icon-link"/></svg>
          </button>
          <button type="button" class="composer__action" @click="startAnnotationForComment" :disabled="commentPosting || isDrawingMode" title="Add Drawing">
            <svg class="icon"><use href="#icon-pen"/></svg>
          </button>
          <button v-if="voiceRecorderSupported" type="button" class="composer__action" @click="startVoiceRecording" :disabled="commentPosting || pendingAttachmentCount >= maxAttachments || !!pendingVoiceNote || !!replyTarget" aria-label="Record voice note" title="Record voice note">
            <svg class="icon"><use href="#icon-mic"/></svg>
          </button>
          <button type="button" class="composer__action composer__action--submit" @click="postMediaComment" :disabled="commentPosting || !!replyTarget || !canSubmitComment" :title="commentPosting ? 'Posting comment' : 'Post comment'">
            <svg class="icon" :class="{ 'is-spinning': commentPosting }"><use :href="commentPosting ? '#icon-loader' : '#icon-check'"/></svg>
          </button>
        </div>
      </div>
    </div>

    <CommentMentionPopover
      :open="mentionOpen"
      :anchor="mentionAnchorElement"
      :mode="mentionMode"
      :query="mentionQuery"
      :groups="mentionGroups"
      :browse-path="mentionBrowsePath"
      :browse-rows="mentionBrowseRows"
      :browse-breadcrumbs="mentionBrowseBreadcrumbs"
      :loading="mentionLoading"
      :error="mentionError"
      :active-index="mentionActiveIndex"
      :listbox-id="mentionListboxId"
      @choose="chooseMention"
      @browse="mentionAutocomplete.enterBrowse"
      @back="mentionAutocomplete.goBack"
      @show-more="mentionAutocomplete.showMore"
      @set-active="setMentionActiveIndex"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, shallowRef, toRefs, watch } from 'vue'
import { commentMentionMarker, useCommentMentionAutocomplete } from '../../composables/useCommentMentionAutocomplete'
import { useOutsideClick } from '../../composables/useOutsideClick'
import { getPdfAnnotationTarget } from '../../lib/annotations'
import { projectContentItemTarget } from '../../lib/projectContentItems'
import { hasProjectItemDrag, readProjectItemDrag } from '../../lib/projectItemDrag'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useProjectTrackerSelectionStore } from '../../ownership/projectTrackerSelection'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { getCommentAvatarStyle as getAvatarStyle, getCommentInitials as getInitials } from '../../utils/commentDisplay'
import { formatIsoTimestamp, formatLocaleDateTime, normalizeTimestamp } from '../../utils/formatters'
import { segmentCommentText } from '../../utils/textSanitization'
import { notify } from '../../utils/toasts'
import CommentAttachmentCard from './CommentAttachmentCard.vue'
import CommentMentionPopover from './CommentMentionPopover.vue'
import CommentVoiceNote from './CommentVoiceNote.vue'
import VoiceRecordingStatus from './VoiceRecordingStatus.vue'

const props = defineProps({
  comments: { type: Array, default: () => [] },
  commentPosting: { type: Boolean, default: false },
  currentUser: { type: Object, default: null },
  userName: { type: String, default: '' },
  userNameInput: { type: String, default: '' },
  newComment: { type: String, default: '' },
  pendingAnnotation: { type: String, default: '' },
  replyTarget: { type: Object, default: null },
  pendingCommentAttachments: { type: Array, default: () => [] },
  mentionContext: { type: Object, default: () => ({ enabled: false, projectId: '', trackerId: '', shots: [] }) },
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
  onAddPendingInlineMention: { type: Function, default: () => false },
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
  commentPosting,
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
const topLevelCommentTextarea = ref(null)
const replyCommentTextarea = ref(null)
const topLevelComposer = ref(null)
const replyComposer = ref(null)
const activeMentionTextarea = shallowRef(null)
const activeMentionComposer = ref('')
const projectDragComposer = ref('')
const projectDragItemCount = ref(0)
const projectDragProjectId = ref('')
const projectDragDepth = { top: 0, reply: 0 }
const mentionListboxId = 'comment-mention-listbox'
const { picker } = useFileBrowserStore()
const { currentProject } = useProjectTrackerSelectionStore()
const { shareMode } = useShareAccessContext()

const showNameInput = computed(() => !props.currentUser && !props.userName)
const replyPlaceholder = computed(() => props.mentionContext?.enabled
  ? `Reply to ${props.replyTarget?.user_name || 'comment'}…  @ to mention`
  : `Reply to ${props.replyTarget?.user_name || 'comment'}...`)
const topLevelCommentPlaceholder = computed(() => {
  if (props.pendingAnnotation) return 'Add a note (optional)...'
  return props.mentionContext?.enabled ? 'Add a review note…  @ to mention' : 'Add a review note...'
})
const pendingAttachmentCount = computed(() => props.pendingCommentAttachments.length + (props.pendingVoiceNote ? 1 : 0))
const canSubmitComment = computed(() => !!props.newComment.trim() || !!props.pendingAnnotation || pendingAttachmentCount.value > 0)
const projectDragBlockedReason = computed(() => {
  if (!props.mentionContext?.enabled || !props.currentUser || shareMode.value) return 'Project mentions are unavailable here.'
  if (props.commentPosting) return 'Wait for the current comment to finish posting.'
  if (props.voiceRecorderState === 'recording') return 'Finish the voice recording before adding a mention.'
  if (projectDragComposer.value === 'top' && props.replyTarget) return 'Finish or cancel the reply first.'
  if (projectDragProjectId.value && projectDragProjectId.value !== props.mentionContext.projectId) {
    return 'These items belong to a different project.'
  }
  return ''
})
const projectDragTitle = computed(() => {
  if (projectDragBlockedReason.value) return 'Cannot mention these items'
  if (projectDragItemCount.value === 1) return 'Mention 1 item'
  if (projectDragItemCount.value > 1) return `Mention ${projectDragItemCount.value} items`
  return 'Mention project items'
})
const drawingHint = computed(() => `Drawing on ${props.isViewingVideo ? 'frame' : props.isViewingImage ? 'image' : 'document'} • Post to save`)
function commentWithSegments(comment) {
  const inlineReferences = (comment.attachments || []).filter(attachment => (
    attachment?.attachment_type === 'reference' && attachment?.marker
  ))
  return {
    ...comment,
    attachments: (comment.attachments || []).filter(attachment => !attachment?.marker),
    textSegments: segmentCommentText(comment.text, inlineReferences),
  }
}

const commentsWithSegments = computed(() => props.comments.map(comment => ({
  ...commentWithSegments(comment),
  replies: (comment.replies || []).map(commentWithSegments),
})))

const mentionAutocomplete = useCommentMentionAutocomplete({
  enabled: computed(() => props.mentionContext?.enabled),
  projectId: computed(() => props.mentionContext?.projectId),
  trackerId: computed(() => props.mentionContext?.trackerId),
  shots: computed(() => props.mentionContext?.shots || []),
})
const {
  open: mentionOpen,
  mode: mentionMode,
  query: mentionQuery,
  anchorElement: mentionAnchorElement,
  groups: mentionGroups,
  browsePath: mentionBrowsePath,
  browseRows: mentionBrowseRows,
  browseBreadcrumbs: mentionBrowseBreadcrumbs,
  loading: mentionLoading,
  error: mentionError,
  activeIndex: mentionActiveIndex,
  activeDescendant: mentionActiveDescendant,
} = mentionAutocomplete

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

function updateNewComment(event, composer) {
  emit('update:newComment', event.target.value)
  resizeCommentTextarea(event.target)
  syncMentionFromTextarea(event, composer)
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

function openInlineMention(comment, reference) {
  props.onOpenAttachmentLightbox(comment, reference)
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

function inspectCommentProjectDrag(event) {
  if (!hasProjectItemDrag(event?.dataTransfer)) return null
  return readProjectItemDrag(event.dataTransfer)
}

function syncCommentProjectDrag(payload, composer) {
  projectDragComposer.value = composer
  projectDragProjectId.value = payload?.projectId || ''
  projectDragItemCount.value = payload?.items?.length || 0
}

function resetCommentProjectDrag(composer = '') {
  if (composer) projectDragDepth[composer] = 0
  else {
    projectDragDepth.top = 0
    projectDragDepth.reply = 0
  }
  if (composer && projectDragComposer.value !== composer) return
  projectDragComposer.value = ''
  projectDragProjectId.value = ''
  projectDragItemCount.value = 0
}

function handleCommentDragEnter(event, composer) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  projectDragDepth[composer] += 1
  syncCommentProjectDrag(inspectCommentProjectDrag(event), composer)
}

function handleCommentDragOver(event, composer) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  if (projectDragComposer.value !== composer || !projectDragProjectId.value) {
    syncCommentProjectDrag(inspectCommentProjectDrag(event), composer)
  }
  event.dataTransfer.dropEffect = projectDragBlockedReason.value ? 'none' : 'copy'
}

function handleCommentDragLeave(event, composer) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.stopPropagation()
  projectDragDepth[composer] = Math.max(0, projectDragDepth[composer] - 1)
  if (projectDragDepth[composer] === 0) resetCommentProjectDrag(composer)
}

function insertDroppedMentions(items, composer) {
  const textarea = composer === 'reply' ? replyCommentTextarea.value : topLevelCommentTextarea.value
  if (!textarea) return false

  const targets = items
    .map(projectContentItemTarget)
    .filter(target => target && !target.disabled && ['folder', 'media_asset'].includes(target.target_type))
  if (!targets.length) {
    notify('These project items are not available as mentions yet.')
    return false
  }

  const markers = []
  const markerSet = new Set()
  for (const target of targets) {
    const baseMarker = commentMentionMarker(target)
    const marker = markerSet.has(baseMarker)
      ? commentMentionMarker({ ...target, label: target.path || target.target_id })
      : baseMarker
    if (props.onAddPendingInlineMention(target, marker) === false) break
    markers.push(marker)
    markerSet.add(marker)
  }
  if (!markers.length) return false

  const source = String(props.newComment || '')
  const hasActiveCaret = document.activeElement === textarea
  const start = hasActiveCaret && Number.isInteger(textarea.selectionStart) ? textarea.selectionStart : source.length
  const end = hasActiveCaret && Number.isInteger(textarea.selectionEnd) ? textarea.selectionEnd : start
  const before = source.slice(0, start)
  const after = source.slice(end)
  const leadingSpace = before && !/\s$/.test(before) ? ' ' : ''
  const trailingSpace = !after || !/^\s/.test(after) ? ' ' : ''
  const inserted = `${leadingSpace}${markers.join(' ')}${trailingSpace}`
  const text = `${before}${inserted}${after}`
  const caret = before.length + inserted.length

  activeMentionTextarea.value = textarea
  activeMentionComposer.value = composer
  mentionAutocomplete.dismiss()
  emit('update:newComment', text)
  nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(caret, caret)
    resizeCommentTextarea(textarea)
  })
  return true
}

function handleCommentDrop(event, composer) {
  if (!hasProjectItemDrag(event.dataTransfer)) return
  event.preventDefault()
  event.stopPropagation()
  const payload = inspectCommentProjectDrag(event)
  syncCommentProjectDrag(payload, composer)
  const blockedReason = projectDragBlockedReason.value
  resetCommentProjectDrag()
  if (!payload) {
    notify('Those sidebar items could not be read. Try dragging them again.')
    return
  }
  if (blockedReason) {
    notify(blockedReason)
    return
  }
  insertDroppedMentions(payload.items, composer)
}

function pendingAttachmentIcon(attachment) {
  if (attachment?.target_type === 'shot') return '#icon-video'
  if (attachment?.target_type === 'folder') return '#icon-folder'
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
  const textareas = [topLevelCommentTextarea.value, replyCommentTextarea.value]
  textareas.forEach(resizeCommentTextarea)
}

function mentionOpenFor(composer) {
  return mentionOpen.value && activeMentionComposer.value === composer
}

function syncMentionFromTextarea(event, composer) {
  if (composer === 'top' && props.replyTarget) {
    mentionAutocomplete.dismiss()
    return
  }
  const textarea = event?.currentTarget || event?.target
  if (!textarea) return
  activeMentionTextarea.value = textarea
  activeMentionComposer.value = composer
  const anchor = composer === 'reply' ? replyComposer.value : topLevelComposer.value
  mentionAutocomplete.syncFromTextarea(textarea, anchor)
}

function handleCommentKeydown(event, composer) {
  if (event.isComposing) return
  if (mentionOpenFor(composer)) {
    const result = mentionAutocomplete.handleKeydown(event)
    if (result?.item) chooseMention(result.item)
    if (result?.handled) return
  }
  if (event.key === 'Enter' && event.ctrlKey) postMediaComment()
}

function handleCommentKeyup(event, composer) {
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    syncMentionFromTextarea(event, composer)
  }
}

function chooseMention(item) {
  const selectable = mentionAutocomplete.activate(item)
  if (!selectable) return
  const textarea = activeMentionTextarea.value
  const result = mentionAutocomplete.select(selectable, textarea?.value ?? props.newComment)
  if (!result) return
  if (props.onAddPendingInlineMention(result.item, result.marker) === false) return
  emit('update:newComment', result.text)
  nextTick(() => {
    const target = activeMentionTextarea.value
    if (!target) return
    target.focus()
    target.setSelectionRange(result.caret, result.caret)
    resizeCommentTextarea(target)
  })
}

function setMentionActiveIndex(index) {
  mentionActiveIndex.value = index
}

function handleMentionBlur() {
  window.setTimeout(() => mentionAutocomplete.dismiss(), 0)
}

watch(() => props.newComment, () => {
  nextTick(resizeActiveCommentTextareas)
  if (!props.newComment) mentionAutocomplete.reset()
})

watch(() => props.replyTarget?.id, () => {
  mentionAutocomplete.dismiss()
  activeMentionTextarea.value = null
  activeMentionComposer.value = ''
  resetCommentProjectDrag()
})

useOutsideClick(null, cancelReply, {
  enabled: computed(() => Boolean(props.replyTarget) && !props.isDrawingMode),
  isInside: event => event.target instanceof Element
    && Boolean(event.target.closest('.comment-inline-composer, .comment-thread-reply-button, .comment-mention-popover')),
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
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.comments-list {
  --comment-avatar-size: 26px;
  --comment-gutter: 10px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 12px 16px;
}

.comments-section.is-empty .comments-list {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.empty-comments {
  flex: 1;
  min-height: 160px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.empty-comments .v-empty-state-icon {
  width: 32px;
  height: 32px;
  opacity: 0.46;
}

.empty-comments .v-empty-state-copy {
  max-width: 220px;
  margin: -4px 0 0;
}

.comment {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 14px 4px 15px;
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.comment + .comment { border-top: 1px solid var(--v-divider-subtle); }
.comment:hover { background: color-mix(in srgb, var(--v-bg-hover) 42%, transparent); }

.comment.is-activity-focus,
.comment-reply.is-activity-focus {
  background: var(--v-accent-subtle);
}

.comment.is-activity-focus::before {
  content: '';
  position: absolute;
  inset: 9px auto 9px -8px;
  width: 2px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
}

.comment.resolved,
.comment-reply.resolved { opacity: 0.58; }

.comment-entry {
  display: grid;
  grid-template-columns: var(--comment-avatar-size) minmax(0, 1fr);
  align-items: start;
  gap: var(--comment-gutter);
  min-width: 0;
}

.comment-avatar {
  display: grid;
  place-items: center;
  width: var(--comment-avatar-size);
  height: var(--comment-avatar-size);
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
  color: #fff;
  font: 700 var(--v-text-3xs)/1 var(--v-font);
  letter-spacing: 0.02em;
  user-select: none;
}

.comment-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.comment-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 20px;
}

.comment-header-main {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  flex: 1 1 auto;
  gap: 6px;
}

.comment-header-tools {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
}

.author {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.comment-posted-at,
.comment-number {
  flex: 0 0 auto;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.comment-number,
.comment-secondary-actions {
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--v-transition-fast);
}

.comment-number { color: color-mix(in srgb, var(--v-text-muted) 62%, transparent); }

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

.comment-action-button,
.composer__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: var(--v-button-radius);
  cursor: pointer;
}

.comment-action-button {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  transition: color var(--v-transition-fast), background var(--v-transition-fast);
}

.comment-action-button:hover {
  background: var(--v-bg-hover);
  color: var(--v-text);
}

.comment-action-button.is-danger:hover {
  background: var(--v-danger-bg);
  color: var(--v-danger);
}

.comment-action-button .icon { width: 12px; height: 12px; }

.comment-text {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  line-height: 1.5;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.comment-message { min-width: 0; }

.comment-timecode,
.comment-annotation-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  height: 18px;
  border-radius: 5px;
}

.comment-timecode {
  padding: 0 6px;
  background: color-mix(in srgb, var(--v-warning) 11%, transparent);
  color: color-mix(in srgb, var(--v-warning) 72%, var(--v-text-secondary));
  font-size: var(--v-text-2xs);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.comment:hover .comment-timecode {
  background: color-mix(in srgb, var(--v-warning) 16%, transparent);
  color: color-mix(in srgb, var(--v-warning) 85%, var(--v-text));
}

.comment-annotation-chip {
  width: 18px;
  background: color-mix(in srgb, var(--v-annotation) 13%, transparent);
  color: var(--v-annotation);
}

.comment-annotation-chip .icon { width: 10px; height: 10px; }
.comment-text-placeholder { color: var(--v-text-muted); font-style: italic; }

.comment-text-link {
  color: var(--v-info);
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, var(--v-info) 62%, transparent);
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}

.comment-text-link:hover { color: color-mix(in srgb, var(--v-info) 76%, white); }

.comment-mention-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 21px;
  margin: 0 1px;
  padding: 1px 7px 1px 5px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 26%, var(--v-control-border));
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent-subtle) 72%, var(--v-surface-inline));
  color: color-mix(in srgb, var(--v-accent) 82%, var(--v-text));
  font: 650 var(--v-text-xs)/1.35 var(--v-font);
  vertical-align: baseline;
  cursor: pointer;
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast), color var(--v-transition-fast);
}

.comment-mention-chip:hover {
  border-color: color-mix(in srgb, var(--v-accent) 54%, var(--v-control-border));
  background: var(--v-accent-muted);
  color: var(--v-text);
}

.comment-mention-chip:focus-visible {
  outline: 2px solid var(--v-accent);
  outline-offset: 1px;
}

.comment-mention-chip .icon { width: 11px; height: 11px; }

.comment-replies {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 2px 0 0 calc(var(--comment-avatar-size) / 2);
  padding: 3px 0 1px calc(var(--comment-avatar-size) / 2 + var(--comment-gutter));
  border-left: 1px solid color-mix(in srgb, var(--v-control-border) 54%, transparent);
}

.comment-reply { --comment-avatar-size: 20px; }
.comment-reply .author { font-size: var(--v-text-sm); }
.comment-reply .comment-text { font-size: var(--v-text-sm); }

.comment-reply-button {
  align-self: flex-start;
  min-height: 24px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--v-text-muted);
  font: 600 var(--v-text-xs)/1 var(--v-font);
  cursor: pointer;
  transition: color var(--v-transition-fast);
}

.comment-reply-button:hover { color: var(--v-accent); }

.comment-thread-reply-button {
  margin-left: calc(var(--comment-avatar-size) + var(--comment-gutter));
}

.comment-inline-composer {
  margin: 4px 0 0 calc(var(--comment-avatar-size) + var(--comment-gutter));
  cursor: default;
}

.comment-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 5px;
}

.drawing-panel {
  margin: 0 12px 10px;
  padding: 10px;
  border: 1px solid var(--v-warning-border);
  border-radius: var(--v-radius-md);
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

.color-picker { display: flex; gap: 5px; }

.color-btn {
  width: 22px;
  height: 22px;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
}

.color-btn.active { border-color: white; box-shadow: 0 0 0 1px var(--v-accent); }

.add-comment {
  flex: 0 0 auto;
  padding: 10px 12px calc(12px + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid var(--v-divider);
  background: var(--v-surface-canvas);
}

.name-input {
  width: 100%;
  min-height: 36px;
  margin-bottom: 8px;
  padding: 0 10px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  color: var(--v-text);
  font: 500 var(--v-text-base)/1 var(--v-font);
}

.name-input:focus {
  outline: none;
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.pending-annotation,
.pending-voice-note,
.pending-attachment {
  border: 1px solid color-mix(in srgb, var(--v-control-border) 74%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inset);
}

.pending-annotation {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  padding: 7px 9px;
  color: var(--v-annotation);
  font-size: var(--v-text-xs);
}

.pending-annotation .icon { width: 13px; height: 13px; }

.pending-annotation button,
.pending-attachment-remove {
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
}

.pending-annotation button {
  margin-left: auto;
  padding: 0 4px;
  font-size: var(--v-text-lg);
}

.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.pending-voice-note {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  padding: 2px 4px 2px 2px;
}

.pending-voice-note .pending-attachment-remove {
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-md);
}

.pending-attachment {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
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
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
}

.pending-attachment-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-attachment-remove { padding: 2px 4px; }

.pending-attachment-remove:hover,
.pending-annotation button:hover { color: var(--v-danger); }

.composer {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 8px 7px 11px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.composer__drop-hint {
  position: absolute;
  inset: 3px;
  z-index: 3;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-content: center;
  align-items: center;
  column-gap: 8px;
  padding: 7px 10px;
  pointer-events: none;
  border: 1px solid color-mix(in srgb, var(--v-accent) 46%, var(--v-control-border));
  border-radius: calc(var(--v-radius-md) - 2px);
  background: var(--v-surface-raised-strong);
  box-shadow: var(--v-surface-shadow-raised);
  color: var(--v-accent);
}

.composer__drop-hint .icon {
  grid-row: 1 / span 2;
  width: 17px;
  height: 17px;
}

.composer__drop-hint strong {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  line-height: 1.25;
}

.composer__drop-hint span {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  line-height: 1.3;
}

.composer__drop-hint.is-blocked {
  border-color: var(--v-danger-border);
  background: color-mix(in srgb, var(--v-danger-bg) 72%, var(--v-surface-raised));
  color: var(--v-danger);
}

.composer:hover { background: var(--v-surface-inset-hover); }

.composer:focus-within {
  border-color: var(--v-control-border-hover);
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.composer__textarea {
  width: 100%;
  min-height: 30px;
  max-height: 160px;
  padding: 0;
  overflow: hidden;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--v-text);
  font: 500 var(--v-text-base)/1.45 var(--v-font);
  field-sizing: content;
  resize: none;
}

.composer__textarea::placeholder { color: var(--v-text-muted); }

.composer__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.composer__meta {
  min-width: 0;
  margin-right: auto;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer__meta strong { color: var(--v-text-secondary); font-weight: 600; }

.composer__action {
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.composer__action:hover:not(:disabled) { background: var(--v-bg-hover); color: var(--v-text); }
.composer__action:disabled { opacity: 0.42; cursor: not-allowed; }
.composer__action .icon { width: 13px; height: 13px; }
.composer__action .icon.is-spinning { animation: v-spin 0.8s linear infinite; }

.composer__action--submit {
  background: var(--v-accent);
  color: var(--v-on-accent);
}

.composer__action--submit:hover:not(:disabled) { background: var(--v-accent-hover); color: var(--v-on-accent); }

.composer__action--submit:disabled {
  background: color-mix(in srgb, var(--v-accent) 26%, transparent);
  color: var(--v-text-muted);
  opacity: 1;
}

.composer--inline-reply { width: 100%; }

.comment-inline-cancel {
  height: 28px;
  margin-right: auto;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  font: 600 var(--v-text-xs)/1 var(--v-font);
  cursor: pointer;
}

.comment-inline-cancel:hover { color: var(--v-text); }

@media (max-width: 768px) {
  .comments-section { --comments-safe-bottom: max(8px, calc(env(safe-area-inset-bottom, 0px) + 4px)); }
  .comments-list { padding: 0 var(--v-viewer-mobile-content-gutter) 14px; }
  .empty-comments {
    min-height: 144px;
    padding: var(--v-space-5) var(--v-space-4);
  }
  .comment { padding-block: 14px; }
  .comment-number,
  .comment-secondary-actions { opacity: 0.72; pointer-events: auto; }
  .comment-action-button { width: 32px; height: 32px; }
  .comment-text,
  .comment-reply .comment-text { font-size: var(--v-text-base); }
  .comment-thread-reply-button { min-height: 30px; }
  .add-comment {
    position: sticky;
    bottom: 0;
    z-index: 3;
    margin-top: auto;
    padding: 8px var(--v-viewer-mobile-content-gutter) var(--comments-safe-bottom);
    background: var(--v-surface-canvas);
  }
  .composer {
    gap: 2px;
    padding: 8px 7px 6px 10px;
  }
  .composer__textarea { min-height: 28px; font-size: var(--v-text-xl); }
  .composer__action { width: 44px; height: 44px; }
  .composer__action .icon { width: 15px; height: 15px; }
}

@media (prefers-reduced-motion: reduce) {
  .composer__action .icon.is-spinning { animation-duration: 1.6s; }
}
</style>
