<template>
  <section class="admin-section team-settings-section">
    <AdminSettingsHeader
      eyebrow="Workspace"
      title="Team"
      description="Set the identity people see on deliveries and control who can enter your Vueio workspace."
      icon="#icon-users"
    >
      <button class="v-btn v-btn-primary v-btn-sm" @click="$emit('open-create-user-modal')">
        <svg class="icon"><use href="#icon-plus" /></svg>
        Add member
      </button>
    </AdminSettingsHeader>

    <div class="team-settings-shell">
      <div class="settings-panel identity-panel team-profile-panel">
        <div class="identity-hero">
          <div class="identity-logo-preview" :class="{ 'is-empty': !identityLogoUrl }">
            <img v-if="identityLogoUrl" :src="identityLogoUrl" alt="" />
            <span v-else>{{ identityInitials }}</span>
          </div>
          <div class="identity-hero-copy">
            <p class="settings-eyebrow">Team profile</p>
            <h2 class="settings-title">{{ identityTeamName }}</h2>
            <p class="settings-copy">
              Delivery pages inherit this logo, company name, and website unless a project overrides them.
            </p>
          </div>
        </div>

        <div class="v-form-grid admin-form-grid identity-form-grid">
          <VField label="Company name">
            <input
              :value="identityForm.team_name"
              class="v-input"
              placeholder="Vue"
              @input="$emit('update-identity-field', 'team_name', $event.target.value)"
            />
          </VField>
          <VField label="Website">
            <input
              :value="identityForm.website_url"
              class="v-input"
              placeholder="https://example.com"
              @input="$emit('update-identity-field', 'website_url', $event.target.value)"
            />
          </VField>
        </div>

        <div class="identity-logo-row">
          <div>
            <span class="settings-eyebrow">Logo</span>
            <p class="admin-note">{{ identityLogoUrl ? 'Shown by default on delivery pages.' : 'Upload a default delivery logo for the team.' }}</p>
          </div>
          <div class="identity-logo-actions">
            <label class="v-btn v-btn-secondary v-btn-sm" :class="{ 'is-disabled': identityLogoSaving }">
              <input type="file" hidden accept="image/*" :disabled="identityLogoSaving" @change="$emit('identity-logo-change', $event)" />
              <svg class="icon"><use href="#icon-upload" /></svg>
              <span>{{ identityLogoUrl ? 'Replace logo' : 'Upload logo' }}</span>
            </label>
            <button
              v-if="identityLogoUrl"
              class="v-btn v-btn-ghost v-btn-sm"
              :disabled="identityLogoSaving"
              @click="$emit('remove-identity-logo')"
            >
              Remove
            </button>
          </div>
        </div>

        <div class="identity-delivery-sample">
          <div class="identity-sample-mark">
            <img v-if="identityLogoUrl" :src="identityLogoUrl" alt="" />
            <span v-else>{{ identityInitials }}</span>
          </div>
          <div>
            <span>Default delivery greeting</span>
            <strong>Thank you for choosing {{ identityTeamName }}.</strong>
            <a v-if="identityWebsiteUrl" :href="identityWebsiteUrl" target="_blank" rel="noopener noreferrer">{{ identityWebsiteUrl }}</a>
          </div>
        </div>

        <p v-if="identityMessage" class="v-inline-note admin-note">{{ identityMessage }}</p>
        <div class="admin-card-actions">
          <button class="v-btn v-btn-primary" :disabled="identitySaving" @click="$emit('save-identity')">
            {{ identitySaving ? 'Saving' : 'Save team profile' }}
          </button>
        </div>
      </div>

      <div class="team-members-panel">
        <div class="team-members-head">
          <div>
            <p class="settings-eyebrow">Team members</p>
            <h2 class="settings-title">{{ users.length }} {{ users.length === 1 ? 'member' : 'members' }}</h2>
            <p class="settings-copy">Manage who can access Vueio and what workspace surfaces they can enter.</p>
          </div>
          <div class="team-member-counts">
            <span>{{ adminUserCount }} {{ adminUserCount === 1 ? 'admin' : 'admins' }}</span>
            <span>{{ artistUserCount }} {{ artistUserCount === 1 ? 'artist' : 'artists' }}</span>
          </div>
        </div>

        <div class="admin-toolbar team-member-toolbar">
          <div class="v-search-shell admin-search-wrap">
            <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
            <input
              :value="userSearch"
              class="v-search-input admin-search-input"
              placeholder="Search members..."
              @input="$emit('update:user-search', $event.target.value)"
            />
          </div>
          <span class="team-member-toolbar-count">{{ filteredUsers.length }} shown</span>
        </div>

        <div v-if="filteredUsers.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No team members match your search.</div>
        <div v-else class="team-member-list">
          <article v-for="user in filteredUsers" :key="user.id" class="team-member-item" :class="{ 'is-current': user.id === currentUser?.id }">
            <div class="team-member-avatar">{{ userInitials(user) }}</div>
            <div class="team-member-main">
              <div class="team-member-title-row">
                <h3>{{ user.display_name }}</h3>
                <span v-if="user.id === currentUser?.id" class="admin-badge success">You</span>
                <span class="admin-badge" :class="user.role === 'admin' ? 'success' : ''">{{ user.role }}</span>
              </div>
              <div class="team-member-meta">
                <span>@{{ user.username }}</span>
                <span>{{ summarizeAppAccess(user) }}</span>
              </div>
            </div>
            <div class="team-member-actions">
              <button class="v-btn v-btn-ghost v-btn-sm" @click="$emit('open-edit-user-modal', user)">Edit</button>
              <button v-if="user.id !== currentUser?.id" class="v-btn v-btn-danger v-btn-sm" @click="$emit('delete-user', user)">Delete</button>
            </div>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { VField } from '../primitives'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

