<template>
  <VModal
    :modelValue="show"
    size="md"
    class="project-settings-modal-shell"
    :aria-labelledby="settingsTitleId"
    :presentation="isMobile ? 'sheet' : 'dialog'"
    :mobile-full-height="isMobile"
    @update:modelValue="close"
  >
    <template #header>
      <VModalHeader @close="close">
        <div class="ps-head">
          <div class="ps-head-eyebrow v-eyebrow">{{ scope === 'tracker' ? 'Tracker Settings' : 'Project Settings' }}</div>
          <h2 :id="settingsTitleId" class="ps-head-title v-truncate">{{ scope === 'tracker' ? (tracker?.name || 'Tracker') : (project?.title || 'Project') }}</h2>
          <p class="ps-head-subtitle">
            {{ scope === 'tracker' ? 'Choose which review tools are available for this tracker.' : 'Manage project details, storage, and access.' }}
          </p>
        </div>
      </VModalHeader>
    </template>

    <div v-if="project" class="ps-body">
      <!-- ─── Hero card: thumbnail + status snapshot + change ───────── -->
      <section v-if="scope === 'project'" class="ps-hero">
        <div class="ps-hero-thumb" :class="{ 'is-empty': !thumbnailUrl }">
          <img v-if="thumbnailUrl" :src="thumbnailUrl" alt="" />
          <svg v-else class="icon" aria-hidden="true"><use href="#icon-project" /></svg>
        </div>
        <div class="ps-hero-meta">
          <div class="ps-hero-status">
            <span class="ps-status-dot" :style="{ background: getStatusColor(draftStatus) }" aria-hidden="true"></span>
            <span class="ps-hero-status-label">{{ statusLabel(draftStatus) }}</span>
            <template v-if="dueDateFormatted">
              <span class="ps-hero-due">Due {{ dueDateFormatted }}</span>
            </template>
          </div>
          <button
            v-if="canEditProject"
            type="button"
            class="v-btn v-btn-secondary v-btn-sm ps-hero-btn"
            :disabled="saving"
            @click="openThumbnailPicker"
          >
            <svg class="icon"><use href="#icon-image" /></svg>
            <span>{{ project.thumbnail_path ? 'Change thumbnail' : 'Set thumbnail' }}</span>
          </button>
        </div>
      </section>

      <!-- ─── Details ─────────────────────────────────────────────── -->
      <section v-if="scope === 'project'" class="ps-section">
        <div class="v-section-label">
          <h3>Details</h3>
        </div>
        <div class="ps-form-grid">
          <label class="ps-field is-full">
            <span class="v-field-label">Project name</span>
            <input
              :value="draftTitle"
              class="v-input ps-input"
              :disabled="saving || !canEditProject"
              placeholder="Untitled project"
              @input="$emit('update:draftTitle', $event.target.value)"
            />
          </label>

          <label class="ps-field is-half">
            <span class="v-field-label">Status</span>
            <div
              class="v-control-pill ps-status-pill ps-control-pill"
              :class="{ 'is-disabled': saving || !canEditProject }"
            >
              <span class="ps-status-dot" :style="{ background: getStatusColor(draftStatus) }" aria-hidden="true"></span>
              <span class="ps-control-pill-label v-truncate">{{ statusLabel(draftStatus) }}</span>
              <svg class="ps-control-pill-chevron icon" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
              <select
                :value="draftStatus"
                class="ps-control-pill-native"
                :disabled="saving || !canEditProject"
                aria-label="Project status"
                @change="$emit('update:draftStatus', $event.target.value)"
              >
                <option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
          </label>

          <label class="ps-field is-half">
            <span class="v-field-label">Due date</span>
            <input
              :value="draftDueDate"
              type="date"
              class="v-input ps-input ps-input-date"
              :disabled="saving || !canEditProject"
              @input="$emit('update:draftDueDate', $event.target.value)"
            />
          </label>

          <label class="ps-field is-full">
            <span class="v-field-label">Description</span>
            <textarea
              :value="draftDescription"
              class="v-input ps-textarea"
              rows="3"
              :disabled="saving || !canEditProject"
              placeholder="A short note about what this project is for…"
              @input="$emit('update:draftDescription', $event.target.value)"
            ></textarea>
          </label>
        </div>
      </section>

      <!-- ─── Tracker Tools ──────────────────────────────────────── -->
      <section v-if="scope === 'tracker'" class="ps-section">
        <div class="v-section-label">
          <h3>Tracker Tools</h3>
        </div>

        <div class="ps-tool-list">
          <div
            v-for="tool in toolRows"
            :key="tool.key"
            class="ps-tool-card"
            :class="{ 'is-disabled': !tool.enabled }"
          >
            <div class="ps-tool-row">
              <div class="ps-tool-icon" aria-hidden="true">
                <svg class="icon"><use :href="tool.icon" /></svg>
              </div>
              <div class="ps-tool-copy">
                <div class="ps-tool-topline">
                  <strong class="ps-tool-name">{{ tool.name }}</strong>
                  <span class="v-tag" :class="{ 'v-tag--accent': tool.enabled }">{{ tool.enabled ? 'On' : 'Off' }}</span>
                </div>
                <p class="ps-tool-hint">{{ tool.hint }}</p>
              </div>
              <label
                class="v-switch ps-tool-switch"
                :class="{ 'is-checked': tool.enabled, 'is-disabled': saving || !canEditProject }"
              >
                <input
                  type="checkbox"
                  class="v-switch-input"
                  :checked="tool.enabled"
                  :disabled="saving || !canEditProject"
                  :aria-label="`Enable ${tool.name}`"
                  @change="setToolEnabled(tool.key, $event.target.checked)"
                />
                <span class="v-switch-track" aria-hidden="true"><span class="v-switch-thumb"></span></span>
              </label>
            </div>

            <div
              v-if="tool.key === 'version_review' && pendingPublicationCount"
              class="ps-tool-notice"
            >
              <svg class="icon" aria-hidden="true"><use href="#icon-clock" /></svg>
              <div>
                <strong>{{ pendingPublicationCount }} version{{ pendingPublicationCount === 1 ? '' : 's' }} awaiting publication</strong>
                <span>Changing this setting will not publish existing versions. Owners can resolve them from the version menu.</span>
              </div>
            </div>

            <div v-if="tool.access" class="ps-tool-access">
              <div class="ps-tool-access-copy">
                <span class="v-field-label">Access</span>
                <span>{{ tool.accessLabel }}</span>
              </div>
              <div class="v-view-toggle ps-tool-access-toggle" role="group" :aria-label="`${tool.name} access`">
                <button
                  v-for="option in accessOptions"
                  :key="`${tool.key}-${option.value}`"
                  type="button"
                  class="v-view-toggle-btn"
                  :class="{ active: tool.access === option.value }"
                  :disabled="saving || !canEditProject || !tool.enabled"
                  @click="setToolAccess(tool.key, option.value)"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>

            <div
              v-if="tool.key === 'delivery' && tool.enabled"
              class="ps-tool-delivery"
              :class="{ 'is-disabled': saving || !canEditProject }"
            >
              <label class="ps-field ps-tool-message">
                <span class="v-field-label">Greeting override</span>
                <textarea
                  :value="trackerSettings.delivery.message"
                  class="v-input ps-textarea ps-tool-message-input"
                  rows="2"
                  :disabled="saving || !canEditProject"
                  :placeholder="inheritedDeliveryMessage"
                  @input="setDeliveryMessage($event.target.value)"
                ></textarea>
                <span class="ps-field-hint">Leave blank to inherit the team name.</span>
              </label>

              <label class="ps-field ps-tool-message">
                <span class="v-field-label">Delivery notes</span>
                <textarea
                  :value="trackerSettings.delivery.notes"
                  class="v-input ps-textarea ps-tool-message-input"
                  rows="3"
                  :disabled="saving || !canEditProject"
                  placeholder="Optional handoff notes for this delivery…"
                  @input="setDeliveryNotes($event.target.value)"
                ></textarea>
              </label>

              <div class="ps-delivery-logo-control">
                <div class="ps-delivery-logo-mark" :class="{ 'is-empty': !deliveryLogoUrl }" aria-hidden="true">
                  <img v-if="deliveryLogoUrl" :src="deliveryLogoUrl" alt="" />
                  <svg v-else class="icon"><use href="#icon-image" /></svg>
                </div>
                <div class="ps-delivery-logo-copy">
                  <span class="v-field-label">Logo</span>
                  <span>{{ deliveryLogoStatus }}</span>
                </div>
                <div class="ps-delivery-logo-actions">
                  <label
                    class="v-btn v-btn-secondary v-btn-sm ps-delivery-logo-upload"
                    :class="{ 'is-disabled': saving || !canEditProject || deliveryLogoUploading }"
                  >
                    <input
                      type="file"
                      accept="image/*"
                      hidden
                      :disabled="saving || !canEditProject || deliveryLogoUploading"
                      @change="handleDeliveryLogoChange"
                    />
                    <svg class="icon"><use href="#icon-upload" /></svg>
                    <span>{{ hasCustomDeliveryLogo ? 'Replace' : 'Upload' }}</span>
                  </label>
                  <button
                    type="button"
                    class="v-btn v-btn-secondary v-btn-sm ps-delivery-logo-nas"
                    :disabled="saving || !canEditProject || deliveryLogoUploading"
                    @click="chooseDeliveryLogoFromNas"
                  >
                    <svg class="icon"><use href="#icon-folder" /></svg>
                    <span>NAS</span>
                  </button>
                  <button
                    v-if="hasCustomDeliveryLogo"
                    type="button"
                    class="v-btn v-btn-ghost v-btn-sm ps-delivery-logo-remove"
                    :disabled="saving || !canEditProject || deliveryLogoUploading"
                    @click="removeDeliveryLogo"
                  >
                    Remove
                  </button>
                </div>
              </div>

              <div class="ps-delivery-links">
                <div class="ps-delivery-links-head">
                  <div>
                    <span class="v-field-label">Accessory links</span>
                    <p v-if="appIdentity.website_url">Website inherited from team settings.</p>
                    <p v-else>Add optional client-facing links for this delivery.</p>
                  </div>
                  <button
                    type="button"
                    class="v-btn v-btn-secondary v-btn-sm"
                    :disabled="saving || !canEditProject || trackerSettings.delivery.links.length >= 4"
                    @click="addDeliveryLink"
                  >
                    <svg class="icon"><use href="#icon-plus" /></svg>
                    <span>Add link</span>
                  </button>
                </div>
                <div v-if="appIdentity.website_url" class="ps-delivery-link-row is-inherited">
                  <div class="ps-delivery-link-inherited">
                    <strong>Website</strong>
                    <span>{{ appIdentity.website_url }}</span>
                  </div>
                  <span class="v-tag v-tag--accent">Team</span>
                </div>
                <div
                  v-for="(link, index) in trackerSettings.delivery.links"
                  :key="`delivery-link-${index}`"
                  class="ps-delivery-link-row"
                >
                  <input
                    :value="link.label"
                    class="v-input ps-delivery-link-label"
                    :disabled="saving || !canEditProject"
                    placeholder="Button label"
                    @input="setDeliveryLink(index, { label: $event.target.value })"
                  />
                  <input
                    :value="link.url"
                    class="v-input ps-delivery-link-url"
                    :disabled="saving || !canEditProject"
                    placeholder="https://example.com"
                    @input="setDeliveryLink(index, { url: $event.target.value })"
                  />
                  <button
                    type="button"
                    class="v-btn v-btn-ghost v-btn-icon v-btn-sm"
                    :disabled="saving || !canEditProject"
                    :aria-label="`Remove ${link.label || 'delivery link'}`"
                    @click="removeDeliveryLink(index)"
                  >
                    <svg class="icon"><use href="#icon-trash" /></svg>
                  </button>
                </div>
              </div>

              <button
                type="button"
                class="ps-delivery-preview-link"
                :disabled="!tracker || saving"
                @click="openDeliveryPreview"
              >
                <span class="ps-delivery-preview-icon" aria-hidden="true">
                  <svg class="icon"><use href="#icon-external-link" /></svg>
                </span>
                <span class="ps-delivery-preview-copy">
                  <strong>Preview delivery page</strong>
                  <span>Opens a temporary preview of this tracker in a new tab.</span>
                </span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section v-if="scope === 'project'" class="ps-section">
        <div class="v-section-label">
          <h3>Project storage</h3>
          <span v-if="project.storage_read_only" class="v-tag">Read only</span>
        </div>
        <div class="ps-storage-card">
          <div v-if="project.has_offline_media" class="ps-storage-row ps-storage-alert">
            <div class="ps-storage-icon" aria-hidden="true">
              <svg class="icon"><use href="#icon-alert" /></svg>
            </div>
            <div class="ps-storage-copy">
              <strong>Some media is offline</strong>
              <span>{{ project.unavailable_asset_count }} file{{ project.unavailable_asset_count === 1 ? '' : 's' }} missing. Search the working folder to reconnect files that were moved.</span>
            </div>
            <div v-if="canEditProject" class="ps-storage-actions">
              <button type="button" class="v-btn v-btn-primary v-btn-sm" @click="openRelinkMedia">
                <svg class="icon"><use href="#icon-search" /></svg>
                Find media…
              </button>
            </div>
          </div>

          <div class="ps-storage-row">
            <div class="ps-storage-icon" aria-hidden="true">
              <svg class="icon"><use :href="project.storage_read_only ? '#icon-lock' : '#icon-folder'" /></svg>
            </div>
            <div class="ps-storage-copy">
              <strong>{{ project.storage_read_only ? 'Read-only storage' : project.uses_internal_storage ? 'Internal storage' : 'Working project folder' }}</strong>
              <span>{{ project.storage_read_only ? 'Files play from a read-only location. Relocate the project to make changes.' : project.uses_internal_storage ? 'Move Vue-owned files into your real working folder when you are ready.' : 'Vue follows this folder wherever you relocate it.' }}</span>
              <code>{{ project.storage_root || 'data' }} / {{ project.storage_path || project.id }}</code>
            </div>
            <div v-if="canEditProject" class="ps-storage-actions">
              <button v-if="project.uses_internal_storage" type="button" class="v-btn v-btn-secondary v-btn-sm" @click="openMigrateProject">
                Set project folder
              </button>
              <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="openRelocateProject">
                Relocate…
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ─── Team ────────────────────────────────────────────────── -->
      <section v-if="scope === 'project'" class="ps-section">
        <div class="v-section-label">
          <h3>Team</h3>
          <span v-if="teamMembers.length" class="v-section-count">{{ teamMembers.length }}</span>
        </div>

        <div v-if="teamMembers.length" class="ps-team-list">
          <div v-for="member in teamMembers" :key="member.id" class="ps-team-row">
            <div class="ps-avatar" :style="avatarStyleFor(member)" aria-hidden="true">
              {{ initialsFor(member) }}
            </div>
            <div class="ps-team-copy">
              <div class="ps-team-name v-truncate">
                <span>{{ member.display_name || member.username }}</span>
                <span v-if="isCurrentUser(member)" class="v-tag v-tag--accent">You</span>
              </div>
              <span class="ps-team-handle v-truncate">{{ member.username }}</span>
            </div>
            <div class="ps-team-actions">
              <div
                class="v-control-pill ps-role-pill ps-control-pill"
                :class="{ 'is-disabled': !canManageProjectTeam || isLockedTeamRole(member) || teamSaving || teamLoading, 'is-locked': isLockedTeamRole(member) }"
              >
                <span class="ps-control-pill-label v-truncate">{{ formatTeamRole(teamMemberRoleValue(member)) }}</span>
                <svg
                  v-if="!isLockedTeamRole(member)"
                  class="ps-control-pill-chevron icon"
                  aria-hidden="true"
                ><use href="#icon-chevron-down" /></svg>
                <select
                  v-if="!isLockedTeamRole(member)"
                  :value="teamMemberRoleValue(member)"
                  class="ps-control-pill-native"
                  :disabled="!canManageProjectTeam || teamSaving || teamLoading"
                  :aria-label="`Role for ${member.display_name || member.username}`"
                  @change="updateTeamMember(member, $event.target.value)"
                >
                  <option v-if="!teamMemberHasEditableRole(member)" :value="teamMemberRoleValue(member)" disabled>
                    {{ formatTeamRole(teamMemberRoleValue(member)) }}
                  </option>
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                  <option value="owner" :disabled="member.project_role !== 'owner'">Owner</option>
                </select>
              </div>
              <button
                v-if="canManageProjectTeam && !isLockedTeamRole(member)"
                type="button"
                class="v-btn v-btn-ghost v-btn-icon v-btn-sm ps-team-remove"
                :disabled="teamSaving || teamLoading"
                :aria-label="`Remove ${member.display_name || member.username}`"
                @click="removeTeamMember(member)"
              >
                <svg class="icon"><use href="#icon-trash" /></svg>
              </button>
              <span v-else class="ps-team-remove-slot" aria-hidden="true"></span>
            </div>
          </div>
        </div>

        <div v-else class="ps-empty">
          <div class="ps-empty-icon-wrap" aria-hidden="true">
            <svg class="icon"><use href="#icon-user" /></svg>
          </div>
          <div class="ps-empty-copy">
            <strong class="ps-empty-title">No collaborators yet</strong>
            <span class="ps-empty-hint">Invite teammates so they can view or edit this project.</span>
          </div>
        </div>

        <div v-if="canManageProjectTeam" class="ps-team-compose">
          <div class="ps-team-compose-user">
            <svg class="icon ps-team-compose-icon" aria-hidden="true"><use href="#icon-user" /></svg>
            <select
              :value="teamAddUserId"
              class="ps-team-compose-select"
              :disabled="teamSaving || teamLoading || !availableTeamCandidates.length"
              aria-label="Choose a teammate to add"
              @change="$emit('update:teamAddUserId', $event.target.value)"
            >
              <option value="">{{ availableTeamCandidates.length ? 'Invite a teammate…' : 'Everyone is already added' }}</option>
              <option v-for="candidate in availableTeamCandidates" :key="candidate.id" :value="candidate.id">
                {{ candidate.display_name }} · {{ candidate.username }}
              </option>
            </select>
            <svg class="icon ps-team-compose-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
          </div>
          <div class="ps-team-compose-trailing">
            <div class="v-control-pill v-control-pill-compact ps-role-pill ps-control-pill ps-control-pill-compact" :class="{ 'is-disabled': teamSaving || teamLoading }">
              <span class="ps-control-pill-label">{{ formatTeamRole(teamAddRole) }}</span>
              <svg class="ps-control-pill-chevron icon" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
              <select
                :value="teamAddRole"
                class="ps-control-pill-native"
                :disabled="teamSaving || teamLoading"
                aria-label="Role for new teammate"
                @change="$emit('update:teamAddRole', $event.target.value)"
              >
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
            </div>
            <button
              type="button"
              class="v-btn v-btn-primary v-btn-sm ps-team-add-btn"
              :disabled="!teamAddUserId || teamSaving || teamLoading"
              @click="addTeamMember"
            >
              <svg class="icon"><use href="#icon-plus" /></svg>
              <span>Invite</span>
            </button>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <button type="button" class="v-btn v-btn-secondary" @click="close">Close</button>
      <button
        v-if="canEditProject"
        type="button"
        class="v-btn v-btn-primary"
        :disabled="saving || (scope === 'project' && !draftTitle?.trim())"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save Changes' }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed } from 'vue'
