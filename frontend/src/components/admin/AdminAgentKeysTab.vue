<template>
  <section class="admin-section agent-key-section">
    <AdminSettingsHeader
      eyebrow="Automation"
      title="Agent keys"
      description="Give an agent revocable access that always follows the permissions of its Vueio owner."
      icon="#icon-zap"
    >
      <button class="v-btn v-btn-secondary v-btn-sm" :disabled="personalKeySaving" @click="$emit('create-personal-agent-key')">
        <svg class="icon"><use href="#icon-plus" /></svg>
        {{ isAdmin ? 'New personal key' : 'New key' }}
      </button>
      <button v-if="isAdmin" class="v-btn v-btn-primary v-btn-sm" @click="$emit('open-create-key-modal')">
        <svg class="icon"><use href="#icon-plus" /></svg>
        New managed key
      </button>
    </AdminSettingsHeader>

    <div class="admin-toolbar agent-key-toolbar">
      <div class="v-search-shell admin-search-wrap">
        <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
        <input
          :value="keySearch"
          class="v-search-input admin-search-input"
          placeholder="Search keys..."
          @input="$emit('update:key-search', $event.target.value)"
        />
      </div>
      <div class="admin-toolbar-actions">
        <div v-if="isAdmin" class="admin-filter-row">
          <button class="v-chip admin-chip" :class="{ active: agentKeyScope === 'mine' }" @click="$emit('update:agent-key-scope', 'mine')">My keys</button>
          <button class="v-chip admin-chip" :class="{ active: agentKeyScope === 'all' }" @click="$emit('update:agent-key-scope', 'all')">All team keys</button>
        </div>
        <span class="agent-key-result-count">{{ filteredVisibleAgentKeys.length }} shown</span>
      </div>
    </div>

    <div v-if="filteredVisibleAgentKeys.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No agent keys match your filters.</div>
    <div v-else class="agent-key-owner-list">
      <article v-for="group in groupedVisibleAgentKeys" :key="group.key" class="agent-key-owner-group">
        <header class="agent-key-owner-header">
          <div class="agent-key-owner-identity">
            <div class="agent-key-owner-avatar">{{ group.initials }}</div>
            <div>
              <div class="agent-key-owner-kicker">{{ group.subtitle }}</div>
              <h3>{{ group.ownerLabel }}</h3>
              <p>{{ group.summary }}</p>
            </div>
          </div>
          <div class="agent-key-owner-counts">
            <span class="share-count-pill is-active">{{ group.activeCount }} active</span>
            <span v-if="group.inactiveCount" class="share-count-pill is-revoked">{{ group.inactiveCount }} inactive</span>
          </div>
        </header>

        <ol class="agent-key-list">
          <li v-for="entry in group.entries" :key="entry.key" class="agent-key-item" :class="{ 'is-disabled': !entry.record.is_active }">
            <div class="agent-key-main">
              <div class="agent-key-title-row">
                <h4>{{ entry.record.name }}</h4>
                <span class="share-status-pill" :class="entry.record.is_active ? 'success' : 'danger'">{{ entry.record.is_active ? 'Active' : 'Inactive' }}</span>
                <span v-if="entry.isMine" class="admin-badge success">Mine</span>
                <span v-if="entry.kind === 'managed'" class="admin-badge">Managed</span>
                <span class="admin-badge">Shown once</span>
              </div>
              <div class="agent-key-meta">
                <span>{{ entry.record.key_prefix }}...</span>
                <span>{{ entry.record.last_used_at ? `Last used ${formatDateLabel(entry.record.last_used_at)}` : 'Never used' }}</span>
                <span>{{ entry.kind === 'personal' ? 'Acts as you' : 'Admin managed' }}</span>
              </div>
              <p class="agent-key-permission-note">Inherits the owner’s current Vueio permissions</p>
            </div>
            <div class="agent-key-actions">
              <button class="v-btn v-btn-secondary v-btn-sm" @click="$emit('reissue-agent-key-skill', entry)">
                <svg class="icon"><use href="#icon-copy" /></svg>
                Reissue and copy skill
              </button>
              <button class="v-btn v-btn-ghost v-btn-sm" @click="$emit('reissue-unified-agent-key', entry)">Reissue</button>
              <VMenu
                :open="openActionKey === entry.key"
                align="end"
                :min-width="190"
                teleport
                @update:open="openActionKey = $event ? entry.key : ''"
              >
                <template #trigger="{ triggerProps }">
                  <VOverflowButton
                    v-bind="triggerProps"
                    :active="openActionKey === entry.key"
                    :label="`More actions for ${entry.record.name}`"
                    @click="openActionKey = openActionKey === entry.key ? '' : entry.key"
                  />
                </template>
                <VMenuActionList :actions="entryMenuActions(entry)" />
              </VMenu>
            </div>
          </li>
        </ol>
      </article>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { VMenu, VMenuActionList, VOverflowButton } from '../primitives'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

