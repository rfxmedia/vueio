<template>
  <VModal
    :modelValue="showShareCreate"
    @update:modelValue="cancelShareCreate"
    class="share-create-modal-shell"
    :size="canManageProjectShares ? 'lg' : 'md'"
  >
    <template #header>
      <VModalHeader @close="cancelShareCreate">
        <div class="share-modal-head">
          <div class="share-modal-eyebrow v-eyebrow">{{ canManageProjectShares ? 'Project sharing' : 'Share link' }}</div>
          <div class="share-modal-title v-truncate">{{ shareModalTitle }}</div>
        </div>
      </VModalHeader>
    </template>

    <div class="share-create-body">
      <VTabs
        v-if="canManageProjectShares"
        class="share-modal-tabs"
        :model-value="shareCreateTab"
        :tabs="shareModalTabs"
        variant="segmented"
        :full-width="true"
        aria-label="Share link menu"
        @update:modelValue="setShareCreateTab"
      />

      <section v-if="shareCreateTab === 'create'" class="share-create-pane">
        <p class="v-inline-note">{{ shareCreateTargetNote }}</p>

        <div class="v-form-grid">
          <VField label="Expiration Date" hint="Default: 30 days from today. All links expire for security.">
            <input type="date" v-model="shareCreateForm.expiresDate" class="v-input" required />
          </VField>

          <VField label="Password Protection">
            <input type="password" v-model="shareCreateForm.password" placeholder="Optional password" class="v-input" />
          </VField>

          <div
            class="share-access-options v-modal-choice-grid"
            :class="{ 'has-file-request': canRequestFiles }"
          >
            <div class="share-access-option is-downloads v-modal-card-soft">
              <VSwitch
                v-model="shareCreateForm.allowDownload"
                label="Allow downloads"
                :hint="shareCreateForm.requestFiles ? 'Unavailable for file requests.' : 'People can download shared files.'"
                :disabled="shareCreateForm.requestFiles"
              />
            </div>

            <div v-if="canRequestFiles" class="share-access-option is-request-files v-modal-card-soft">
              <VSwitch
                :model-value="shareCreateForm.requestFiles"
                label="Request files"
                hint="Upload-only link; existing contents stay private."
                @update:modelValue="setRequestFiles"
              />
            </div>

            <div
              v-if="shareCreateType === 'folder' && !shareCreateForm.requestFiles"
              class="share-access-option v-modal-card-soft"
            >
              <VSwitch
                v-model="shareCreateForm.allowUpload"
                label="Allow file uploads"
                hint="People can add files to this folder."
              />
            </div>
          </div>
        </div>
      </section>

      <section v-else class="share-manage-pane">
        <div v-if="projectSharesLoading" class="share-manage-state">
          <svg class="icon spinning"><use href="#icon-loader" /></svg>
          <span>Loading active shares</span>
        </div>

        <div v-else-if="projectSharesError" class="share-manage-state is-error">
          <svg class="icon"><use href="#icon-info" /></svg>
          <span>{{ projectSharesError }}</span>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="loadProjectShares">Retry</button>
        </div>

        <div v-else-if="!projectShares.length" class="share-manage-empty">
          <div class="share-manage-empty-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-link" /></svg>
          </div>
          <div>
            <strong>No active shares</strong>
            <span>This project does not have any active share links yet.</span>
          </div>
        </div>

        <ol v-else class="share-manage-list">
          <li v-for="share in projectShares" :key="share.id" class="share-manage-item">
            <div class="share-manage-row">
              <span class="share-manage-icon" aria-hidden="true">
                <svg class="icon"><use :href="shareTypeIcon(share)" /></svg>
              </span>
              <div class="share-manage-main">
                <div class="share-manage-title-row">
                  <h4>{{ shareDisplayName(share) }}</h4>
                  <span class="share-status-pill success">Active</span>
                </div>
                <div class="share-manage-meta">
                  <span>{{ shareTypeLabel(share) }}</span>
                  <span>{{ share.created_by || 'Unknown creator' }}</span>
                  <span>{{ formatDateLabel(share.created_at) }}</span>
                  <span>{{ share.access_count || 0 }} views</span>
                </div>
                <div class="share-manage-access">
                  <span v-if="share.request_files">File request</span>
                  <span>{{ share.has_password ? 'Password' : 'No password' }}</span>
                  <span v-if="!share.request_files">{{ share.allow_download ? 'Downloads on' : 'Downloads off' }}</span>
                  <span v-if="share.allow_upload">{{ share.request_files ? 'Uploads only' : 'Uploads on' }}</span>
                  <span>{{ share.expires_at ? `Expires ${formatDateLabel(share.expires_at)}` : 'No expiration' }}</span>
                </div>
              </div>
              <div class="share-manage-actions">
                <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="copyProjectShareLink(share)">
                  <svg class="icon"><use href="#icon-copy" /></svg>
                  <span>Copy</span>
                </button>
                <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="openProjectShareEditor(share)">
                  <svg class="icon"><use href="#icon-edit" /></svg>
                  <span>Edit</span>
                </button>
                <button
                  type="button"
                  class="v-btn v-btn-danger v-btn-sm"
                  :disabled="projectShareBusyId === share.id"
                  @click="revokeProjectShare(share)"
                >
                  Revoke
                </button>
              </div>
            </div>

            <div v-if="editingProjectShare?.id === share.id" class="share-manage-edit">
              <div class="share-manage-edit-head">
                <strong>Edit share</strong>
                <button type="button" class="v-icon-action is-muted is-compact" aria-label="Close edit form" @click="closeProjectShareEditor">
                  <svg class="icon"><use href="#icon-close" /></svg>
                </button>
              </div>
              <div class="share-manage-edit-grid">
                <VField label="Expiration">
                  <input v-model="projectShareEditForm.expiresDate" type="date" class="v-input" />
                </VField>
                <VField label="Password">
                  <input v-model="projectShareEditForm.password" type="password" class="v-input" placeholder="Leave blank to remove" />
                </VField>
                <VSwitch v-if="!share.request_files" v-model="projectShareEditForm.allowDownload" label="Allow downloads" />
                <VSwitch
                  v-if="shareSupportsUpload(share) && !share.request_files"
                  v-model="projectShareEditForm.allowUpload"
                  label="Allow file uploads"
                />
              </div>
              <div class="share-manage-edit-actions">
                <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="closeProjectShareEditor">Cancel</button>
                <button
                  type="button"
                  class="v-btn v-btn-primary v-btn-sm"
                  :disabled="projectShareBusyId === share.id"
                  @click="saveProjectShareEdit"
                >
                  Save
                </button>
              </div>
            </div>
          </li>
        </ol>
      </section>
    </div>

    <template #footer>
      <template v-if="shareCreateTab === 'shares'">
        <button type="button" class="v-btn v-btn-secondary" @click="cancelShareCreate">Close</button>
        <button type="button" class="v-btn v-btn-secondary" :disabled="projectSharesLoading" @click="loadProjectShares">
          <svg class="icon" :class="{ spinning: projectSharesLoading }"><use href="#icon-refresh" /></svg>
          <span>Refresh</span>
        </button>
      </template>
      <template v-else>
        <button type="button" class="v-btn v-btn-secondary" @click="cancelShareCreate">Cancel</button>
        <button type="button" class="v-btn v-btn-primary" @click="confirmShareCreate">Create Link</button>
      </template>
    </template>
  </VModal>

  <VModal
    :modelValue="!!shareModal"
    @update:modelValue="closeShareModal"
    :title="shareResultTitle"
    size="md"
  >
    <template #header>
      <VModalHeader :title="shareResultTitle" @close="closeShareModal" />
    </template>

    <div class="v-modal-stack">
      <p class="v-inline-note">{{ shareResultMessage }}</p>
      <div class="share-result-row v-modal-card-soft">
        <input type="text" class="v-input" :value="shareResultUrl" readonly />
        <button class="v-btn v-btn-primary" @click="copyShareLink(shareResultUrl)">Copy</button>
      </div>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="closeShareModal">Done</button>
    </template>
  </VModal>

  <VModal
    v-if="showLogin && !shareMode && !sharePasswordRequired"
    :modelValue="showLogin && !shareMode && !sharePasswordRequired"
    size="sm"
    :closeable="false"
    aria-label="Sign in"
    >
    <div class="auth-card v-modal-auth">
      <div class="auth-brand">vue<span>.</span>io</div>
      <p class="auth-subtitle">Review Platform</p>

      <div class="v-form-grid">
        <label class="v-field">
          <span class="v-field-label">Username</span>
          <input
            :value="loginUsername"
            autocomplete="username"
            class="v-input login-input"
            @input="setLoginUsername($event.target.value)"
            @keydown.enter="login"
          />
        </label>
        <label class="v-field">
          <span class="v-field-label">Password</span>
          <input
            :value="loginPassword"
            type="password"
            autocomplete="current-password"
            class="v-input login-input"
            @input="setLoginPassword($event.target.value)"
            @keydown.enter="login"
          />
        </label>
        <p v-if="loginError" class="v-text-danger auth-error" role="alert">{{ loginError }}</p>
        <button class="v-btn v-btn-primary v-btn-lg auth-submit" @click="login" :disabled="!loginUsername || !loginPassword">Sign In</button>
      </div>
    </div>
  </VModal>

  <VModal
    v-if="sharePasswordRequired"
    :modelValue="sharePasswordRequired"
    size="sm"
    :closeable="false"
    :aria-label="shareAccessTitle"
    >
    <div class="auth-card v-modal-auth">
      <div class="share-access-icon v-modal-auth-icon">
        <svg class="icon"><use :href="shareAccessIcon" /></svg>
      </div>
      <h3 class="auth-title">{{ shareAccessTitle }}</h3>
      <p class="auth-subtitle auth-subtitle-spacious">{{ shareAccessError || 'This shared content is password protected' }}</p>

      <template v-if="canEnterSharePassword">
        <div class="v-form-grid">
          <label class="v-field">
            <span class="v-field-label">Share password</span>
            <input
              :value="sharePasswordInput"
              type="password"
              autocomplete="current-password"
              class="v-input"
              @input="setSharePasswordInput($event.target.value)"
              @keydown.enter="submitSharePassword"
            />
          </label>
          <button class="v-btn v-btn-primary v-btn-lg auth-submit" @click="submitSharePassword" :disabled="!sharePasswordInput">Access Content</button>
        </div>
      </template>
      <a v-else href="/" class="v-btn v-btn-secondary auth-back-link">← Back to Home</a>
    </div>
  </VModal>

  <VModal
    :modelValue="showChangePassword"
    @update:modelValue="closeChangePassword"
    title="Change Password"
    size="md"
  >
    <template #header>
      <VModalHeader title="Change Password" @close="closeChangePassword" />
    </template>

    <div class="v-form-grid">
      <input v-model="passwordForm.current" type="password" placeholder="Current Password" class="v-input" />
      <input v-model="passwordForm.new" type="password" placeholder="New Password" class="v-input" />
      <input v-model="passwordForm.confirm" type="password" placeholder="Confirm New Password" class="v-input" />
      <p v-if="passwordError" class="v-text-danger auth-error">{{ passwordError }}</p>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="closeChangePassword">Cancel</button>
      <button class="v-btn v-btn-primary" @click="changeMyPassword" :disabled="!passwordForm.new || passwordForm.new !== passwordForm.confirm">Save</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed } from 'vue'
