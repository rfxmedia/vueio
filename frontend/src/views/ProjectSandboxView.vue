<template>
  <section
    class="sbx"
    :class="{ 'is-editing': editing, 'is-share': shareMode }"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- ─── Toolbar ─────────────────────────────────────────── -->
    <header class="sbx-bar">
      <div class="sbx-bar-lead">
        <span class="sbx-tile" aria-hidden="true"><svg class="icon"><use href="#icon-code" /></svg></span>
        <div class="sbx-heading">
          <h1 class="sbx-name" :title="sandbox?.name">{{ sandbox?.name }}</h1>
          <p class="sbx-status" aria-live="polite">
            <template v-if="editing">
              <span>{{ draftBase ? `Editing version ${draftBase}` : 'New page' }}</span>
              <span v-if="dirty" class="sbx-unsaved"><span class="sbx-unsaved-dot" aria-hidden="true"></span>Unsaved changes</span>
            </template>
            <template v-else>
              <span :title="statusTitle">{{ statusLabel }}</span>
              <Transition name="sbx-fade"><span v-if="liveNotice" class="sbx-live">{{ liveNotice }}</span></Transition>
            </template>
          </p>
        </div>
      </div>

      <div v-if="editing" class="sbx-bar-actions is-editing">
        <div class="sbx-segmented" role="group" aria-label="Layout">
          <button
            v-for="option in layoutOptions"
            :key="option.value"
            type="button"
            :class="{ 'is-active': layout === option.value }"
            :aria-pressed="layout === option.value"
            :aria-label="option.label"
            :title="option.title"
            @click="setLayout(option.value)"
          >
            <svg class="icon" aria-hidden="true"><use :href="option.icon" /></svg>
            <span>{{ option.label }}</span>
          </button>
        </div>
        <input
          v-model="message"
          class="v-input sbx-message"
          maxlength="200"
          placeholder="Describe your change (optional)"
          aria-label="Describe your change"
          @keydown.enter.prevent="save()"
        />
        <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="stopEditing">{{ dirty ? 'Cancel' : 'Done' }}</button>
        <button type="button" class="v-btn v-btn-primary v-btn-sm sbx-save" :disabled="saving || !dirty" :title="`Save version (${saveShortcut})`" @click="save()">
          <svg v-if="saving" class="icon spinning" aria-hidden="true"><use href="#icon-loader" /></svg>
          <span>Save version</span>
        </button>
      </div>

      <div v-else class="sbx-bar-actions">
        <button v-if="!shareMode" type="button" class="v-btn v-btn-quiet v-btn-sm" :class="{ 'is-active': historyOpen }" :aria-pressed="historyOpen" aria-label="History" title="History" @click="toggleHistory">
          <svg class="icon" aria-hidden="true"><use href="#icon-history" /></svg>
          <span class="sbx-btn-label">History</span>
        </button>
        <button v-if="canEdit && hasPage" type="button" class="v-btn v-btn-secondary v-btn-sm" aria-label="Edit code" title="Edit code" @click="startEditing()">
          <svg class="icon" aria-hidden="true"><use href="#icon-code" /></svg>
          <span class="sbx-btn-label">Edit code</span>
        </button>
        <button v-if="canShare" type="button" class="v-btn v-btn-secondary v-btn-sm" aria-label="Share" title="Share" @click="shareProjectSandbox(sandbox)">
          <svg class="icon" aria-hidden="true"><use href="#icon-share" /></svg>
          <span class="sbx-btn-label">Share</span>
        </button>
        <button v-if="hasPage" type="button" class="v-icon-action is-muted" title="Full screen" aria-label="Full screen" @click="frameRef?.requestFullscreen()">
          <svg class="icon" aria-hidden="true"><use href="#icon-fullscreen" /></svg>
        </button>
        <VMenu v-if="!shareMode" v-model:open="menuOpen" align="end" teleport>
          <template #trigger="{ triggerProps }">
            <button type="button" class="v-icon-action is-muted" aria-label="More actions" title="More" v-bind="triggerProps" @click="menuOpen = !menuOpen">
              <svg class="icon" aria-hidden="true"><use href="#icon-more" /></svg>
            </button>
          </template>
          <VMenuActionList :actions="menuActions" />
        </VMenu>
      </div>
    </header>

    <!-- ─── Old version banner ──────────────────────────────── -->
    <div v-if="viewing && !editing" class="sbx-banner" role="status">
      <svg class="icon" aria-hidden="true"><use href="#icon-history" /></svg>
      <p>
        <strong>Version {{ viewing.number }}</strong>
        <span>{{ viewingLabel }}</span>
      </p>
      <div class="sbx-banner-actions">
        <button type="button" class="v-btn v-btn-quiet v-btn-sm" :aria-pressed="comparing" @click="comparing = !comparing">
          <svg class="icon" aria-hidden="true"><use :href="comparing ? '#icon-eye' : '#icon-compare'" /></svg>
          {{ comparing ? 'Show page' : 'Compare with current' }}
        </button>
        <button v-if="canEdit" type="button" class="v-btn v-btn-secondary v-btn-sm" @click="restore(viewing.number)">
          <svg class="icon" aria-hidden="true"><use href="#icon-undo" /></svg>
          Restore this version
        </button>
        <button type="button" class="v-btn v-btn-quiet v-btn-sm" @click="showCurrent">Back to current</button>
      </div>
    </div>

    <div v-if="editing && reviewing" class="sbx-banner is-review" role="status">
      <svg class="icon" aria-hidden="true"><use href="#icon-eye" /></svg>
      <p>
        <strong>Check the page</strong>
        <span>It is not saved yet. Save it to make it version {{ (contentVersion || 0) + 1 }}.</span>
      </p>
    </div>

    <!-- ─── Body ────────────────────────────────────────────── -->
    <div class="sbx-body">
      <div class="sbx-stage">
        <div v-if="loadState === 'loading'" class="sbx-state">
          <span class="sbx-spinner" aria-hidden="true"></span>
          <span>Opening the page…</span>
        </div>
        <div v-else-if="loadState === 'error'" class="sbx-state is-error">
          <span>{{ loadError }}</span>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="loadLatest()">Try again</button>
        </div>

        <!-- Editing: code, live preview, or both -->
        <div v-else-if="editing" class="sbx-editor" :class="`is-${layout}`">
          <div v-show="layout !== 'preview'" class="sbx-pane is-code">
            <SandboxCodeEditor
              ref="editorRef"
              v-model="draft"
              placeholder="Paste your HTML here, or start typing."
              @save="save()"
            />
          </div>
          <div v-show="layout !== 'code'" class="sbx-pane is-preview">
            <SandboxFrame :html="previewHtml" :title="`${sandbox?.name || 'Sandbox'} preview`" keep-scroll />
          </div>
        </div>

        <!-- Blank page -->
        <div v-else-if="!hasPage && !viewing" class="sbx-empty">
          <div class="sbx-empty-art" aria-hidden="true">
            <div class="sbx-art-window">
              <span class="sbx-art-dots"><i></i><i></i><i></i></span>
              <span class="sbx-art-line is-title"></span>
              <span class="sbx-art-line"></span>
              <span class="sbx-art-line is-short"></span>
              <span class="sbx-art-blocks"><i></i><i></i><i></i></span>
            </div>
            <svg class="icon sbx-art-spark is-one"><use href="#icon-sparkles" /></svg>
            <svg class="icon sbx-art-spark is-two"><use href="#icon-sparkles" /></svg>
          </div>

          <template v-if="canEdit">
            <h2 class="sbx-empty-title">What should we build?</h2>
            <p class="sbx-empty-copy">
              A blank page for anything: a budget, a schedule, a pitch. Paste the HTML,
              drop in a file, or ask your AI agent to build it for you.
            </p>

            <div class="sbx-choices">
              <button type="button" class="sbx-choice" :class="{ 'is-active': agentPromptOpen }" :aria-expanded="agentPromptOpen" @click="agentPromptOpen = !agentPromptOpen">
                <span class="sbx-choice-icon is-agent" aria-hidden="true"><svg class="icon"><use href="#icon-sparkles" /></svg></span>
                <span class="sbx-choice-title">Ask your AI agent</span>
                <span class="sbx-choice-copy">Copy a prompt. Your agent builds the page and saves it here.</span>
              </button>
              <button type="button" class="sbx-choice" @click="startEditing({ text: '', layout: 'split', review: false })">
                <span class="sbx-choice-icon" aria-hidden="true"><svg class="icon"><use href="#icon-code" /></svg></span>
                <span class="sbx-choice-title">Paste code</span>
                <span class="sbx-choice-copy">Paste HTML from anywhere. You see the page before you save it.</span>
              </button>
              <button type="button" class="sbx-choice" @click="chooseFile">
                <span class="sbx-choice-icon" aria-hidden="true"><svg class="icon"><use href="#icon-upload" /></svg></span>
                <span class="sbx-choice-title">Upload a file</span>
                <span class="sbx-choice-copy">Choose an HTML file, or drop it anywhere on this page.</span>
              </button>
            </div>

            <Transition name="sbx-reveal">
              <div v-if="agentPromptOpen" class="sbx-prompt">
                <div class="sbx-prompt-head">
                  <span>Prompt for your agent</span>
                  <button type="button" class="v-btn v-btn-primary v-btn-sm" @click="copyAgentPrompt">
                    <svg class="icon" aria-hidden="true"><use :href="promptCopied ? '#icon-check' : '#icon-copy'" /></svg>
                    {{ promptCopied ? 'Copied' : 'Copy prompt' }}
                  </button>
                </div>
                <pre class="sbx-prompt-text">{{ agentPrompt }}</pre>
                <p class="sbx-prompt-hint">
                  Add what the page should show at the end. Your agent needs access to Vueio:
                  <a href="/settings?tab=agent-keys" @click.prevent="openAgentSettings">connect it in Settings</a>.
                </p>
              </div>
            </Transition>

            <p class="sbx-empty-foot">
              <span><kbd>{{ pasteShortcut }}</kbd> pastes HTML here</span>
              <span aria-hidden="true">·</span>
              <button type="button" class="sbx-link" @click="startEditing({ text: starterPage, layout: 'split', review: false })">Start from a blank template</button>
            </p>
          </template>
          <template v-else>
            <h2 class="sbx-empty-title">{{ shareMode ? 'This page is empty' : 'Nothing here yet' }}</h2>
            <p class="sbx-empty-copy">{{ shareMode ? 'Come back later to see it.' : 'Someone who manages this project can build this page.' }}</p>
          </template>
        </div>

        <!-- The page, an old version, or the changes -->
        <SandboxDiffView
          v-else-if="viewing && comparing"
          :project-id="currentProject.id"
          :sandbox-id="sandbox.id"
          :from-version="viewing.number"
          :to-version="contentVersion"
        />
        <SandboxFrame
          v-else
          ref="frameRef"
          :key="viewing ? `v${viewing.number}` : 'current'"
          :html="viewing ? viewing.content : content"
          :title="sandbox?.name || 'Sandbox page'"
          keep-scroll
        />

        <div v-if="dropActive" class="sbx-drop" aria-hidden="true">
          <div class="sbx-drop-card">
            <svg class="icon"><use href="#icon-upload" /></svg>
            <strong>Drop an HTML file</strong>
            <span>You see the page before you save it.</span>
          </div>
        </div>
      </div>

      <Transition name="sbx-slide">
        <SandboxHistoryPanel
          v-if="historyOpen && !shareMode && !editing"
          class="sbx-history"
          :project-id="currentProject.id"
          :sandbox-id="sandbox.id"
          :latest-version="contentVersion"
          :selected-number="viewing ? viewing.number : contentVersion"
          @select="selectVersion"
          @close="historyOpen = false"
        />
      </Transition>
    </div>

    <input ref="fileInputRef" type="file" accept=".html,.htm,text/html" hidden @change="onFileChosen" />

    <!-- ─── Someone saved first ─────────────────────────────── -->
    <VModal :model-value="Boolean(conflict)" size="sm" title="A newer version was saved" @update:model-value="value => !value && (conflict = null)">
      <template #header>
        <VModalHeader title="A newer version was saved" @close="conflict = null" />
      </template>
      <p class="sbx-conflict-copy">
        Version {{ conflict?.latest }} was saved while you were editing. Your changes are still here.
        Save yours as the newest version, or open version {{ conflict?.latest }} instead.
      </p>
      <template #footer>
        <button type="button" class="v-btn v-btn-quiet" @click="discardForLatest">Open version {{ conflict?.latest }}</button>
        <button type="button" class="v-btn v-btn-primary" :disabled="saving" @click="save({ force: true })">Save mine as version {{ (conflict?.latest || 0) + 1 }}</button>
      </template>
    </VModal>
  </section>
