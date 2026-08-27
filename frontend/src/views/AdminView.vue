<template>
  <section class="admin-page">
    <header class="admin-page-header">
      <div class="admin-header-copy">
        <h1 class="admin-title">Settings</h1>
        <p>Manage your account, workspace, and Vueio installation.</p>
      </div>
      <div class="admin-header-overview">
        <div v-if="isAdmin" class="admin-workspace-summary" aria-label="Workspace summary">
          <span><strong>{{ users.length }}</strong> members</span>
          <span><strong>{{ activeShareCount }}</strong> active shares</span>
          <span><strong>{{ activeKeyCount }}</strong> active keys</span>
          <span
            v-if="systemHealth"
            class="admin-system-summary"
            :class="{ warn: systemHealth.cpu_percent > 80 || systemHealth.mem_percent > 85 }"
          >
            {{ systemHealth.cpu_percent }}% CPU, {{ systemHealth.mem_percent }}% memory
          </span>
        </div>
        <button
          class="v-btn v-btn-ghost v-btn-icon v-btn-sm admin-refresh"
          type="button"
          :aria-label="settingsRefreshing ? 'Refreshing settings' : 'Refresh settings'"
          :title="settingsRefreshing ? 'Refreshing settings' : 'Refresh settings'"
          :disabled="settingsRefreshing"
          @click="refreshAll"
        >
          <svg class="icon" :class="{ spinning: settingsRefreshing }"><use href="#icon-refresh"/></svg>
        </button>
      </div>
    </header>

    <div v-if="visibleAgentToken?.token" class="admin-callout">
      <div>
        <div class="admin-callout-title">{{ visibleAgentToken.title }}</div>
        <div class="admin-callout-subtitle">{{ visibleAgentToken.subtitle }}</div>
      </div>
      <div class="admin-token-row">
        <code class="admin-token">{{ visibleAgentToken.token }}</code>
        <button class="v-btn v-btn-primary v-btn-sm" @click="copyText(visibleAgentToken.token, 'Agent key copied')">Copy</button>
        <button class="v-btn v-btn-secondary v-btn-sm" @click="copyVisibleAgentSkill">Copy skill</button>
        <button class="v-btn v-btn-secondary v-btn-sm" @click="visibleAgentToken = null">Dismiss</button>
      </div>
    </div>

    <div class="admin-settings-shell">
      <aside class="admin-settings-rail" aria-label="Settings navigation">
        <nav class="admin-settings-nav">
          <section v-for="group in settingsNavGroups" :key="group.label" class="admin-nav-group">
            <h2>{{ group.label }}</h2>
            <button
              v-for="tab in group.tabs"
              :key="tab.value"
              type="button"
              class="admin-nav-item"
              :class="{ active: activeTab === tab.value }"
              :aria-current="activeTab === tab.value ? 'page' : undefined"
              @click="activeTab = tab.value"
            >
              <svg class="icon" aria-hidden="true"><use :href="tab.icon" /></svg>
              <span>
                <strong>{{ tab.label }}</strong>
                <small>{{ tab.description }}</small>
              </span>
              <svg class="icon admin-nav-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
            </button>
          </section>
        </nav>
      </aside>

      <label class="admin-mobile-nav">
        <span class="admin-mobile-nav-label">Settings section</span>
        <span class="admin-mobile-nav-control">
          <svg class="icon" aria-hidden="true"><use :href="activeSettingsTab.icon" /></svg>
          <select :value="activeTab" aria-label="Settings section" @change="activeTab = $event.target.value">
            <optgroup v-for="group in settingsNavGroups" :key="group.label" :label="group.label">
              <option v-for="tab in group.tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</option>
            </optgroup>
          </select>
          <svg class="icon admin-mobile-nav-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
        </span>
      </label>

      <main class="admin-settings-content" :class="{ 'is-wide': activeSettingsTab.wide }">

    <section v-if="activeTab === 'account'" class="admin-section account-settings-section">
      <AdminSettingsHeader
        eyebrow="Personal"
        title="Account"
        description="Review your Vueio identity and keep your sign-in credentials secure."
        icon="#icon-user"
      />

      <div class="account-settings-grid">
        <section class="account-profile-card">
          <div class="account-profile-identity">
            <div class="account-profile-avatar">{{ currentUserInitials }}</div>
            <div>
              <p class="settings-eyebrow">Signed in as</p>
              <h3>{{ currentUser?.display_name || currentUser?.username }}</h3>
              <p>@{{ currentUser?.username }}</p>
            </div>
          </div>
          <dl class="account-profile-facts">
            <div>
              <dt>Role</dt>
              <dd>{{ currentUser?.role === 'admin' ? 'Administrator' : 'Artist' }}</dd>
            </div>
            <div>
              <dt>Access</dt>
              <dd>{{ currentUser?.role === 'admin' ? 'Full workspace access' : 'Assigned workspace access' }}</dd>
            </div>
          </dl>
          <p class="account-profile-note">
            Your account identity is used for comments, approvals, activity, and agent keys.
          </p>
        </section>

        <section class="account-password-card">
          <div class="account-password-head">
            <div>
              <p class="settings-eyebrow">Security</p>
              <h3>Password</h3>
              <p>Use at least 8 characters. Your current password is required to confirm the change.</p>
            </div>
            <div class="account-password-state" :class="{ 'is-ready': canSavePassword }">
              <svg class="icon"><use :href="canSavePassword ? '#icon-check' : '#icon-lock'" /></svg>
              <span>{{ canSavePassword ? 'Ready to save' : 'Complete all fields' }}</span>
            </div>
          </div>

          <div class="account-password-fields">
            <VField label="Current password" class="account-current-password">
              <input v-model="passwordForm.current" type="password" class="v-input" autocomplete="current-password" />
            </VField>
            <VField label="New password">
              <input v-model="passwordForm.new" type="password" class="v-input" autocomplete="new-password" />
            </VField>
            <VField label="Confirm new password">
              <input v-model="passwordForm.confirm" type="password" class="v-input" autocomplete="new-password" />
            </VField>
          </div>
          <p v-if="passwordMessage" class="v-inline-note admin-note">{{ passwordMessage }}</p>
          <div class="admin-card-actions">
            <button class="v-btn v-btn-primary" :disabled="passwordSaving || !canSavePassword" @click="saveMyPassword">
              {{ passwordSaving ? 'Saving' : 'Update password' }}
            </button>
          </div>
        </section>
      </div>
    </section>

    <section v-if="activeTab === 'notifications'" class="admin-section notification-preferences-section">
      <AdminSettingsHeader
        eyebrow="Personal"
        title="Notifications"
        description="Choose which activity matters to you and where Vueio should deliver it."
        icon="#icon-bell"
      >
        <button class="v-btn v-btn-primary v-btn-sm" :disabled="notificationSaving" @click="saveNotificationPrefs">
          {{ notificationSaving ? 'Saving' : 'Save preferences' }}
        </button>
      </AdminSettingsHeader>

      <div class="notification-preferences-body">
        <section class="notification-preference-card">
          <div>
            <p class="settings-eyebrow">Delivery</p>
            <h3>Where should activity reach you?</h3>
            <p>Channels only receive activity allowed by the scope and activity choices below.</p>
          </div>
          <div class="settings-toggle-grid">
            <VSwitch
              v-for="channel in visibleNotificationChannels"
              :key="channel.value"
              v-model="notificationPrefs.channels[channel.value]"
              :label="channel.label"
              :hint="channel.hint"
            />
          </div>
          <VField v-if="isAdmin" label="Activity scope">
            <select v-model="notificationPrefs.default_scope" class="v-input">
              <option value="related_to_me">Only activity related to me</option>
              <option value="all_visible">Everything I can access</option>
            </select>
          </VField>
          <div v-else class="admin-readonly-field">
            <span>Activity scope</span>
            <strong>Only activity related to me</strong>
          </div>
          <p class="notification-control-help">
            {{ notificationPrefs.default_scope === 'all_visible'
              ? 'You will receive matching activity from every project you can access.'
              : 'You will receive matching activity when you are assigned, mentioned, or participating.' }}
          </p>
        </section>

        <section class="notification-preference-card">
          <div>
            <p class="settings-eyebrow">Activity</p>
            <h3>What should Vueio tell you about?</h3>
            <p>Follow all activity, or narrow notifications to the types you care about.</p>
          </div>
          <div class="notification-mode-toggle" role="group" aria-label="Notification activity mode">
            <button
              type="button"
              :class="{ active: notificationEventMode === 'all' }"
              :aria-pressed="notificationEventMode === 'all'"
              @click="setNotificationEventMode('all')"
            >
              All activity
            </button>
            <button
              type="button"
              :class="{ active: notificationEventMode === 'selected' }"
              :aria-pressed="notificationEventMode === 'selected'"
              @click="setNotificationEventMode('selected')"
            >
              Selected types
            </button>
          </div>
          <div v-if="notificationEventMode === 'selected'" class="settings-option-grid notification-event-grid">
            <VCheckbox
              v-for="option in notificationEventOptions"
              :key="option.value"
              :model-value="notificationPrefs.event_types.includes(option.value)"
              :label="option.label"
              :hint="option.hint"
              @update:modelValue="toggleNotificationEventType(option.value, $event)"
            />
          </div>
          <p class="notification-control-help">
            {{ notificationEventMode === 'all'
              ? 'All current and future activity types are included.'
              : `${notificationPrefs.event_types.length} of ${notificationEventOptions.length} activity types selected.` }}
          </p>
        </section>
        <p v-if="notificationMessage" class="v-inline-note admin-note notification-preferences-message">{{ notificationMessage }}</p>
      </div>
    </section>

    <AdminTeamTab
      v-if="isAdmin && activeTab === 'team'"
      :current-user="currentUser"
      :identity-form="identityForm"
      :identity-initials="identityInitials"
      :identity-logo-saving="identityLogoSaving"
      :identity-logo-url="identityLogoUrl"
      :identity-message="identityMessage"
      :identity-saving="identitySaving"
      :identity-team-name="identityTeamName"
      :identity-website-url="identityWebsiteUrl"
      :users="users"
      :filtered-users="filteredUsers"
      :user-search="userSearch"
      :admin-user-count="adminUserCount"
      :artist-user-count="artistUserCount"
      :summarize-app-access="summarizeAppAccess"
      :user-initials="userInitials"
      @update:user-search="userSearch = $event"
      @update-identity-field="updateIdentityField"
      @identity-logo-change="handleIdentityLogoChange"
      @remove-identity-logo="removeIdentityLogo"
      @save-identity="saveIdentity"
      @open-create-user-modal="openCreateUserModal"
      @open-edit-user-modal="openEditUserModal"
      @delete-user="deleteUserConfirm"
    />

    <AdminAgentKeysTab
      v-if="activeTab === 'agent-keys'"
      :agent-key-scope="agentKeyScope"
      :filtered-visible-agent-keys="filteredVisibleAgentKeys"
      :format-date-label="formatDateLabel"
      :grouped-visible-agent-keys="groupedVisibleAgentKeys"
      :is-admin="isAdmin"
      :key-search="keySearch"
      :personal-key-saving="personalKeySaving"
      @update:agent-key-scope="agentKeyScope = $event"
      @update:key-search="keySearch = $event"
      @create-personal-agent-key="createPersonalAgentKey"
      @delete-unified-agent-key="deleteUnifiedAgentKeyConfirm"
      @open-create-key-modal="openCreateKeyModal"
      @open-edit-agent-key="openEditAgentKey"
      @reissue-agent-key-skill="reissueAndCopyAgentKeySkill"
      @reissue-unified-agent-key="reissueUnifiedAgentKey"
      @toggle-unified-agent-key="toggleUnifiedAgentKey"
    />

    <header v-if="isAdmin && activeTab === 'notifications'" class="settings-admin-heading">
      <p class="settings-eyebrow">Administration</p>
      <h2>External delivery</h2>
      <p>Connect Discord and review recent delivery health for the workspace.</p>
    </header>

    <details v-if="isAdmin && activeTab === 'notifications'" class="admin-section settings-disclosure discord-settings-section">
      <summary class="settings-disclosure-summary">
        <span class="settings-disclosure-icon"><svg class="icon"><use href="#icon-send" /></svg></span>
        <span class="settings-disclosure-copy">
          <strong>Discord delivery</strong>
          <span>Configure the bot and map Vueio activity to Discord channels.</span>
        </span>
        <span class="settings-disclosure-meta">
          <span class="admin-badge" :class="discordProvider.is_configured ? 'success' : 'warn'">
            {{ discordProvider.is_configured ? 'Configured' : 'Needs setup' }}
          </span>
          <span>{{ subscriptions.length }} {{ subscriptions.length === 1 ? 'channel' : 'channels' }}</span>
        </span>
        <svg class="icon settings-disclosure-chevron"><use href="#icon-chevron-down" /></svg>
      </summary>

      <div class="settings-disclosure-body discord-settings-body">
      <div class="settings-panel settings-form-panel discord-provider-panel">
        <div>
          <p class="settings-eyebrow">Discord</p>
          <h2 class="settings-title">Bot and channels</h2>
          <p class="settings-copy">Configure the bot once, then map Discord channels to Vueio users.</p>
        </div>
        <div class="settings-toggle-grid discord-status-grid">
          <div class="admin-access-stack">
            <span class="admin-state" :class="discordProvider.is_configured ? 'success' : 'danger'">
              {{ discordProvider.is_configured ? 'Token configured' : 'Token missing' }}
            </span>
            <span class="admin-access-line">{{ discordProvider.has_saved_token ? 'Saved in Vueio settings' : (discordProvider.uses_env_token ? 'Using server env token' : 'No token source') }}</span>
          </div>
          <div class="admin-access-stack">
            <span class="admin-state">Permissions {{ discordProvider.bot_permissions || 84992 }}</span>
            <span class="admin-access-line">View Channels, Send Messages, Embed Links, Read Message History</span>
          </div>
        </div>
        <div class="v-form-grid admin-form-grid">
          <VField label="Application ID">
            <input v-model="discordProviderForm.application_id" class="v-input" placeholder="1507844460061655181" />
          </VField>
          <VField label="Public base URL">
            <input v-model="discordProviderForm.public_base_url" class="v-input" placeholder="https://vue.example.com" />
          </VField>
          <VField label="Bot token">
            <div class="admin-secret-input">
              <input
                v-model="discordProviderForm.bot_token"
                class="v-input"
                :type="discordTokenVisible ? 'text' : 'password'"
                autocomplete="off"
                placeholder="Paste a new token to update"
              />
              <button
                class="v-btn v-btn-ghost v-btn-icon v-btn-sm admin-secret-toggle"
                type="button"
                :title="discordTokenVisible ? 'Hide bot token' : 'Reveal bot token'"
                :aria-label="discordTokenVisible ? 'Hide bot token' : 'Reveal bot token'"
                @click="discordTokenVisible = !discordTokenVisible"
              >
                <svg class="icon"><use :href="discordTokenVisible ? '#icon-eye-off' : '#icon-eye'" /></svg>
              </button>
            </div>
          </VField>
        </div>
        <div v-if="discordProvider.invite_url" class="admin-token-callout discord-invite-callout">
          <div>
            <strong>Invite URL</strong>
            <p class="admin-note">Use this to add the configured bot to a Discord server. Private channels still need the bot role added inside Discord.</p>
          </div>
          <a class="v-btn v-btn-secondary v-btn-sm" :href="discordProvider.invite_url" target="_blank" rel="noreferrer">Open invite</a>
        </div>
        <p v-if="discordProviderMessage" class="v-inline-note admin-note">{{ discordProviderMessage }}</p>
        <div class="admin-form-actions">
          <button class="v-btn v-btn-primary" :disabled="discordProviderSaving" @click="saveDiscordProvider">
            {{ discordProviderSaving ? 'Saving' : 'Save Discord setup' }}
          </button>
          <button
            v-if="discordProvider.has_saved_token"
            class="v-btn v-btn-danger"
            :disabled="discordProviderSaving"
            @click="clearDiscordProviderToken"
          >
            Clear Saved Token
          </button>
        </div>
      </div>

      <div class="settings-panel discord-channel-panel">
        <div class="admin-toolbar discord-channel-toolbar">
          <div>
            <strong>Discord channels</strong>
            <p class="admin-note">Map each channel to the Vueio user whose related activity should be delivered there.</p>
          </div>
          <button class="v-btn v-btn-primary v-btn-sm" @click="openCreateSubscriptionModal">
            <svg class="icon"><use href="#icon-plus" /></svg>
            New Channel
          </button>
        </div>

        <div v-if="subscriptions.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No notification channels configured.</div>
        <div v-else class="admin-list">
          <div class="v-column-header admin-list-header admin-subscription-grid">
            <span>Recipient</span>
            <span>Destination</span>
            <span>Rules</span>
            <span>Actions</span>
          </div>
          <article v-for="subscription in subscriptions" :key="subscription.id" class="admin-card subscription-card" :class="{ inactive: !subscription.is_enabled }">
            <div class="admin-card-main">
              <div class="admin-card-title-row">
                <h3 class="admin-card-title">{{ subscription.recipient_display_name }}</h3>
                <div class="admin-badge-row">
                  <span class="admin-badge" :class="subscription.is_enabled ? 'success' : 'danger'">{{ subscription.is_enabled ? 'Enabled' : 'Disabled' }}</span>
                  <span class="admin-badge">{{ subscription.provider }}</span>
                </div>
              </div>
              <div class="admin-card-subtitle">
                <span>{{ subscription.scope === 'all_visible' ? 'Everything visible' : 'Related to user' }}</span>
                <span>•</span>
                <span>{{ formatDateLabel(subscription.updated_at || subscription.created_at) }}</span>
              </div>
            </div>
            <div class="admin-access-stack">
              <span class="admin-state">#{{ subscription.destination }}</span>
              <span class="admin-access-line">{{ formatSubscriptionFilters(subscription) }}</span>
            </div>
            <div class="admin-access-stack">
              <span class="admin-state">{{ subscription.event_filters?.length ? subscription.event_filters.join(', ') : 'All activity' }}</span>
              <span class="admin-access-line">{{ subscription.project_filters?.length ? `${subscription.project_filters.length} project filters` : 'All projects' }}</span>
            </div>
            <div class="admin-card-actions">
              <button class="v-btn v-btn-ghost v-btn-sm" @click="testSubscription(subscription)">Test</button>
              <button class="v-btn v-btn-ghost v-btn-sm" @click="openEditSubscriptionModal(subscription)">Edit</button>
              <button class="v-btn v-btn-ghost v-btn-sm" @click="toggleSubscription(subscription)">{{ subscription.is_enabled ? 'Disable' : 'Enable' }}</button>
              <button class="v-btn v-btn-danger v-btn-sm" @click="deleteSubscriptionConfirm(subscription)">Delete</button>
            </div>
          </article>
        </div>
      </div>
      </div>
    </details>

    <details v-if="isAdmin && activeTab === 'notifications'" class="admin-section settings-disclosure delivery-health-section">
      <summary class="settings-disclosure-summary">
        <span class="settings-disclosure-icon"><svg class="icon"><use href="#icon-activity" /></svg></span>
        <span class="settings-disclosure-copy">
          <strong>Delivery history</strong>
          <span>Inspect recent external notification attempts and failures.</span>
        </span>
        <span class="settings-disclosure-meta">
          <span>{{ deliveries.length }} recent</span>
          <span v-if="failedDeliveryCount" class="admin-badge danger">{{ failedDeliveryCount }} failed</span>
          <span v-else class="admin-badge success">Healthy</span>
        </span>
        <svg class="icon settings-disclosure-chevron"><use href="#icon-chevron-down" /></svg>
      </summary>

      <div class="settings-disclosure-body">
        <div class="delivery-health-toolbar">
          <span>Showing {{ displayedDeliveries.length }} of {{ deliveries.length }} recent attempts</span>
          <button class="v-btn v-btn-secondary v-btn-sm" @click="loadDeliveries">Refresh</button>
        </div>

        <div v-if="deliveries.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No notification deliveries yet.</div>
        <div v-else class="admin-list">
          <div class="v-column-header admin-list-header admin-delivery-grid">
            <span>Delivery</span>
            <span>Status</span>
            <span>Details</span>
          </div>
          <article v-for="delivery in displayedDeliveries" :key="delivery.id" class="admin-card delivery-card">
            <div class="admin-card-main">
              <div class="admin-card-title-row">
                <h3 class="admin-card-title">{{ delivery.payload?.event?.summary || `Event ${delivery.tracker_event_id}` }}</h3>
                <span class="admin-badge">{{ delivery.provider }}</span>
              </div>
              <div class="admin-card-subtitle">
                <span>{{ delivery.recipient_user_id }}</span>
                <span>•</span>
                <span>{{ formatDateLabel(delivery.created_at) }}</span>
              </div>
            </div>
            <div class="admin-access-stack">
              <span class="admin-state" :class="deliveryStateClass(delivery.status)">{{ delivery.status }}</span>
              <span class="admin-access-line">{{ delivery.attempts || 0 }} attempts</span>
            </div>
            <div class="admin-access-stack">
              <span class="admin-access-line">{{ delivery.last_error || (delivery.sent_at ? `Sent ${formatDateLabel(delivery.sent_at)}` : 'Waiting for worker') }}</span>
            </div>
          </article>
        </div>
        <button
          v-if="displayedDeliveries.length < deliveries.length"
          class="v-btn v-btn-secondary admin-show-more"
          type="button"
          @click="deliveryVisibleLimit += 10"
        >
          Show 10 more
        </button>
      </div>
    </details>

    <AdminThemeManager v-if="isAdmin && activeTab === 'theme'" />

    <AdminUpdatesTab v-if="isAdmin && activeTab === 'updates'" />

    <AdminStorageTab
      v-if="isAdmin && activeTab === 'storage'"
      :transcodes-resetting="transcodesResetting"
      @reset-transcodes="resetTranscodes"
    />

    <section v-if="isAdmin && activeTab === 'downloads'" class="admin-section download-audit-section">
      <AdminSettingsHeader
        eyebrow="Audit"
        title="Download history"
        description="See who downloaded files, folders, tracker packages, and shared-link media."
        icon="#icon-download"
      >
        <div class="admin-toolbar-actions">
          <div class="v-search-shell admin-search-wrap">
            <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
            <input v-model="downloadSearch" class="v-search-input admin-search-input" placeholder="Search downloads..." />
          </div>
          <button class="v-btn v-btn-secondary v-btn-sm" :disabled="downloadEventsLoading" @click="loadDownloadEvents">
            {{ downloadEventsLoading ? 'Refreshing' : 'Refresh' }}
          </button>
        </div>
      </AdminSettingsHeader>

      <div class="download-audit-summary">
        <div class="download-audit-stat">
          <span class="v-eyebrow">Total loaded</span>
          <strong>{{ downloadEvents.length }}</strong>
        </div>
        <div class="download-audit-stat">
          <span class="v-eyebrow">Shared links</span>
          <strong>{{ sharedDownloadCount }}</strong>
        </div>
        <div class="download-audit-stat">
          <span class="v-eyebrow">Packages</span>
          <strong>{{ packageDownloadCount }}</strong>
        </div>
      </div>

      <div v-if="downloadEventsLoading && !downloadEvents.length" class="v-empty-state v-empty-state-compact admin-empty">Loading download history.</div>
      <div v-else-if="downloadEventsError" class="v-empty-state v-empty-state-compact admin-empty">{{ downloadEventsError }}</div>
      <div v-else-if="filteredDownloadEvents.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No downloads match your filters.</div>
      <template v-else>
        <div class="download-audit-list-head">
          <span>Showing {{ displayedDownloadEvents.length }} of {{ filteredDownloadEvents.length }} matching events</span>
          <span>History is limited to 180 days and 10,000 events.</span>
        </div>
        <div class="download-audit-list">
        <article v-for="event in displayedDownloadEvents" :key="event.id" class="download-audit-row">
          <div class="download-audit-main">
            <div class="download-audit-title-row">
              <span class="download-audit-type" :class="downloadEventClass(event)">{{ downloadEventLabel(event) }}</span>
              <h3>{{ downloadEventTitle(event) }}</h3>
            </div>
            <div class="download-audit-meta">
              <span>{{ event.user_name || 'Unknown downloader' }}</span>
              <span>{{ formatDateLabel(event.created_at) }}</span>
              <span>{{ event.source === 'share' ? `Share ${event.share_id || 'link'}` : (event.auth_mode || 'session') }}</span>
            </div>
          </div>

          <div class="download-audit-signal">
            <span class="v-eyebrow">Source</span>
            <strong>{{ event.source === 'share' ? 'Shared link' : 'Team' }}</strong>
            <span>{{ event.share_id || event.auth_mode || 'session' }}</span>
          </div>

          <div class="download-audit-signal">
            <span class="v-eyebrow">Transfer</span>
            <strong>{{ formatSizeBytes(event.size_bytes, { zeroLabel: 'Size unknown', compact: true }) }}</strong>
            <span>{{ event.status || 'started' }}</span>
          </div>

          <details class="download-audit-details">
            <summary>Details</summary>
            <div class="download-detail-grid">
              <div><span class="v-eyebrow">Event ID</span><code>{{ event.id }}</code></div>
              <div><span class="v-eyebrow">Project</span><code>{{ event.project_id || 'none' }}</code></div>
              <div><span class="v-eyebrow">Tracker</span><code>{{ event.tracker_id || 'none' }}</code></div>
              <div><span class="v-eyebrow">Filename</span><code>{{ event.filename || 'none' }}</code></div>
              <div><span class="v-eyebrow">Bytes</span><code>{{ formatSizeBytes(event.size_bytes, { zeroLabel: 'unknown', compact: true }) }}</code></div>
              <div><span class="v-eyebrow">Resource</span><code>{{ event.resource_type || 'unknown' }}</code></div>
              <div><span class="v-eyebrow">Share</span><code>{{ event.share_id || 'none' }}</code></div>
              <div class="download-detail-wide"><span class="v-eyebrow">Context</span><code>{{ compactJson(event.metadata) }}</code></div>
            </div>
          </details>
        </article>
        </div>
        <button
          v-if="displayedDownloadEvents.length < filteredDownloadEvents.length"
          class="v-btn v-btn-secondary admin-show-more"
          type="button"
          @click="downloadVisibleLimit += 15"
        >
          Show 15 more
        </button>
      </template>
    </section>

    <section v-if="isAdmin && activeTab === 'shares'" class="admin-section share-settings-section">
      <AdminSettingsHeader
        eyebrow="Access"
        title="Shared links"
        description="Find, update, revoke, or permanently remove every client-facing link from one place."
        icon="#icon-share"
      />
      <div class="admin-toolbar">
        <div class="v-search-shell admin-search-wrap">
          <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
          <input v-model="shareSearch" class="v-search-input admin-search-input" placeholder="Search links..." />
        </div>
        <div class="admin-filter-row">
          <button class="v-chip admin-chip" :class="{ active: shareStatusFilter === 'all' }" @click="shareStatusFilter = 'all'">All</button>
          <button class="v-chip admin-chip" :class="{ active: shareStatusFilter === 'active' }" @click="shareStatusFilter = 'active'">Active</button>
          <button class="v-chip admin-chip" :class="{ active: shareStatusFilter === 'expired' }" @click="shareStatusFilter = 'expired'">Expired</button>
          <button class="v-chip admin-chip" :class="{ active: shareStatusFilter === 'inactive' }" @click="shareStatusFilter = 'inactive'">Revoked</button>
        </div>
        <span class="share-filter-count">{{ filteredShares.length }} links in {{ groupedShares.length }} groups</span>
      </div>

      <div v-if="filteredShares.length === 0" class="v-empty-state v-empty-state-compact admin-empty">No shares match your filters.</div>
      <div v-else class="share-project-list">
        <details
          v-for="group in displayedShareGroups"
          :key="group.key"
          class="share-project-group"
          :open="Boolean(shareSearch.trim())"
        >
          <summary class="share-project-header">
            <div class="share-project-identity">
              <div class="share-project-thumb" :class="{ 'is-empty': !group.thumbnailUrl }">
                <img v-if="group.thumbnailUrl" :src="group.thumbnailUrl" :alt="group.title" @error="hideBrokenShareThumbnail" />
                <span v-else>{{ group.initials }}</span>
              </div>
              <div class="share-project-heading">
                <div class="v-eyebrow share-project-kicker">{{ group.subtitle }}</div>
                <h3>{{ group.title }}</h3>
                <p>{{ group.summary }}</p>
              </div>
            </div>
            <div class="share-project-counts">
              <span class="share-count-pill is-active">{{ group.activeCount }} active</span>
              <span v-if="group.expiredCount" class="share-count-pill is-expired">{{ group.expiredCount }} expired</span>
              <span v-if="group.revokedCount" class="share-count-pill is-revoked">{{ group.revokedCount }} revoked</span>
              <svg class="icon share-project-chevron"><use href="#icon-chevron-down" /></svg>
            </div>
          </summary>

          <ol class="share-item-list">
            <li v-for="share in group.shares" :key="share.id" class="share-item" :class="{ 'is-disabled': !share.is_active || isShareExpired(share) }">
              <div class="share-item-main">
                <div class="share-item-title-row">
                  <h4>{{ shareDisplayName(share) }}</h4>
                  <span class="share-status-pill" :class="shareStateClass(share)">{{ shareStateLabel(share) }}</span>
                </div>
                <div class="share-item-meta">
                  <span>{{ share.created_by || 'Unknown creator' }}</span>
                  <span>{{ formatDateLabel(share.created_at) }}</span>
                  <span>{{ share.access_count || 0 }} views</span>
                  <span>ID {{ share.id }}</span>
                </div>
              </div>
              <div class="share-item-access">
                <span>{{ formatShareAccess(share) }}</span>
                <span v-if="share.expires_at">Expires {{ formatDateLabel(share.expires_at) }}</span>
                <span v-else>No expiration</span>
              </div>
              <div class="share-item-actions">
                <button class="v-btn v-btn-ghost v-btn-sm" @click="copyShareToClipboard(share)">Copy link</button>
                <button class="v-btn v-btn-ghost v-btn-sm" @click="openShareEditor(share)">Edit</button>
                <VMenu
                  :open="shareActionMenuOpen === share.id"
                  align="end"
                  :min-width="190"
                  teleport
                  @update:open="shareActionMenuOpen = $event ? share.id : ''"
                >
                  <template #trigger="{ triggerProps }">
                    <VOverflowButton
                      v-bind="triggerProps"
                      :active="shareActionMenuOpen === share.id"
                      :label="`More actions for ${shareDisplayName(share)}`"
                      @click="shareActionMenuOpen = shareActionMenuOpen === share.id ? '' : share.id"
                    />
                  </template>
                  <VMenuActionList :actions="shareMenuActions(share)" />
                </VMenu>
              </div>
            </li>
          </ol>
        </details>
      </div>
      <button
        v-if="displayedShareGroups.length < groupedShares.length"
        class="v-btn v-btn-secondary admin-show-more"
        type="button"
        @click="shareGroupVisibleLimit += 12"
      >
        Show 12 more groups
      </button>
    </section>
      </main>
    </div>

    <VModal :modelValue="!!editingShare" size="md" @update:modelValue="closeShareEditor">
      <template #header>
        <VModalHeader title="Edit shared link" @close="closeShareEditor" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="Expiration" hint="Leave blank to keep the link available until it is revoked.">
          <input v-model="shareEditForm.expiresDate" type="date" class="v-input" />
        </VField>
        <VField label="Password" hint="Leave blank to remove password protection.">
          <input v-model="shareEditForm.password" type="password" class="v-input" placeholder="Leave blank to remove" />
        </VField>
        <VSwitch v-model="shareEditForm.allowDownload" label="Allow downloads" hint="Viewers can save the shared files to their device." />
        <VSwitch
          v-if="editingShare?.share_type === 'folder'"
          v-model="shareEditForm.allowUpload"
          label="Allow file uploads"
          hint="Viewers can add files to the shared folder."
        />
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeShareEditor">Cancel</button>
        <button class="v-btn v-btn-primary" @click="saveShareEdit">Save</button>
      </template>
    </VModal>

    <VModal :modelValue="showUserModal" size="md" @update:modelValue="closeUserModal">
      <template #header>
        <VModalHeader :title="editingUser ? 'Edit team member' : 'Add team member'" @close="closeUserModal" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="Username" hint="Used to sign in. A username cannot be changed later." :required="!editingUser">
          <input v-model="userForm.username" class="v-input" :disabled="!!editingUser" />
        </VField>
        <VField label="Display name" hint="Shown on comments, approvals, and activity.">
          <input v-model="userForm.display_name" class="v-input" />
        </VField>
        <VField
          :label="editingUser ? 'New password' : 'Password'"
          :hint="editingUser ? 'Leave blank to keep the current password.' : 'Use at least 8 characters.'"
          :required="!editingUser"
        >
          <input v-model="userForm.password" type="password" class="v-input" :placeholder="editingUser ? 'Leave blank to keep current' : 'Required'" />
        </VField>
        <VField label="Role" hint="Administrators control the entire workspace. Artists receive explicit access.">
          <select v-if="canEditUserRole" v-model="userForm.role" class="v-input">
            <option value="artist">Artist</option>
            <option value="admin">Admin</option>
          </select>
          <div v-else class="admin-readonly-field">
            <span>Legacy role</span>
            <strong>{{ userForm.role }}</strong>
          </div>
        </VField>

        <div v-if="userForm.role === 'artist'" class="v-subsection admin-subsection">
          <div class="v-section-label v-section-label--ruled">App access</div>
          <VCheckbox
            :model-value="userForm.app_access.project_manager"
            label="Projects"
            hint="Enter the Projects area and assigned Horizons projects"
            @update:modelValue="userForm.app_access.project_manager = $event"
          />
          <VCheckbox
            :model-value="userForm.app_access.file_browser"
            label="Files"
            hint="Browse shared storage through Vueio"
            @update:modelValue="userForm.app_access.file_browser = $event"
          />
        </div>

        <div v-if="userForm.role === 'artist'" class="v-subsection admin-subsection">
          <div class="v-section-label v-section-label--ruled">Horizons access model</div>
          <p class="v-inline-note admin-note">
            Project permissions are assigned per project in Horizons. The switches above only control which main areas this account can enter.
          </p>
        </div>
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeUserModal">Cancel</button>
        <button class="v-btn v-btn-primary" @click="saveUser">{{ editingUser ? 'Save changes' : 'Add member' }}</button>
      </template>
    </VModal>

    <VModal :modelValue="showKeyModal" size="md" @update:modelValue="closeKeyModal">
      <template #header>
        <VModalHeader :title="editingKey ? 'Edit agent key' : 'New managed agent key'" @close="closeKeyModal" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="Label" hint="Use a name that identifies the agent or automation using this key.">
          <input v-model="keyForm.name" class="v-input" placeholder="Agent key" />
        </VField>
        <p class="v-inline-note admin-note">{{ keyModalNote }}</p>
        <VSwitch v-if="editingKey" v-model="keyForm.is_active" label="Key is active" />
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeKeyModal">Cancel</button>
        <button class="v-btn v-btn-primary" @click="saveAgentKey">{{ editingKey ? 'Save changes' : 'Create key' }}</button>
      </template>
    </VModal>

    <VModal :modelValue="showSubscriptionModal" size="md" @update:modelValue="closeSubscriptionModal">
      <template #header>
        <VModalHeader :title="editingSubscription ? 'Edit Discord channel' : 'Connect Discord channel'" @close="closeSubscriptionModal" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="Recipient" hint="Vueio evaluates visibility and preferences as this person.">
          <select v-model="subscriptionForm.recipient_user_id" class="v-input">
            <option value="" disabled>Select a user</option>
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.display_name }} (@{{ user.username }})</option>
          </select>
        </VField>
        <VField label="Discord channel ID" hint="Copy the numeric channel ID from Discord developer mode.">
          <input v-model="subscriptionForm.destination" class="v-input" placeholder="123456789012345678" />
        </VField>
        <VField label="Scope" hint="Controls how broadly activity is selected before filters are applied.">
          <select v-model="subscriptionForm.scope" class="v-input">
            <option value="related_to_me">Related to recipient</option>
            <option value="all_visible">Everything recipient can access</option>
          </select>
        </VField>
        <VSwitch v-model="subscriptionForm.is_enabled" label="Channel is enabled" hint="Pause delivery without deleting this mapping." />
        <VSwitch v-model="subscriptionForm.config.mention_everyone" label="Mention @everyone" hint="Add an @everyone mention to every delivered message." />
        <div class="v-subsection admin-subsection">
          <div class="v-section-label v-section-label--ruled">Activity filters</div>
          <div class="settings-option-grid">
            <VCheckbox
              v-for="option in notificationEventOptions"
              :key="`sub-${option.value}`"
              :model-value="subscriptionForm.event_filters.includes(option.value)"
              :label="option.label"
              @update:modelValue="toggleSubscriptionEventFilter(option.value, $event)"
            />
          </div>
          <p class="v-inline-note admin-note">No filters means the channel receives every matching event allowed by the recipient scope and preferences.</p>
        </div>
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeSubscriptionModal">Cancel</button>
        <button class="v-btn v-btn-primary" :disabled="subscriptionSaving" @click="saveSubscription">
          {{ subscriptionSaving ? 'Saving' : 'Save channel' }}
        </button>
      </template>
    </VModal>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { getApiErrorMessage } from '../lib/api'