import { VField, VModal, VModalHeader, VSwitch, VTabs } from '../primitives'
import { formatShareDateLabel as formatDateLabel } from '../../utils/formatters'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useShareManagementStore } from '../../ownership/shareManagement'

const {
  showShareCreate,
  shareCreateTarget,
  shareCreateType,
  shareCreateForm,
  shareCreateTab,
  canManageProjectShares,
  projectShares,
  projectSharesLoading,
  projectSharesError,
  projectShareBusyId,
  editingProjectShare,
  projectShareEditForm,
  lastCreatedWasFileRequest,
  setShareCreateTab,
  loadProjectShares,
  copyProjectShareLink,
  openProjectShareEditor,
  closeProjectShareEditor,
  saveProjectShareEdit,
  revokeProjectShare,
  cancelShareCreate,
  confirmShareCreate,
  shareModal,
  projectShareUrl,
  shareUrl,
  closeShareModal,
  copyShareLink,
  sharePasswordInput,
  setSharePasswordInput,
  submitSharePassword,
} = useShareManagementStore()
const {
  showLogin,
  loginUsername,
  loginPassword,
  loginError,
  showChangePassword,
  passwordForm,
  passwordError,
  setLoginUsername,
  setLoginPassword,
  login,
  closeChangePassword,
  changeMyPassword,
} = useSessionAuthStore()
const { shareMode, sharePasswordRequired, shareAccessError } = useShareAccessContext()