</template>

<script>
// Unsaved drafts by sandbox id, kept while Vueio stays open.
const unsavedDrafts = new Map()
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { getApiErrorMessage } from '../lib/api'
import { notify } from '../utils/toasts'
import { formatActivityAbsoluteTimestamp, formatActivityRelativeTimestamp, formatLocaleDateTime } from '../utils/formatters'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { VMenu, VMenuActionList, VModal, VModalHeader } from '../components/primitives'
import SandboxCodeEditor from '../components/sandbox/SandboxCodeEditor.vue'
import SandboxDiffView from '../components/sandbox/SandboxDiffView.vue'
import SandboxFrame from '../components/sandbox/SandboxFrame.vue'
import SandboxHistoryPanel from '../components/sandbox/SandboxHistoryPanel.vue'

const MAX_PAGE_CHARS = 5 * 1024 * 1024
const POLL_MS = 30_000
const LAYOUT_KEY = 'vueio.sandbox.layout'

const router = useRouter()
const route = useRoute()
const { currentProject, currentPage } = useProjectTrackerSelectionStore()
const { canEditProject, isRestrictedMember } = useSessionAuthStore()
const { shareMode, pendingShareId } = useShareAccessContext()
const { canShareProject, shareProjectSandbox, startRenameSandbox, deleteSandbox } = useProjectWorkspaceStore()

