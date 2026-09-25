<template>
  <section class="admin-section settings-stack">
    <AdminSettingsHeader
      title="Members"
      description="Add people and control what each person can open and change."
      icon="#icon-users"
    >
      <button class="v-btn v-btn-primary v-btn-sm" type="button" @click="$emit('open-create-user-modal')">
        <svg class="icon"><use href="#icon-plus" /></svg>
        Add member
      </button>
    </AdminSettingsHeader>

    <section class="settings-card">
      <div class="settings-list-toolbar">
        <div class="v-search-shell admin-search-wrap">
          <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
          <input
            :value="userSearch"
            class="v-search-input admin-search-input"
            placeholder="Search members"
            aria-label="Search members"
            @input="$emit('update:user-search', $event.target.value)"
          />
        </div>
        <span class="settings-list-count">
          {{ adminUserCount }} {{ adminUserCount === 1 ? 'administrator' : 'administrators' }} · {{ memberUserCount }} {{ memberUserCount === 1 ? 'member' : 'members' }}
        </span>
      </div>

      <div v-if="filteredUsers.length === 0" class="settings-empty">
        <strong>No members found</strong>
        <span>Try a different name or username.</span>
      </div>
      <ul v-else class="settings-list">
        <li v-for="user in filteredUsers" :key="user.id" class="settings-list-row">
          <span class="settings-list-mark is-round" aria-hidden="true">{{ userInitials(user) }}</span>
          <div class="settings-list-main">
            <div class="settings-list-title">
              <span>{{ user.display_name }}</span>
              <span v-if="user.id === currentUser?.id" class="settings-count-pill">You</span>
            </div>
            <div class="settings-list-meta">
              <span>@{{ user.username }}</span>
              <span>{{ summarizeAppAccess(user) }}</span>
            </div>
          </div>
          <div class="settings-list-actions">
            <span class="member-role" :class="{ 'is-admin': user.role === 'admin' }">{{ user.role === 'admin' ? 'Administrator' : 'Member' }}</span>
            <template v-if="user.can_manage">
              <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="$emit('open-edit-user-modal', user)">Edit</button>
              <VMenu
                v-if="user.id !== currentUser?.id"
                :open="openMenuId === user.id"
                align="end"
                :min-width="180"
                teleport
                @update:open="openMenuId = $event ? user.id : ''"
              >
                <template #trigger="{ triggerProps }">
                  <VOverflowButton
                    v-bind="triggerProps"
                    :active="openMenuId === user.id"
                    :label="`More actions for ${user.display_name}`"
                    @click="openMenuId = openMenuId === user.id ? '' : user.id"
                  />
                </template>
                <VMenuActionList :actions="[{ label: 'Remove member', icon: '#icon-trash', danger: true, run: () => $emit('delete-user', user) }]" />
              </VMenu>
            </template>
            <span v-else class="member-protected" title="Only administrators can change administrator accounts.">
              <svg class="icon" aria-hidden="true"><use href="#icon-lock" /></svg>
              Protected
            </span>
          </div>
        </li>
      </ul>
    </section>

    <p class="members-footnote">
      Project roles still apply. A member sees a project only after someone adds them to it.
    </p>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { VMenu, VMenuActionList, VOverflowButton } from '../primitives'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

defineProps({
  adminUserCount: { type: Number, required: true },
  memberUserCount: { type: Number, required: true },
  currentUser: { type: Object, default: null },
  filteredUsers: { type: Array, required: true },
  summarizeAppAccess: { type: Function, required: true },
  userInitials: { type: Function, required: true },
  userSearch: { type: String, default: '' },
})

defineEmits([
  'delete-user',
  'open-create-user-modal',
  'open-edit-user-modal',
  'update:user-search',
])

const openMenuId = ref('')
</script>

<style scoped>
.member-role {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  margin-right: 4px;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
}

.member-role.is-admin {
  background: var(--v-accent-muted);
  color: var(--v-accent-hover);
}

.member-protected {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 6px;
  color: var(--v-text-dim);
  font-size: var(--v-text-sm);
}

.member-protected .icon {
  width: 12px;
  height: 12px;
}

.members-footnote {
  margin: 0;
  padding: 0 2px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}
</style>