const shareModalTabs = computed(() => [
  { value: 'create', label: 'Create link' },
  { value: 'shares', label: 'Active shares', count: projectShares.value.length || undefined },
])

const shareResultTitle = computed(() => lastCreatedWasFileRequest.value
  ? 'File Request Link'
  : (shareModal.value === 'project' ? 'Project Share Link' : 'Share Link'))
const shareResultMessage = computed(() => lastCreatedWasFileRequest.value
  ? 'Anyone with this link can upload files without viewing the folder contents:'
  : `Anyone with this link can view${shareModal.value === 'project' ? ' this project' : ''}:`)
const shareResultUrl = computed(() => shareModal.value === 'project' ? projectShareUrl.value : shareUrl.value)
const shareCreateTargetLabel = computed(() => shareCreateTarget.value?.name || shareCreateTarget.value?.title || shareCreateTarget.value?.path || 'Create Share Link')
const shareModalTitle = computed(() => canManageProjectShares.value ? shareCreateTargetLabel.value : 'Create Share Link')
const shareCreateTargetNote = computed(() => canManageProjectShares.value ? `Creating link for ${shareCreateTargetLabel.value}` : shareCreateTargetLabel.value)
const canRequestFiles = computed(() => ['folder', 'project-folder'].includes(shareCreateType.value))
const shareAccessLower = computed(() => (shareAccessError.value || '').toLowerCase())
const shareLinkExpired = computed(() => shareAccessLower.value.includes('expired'))
const shareLinkRevoked = computed(() => shareAccessLower.value.includes('revoked'))
const shareFileUnavailable = computed(() => ['unavailable', 'deleted', 'replaced'].some(value => shareAccessLower.value.includes(value)))
const shareAccessIcon = computed(() => {
  if (shareFileUnavailable.value) return '#icon-file'
  return (shareLinkExpired.value || shareLinkRevoked.value) ? '#icon-clock' : '#icon-lock'
})
const shareAccessTitle = computed(() => {
  if (shareLinkExpired.value) return 'Link Expired'
  if (shareLinkRevoked.value) return 'Link Revoked'
  if (shareFileUnavailable.value) return 'File Unavailable'
  return 'Password Required'
})
const canEnterSharePassword = computed(() => !shareLinkExpired.value && !shareLinkRevoked.value && !shareFileUnavailable.value)