const sandbox = computed(() => currentPage.value)
const canEdit = computed(() => !shareMode.value && canEditProject.value && !isRestrictedMember.value)
const canShare = computed(() => !shareMode.value && Boolean(canShareProject?.value))
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const saveShortcut = isMac ? '⌘S' : 'Ctrl+S'
const pasteShortcut = isMac ? '⌘V' : 'Ctrl+V'

const frameRef = ref(null)
const editorRef = ref(null)
const fileInputRef = ref(null)

// The newest page and its version.
const content = ref('')
const contentVersion = ref(0)
const versionInfo = ref(null)
const updatedAt = ref(null)
const loadState = ref('loading')
const loadError = ref('')
const liveNotice = ref('')

// Editing
const editing = ref(false)
const draft = ref('')
const draftOrigin = ref('')
const draftBase = ref(0)
const message = ref('')
const saving = ref(false)
const reviewing = ref(false)
const previewHtml = ref('')
// The layout the person chose last. Reviewing a pasted or uploaded page
// shows only the page, without changing that choice.
const savedLayout = () => (['code', 'split', 'preview'].includes(localStorage.getItem(LAYOUT_KEY)) ? localStorage.getItem(LAYOUT_KEY) : 'split')
const layout = ref(savedLayout())
const conflict = ref(null)

// History
const historyOpen = ref(false)
const viewing = ref(null)
const comparing = ref(false)

// The sandbox on screen. Navigation clears currentPage before this view
// closes, so the id is kept here for its unsaved draft.
let openId = null

const menuOpen = ref(false)
const agentPromptOpen = ref(false)
const promptCopied = ref(false)
const dropActive = ref(false)