import {
  VCheckbox,
  VField,
  VMenu,
  VMenuActionList,
  VModal,
  VModalHeader,
  VOverflowButton,
  VSwitch,
} from '../components/primitives'
import AdminSettingsHeader from '../components/admin/AdminSettingsHeader.vue'
import { formatDateMMDDYYYYFromEpoch as formatDateLabel, formatSizeBytes } from '../utils/formatters'
import { notify } from '../utils/toasts'
import { buildVueioAgentSkill, resolveVueioApiBaseUrl } from '../utils/vueioAgentSkill'
import { useAppIdentityStore } from '../ownership/appIdentity'
import { useSessionAuthStore } from '../ownership/sessionAuth'

const AdminAgentKeysTab = defineAsyncComponent(() => import('../components/admin/AdminAgentKeysTab.vue'))
const AdminStorageTab = defineAsyncComponent(() => import('../components/admin/AdminStorageTab.vue'))
const AdminTeamTab = defineAsyncComponent(() => import('../components/admin/AdminTeamTab.vue'))
const AdminThemeManager = defineAsyncComponent(() => import('../components/admin/AdminThemeManager.vue'))
const AdminUpdatesTab = defineAsyncComponent(() => import('../components/admin/AdminUpdatesTab.vue'))

const route = useRoute()
const router = useRouter()
const { currentUser } = useSessionAuthStore()
const { identity: appIdentity, update: updateAppIdentity } = useAppIdentityStore()
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const userTabs = [
  { value: 'account', label: 'Account', description: 'Identity and password', icon: '#icon-user' },
  { value: 'notifications', label: 'Notifications', description: 'Delivery and activity', icon: '#icon-bell', wide: true },
  { value: 'agent-keys', label: 'Agent keys', description: 'Agent access and rotation', icon: '#icon-zap', wide: true },
]
const adminOnlyTabs = [
  { value: 'team', label: 'Team', description: 'Identity and members', icon: '#icon-users', wide: true },
  { value: 'shares', label: 'Shared links', description: 'Client-facing access', icon: '#icon-share', wide: true },
  { value: 'theme', label: 'Theme', description: 'Workspace appearance', icon: '#icon-pen', wide: true },
  { value: 'storage', label: 'Storage', description: 'Previews and transcodes', icon: '#icon-package' },
  { value: 'downloads', label: 'Download history', description: 'Transfer activity', icon: '#icon-download', wide: true },
  { value: 'updates', label: 'Updates', description: 'Version and releases', icon: '#icon-refresh' },
]
const activeTab = ref('account')
const systemHealth = ref(null)
const settingsRefreshing = ref(false)
const transcodesResetting = ref(false)
const adminTabs = computed(() => isAdmin.value ? [...userTabs, ...adminOnlyTabs] : userTabs)
const settingsNavGroups = computed(() => [
  { label: 'Personal', tabs: userTabs },
  ...(isAdmin.value
    ? [
        { label: 'Workspace', tabs: adminOnlyTabs.slice(0, 3) },
        { label: 'System', tabs: adminOnlyTabs.slice(3) },
      ]
    : []),
])
const activeSettingsTab = computed(() => (
  adminTabs.value.find(tab => tab.value === activeTab.value) || userTabs[0]
))

