<template>
  <section class="admin-section settings-stack">
    <AdminSettingsHeader
      title="Branding"
      description="Your company name, website and logo on delivery pages. A project can use its own branding instead."
      icon="#icon-briefcase"
    />

    <div class="branding-layout">
      <form class="settings-card" @submit.prevent="$emit('save-identity')">
        <div class="settings-card-head">
          <div>
            <h3>Company</h3>
            <p>Shown to clients who open a delivery page.</p>
          </div>
        </div>
        <div class="settings-card-body">
          <VField label="Company name">
            <input
              :value="identityForm.team_name"
              class="v-input"
              placeholder="Vue"
              autocomplete="organization"
              @input="$emit('update-identity-field', 'team_name', $event.target.value)"
            />
          </VField>
          <VField label="Website" hint="Optional. Clients can open this link from the delivery page.">
            <input
              :value="identityForm.website_url"
              class="v-input"
              type="url"
              placeholder="https://example.com"
              autocomplete="url"
              @input="$emit('update-identity-field', 'website_url', $event.target.value)"
            />
          </VField>
        </div>
        <div class="settings-row branding-logo-row">
          <div class="branding-logo" :class="{ 'is-empty': !identityLogoUrl }">
            <img v-if="identityLogoUrl" :src="identityLogoUrl" alt="" />
            <span v-else>{{ identityInitials }}</span>
          </div>
          <div class="settings-row-copy">
            <strong>Logo</strong>
            <span>{{ identityLogoUrl ? 'Shown at the top of delivery pages.' : 'Without a logo, delivery pages show your initials.' }}</span>
          </div>
          <div class="settings-row-control">
            <button
              v-if="identityLogoUrl"
              class="v-btn v-btn-ghost v-btn-sm"
              type="button"
              :disabled="identityLogoSaving"
              @click="$emit('remove-identity-logo')"
            >
              Remove
            </button>
            <label class="v-btn v-btn-secondary v-btn-sm" :class="{ 'is-disabled': identityLogoSaving }">
              <input type="file" hidden accept="image/*" :disabled="identityLogoSaving" @change="$emit('identity-logo-change', $event)" />
              <svg class="icon"><use href="#icon-upload" /></svg>
              <span>{{ identityLogoSaving ? 'Uploading' : identityLogoUrl ? 'Replace' : 'Upload logo' }}</span>
            </label>
          </div>
        </div>
        <div class="settings-card-foot">
          <p v-if="identityMessage" role="status">{{ identityMessage }}</p>
          <button class="v-btn v-btn-primary v-btn-sm" type="submit" :disabled="identitySaving || !identityChanged">
            {{ identitySaving ? 'Saving' : 'Save changes' }}
          </button>
        </div>
      </form>

      <aside class="settings-card branding-preview" aria-label="Delivery page preview">
        <div class="settings-card-head">
          <div>
            <h3>Preview</h3>
            <p>What clients see.</p>
          </div>
        </div>
        <div class="branding-preview-stage">
          <div class="branding-preview-mark">
            <img v-if="identityLogoUrl" :src="identityLogoUrl" alt="" />
            <span v-else>{{ previewInitials }}</span>
          </div>
          <strong>Thank you for choosing {{ previewName }}.</strong>
          <span v-if="previewWebsite" class="branding-preview-link">{{ previewWebsite }}</span>
          <div class="branding-preview-files" aria-hidden="true">
            <i></i><i></i><i></i>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { VField } from '../primitives'
import AdminSettingsHeader from './AdminSettingsHeader.vue'

const props = defineProps({
  identityForm: { type: Object, required: true },
  identityInitials: { type: String, required: true },
  identityLogoSaving: { type: Boolean, required: true },
  identityLogoUrl: { type: String, default: '' },
  identityMessage: { type: String, default: '' },
  identitySaving: { type: Boolean, required: true },
  identityTeamName: { type: String, required: true },
  identityWebsiteUrl: { type: String, default: '' },
})

defineEmits([
  'identity-logo-change',
  'remove-identity-logo',
  'save-identity',
  'update-identity-field',
])

const previewName = computed(() => props.identityForm.team_name.trim() || 'Vue')
const previewWebsite = computed(() => props.identityForm.website_url.trim())
const previewInitials = computed(() => previewName.value.split(/\s+/).slice(0, 2).map(part => part.charAt(0).toUpperCase()).join(''))
const identityChanged = computed(() => (
  props.identityForm.team_name !== props.identityTeamName
  || props.identityForm.website_url !== props.identityWebsiteUrl
))
</script>

<style scoped>
.branding-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  align-items: start;
  gap: var(--v-space-4);
}

.branding-logo-row {
  justify-content: flex-start;
  border-top: 1px solid var(--v-divider-subtle);
}

.branding-logo-row .settings-row-copy {
  flex: 1 1 auto;
}

.branding-logo,
.branding-preview-mark {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-black) 55%, transparent);
  box-shadow: inset 0 0 0 1px var(--v-control-border);
  color: var(--v-text);
  font-weight: 750;
}

.branding-logo {
  width: 56px;
  height: 40px;
  font-size: var(--v-text-sm);
}

.branding-logo.is-empty {
  box-shadow: inset 0 0 0 1px var(--v-control-border);
  color: var(--v-text-muted);
}

.branding-logo img,
.branding-preview-mark img {
  max-width: 100%;
  max-height: 100%;
  padding: 6px;
  object-fit: contain;
}

.branding-logo-row label {
  cursor: pointer;
}

.branding-logo-row label.is-disabled {
  pointer-events: none;
  opacity: 0.6;
}

.branding-preview {
  position: sticky;
  top: 16px;
  overflow: hidden;
}

.branding-preview-stage {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 28px 20px 24px;
  text-align: center;
  background:
    radial-gradient(120% 80% at 50% 0%, color-mix(in srgb, var(--v-accent) 7%, transparent), transparent 70%),
    var(--v-surface-inset);
  border-radius: 0 0 var(--v-radius-lg) var(--v-radius-lg);
}

.branding-preview-mark {
  width: 72px;
  height: 52px;
  margin-bottom: 4px;
  font-size: var(--v-text-md);
}

.branding-preview-stage strong {
  max-width: 100%;
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 650;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.branding-preview-link {
  max-width: 100%;
  overflow: hidden;
  color: var(--v-accent-hover);
  font-size: var(--v-text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.branding-preview-files {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  width: 100%;
  margin-top: 10px;
}

.branding-preview-files i {
  aspect-ratio: 16 / 10;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
}

@media (max-width: 1100px) {
  .branding-layout {
    grid-template-columns: 1fr;
  }

  .branding-preview {
    position: static;
  }
}

@media (max-width: 768px) {
  .branding-logo-row {
    display: grid;
    grid-template-columns: 56px minmax(0, 1fr);
    align-items: center;
  }

  .branding-logo-row .settings-row-control {
    grid-column: 1 / -1;
  }

  .branding-logo-row .settings-row-control .v-btn {
    flex: 1 1 auto;
    min-height: var(--v-btn-height-lg);
  }
}
</style>