const hasPage = computed(() => loadState.value === 'ready' && content.value.trim().length > 0)
const dirty = computed(() => editing.value && draft.value !== draftOrigin.value)

const layoutOptions = [
  { value: 'code', label: 'Code', icon: '#icon-code', title: 'Show only the code' },
  { value: 'split', label: 'Split', icon: '#icon-compare', title: 'Show the code and the page' },
  { value: 'preview', label: 'Page', icon: '#icon-eye', title: 'Show only the page' },
]

const statusLabel = computed(() => {
  if (loadState.value !== 'ready') return ''
  if (!contentVersion.value) return 'Blank page'
  const when = formatActivityRelativeTimestamp(updatedAt.value)
  if (shareMode.value) return [currentProject.value?.title, `Updated ${when}`].filter(Boolean).join(' · ')
  const info = versionInfo.value
  const who = info?.author_name ? ` by ${info.author_name}${info.agent_name ? ` with ${info.agent_name}` : ''}` : ''
  return `Version ${contentVersion.value} · Saved ${when}${who}`
})
const statusTitle = computed(() => (updatedAt.value ? formatActivityAbsoluteTimestamp(updatedAt.value) : ''))
const viewingLabel = computed(() => {
  const info = viewing.value?.info
  if (!info) return ''
  const when = formatLocaleDateTime(info.created_at, { unit: 'seconds', options: { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' } })
  return [when, info.author_name && `by ${info.author_name}`, info.message].filter(Boolean).join(' · ')
})

const fileName = computed(() => `${sandbox.value?.slug || 'sandbox'}${viewing.value ? `-v${viewing.value.number}` : ''}.html`)

const menuAction = run => () => {
  menuOpen.value = false
  run()
}
const menuActions = computed(() => [
  { label: 'Edit details', icon: '#icon-edit', show: canEdit.value, run: menuAction(() => startRenameSandbox(sandbox.value)) },
  { label: 'Upload an HTML file', icon: '#icon-upload', show: canEdit.value, run: menuAction(chooseFile) },
  { label: 'Copy prompt for an AI agent', icon: '#icon-sparkles', show: canEdit.value, run: menuAction(copyAgentPrompt) },
  { label: 'Download HTML', icon: '#icon-download', show: hasPage.value || Boolean(viewing.value), run: menuAction(downloadHtml) },
  { divider: true },
  { label: 'Delete sandbox', icon: '#icon-trash', danger: true, show: canEdit.value, run: menuAction(() => deleteSandbox(sandbox.value)) },
])

const starterPage = computed(() => `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeText(sandbox.value?.name || 'Sandbox')}</title>
  <style>
    body { margin: 0; padding: 48px; font-family: system-ui, sans-serif; color: #18181b; background: #fafafa; }
    h1 { margin: 0 0 8px; font-size: 32px; }
  </style>
</head>
<body>
  <h1>${escapeText(sandbox.value?.name || 'Sandbox')}</h1>
  <p>Start building here.</p>
</body>
</html>
`)

const agentPrompt = computed(() => [
  `Build a web page for the Vue Sandbox "${sandbox.value?.name}" in the Vueio project "${currentProject.value?.title}".`,
  'Make it one complete HTML file, with its CSS and JavaScript inside. It can load libraries, such as a chart library, from a CDN. Make it look polished.',
  `Save it with the Vueio sandbox_save tool, with project_id "${currentProject.value?.id}" and sandbox_ref "${sandbox.value?.id}". Give each save a short message.`,
  '',
  'The page should show:',
  '',
].join('\n'))

function escapeText(text) {
  return String(text).replace(/[&<>"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[character])
}

// ─── Loading and live updates ─────────────────────────────

async function fetchSandbox({ version = null, limit = MAX_PAGE_CHARS } = {}) {
  if (shareMode.value) {
    const { data } = await api.get(`/api/projects/shared/${encodeURIComponent(pendingShareId.value)}/sandbox`, { params: { limit } })
    return data
  }
  const { data } = await api.get(
    `/api/projects/${currentProject.value.id}/sandboxes/${encodeURIComponent(openId)}`,
    { params: { limit, ...(version ? { version } : {}) } },
  )
  return data
}

function applyLatest(data) {
  content.value = data.content || ''
  contentVersion.value = data.latest_version || 0
  versionInfo.value = data.version || null
  updatedAt.value = data.version?.created_at || data.updated_at || null
  if (!shareMode.value && currentPage.value?.id === data.id) {
    currentPage.value = {
      ...currentPage.value,
      name: data.name,
      slug: data.slug,
      description: data.description,
      latest_version: data.latest_version,
      version: data.version,
      updated_at: data.updated_at,
    }
  }
}

let loadRequest = 0
async function loadLatest({ announce = false } = {}) {
  const id = ++loadRequest
  if (!announce) loadState.value = 'loading'
  try {
    const data = await fetchSandbox()
    if (id !== loadRequest) return
    const previous = contentVersion.value
    applyLatest(data)
    loadState.value = 'ready'
    if (announce && data.latest_version > previous) flashNotice(`Updated to version ${data.latest_version}`)
  } catch (error) {
    if (id !== loadRequest || announce) return
    loadError.value = getApiErrorMessage(error, 'Could not open this page.')
    loadState.value = 'error'
  }
}

let noticeTimer = 0
function flashNotice(text) {
  liveNotice.value = text
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => { liveNotice.value = '' }, 6000)
}

// Someone, or their agent, may save while this page is open. Check now and
// then and show the newest version, keeping the reader's place.
let pollTimer = 0
let checking = false
let closed = false
async function checkForUpdates() {
  clearTimeout(pollTimer)
  if (closed || checking) return
  checking = true
  const id = openId
  try {
    if (document.visibilityState === 'visible' && !editing.value && !viewing.value && loadState.value === 'ready' && id) {
      const data = await fetchSandbox({ limit: 0 })
      if (!closed && id === openId && data.latest_version !== contentVersion.value) await loadLatest({ announce: true })
    }
  } catch {
    // A failed check changes nothing; the next one tries again.
  } finally {
    checking = false
    if (!closed) pollTimer = setTimeout(checkForUpdates, POLL_MS)
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') void checkForUpdates()
}

watch(() => sandbox.value?.id, (id, previousId) => {
  if (previousId) stashDraft(previousId)
  if (!id) return
  openId = id
  editing.value = false
  viewing.value = null
  comparing.value = false
  agentPromptOpen.value = false
  content.value = ''
  contentVersion.value = 0
  void loadLatest().then(() => {
    if (closed || sandbox.value?.id !== id) return
    if (loadState.value === 'ready') resumeDraft(id)
    clearTimeout(pollTimer)
    if (!checking) pollTimer = setTimeout(checkForUpdates, POLL_MS)
  })
}, { immediate: true })

// A rename changes the slug. Keep the address in step so a reload, or back
// and forward, still opens this sandbox.
watch(() => sandbox.value?.slug, (slug, oldSlug) => {
  if (!slug || !oldSlug || slug === oldSlug || shareMode.value) return
  if (route.name !== 'project-sandbox' || route.params.sandbox !== oldSlug) return
  void router.replace({ name: 'project-sandbox', params: { projectId: route.params.projectId, sandbox: slug } })
})

// ─── Editing ──────────────────────────────────────────────

let previewTimer = 0
watch(draft, value => {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => { previewHtml.value = value }, 300)
})

function setLayout(value) {
  layout.value = value
  localStorage.setItem(LAYOUT_KEY, value)
}

function startEditing({ text = null, layout: nextLayout = null, review = false, message: initialMessage = '' } = {}) {
  draft.value = text ?? content.value
  draftOrigin.value = text === null ? content.value : (hasPage.value ? content.value : '')
  draftBase.value = contentVersion.value
  previewHtml.value = draft.value
  message.value = initialMessage
  reviewing.value = review
  layout.value = nextLayout || savedLayout()
  viewing.value = null
  comparing.value = false
  historyOpen.value = false
  agentPromptOpen.value = false
  editing.value = true
  void nextTick(() => editorRef.value?.focus())
}

function confirmDiscard() {
  return !dirty.value || confirm('Discard your unsaved changes?')
}

function stopEditing() {
  if (!confirmDiscard()) return
  editing.value = false
  reviewing.value = false
}

async function save({ force = false } = {}) {
  if (saving.value || !canEdit.value || (!dirty.value && !force)) return
  saving.value = true
  const text = draft.value
  try {
    const { data } = await api.post(`/api/projects/${currentProject.value.id}/sandboxes/${encodeURIComponent(sandbox.value.id)}/versions`, {
      content: text,
      message: message.value.trim() || null,
      ...(force ? {} : { base_version: draftBase.value }),
    })
    applyLatest({ ...data, content: text })
    conflict.value = null
    draftOrigin.value = text
    draftBase.value = data.latest_version
    message.value = ''
    notify(data.changed ? `Saved version ${data.latest_version}` : 'This is already the current version')
    if (reviewing.value) {
      editing.value = false
      reviewing.value = false
    }
  } catch (error) {
    if (error?.response?.status === 409 && !force) {
      const latest = await fetchSandbox({ limit: 0 }).catch(() => null)
      conflict.value = { latest: latest?.latest_version || draftBase.value + 1 }
    } else {
      notify(`Failed to save: ${getApiErrorMessage(error)}`)
    }
  } finally {
    saving.value = false
  }
}

async function discardForLatest() {
  conflict.value = null
  editing.value = false
  reviewing.value = false
  await loadLatest()
}

function onKeydown(event) {
  if (editing.value && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void save()
  } else if (event.key === 'Escape' && historyOpen.value && !editing.value && !conflict.value) {
    historyOpen.value = false
  }
}

function onBeforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

// Unsaved work survives leaving the sandbox inside Vueio, such as a click in
// the sidebar: it comes back when the sandbox opens again.
function stashDraft(id = openId) {
  if (!id || !dirty.value) return
  unsavedDrafts.set(id, { text: draft.value, origin: draftOrigin.value, base: draftBase.value, message: message.value, review: reviewing.value })
}

function resumeDraft(id) {
  const saved = unsavedDrafts.get(id)
  if (!saved || !canEdit.value) return
  unsavedDrafts.delete(id)
  startEditing({ text: saved.text, review: saved.review, message: saved.message })
  draftOrigin.value = saved.origin
  draftBase.value = saved.base
  notify('Your unsaved changes are back.')
}

// ─── Files and pasting ────────────────────────────────────

function chooseFile() {
  fileInputRef.value?.click()
}

async function openFile(file) {
  if (!file) return
  if (!/\.html?$/i.test(file.name) && file.type !== 'text/html') {
    notify('Choose an HTML file, such as page.html')
    return
  }
  if (file.size > MAX_PAGE_CHARS) {
    notify('The file is larger than 5 MB. Link large images instead of putting them in the page.')
    return
  }
  if (editing.value && !confirmDiscard()) return
  startEditing({ text: await file.text(), layout: 'preview', review: true, message: `Uploaded ${file.name}`.slice(0, 200) })
}

function onFileChosen(event) {
  void openFile(event.target.files?.[0])
  event.target.value = ''
}

const isFileDrag = event => canEdit.value && Array.from(event.dataTransfer?.types || []).includes('Files')
let dragDepth = 0
function onDragEnter(event) {
  if (!isFileDrag(event)) return
  event.preventDefault()
  dragDepth += 1
  dropActive.value = true
}
function onDragOver(event) {
  if (!isFileDrag(event)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}
function onDragLeave(event) {
  if (!isFileDrag(event)) return
  dragDepth = Math.max(0, dragDepth - 1)
  if (!dragDepth) dropActive.value = false
}
function onDrop(event) {
  if (!isFileDrag(event)) return
  event.preventDefault()
  dragDepth = 0
  dropActive.value = false
  void openFile(event.dataTransfer.files?.[0])
}

// On a blank page, pasting anywhere opens the pasted page for a check.
function onPaste(event) {
  if (!canEdit.value || editing.value || hasPage.value || loadState.value !== 'ready') return
  if (event.target instanceof Element && event.target.closest('input, textarea, [contenteditable="true"]')) return
  const text = event.clipboardData?.getData('text/plain') || ''
  if (!text.trim()) return
  event.preventDefault()
  startEditing({ text, layout: 'preview', review: true, message: 'Pasted the page' })
}

// ─── History ──────────────────────────────────────────────

function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value) showCurrent()
}

function showCurrent() {
  viewing.value = null
  comparing.value = false
}

let viewRequest = 0
async function selectVersion(number) {
  if (number === contentVersion.value) {
    showCurrent()
    return
  }
  const id = ++viewRequest
  try {
    const data = await fetchSandbox({ version: number })
    if (id !== viewRequest) return
    viewing.value = { number, content: data.content || '', info: data.version }
  } catch (error) {
    notify(`Failed to open version ${number}: ${getApiErrorMessage(error)}`)
  }
}

async function restore(number) {
  if (!confirm(`Restore version ${number}? Vueio saves a copy of it as version ${contentVersion.value + 1}. No version is deleted.`)) return
  try {
    const { data } = await api.post(`/api/projects/${currentProject.value.id}/sandboxes/${encodeURIComponent(sandbox.value.id)}/versions/${number}/restore`)
    const restored = viewing.value?.number === number ? viewing.value.content : null
    showCurrent()
    if (restored === null) await loadLatest()
    else applyLatest({ ...data, content: restored })
    notify(data.changed ? `Restored version ${number} as version ${data.latest_version}` : `Version ${number} is already the current page`)
  } catch (error) {
    notify(`Failed to restore: ${getApiErrorMessage(error)}`)
  }
}

// ─── Other actions ────────────────────────────────────────

function downloadHtml() {
  const blob = new Blob([viewing.value ? viewing.value.content : content.value], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName.value })
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

let copiedTimer = 0
async function copyAgentPrompt() {
  try {
    await navigator.clipboard.writeText(agentPrompt.value)
    promptCopied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { promptCopied.value = false }, 2000)
    notify('Prompt copied. Paste it into your AI agent and add what the page should show.')
  } catch {
    agentPromptOpen.value = true
    notify('Copy the prompt from the box below.')
  }
}

function openAgentSettings() {
  void router.push({ name: 'settings', query: { tab: 'agent-keys' } })
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('paste', onPaste)
  window.addEventListener('beforeunload', onBeforeUnload)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  closed = true
  stashDraft()
  clearTimeout(pollTimer)
  clearTimeout(previewTimer)
  clearTimeout(noticeTimer)
  clearTimeout(copiedTimer)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('paste', onPaste)
  window.removeEventListener('beforeunload', onBeforeUnload)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.sbx {
  --sbx-tone: var(--v-sandbox);
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--v-bg-base);
}

/* ─── Toolbar ─── */
.sbx-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 60px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--v-divider);
  background: var(--v-surface-panel);
}