import { VModal, VModalHeader } from '../primitives'
import { formatLocaleDate } from '../../utils/formatters'
import { TRACKER_TOOL_ACCESS_OPTIONS, normalizeTrackerSettings } from '../../utils/trackerSettings'

const props = defineProps({
  show: { type: Boolean, default: false },
  scope: { type: String, default: 'project' },
  isMobile: { type: Boolean, default: false },
  project: { type: Object, default: null },
  tracker: { type: Object, default: null },
  canEditProject: { type: Boolean, default: false },
  canManageProjectTeam: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  teamSaving: { type: Boolean, default: false },
  teamLoading: { type: Boolean, default: false },
  draftTitle: { type: String, default: '' },
  draftDescription: { type: String, default: '' },
  draftDueDate: { type: String, default: '' },
  draftStatus: { type: String, default: 'not_started' },
  draftSettings: { type: Object, default: () => normalizeTrackerSettings() },
  statusOptions: { type: Array, default: () => [] },
  thumbnailUrl: { type: String, default: '' },
  deliveryLogoUrl: { type: String, default: '' },
  appIdentity: { type: Object, default: () => ({}) },
  deliveryLogoUploading: { type: Boolean, default: false },
  teamMembers: { type: Array, default: () => [] },
  teamOptions: { type: Array, default: () => [] },
  teamAddUserId: { type: String, default: '' },
  teamAddRole: { type: String, default: 'viewer' },
  currentUserId: { type: String, default: '' },
  close: { type: Function, required: true },
  save: { type: Function, required: true },
  openThumbnailPicker: { type: Function, default: () => {} },
  uploadDeliveryLogo: { type: Function, default: () => {} },
  chooseDeliveryLogoFromNas: { type: Function, default: () => {} },
  removeDeliveryLogo: { type: Function, default: () => {} },
  openDeliveryPreview: { type: Function, default: () => {} },
  addTeamMember: { type: Function, default: () => {} },
  updateTeamMember: { type: Function, default: () => {} },
  removeTeamMember: { type: Function, default: () => {} },
  openRelocateProject: { type: Function, default: () => {} },
  openRelinkMedia: { type: Function, default: () => {} },
  openMigrateProject: { type: Function, default: () => {} },
})