const defaultNotificationPrefs = () => ({
  default_scope: currentUser.value?.role === 'admin' ? 'all_visible' : 'related_to_me',
  event_types: [],
  channels: {
    in_app: true,
    discord: true,
    email: false,
    telegram: false,
    whatsapp: false,
  },
})
const notificationEventOptions = [
  { value: 'comments', label: 'Comments', hint: 'New comments, replies, and mentions' },
  { value: 'status', label: 'Status', hint: 'Shot and project status changes' },
  { value: 'assignments', label: 'Assignments', hint: 'People assigned or reassigned' },
  { value: 'versions', label: 'Versions', hint: 'New media versions and uploads' },
  { value: 'downloads', label: 'Downloads', hint: 'File and package download activity' },
  { value: 'updates', label: 'General updates', hint: 'Other project and tracker changes' },
]
const visibleNotificationChannels = [
  { value: 'in_app', label: 'In-app bell', hint: 'Keep activity in Vueio’s notification tray' },
  { value: 'discord', label: 'Discord', hint: 'Send matching activity to your mapped channel' },
]
const notificationPrefs = ref(defaultNotificationPrefs())
const notificationSaving = ref(false)
const notificationMessage = ref('')

const passwordForm = ref({ current: '', new: '', confirm: '' })
const passwordSaving = ref(false)
const passwordMessage = ref('')
const identityForm = ref({ team_name: 'Vue', website_url: '' })
const identitySaving = ref(false)
const identityLogoSaving = ref(false)
const identityMessage = ref('')