.sbx-bar-lead {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.sbx-tile {
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--sbx-tone) 17%, transparent);
  color: color-mix(in srgb, var(--sbx-tone) 86%, white);
}

.sbx-tile .icon {
  width: 16px;
  height: 16px;
}

.sbx-heading {
  min-width: 0;
}

.sbx-name {
  margin: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sbx-status {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--v-text-dim);
  font-size: 12px;
  white-space: nowrap;
}

.sbx-status > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
}

.sbx-unsaved,
.sbx-live {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 6px;
  color: color-mix(in srgb, var(--sbx-tone) 82%, white);
  font-weight: 600;
}

.sbx-unsaved-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sbx-tone);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--sbx-tone) 24%, transparent);
}

.sbx-bar-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}

.sbx-bar-actions .v-btn.is-active {
  background: color-mix(in srgb, var(--sbx-tone) 16%, transparent);
  color: var(--v-text);
}

.sbx-segmented {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  box-shadow: inset 0 0 0 1px var(--v-divider-subtle);
}

.sbx-segmented button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: calc(var(--v-radius-md) - 2px);
  background: transparent;
  color: var(--v-text-muted);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
}

.sbx-segmented button .icon {
  width: 13px;
  height: 13px;
}

.sbx-segmented button.is-active {
  background: var(--v-surface-raised);
  box-shadow: var(--v-surface-shadow-raised);
  color: var(--v-text);
}

