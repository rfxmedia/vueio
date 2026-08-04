<template>
  <section class="admin-section admin-theme-manager">
    <AdminSettingsHeader
      eyebrow="Appearance"
      title="Theme"
      description="Tune nine source colors and let Vueio derive every surface, border, and interaction state."
      icon="#icon-pen"
    >
      <div v-if="updatedAt || updatedBy" class="admin-theme-meta">
          <span v-if="updatedBy">Last saved by {{ updatedBy }}</span>
          <span v-if="updatedAt && updatedBy">•</span>
          <span v-if="updatedAt">{{ updatedAtLabel }}</span>
      </div>
      <div class="admin-theme-actions">
        <button class="v-btn v-btn-secondary v-btn-sm" :disabled="loading || saving" @click="loadTheme">Reload</button>
        <button class="v-btn v-btn-secondary v-btn-sm" :disabled="saving" @click="resetTheme">Reset</button>
        <button class="v-btn v-btn-primary v-btn-sm" :disabled="saving || !hasUnsavedChanges" @click="saveTheme">
          {{ saving ? 'Saving' : 'Save Theme' }}
        </button>
      </div>
    </AdminSettingsHeader>

    <div class="admin-theme-workspace">
      <section class="admin-theme-preview v-modal-card-soft">
      <div class="admin-theme-preview-stage">
        <article class="theme-sample-row">
          <div class="theme-sample-select" aria-hidden="true"></div>
          <div class="theme-sample-thumb">
            <span>V3</span>
          </div>
          <div class="theme-sample-row-body">
            <div class="theme-sample-row-head">
              <div>
                <strong>S3</strong>
                <span>May 24 08:41 PM</span>
              </div>
              <div class="theme-sample-pills">
                <span class="theme-sample-pill warning">Review</span>
                <span class="theme-sample-pill">Alex Vue</span>
              </div>
            </div>
            <div class="theme-sample-note">
              <span>Brief</span>
              <em>No brief written yet</em>
            </div>
          </div>
        </article>

        <div class="theme-sample-grid">
          <section class="theme-sample-tray" aria-label="Notification tray preview">
            <header>
              <div>
                <strong>Activity</strong>
                <span>2 unread updates from 1 project</span>
              </div>
              <button type="button" aria-label="Refresh preview"></button>
            </header>
            <div class="theme-sample-tabs">
              <span class="active">Unread <b>2</b></span>
              <span>Read</span>
            </div>
            <div class="theme-sample-project">
              <div class="theme-sample-avatar">T</div>
              <div>
                <strong>TIME - Bebe Rexha</strong>
                <span>1 status · 1 versions</span>
              </div>
              <b>2 updates</b>
            </div>
            <ol class="theme-sample-events">
              <li>
                <i></i>
                <span>Changed S13 status to waiting review</span>
              </li>
              <li>
                <i></i>
                <span>Added version to S13 (3)</span>
              </li>
            </ol>
          </section>

          <section class="theme-sample-panel" aria-label="Settings panel preview">
            <strong>Project tools</strong>
            <div class="theme-sample-tool">
              <span>Details</span>
              <b>On</b>
            </div>
            <div class="theme-sample-control-row">
              <span class="active">Admin</span>
              <span>Team</span>
              <span>All</span>
            </div>
            <button type="button">Save Changes</button>
          </section>
        </div>
      </div>
      <div class="admin-theme-preview-caption">
        <div class="admin-theme-preview-title">Product preview</div>
        <p>
          Changes preview against real Vueio surfaces before publishing globally.
        </p>
        <p class="admin-theme-derived-note">
          Outlines are fixed brightness lifts from their surface fills. Text colors only change text.
        </p>
      </div>
      </section>

      <div class="admin-theme-control-list">
        <section
          v-for="group in THEME_COLOR_GROUPS"
          :key="group.id"
          class="admin-theme-group v-modal-card-soft"
        >
          <div class="admin-theme-group-head">
            <div class="admin-theme-group-title">{{ group.label }}</div>
            <p class="admin-theme-group-copy">{{ group.description }}</p>
          </div>

          <div class="admin-theme-grid">
            <label
              v-for="token in group.tokens"
              :key="token.cssVar"
              class="admin-theme-field"
            >
              <div class="admin-theme-field-head">
                <div class="admin-theme-field-meta">
                  <span class="admin-theme-field-label">{{ token.label }}</span>
                  <code class="admin-theme-field-var">{{ token.cssVar }}</code>
                </div>
                <button class="v-btn v-btn-quiet v-btn-sm" @click.prevent="copyColor(token.cssVar)">
                  {{ copiedKey === token.cssVar ? 'Copied' : 'Copy' }}
                </button>
              </div>

              <div class="admin-theme-field-controls">
                <input
                  :value="pickerValue(token.cssVar)"
                  type="color"
                  class="admin-theme-picker"
                  @input="updateThemeColor(token.cssVar, $event.target.value)"
                />
                <input
                  :value="themeForm[token.cssVar]"
                  class="v-input admin-theme-input"
                  spellcheck="false"
                  autocapitalize="off"
                  autocomplete="off"
                  @input="updateThemeColor(token.cssVar, $event.target.value)"
                  @blur="normalizeThemeField(token.cssVar)"
                />
              </div>
            </label>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import api, { getApiErrorMessage } from '../../lib/api'
