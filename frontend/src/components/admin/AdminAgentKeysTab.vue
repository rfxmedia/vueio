<template>
  <section class="admin-section settings-stack">
    <AdminSettingsHeader
      title="Agent keys"
      description="Let an AI agent or script use Vueio for you. A key can see and do only what its owner can."
      icon="#icon-zap"
    >
      <button class="v-btn v-btn-primary v-btn-sm" type="button" @click="$emit('open-create-key-modal')">
        <svg class="icon"><use href="#icon-plus" /></svg>
        New key
      </button>
    </AdminSettingsHeader>

    <section v-if="visibleToken?.token" class="settings-card agent-token-card" role="status">
      <div class="settings-card-head">
        <div>
          <h3>{{ visibleToken.title }}</h3>
          <p>Copy the token now. Vueio shows it only once. {{ visibleToken.subtitle }}</p>
        </div>
      </div>
      <div class="settings-card-body agent-token-body">
        <code class="agent-token">{{ visibleToken.token }}</code>
        <div class="agent-token-actions">
          <button class="v-btn v-btn-primary v-btn-sm" type="button" @click="$emit('copy-token')">
            <svg class="icon"><use href="#icon-copy" /></svg>
            Copy token
          </button>
          <button class="v-btn v-btn-secondary v-btn-sm" type="button" @click="$emit('copy-token-skill')">Copy skill</button>
          <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="$emit('dismiss-token')">Done</button>
        </div>
      </div>
    </section>

    <section class="settings-card">
      <div class="settings-list-toolbar">
        <div class="v-search-shell admin-search-wrap">
          <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
          <input
            :value="keySearch"
            class="v-search-input admin-search-input"
            placeholder="Search keys"
            aria-label="Search keys"
            @input="$emit('update:key-search', $event.target.value)"
          />
        </div>
        <div v-if="isAdmin" class="settings-segmented" role="group" aria-label="Show keys">
          <button type="button" :aria-pressed="agentKeyScope === 'mine'" @click="$emit('update:agent-key-scope', 'mine')">Mine</button>
          <button type="button" :aria-pressed="agentKeyScope === 'all'" @click="$emit('update:agent-key-scope', 'all')">Everyone</button>
        </div>
        <span class="settings-list-count">{{ filteredVisibleAgentKeys.length }} {{ filteredVisibleAgentKeys.length === 1 ? 'key' : 'keys' }}</span>
      </div>

      <div v-if="filteredVisibleAgentKeys.length === 0" class="settings-empty">
        <strong>{{ keySearch ? 'No keys found' : 'No agent keys yet' }}</strong>
        <span>{{ keySearch ? 'Try a different name.' : 'Select New key to connect an agent or script.' }}</span>
      </div>
      <div v-else>
      <template v-for="group in groupedVisibleAgentKeys" :key="group.key">
        <div v-if="showGroups" class="settings-list-group">
          {{ group.ownerLabel }}
          <span class="settings-count-pill">{{ group.entries.length }}</span>
        </div>
        <ul class="settings-list">
          <li v-for="entry in group.entries" :key="entry.key" class="settings-list-row" :class="{ 'is-muted': !entry.record.is_active }">
            <span class="settings-list-mark" aria-hidden="true"><svg class="icon"><use href="#icon-zap" /></svg></span>
            <div class="settings-list-main">
              <div class="settings-list-title">
                <span>{{ entry.record.name }}</span>
                <span v-if="!entry.record.is_active" class="settings-count-pill">Off</span>
              </div>
              <div class="settings-list-meta">
                <span class="agent-key-prefix">{{ entry.record.key_prefix }}…</span>
                <span>{{ entry.record.last_used_at ? `Last used ${formatDateLabel(entry.record.last_used_at)}` : 'Never used' }}</span>
              </div>
            </div>
            <div class="settings-list-actions">
              <button
                class="v-btn v-btn-ghost v-btn-sm"
                type="button"
                title="Makes a new token and copies setup text for your agent. The old token stops working."
                @click="$emit('reissue-agent-key-skill', entry)"
              >
                <svg class="icon"><use href="#icon-copy" /></svg>
                Copy skill
              </button>
              <VMenu
                :open="openActionKey === entry.key"
                align="end"
                :min-width="200"
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
        </ul>
      </template>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VMenu, VMenuActionList, VOverflowButton } from '../primitives'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

const openActionKey = ref('')

const props = defineProps({
  agentKeyScope: { type: String, required: true },
  filteredVisibleAgentKeys: { type: Array, required: true },
  formatDateLabel: { type: Function, required: true },
  groupedVisibleAgentKeys: { type: Array, required: true },
  isAdmin: { type: Boolean, required: true },
  keySearch: { type: String, default: '' },
  visibleToken: { type: Object, default: null },
})

const emit = defineEmits([
  'copy-token',
  'copy-token-skill',
  'delete-unified-agent-key',
  'dismiss-token',
  'open-create-key-modal',
  'open-edit-agent-key',
  'reissue-agent-key-skill',
  'reissue-unified-agent-key',
  'toggle-unified-agent-key',
  'update:agent-key-scope',
  'update:key-search',
])

const showGroups = computed(() => props.isAdmin && props.agentKeyScope === 'all')

function entryMenuActions(entry) {
  return [
    { label: 'Rename', icon: '#icon-edit', run: () => emit('open-edit-agent-key', entry) },
    { label: 'Make new token', icon: '#icon-refresh', run: () => emit('reissue-unified-agent-key', entry) },
    {
      label: entry.record.is_active ? 'Turn off' : 'Turn on',
      icon: entry.record.is_active ? '#icon-lock' : '#icon-check',
      run: () => emit('toggle-unified-agent-key', entry),
    },
    { divider: true },
    { label: 'Delete key', icon: '#icon-trash', danger: true, run: () => emit('delete-unified-agent-key', entry) },
  ]
}
</script>

<style scoped>
.agent-token-card {
  border-color: color-mix(in srgb, var(--v-accent) 28%, var(--v-surface-border-soft));
  background: color-mix(in srgb, var(--v-accent) 5%, var(--v-surface-canvas));
}

.agent-token-body {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.agent-token {
  min-width: 0;
  overflow-x: auto;
  padding: 9px 12px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  color: var(--v-text);
  font-size: var(--v-text-sm);
  white-space: nowrap;
}

.agent-token-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--v-space-2);
}

.agent-key-prefix {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: var(--v-text-xs);
}

@media (max-width: 768px) {
  .agent-token-body {
    grid-template-columns: 1fr;
  }

  .agent-token-actions .v-btn {
    flex: 1 1 auto;
    min-height: var(--v-btn-height-lg);
  }
}
</style>
