<template>
  <VModal
    :model-value="setupRequired && !shareMode"
    size="md"
    :closeable="false"
    aria-label="Create the first admin account"
  >
    <template #header>
      <VModalHeader :closeable="false">
        <div class="setup-heading">
          <div class="setup-brand" aria-hidden="true">V</div>
          <div class="v-modal-header-copy">
            <span class="v-modal-header-eyebrow">Welcome to Vueio</span>
            <h2 class="v-modal-header-title">Create your workspace</h2>
            <p class="v-modal-header-subtitle">
              Finish the one-time setup, then you’re ready to create and review projects.
            </p>
          </div>
        </div>
      </VModalHeader>
    </template>

    <section class="setup-auth v-modal-stack">
      <form id="vueio-setup-form" class="setup-form" @submit.prevent="completeSetup">
        <section v-if="tokenRequired" class="v-modal-section">
          <div class="v-modal-section-head">
            <h3 class="v-modal-section-title">Verify this installation</h3>
            <p class="v-modal-section-copy">
              Enter the one-time setup code shown by the Vueio installer.
              Lost it? Run <code>sudo vueioctl setup-token</code> on the server.
            </p>
          </div>
          <VField label="Setup code" required hint="This code stops anyone else from claiming your new server.">
            <input
              :value="form.setup_token"
              class="v-input"
              type="password"
              autocomplete="one-time-code"
              placeholder="One-time setup code"
              autofocus
              required
              @input="setSetupField('setup_token', $event.target.value)"
            />
          </VField>
        </section>

        <section class="v-modal-section">
          <div class="v-modal-section-head">
            <h3 class="v-modal-section-title">Workspace</h3>
            <p class="v-modal-section-copy">
              This name appears to your team and shared-link viewers.
            </p>
          </div>
          <VField label="Workspace name">
            <input
              :value="form.team_name"
              class="v-input"
              autocomplete="organization"
              placeholder="Your studio or team"
              @input="setSetupField('team_name', $event.target.value)"
            />
          </VField>
        </section>

        <section class="v-modal-section">
          <div class="v-modal-section-head">
            <h3 class="v-modal-section-title">Owner account</h3>
            <p class="v-modal-section-copy">
              This account has full access to Vueio. You can add other people later.
            </p>
          </div>
          <div class="setup-form-grid">
            <VField label="Username" required>
              <input
                :value="form.username"
                class="v-input"
                autocomplete="username"
                placeholder="admin"
                required
                @input="setSetupField('username', $event.target.value)"
              />
            </VField>
            <VField label="Your name" hint="Optional">
              <input
                :value="form.display_name"
                class="v-input"
                autocomplete="name"
                placeholder="How your team sees you"
                @input="setSetupField('display_name', $event.target.value)"
              />
            </VField>
            <VField label="Password" required hint="Use at least 8 characters.">
              <input
                :value="form.password"
                class="v-input"
                type="password"
                autocomplete="new-password"
                placeholder="Minimum 8 characters"
                required
                :aria-invalid="passwordValidationMessage ? 'true' : undefined"
                @input="setSetupField('password', $event.target.value)"
              />
            </VField>
            <VField label="Confirm password" required>
              <input
                :value="form.confirm"
                class="v-input"
                type="password"
                autocomplete="new-password"
                placeholder="Repeat password"
                required
                :aria-invalid="passwordValidationMessage ? 'true' : undefined"
                @input="setSetupField('confirm', $event.target.value)"
              />
            </VField>
          </div>
          <p
            v-if="passwordValidationMessage"
            class="v-field-help is-error"
            role="status"
            aria-live="polite"
          >
            {{ passwordValidationMessage }}
          </p>
        </section>
      </form>
    </section>

    <template #footer>
      <p v-if="error" class="setup-error" role="alert">{{ error }}</p>
      <button
        class="v-btn v-btn-primary v-btn-lg setup-submit"
        type="submit"
        form="vueio-setup-form"
        :disabled="submitting || !canSubmit"
      >
        {{ submitting ? 'Creating workspace…' : 'Create workspace' }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed } from 'vue'
import { VField, VModal, VModalHeader } from '../primitives'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'

const {
  setupRequired,
  setupStatus: status,
  setupSubmitting: submitting,
  setupError: error,
  setupForm: form,
  setSetupField,
  completeSetup,
} = useSessionAuthStore()
const { shareMode } = useShareAccessContext()

const tokenRequired = computed(() => status.value?.setup_token_required === true)
const passwordValidationMessage = computed(() => {
  const password = String(form.value?.password || '')
  const confirm = String(form.value?.confirm || '')
  if (password && password.length < 8) return 'Password must be at least 8 characters.'
  if (confirm && password !== confirm) return 'Passwords do not match.'
  return ''
})
const canSubmit = computed(() => (
  (!tokenRequired.value || Boolean(String(form.value?.setup_token || '').trim())) &&
  Boolean(String(form.value?.username || '').trim()) &&
  String(form.value?.password || '').length >= 8 &&
  form.value?.password === form.value?.confirm
))
</script>

<style scoped>
.setup-auth {
  max-width: 100%;
}

.setup-heading {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
}

.setup-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-md);
  background: var(--v-accent-subtle);
  color: var(--v-accent);
  font-size: var(--v-text-lg);
  font-weight: 800;
  line-height: 1;
}

.setup-form {
  display: grid;
  gap: var(--v-space-4);
}

.setup-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-3);
}

.setup-error {
  flex: 1 1 100%;
  margin: 0;
  color: var(--v-danger);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

.setup-submit {
  width: 100%;
}

@media (max-width: 640px) {
  .setup-form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