function setRequestFiles(enabled) {
  shareCreateForm.value.requestFiles = enabled
  if (!enabled) return
  shareCreateForm.value.allowDownload = false
  shareCreateForm.value.allowUpload = false
}

const SHARE_TYPE_LABELS = {
  project: 'Project',
  tracker: 'Tracker',
  page: 'Dashboard',
  'project-file': 'File',
  'project-folder': 'Folder',
  file: 'File',
  folder: 'Folder',
}

function shareDisplayName(share) {
  return share.target_name || share.path || share.tracker_name || share.project_title || share.project_id || share.id
}

function shareTypeLabel(share) {
  if (share.request_files) return 'File request'
  return SHARE_TYPE_LABELS[share.share_type] || 'Share'
}

function shareTypeIcon(share) {
  if (share.request_files) return '#icon-inbox'
  if (share.share_type === 'project') return '#icon-project'
  if (share.share_type === 'tracker') return '#icon-layout'
  if (share.share_type === 'page') return '#icon-link'
  if (share.share_type === 'project-folder' || share.share_type === 'folder') return '#icon-folder'
  return '#icon-file'
}

function shareSupportsUpload(share) {
  return ['folder', 'project-folder', 'page'].includes(share.share_type)
}

</script>

<style scoped>
:global(.share-create-modal-shell.v-modal-lg) {
  max-width: 760px;
}

.share-modal-head {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}


.share-modal-title {
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  font-weight: 700;
  line-height: 1.25;
}

.share-create-body,
.share-create-pane {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
}

.share-access-options {
  gap: var(--v-space-2);
}

.share-access-option {
  justify-content: center;
  min-width: 0;
  padding: 12px 14px;
}

.share-access-option :deep(.v-switch) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
}

.share-access-option :deep(.v-switch-copy) {
  grid-column: 1;
  grid-row: 1;
  min-width: 0;
}

.share-access-option :deep(.v-switch-track) {
  grid-column: 2;
  grid-row: 1;
  margin-top: 0;
}

@media (min-width: 769px) {
  .share-access-options.has-file-request .is-downloads {
    grid-column: 1;
  }

  .share-access-options.has-file-request .is-request-files {
    grid-column: 2;
  }
}

.share-modal-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
}

.share-modal-tabs :deep(.v-tab-btn) {
  min-width: 0;
}

.share-manage-pane {
  min-height: 240px;
  max-height: min(58vh, 520px);
  overflow: auto;
  padding-right: 2px;
}

.share-manage-state,
.share-manage-empty {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-3);
  color: var(--v-text-muted);
  text-align: center;
}

.share-manage-state {
  flex-direction: column;
  font-size: var(--v-text-base);
}

.share-manage-state .icon {
  width: 24px;
  height: 24px;
}

.share-manage-state .icon.spinning,
.icon.spinning {
  animation: v-spin 900ms linear infinite;
}

.share-manage-state.is-error {
  color: var(--v-danger-text);
}