import { formatLocaleDateTime } from '../../utils/formatters'
import { notify } from '../../utils/toasts'
import {
  THEME_COLOR_GROUPS,
  DEFAULT_THEME_COLORS,
  applyThemeColors,
  normalizeThemeColor,
  resolveThemeColors,
} from '../../utils/themeManager'

const loading = ref(false)
const saving = ref(false)
const copiedKey = ref('')
const updatedAt = ref(null)
const updatedBy = ref('')
const createThemeState = (colors = DEFAULT_THEME_COLORS) => ({ ...resolveThemeColors(colors) })
const themeForm = ref(createThemeState())
const savedTheme = ref(createThemeState())

const hasUnsavedChanges = computed(() => JSON.stringify(themeForm.value) !== JSON.stringify(savedTheme.value))
const updatedAtLabel = computed(() => {
  if (!updatedAt.value) return ''
  return formatLocaleDateTime(updatedAt.value, { unit: 'seconds' })
})

function setThemeState(payload) {
  const resolved = createThemeState(payload?.colors || {})
  themeForm.value = resolved
  savedTheme.value = { ...resolved }
  updatedAt.value = payload?.updated_at || null
  updatedBy.value = payload?.updated_by || ''
  applyThemeColors(resolved)
}

async function loadTheme() {
  loading.value = true
  try {
    const { data } = await api.get('/api/theme')
    setThemeState(data)
  } catch (error) {
    notify(`Failed to load theme: ${getApiErrorMessage(error)}`)
  } finally {
    loading.value = false
  }
}

function updateThemeColor(cssVar, value) {
  themeForm.value = {
    ...themeForm.value,
    [cssVar]: value,
  }
  const normalized = normalizeThemeColor(value)
  if (!normalized) return
  applyThemeColors({
    ...themeForm.value,
    [cssVar]: normalized,
  })
}

function normalizeThemeField(cssVar) {
  const normalized = normalizeThemeColor(themeForm.value[cssVar]) || savedTheme.value[cssVar] || DEFAULT_THEME_COLORS[cssVar]
  themeForm.value = {
    ...themeForm.value,
    [cssVar]: normalized,
  }
  applyThemeColors(themeForm.value)
}

function pickerValue(cssVar) {
  return normalizeThemeColor(themeForm.value[cssVar]) || savedTheme.value[cssVar] || DEFAULT_THEME_COLORS[cssVar]
}

async function saveTheme() {
  saving.value = true
  try {
    const resolved = resolveThemeColors(themeForm.value)
    const { data } = await api.put('/api/admin/theme', { colors: resolved })
    setThemeState(data)
  } catch (error) {
    notify(`Failed to save theme: ${getApiErrorMessage(error)}`)
  } finally {
    saving.value = false
  }
}

async function resetTheme() {
  saving.value = true
  try {
    const { data } = await api.delete('/api/admin/theme')
    setThemeState(data)
  } catch (error) {
    notify(`Failed to reset theme: ${getApiErrorMessage(error)}`)
  } finally {
    saving.value = false
  }
}

async function copyColor(cssVar) {
  await navigator.clipboard.writeText(themeForm.value[cssVar])
  copiedKey.value = cssVar
  window.setTimeout(() => {
    if (copiedKey.value === cssVar) copiedKey.value = ''
  }, 1200)
}