const emit = defineEmits([
  'update:draftTitle',
  'update:draftDescription',
  'update:draftDueDate',
  'update:draftStatus',
  'update:draftSettings',
  'update:teamAddUserId',
  'update:teamAddRole',
])

const availableTeamCandidates = computed(() => props.teamOptions.filter(candidate => !candidate?.is_member && candidate?.id))
const settingsTitleId = computed(() => `project-settings-title-${props.scope === 'tracker' ? 'tracker' : 'project'}`)
const trackerSettings = computed(() => normalizeTrackerSettings(props.draftSettings, { preserveDeliveryMessage: true }))
const accessOptions = TRACKER_TOOL_ACCESS_OPTIONS
const teamName = computed(() => String(props.appIdentity?.team_name || '').trim() || 'Vue')
const inheritedDeliveryMessage = computed(() => `Thank you for choosing ${teamName.value}.`)
const hasCustomDeliveryLogo = computed(() => Boolean(trackerSettings.value.delivery.logo_upload_name))
const deliveryLogoStatus = computed(() => {
  if (hasCustomDeliveryLogo.value) return 'Custom logo for this delivery page.'
  if (props.appIdentity?.logo_url) return 'Using the team logo from settings.'
  return 'No logo set yet; delivery uses the fallback mark.'
})

