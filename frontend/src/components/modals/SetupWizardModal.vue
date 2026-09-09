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
            <span class="v-modal-header-eyebrow">Step 1 of 2 · Workspace</span>
            <h2 class="v-modal-header-title">Create your workspace</h2>
            <p class="v-modal-header-subtitle">
              Your account belongs to this Vueio installation. Next, check your media storage.
            </p>
          </div>
        </div>
      </VModalHeader>
    </template>

    <section class="setup-auth v-modal-stack">
      <form id="vueio-setup-form" ref="setupFormElement" class="setup-form" novalidate :aria-busy="submitting" @submit.prevent="submitSetup">
        <section v-if="tokenRequired" class="v-modal-section">
          <div class="v-modal-section-head">
            <h3 class="v-modal-section-title">Verify this installation</h3>
            <p class="v-modal-section-copy">
              Paste the setup code from your terminal to connect this browser to your installation.
            </p>
          </div>
          <VField label="Setup code" required :error="fieldError('setup_token')">
            <input
              :value="form.setup_token"
              class="v-input"
              type="password"
              autocomplete="one-time-code"
              placeholder="One-time setup code"
              autofocus
              required
              :aria-invalid="fieldError('setup_token') ? 'true' : undefined"
              aria-describedby="setup-code-help"
              @blur="touched.setup_token = true"
              @input="setSetupField('setup_token', $event.target.value)"
            />
          </VField>
          <details id="setup-code-help" class="setup-code-help">
            <summary>Where do I find my code?</summary>
            <p>Copy the code under “Continue in your browser” in the terminal. If you closed it, run <code>vueioctl setup-token</code> on the computer running Vueio. Add <code>sudo</code> at the start on Linux.</p>
          </details>
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
            <VField label="Username" required :error="fieldError('username')" hint="3–48 letters, numbers, dots, dashes or underscores.">
              <input
                :value="form.username"
                class="v-input"
                autocomplete="username"
                placeholder="admin"
                required
                maxlength="48"
                :aria-invalid="fieldError('username') ? 'true' : undefined"
                @blur="touched.username = true"
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
            <VField label="Password" required :error="fieldError('password')" hint="Use at least 8 characters.">
              <input
                :value="form.password"
                class="v-input"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="new-password"
                placeholder="Minimum 8 characters"
                required
                maxlength="1024"
                :aria-invalid="fieldError('password') ? 'true' : undefined"
                @blur="touched.password = true"
                @input="setSetupField('password', $event.target.value)"
              />
            </VField>
            <VField label="Confirm password" required :error="fieldError('confirm')">
              <input
                :value="form.confirm"
                class="v-input"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="new-password"
                placeholder="Repeat password"
                required
                :aria-invalid="fieldError('confirm') ? 'true' : undefined"
                @blur="touched.confirm = true"
                @input="setSetupField('confirm', $event.target.value)"
              />
            </VField>
          </div>
          <button class="v-btn v-btn-ghost v-btn-sm" type="button" :aria-pressed="showPassword" @click="showPassword = !showPassword">
            {{ showPassword ? 'Hide passwords' : 'Show passwords' }}
          </button>
        </section>
      </form>
    </section>

    <template #footer>
      <p v-if="error" ref="errorElement" class="setup-error" role="alert" tabindex="-1">{{ error }}</p>
      <button
        class="v-btn v-btn-primary v-btn-lg setup-submit"
        type="submit"
        form="vueio-setup-form"
        :disabled="submitting"
      >
        {{ submitting ? 'Creating workspace…' : 'Continue to storage' }}
      </button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
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
const setupFormElement = ref(null)
const errorElement = ref(null)
const touched = ref({})
const attempted = ref(false)
const showPassword = ref(false)
const errors = computed(() => ({
  setup_token: tokenRequired.value && !form.value.setup_token.trim() ? 'Paste the setup code from your terminal.' : '',
  username: /^[A-Za-z0-9_.-]{3,48}$/.test(form.value.username.trim()) ? '' : 'Use 3–48 letters, numbers, dots, dashes or underscores.',
  password: form.value.password.length >= 8 ? '' : 'Use at least 8 characters.',
  confirm: !form.value.confirm ? 'Enter your password again.' : form.value.password !== form.value.confirm ? 'Passwords do not match.' : '',
}))

function fieldError(field) {
  return attempted.value || touched.value[field] ? errors.value[field] : ''
}

async function submitSetup() {
  if (submitting.value) return
  attempted.value = true
  if (Object.values(errors.value).some(Boolean)) {
    await nextTick()
    setupFormElement.value?.querySelector('[aria-invalid="true"]')?.focus()
    return
  }
  await completeSetup()
}

watch(error, async value => {
  if (!value) return
  await nextTick()
  errorElement.value?.focus()
})
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

.setup-code-help {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.5;
}

.setup-code-help summary {
  width: fit-content;
  cursor: pointer;
  color: var(--v-text-secondary);
}

.setup-code-help p {
  margin: var(--v-space-2) 0 0;
  overflow-wrap: anywhere;
}

@media (max-width: 640px) {
  .setup-form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