onMounted(loadTheme)
</script>

<style scoped>
.admin-theme-manager {
  overflow: hidden;
}

.admin-theme-meta,
.admin-theme-group-copy,
.admin-theme-preview-caption p {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

.admin-theme-meta {
  text-align: right;
  white-space: nowrap;
}

.admin-theme-meta span + span {
  margin-left: 5px;
}

.admin-theme-derived-note {
  margin-top: 6px;
}

.admin-theme-workspace {
  display: grid;
  grid-template-columns: minmax(440px, 1fr) minmax(440px, 0.92fr);
  align-items: start;
  gap: 14px;
  padding: 14px;
}

.admin-theme-control-list {
  display: grid;
  gap: 14px;
}

.admin-theme-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}

.admin-theme-preview,
.admin-theme-group {
  display: grid;
  gap: 14px;
  padding: var(--v-space-4);
  overflow: visible;
}

.admin-theme-preview {
  position: sticky;
  top: 12px;
  grid-template-columns: 1fr;
  align-items: center;
}

.admin-theme-preview-stage {
  padding: var(--v-space-4);
  border-radius: var(--v-radius-lg);
  background: var(--v-bg-base);
  border: 1px solid var(--v-border);
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  overflow: hidden;
}

.theme-sample-row {
  display: grid;
  grid-template-columns: 32px minmax(96px, 30%) minmax(0, 1fr);
  min-height: 112px;
  overflow: hidden;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  border: 1px solid var(--v-surface-border-strong);
  box-shadow: var(--v-surface-shadow-raised);
}

.theme-sample-select {
  align-self: center;
  justify-self: center;
  width: 14px;
  height: 14px;
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  border: 1px solid var(--v-control-border);
}

.theme-sample-thumb {
  position: relative;
  min-width: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 78% 28%, color-mix(in srgb, var(--v-accent) 58%, transparent), transparent 18%),
    linear-gradient(135deg, color-mix(in srgb, var(--v-info) 34%, var(--v-surface-inline)), var(--v-bg-black));
  border-left: 1px solid var(--v-surface-border-strong);
  border-right: 1px solid color-mix(in srgb, var(--v-bg-base) 72%, transparent);
}

.theme-sample-thumb span {
  position: absolute;
  top: 10px;
  left: 10px;
  min-height: 24px;
  padding: 0 9px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  background: var(--v-overlay-pill-bg);
  color: var(--v-overlay-pill-text);
  border: 1px solid var(--v-overlay-pill-border);
  font-size: var(--v-text-xs);
  font-weight: 800;
}

.theme-sample-row-body {
  min-width: 0;
  padding: 13px 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--v-space-3);
}

.theme-sample-row-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.theme-sample-row-head > div:first-child,
.theme-sample-project > div,
.theme-sample-tray header > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.theme-sample-row strong,
.theme-sample-tray strong,
.theme-sample-panel strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  line-height: 1.2;
}

.theme-sample-row span,
.theme-sample-tray span,
.theme-sample-panel span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.25;
}

.theme-sample-pills,
.theme-sample-control-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.theme-sample-pill {
  min-height: 26px;
  padding: 0 10px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  background: var(--v-surface-inset);
  border: 1px solid var(--v-control-border);
  color: var(--v-text-secondary) !important;
  font-weight: 700;
}

.theme-sample-pill.warning {
  background: color-mix(in srgb, var(--v-warning) 10%, var(--v-surface-inset));
  border-color: color-mix(in srgb, var(--v-warning) 26%, var(--v-control-border));
  color: var(--v-warning) !important;
}