const myAgentKeys = ref([])
const personalKeySaving = ref(false)

const shares = ref([])
const shareSearch = ref('')
const shareStatusFilter = ref('all')
const shareGroupVisibleLimit = ref(12)
const shareActionMenuOpen = ref('')
const editingShare = ref(null)
const shareEditForm = ref({ expiresDate: '', password: '', allowDownload: false, allowUpload: false })

const users = ref([])
const userSearch = ref('')
const showUserModal = ref(false)
const editingUser = ref(null)
const defaultUserForm = () => ({
  username: '',
  display_name: '',
  password: '',
  role: 'artist',
  app_access: { file_browser: false, project_manager: true },
})
const userForm = ref(defaultUserForm())
const canEditUserRole = computed(() => !editingUser.value || ['admin', 'artist'].includes(userForm.value.role))

const agentKeys = ref([])
const keySearch = ref('')
const agentKeyScope = ref('mine')
const showKeyModal = ref(false)
const editingKey = ref(null)
const editingKeyKind = ref('managed')
const visibleAgentToken = ref(null)
const defaultKeyForm = () => ({ name: '', is_active: true })
const keyForm = ref(defaultKeyForm())
const subscriptions = ref([])
const deliveries = ref([])
const deliveryVisibleLimit = ref(10)
const downloadEvents = ref([])
const downloadEventsLoading = ref(false)
const downloadEventsError = ref('')
const downloadSearch = ref('')
const downloadVisibleLimit = ref(15)
const defaultDiscordProvider = () => ({
  provider: 'discord',
  is_configured: false,
  has_saved_token: false,
  uses_env_token: false,
  public_base_url: '',
  application_id: '',
  bot_permissions: 84992,
  invite_url: '',
})
const discordProvider = ref(defaultDiscordProvider())
const discordProviderForm = ref({ application_id: '', public_base_url: '', bot_token: '' })
const discordTokenVisible = ref(false)
const discordProviderSaving = ref(false)
const discordProviderMessage = ref('')
const showSubscriptionModal = ref(false)
const editingSubscription = ref(null)
const subscriptionSaving = ref(false)
const defaultSubscriptionForm = () => ({
  provider: 'discord',
  recipient_user_id: '',
  destination: '',
  scope: 'related_to_me',
  project_filters: [],
  event_filters: [],
  config: { mention_everyone: false },
  is_enabled: true,
})
const subscriptionForm = ref(defaultSubscriptionForm())

const activeShareCount = computed(() => shares.value.filter(share => share.is_active && (!share.expires_at || share.expires_at >= Date.now() / 1000)).length)
const activeKeyCount = computed(() => agentKeys.value.filter(key => key.is_active).length)
const sharedDownloadCount = computed(() => downloadEvents.value.filter(event => event.source === 'share').length)
const packageDownloadCount = computed(() => downloadEvents.value.filter(event => (
  ['download_all', 'download_folder_zip', 'download_zip'].includes(event.event_type)
)).length)
const failedDeliveryCount = computed(() => deliveries.value.filter(delivery => ['failed', 'error', 'dead'].includes(String(delivery.status || '').toLowerCase())).length)
const displayedDeliveries = computed(() => deliveries.value.slice(0, deliveryVisibleLimit.value))
const notificationEventMode = computed(() => notificationPrefs.value.event_types.length ? 'selected' : 'all')
const canSavePassword = computed(() => {
  return Boolean(
    passwordForm.value.current &&
    passwordForm.value.new &&
    passwordForm.value.confirm &&
    passwordForm.value.new === passwordForm.value.confirm &&
    passwordForm.value.new.length >= 8
  )
})
const currentUserInitials = computed(() => userInitials(currentUser.value))
const identityTeamName = computed(() => appIdentity.value?.team_name || 'Vue')
const identityWebsiteUrl = computed(() => appIdentity.value?.website_url || '')
const identityLogoUrl = computed(() => appIdentity.value?.logo_url || '')
const identityInitials = computed(() => {
  const parts = identityTeamName.value.trim().split(/\s+/).slice(0, 2)
  return parts.map(part => part.charAt(0).toUpperCase()).join('') || 'V'
})
const keyModalNote = computed(() => {
  if (editingKey.value) return 'This key continues to inherit its owner’s current Vueio permissions.'
  if (isAdmin.value) return 'This managed key acts as your current administrator identity. You can deactivate or delete it at any time.'
  return 'This key acts as your account and cannot see anything you cannot see.'
})

watch(appIdentity, (identity) => {
  identityForm.value = {
    team_name: identity?.team_name || 'Vue',
    website_url: identity?.website_url || '',
  }
}, { immediate: true, deep: true })

const filteredShares = computed(() => {
  let list = [...shares.value]
  const now = Date.now() / 1000
  if (shareStatusFilter.value === 'active') list = list.filter(share => share.is_active && (!share.expires_at || share.expires_at >= now))
  else if (shareStatusFilter.value === 'inactive') list = list.filter(share => !share.is_active)
  else if (shareStatusFilter.value === 'expired') list = list.filter(share => share.expires_at && share.expires_at < now)

  const search = shareSearch.value.trim().toLowerCase()
  if (!search) return list
  return list.filter(share => {
    const haystack = [share.id, share.target_name, share.path, share.project_id, share.project_title, share.tracker_name, share.created_by, share.share_type]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(search)
  })
})

const groupedShares = computed(() => {
  const groups = new Map()
  filteredShares.value.forEach(share => {
    const key = share.project_id || `standalone:${share.share_type || 'share'}:${share.path || 'unknown'}`
    if (!groups.has(key)) {
      groups.set(key, createShareGroup(key, share))
    }
    groups.get(key).shares.push(share)
  })

  return [...groups.values()].map(group => {
    const shares = group.shares
    const activeCount = shares.filter(share => share.is_active && !isShareExpired(share)).length
    const expiredCount = shares.filter(share => isShareExpired(share)).length
    const revokedCount = shares.filter(share => !share.is_active).length
    const viewCount = shares.reduce((total, share) => total + (share.access_count || 0), 0)
    return {
      ...group,
      activeCount,
      expiredCount,
      revokedCount,
      summary: `${shares.length} ${shares.length === 1 ? 'share' : 'shares'} · ${viewCount} ${viewCount === 1 ? 'view' : 'views'}`,
    }
  })
})
const displayedShareGroups = computed(() => groupedShares.value.slice(0, shareGroupVisibleLimit.value))

watch([shareSearch, shareStatusFilter], () => {
  shareGroupVisibleLimit.value = 12
})

function createShareGroup(key, share) {
  const projectTitle = share.project_title || inferProjectTitle(share)
  const hasProject = Boolean(share.project_id)
  const title = projectTitle || 'Standalone shares'
  return {
    key,
    title,
    subtitle: hasProject ? 'Project shares' : 'Files and legacy links',
    initials: initialsForText(title),
    thumbnailUrl: hasProject ? projectThumbnailUrl(share) : '',
    shares: [],
  }
}

const filteredUsers = computed(() => {
  const search = userSearch.value.trim().toLowerCase()
  if (!search) return users.value
  return users.value.filter(user => [user.id, user.username, user.display_name, user.role].filter(Boolean).join(' ').toLowerCase().includes(search))
})

const adminUserCount = computed(() => users.value.filter(user => user.role === 'admin').length)
const artistUserCount = computed(() => users.value.filter(user => user.role === 'artist').length)

const visibleAgentKeys = computed(() => {
  const personalRows = myAgentKeys.value.map(key => normalizeAgentKeyEntry(key, 'personal'))
  if (!isAdmin.value || agentKeyScope.value === 'mine') return personalRows

  const rows = agentKeys.value.map(key => normalizeAgentKeyEntry(key, 'managed'))
  const managedIds = new Set(rows.map(entry => entry.record.id))
  personalRows.forEach(entry => {
    if (!managedIds.has(entry.record.id)) rows.push(entry)
  })
  return rows
})

const filteredVisibleAgentKeys = computed(() => {
  const search = keySearch.value.trim().toLowerCase()
  if (!search) return visibleAgentKeys.value
  return visibleAgentKeys.value.filter(entry => {
    const key = entry.record
    return [
      key.name,
      key.user_id,
      key.user_display_name,
      key.key_prefix,
      entry.ownerLabel,
      entry.kind,
    ].filter(Boolean).join(' ').toLowerCase().includes(search)
  })
})