const openActionKey = ref('')

defineProps({
  agentKeyScope: { type: String, required: true },
  filteredVisibleAgentKeys: { type: Array, required: true },
  formatDateLabel: { type: Function, required: true },
  groupedVisibleAgentKeys: { type: Array, required: true },
  isAdmin: { type: Boolean, required: true },
  keySearch: { type: String, default: '' },
  personalKeySaving: { type: Boolean, required: true },
})

const emit = defineEmits([
  'create-personal-agent-key',
  'delete-unified-agent-key',
  'open-create-key-modal',
  'open-edit-agent-key',
  'reissue-agent-key-skill',
  'reissue-unified-agent-key',
  'toggle-unified-agent-key',
  'update:agent-key-scope',
  'update:key-search',
])

function entryMenuActions(entry) {
  return [
    { label: 'Edit key', icon: '#icon-edit', run: () => emit('open-edit-agent-key', entry) },
    {
      label: entry.record.is_active ? 'Deactivate key' : 'Activate key',
      icon: entry.record.is_active ? '#icon-lock' : '#icon-check',
      run: () => emit('toggle-unified-agent-key', entry),
    },
    { divider: true },
    { label: 'Delete key', icon: '#icon-trash', danger: true, run: () => emit('delete-unified-agent-key', entry) },
  ]
}
</script>

<style scoped>
.agent-key-section {
  overflow: hidden;
}

.agent-key-toolbar {
  align-items: center;
  margin-top: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.agent-key-toolbar .admin-toolbar-actions {
  justify-content: flex-end;
  gap: 10px;
}

.agent-key-toolbar .admin-search-wrap {
  flex: 1 1 260px;
  max-width: 420px;
}

.agent-key-result-count {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.agent-key-owner-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  padding-top: var(--v-space-4);
}

.agent-key-owner-group {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.agent-key-owner-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-tint-strong);
}

.agent-key-owner-identity {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v-space-3);
}

.agent-key-owner-avatar {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-border) 62%, transparent);
  background: color-mix(in srgb, var(--v-bg-field) 72%, transparent);
  color: var(--v-accent-hover);
  font-size: var(--v-text-base);
  font-weight: 800;
}

.agent-key-owner-kicker {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.08em;
  line-height: 1.1;
  text-transform: uppercase;
}

.agent-key-owner-header h3 {
  margin: 3px 0 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  line-height: 1.25;
}

.agent-key-owner-header p {
  margin: 3px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.25;
}

.agent-key-owner-counts {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.agent-key-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  margin: 0;
  padding: 8px 10px 10px;
  list-style: none;
}

.agent-key-item {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 11px 14px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.agent-key-item:hover {
  border-color: color-mix(in srgb, var(--v-border) 64%, transparent);
  background: var(--v-surface-tint-hover);
}

.agent-key-item.is-disabled {
  opacity: 0.72;
}

.agent-key-main {
  min-width: 0;
}

.agent-key-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2);
}

.agent-key-title-row h4 {
  min-width: 0;
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  line-height: 1.3;
}

.agent-key-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 8px;
  margin-top: 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.agent-key-meta span:not(:last-child)::after {
  content: '·';
  margin-left: var(--v-space-2);
  color: color-mix(in srgb, var(--v-text-muted) 58%, transparent);
}

.agent-key-permission-note {
  margin-top: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.agent-key-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 7px;
  max-width: 430px;
}

@media (max-width: 768px) {
  .agent-key-toolbar {
    gap: 10px;
    overflow-x: visible;
    align-items: stretch;
    flex-direction: column;
  }

  .agent-key-toolbar .admin-toolbar-actions {
    align-items: center;
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .agent-key-toolbar > .admin-search-wrap {
    flex: 0 0 100%;
    width: 100%;
    max-width: none;
  }

  .agent-key-toolbar .admin-filter-row {
    flex: 1 1 auto;
    width: auto;
    max-width: 100%;
  }

  .agent-key-owner-list {
    padding-top: var(--v-space-3);
    gap: 10px;
  }

  .agent-key-owner-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: var(--v-space-3);
  }

  .agent-key-owner-counts {
    justify-content: flex-start;
  }

  .agent-key-list {
    gap: 7px;
    padding: var(--v-space-2);
  }

  .agent-key-item {
    grid-template-columns: 1fr;
    gap: var(--v-space-2);
    padding: 10px;
  }

  .agent-key-actions {
    justify-content: flex-start;
    max-width: none;
    gap: 5px;
  }

  .agent-key-actions .v-btn {
    min-width: 0;
  }
}
</style>