.sbx-message {
  width: clamp(160px, 22vw, 300px);
  height: 32px;
}

.sbx-save {
  min-width: 118px;
}

/* ─── Banners ─── */
.sbx-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid color-mix(in srgb, var(--sbx-tone) 26%, transparent);
  background: color-mix(in srgb, var(--sbx-tone) 9%, var(--v-surface-panel));
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.sbx-banner > .icon {
  flex: none;
  width: 15px;
  height: 15px;
  color: color-mix(in srgb, var(--sbx-tone) 86%, white);
}

.sbx-banner p {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 2px 10px;
  min-width: 0;
  margin: 0;
}

.sbx-banner strong {
  color: var(--v-text);
}

.sbx-banner-actions {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  gap: 6px;
}

/* ─── Body ─── */
.sbx-body {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
}

.sbx-stage {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.sbx-stage > :deep(.sandbox-frame),
.sbx-stage > .sbd {
  flex: 1;
}

.sbx-history {
  flex: none;
}

.sbx-state {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.sbx-state.is-error {
  color: var(--v-danger);
}

.sbx-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid color-mix(in srgb, var(--sbx-tone) 30%, transparent);
  border-top-color: var(--sbx-tone);
  border-radius: 50%;
  animation: sbx-spin 800ms linear infinite;
}

/* ─── Editor ─── */
.sbx-editor {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
}

.sbx-editor.is-code,
.sbx-editor.is-preview {
  grid-template-columns: minmax(0, 1fr);
}

.sbx-pane {
  min-width: 0;
  min-height: 0;
}

.sbx-editor.is-split .sbx-pane.is-code {
  border-right: 1px solid var(--v-divider);
}

/* ─── Blank page ─── */
.sbx-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  overflow-y: auto;
  padding: clamp(32px, 8vh, 88px) 24px 48px;
  background:
    radial-gradient(60% 50% at 50% 0%, color-mix(in srgb, var(--sbx-tone) 10%, transparent), transparent 70%),
    var(--v-bg-base);
  text-align: center;
}