const groupedVisibleAgentKeys = computed(() => {
  const groups = new Map()
  filteredVisibleAgentKeys.value.forEach(entry => {
    const key = entry.isMine ? 'mine' : `owner:${entry.record.user_id || entry.ownerLabel}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        ownerLabel: entry.ownerLabel,
        subtitle: entry.isMine ? 'Your agent keys' : 'Managed owner',
        initials: initialsForText(entry.ownerLabel),
        entries: [],
      })
    }
    groups.get(key).entries.push(entry)
  })

  return [...groups.values()].map(group => {
    const activeCount = group.entries.filter(entry => entry.record.is_active).length
    const inactiveCount = group.entries.length - activeCount
    return {
      ...group,
      activeCount,
      inactiveCount,
      summary: `${group.entries.length} ${group.entries.length === 1 ? 'key' : 'keys'} · ${activeCount} active`,
    }
  })
})

const filteredDownloadEvents = computed(() => {
  const query = downloadSearch.value.trim().toLowerCase()
  if (!query) return downloadEvents.value
  return downloadEvents.value.filter(event => [
    event.user_name,
    event.user_id,
    event.filename,
    event.resource_name,
    event.project_id,
    event.tracker_id,
    event.share_id,
    event.event_type,
  ].some(value => String(value || '').toLowerCase().includes(query)))
})
const displayedDownloadEvents = computed(() => filteredDownloadEvents.value.slice(0, downloadVisibleLimit.value))

watch(downloadSearch, () => {
  downloadVisibleLimit.value = 15
})

function normalizeAgentKeyEntry(key, kind) {
  const isMine = kind === 'personal' || key.user_id === currentUser.value?.id || key.user_id === currentUser.value?.username
  const ownerLabel = isMine ? (currentUserName() || 'You') : (key.user_display_name || key.user_id || 'Unknown owner')
  return {
    key: `${kind}:${key.id}`,
    kind,
    isMine,
    ownerLabel,
    record: key,
  }
}

function summarizeAppAccess(user) {
  if (user.role === 'admin') return 'Full admin access'
  if (user.role !== 'artist') return 'Service account'
  const access = []
  if (user.app_access?.project_manager) access.push('Projects')
  if (user.app_access?.file_browser) access.push('Files')
  return access.length ? access.join(' + ') : 'No app access'
}

function userInitials(user) {
  const label = String(user?.display_name || user?.username || '?').trim()
  const parts = label.split(/\s+/).filter(Boolean).slice(0, 2)
  return (parts.length ? parts.map(part => part[0]).join('') : '?').toUpperCase()
}

function isShareExpired(share) {
  return Boolean(share.expires_at && share.expires_at < Date.now() / 1000)
}

function shareDisplayName(share) {
  return share.target_name || share.path || share.tracker_name || share.project_title || share.project_id || share.id
}

function inferProjectTitle(share) {
  const target = share.target_name || ''
  if (target.includes(' / ')) return target.split(' / ')[0]
  if (share.share_type === 'project') return target
  return ''
}

function projectThumbnailUrl(share) {
  if (!share.project_id) return ''
  const params = new URLSearchParams({ entity_type: 'project' })
  return `/api/horizons/projects/${encodeURIComponent(share.project_id)}/thumbnail/resolved?${params.toString()}`
}

function hideBrokenShareThumbnail(event) {
  event.target.style.display = 'none'
}

function initialsForText(value) {
  const words = String(value || '')
    .replace(/[^a-zA-Z0-9\s]/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!words.length) return 'S'
  return words.slice(0, 2).map(word => word[0]).join('').toUpperCase()
}

function shareStateLabel(share) {
  if (!share.is_active) return 'Revoked'
  if (isShareExpired(share)) return 'Expired'
  return 'Active'
}

function shareStateClass(share) {
  if (!share.is_active) return 'danger'
  if (isShareExpired(share)) return 'warn'
  return 'success'
}

function canDeleteShare(share) {
  return !share.is_active || isShareExpired(share)
}

function shareMenuActions(share) {
  const canRevoke = share.is_active && !isShareExpired(share)
  return [
    {
      label: canRevoke ? 'Revoke link' : 'Restore link',
      icon: canRevoke ? '#icon-lock' : '#icon-refresh',
      danger: canRevoke,
      run: () => canRevoke ? revokeShare(share) : reactivateShare(share),
    },
    { divider: true, show: canDeleteShare(share) },
    {
      label: 'Delete permanently',
      icon: '#icon-trash',
      danger: true,
      show: canDeleteShare(share),
      run: () => deleteShare(share),
    },
  ]
}

function formatShareAccess(share) {
  const parts = [share.share_type || 'share']
  if (share.has_password) parts.push('password')
  if (share.allow_download) parts.push('download')
  if (share.allow_upload) parts.push('upload')
  return parts.join(' · ')
}

function downloadEventLabel(event) {
  if (event.event_type === 'download_all') return 'Download All'
  if (event.event_type === 'download_folder_zip') return 'Folder zip'
  if (event.event_type === 'download_zip') return 'Zip'
  return 'File'
}

function downloadEventClass(event) {
  if (event.source === 'share') return 'is-share'
  if (event.event_type === 'download_all') return 'is-tracker'
  return 'is-file'
}

function downloadEventTitle(event) {
  return event.resource_name || event.filename || event.resource_id || 'Download'
}

function compactJson(value) {
  try {
    return JSON.stringify(value || {})
  } catch {
    return '{}'
  }
}

async function copyText(value, successMessage = 'Copied') {
  try {
    await navigator.clipboard.writeText(value)
    notify(successMessage)
  } catch {
    notify('Copy failed')
  }
}

function agentApiBaseUrl() {
  return resolveVueioApiBaseUrl()
}

function agentSkillIdentity(key = {}) {
  return key.user_display_name || key.user_id || currentUserName()
}

async function copyAgentSkillWithToken(key, token) {
  await copyText(buildVueioAgentSkill({
    baseUrl: agentApiBaseUrl(),
    keyName: key?.name || 'Vueio agent key',
    userName: agentSkillIdentity(key),
    token,
  }), 'Agent skill copied')
}

async function copyVisibleAgentSkill() {
  if (!visibleAgentToken.value?.token) return
  await copyAgentSkillWithToken(visibleAgentToken.value.key || {}, visibleAgentToken.value.token)
}

function buildShareUrl(share) {
  const baseUrl = window.location.origin
  if (share.share_type === 'project' || share.share_type === 'tracker') return `${baseUrl}/p/${share.id}`
  if (share.share_type === 'project-file' || share.share_type === 'project-folder') return `${baseUrl}/p/${share.id}/f`
  return `${baseUrl}/s/${share.id}`
}

function copyShareToClipboard(share) {
  copyText(buildShareUrl(share), 'Share link copied')
}

async function loadUsers() {
  const { data } = await api.get('/api/users')
  users.value = data
}

async function loadShares() {
  const { data } = await api.get('/api/admin/shares')
  shares.value = data.shares || []
}

async function loadSystemHealth() {
  const { data } = await api.get('/api/admin/system-health')
  systemHealth.value = data
}

async function resetTranscodes() {
  if (!confirm('Reset all generated transcodes? Source files will not be changed, but previews must regenerate when opened again.')) return
  transcodesResetting.value = true
  try {
    await api.delete('/api/admin/transcodes')
    notify('All transcode previews were reset.')
  } catch (error) {
    notify(getApiErrorMessage(error, 'Failed to reset transcodes.'), { tone: 'error' })
  } finally {
    transcodesResetting.value = false
  }
}

async function loadAgentKeys() {
  const { data } = await api.get('/api/admin/agent-keys')
  agentKeys.value = data.keys || []
}

async function loadMyAgentKeys() {
  const { data } = await api.get('/api/me/agent-keys')
  myAgentKeys.value = data.keys || []
}

async function reloadAgentKeys() {
  const tasks = [loadMyAgentKeys()]
  if (isAdmin.value) tasks.push(loadAgentKeys())
  await Promise.all(tasks)
}

function normalizeNotificationPrefs(data) {
  const defaults = defaultNotificationPrefs()
  return {
    default_scope: data?.default_scope || defaults.default_scope,
    event_types: Array.isArray(data?.event_types) ? data.event_types : [],
    channels: {
      ...defaults.channels,
      ...(data?.channels || {}),
    },
  }
}

async function loadNotificationPrefs() {
  const { data } = await api.get('/api/me/notification-preferences')
  notificationPrefs.value = normalizeNotificationPrefs(data)
  if (!isAdmin.value) {
    notificationPrefs.value.default_scope = 'related_to_me'
  }
}

function setNotificationEventMode(mode) {
  notificationPrefs.value.event_types = mode === 'selected'
    ? notificationEventOptions.map(option => option.value)
    : []
}

function toggleNotificationEventType(value, checked) {
  if (checked) {
    notificationPrefs.value.event_types = [...new Set([...notificationPrefs.value.event_types, value])]
    return
  }
  notificationPrefs.value.event_types = notificationPrefs.value.event_types.filter(entry => entry !== value)
}

async function saveNotificationPrefs() {
  notificationSaving.value = true
  notificationMessage.value = ''
  try {
    const payload = {
      ...notificationPrefs.value,
      default_scope: isAdmin.value ? notificationPrefs.value.default_scope : 'related_to_me',
    }
    const { data } = await api.put('/api/me/notification-preferences', payload)
    notificationPrefs.value = normalizeNotificationPrefs(data)
    notificationMessage.value = 'Notification preferences saved.'
  } catch (error) {
    notificationMessage.value = getApiErrorMessage(error, 'Failed to save notification preferences.')
  } finally {
    notificationSaving.value = false
  }
}

async function saveMyPassword() {
  passwordMessage.value = ''
  if (passwordForm.value.new !== passwordForm.value.confirm) {
    passwordMessage.value = 'Passwords do not match.'
    return
  }
  passwordSaving.value = true
  try {
    await api.put('/api/me/password', {
      current_password: passwordForm.value.current,
      new_password: passwordForm.value.new,
    })
    passwordForm.value = { current: '', new: '', confirm: '' }
    passwordMessage.value = 'Password changed.'
  } catch (error) {
    passwordMessage.value = getApiErrorMessage(error, 'Failed to change password.')
  } finally {
    passwordSaving.value = false
  }
}

function applyIdentity(identity) {
  updateAppIdentity(identity)
  identityForm.value = {
    team_name: identity?.team_name || 'Vue',
    website_url: identity?.website_url || '',
  }
}

function updateIdentityField(field, value) {
  identityForm.value = {
    ...identityForm.value,
    [field]: value,
  }
}

async function loadIdentity() {
  const { data } = await api.get('/api/identity')
  applyIdentity(data)
}

async function saveIdentity() {
  identitySaving.value = true
  identityMessage.value = ''
  try {
    const { data } = await api.put('/api/admin/identity', {
      team_name: identityForm.value.team_name,
      website_url: identityForm.value.website_url,
    })
    applyIdentity(data)
    identityMessage.value = 'Identity saved.'
  } catch (error) {
    identityMessage.value = getApiErrorMessage(error, 'Failed to save identity.')
  } finally {
    identitySaving.value = false
  }
}

async function handleIdentityLogoChange(event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  identityLogoSaving.value = true
  identityMessage.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post('/api/admin/identity/logo', formData)
    applyIdentity(data)
    identityMessage.value = 'Logo updated.'
  } catch (error) {
    identityMessage.value = getApiErrorMessage(error, 'Failed to update logo.')
  } finally {
    identityLogoSaving.value = false
    if (event?.target) event.target.value = ''
  }
}

async function removeIdentityLogo() {
  identityLogoSaving.value = true
  identityMessage.value = ''
  try {
    const { data } = await api.delete('/api/admin/identity/logo')
    applyIdentity(data)
    identityMessage.value = 'Logo removed.'
  } catch (error) {
    identityMessage.value = getApiErrorMessage(error, 'Failed to remove logo.')
  } finally {
    identityLogoSaving.value = false
  }
}

async function loadSubscriptions() {
  const { data } = await api.get('/api/admin/notification-subscriptions')
  subscriptions.value = data.subscriptions || []
}

function normalizeDiscordProvider(data) {
  return { ...defaultDiscordProvider(), ...(data || {}) }
}

async function loadDiscordProvider() {
  const { data } = await api.get('/api/admin/notification-providers/discord')
  discordProvider.value = normalizeDiscordProvider(data)
  discordProviderForm.value = {
    application_id: discordProvider.value.application_id || '',
    public_base_url: discordProvider.value.public_base_url || '',
    bot_token: '',
  }
}

async function saveDiscordProvider() {
  discordProviderSaving.value = true
  discordProviderMessage.value = ''
  try {
    const payload = {
      application_id: discordProviderForm.value.application_id.trim(),
      public_base_url: discordProviderForm.value.public_base_url.trim(),
    }
    const token = discordProviderForm.value.bot_token.trim()
    if (token) payload.bot_token = token
    const { data } = await api.put('/api/admin/notification-providers/discord', payload)
    discordProvider.value = normalizeDiscordProvider(data)
    discordProviderForm.value = {
      application_id: discordProvider.value.application_id || '',
      public_base_url: discordProvider.value.public_base_url || '',
      bot_token: '',
    }
    discordTokenVisible.value = false
    discordProviderMessage.value = 'Discord setup saved.'
  } catch (error) {
    discordProviderMessage.value = getApiErrorMessage(error, 'Failed to save Discord setup.')
  } finally {
    discordProviderSaving.value = false
  }
}

async function clearDiscordProviderToken() {
  if (!confirm('Clear the saved Discord bot token? Existing env token fallback, if any, will still be used.')) return
  discordProviderSaving.value = true
  discordProviderMessage.value = ''
  try {
    const { data } = await api.put('/api/admin/notification-providers/discord', { bot_token: '', clear_token: true })
    discordProvider.value = normalizeDiscordProvider(data)
    discordProviderForm.value.bot_token = ''
    discordTokenVisible.value = false
    discordProviderMessage.value = 'Saved Discord token cleared.'
  } catch (error) {
    discordProviderMessage.value = getApiErrorMessage(error, 'Failed to clear Discord token.')
  } finally {
    discordProviderSaving.value = false
  }
}

async function loadDeliveries() {
  const { data } = await api.get('/api/admin/notification-deliveries', { params: { limit: 100 } })
  deliveries.value = data.deliveries || []
  deliveryVisibleLimit.value = 10
}

async function loadDownloadEvents() {
  downloadEventsLoading.value = true
  downloadEventsError.value = ''
  try {
    const { data } = await api.get('/api/admin/download-events', { params: { limit: 250 } })
    downloadEvents.value = data.events || []
    downloadVisibleLimit.value = 15
  } catch (error) {
    downloadEvents.value = []
    downloadEventsError.value = error.response?.status === 404
      ? 'Download history is not available from this backend yet.'
      : (getApiErrorMessage(error, 'Failed to load download history.'))
  } finally {
    downloadEventsLoading.value = false
  }
}

async function refreshAll() {
  if (settingsRefreshing.value) return
  settingsRefreshing.value = true
  try {
    const tasks = [loadNotificationPrefs(), loadMyAgentKeys()]
    if (isAdmin.value) {
      tasks.push(loadIdentity(), loadUsers(), loadShares(), loadSystemHealth(), loadAgentKeys(), loadDiscordProvider(), loadSubscriptions(), loadDeliveries(), loadDownloadEvents())
    }
    const results = await Promise.allSettled(tasks)
    const failedCount = results.filter(result => result.status === 'rejected').length
    if (failedCount) console.warn(`[vue.io settings load] ${failedCount} request(s) failed`)
  } finally {
    settingsRefreshing.value = false
  }
}

function openShareEditor(share) {
  editingShare.value = share
  shareEditForm.value = {
    expiresDate: share.expires_at ? new Date(share.expires_at * 1000).toISOString().split('T')[0] : '',
    password: '',
    allowDownload: !!share.allow_download,
    allowUpload: !!share.allow_upload,
  }
}

function closeShareEditor() {
  editingShare.value = null
}

async function saveShareEdit() {
  if (!editingShare.value) return
  try {
    await api.put(`/api/admin/shares/${editingShare.value.id}`, {
      expires_at: shareEditForm.value.expiresDate ? (new Date(`${shareEditForm.value.expiresDate}T23:59:59`).getTime() / 1000) : 0,
      password: shareEditForm.value.password,
      allow_download: shareEditForm.value.allowDownload,
      allow_upload: editingShare.value.share_type === 'folder' ? shareEditForm.value.allowUpload : false,
    })
    closeShareEditor()
    await loadShares()
  } catch (error) {
    notify(`Failed to update share: ${getApiErrorMessage(error)}`)
  }
}

async function revokeShare(share) {
  if (!confirm(`Revoke share link for "${share.target_name || share.path || share.id}"?`)) return
  try {
    await api.put(`/api/admin/shares/${share.id}`, { is_active: false })
    await loadShares()
  } catch (error) {
    notify(`Failed to revoke share: ${getApiErrorMessage(error)}`)
  }
}

async function reactivateShare(share) {
  try {
    const payload = { is_active: true }
    if (isShareExpired(share)) {
      const thirtyDays = 30 * 24 * 60 * 60
      payload.expires_at = Math.floor(Date.now() / 1000) + thirtyDays
    }
    await api.put(`/api/admin/shares/${share.id}`, payload)
    await loadShares()
  } catch (error) {
    notify(`Failed to restore share: ${getApiErrorMessage(error)}`)
  }
}

async function deleteShare(share) {
  const label = share.target_name || share.path || share.id
  if (!confirm(`Permanently delete share link for "${label}"? This cannot be undone.`)) return
  try {
    await api.delete(`/api/admin/shares/${share.id}`)
    await loadShares()
  } catch (error) {
    notify(`Failed to delete share: ${getApiErrorMessage(error)}`)
  }
}

function openCreateUserModal() {
  editingUser.value = null
  userForm.value = defaultUserForm()
  showUserModal.value = true
}

function openEditUserModal(user) {
  editingUser.value = user
  userForm.value = {
    username: user.username,
    display_name: user.display_name,
    password: '',
    role: user.role,
    app_access: {
      file_browser: !!user.app_access?.file_browser,
      project_manager: !!user.app_access?.project_manager,
    },
  }
  showUserModal.value = true
}

function closeUserModal() {
  showUserModal.value = false
  editingUser.value = null
  userForm.value = defaultUserForm()
}

async function saveUser() {
  try {
    if (editingUser.value) {
      const payload = {
        display_name: userForm.value.display_name,
      }
      if (['admin', 'artist'].includes(userForm.value.role)) {
        payload.role = userForm.value.role
        payload.app_access = userForm.value.role === 'admin' ? null : userForm.value.app_access
      }
      if (userForm.value.password) payload.password = userForm.value.password
      await api.put(`/api/users/${editingUser.value.id}`, payload)
    } else {
      if (!userForm.value.username || !userForm.value.password) {
        notify('Username and password are required')
        return
      }
      await api.post('/api/users', {
        username: userForm.value.username,
        display_name: userForm.value.display_name || userForm.value.username,
        password: userForm.value.password,
        role: userForm.value.role,
        app_access: userForm.value.role === 'admin' ? null : userForm.value.app_access,
      })
    }
    closeUserModal()
    await loadUsers()
  } catch (error) {
    notify(`Failed to save user: ${getApiErrorMessage(error)}`)
  }
}

async function deleteUserConfirm(user) {
  if (!confirm(`Delete user "${user.display_name}"?`)) return
  try {
    await api.delete(`/api/users/${user.id}`)
    await loadUsers()
  } catch (error) {
    notify(`Failed to delete user: ${getApiErrorMessage(error)}`)
  }
}

function openCreateKeyModal() {
  editingKey.value = null
  editingKeyKind.value = 'managed'
  keyForm.value = defaultKeyForm()
  showKeyModal.value = true
}

function openEditAgentKey(entry) {
  editingKey.value = entry.record
  editingKeyKind.value = entry.kind
  keyForm.value = {
    name: entry.record.name,
    is_active: !!entry.record.is_active,
  }
  showKeyModal.value = true
}

function closeKeyModal() {
  showKeyModal.value = false
  editingKey.value = null
  editingKeyKind.value = 'managed'
  keyForm.value = defaultKeyForm()
}

async function saveAgentKey() {
  try {
    if (editingKey.value) {
      const path = editingKeyKind.value === 'personal'
        ? `/api/me/agent-keys/${editingKey.value.id}`
        : `/api/admin/agent-keys/${editingKey.value.id}`
      await api.put(path, {
        name: keyForm.value.name,
        is_active: keyForm.value.is_active,
      })
    } else {
      const { data } = await api.post('/api/admin/agent-keys', {
        name: keyForm.value.name,
      })
      visibleAgentToken.value = {
        title: 'Agent key ready',
        subtitle: 'Copy this token and hand it to the agent.',
        token: data.token || '',
        key: data.key,
      }
    }
    closeKeyModal()
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to save key: ${getApiErrorMessage(error)}`)
  }
}

async function reissueAgentKey(key) {
  if (!confirm(`Reissue agent key "${key.name}"? The old token will stop working immediately.`)) return
  try {
    const { data } = await api.post(`/api/admin/agent-keys/${key.id}/reissue`)
    visibleAgentToken.value = {
      title: `${key.name} reissued`,
      subtitle: 'This is the new live token. The previous token is now dead.',
      token: data.token || '',
      key: data.key || key,
    }
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to reissue key: ${getApiErrorMessage(error)}`)
  }
}

async function reissueAndCopyManagedAgentSkill(key) {
  if (!confirm(`Reissue agent key "${key.name}" so the skill can include a visible token? The old token will stop working immediately.`)) return
  try {
    const { data } = await api.post(`/api/admin/agent-keys/${key.id}/reissue`)
    await copyAgentSkillWithToken(data.key || key, data.token || '')
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to copy skill: ${getApiErrorMessage(error)}`)
  }
}