const ACCESS_LABELS = {
  admin: 'Admins only',
  team: 'Team members',
  all: 'Team members and share links',
}

const toolRows = computed(() => [
  {
    key: 'comparison',
    name: 'Comparison',
    icon: '#icon-compare',
    hint: 'Compare two versions of the same shot in the media viewer.',
    enabled: trackerSettings.value.comparison.enabled,
    access: trackerSettings.value.comparison.access,
    accessLabel: ACCESS_LABELS[trackerSettings.value.comparison.access],
  },
  {
    key: 'details',
    name: 'Details',
    icon: '#icon-activity',
    hint: 'Show tracker progress, stats, and activity in the details panel.',
    enabled: trackerSettings.value.details.enabled,
    access: trackerSettings.value.details.access,
    accessLabel: ACCESS_LABELS[trackerSettings.value.details.access],
  },
  {
    key: 'brief_preview',
    name: 'Brief preview',
    icon: '#icon-info',
    hint: 'Show the brief summary beneath each shot in Vue Trackers.',
    enabled: trackerSettings.value.brief_preview.enabled,
  },
  {
    key: 'version_review',
    name: 'Approve versions before sharing',
    icon: '#icon-eye',
    hint: 'New versions stay internal until an owner publishes them.',
    enabled: trackerSettings.value.version_review.enabled,
  },
  {
    key: 'delivery',
    name: 'Delivery mode',
    icon: '#icon-package',
    hint: 'Open shared tracker links with a polished handoff screen.',
    enabled: trackerSettings.value.delivery.enabled,
  },
])

const EDITABLE_TEAM_ROLES = new Set(['viewer', 'editor', 'owner'])

const pendingPublicationCount = computed(() => (
  (props.tracker?.shots || []).reduce((count, shot) => (
    count + (shot?.versions || []).filter(version => (
      String(version?.share_state || '').trim().toLowerCase() === 'pending'
    )).length
  ), 0)
))