defineProps({
  adminUserCount: { type: Number, required: true },
  artistUserCount: { type: Number, required: true },
  currentUser: { type: Object, default: null },
  filteredUsers: { type: Array, required: true },
  identityForm: { type: Object, required: true },
  identityInitials: { type: String, required: true },
  identityLogoSaving: { type: Boolean, required: true },
  identityLogoUrl: { type: String, default: '' },
  identityMessage: { type: String, default: '' },
  identitySaving: { type: Boolean, required: true },
  identityTeamName: { type: String, required: true },
  identityWebsiteUrl: { type: String, default: '' },
  summarizeAppAccess: { type: Function, required: true },
  userInitials: { type: Function, required: true },
  userSearch: { type: String, default: '' },
  users: { type: Array, required: true },
})

defineEmits([
  'delete-user',
  'identity-logo-change',
  'open-create-user-modal',
  'open-edit-user-modal',
  'remove-identity-logo',
  'save-identity',
  'update:user-search',
  'update-identity-field',
])
</script>

<style scoped>
.team-settings-section {
  max-width: 1280px;
  overflow: hidden;
}

.team-settings-shell {
  display: grid;
  grid-template-columns: minmax(420px, 0.82fr) minmax(500px, 1fr);
  align-items: start;
  gap: var(--v-space-4);
  padding-top: var(--v-space-4);
}

.identity-panel {
  gap: 18px;
}

.team-profile-panel,
.team-members-panel {
  max-width: none;
  padding: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.team-members-panel {
  display: grid;
  gap: var(--v-space-3);
  padding: 0;
  overflow: hidden;
}

.team-members-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--v-space-4);
  padding: 14px 14px 0;
}

.team-member-counts {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 2px;
}

.team-member-counts span {
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--v-border) 52%, transparent);
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-bg-field) 34%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 740;
}

.team-member-toolbar {
  border-top: 1px solid color-mix(in srgb, var(--v-divider-subtle) 80%, transparent);
  border-bottom-color: color-mix(in srgb, var(--v-divider-subtle) 70%, transparent);
}

.team-member-toolbar .admin-search-wrap {
  flex: 1 1 260px;
  max-width: 360px;
}

.team-member-toolbar-count {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.team-member-list {
  display: grid;
  gap: 2px;
  padding: 0 8px 8px;
}

.team-member-item {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  padding: 10px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.team-member-item:hover,
.team-member-item.is-current {
  border-color: color-mix(in srgb, var(--v-border) 58%, transparent);
  background: var(--v-surface-tint-hover);
}

.team-member-avatar {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--v-accent) 30%, var(--v-border));
  border-radius: 50%;
  background: color-mix(in srgb, var(--v-accent) 18%, var(--v-bg-field));
  color: color-mix(in srgb, var(--v-accent) 70%, var(--v-text));
  font-size: var(--v-text-sm);
  font-weight: 820;
  letter-spacing: 0;
}

