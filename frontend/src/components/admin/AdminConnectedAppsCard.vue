<template>
  <section class="settings-card">
    <div class="settings-card-head">
      <div>
        <h3>Connected apps</h3>
        <p>Apps such as Claude and ChatGPT that you connected with Sign in with Vueio. They act as you, like an agent key.</p>
      </div>
    </div>
    <div v-if="loading" class="settings-empty">
      <span>Loading…</span>
    </div>
    <div v-else-if="apps.length === 0" class="settings-empty">
      <strong>No connected apps</strong>
      <span>In a chat app, add a connector with the address {{ mcpUrl }}, then sign in to Vueio.</span>
    </div>
    <ul v-else class="settings-list">
      <li v-for="app in apps" :key="app.id" class="settings-list-row">
        <span class="settings-list-mark" aria-hidden="true"><svg class="icon"><use href="#icon-link" /></svg></span>
        <div class="settings-list-main">
          <div class="settings-list-title"><span>{{ app.client_name }}</span></div>
          <div class="settings-list-meta">
            <span>Connected {{ formatDateLabel(app.created_at) }}</span>
            <span>{{ app.last_used_at ? `Last used ${formatDateLabel(app.last_used_at)}` : 'Never used' }}</span>
          </div>
        </div>
        <div class="settings-list-actions">
          <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="busyId === app.id" @click="disconnect(app)">
            Disconnect
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'
import { notify } from '../../utils/toasts'
import { resolveVueioApiBaseUrl } from '../../utils/vueioAgentSetup'

defineProps({
  formatDateLabel: { type: Function, required: true },
})

const apps = ref([])
const loading = ref(true)
const busyId = ref('')
const mcpUrl = `${resolveVueioApiBaseUrl()}/api/mcp`

async function load() {
  try {
    const { data } = await api.get('/api/me/connected-apps')
    apps.value = data.apps || []
  } catch (error) {
    notify(`Failed to load connected apps: ${getApiErrorMessage(error)}`)
  } finally {
    loading.value = false
  }
}

async function disconnect(app) {
  if (!confirm(`Disconnect ${app.client_name}? It stops working at once. You can connect it again later.`)) return
  busyId.value = app.id
  try {
    await api.delete(`/api/me/connected-apps/${app.id}`)
    apps.value = apps.value.filter(item => item.id !== app.id)
    notify(`${app.client_name} disconnected`)
  } catch (error) {
    notify(`Failed to disconnect: ${getApiErrorMessage(error)}`)
  } finally {
    busyId.value = ''
  }
}

onMounted(load)
</script>