async function reissueUnifiedAgentKey(entry) {
  if (entry.kind === 'personal') {
    await reissuePersonalAgentKey(entry.record)
    return
  }
  await reissueAgentKey(entry.record)
}

async function reissueAndCopyAgentKeySkill(entry) {
  if (entry.kind === 'personal') {
    await reissueAndCopyPersonalAgentSkill(entry.record)
    return
  }
  await reissueAndCopyManagedAgentSkill(entry.record)
}

async function toggleUnifiedAgentKey(entry) {
  if (entry.kind === 'personal') {
    await togglePersonalAgentKey(entry.record)
    return
  }
  await toggleAgentKeyActive(entry.record)
}

async function deleteUnifiedAgentKeyConfirm(entry) {
  if (entry.kind === 'personal') {
    await deletePersonalAgentKeyConfirm(entry.record)
    return
  }
  await deleteAgentKeyConfirm(entry.record)
}

async function toggleAgentKeyActive(key) {
  try {
    await api.put(`/api/admin/agent-keys/${key.id}`, { is_active: !key.is_active })
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to update key: ${getApiErrorMessage(error)}`)
  }
}

async function deleteAgentKeyConfirm(key) {
  if (!confirm(`Delete agent key "${key.name}" permanently? This cannot be undone.`)) return
  try {
    await api.delete(`/api/admin/agent-keys/${key.id}`)
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to delete key: ${getApiErrorMessage(error)}`)
  }
}

async function createPersonalAgentKey() {
  personalKeySaving.value = true
  try {
    const { data } = await api.post('/api/me/agent-keys', {
      name: `${currentUserName()} Agent Key`,
    })
    visibleAgentToken.value = {
      title: 'Personal agent key ready',
      subtitle: 'This key acts as your account and cannot see anything you cannot see.',
      token: data.token || '',
      key: data.key,
    }
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to create personal key: ${getApiErrorMessage(error)}`)
  } finally {
    personalKeySaving.value = false
  }
}

function currentUserName() {
  return currentUser.value?.display_name || currentUser.value?.username || 'Personal'
}

async function reissuePersonalAgentKey(key) {
  if (!confirm(`Reissue personal agent key "${key.name}"? The old token will stop working immediately.`)) return
  try {
    const { data } = await api.post(`/api/me/agent-keys/${key.id}/reissue`)
    visibleAgentToken.value = {
      title: `${key.name} reissued`,
      subtitle: 'This is the new token. The previous token is now dead.',
      token: data.token || '',
      key: data.key || key,
    }
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to reissue key: ${getApiErrorMessage(error)}`)
  }
}

async function reissueAndCopyPersonalAgentSkill(key) {
  if (!confirm(`Reissue personal agent key "${key.name}" so the skill can include a visible token? The old token will stop working immediately.`)) return
  try {
    const { data } = await api.post(`/api/me/agent-keys/${key.id}/reissue`)
    await copyAgentSkillWithToken(data.key || key, data.token || '')
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to copy skill: ${getApiErrorMessage(error)}`)
  }
}

async function togglePersonalAgentKey(key) {
  try {
    await api.put(`/api/me/agent-keys/${key.id}`, { is_active: !key.is_active })
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to update key: ${getApiErrorMessage(error)}`)
  }
}