const STATUS_COLORS = {
  not_started: 'var(--v-status-draft)',
  in_progress: 'var(--v-status-active)',
  waiting_review: 'var(--v-status-review)',
  edits_requested: 'var(--v-status-hold)',
  done: 'var(--v-status-done)',
}

// Calm but distinct hues for avatar rings, mapped deterministically per user.
const AVATAR_HUES = [
  'var(--v-accent)',
  'var(--v-info)',
  'color-mix(in srgb, var(--v-accent) 58%, var(--v-info))',
  'color-mix(in srgb, var(--v-info) 64%, var(--v-text-secondary))',
  'color-mix(in srgb, var(--v-accent) 48%, var(--v-text-secondary))',
  'var(--v-warning)',
]

function emitTrackerSettings(toolKey, patch) {
  const current = normalizeTrackerSettings(props.draftSettings, { preserveDeliveryMessage: true })
  emit('update:draftSettings', {
    ...current,
    [toolKey]: {
      ...current[toolKey],
      ...patch,
    },
  })
}

function setToolEnabled(toolKey, enabled) {
  emitTrackerSettings(toolKey, { enabled })
}

function setToolAccess(toolKey, access) {
  emitTrackerSettings(toolKey, { access })
}

function setDeliveryMessage(message) {
  emitTrackerSettings('delivery', { message: String(message ?? '') })
}

function setDeliveryNotes(notes) {
  emitTrackerSettings('delivery', { notes: String(notes ?? '') })
}

function setDeliveryLink(index, patch) {
  const links = trackerSettings.value.delivery.links.map(link => ({ ...link }))
  links[index] = { ...(links[index] || { label: '', url: '' }), ...patch }
  emitTrackerSettings('delivery', { links })
}

function addDeliveryLink() {
  const links = [...trackerSettings.value.delivery.links, { label: '', url: '' }]
  emitTrackerSettings('delivery', { links })
}

function removeDeliveryLink(index) {
  const links = trackerSettings.value.delivery.links.filter((_, linkIndex) => linkIndex !== index)
  emitTrackerSettings('delivery', { links })
}

function handleDeliveryLogoChange(event) {
  const file = event?.target?.files?.[0]
  if (file) props.uploadDeliveryLogo(file)
  if (event?.target) event.target.value = ''
}

function hashString(value) {
  let hash = 0
  const seed = String(value ?? '')
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  }
  return hash
}

function getAvatarHue(seed) {
  return AVATAR_HUES[hashString(seed) % AVATAR_HUES.length]
}

function teamMemberRoleValue(member) {
  return member?.project_role || 'viewer'
}

function teamMemberHasEditableRole(member) {
  return EDITABLE_TEAM_ROLES.has(teamMemberRoleValue(member))
}

function isLockedTeamRole(member) {
  return ['admin', 'owner'].includes(teamMemberRoleValue(member))
}