.theme-sample-note {
  min-height: 30px;
  padding: 0 10px;
  border-radius: var(--v-radius-md);
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.theme-sample-note span {
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.theme-sample-note em {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.theme-sample-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(180px, 0.92fr);
  gap: var(--v-space-3);
}

.theme-sample-tray,
.theme-sample-panel {
  min-width: 0;
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  border: 1px solid var(--v-surface-border-strong);
  box-shadow: var(--v-surface-shadow-raised);
}

.theme-sample-tray {
  padding: 13px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.theme-sample-tray header,
.theme-sample-project {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.theme-sample-tray header button {
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: var(--v-bg-hover);
}

.theme-sample-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px;
  padding: 3px;
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  border: 1px solid var(--v-surface-border-soft);
  box-shadow: var(--v-surface-shadow-inset);
}

.theme-sample-tabs span {
  min-height: 26px;
  border-radius: var(--v-button-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-weight: 800;
}

.theme-sample-tabs .active {
  background: var(--v-surface-raised);
  color: var(--v-accent);
}

.theme-sample-tabs b,
.theme-sample-project > b,
.theme-sample-tool b {
  min-height: 16px;
  padding: 0 6px;
  border-radius: var(--v-radius-full);
  display: inline-flex;
  align-items: center;
  background: var(--v-accent);
  color: var(--v-bg-black);
  font-size: var(--v-text-2xs);
  font-weight: 800;
}

.theme-sample-project {
  padding: var(--v-space-2);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-inline));
}

.theme-sample-avatar {
  width: 28px;
  height: 28px;
  border-radius: var(--v-radius-md);
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--v-surface-inline-strong), var(--v-surface-inline));
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 800;
}

.theme-sample-events {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  margin: 0 0 0 13px;
  padding: 0 0 0 14px;
  border-left: 1.5px solid var(--v-accent);
  list-style: none;
}

.theme-sample-events li {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-2);
  min-height: 28px;
}

.theme-sample-events i {
  width: 14px;
  height: 14px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent) 18%, transparent);
  border: 1px solid var(--v-accent);
  box-shadow: 0 0 0 3px var(--v-surface-canvas);
}

.theme-sample-events span {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.theme-sample-panel {
  padding: 13px;
  display: flex;
  flex-direction: column;
  gap: 11px;
}

.theme-sample-tool {
  padding: 10px;
  border-radius: var(--v-radius-md);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--v-surface-raised);
  border: 1px solid var(--v-surface-border-soft);
}

.theme-sample-control-row {
  padding: 3px;
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  border: 1px solid var(--v-surface-border-soft);
}

.theme-sample-control-row span {
  flex: 1 1 0;
  min-height: 24px;
  padding: 0 9px;
  border-radius: var(--v-button-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
}

.theme-sample-control-row .active {
  background: var(--v-surface-raised);
  color: var(--v-text);
}

.theme-sample-panel button {
  min-height: 32px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: var(--v-accent);
  color: var(--v-bg-black);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-weight: 800;
}

.admin-theme-preview-title,
.admin-theme-group-title,
.admin-theme-field-label {
  color: var(--v-text);
  font-weight: 600;
}

.admin-theme-group-head {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.admin-theme-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-3);
}

.admin-theme-field {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--v-space-3);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-inline);
  border: 1px solid var(--v-control-border);
}

.admin-theme-field-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.admin-theme-field-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.admin-theme-field-var {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.3;
}

.admin-theme-field-controls {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.admin-theme-picker {
  width: 48px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: transparent;
  cursor: pointer;
}

.admin-theme-picker::-webkit-color-swatch-wrapper {
  padding: 5px;
}

.admin-theme-picker::-webkit-color-swatch,
.admin-theme-picker::-moz-color-swatch {
  border: 0;
  border-radius: var(--v-radius-md);
}

.admin-theme-input {
  font-family: var(--v-font);
  text-transform: uppercase;
}

@media (max-width: 1120px) {
  .admin-theme-workspace {
    grid-template-columns: 1fr;
  }

  .admin-theme-preview {
    position: static;
    grid-template-columns: minmax(0, 1.2fr) minmax(220px, 0.8fr);
  }
}

@media (max-width: 980px) {
  .admin-theme-preview {
    grid-template-columns: 1fr;
  }

  .theme-sample-grid {
    grid-template-columns: 1fr;
  }

  .admin-theme-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .admin-theme-actions {
    justify-content: stretch;
  }

  .admin-theme-actions .v-btn {
    flex: 1 1 0;
  }

  .admin-theme-workspace {
    gap: 10px;
    padding: 10px;
  }

  .admin-theme-preview,
  .admin-theme-group {
    padding: 12px;
  }

  .admin-theme-preview-stage {
    padding: 14px;
  }

  .theme-sample-row {
    grid-template-columns: 28px minmax(82px, 34%) minmax(0, 1fr);
  }

  .theme-sample-row-head {
    flex-direction: column;
    gap: var(--v-space-2);
  }

  .admin-theme-field {
    padding: 11px;
  }
}
</style>