.share-manage-empty {
  padding: var(--v-space-6);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-raised);
}

.share-manage-empty-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  border: 1px solid var(--v-control-border);
  background: var(--v-surface-inset);
  color: var(--v-accent-hover);
}

.share-manage-empty-icon .icon {
  width: 18px;
  height: 18px;
}

.share-manage-empty div:last-child {
  display: flex;
  flex-direction: column;
  gap: 3px;
  text-align: left;
}

.share-manage-empty strong {
  color: var(--v-text);
  font-size: var(--v-text-md);
}

.share-manage-empty span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.share-manage-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.share-manage-item {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-border) 70%, transparent);
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-surface-inline) 44%, var(--v-bg-raised));
}

.share-manage-row {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  padding: var(--v-space-3);
}

.share-manage-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-border) 62%, transparent);
  background: color-mix(in srgb, var(--v-bg-field) 72%, transparent);
  color: var(--v-accent-hover);
}

.share-manage-icon .icon {
  width: 16px;
  height: 16px;
}

.share-manage-main {
  min-width: 0;
}

.share-manage-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2);
  min-width: 0;
}

.share-manage-title-row h4 {
  min-width: 0;
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  line-height: 1.3;
}

.share-status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-xs);
  font-weight: 800;
  white-space: nowrap;
}

.share-status-pill.success {
  background: color-mix(in srgb, var(--v-accent-muted) 50%, transparent);
  color: var(--v-accent-hover);
}

.share-manage-meta,
.share-manage-access {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 8px;
  margin-top: 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.share-manage-meta span:not(:last-child)::after,
.share-manage-access span:not(:last-child)::after {
  content: '·';
  margin-left: var(--v-space-2);
  color: color-mix(in srgb, var(--v-text-muted) 58%, transparent);
}

.share-manage-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 7px;
}

.share-manage-actions .v-btn,
.share-manage-edit-actions .v-btn,
.v-modal-footer .v-btn {
  gap: 6px;
}

.share-manage-actions .icon,
.v-modal-footer .icon {
  width: 13px;
  height: 13px;
}

.share-manage-edit {
  margin: 0 10px 10px;
  padding: var(--v-space-3);
  border-top: 1px solid var(--v-divider-subtle);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-field) 62%, transparent);
}

.share-manage-edit-head,
.share-manage-edit-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.share-manage-edit-head {
  margin-bottom: 10px;
}

.share-manage-edit-head strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
}

.share-manage-edit-head .icon {
  width: 14px;
  height: 14px;
}

.share-manage-edit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-3);
}

.share-manage-edit-actions {
  justify-content: flex-end;
  margin-top: var(--v-space-3);
}

.share-result-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.share-result-row .v-input {
  flex: 1;
}

.auth-card {
  text-align: center;
}

.auth-brand {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0;
  color: var(--v-text);
  margin-bottom: var(--v-space-1);
}

.auth-brand span {
  color: var(--v-accent);
}

.auth-title {
  margin: 0 0 var(--v-space-2) 0;
  font-size: var(--v-text-2xl);
}

.auth-subtitle {
  margin: 0 0 var(--v-space-6) 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.auth-subtitle-spacious {
  margin-bottom: var(--v-space-4);
}

.auth-submit {
  width: 100%;
}

.auth-back-link {
  margin-top: var(--v-space-4);
}

.auth-error {
  margin: 0;
  font-size: var(--v-text-sm);
}

.login-input {
  background: var(--v-bg-field);
  border-color: var(--v-control-border);
}

.login-input::placeholder {
  color: var(--v-text-muted);
}

.login-input:focus {
  background: var(--v-bg-field-hover);
}

.share-access-icon {
  margin-bottom: var(--v-space-1);
}

.share-access-icon .icon {
  width: 32px;
  height: 32px;
}

@media (max-width: 768px) {
  .share-manage-pane {
    max-height: 56vh;
  }

  .share-manage-row {
    grid-template-columns: 38px minmax(0, 1fr);
    align-items: start;
  }

  .share-manage-actions {
    grid-column: 1 / -1;
    justify-content: stretch;
  }

  .share-manage-actions .v-btn {
    flex: 1 1 0;
  }

  .share-manage-edit-grid {
    grid-template-columns: 1fr;
  }

  .share-manage-empty {
    align-items: flex-start;
    justify-content: flex-start;
    min-height: 0;
    text-align: left;
  }

  .share-result-row {
    flex-direction: column;
    align-items: stretch;
  }

  .auth-subtitle {
    margin-bottom: var(--v-space-4);
  }
}
</style>