function formatTeamRole(role) {
  const value = String(role || 'viewer')
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function getStatusColor(value) {
  return STATUS_COLORS[value] || 'var(--v-status-draft)'
}

function statusLabel(value) {
  const match = props.statusOptions.find(option => option.value === value)
  return match?.label || formatTeamRole(value)
}

function initialsFor(member) {
  const source = member?.display_name || member?.username || '?'
  const parts = String(source).trim().split(/\s+/).slice(0, 2)
  return parts.map(part => part.charAt(0).toUpperCase()).join('') || '?'
}

function avatarStyleFor(member) {
  const seed = member?.id || member?.username || member?.display_name || 'user'
  const hue = getAvatarHue(seed)
  return {
    background: `color-mix(in srgb, ${hue} 18%, var(--v-surface-inline))`,
    color: hue,
    boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${hue} 28%, transparent)`,
  }
}

function isCurrentUser(member) {
  if (!props.currentUserId || !member?.id) return false
  return String(member.id) === String(props.currentUserId)
}

const dueDateFormatted = computed(() => {
  return formatLocaleDate(props.draftDueDate, {
    options: { month: 'short', day: 'numeric', year: 'numeric' },
  })
})
</script>

<style scoped>
/* ─── Modal sizing ─────────────────────────────────── */
:global(.project-settings-modal-shell.v-modal-lg),
:global(.project-settings-modal-shell.v-modal-md) {
  max-width: 664px;
  max-height: min(calc(100dvh - 48px), 780px);
  --v-modal-header-padding: 20px 22px 18px;
  --v-modal-body-padding: 20px 22px 26px;
  --v-modal-footer-padding: 14px 22px 18px;
  --v-modal-bg: color-mix(in srgb, var(--v-surface-canvas) 96%, var(--v-bg-base));
  --v-modal-header-bg: color-mix(in srgb, var(--v-surface-panel) 82%, var(--v-modal-bg));
  --v-modal-footer-bg: color-mix(in srgb, var(--v-surface-panel) 82%, var(--v-modal-bg));
  border-color: color-mix(in srgb, var(--v-surface-border-strong) 86%, transparent);
  box-shadow:
    0 28px 72px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

:deep(.v-modal-body) {
  gap: 0;
  scrollbar-gutter: stable;
}

:deep(.v-modal-footer) {
  min-height: 68px;
}

/* ─── Header ───────────────────────────────────────── */
.ps-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  width: 100%;
}

.ps-head-title {
  margin: 0;
  font-size: var(--v-text-2xl);
  font-weight: 700;
  line-height: 1.22;
  letter-spacing: -0.015em;
  color: var(--v-text);
}

.ps-head-subtitle {
  max-width: 52ch;
  margin: 1px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

/* ─── Body shell ───────────────────────────────────── */
.ps-body {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

/* ─── Hero card ────────────────────────────────────── */
.ps-hero {
  display: grid;
  grid-template-columns: 144px minmax(0, 1fr);
  gap: var(--v-space-4);
  align-items: center;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 76%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-panel) 72%, var(--v-modal-bg));
  box-shadow: none;
}

.ps-hero-thumb {
  position: relative;
  width: 144px;
  aspect-ratio: 16 / 9;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-md);
  overflow: hidden;
  background: var(--v-bg-black);
  flex: 0 0 auto;
}

.ps-hero-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ps-hero-thumb.is-empty {
  background: color-mix(in srgb, var(--v-bg-black) 75%, transparent);
  border: 1px dashed color-mix(in srgb, var(--v-control-border) 80%, transparent);
}

.ps-hero-thumb .icon {
  width: 22px;
  height: 22px;
  color: var(--v-text-muted);
}

.ps-hero-meta {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-4);
  min-width: 0;
}

.ps-hero-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: var(--v-text-base);
  color: var(--v-text-secondary);
  min-width: 0;
}

.ps-hero-status-label {
  color: var(--v-text);
  font-weight: 600;
}

.ps-hero-due {
  margin-left: 2px;
  padding-left: 10px;
  border-left: 1px solid var(--v-divider-subtle);
  color: var(--v-text-muted);
  font-variant-numeric: tabular-nums;
}

.ps-hero-btn {
  justify-self: end;
  gap: 6px;
}

.ps-hero-btn .icon {
  width: 13px;
  height: 13px;
}

.ps-status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v-radius-full);
  flex: 0 0 auto;
  box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 30%, transparent);
}

/* ─── Section shell ────────────────────────────────── */
.ps-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ps-section > .v-section-label {
  padding: 0;
  color: color-mix(in srgb, var(--v-text-secondary) 84%, var(--v-text-muted));
  letter-spacing: 0.13em;
}

/* ─── Form grid ────────────────────────────────────── */
.ps-storage-card {
  display: grid;
  gap: 0;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 78%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-raised) 76%, var(--v-modal-bg));
  box-shadow: none;
  overflow: hidden;
}

.ps-storage-row {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 11px;
  align-items: start;
  padding: 13px 14px;
}

.ps-storage-row + .ps-storage-row {
  border-top: 1px solid var(--v-divider-subtle);
}

.ps-storage-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 16%, transparent);
}

.ps-storage-alert .ps-storage-icon {
  color: var(--v-warning);
  background: color-mix(in srgb, var(--v-warning) 7%, var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-warning) 16%, transparent);
}

.ps-storage-icon .icon { width: 16px; height: 16px; }

.ps-storage-copy { min-width: 0; display: grid; gap: 3px; padding-top: 2px; }
.ps-storage-copy strong { color: var(--v-text); font-size: var(--v-text-sm); line-height: 1.3; }
.ps-storage-copy span { color: var(--v-text-muted); font-size: var(--v-text-xs); line-height: 1.4; }
.ps-storage-copy code {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--v-text-muted);
  font: var(--v-text-2xs)/1.4 var(--v-font-mono, monospace);
}

.ps-storage-actions {
  display: flex;
  align-items: center;
  gap: 7px;
  padding-top: 2px;
}

.ps-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 12px;
}

.ps-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.ps-field.is-full {
  grid-column: 1 / -1;
}

.ps-field-hint {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.ps-input,
.ps-textarea {
  font-size: var(--v-text-md);
  font-weight: 450;
  color: var(--v-text);
}

.ps-input {
  height: 42px;
}

.ps-input-date {
  font-variant-numeric: tabular-nums;
}

.ps-input-date::-webkit-calendar-picker-indicator {
  filter: invert(0.55);
  cursor: pointer;
  opacity: 0.7;
  transition: opacity var(--v-transition-fast);
}

.ps-input-date:hover::-webkit-calendar-picker-indicator {
  opacity: 1;
}

.ps-textarea {
  min-height: 88px;
  resize: vertical;
  padding-top: 10px;
  padding-bottom: 10px;
  line-height: 1.45;
}

/* ─── Control pill (status + role) ─────────────────── */
.ps-control-pill {
  position: relative;
  width: 100%;
  height: 42px;
  padding: 0 12px 0 14px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-base);
  font-weight: 600;
  cursor: pointer;
}

.ps-control-pill:hover:not(.is-disabled):not(.is-locked) {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
}

.ps-control-pill.is-disabled,
.ps-control-pill.is-locked {
  cursor: default;
  color: var(--v-text-secondary);
}

.ps-control-pill.is-disabled {
  opacity: 0.65;
}

.ps-control-pill-compact {
  height: 34px;
  padding: 0 10px 0 12px;
  border-radius: var(--v-button-radius);
  font-size: var(--v-text-sm);
}

.ps-control-pill-label {
  flex: 1;
  min-width: 0;
  text-align: left;
}

.ps-control-pill-chevron {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
  flex: 0 0 auto;
}

.ps-control-pill-native {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  color: transparent;
  cursor: pointer;
  appearance: none;
  font: inherit;
}

.ps-control-pill-native:disabled {
  cursor: not-allowed;
}

.ps-control-pill-native:focus-visible {
  outline: none;
}

.ps-control-pill:has(.ps-control-pill-native:focus-visible) {
  border-color: var(--v-control-border-selected);
  box-shadow: var(--v-control-ring-selected);
}

.ps-status-pill .ps-status-dot {
  margin-right: 2px;
}

/* ─── Tracker tools ────────────────────────────────── */
.ps-tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ps-tool-card {
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 78%, transparent);
  background: color-mix(in srgb, var(--v-surface-raised) 76%, var(--v-modal-bg));
  box-shadow: none;
  overflow: hidden;
}

.ps-tool-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: var(--v-space-3);
  align-items: center;
  padding: 13px 14px;
}

.ps-tool-card.is-disabled {
  background: color-mix(in srgb, var(--v-surface-raised) 48%, var(--v-modal-bg));
}

.ps-tool-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--v-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--v-surface-inset) 72%, var(--v-surface-raised));
  color: var(--v-accent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 17%, transparent);
  flex: 0 0 auto;
}

.ps-tool-card.is-disabled .ps-tool-icon {
  color: var(--v-text-muted);
  background: color-mix(in srgb, var(--v-surface-inset) 62%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-surface-border-soft) 72%, transparent);
}

.ps-tool-icon .icon {
  width: 17px;
  height: 17px;
}

.ps-tool-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.ps-tool-topline {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
}

.ps-tool-name {
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 650;
}

.ps-tool-hint {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.ps-tool-switch {
  align-items: center;
  gap: 0;
}

.ps-tool-notice {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 9px;
  margin: 0 12px 12px 62px;
  padding: 10px 0 0;
  color: var(--v-warning);
  border-top: 1px solid color-mix(in srgb, var(--v-warning) 18%, transparent);
}

.ps-tool-notice > .icon {
  width: 15px;
  height: 15px;
  margin-top: 1px;
}

.ps-tool-notice > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ps-tool-notice strong {
  color: color-mix(in srgb, var(--v-warning) 78%, var(--v-text));
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.ps-tool-notice span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.4;
}

.ps-tool-access {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  margin: 0 12px 12px 62px;
  padding: 11px 0 0;
  border-top: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 62%, transparent);
}

.ps-tool-card.is-disabled .ps-tool-access {
  opacity: 0.58;
}

.ps-tool-access-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.ps-tool-access-copy > span:last-child {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  font-weight: 550;
}

.ps-tool-access-toggle {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
  min-width: 232px;
  padding: 3px;
}

.ps-tool-access-toggle .v-view-toggle-btn {
  width: auto;
  min-width: 0;
  height: 30px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: var(--v-button-radius);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.ps-tool-access-toggle .v-view-toggle-btn:hover:not(:disabled) {
  color: var(--v-text);
}

.ps-tool-access-toggle .v-view-toggle-btn.active {
  color: var(--v-text);
}

.ps-tool-access-toggle .v-view-toggle-btn:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.ps-tool-message {
  margin: 0 12px 12px 62px;
  padding: 11px 0 0;
  border-top: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 62%, transparent);
}

.ps-tool-message.is-disabled {
  opacity: 0.68;
}

.ps-tool-message-input {
  min-height: 62px;
  resize: vertical;
}

.ps-tool-delivery {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  margin: 0 12px 12px 62px;
  padding: 11px 0 0;
  border-top: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 62%, transparent);
}

.ps-tool-delivery.is-disabled {
  opacity: 0.68;
}

.ps-tool-delivery .ps-tool-message {
  margin: 0;
  padding: 0;
  border-top: 0;
}

.ps-delivery-logo-control {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-surface-canvas) 68%, transparent);
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 64%, transparent);
}

.ps-delivery-logo-mark {
  width: 54px;
  height: 38px;
  border-radius: var(--v-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--v-surface-inset);
  border: 1px solid var(--v-surface-border-soft);
}

.ps-delivery-logo-mark img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 5px;
}

.ps-delivery-logo-mark.is-empty {
  color: var(--v-text-muted);
  border-style: dashed;
}

.ps-delivery-logo-mark .icon {
  width: 17px;
  height: 17px;
}

.ps-delivery-logo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ps-delivery-logo-copy > span:last-child {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  font-weight: 550;
  line-height: 1.35;
}

.ps-delivery-logo-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ps-delivery-logo-upload {
  gap: 6px;
  cursor: pointer;
}

.ps-delivery-logo-nas {
  gap: 6px;
}

.ps-delivery-logo-upload.is-disabled {
  pointer-events: none;
  opacity: 0.62;
}

.ps-delivery-logo-upload .icon,
.ps-delivery-logo-nas .icon {
  width: 13px;
  height: 13px;
}

.ps-delivery-logo-remove {
  min-height: 32px;
}

.ps-delivery-links {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: 10px;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-canvas) 68%, transparent);
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 64%, transparent);
}

.ps-delivery-links-head,
.ps-delivery-link-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
}

.ps-delivery-links-head {
  justify-content: space-between;
}

.ps-delivery-links-head p {
  margin: 3px 0 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.ps-delivery-links-head .v-btn {
  flex: 0 0 auto;
  gap: 6px;
}

.ps-delivery-links-head .icon {
  width: 13px;
  height: 13px;
}

.ps-delivery-link-row {
  min-height: 38px;
}

.ps-delivery-link-row.is-inherited {
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-tint-strong);
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 58%, transparent);
}

.ps-delivery-link-inherited {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ps-delivery-link-inherited strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
}

.ps-delivery-link-inherited span {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ps-delivery-link-label {
  flex: 0 1 132px;
}

.ps-delivery-link-url {
  flex: 1 1 180px;
}

.ps-delivery-link-row .v-input {
  min-height: 34px;
  font-size: var(--v-text-base);
}

.ps-delivery-preview-link {
  width: 100%;
  min-height: 52px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 64%, transparent);
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-surface-canvas) 68%, transparent);
  color: var(--v-text);
  text-align: left;
  cursor: pointer;
}

.ps-delivery-preview-link:hover:not(:disabled) {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
}

.ps-delivery-preview-link:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.ps-delivery-preview-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--v-radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--v-accent) 28%, transparent);
}

.ps-delivery-preview-icon .icon {
  width: 15px;
  height: 15px;
}

.ps-delivery-preview-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ps-delivery-preview-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 750;
}

.ps-delivery-preview-copy span {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 550;
  line-height: 1.35;
}

/* ─── Team list ────────────────────────────────────── */
.ps-team-list {
  display: flex;
  flex-direction: column;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-surface-raised) 76%, var(--v-modal-bg));
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 78%, transparent);
  box-shadow: none;
  overflow: hidden;
}

.ps-team-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: var(--v-space-3);
  align-items: center;
  min-height: 56px;
  padding: 10px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 52%, transparent);
}

.ps-team-row:last-child {
  border-bottom: 0;
}

.ps-avatar {
  width: 34px;
  height: 34px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--v-text-sm);
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  flex: 0 0 auto;
}

.ps-team-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ps-team-name {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  font-size: var(--v-text-md);
  font-weight: 600;
  letter-spacing: 0;
  color: var(--v-text);
  min-width: 0;
}

.ps-team-name > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.ps-team-handle {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.ps-team-actions {
  display: grid;
  grid-template-columns: minmax(96px, auto) var(--v-btn-height-sm);
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.ps-role-pill {
  min-width: 96px;
  width: 100%;
}

.ps-team-remove,
.ps-team-remove-slot {
  width: var(--v-btn-height-sm);
  height: var(--v-btn-height-sm);
  flex: 0 0 auto;
}

.ps-team-remove {
  color: var(--v-text-muted);
}

.ps-team-remove:hover:not(:disabled) {
  color: var(--v-danger);
}

.ps-team-remove-slot {
  display: block;
  visibility: hidden;
  pointer-events: none;
}

/* ─── Team empty state ─────────────────────────────── */
.ps-empty {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--v-space-4);
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-surface-border-soft) 72%, transparent);
  background: color-mix(in srgb, var(--v-surface-raised) 58%, var(--v-modal-bg));
}

.ps-empty-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: var(--v-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--v-surface-inset);
  color: var(--v-text-secondary);
  flex: 0 0 auto;
}

.ps-empty-icon-wrap .icon {
  width: 18px;
  height: 18px;
}

.ps-empty-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ps-empty-title {
  font-size: var(--v-text-base);
  font-weight: 600;
  color: var(--v-text);
}

.ps-empty-hint {
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
  line-height: 1.45;
}

/* ─── Team compose row ─────────────────────────────── */
.ps-team-compose {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.ps-team-compose-user {
  position: relative;
  display: flex;
  align-items: center;
  height: 42px;
  padding: 0 36px 0 36px;
  border-radius: var(--v-radius-md);
  border: 1px solid var(--v-control-border);
  background: var(--v-control-bg);
  box-shadow: var(--v-surface-shadow-inset);
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
  min-width: 0;
}

.ps-team-compose-user:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
}

.ps-team-compose-user:has(select:focus-visible) {
  border-color: var(--v-control-border-selected);
  box-shadow: var(--v-control-ring-selected);
}

.ps-team-compose-icon {
  position: absolute;
  left: 12px;
  width: 14px;
  height: 14px;
  color: var(--v-text-muted);
  pointer-events: none;
}

.ps-team-compose-chevron {
  position: absolute;
  right: 12px;
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
  pointer-events: none;
}

.ps-team-compose-select {
  appearance: none;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  width: 100%;
  height: 100%;
  font: inherit;
  font-size: var(--v-text-base);
  font-weight: 500;
  color: var(--v-text);
  cursor: pointer;
}

.ps-team-compose-select:disabled {
  cursor: not-allowed;
  color: var(--v-text-muted);
}

.ps-team-compose-select:focus-visible {
  outline: none;
}

.ps-team-compose-trailing {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  flex: 0 0 auto;
}

.ps-team-add-btn {
  gap: 6px;
  height: 38px;
}

.ps-team-add-btn .icon {
  width: 13px;
  height: 13px;
}

/* ─── Mobile ───────────────────────────────────────── */
@media (max-width: 768px) {
  :global(.project-settings-modal-shell.v-modal-lg.is-sheet.is-mobile-full-height),
  :global(.project-settings-modal-shell.v-modal-md.is-sheet.is-mobile-full-height) {
    min-height: calc(100dvh - 8px);
    max-height: calc(100dvh - 8px);
    --v-modal-header-padding: 18px 16px 16px;
    --v-modal-body-padding: 16px 16px 22px;
    --v-modal-footer-padding: 12px 16px max(16px, env(safe-area-inset-bottom));
  }

  .ps-storage-row { grid-template-columns: 38px minmax(0, 1fr); }
  .ps-storage-actions { grid-column: 1 / -1; }
  .ps-storage-actions .v-btn { flex: 1; min-height: 44px; }
  :deep(.v-modal-body) {
    gap: 0;
    scrollbar-gutter: auto;
  }

  :deep(.v-modal-footer) {
    min-height: 68px;
  }

  :global(.project-settings-modal-shell .v-modal-footer > .v-btn) {
    height: 44px;
    min-height: 44px;
  }

  .ps-body {
    gap: 22px;
  }

  .ps-hero {
    grid-template-columns: 96px minmax(0, 1fr);
    gap: var(--v-space-3);
    padding: 10px;
  }

  .ps-hero-thumb {
    width: 96px;
  }

  .ps-hero-meta {
    grid-template-columns: minmax(0, 1fr);
    gap: 9px;
  }

  .ps-hero-btn {
    justify-self: start;
    min-height: 44px;
  }

  .ps-form-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .ps-field.is-half {
    grid-column: auto;
  }

  .ps-input,
  .ps-control-pill,
  .ps-team-compose-user {
    height: 44px;
  }

  .ps-textarea {
    min-height: 96px;
  }

  .ps-tool-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 10px;
    padding: 12px;
  }

  .ps-tool-icon {
    width: 34px;
    height: 34px;
    border-radius: var(--v-radius-md);
  }

  .ps-tool-switch {
    grid-column: auto;
    justify-self: end;
    margin-left: 0;
  }

  .ps-tool-access {
    flex-direction: column;
    align-items: stretch;
    margin-left: 56px;
  }

  .ps-tool-notice {
    margin-left: 56px;
  }

  .ps-tool-delivery {
    margin-left: 56px;
  }

  .ps-delivery-logo-control {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .ps-delivery-logo-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }

  .ps-delivery-links-head,
  .ps-delivery-link-row {
    align-items: stretch;
    flex-direction: column;
  }

  .ps-delivery-links-head .v-btn,
  .ps-delivery-link-row .v-input {
    width: 100%;
  }

  .ps-delivery-link-row.is-inherited {
    align-items: flex-start;
  }

  .ps-tool-access-toggle {
    width: 100%;
    min-width: 0;
  }

  .ps-tool-access-toggle .v-view-toggle-btn {
    flex: 1 1 0;
    min-height: 40px;
    height: 40px;
  }

  .ps-tool-delivery .v-btn,
  .ps-delivery-preview-link {
    min-height: 44px;
  }

  .ps-team-row {
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-rows: auto auto;
    grid-template-areas:
      "avatar copy"
      "actions actions";
    gap: 10px 12px;
    padding: 12px;
  }

  .ps-avatar {
    grid-area: avatar;
  }

  .ps-team-copy {
    grid-area: copy;
  }

  .ps-team-actions {
    grid-area: actions;
    width: 100%;
    grid-template-columns: minmax(0, 1fr) 44px;
  }

  .ps-team-actions .ps-team-remove.v-btn-icon,
  .ps-team-actions .ps-team-remove-slot {
    width: 44px;
    min-width: 44px;
    height: 44px;
    min-height: 44px;
  }

  .ps-role-pill {
    min-width: 0;
  }

  .ps-team-compose {
    grid-template-columns: 1fr;
    gap: var(--v-space-2);
  }

  .ps-team-compose-trailing {
    width: 100%;
    justify-content: space-between;
  }

  .ps-role-pill.ps-control-pill-compact {
    flex: 1 1 auto;
  }

  .ps-team-add-btn {
    flex: 0 0 auto;
    height: 44px;
  }
}
</style>