.sbx-empty-art {
  position: relative;
  width: 168px;
  height: 116px;
  margin-bottom: 26px;
}

.sbx-art-window {
  position: absolute;
  inset: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(160deg, color-mix(in srgb, var(--v-surface-raised) 92%, white), var(--v-surface-panel));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--sbx-tone) 30%, transparent),
    0 18px 40px color-mix(in srgb, var(--sbx-tone) 18%, transparent);
  animation: sbx-float 5s ease-in-out infinite;
}

.sbx-art-dots {
  display: flex;
  gap: 4px;
}

.sbx-art-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--v-text) 22%, transparent);
}

.sbx-art-line {
  height: 6px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--v-text) 14%, transparent);
}

.sbx-art-line.is-title {
  width: 58%;
  height: 8px;
  background: color-mix(in srgb, var(--sbx-tone) 70%, transparent);
}

.sbx-art-line.is-short {
  width: 40%;
}

.sbx-art-blocks {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 2px;
}

.sbx-art-blocks i {
  height: 18px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--sbx-tone) 18%, transparent);
}

.sbx-art-blocks i:nth-child(2) {
  background: color-mix(in srgb, var(--v-accent) 22%, transparent);
}

.sbx-art-spark {
  position: absolute;
  color: color-mix(in srgb, var(--sbx-tone) 90%, white);
  animation: sbx-twinkle 2.8s ease-in-out infinite;
}

.sbx-art-spark.is-one {
  top: -2px;
  right: 0;
  width: 26px;
  height: 26px;
}

.sbx-art-spark.is-two {
  bottom: 0;
  left: -2px;
  width: 17px;
  height: 17px;
  animation-delay: 1.3s;
}

.sbx-empty-title {
  margin: 0;
  color: var(--v-text);
  font-size: clamp(24px, 3vw, 30px);
  font-weight: 700;
  letter-spacing: -0.01em;
}

.sbx-empty-copy {
  max-width: 470px;
  margin: 10px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base, 14px);
  line-height: 1.55;
}

.sbx-choices {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  width: min(760px, 100%);
  margin-top: 32px;
}

.sbx-choice {
  display: grid;
  gap: 6px;
  justify-items: start;
  padding: 18px 18px 20px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 72%, transparent);
  border-radius: 14px;
  background: var(--v-surface-tint-strong, var(--v-surface-panel));
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
}

.sbx-choice:hover {
  border-color: color-mix(in srgb, var(--sbx-tone) 46%, transparent);
  background: color-mix(in srgb, var(--sbx-tone) 6%, var(--v-surface-panel));
  transform: translateY(-1px);
}

.sbx-choice.is-active {
  border-color: color-mix(in srgb, var(--sbx-tone) 60%, transparent);
  background: color-mix(in srgb, var(--sbx-tone) 10%, var(--v-surface-panel));
}