.team-member-main {
  min-width: 0;
}

.team-member-title-row,
.team-member-meta,
.team-member-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.team-member-title-row {
  gap: 7px;
}

.team-member-title-row h3 {
  min-width: 0;
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  line-height: 1.3;
}

.team-member-meta {
  gap: 5px 8px;
  margin-top: var(--v-space-1);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.team-member-meta span:not(:last-child)::after {
  content: '·';
  margin-left: var(--v-space-2);
  color: color-mix(in srgb, var(--v-text-muted) 58%, transparent);
}

.team-member-actions {
  justify-content: flex-end;
  gap: 7px;
}

.identity-hero,
.identity-logo-row,
.identity-delivery-sample {
  display: flex;
  align-items: center;
  gap: 14px;
}

.identity-hero {
  align-items: flex-start;
  padding: 0 0 var(--v-space-4);
  border-bottom: 1px solid var(--v-divider-subtle);
}

.identity-logo-preview,
.identity-sample-mark {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-border) 62%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 62%, transparent);
  color: var(--v-text);
  font-weight: 850;
  letter-spacing: 0;
}

.identity-logo-preview {
  width: 82px;
  height: 62px;
  border-radius: var(--v-radius-lg);
}

.identity-logo-preview img,
.identity-sample-mark img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  padding: var(--v-space-2);
}

.identity-logo-preview.is-empty {
  border-style: dashed;
  color: color-mix(in srgb, var(--v-accent) 68%, var(--v-text-secondary));
}

.identity-hero-copy {
  min-width: 0;
}

.identity-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: var(--v-space-3);
}

.identity-logo-row {
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.identity-logo-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.identity-logo-actions label {
  gap: 7px;
  cursor: pointer;
}

.identity-logo-actions label.is-disabled {
  pointer-events: none;
  opacity: 0.62;
}

.identity-logo-actions .icon {
  width: 13px;
  height: 13px;
}

.identity-delivery-sample {
  align-items: flex-start;
  padding: 12px 14px;
  border-left: 2px solid color-mix(in srgb, var(--v-accent) 64%, transparent);
  background: color-mix(in srgb, var(--v-bg-field) 28%, transparent);
  border-radius: var(--v-radius-md);
}

.identity-sample-mark {
  width: 54px;
  height: 38px;
  border-radius: var(--v-radius-md);
  font-size: var(--v-text-sm);
}

.identity-delivery-sample div:last-child {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.identity-delivery-sample span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 780;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.identity-delivery-sample strong {
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.identity-delivery-sample a {
  color: var(--v-accent-hover);
  font-size: var(--v-text-base);
  text-decoration: none;
}

@media (max-width: 1100px) {
  .team-settings-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .team-profile-panel,
  .team-members-panel {
    padding: 14px;
    border-radius: var(--v-radius-md);
  }

  .identity-logo-actions {
    flex-wrap: wrap;
  }

  .team-settings-shell {
    grid-template-columns: 1fr;
    padding-top: var(--v-space-3);
  }

  .team-members-head,
  .team-member-toolbar {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .team-members-head,
  .team-member-toolbar {
    flex-direction: column;
  }

  .team-member-counts,
  .team-member-actions {
    justify-content: flex-start;
  }

  .team-member-toolbar .admin-search-wrap {
    width: 100%;
    max-width: none;
  }

  .team-member-item {
    grid-template-columns: 34px minmax(0, 1fr);
    gap: var(--v-space-2);
  }

  .team-member-avatar {
    width: 34px;
    height: 34px;
  }

  .team-member-actions {
    grid-column: 2;
  }
}

@media (min-width: 481px) and (max-width: 768px) {
  .team-member-item {
    grid-template-columns: 34px minmax(0, 1fr) auto;
  }

  .team-member-actions {
    grid-column: auto;
  }
}

@media (max-width: 480px) {
  .identity-form-grid {
    grid-template-columns: 1fr;
  }

  .identity-hero,
  .identity-logo-row,
  .identity-delivery-sample {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