async function deletePersonalAgentKeyConfirm(key) {
  if (!confirm(`Delete personal agent key "${key.name}" permanently? This cannot be undone.`)) return
  try {
    await api.delete(`/api/me/agent-keys/${key.id}`)
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to delete key: ${getApiErrorMessage(error)}`)
  }
}

function formatSubscriptionFilters(subscription) {
  const scope = subscription.scope === 'all_visible' ? 'all visible activity' : 'related activity'
  const eventFilters = subscription.event_filters?.length ? subscription.event_filters.join(', ') : 'all types'
  return `${scope} · ${eventFilters}`
}

function deliveryStateClass(status) {
  if (status === 'sent') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'sending') return 'warn'
  return ''
}

function openCreateSubscriptionModal() {
  editingSubscription.value = null
  subscriptionForm.value = defaultSubscriptionForm()
  showSubscriptionModal.value = true
}

function openEditSubscriptionModal(subscription) {
  editingSubscription.value = subscription
  subscriptionForm.value = {
    provider: subscription.provider || 'discord',
    recipient_user_id: subscription.recipient_user_id || '',
    destination: subscription.destination || '',
    scope: subscription.scope || 'related_to_me',
    project_filters: [...(subscription.project_filters || [])],
    event_filters: [...(subscription.event_filters || [])],
    config: { mention_everyone: false, ...(subscription.config || {}) },
    is_enabled: !!subscription.is_enabled,
  }
  showSubscriptionModal.value = true
}

function closeSubscriptionModal() {
  showSubscriptionModal.value = false
  editingSubscription.value = null
  subscriptionForm.value = defaultSubscriptionForm()
}

function toggleSubscriptionEventFilter(value, checked) {
  if (checked) {
    subscriptionForm.value.event_filters = [...new Set([...subscriptionForm.value.event_filters, value])]
    return
  }
  subscriptionForm.value.event_filters = subscriptionForm.value.event_filters.filter(entry => entry !== value)
}

async function saveSubscription() {
  if (!subscriptionForm.value.recipient_user_id || !subscriptionForm.value.destination) {
    notify('Recipient and Discord channel ID are required')
    return
  }
  subscriptionSaving.value = true
  try {
    const payload = {
      ...subscriptionForm.value,
      project_filters: subscriptionForm.value.project_filters.filter(Boolean),
      event_filters: subscriptionForm.value.event_filters.filter(Boolean),
      config: {
        ...subscriptionForm.value.config,
        mention_everyone: !!subscriptionForm.value.config?.mention_everyone,
      },
    }
    if (editingSubscription.value) {
      await api.put(`/api/admin/notification-subscriptions/${editingSubscription.value.id}`, payload)
    } else {
      await api.post('/api/admin/notification-subscriptions', payload)
    }
    closeSubscriptionModal()
    await loadSubscriptions()
  } catch (error) {
    notify(`Failed to save channel: ${getApiErrorMessage(error)}`)
  } finally {
    subscriptionSaving.value = false
  }
}

async function toggleSubscription(subscription) {
  try {
    await api.put(`/api/admin/notification-subscriptions/${subscription.id}`, { is_enabled: !subscription.is_enabled })
    await loadSubscriptions()
  } catch (error) {
    notify(`Failed to update channel: ${getApiErrorMessage(error)}`)
  }
}

async function testSubscription(subscription) {
  try {
    await api.post(`/api/admin/notification-subscriptions/${subscription.id}/test`)
    notify('Test delivery sent.')
  } catch (error) {
    notify(`Test delivery failed: ${getApiErrorMessage(error)}`)
  }
}

async function deleteSubscriptionConfirm(subscription) {
  if (!confirm(`Delete Discord channel for "${subscription.recipient_display_name}"?`)) return
  try {
    await api.delete(`/api/admin/notification-subscriptions/${subscription.id}`)
    await loadSubscriptions()
  } catch (error) {
    notify(`Failed to delete channel: ${getApiErrorMessage(error)}`)
  }
}

watch(adminTabs, tabs => {
  if (activeTab.value === 'channels' || activeTab.value === 'discord' || activeTab.value === 'deliveries') {
    activeTab.value = 'notifications'
    return
  }
  if (activeTab.value === 'personal-keys' || activeTab.value === 'keys') {
    activeTab.value = 'agent-keys'
    return
  }
  if (activeTab.value === 'identity' || activeTab.value === 'users') {
    activeTab.value = 'team'
    return
  }
  if (!tabs.some(tab => tab.value === activeTab.value)) {
    activeTab.value = 'account'
  }
}, { immediate: true })

watch(() => route.query.tab, tab => {
  if (typeof tab === 'string' && adminTabs.value.some(item => item.value === tab)) {
    activeTab.value = tab
  }
}, { immediate: true })

watch(activeTab, tab => {
  const query = tab === 'account' ? {} : { tab }
  if ((route.query.tab || '') !== (query.tab || '')) {
    router.replace({ path: '/settings', query })
  }
})

onMounted(refreshAll)
</script>

<style scoped>
.admin-page {
  flex: 1;
  min-height: 0;
  padding: 24px clamp(20px, 3vw, 44px) 40px;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-6);
}

.admin-page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--v-space-6);
  width: min(100%, 1440px);
  margin-inline: auto;
  flex-shrink: 0;
}

.admin-header-copy {
  min-width: 0;
}

.admin-header-copy p {
  margin: 6px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-md);
}

.admin-title {
  margin: 0;
  color: var(--v-text);
  font-size: clamp(24px, 2.2vw, 30px);
  font-weight: 760;
  letter-spacing: -0.025em;
  line-height: 1.08;
}

.admin-header-overview {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
}

.admin-refresh .icon.spinning {
  animation: v-spin 0.8s linear infinite;
}

.admin-workspace-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px 16px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
}

.admin-workspace-summary span {
  white-space: nowrap;
}

.admin-workspace-summary strong {
  color: var(--v-text-secondary);
  font-weight: 760;
}

.admin-system-summary.warn {
  color: var(--v-warning);
}

.admin-section {
  min-width: 0;
  flex: 0 0 auto;
}

.admin-callout {
  width: min(100%, 1440px);
  margin-inline: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
  border: 1px solid color-mix(in srgb, var(--v-accent) 22%, var(--v-surface-border-soft));
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-accent) 6%, var(--v-surface-panel));
  box-shadow: var(--v-surface-shadow-raised);
}

.admin-callout-title {
  font-weight: 600;
}

.admin-callout-subtitle {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  margin-top: var(--v-space-1);
}

.admin-token-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--v-space-2);
  align-items: center;
}

.admin-token {
  flex: 1;
  min-width: 220px;
  background: var(--v-bg-field);
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  padding: 10px 12px;
  white-space: nowrap;
  overflow: auto;
}

.admin-settings-shell {
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  align-items: start;
  gap: clamp(22px, 3vw, 42px);
  width: min(100%, 1440px);
  margin-inline: auto;
}

.admin-settings-rail {
  position: sticky;
  top: 20px;
  min-width: 0;
  padding-right: var(--v-space-5);
  border-right: 1px solid var(--v-divider-subtle);
}

.admin-settings-nav {
  display: grid;
  gap: var(--v-space-5);
}

.admin-nav-group {
  display: grid;
  gap: 5px;
}

.admin-nav-group h2 {
  margin: 0 0 3px;
  padding: 0 9px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 760;
  letter-spacing: 0.12em;
  line-height: 1.2;
  text-transform: uppercase;
}

.admin-nav-item {
  position: relative;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 12px;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 50px;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  text-align: left;
  cursor: pointer;
  transition:
    background-color var(--v-duration-fast) var(--v-ease-emphasized),
    border-color var(--v-duration-fast) var(--v-ease-emphasized),
    color var(--v-duration-fast) var(--v-ease-emphasized);
}

.admin-nav-item:hover {
  border-color: color-mix(in srgb, var(--v-border) 56%, transparent);
  background: var(--v-surface-tint);
  color: var(--v-text-secondary);
}

.admin-nav-item.active {
  border-color: color-mix(in srgb, var(--v-accent) 18%, var(--v-border));
  background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-tint));
  color: var(--v-accent);
}

.admin-nav-item > .icon:first-child {
  width: 16px;
  height: 16px;
}

.admin-nav-item > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.admin-nav-item strong {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  font-weight: 720;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-nav-item.active strong {
  color: var(--v-text);
}

.admin-nav-item small {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-nav-chevron {
  width: 11px;
  height: 11px;
  opacity: 0;
  transform: translateX(-3px);
  transition:
    opacity var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.admin-nav-item.active .admin-nav-chevron {
  opacity: 0.8;
  transform: translateX(0);
}

.admin-mobile-nav {
  display: none;
}

.admin-settings-content {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
  width: min(100%, 920px);
  min-width: 0;
}

.admin-settings-content.is-wide {
  width: min(100%, 1180px);
}

.account-settings-section,
.notification-preferences-section {
  overflow: hidden;
}

.account-settings-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.62fr) minmax(520px, 1.38fr);
  gap: var(--v-space-4);
  padding-top: var(--v-space-4);
}

.account-profile-card,
.account-password-card,
.notification-preference-card {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.account-profile-card {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
}

.account-profile-identity {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
}

.account-profile-avatar {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 12%, var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 24%, transparent);
  font-size: var(--v-text-lg);
  font-weight: 800;
}

.account-profile-identity h3,
.account-password-head h3,
.notification-preference-card h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-lg);
  line-height: 1.25;
}

.account-profile-identity p:last-child,
.account-password-head p,
.notification-preference-card > div:first-child > p:last-child {
  margin: 4px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

.account-profile-facts {
  display: grid;
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  background: var(--v-divider-subtle);
}

.account-profile-facts div {
  display: grid;
  gap: 4px;
  padding: 11px 12px;
  background: var(--v-surface-well);
}

.account-profile-facts dt {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.account-profile-facts dd {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
}

.account-profile-note {
  margin: auto 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.account-password-card {
  display: grid;
  gap: var(--v-space-4);
}

.account-password-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.account-password-state {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 0 9px;
  border-radius: var(--v-button-radius);
  color: var(--v-text-muted);
  background: var(--v-surface-well);
  font-size: var(--v-text-xs);
  font-weight: 700;
}

.account-password-state.is-ready {
  color: var(--v-accent-hover);
  background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-inline));
}

.account-password-state .icon {
  width: 12px;
  height: 12px;
}

.account-password-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-3);
}

.account-current-password {
  grid-column: 1 / -1;
}

.notification-preferences-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-4);
  padding-top: var(--v-space-4);
}

.notification-preference-card {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-4);
}

.settings-toggle-grid,
.settings-option-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: var(--v-space-2);
}

.notification-preference-card .settings-toggle-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.notification-preference-card :deep(.v-switch),
.notification-event-grid :deep(.v-checkbox) {
  align-items: flex-start;
  min-height: 62px;
  padding: 11px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.notification-mode-toggle {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  box-shadow: var(--v-surface-shadow-inset);
}

.notification-mode-toggle button {
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font: 650 var(--v-text-base)/1 var(--v-font);
  cursor: pointer;
}

.notification-mode-toggle button:hover,
.notification-mode-toggle button.active {
  color: var(--v-text);
  background: var(--v-control-bg-active);
}

.notification-control-help {
  margin: auto 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.notification-preferences-message {
  grid-column: 1 / -1;
}

.settings-disclosure {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.settings-admin-heading {
  padding: var(--v-space-3) 2px 0;
}

.settings-admin-heading h2 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-xl);
  line-height: 1.25;
}

.settings-admin-heading > p:last-child {
  margin: 5px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

.settings-disclosure-summary {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto 16px;
  align-items: center;
  gap: var(--v-space-3);
  min-height: 68px;
  padding: 12px 16px;
  list-style: none;
  cursor: pointer;
  transition: background-color var(--v-transition-fast);
}

.settings-disclosure-summary::-webkit-details-marker {
  display: none;
}

.settings-disclosure-summary:hover {
  background: var(--v-surface-tint-hover);
}

.settings-disclosure-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-inline));
}

.settings-disclosure-icon .icon {
  width: 15px;
  height: 15px;
}

.settings-disclosure-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.settings-disclosure-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-md);
}

.settings-disclosure-copy > span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.settings-disclosure-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.settings-disclosure-chevron {
  width: 14px;
  height: 14px;
  color: var(--v-text-muted);
  transition: transform var(--v-transition-fast);
}

.settings-disclosure[open] .settings-disclosure-chevron {
  transform: rotate(180deg);
}

.settings-disclosure-body {
  border-top: 1px solid var(--v-divider-subtle);
}

.discord-settings-body {
  display: grid;
  gap: var(--v-space-4);
  padding: var(--v-space-4);
}

.discord-provider-panel {
  width: 100%;
  max-width: none;
}

.discord-provider-panel .admin-form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.discord-channel-panel {
  width: 100%;
  max-width: none;
  gap: 0;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-border) 62%, transparent);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-tint);
}

.discord-channel-toolbar {
  padding: 12px 14px;
}

.discord-status-grid {
  align-items: stretch;
}

.admin-secret-input {
  position: relative;
}

.admin-secret-input .v-input {
  padding-right: 42px;
}

.admin-secret-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  width: 30px;
  height: 30px;
  transform: translateY(-50%);
  color: var(--v-text-muted);
}

.admin-secret-toggle:hover {
  color: var(--v-text);
}

.discord-invite-callout,
.admin-form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  flex-wrap: wrap;
}

.discord-invite-callout {
  padding: var(--v-space-3);
  border: 1px solid color-mix(in srgb, var(--v-border) 58%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-field) 42%, transparent);
}

.admin-form-actions {
  justify-content: flex-start;
}

.admin-readonly-field {
  display: flex;
  min-height: 42px;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-field) 78%, transparent);
  padding: 0 14px;
}

.admin-readonly-field span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.admin-readonly-field strong {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
}

.admin-theme-manager {
  overflow: visible;
  flex-shrink: 0;
}

.admin-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px 10px;
}

.delivery-health-toolbar,
.download-audit-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 10px 14px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.delivery-health-toolbar {
  border-bottom: 1px solid var(--v-divider-subtle);
}

.admin-show-more {
  display: flex;
  width: calc(100% - 28px);
  margin: 0 14px 14px;
  justify-content: center;
}

.download-audit-section {
  overflow: hidden;
}

.download-audit-section :deep(.settings-view-actions) {
  flex: 1 1 420px;
}

.download-audit-section :deep(.settings-view-actions > .admin-toolbar-actions) {
  width: 100%;
}

.download-audit-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--v-space-2);
  padding: 16px 0 4px;
}

/* Recessed like every other read-only stat surface in the app, rather than
   an outlined card that reads as something you can click. */
.download-audit-stat {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-well);
  box-shadow: var(--v-surface-well-ring);
}

.download-audit-stat strong {
  color: var(--v-text);
  font-size: var(--v-text-xl);
}

.download-audit-list {
  display: grid;
  gap: var(--v-space-2);
  padding: 10px 0 14px;
}

.download-audit-list-head {
  padding-bottom: 0;
}

.download-audit-row {
  display: grid;
  grid-template-columns: minmax(260px, 1.35fr) minmax(180px, 0.72fr) minmax(180px, 0.72fr) auto;
  gap: 14px;
  align-items: center;
  padding: var(--v-space-3);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.download-audit-main,
.download-audit-signal {
  min-width: 0;
}

.download-audit-title-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-width: 0;
}

.download-audit-title-row h3 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-md);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-audit-type {
  flex: 0 0 auto;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  font-size: var(--v-text-xs);
  font-weight: 800;
}

.download-audit-type.is-share {
  color: var(--v-accent-hover);
  background: color-mix(in srgb, var(--v-accent-muted) 52%, transparent);
}

.download-audit-type.is-tracker {
  color: var(--v-info);
  background: color-mix(in srgb, var(--v-info) 14%, transparent);
}

.download-audit-type.is-file {
  color: var(--v-text-secondary);
  background: color-mix(in srgb, var(--v-bg-field) 70%, transparent);
}

.download-audit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 10px;
  margin-top: 6px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.download-audit-signal {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.download-audit-signal strong {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-audit-signal span:last-child {
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-audit-details {
  justify-self: end;
}

.download-audit-details summary {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--v-border) 54%, transparent);
  border-radius: var(--v-radius-md);
  color: var(--v-text-secondary);
  cursor: pointer;
  font-size: var(--v-text-sm);
  font-weight: 700;
  list-style: none;
}

.download-audit-details[open] {
  grid-column: 1 / -1;
  justify-self: stretch;
}

.download-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-2);
  margin-top: 10px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--v-border) 52%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-field) 42%, transparent);
}

.download-detail-grid div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.download-detail-grid code {
  overflow: hidden;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-detail-wide {
  grid-column: 1 / -1;
}

.share-project-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  gap: var(--v-space-3);
  padding: var(--v-space-4) 0;
}

.share-project-group {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.share-settings-section > .admin-toolbar {
  margin-top: var(--v-space-4);
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
  box-shadow: var(--v-surface-shadow-raised);
}

.share-project-group[open] {
  grid-column: 1 / -1;
}

.share-project-group:not([open]) .share-project-header {
  border-bottom-color: transparent;
}

.share-project-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--v-divider-subtle);
  background: var(--v-surface-tint-strong);
  list-style: none;
  cursor: pointer;
  transition: background-color var(--v-transition-fast);
}

.share-project-header::-webkit-details-marker {
  display: none;
}

.share-project-header:hover {
  background: var(--v-surface-tint-hover);
}

.share-project-identity {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v-space-3);
}

.share-project-thumb {
  width: 54px;
  height: 34px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  border: 1px solid color-mix(in srgb, var(--v-border) 62%, transparent);
  background: color-mix(in srgb, var(--v-bg-field) 72%, transparent);
  color: var(--v-accent-hover);
  font-size: var(--v-text-sm);
  font-weight: 800;
}

.share-project-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.share-project-thumb.is-empty {
  background: color-mix(in srgb, var(--v-bg-field) 86%, transparent);
}

.share-project-heading {
  min-width: 0;
}

/* Truncates rather than wraps: this sits in a fixed-height card header. */
.share-project-kicker {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-project-heading h3 {
  margin: 3px 0 0;
  color: var(--v-text);
  font-size: var(--v-text-md);
  line-height: 1.25;
}

.share-project-heading p {
  margin: 3px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.25;
}

.share-project-counts {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.share-project-chevron {
  width: 14px;
  height: 14px;
  margin-left: 3px;
  align-self: center;
  color: var(--v-text-muted);
  transition: transform var(--v-transition-fast);
}

.share-project-group[open] .share-project-chevron {
  transform: rotate(180deg);
}

.share-filter-count {
  flex: 0 0 auto;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.share-item-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  margin: 0;
  padding: 8px 10px 10px;
  list-style: none;
}

.share-item {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(150px, 0.45fr) auto;
  gap: var(--v-space-3);
  align-items: center;
  padding: 11px 14px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  transition: background-color 140ms ease, border-color 140ms ease, transform 140ms ease;
}

.share-item:hover {
  border-color: color-mix(in srgb, var(--v-border) 64%, transparent);
  background: var(--v-surface-tint-hover);
}

.share-item.is-disabled {
  background: transparent;
}

.share-item-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2);
}

.share-item-title-row h4 {
  min-width: 0;
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  line-height: 1.3;
}

.share-item-meta,
.share-item-access {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 8px;
  margin-top: 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.35;
}

.share-item-meta span:not(:last-child)::after {
  content: '·';
  margin-left: var(--v-space-2);
  color: color-mix(in srgb, var(--v-text-muted) 58%, transparent);
}

.share-item-access {
  margin-top: 0;
  flex-direction: column;
  gap: 3px;
}

.share-item-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 7px;
}

.admin-list-header {
  display: grid;
  gap: 14px;
  padding: 2px 4px 7px;
}

.admin-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px 14px;
  padding: 12px 14px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-md);
  background: transparent;
  transition: background-color 140ms ease, border-color 140ms ease;
}

.admin-subscription-grid,
.subscription-card {
  grid-template-columns: minmax(190px, 1fr) minmax(180px, 0.8fr) minmax(170px, 0.8fr) minmax(260px, auto);
}

.admin-delivery-grid,
.delivery-card {
  grid-template-columns: minmax(240px, 1fr) minmax(120px, 0.4fr) minmax(240px, 0.9fr);
}

.admin-card:hover {
  border-color: color-mix(in srgb, var(--v-border) 58%, transparent);
  background: var(--v-surface-tint-hover);
}

.admin-card-main {
  min-width: 0;
}

.admin-card-title-row {
  display: flex;
  gap: var(--v-space-2);
  justify-content: flex-start;
  align-items: flex-start;
  flex-wrap: wrap;
}

.admin-card-title {
  margin: 0;
  font-size: var(--v-text-md);
  line-height: 1.3;
  color: var(--v-text);
}

.admin-card-subtitle {
  margin-top: var(--v-space-1);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.admin-access-stack {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  min-width: 0;
  align-self: center;
}

.admin-state {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 700;
}

.admin-state.success {
  color: var(--v-accent-hover);
}

.admin-state.warn {
  color: var(--v-warning);
}

.admin-state.danger {
  color: var(--v-danger-text);
}

.admin-access-line {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.admin-subsection {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: var(--v-space-3);
  border: 1px solid color-mix(in srgb, var(--v-border) 54%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-field) 28%, transparent);
}

@media (max-width: 1000px) {
  .account-settings-grid,
  .notification-preferences-body {
    grid-template-columns: 1fr;
  }

  .discord-provider-panel .admin-form-grid {
    grid-template-columns: 1fr;
  }

  .share-project-list {
    grid-template-columns: 1fr;
  }

  .share-project-group[open] {
    grid-column: auto;
  }
}

@media (max-width: 900px) {
  .admin-settings-shell {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--v-space-4);
  }

  .admin-settings-rail {
    display: none;
  }

  .admin-mobile-nav {
    display: grid;
    gap: 7px;
    position: sticky;
    top: 0;
    z-index: var(--v-z-sticky);
    margin-inline: -2px;
    padding: 10px 2px 12px;
    background: color-mix(in srgb, var(--v-bg-base) 96%, transparent);
  }

  .admin-mobile-nav-label {
    padding-inline: 2px;
    color: var(--v-text-muted);
    font-size: var(--v-text-xs);
    font-weight: 720;
  }

  .admin-mobile-nav-control {
    position: relative;
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr) 14px;
    align-items: center;
    gap: 10px;
    min-height: 46px;
    padding: 0 13px;
    border: 1px solid var(--v-control-border);
    border-radius: var(--v-radius-md);
    background: var(--v-control-bg);
    box-shadow: var(--v-surface-shadow-inset);
    color: var(--v-accent);
  }

  .admin-mobile-nav-control > .icon:first-child {
    width: 17px;
    height: 17px;
  }

  .admin-mobile-nav-control select {
    width: 100%;
    min-width: 0;
    height: 44px;
    padding: 0;
    border: 0;
    outline: 0;
    appearance: none;
    background: transparent;
    color: var(--v-text);
    font: 720 var(--v-text-md)/1 var(--v-font);
    cursor: pointer;
  }

  .admin-mobile-nav-chevron {
    width: 13px;
    height: 13px;
    color: var(--v-text-muted);
    pointer-events: none;
  }

  .admin-settings-content,
  .admin-settings-content.is-wide {
    width: 100%;
  }
}

@media (max-width: 768px) {
  .admin-page {
    padding: 14px 14px 80px;
    gap: var(--v-space-4);
  }

  .admin-page-header {
    align-items: stretch;
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .admin-header-copy p {
    font-size: var(--v-text-base);
  }

  .admin-header-overview {
    align-items: flex-start;
    gap: var(--v-space-2);
  }

  .admin-workspace-summary {
    flex: 1 1 auto;
    justify-content: flex-start;
    gap: 5px 12px;
  }

  .admin-title {
    font-size: 24px;
  }

  .admin-token {
    min-width: 0;
  }

  .account-settings-grid,
  .notification-preferences-body {
    grid-template-columns: 1fr;
    gap: 10px;
    padding-top: var(--v-space-3);
  }

  .account-profile-card,
  .account-password-card,
  .notification-preference-card {
    padding: 14px;
  }

  .account-password-head {
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .account-password-fields {
    grid-template-columns: 1fr;
  }

  .account-current-password {
    grid-column: auto;
  }

  .notification-preference-card .settings-toggle-grid,
  .notification-event-grid {
    grid-template-columns: 1fr;
  }

  .settings-disclosure-summary {
    grid-template-columns: 34px minmax(0, 1fr) 14px;
    gap: 10px;
    padding: 11px 12px;
  }

  .settings-disclosure-meta {
    grid-column: 2 / -1;
    grid-row: 2;
    justify-content: flex-start;
  }

  .settings-disclosure-chevron {
    grid-column: 3;
    grid-row: 1;
  }

  .discord-settings-body {
    padding: var(--v-space-3);
  }

  .delivery-health-toolbar,
  .download-audit-list-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 5px;
  }

  .share-project-list {
    padding: var(--v-space-3) 0;
    gap: 10px;
  }

  .download-audit-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .download-audit-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .download-audit-main,
  .download-audit-details {
    grid-column: 1 / -1;
  }

  .download-detail-grid {
    grid-template-columns: 1fr;
  }

  .download-audit-section .admin-toolbar-actions,
  .download-audit-section .admin-search-wrap {
    width: 100%;
    max-width: none;
  }

  .download-audit-section .admin-toolbar-actions {
    flex-wrap: nowrap;
  }

  .download-audit-section :deep(.settings-view-actions) {
    flex: 0 0 auto;
  }

  .download-audit-section .admin-toolbar-actions .v-btn {
    flex: 0 0 auto;
  }

  .download-audit-details {
    justify-self: stretch;
  }

  .download-audit-details summary {
    justify-content: center;
    width: 100%;
  }

  .share-project-group {
    border-radius: var(--v-radius-lg);
  }

  .share-project-header {
    padding: var(--v-space-3);
  }

  .share-project-thumb {
    width: 48px;
    height: 30px;
  }

  .share-filter-count {
    width: 100%;
  }

  .share-settings-section > .admin-toolbar {
    flex-wrap: wrap;
    overflow-x: visible;
  }

  .share-settings-section > .admin-toolbar .admin-search-wrap {
    flex: 1 0 100%;
    width: 100%;
    max-width: none;
  }

  .share-settings-section > .admin-toolbar .admin-filter-row {
    flex: 1 1 auto;
  }

  .share-item-list {
    gap: 7px;
    padding: var(--v-space-2);
  }

  .share-item {
    grid-template-columns: 1fr;
    gap: var(--v-space-2);
    padding: 10px;
  }

  .share-item-actions {
    justify-content: flex-start;
    gap: 5px;
  }

  .share-item-actions .v-btn {
    min-width: 0;
  }

  .admin-list-header {
    display: none;
  }

  .admin-subscription-grid,
  .admin-delivery-grid,
  .subscription-card,
  .delivery-card,
  .admin-card {
    grid-template-columns: 1fr;
    gap: 8px 0;
    padding: 10px 12px;
  }

}

@media (max-width: 480px) {
  .admin-workspace-summary span:nth-child(n + 2) {
    display: none;
  }

  .share-project-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .share-project-counts {
    justify-content: flex-start;
  }
}
</style>