.sbx-choice-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin-bottom: 6px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--v-text) 7%, transparent);
  color: var(--v-text-secondary);
}

.sbx-choice-icon.is-agent {
  background: linear-gradient(135deg, color-mix(in srgb, var(--sbx-tone) 40%, transparent), color-mix(in srgb, var(--v-accent) 26%, transparent));
  color: white;
}

.sbx-choice-icon .icon {
  width: 17px;
  height: 17px;
}

.sbx-choice-title {
  color: var(--v-text);
  font-size: 14px;
  font-weight: 650;
}

.sbx-choice-copy {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.sbx-prompt {
  width: min(760px, 100%);
  margin-top: 14px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--sbx-tone) 34%, transparent);
  border-radius: 14px;
  background: var(--v-surface-panel);
  text-align: left;
}

.sbx-prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px 10px 16px;
  border-bottom: 1px solid var(--v-divider-subtle);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.sbx-prompt-text {
  margin: 0;
  padding: 14px 16px;
  color: var(--v-text-secondary);
  font-family: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.sbx-prompt-hint {
  margin: 0;
  padding: 0 16px 14px;
  color: var(--v-text-dim);
  font-size: var(--v-text-sm);
  line-height: 1.5;
}

.sbx-prompt-hint a {
  color: color-mix(in srgb, var(--sbx-tone) 86%, white);
}

.sbx-empty-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin: 26px 0 0;
  color: var(--v-text-dim);
  font-size: var(--v-text-sm);
}

.sbx-empty-foot kbd {
  padding: 1px 6px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--v-text) 8%, transparent);
  box-shadow: inset 0 -1px 0 color-mix(in srgb, var(--v-text) 12%, transparent);
  color: var(--v-text-secondary);
  font-family: inherit;
  font-size: 12px;
}

.sbx-link {
  padding: 0;
  border: 0;
  background: none;
  color: color-mix(in srgb, var(--sbx-tone) 86%, white);
  font: inherit;
  cursor: pointer;
}

.sbx-link:hover {
  text-decoration: underline;
}

/* ─── Drop ─── */
.sbx-drop {
  position: absolute;
  inset: 12px;
  z-index: 4;
  display: grid;
  place-items: center;
  border: 2px dashed color-mix(in srgb, var(--sbx-tone) 60%, transparent);
  border-radius: 16px;
  background: color-mix(in srgb, var(--v-bg-base) 78%, transparent);
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.sbx-drop-card {
  display: grid;
  gap: 6px;
  justify-items: center;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.sbx-drop-card .icon {
  width: 26px;
  height: 26px;
  color: var(--sbx-tone);
}

.sbx-drop-card strong {
  color: var(--v-text);
  font-size: 15px;
}

.sbx-conflict-copy {
  margin: 0;
  color: var(--v-text-secondary);
  line-height: 1.55;
}

/* ─── Motion ─── */
.sbx-fade-enter-active,
.sbx-fade-leave-active {
  transition: opacity 240ms ease;
}

.sbx-fade-enter-from,
.sbx-fade-leave-to {
  opacity: 0;
}

.sbx-reveal-enter-active,
.sbx-reveal-leave-active {
  transition: opacity 200ms ease, transform 200ms var(--v-ease-emphasized, ease);
}

.sbx-reveal-enter-from,
.sbx-reveal-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.sbx-slide-enter-active,
.sbx-slide-leave-active {
  transition: opacity 180ms ease, transform 220ms var(--v-ease-emphasized, ease);
}

.sbx-slide-enter-from,
.sbx-slide-leave-to {
  opacity: 0;
  transform: translateX(16px);
}

@keyframes sbx-spin {
  to { transform: rotate(360deg); }
}

@keyframes sbx-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

@keyframes sbx-twinkle {
  0%, 100% { opacity: 0.35; transform: scale(0.86) rotate(0deg); }
  50% { opacity: 1; transform: scale(1) rotate(12deg); }
}

@media (prefers-reduced-motion: reduce) {
  .sbx-art-window,
  .sbx-art-spark {
    animation: none;
  }
}

/* ─── Narrow screens ─── */
@media (max-width: 900px) {
  .sbx-btn-label,
  .sbx-segmented button span {
    display: none;
  }

  .sbx-message {
    width: 150px;
  }
}

@media (max-width: 640px) {
  .sbx-bar {
    flex-wrap: wrap;
    gap: 8px 12px;
    padding: 8px 10px;
  }

  .sbx-bar-actions.is-editing {
    flex-wrap: wrap;
    width: 100%;
  }

  .sbx-bar-actions.is-editing .sbx-segmented + .sbx-message + .v-btn {
    margin-left: auto;
  }

  .sbx-message {
    flex: 1 1 100%;
    order: 1;
    width: auto;
    min-width: 0;
  }

  .sbx-save {
    min-width: 0;
  }

  .sbx-editor.is-split {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  }

  .sbx-editor.is-split .sbx-pane.is-code {
    border-right: 0;
    border-bottom: 1px solid var(--v-divider);
  }

  .sbx-choices {
    grid-template-columns: minmax(0, 1fr);
  }

  .sbx-banner {
    flex-wrap: wrap;
  }

  .sbx-history {
    position: absolute;
    inset: 0;
    z-index: 5;
    width: 100%;
  }
}
</style>
