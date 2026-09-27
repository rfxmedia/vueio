<template>
  <section class="admin-page">
    <h1 class="v-sr-only">Settings</h1>
    <div class="admin-settings-shell" :class="{ 'is-setup': isStorageSetup, 'is-index': showMobileIndex }">
      <aside v-if="!isStorageSetup" class="admin-settings-rail" aria-label="Settings sections">
        <nav class="admin-settings-nav">
          <section v-for="group in settingsNavGroups" :key="group.label" class="admin-nav-group">
            <h2>{{ group.label }}</h2>
            <div class="admin-nav-list">
              <button
                v-for="tab in group.tabs"
                :key="tab.value"
                type="button"
                class="admin-nav-item"
                :class="{ active: !showMobileIndex && activeTab === tab.value }"
                :aria-current="!showMobileIndex && activeTab === tab.value ? 'page' : undefined"
                @click="selectTab(tab.value)"
              >
                <span class="admin-nav-icon" aria-hidden="true"><svg class="icon"><use :href="tab.icon" /></svg></span>
                <span class="admin-nav-copy">
                  <strong>{{ tab.label }}</strong>
                  <small>{{ tab.description }}</small>
                </span>
                <span v-if="navBadges[tab.value]" class="admin-nav-badge" :class="navBadges[tab.value].tone">{{ navBadges[tab.value].label }}</span>
                <svg class="icon admin-nav-chevron" aria-hidden="true"><use href="#icon-chevron-right" /></svg>
              </button>
            </div>
          </section>
        </nav>
      </aside>

      <main v-if="!showMobileIndex" class="admin-settings-content" :class="{ 'is-wide': activeSettingsTab.wide }">
        <button v-if="isCompact && !isStorageSetup" class="admin-mobile-back" type="button" @click="openMobileIndex">
          <svg class="icon" aria-hidden="true"><use href="#icon-back" /></svg>
          Settings
        </button>

        <section v-if="activeTab === 'account'" class="admin-section settings-stack">
          <AdminSettingsHeader
            title="Account"
            description="Your profile and sign-in password."
            icon="#icon-user"
          />

          <section class="settings-card">
            <div class="account-identity">
              <div class="account-avatar" aria-hidden="true">{{ currentUserInitials }}</div>
              <div class="account-identity-copy">
                <strong>{{ currentUser?.display_name || currentUser?.username }}</strong>
                <span>@{{ currentUser?.username }}</span>
              </div>
              <span class="account-role" :class="{ 'is-admin': isAdmin }">{{ isAdmin ? 'Administrator' : 'Member' }}</span>
            </div>
            <div class="settings-row">
              <div class="settings-row-copy">
                <strong>Your access</strong>
                <span>{{ isAdmin ? 'You can open every project and change all settings.' : `${summarizeAppAccess(currentUser || {})}. An administrator controls your access.` }}</span>
              </div>
            </div>
          </section>

          <form class="settings-card" @submit.prevent="saveMyPassword">
            <header class="settings-card-head">
              <div>
                <h3>Password</h3>
                <p>Enter your current password, then a new one with at least 8 characters.</p>
              </div>
            </header>
            <div class="settings-card-body account-password-fields">
              <input type="text" class="v-sr-only" autocomplete="username" :value="currentUser?.username || ''" tabindex="-1" aria-hidden="true" readonly />
              <VField label="Current password">
                <input v-model="passwordForm.current" type="password" class="v-input" autocomplete="current-password" />
              </VField>
              <VField label="New password" :error="passwordTooShort ? 'Use at least 8 characters.' : ''">
                <input v-model="passwordForm.new" type="password" class="v-input" autocomplete="new-password" />
              </VField>
              <VField label="Confirm new password" :error="passwordMismatch ? 'The passwords do not match.' : ''">
                <input v-model="passwordForm.confirm" type="password" class="v-input" autocomplete="new-password" />
              </VField>
            </div>
            <footer class="settings-card-foot">
              <p v-if="passwordMessage" role="status">{{ passwordMessage }}</p>
              <button class="v-btn v-btn-primary v-btn-sm" type="submit" :disabled="passwordSaving || !canSavePassword">
                {{ passwordSaving ? 'Saving' : 'Change password' }}
              </button>
            </footer>
          </form>
        </section>

        <section v-if="activeTab === 'notifications'" class="admin-section settings-stack">
          <AdminSettingsHeader
            title="Notifications"
            description="Choose where Vueio tells you about activity, and which activity. Changes save automatically."
            icon="#icon-bell"
          >
            <span v-if="notificationSaving || notificationMessage" class="settings-save-state" :class="{ 'is-error': notificationError }" role="status">
              <svg v-if="!notificationSaving && !notificationError" class="icon" aria-hidden="true"><use href="#icon-check" /></svg>
              {{ notificationSaving ? 'Saving…' : notificationMessage }}
            </span>
          </AdminSettingsHeader>

          <section class="settings-card">
            <header class="settings-card-head">
              <div>
                <h3>Where</h3>
                <p>Turn on each place you want to see activity.</p>
              </div>
            </header>
            <VSwitch
              class="settings-switch-row"
              :model-value="notificationPrefs.channels.in_app"
              label="Notification tray"
              hint="Show activity in the bell at the top of Vueio."
              @update:modelValue="setNotificationChannel('in_app', $event)"
            />
            <VSwitch
              class="settings-switch-row"
              :model-value="notificationPrefs.channels.discord"
              label="Discord"
              :hint="isAdmin ? 'Send activity to the Discord channels connected to you in Discord settings.' : 'Send activity to your Discord channel. An administrator connects the channel.'"
              @update:modelValue="setNotificationChannel('discord', $event)"
            />
          </section>

          <section class="settings-card">
            <header class="settings-card-head">
              <div>
                <h3>What</h3>
                <p>Choose which activity you get.</p>
              </div>
            </header>
            <div class="settings-row">
              <div class="settings-row-copy">
                <strong>Projects</strong>
                <span>
                  {{ notificationPrefs.default_scope === 'all_visible'
                    ? 'Activity from every project you can open.'
                    : 'Activity where you are assigned, mentioned or taking part.' }}
                </span>
              </div>
              <div class="settings-row-control">
                <div v-if="isAdmin" class="settings-segmented" role="group" aria-label="Activity from">
                  <button type="button" :aria-pressed="notificationPrefs.default_scope === 'related_to_me'" @click="setNotificationScope('related_to_me')">Related to me</button>
                  <button type="button" :aria-pressed="notificationPrefs.default_scope === 'all_visible'" @click="setNotificationScope('all_visible')">All projects</button>
                </div>
                <span v-else class="settings-count-pill">Related to me</span>
              </div>
            </div>
            <div class="settings-row is-stacked">
              <div class="notification-types-head">
                <div class="settings-row-copy">
                  <strong>Activity types</strong>
                  <span>
                    {{ notificationEventMode === 'all'
                      ? 'All types, including types that Vueio adds later.'
                      : `${notificationPrefs.event_types.length} of ${notificationEventOptions.length} types.` }}
                  </span>
                </div>
                <div class="settings-row-control">
                  <div class="settings-segmented" role="group" aria-label="Activity types">
                    <button type="button" :aria-pressed="notificationEventMode === 'all'" @click="setNotificationEventMode('all')">All types</button>
                    <button type="button" :aria-pressed="notificationEventMode === 'selected'" @click="setNotificationEventMode('selected')">Choose</button>
                  </div>
                </div>
              </div>
              <div v-if="notificationEventMode === 'selected'" class="notification-event-grid">
                <VCheckbox
                  v-for="option in notificationEventOptions"
                  :key="option.value"
                  :model-value="notificationPrefs.event_types.includes(option.value)"
                  :disabled="isLastNotificationType(option.value)"
                  :label="option.label"
                  :hint="option.hint"
                  @update:modelValue="toggleNotificationEventType(option.value, $event)"
                />
              </div>
            </div>
          </section>
        </section>

        <AdminAgentKeysTab
          v-if="activeTab === 'agent-keys'"
          :agent-key-scope="agentKeyScope"
          :filtered-visible-agent-keys="filteredVisibleAgentKeys"
          :format-date-label="formatDateLabel"
          :grouped-visible-agent-keys="groupedVisibleAgentKeys"
          :is-admin="isAdmin"
          :key-search="keySearch"
          :visible-token="visibleAgentToken"
          @update:agent-key-scope="agentKeyScope = $event"
          @update:key-search="keySearch = $event"
          @copy-token="copyText(visibleAgentToken.token, 'Token copied')"
          @copy-token-skill="copyVisibleAgentSkill"
          @dismiss-token="visibleAgentToken = null"
          @delete-unified-agent-key="deleteUnifiedAgentKeyConfirm"
          @open-create-key-modal="openCreateKeyModal"
          @open-edit-agent-key="openEditAgentKey"
          @reissue-agent-key-skill="reissueAndCopyAgentKeySkill"
          @reissue-unified-agent-key="reissueUnifiedAgentKey"
          @toggle-unified-agent-key="toggleUnifiedAgentKey"
        />

        <AdminMembersTab
          v-if="canManageMembers && activeTab === 'members'"
          :current-user="currentUser"
          :filtered-users="filteredUsers"
          :user-search="userSearch"
          :admin-user-count="adminUserCount"
          :member-user-count="memberUserCount"
          :summarize-app-access="summarizeAppAccess"
          :user-initials="userInitials"
          @update:user-search="userSearch = $event"
          @open-create-user-modal="openCreateUserModal"
          @open-edit-user-modal="openEditUserModal"
          @delete-user="deleteUserConfirm"
        />

        <AdminBrandingTab
          v-if="isAdmin && activeTab === 'branding'"
          :identity-form="identityForm"
          :identity-initials="identityInitials"
          :identity-logo-saving="identityLogoSaving"
          :identity-logo-url="identityLogoUrl"
          :identity-message="identityMessage"
          :identity-saving="identitySaving"
          :identity-team-name="identityTeamName"
          :identity-website-url="identityWebsiteUrl"
          @update-identity-field="updateIdentityField"
          @identity-logo-change="handleIdentityLogoChange"
          @remove-identity-logo="removeIdentityLogo"
          @save-identity="saveIdentity"
        />

        <section v-if="isAdmin && activeTab === 'discord'" class="admin-section settings-stack">
          <AdminSettingsHeader
            title="Discord"
            description="Post Vueio activity in Discord. Set up the bot once, then connect a channel for each person."
            icon="#icon-send"
          >
            <span class="settings-status-pill" :class="discordProvider.is_configured ? 'is-good' : 'is-warn'">
              <i aria-hidden="true"></i>
              {{ discordProvider.is_configured ? 'Connected' : 'Not set up' }}
            </span>
          </AdminSettingsHeader>

          <form class="settings-card" @submit.prevent="saveDiscordProvider">
            <header class="settings-card-head">
              <div>
                <h3>Bot</h3>
                <p>
                  {{ discordProvider.has_saved_token
                    ? 'A bot token is saved in Vueio.'
                    : discordProvider.uses_env_token
                      ? 'Vueio uses the bot token from the server configuration.'
                      : 'Create a bot in the Discord Developer Portal, then paste its details here.' }}
                </p>
              </div>
            </header>
            <div class="settings-card-body discord-bot-fields">
              <VField label="Application ID" hint="On the General Information page of your Discord app.">
                <input v-model="discordProviderForm.application_id" class="v-input" inputmode="numeric" placeholder="123456789012345678" />
              </VField>
              <VField label="Vueio address" hint="Links in Discord messages open this address.">
                <input v-model="discordProviderForm.public_base_url" class="v-input" type="url" placeholder="https://vue.example.com" />
              </VField>
              <VField class="discord-token-field" label="Bot token" :hint="discordProvider.has_saved_token ? 'Leave empty to keep the saved token.' : 'On the Bot page of your Discord app.'">
                <div class="admin-secret-input">
                  <input
                    v-model="discordProviderForm.bot_token"
                    class="v-input"
                    :type="discordTokenVisible ? 'text' : 'password'"
                    autocomplete="off"
                    :placeholder="discordProvider.has_saved_token ? 'Saved' : 'Paste the bot token'"
                  />
                  <button
                    class="v-btn v-btn-ghost v-btn-icon v-btn-sm admin-secret-toggle"
                    type="button"
                    :title="discordTokenVisible ? 'Hide bot token' : 'Show bot token'"
                    :aria-label="discordTokenVisible ? 'Hide bot token' : 'Show bot token'"
                    @click="discordTokenVisible = !discordTokenVisible"
                  >
                    <svg class="icon"><use :href="discordTokenVisible ? '#icon-eye-off' : '#icon-eye'" /></svg>
                  </button>
                </div>
              </VField>
            </div>
            <div v-if="discordProvider.invite_url" class="settings-row discord-invite-row">
              <div class="settings-row-copy">
                <strong>Add the bot to your server</strong>
                <span>The bot needs to view channels, send messages, embed links and read message history. For a private channel, also add the bot role to it in Discord.</span>
              </div>
              <div class="settings-row-control">
                <a class="v-btn v-btn-secondary v-btn-sm" :href="discordProvider.invite_url" target="_blank" rel="noreferrer">
                  Open invite
                  <svg class="icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
                </a>
              </div>
            </div>
            <footer class="settings-card-foot">
              <p v-if="discordProviderMessage" role="status">{{ discordProviderMessage }}</p>
              <button
                v-if="discordProvider.has_saved_token"
                class="v-btn v-btn-ghost v-btn-sm discord-clear-token"
                type="button"
                :disabled="discordProviderSaving"
                @click="clearDiscordProviderToken"
              >
                Remove saved token
              </button>
              <button class="v-btn v-btn-primary v-btn-sm" type="submit" :disabled="discordProviderSaving">
                {{ discordProviderSaving ? 'Saving' : 'Save' }}
              </button>
            </footer>
          </form>

          <section class="settings-card">
            <header class="settings-card-head">
              <div>
                <h3>Channels <span v-if="subscriptions.length" class="settings-count-pill">{{ subscriptions.length }}</span></h3>
                <p>Each channel gets the activity of one person. Vueio sends only what that person can see.</p>
              </div>
              <div class="settings-card-head-actions">
                <button class="v-btn v-btn-secondary v-btn-sm" type="button" @click="openCreateSubscriptionModal">
                  <svg class="icon"><use href="#icon-plus" /></svg>
                  Connect channel
                </button>
              </div>
            </header>
            <div v-if="subscriptions.length === 0" class="settings-empty">
              <strong>No channels connected</strong>
              <span>Connect a channel to start sending activity to Discord.</span>
            </div>
            <ul v-else class="settings-list">
              <li v-for="subscription in subscriptions" :key="subscription.id" class="settings-list-row" :class="{ 'is-muted': !subscription.is_enabled }">
                <span class="settings-list-mark" aria-hidden="true">#</span>
                <div class="settings-list-main">
                  <div class="settings-list-title">
                    <span>{{ subscription.recipient_display_name }}</span>
                    <span v-if="!subscription.is_enabled" class="settings-count-pill">Paused</span>
                  </div>
                  <div class="settings-list-meta">
                    <span>Channel {{ subscription.destination }}</span>
                    <span>{{ subscription.scope === 'all_visible' ? 'All projects' : 'Related to them' }}</span>
                    <span>{{ subscription.event_filters?.length ? subscription.event_filters.map(formatEventType).join(', ') : 'All types' }}</span>
                  </div>
                </div>
                <div class="settings-list-actions">
                  <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="testSubscription(subscription)">Send test</button>
                  <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="openEditSubscriptionModal(subscription)">Edit</button>
                  <VMenu
                    :open="subscriptionMenuOpen === subscription.id"
                    align="end"
                    :min-width="180"
                    teleport
                    @update:open="subscriptionMenuOpen = $event ? subscription.id : ''"
                  >
                    <template #trigger="{ triggerProps }">
                      <VOverflowButton
                        v-bind="triggerProps"
                        :active="subscriptionMenuOpen === subscription.id"
                        :label="`More actions for ${subscription.recipient_display_name}`"
                        @click="subscriptionMenuOpen = subscriptionMenuOpen === subscription.id ? '' : subscription.id"
                      />
                    </template>
                    <VMenuActionList :actions="subscriptionMenuActions(subscription)" />
                  </VMenu>
                </div>
              </li>
            </ul>
          </section>

          <section class="settings-card">
            <header class="settings-card-head">
              <div>
                <h3>
                  Recent deliveries
                  <span v-if="failedDeliveryCount" class="settings-status-pill is-bad"><i aria-hidden="true"></i>{{ failedDeliveryCount }} failed</span>
                  <span v-else-if="deliveries.length" class="settings-status-pill is-good"><i aria-hidden="true"></i>All sent</span>
                </h3>
                <p>The last {{ deliveries.length || 100 }} messages Vueio tried to send.</p>
              </div>
              <div class="settings-card-head-actions">
                <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="loadDeliveries">
                  <svg class="icon"><use href="#icon-refresh" /></svg>
                  Refresh
                </button>
              </div>
            </header>
            <div v-if="deliveries.length === 0" class="settings-empty">
              <strong>Nothing sent yet</strong>
              <span>Messages appear here after Vueio sends activity to Discord.</span>
            </div>
            <ul v-else class="settings-list">
              <li v-for="delivery in displayedDeliveries" :key="delivery.id" class="settings-list-row delivery-row" :class="`is-${deliveryStateClass(delivery.status) || 'waiting'}`">
                <span class="settings-list-mark" aria-hidden="true">
                  <svg class="icon"><use :href="deliveryStateIcon(delivery.status)" /></svg>
                </span>
                <div class="settings-list-main">
                  <div class="settings-list-title">
                    <span>{{ delivery.payload?.event?.summary || `Event ${delivery.tracker_event_id}` }}</span>
                  </div>
                  <div class="settings-list-meta">
                    <span class="delivery-status">{{ formatDeliveryStatus(delivery.status) }}</span>
                    <span>{{ userLabel(delivery.recipient_user_id) }}</span>
                    <span>{{ formatDateLabel(delivery.created_at) }}</span>
                    <span v-if="(delivery.attempts || 0) > 1">{{ delivery.attempts }} attempts</span>
                  </div>
                  <p v-if="delivery.last_error" class="delivery-error">{{ delivery.last_error }}</p>
                </div>
              </li>
            </ul>
            <footer v-if="displayedDeliveries.length < deliveries.length" class="settings-card-foot">
              <p>Showing {{ displayedDeliveries.length }} of {{ deliveries.length }}</p>
              <button class="v-btn v-btn-secondary v-btn-sm" type="button" @click="deliveryVisibleLimit += 10">Show more</button>
            </footer>
          </section>
        </section>

        <AdminThemeManager v-if="isAdmin && activeTab === 'theme'" />

        <AdminLutsTab v-if="isAdmin && activeTab === 'luts'" />

        <AdminUpdatesTab v-if="isAdmin && activeTab === 'updates'" />

        <AdminStorageTab
          v-if="isAdmin && activeTab === 'storage'"
          :storage-roots="storageRoots"
          :storage-roots-error="storageRootsError"
          :storage-roots-loading="storageRootsLoading"
          @refresh-storage-roots="loadStorageRoots"
        />

        <AdminPreviewsTab
          v-if="isAdmin && activeTab === 'previews'"
          :transcodes-resetting="transcodesResetting"
          @reset-transcodes="resetTranscodes"
        />

        <section v-if="isAdmin && activeTab === 'downloads'" class="admin-section settings-stack">
          <AdminSettingsHeader
            title="Download history"
            description="See who downloaded files and when. Vueio keeps up to 180 days and 10,000 downloads."
            icon="#icon-download"
          >
            <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="downloadEventsLoading" @click="loadDownloadEvents">
              <svg class="icon" :class="{ spinning: downloadEventsLoading }"><use href="#icon-refresh" /></svg>
              {{ downloadEventsLoading ? 'Refreshing' : 'Refresh' }}
            </button>
          </AdminSettingsHeader>

          <section class="settings-card">
            <div class="settings-list-toolbar">
              <div class="v-search-shell admin-search-wrap">
                <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
                <input v-model="downloadSearch" class="v-search-input admin-search-input" placeholder="Search files and people" aria-label="Search downloads" />
              </div>
              <div class="settings-segmented" role="group" aria-label="Downloaded by">
                <button type="button" :aria-pressed="downloadSourceFilter === 'all'" @click="downloadSourceFilter = 'all'">All <span class="settings-segmented-count">{{ downloadEvents.length }}</span></button>
                <button type="button" :aria-pressed="downloadSourceFilter === 'team'" @click="downloadSourceFilter = 'team'">Team <span class="settings-segmented-count">{{ downloadEvents.length - sharedDownloadCount }}</span></button>
                <button type="button" :aria-pressed="downloadSourceFilter === 'share'" @click="downloadSourceFilter = 'share'">Shared links <span class="settings-segmented-count">{{ sharedDownloadCount }}</span></button>
              </div>
            </div>

            <div v-if="downloadEventsLoading && !downloadEvents.length" class="settings-empty" role="status">Loading download history…</div>
            <div v-else-if="downloadEventsError" class="settings-empty" role="alert">{{ downloadEventsError }}</div>
            <div v-else-if="filteredDownloadEvents.length === 0" class="settings-empty">
              <strong>{{ downloadEvents.length ? 'No downloads found' : 'No downloads yet' }}</strong>
              <span>{{ downloadEvents.length ? 'Try a different search or filter.' : 'Downloads appear here after someone saves a file.' }}</span>
            </div>
            <ul v-else class="settings-list">
              <li v-for="event in displayedDownloadEvents" :key="event.id" class="download-row" :class="{ 'is-open': expandedDownloadId === event.id }">
                <div class="settings-list-row">
                  <span class="settings-list-mark download-mark" :class="downloadEventClass(event)" aria-hidden="true">
                    <svg class="icon"><use :href="downloadEventIcon(event)" /></svg>
                  </span>
                  <div class="settings-list-main">
                    <div class="settings-list-title">
                      <span>{{ downloadEventTitle(event) }}</span>
                      <span v-if="downloadEventLabel(event) !== 'File'" class="settings-count-pill">{{ downloadEventLabel(event) }}</span>
                    </div>
                    <div class="settings-list-meta">
                      <span>{{ event.user_name || (event.source === 'share' ? 'Shared link visitor' : 'Unknown person') }}</span>
                      <span>{{ formatDateLabel(event.created_at) }}</span>
                      <span>{{ event.source === 'share' ? 'Shared link' : 'Team' }}</span>
                      <span v-if="event.size_bytes">{{ formatSizeBytes(event.size_bytes, { compact: true }) }}</span>
                      <span v-if="event.status && event.status !== 'completed'">{{ event.status }}</span>
                    </div>
                  </div>
                  <div class="settings-list-actions">
                    <button
                      class="v-btn v-btn-ghost v-btn-sm"
                      type="button"
                      :aria-expanded="expandedDownloadId === event.id"
                      @click="expandedDownloadId = expandedDownloadId === event.id ? '' : event.id"
                    >
                      Details
                      <svg class="icon download-details-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
                    </button>
                  </div>
                </div>
                <dl v-if="expandedDownloadId === event.id" class="download-detail-grid">
                  <div><dt>Event ID</dt><dd>{{ event.id }}</dd></div>
                  <div><dt>Project</dt><dd>{{ event.project_id || 'None' }}</dd></div>
                  <div><dt>Tracker</dt><dd>{{ event.tracker_id || 'None' }}</dd></div>
                  <div><dt>File name</dt><dd>{{ event.filename || 'None' }}</dd></div>
                  <div><dt>Size</dt><dd>{{ formatSizeBytes(event.size_bytes, { zeroLabel: 'Unknown', compact: true }) }}</dd></div>
                  <div><dt>Resource</dt><dd>{{ event.resource_type || 'Unknown' }}</dd></div>
                  <div><dt>Sign-in</dt><dd>{{ event.source === 'share' ? `Shared link ${event.share_id || ''}` : (event.auth_mode || 'session') }}</dd></div>
                  <div><dt>Status</dt><dd>{{ event.status || 'started' }}</dd></div>
                  <div class="download-detail-wide"><dt>Context</dt><dd>{{ compactJson(event.metadata) }}</dd></div>
                </dl>
              </li>
            </ul>
            <footer v-if="displayedDownloadEvents.length < filteredDownloadEvents.length" class="settings-card-foot">
              <p>Showing {{ displayedDownloadEvents.length }} of {{ filteredDownloadEvents.length }}</p>
              <button class="v-btn v-btn-secondary v-btn-sm" type="button" @click="downloadVisibleLimit += 15">Show more</button>
            </footer>
          </section>
        </section>

        <section v-if="isAdmin && activeTab === 'shares'" class="admin-section settings-stack share-settings-section">
          <AdminSettingsHeader
            title="Shared links"
            description="Links that let people outside your team open projects and files. Turn a link off to stop access at once."
            icon="#icon-share"
          />

          <div class="share-toolbar">
            <div class="v-search-shell admin-search-wrap">
              <svg class="icon admin-search-icon"><use href="#icon-search" /></svg>
              <input v-model="shareSearch" class="v-search-input admin-search-input" placeholder="Search links" aria-label="Search shared links" />
            </div>
            <div class="settings-segmented" role="group" aria-label="Link status">
              <button type="button" :aria-pressed="shareStatusFilter === 'all'" @click="shareStatusFilter = 'all'">All</button>
              <button type="button" :aria-pressed="shareStatusFilter === 'active'" @click="shareStatusFilter = 'active'">Active</button>
              <button type="button" :aria-pressed="shareStatusFilter === 'expired'" @click="shareStatusFilter = 'expired'">Expired</button>
              <button type="button" :aria-pressed="shareStatusFilter === 'inactive'" @click="shareStatusFilter = 'inactive'">Off</button>
            </div>
            <span class="settings-list-count">{{ filteredShares.length }} {{ filteredShares.length === 1 ? 'link' : 'links' }}</span>
          </div>

          <section v-if="filteredShares.length === 0" class="settings-card settings-empty">
            <strong>{{ shares.length ? 'No links found' : 'No shared links yet' }}</strong>
            <span>{{ shares.length ? 'Try a different search or filter.' : 'Links appear here after someone shares a project or file.' }}</span>
          </section>
          <div v-else class="share-project-list">
            <details
              v-for="group in displayedShareGroups"
              :key="group.key"
              class="share-project-group"
              :open="Boolean(shareSearch.trim()) || groupedShares.length === 1"
            >
              <summary class="share-project-header">
                <div class="share-project-thumb" :class="{ 'is-empty': !group.thumbnailUrl }">
                  <img v-if="group.thumbnailUrl" :src="group.thumbnailUrl" alt="" @error="hideBrokenShareThumbnail" />
                  <span v-else>{{ group.initials }}</span>
                </div>
                <div class="share-project-heading">
                  <h3>{{ group.title }}</h3>
                  <p>{{ group.subtitle }} · {{ group.summary }}</p>
                </div>
                <div class="share-project-counts">
                  <span v-if="group.activeCount" class="settings-status-pill is-good"><i aria-hidden="true"></i>{{ group.activeCount }} active</span>
                  <span v-if="group.expiredCount" class="settings-status-pill is-warn"><i aria-hidden="true"></i>{{ group.expiredCount }} expired</span>
                  <span v-if="group.revokedCount" class="settings-status-pill"><i aria-hidden="true"></i>{{ group.revokedCount }} off</span>
                </div>
                <svg class="icon share-project-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
              </summary>

              <ul class="settings-list">
                <li v-for="share in group.shares" :key="share.id" class="settings-list-row share-item" :class="{ 'is-muted': !share.is_active || isShareExpired(share) }">
                  <span class="settings-list-mark" aria-hidden="true"><svg class="icon"><use :href="shareTypeIcon(share)" /></svg></span>
                  <div class="settings-list-main">
                    <div class="settings-list-title">
                      <span>{{ shareDisplayName(share) }}</span>
                      <span class="settings-status-pill" :class="shareStateTone(share)"><i aria-hidden="true"></i>{{ shareStateLabel(share) }}</span>
                    </div>
                    <div class="settings-list-meta">
                      <span>{{ formatShareAccess(share) }}</span>
                      <span>{{ share.expires_at ? `${isShareExpired(share) ? 'Expired' : 'Expires'} ${formatDateLabel(share.expires_at)}` : 'No end date' }}</span>
                      <span>{{ share.access_count || 0 }} {{ share.access_count === 1 ? 'view' : 'views' }}</span>
                      <span>By {{ share.created_by || 'unknown' }} · {{ formatDateLabel(share.created_at) }}</span>
                    </div>
                  </div>
                  <div class="settings-list-actions">
                    <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="copyShareToClipboard(share)">
                      <svg class="icon"><use href="#icon-link" /></svg>
                      Copy link
                    </button>
                    <button class="v-btn v-btn-ghost v-btn-sm" type="button" @click="openShareEditor(share)">Edit</button>
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
              </ul>
            </details>
          </div>
          <button
            v-if="displayedShareGroups.length < groupedShares.length"
            class="v-btn v-btn-secondary admin-show-more"
            type="button"
            @click="shareGroupVisibleLimit += 12"
          >
            Show more projects
          </button>
        </section>
      </main>
    </div>

    <VModal :modelValue="!!editingShare" size="md" @update:modelValue="closeShareEditor">
      <template #header>
        <VModalHeader title="Edit shared link" @close="closeShareEditor" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="End date" hint="Leave empty to keep the link open until you turn it off.">
          <input v-model="shareEditForm.expiresDate" type="date" class="v-input" />
        </VField>
        <VField label="Password" hint="Leave empty to remove the password.">
          <input v-model="shareEditForm.password" type="password" class="v-input" autocomplete="new-password" placeholder="No password" />
        </VField>
        <VSwitch v-model="shareEditForm.allowDownload" label="Allow downloads" hint="Visitors can save the shared files to their device." />
        <VSwitch
          v-if="editingShare?.share_type === 'folder'"
          v-model="shareEditForm.allowUpload"
          label="Allow uploads"
          hint="Visitors can add files to the shared folder."
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
        <VField label="Username" hint="Used to sign in. You cannot change it later." :required="!editingUser">
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
        <VField label="Role" hint="Administrators can open every project and change all settings. Members get only the access you choose below.">
          <select v-if="canEditUserRole" v-model="userForm.role" class="v-input">
            <option value="member">Member</option>
            <option value="admin">Administrator</option>
          </select>
          <div v-else class="admin-readonly-field">
            <span>Role</span>
            <strong>Member</strong>
          </div>
        </VField>

        <div v-if="userForm.role === 'member'" class="v-subsection admin-subsection member-access-section">
          <p v-if="!isAdmin" class="v-inline-note admin-note">
            You can grant only access that your own account has.
          </p>
          <div class="v-section-label v-section-label--ruled">Can open</div>
          <VCheckbox
            :model-value="userForm.app_access.project_manager"
            label="Projects"
            hint="Open the projects this member is added to."
            :disabled="!canGrantMemberAccess('project_manager')"
            @update:modelValue="setUserAccess('project_manager', $event)"
          />
          <VCheckbox
            :model-value="userForm.app_access.file_browser"
            label="Files"
            hint="Browse configured storage through Vueio."
            :disabled="!canGrantMemberAccess('file_browser')"
            @update:modelValue="setUserAccess('file_browser', $event)"
          />
          <div class="v-section-label v-section-label--ruled member-access-divider">Can manage</div>
          <VCheckbox
            :model-value="userForm.app_access.manage_project_content"
            label="Manage project content"
            hint="Create and organize trackers, shots, assignments, and project settings within permitted projects."
            :disabled="!canGrantMemberAccess('manage_project_content')"
            @update:modelValue="setUserAccess('manage_project_content', $event)"
          />
          <VCheckbox
            :model-value="userForm.app_access.create_projects"
            label="Create projects"
            hint="Create projects and choose their storage folders."
            :disabled="!canGrantMemberAccess('create_projects')"
            @update:modelValue="setUserAccess('create_projects', $event)"
          />
          <VCheckbox
            :model-value="userForm.app_access.delete_projects"
            label="Delete projects"
            hint="Delete projects where this Member has Can manage access."
            :disabled="!canGrantMemberAccess('delete_projects')"
            @update:modelValue="setUserAccess('delete_projects', $event)"
          />
          <VCheckbox
            :model-value="userForm.app_access.manage_members"
            label="Manage members"
            hint="Manage Member accounts with the same or less access. Administrator accounts stay protected."
            :disabled="!canGrantMemberAccess('manage_members')"
            @update:modelValue="setUserAccess('manage_members', $event)"
          />
          <p class="v-inline-note admin-note">
            Project roles still apply: Can view, Can edit or Can manage. These options never open a project that the member is not added to.
          </p>
        </div>
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeUserModal">Cancel</button>
        <button class="v-btn v-btn-primary" @click="saveUser">{{ editingUser ? 'Save' : 'Add member' }}</button>
      </template>
    </VModal>

    <VModal :modelValue="showKeyModal" size="md" @update:modelValue="closeKeyModal">
      <template #header>
        <VModalHeader :title="editingKey ? 'Rename agent key' : 'New agent key'" @close="closeKeyModal" />
      </template>
      <form id="agent-key-form" class="v-form-grid admin-form-grid" @submit.prevent="saveAgentKey">
        <VField label="Name" hint="Use a name that says which agent or script uses this key.">
          <input v-model="keyForm.name" class="v-input" :placeholder="`${currentUserName()} agent`" />
        </VField>
        <p class="v-inline-note admin-note">{{ keyModalNote }}</p>
        <VSwitch v-if="editingKey" v-model="keyForm.is_active" label="Key is on" hint="When off, the key stops working until you turn it on again." />
      </form>
      <template #footer>
        <button class="v-btn v-btn-secondary" type="button" @click="closeKeyModal">Cancel</button>
        <button class="v-btn v-btn-primary" type="submit" form="agent-key-form">{{ editingKey ? 'Save' : 'Make key' }}</button>
      </template>
    </VModal>

    <VModal :modelValue="showSubscriptionModal" size="md" @update:modelValue="closeSubscriptionModal">
      <template #header>
        <VModalHeader :title="editingSubscription ? 'Edit Discord channel' : 'Connect a Discord channel'" @close="closeSubscriptionModal" />
      </template>
      <div class="v-form-grid admin-form-grid">
        <VField label="Person" hint="The channel gets this person's activity. Vueio sends only what this person can see.">
          <select v-model="subscriptionForm.recipient_user_id" class="v-input">
            <option value="" disabled>Choose a person</option>
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.display_name }} (@{{ user.username }})</option>
          </select>
        </VField>
        <VField label="Discord channel ID" hint="In Discord, turn on Developer Mode, then right-click the channel and select Copy Channel ID.">
          <input v-model="subscriptionForm.destination" class="v-input" placeholder="123456789012345678" />
        </VField>
        <VField label="Projects" hint="Which projects the activity comes from.">
          <select v-model="subscriptionForm.scope" class="v-input">
            <option value="related_to_me">Where this person is assigned, mentioned or taking part</option>
            <option value="all_visible">Every project this person can open</option>
          </select>
        </VField>
        <VSwitch v-model="subscriptionForm.is_enabled" label="Send messages" hint="Turn off to pause this channel without removing it." />
        <VSwitch v-model="subscriptionForm.config.mention_everyone" label="Mention @everyone" hint="Add an @everyone mention to every delivered message." />
        <div class="v-subsection admin-subsection">
          <div class="v-section-label v-section-label--ruled">Activity types</div>
          <div class="settings-option-grid">
            <VCheckbox
              v-for="option in notificationEventOptions"
              :key="`sub-${option.value}`"
              :model-value="subscriptionForm.event_filters.includes(option.value)"
              :label="option.label"
              @update:modelValue="toggleSubscriptionEventFilter(option.value, $event)"
            />
          </div>
          <p class="v-inline-note admin-note">Select none to send every type.</p>
        </div>
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" @click="closeSubscriptionModal">Cancel</button>
        <button class="v-btn v-btn-primary" :disabled="subscriptionSaving" @click="saveSubscription">
          {{ subscriptionSaving ? 'Saving' : editingSubscription ? 'Save' : 'Connect channel' }}
        </button>
      </template>
    </VModal>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
import { useUpdateStatusStore } from '../ownership/updateStatus'
import { hasAppAccess, isAdminUser } from '../utils/accountAccess'

const AdminAgentKeysTab = defineAsyncComponent(() => import('../components/admin/AdminAgentKeysTab.vue'))
const AdminBrandingTab = defineAsyncComponent(() => import('../components/admin/AdminBrandingTab.vue'))
const AdminLutsTab = defineAsyncComponent(() => import('../components/admin/AdminLutsTab.vue'))
const AdminMembersTab = defineAsyncComponent(() => import('../components/admin/AdminMembersTab.vue'))
const AdminPreviewsTab = defineAsyncComponent(() => import('../components/admin/AdminPreviewsTab.vue'))
const AdminStorageTab = defineAsyncComponent(() => import('../components/admin/AdminStorageTab.vue'))
const AdminThemeManager = defineAsyncComponent(() => import('../components/admin/AdminThemeManager.vue'))
const AdminUpdatesTab = defineAsyncComponent(() => import('../components/admin/AdminUpdatesTab.vue'))

const route = useRoute()
const router = useRouter()
const { currentUser, canManageMembers } = useSessionAuthStore()
const { identity: appIdentity, update: updateAppIdentity } = useAppIdentityStore()
const { status: updateStatus } = useUpdateStatusStore()
const isAdmin = computed(() => isAdminUser(currentUser.value))

// Settings sections, grouped by who they affect: you, your team, the
// workspace everyone sees, and the Vueio installation itself.
const personalTabs = [
  { value: 'account', label: 'Account', icon: '#icon-user', description: 'Profile and password' },
  { value: 'notifications', label: 'Notifications', icon: '#icon-bell', description: 'Where and what you hear about' },
  { value: 'agent-keys', label: 'Agent keys', icon: '#icon-zap', description: 'Access for AI agents and scripts', wide: true },
]
const membersTab = { value: 'members', label: 'Members', icon: '#icon-users', description: 'People and their access', wide: true }
const teamAdminTabs = [
  { value: 'shares', label: 'Shared links', icon: '#icon-share', description: 'Links for people outside your team', wide: true },
  { value: 'downloads', label: 'Download history', icon: '#icon-download', description: 'Who downloaded which files', wide: true },
]
const workspaceTabs = [
  { value: 'branding', label: 'Branding', icon: '#icon-briefcase', description: 'Name and logo on delivery pages', wide: true },
  { value: 'theme', label: 'Theme', icon: '#icon-pen', description: 'Workspace colors', wide: true },
  { value: 'luts', label: 'Preview LUTs', icon: '#icon-color', description: 'Color looks for review' },
  { value: 'discord', label: 'Discord', icon: '#icon-send', description: 'Post activity in Discord', wide: true },
]
const systemTabs = [
  { value: 'storage', label: 'Storage', icon: '#icon-package', description: 'Drives and Vueio data' },
  { value: 'previews', label: 'Previews', icon: '#icon-video', description: 'Video processing and cache' },
  { value: 'updates', label: 'Updates', icon: '#icon-refresh', description: 'Version and release channel' },
]
// Old links and bookmarks still open the section that now holds the setting.
const TAB_ALIASES = {
  team: 'members',
  users: 'members',
  identity: 'branding',
  channels: 'discord',
  deliveries: 'discord',
  keys: 'agent-keys',
  'personal-keys': 'agent-keys',
}
const activeTab = ref('account')
const isStorageSetup = computed(() => activeTab.value === 'storage' && route.query.setup === 'storage')
const settingsRefreshing = ref(false)
const storageRoots = ref([])
const storageRootsError = ref('')
const storageRootsLoading = ref(false)
const transcodesResetting = ref(false)
const settingsNavGroups = computed(() => [
  { label: 'Personal', tabs: personalTabs },
  ...((canManageMembers.value || isAdmin.value) ? [{
    label: 'Team',
    tabs: [
      ...(canManageMembers.value ? [membersTab] : []),
      ...(isAdmin.value ? teamAdminTabs : []),
    ],
  }] : []),
  ...(isAdmin.value ? [
    { label: 'Workspace', tabs: workspaceTabs },
    { label: 'System', tabs: systemTabs },
  ] : []),
])
const adminTabs = computed(() => settingsNavGroups.value.flatMap(group => group.tabs))
const activeSettingsTab = computed(() => (
  adminTabs.value.find(tab => tab.value === activeTab.value) || personalTabs[0]
))

// Narrow screens show the section list first, then one section at a time.
const compactQuery = window.matchMedia('(max-width: 900px)')
const isCompact = ref(compactQuery.matches)
const syncCompact = event => { isCompact.value = event.matches }
const showMobileIndex = computed(() => isCompact.value && !isStorageSetup.value && !route.query.tab)

function selectTab(tab) {
  if (isCompact.value) router.push({ path: '/settings', query: { tab } })
  else activeTab.value = tab
}

function openMobileIndex() {
  if (window.history.state?.back === '/settings') router.back()
  else router.replace({ path: '/settings' })
}

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
const notificationPrefs = ref(defaultNotificationPrefs())
const notificationSaving = ref(false)
const notificationMessage = ref('')
const notificationError = ref(false)
let notificationSaveRequest = 0

const passwordForm = ref({ current: '', new: '', confirm: '' })
const passwordSaving = ref(false)
const passwordMessage = ref('')
const identityForm = ref({ team_name: 'Vue', website_url: '' })
const identitySaving = ref(false)
const identityLogoSaving = ref(false)
const identityMessage = ref('')

const myAgentKeys = ref([])

const shares = ref([])
const shareSearch = ref('')
const shareStatusFilter = ref('all')
const shareGroupVisibleLimit = ref(12)
const shareActionMenuOpen = ref('')
const subscriptionMenuOpen = ref('')
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
  role: 'member',
  app_access: {
    file_browser: false,
    project_manager: true,
    manage_project_content: false,
    create_projects: false,
    delete_projects: false,
    manage_members: false,
  },
})
const userForm = ref(defaultUserForm())
const canEditUserRole = computed(() => isAdmin.value)

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
const downloadSourceFilter = ref('all')
const expandedDownloadId = ref('')
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
const sharedDownloadCount = computed(() => downloadEvents.value.filter(event => event.source === 'share').length)
const navBadges = computed(() => {
  const badges = {}
  if (users.value.length) badges.members = { label: users.value.length }
  if (activeShareCount.value) badges.shares = { label: activeShareCount.value }
  if (storageRoots.value.some(root => !root.available)) badges.storage = { label: 'Offline', tone: 'is-warn' }
  if (updateStatus.value?.update_available) badges.updates = { label: 'New', tone: 'is-accent' }
  return badges
})
const failedDeliveryCount = computed(() => deliveries.value.filter(delivery => ['failed', 'error', 'dead'].includes(String(delivery.status || '').toLowerCase())).length)
const displayedDeliveries = computed(() => deliveries.value.slice(0, deliveryVisibleLimit.value))
const notificationEventMode = computed(() => notificationPrefs.value.event_types.length ? 'selected' : 'all')
const passwordTooShort = computed(() => Boolean(passwordForm.value.new) && passwordForm.value.new.length < 8)
const passwordMismatch = computed(() => Boolean(passwordForm.value.confirm) && passwordForm.value.new !== passwordForm.value.confirm)
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
const keyModalNote = computed(() => (
  editingKey.value
    ? 'The key keeps its token. It can see and do only what its owner can.'
    : 'The key acts as you. It can see and do only what you can. Vueio shows the token once, after you make the key.'
))

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
      summary: `${shares.length} ${shares.length === 1 ? 'link' : 'links'} · ${viewCount} ${viewCount === 1 ? 'view' : 'views'}`,
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
  const title = projectTitle || 'Other files'
  return {
    key,
    title,
    subtitle: hasProject ? 'Project' : 'Files',
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
const memberUserCount = computed(() => users.value.filter(user => user.role === 'member').length)

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
  const source = downloadSourceFilter.value
  const events = source === 'all'
    ? downloadEvents.value
    : downloadEvents.value.filter(event => (event.source === 'share') === (source === 'share'))
  if (!query) return events
  return events.filter(event => [
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

watch([downloadSearch, downloadSourceFilter], () => {
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
  const access = []
  if (user.app_access?.manage_project_content) access.push('Project manager')
  else if (user.app_access?.project_manager) access.push('Project review')
  if (user.app_access?.file_browser) access.push('Files')
  if (user.app_access?.create_projects) access.push('Create projects')
  if (user.app_access?.delete_projects) access.push('Delete projects')
  if (user.app_access?.manage_members) access.push('Manage members')
  return access.length ? access.join(' · ') : 'No workspace access'
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
  if (!share.is_active) return 'Off'
  if (isShareExpired(share)) return 'Expired'
  return 'Active'
}

function shareStateTone(share) {
  if (!share.is_active) return ''
  if (isShareExpired(share)) return 'is-warn'
  return 'is-good'
}

function shareTypeIcon(share) {
  if (share.share_type === 'project') return '#icon-project'
  if (share.share_type === 'tracker') return '#icon-list'
  if (['folder', 'project-folder'].includes(share.share_type)) return '#icon-folder'
  return '#icon-file'
}

function canDeleteShare(share) {
  return !share.is_active || isShareExpired(share)
}

function shareMenuActions(share) {
  const canRevoke = share.is_active && !isShareExpired(share)
  return [
    {
      label: canRevoke ? 'Turn off link' : 'Turn on link',
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

const SHARE_TYPE_LABELS = {
  project: 'Project',
  tracker: 'Tracker',
  folder: 'Folder',
  'project-folder': 'Folder',
  'project-file': 'File',
  file: 'File',
}

function formatShareAccess(share) {
  const parts = [SHARE_TYPE_LABELS[share.share_type] || 'Link']
  if (share.has_password) parts.push('password')
  if (share.allow_download) parts.push('downloads on')
  if (share.allow_upload) parts.push('uploads on')
  return parts.join(', ')
}

function downloadEventLabel(event) {
  if (event.event_type === 'download_all') return 'Download all'
  if (event.event_type === 'download_folder_zip') return 'Folder zip'
  if (event.event_type === 'download_zip') return 'Zip'
  return 'File'
}

function downloadEventIcon(event) {
  if (event.source === 'share') return '#icon-share'
  if (event.event_type === 'download_all' || event.event_type?.endsWith('zip')) return '#icon-package'
  return '#icon-download'
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

async function loadStorageRoots() {
  storageRootsLoading.value = true
  storageRootsError.value = ''
  try {
    const { data } = await api.get('/api/storage/roots')
    storageRoots.value = Array.isArray(data) ? data : []
  } catch (error) {
    storageRoots.value = []
    storageRootsError.value = getApiErrorMessage(error, 'Vueio could not check the connected storage locations.')
  } finally {
    storageRootsLoading.value = false
  }
}

async function resetTranscodes() {
  if (!confirm('Reset all previews? Original files do not change. Each preview is rebuilt the next time someone opens it.')) return
  transcodesResetting.value = true
  try {
    await api.delete('/api/admin/transcodes')
    notify('All previews were reset.')
  } catch (error) {
    notify(getApiErrorMessage(error, 'Could not reset previews.'), { tone: 'error' })
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
  if (mode === notificationEventMode.value) return
  notificationPrefs.value.event_types = mode === 'selected'
    ? notificationEventOptions.map(option => option.value)
    : []
  saveNotificationPrefs()
}

// An empty list means every type, so the last chosen type cannot be cleared.
function isLastNotificationType(value) {
  const selected = notificationPrefs.value.event_types
  return selected.length === 1 && selected[0] === value
}

function toggleNotificationEventType(value, checked) {
  if (checked) {
    notificationPrefs.value.event_types = [...new Set([...notificationPrefs.value.event_types, value])]
  } else if (!isLastNotificationType(value)) {
    notificationPrefs.value.event_types = notificationPrefs.value.event_types.filter(entry => entry !== value)
  }
  saveNotificationPrefs()
}

function setNotificationChannel(channel, enabled) {
  notificationPrefs.value.channels[channel] = enabled
  saveNotificationPrefs()
}

function setNotificationScope(scope) {
  if (notificationPrefs.value.default_scope === scope) return
  notificationPrefs.value.default_scope = scope
  saveNotificationPrefs()
}

// Each change saves at once. Only the newest reply updates the form, so a
// slow earlier save cannot undo a later change.
async function saveNotificationPrefs() {
  const request = ++notificationSaveRequest
  notificationSaving.value = true
  notificationError.value = false
  try {
    const payload = {
      ...notificationPrefs.value,
      default_scope: isAdmin.value ? notificationPrefs.value.default_scope : 'related_to_me',
    }
    const { data } = await api.put('/api/me/notification-preferences', payload)
    if (request !== notificationSaveRequest) return
    notificationPrefs.value = normalizeNotificationPrefs(data)
    notificationMessage.value = 'Saved'
  } catch (error) {
    if (request !== notificationSaveRequest) return
    notificationError.value = true
    notificationMessage.value = getApiErrorMessage(error, 'Could not save. Try again.')
    loadNotificationPrefs().catch(() => {})
  } finally {
    if (request === notificationSaveRequest) notificationSaving.value = false
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
    identityMessage.value = 'Saved.'
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
    discordProviderMessage.value = 'Saved.'
  } catch (error) {
    discordProviderMessage.value = getApiErrorMessage(error, 'Failed to save Discord setup.')
  } finally {
    discordProviderSaving.value = false
  }
}

async function clearDiscordProviderToken() {
  if (!confirm('Remove the saved bot token? If the server configuration has a token, Vueio uses that one.')) return
  discordProviderSaving.value = true
  discordProviderMessage.value = ''
  try {
    const { data } = await api.put('/api/admin/notification-providers/discord', { bot_token: '', clear_token: true })
    discordProvider.value = normalizeDiscordProvider(data)
    discordProviderForm.value.bot_token = ''
    discordTokenVisible.value = false
    discordProviderMessage.value = 'Saved token removed.'
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
    if (canManageMembers.value) tasks.push(loadUsers())
    if (isAdmin.value) {
      tasks.push(loadIdentity(), loadShares(), loadStorageRoots(), loadAgentKeys(), loadDiscordProvider(), loadSubscriptions(), loadDeliveries(), loadDownloadEvents())
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
  if (!confirm(`Turn off the link to "${share.target_name || share.path || share.id}"? People with the link lose access at once.`)) return
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
  if (!user?.can_manage) return
  editingUser.value = user
  userForm.value = {
    username: user.username,
    display_name: user.display_name,
    password: '',
    role: user.role,
    app_access: {
      file_browser: !!user.app_access?.file_browser,
      project_manager: !!user.app_access?.project_manager,
      manage_project_content: !!user.app_access?.manage_project_content,
      create_projects: !!user.app_access?.create_projects,
      delete_projects: !!user.app_access?.delete_projects,
      manage_members: !!user.app_access?.manage_members,
    },
  }
  showUserModal.value = true
}

function canGrantMemberAccess(capability) {
  return isAdmin.value || hasAppAccess(currentUser.value, capability)
}

function setUserAccess(capability, enabled) {
  if (!canGrantMemberAccess(capability)) return
  userForm.value.app_access[capability] = Boolean(enabled)
  if (capability === 'project_manager' && !enabled) {
    userForm.value.app_access.manage_project_content = false
    userForm.value.app_access.create_projects = false
    userForm.value.app_access.delete_projects = false
  } else if (capability === 'manage_project_content' && !enabled) {
    userForm.value.app_access.create_projects = false
    userForm.value.app_access.delete_projects = false
  } else if (['manage_project_content', 'create_projects', 'delete_projects'].includes(capability) && enabled) {
    userForm.value.app_access.project_manager = true
    if (['create_projects', 'delete_projects'].includes(capability)) {
      userForm.value.app_access.manage_project_content = true
    }
  }
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
      if (['admin', 'member'].includes(userForm.value.role)) {
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
  if (!confirm(`Remove ${user.display_name}? They can no longer sign in. Their comments and history stay.`)) return
  try {
    await api.delete(`/api/users/${user.id}`)
    await loadUsers()
  } catch (error) {
    notify(`Failed to delete user: ${getApiErrorMessage(error)}`)
  }
}

function openCreateKeyModal() {
  editingKey.value = null
  editingKeyKind.value = 'personal'
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
      const { data } = await api.post('/api/me/agent-keys', {
        name: keyForm.value.name.trim() || `${currentUserName()} agent`,
      })
      agentKeyScope.value = 'mine'
      visibleAgentToken.value = {
        title: `${data.key?.name || 'Agent key'} is ready`,
        subtitle: 'Give it to your agent, or copy the skill for setup text that includes it.',
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
  if (!confirm(`Make a new token for "${key.name}"? The old token stops working at once.`)) return
  try {
    const { data } = await api.post(`/api/admin/agent-keys/${key.id}/reissue`)
    visibleAgentToken.value = {
      title: `New token for ${key.name}`,
      subtitle: 'The old token no longer works.',
      token: data.token || '',
      key: data.key || key,
    }
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to reissue key: ${getApiErrorMessage(error)}`)
  }
}

async function reissueAndCopyManagedAgentSkill(key) {
  if (!confirm(`Copy the skill for "${key.name}"? Vueio makes a new token for the skill. The old token stops working at once.`)) return
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
  if (!confirm(`Delete "${key.name}"? Agents that use it lose access. You cannot undo this.`)) return
  try {
    await api.delete(`/api/admin/agent-keys/${key.id}`)
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to delete key: ${getApiErrorMessage(error)}`)
  }
}

function currentUserName() {
  return currentUser.value?.display_name || currentUser.value?.username || 'Personal'
}

async function reissuePersonalAgentKey(key) {
  if (!confirm(`Make a new token for "${key.name}"? The old token stops working at once.`)) return
  try {
    const { data } = await api.post(`/api/me/agent-keys/${key.id}/reissue`)
    visibleAgentToken.value = {
      title: `New token for ${key.name}`,
      subtitle: 'The old token no longer works.',
      token: data.token || '',
      key: data.key || key,
    }
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to reissue key: ${getApiErrorMessage(error)}`)
  }
}

async function reissueAndCopyPersonalAgentSkill(key) {
  if (!confirm(`Copy the skill for "${key.name}"? Vueio makes a new token for the skill. The old token stops working at once.`)) return
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
  if (!confirm(`Delete "${key.name}"? Agents that use it lose access. You cannot undo this.`)) return
  try {
    await api.delete(`/api/me/agent-keys/${key.id}`)
    await reloadAgentKeys()
  } catch (error) {
    notify(`Failed to delete key: ${getApiErrorMessage(error)}`)
  }
}

function subscriptionMenuActions(subscription) {
  return [
    {
      label: subscription.is_enabled ? 'Pause' : 'Resume',
      icon: subscription.is_enabled ? '#icon-pause' : '#icon-play',
      run: () => toggleSubscription(subscription),
    },
    { divider: true },
    { label: 'Remove channel', icon: '#icon-trash', danger: true, run: () => deleteSubscriptionConfirm(subscription) },
  ]
}

function formatEventType(value) {
  return notificationEventOptions.find(option => option.value === value)?.label || value
}

function userLabel(userId) {
  const user = users.value.find(entry => entry.id === userId || entry.username === userId)
  return user?.display_name || userId || 'Unknown person'
}

function formatDeliveryStatus(status) {
  return {
    sent: 'Sent',
    failed: 'Failed',
    sending: 'Sending',
    pending: 'Waiting',
  }[status] || (status ? `${status.charAt(0).toUpperCase()}${status.slice(1)}` : 'Waiting')
}

function deliveryStateIcon(status) {
  if (status === 'sent') return '#icon-check'
  if (status === 'failed') return '#icon-alert'
  return '#icon-clock'
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
    notify('Test message sent.')
  } catch (error) {
    notify(`Test message failed: ${getApiErrorMessage(error)}`)
  }
}

async function deleteSubscriptionConfirm(subscription) {
  if (!confirm(`Remove the Discord channel for ${subscription.recipient_display_name}? Vueio stops sending messages to it.`)) return
  try {
    await api.delete(`/api/admin/notification-subscriptions/${subscription.id}`)
    await loadSubscriptions()
  } catch (error) {
    notify(`Failed to delete channel: ${getApiErrorMessage(error)}`)
  }
}

watch(adminTabs, tabs => {
  if (!tabs.some(tab => tab.value === activeTab.value)) activeTab.value = 'account'
}, { immediate: true })

watch(() => route.query.tab, tab => {
  const resolved = TAB_ALIASES[tab] || tab
  if (typeof resolved === 'string' && adminTabs.value.some(item => item.value === resolved)) {
    activeTab.value = resolved
  }
}, { immediate: true })

watch(activeTab, tab => {
  if (showMobileIndex.value) return
  const query = tab === 'account' && !isCompact.value ? {} : { tab }
  if ((route.query.tab || '') !== (query.tab || '')) {
    router.replace({ path: '/settings', query })
  }
})

onMounted(() => {
  compactQuery.addEventListener('change', syncCompact)
  refreshAll()
})
onBeforeUnmount(() => compactQuery.removeEventListener('change', syncCompact))
</script>

<style scoped>
.admin-page {
  flex: 1;
  min-height: 0;
  padding: 28px clamp(20px, 3vw, 44px) 48px;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.admin-section {
  min-width: 0;
}

.admin-settings-shell {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  align-items: start;
  gap: clamp(24px, 3.2vw, 48px);
  width: min(100%, 1320px);
  margin-inline: auto;
}

.admin-settings-shell.is-setup {
  grid-template-columns: minmax(0, 1fr);
  max-width: 860px;
}

/* Section rail */
.admin-settings-rail {
  position: sticky;
  top: 0;
  min-width: 0;
}

.admin-settings-nav {
  display: grid;
  gap: 18px;
}

.admin-nav-group {
  display: grid;
  gap: 4px;
}

.admin-nav-group h2 {
  margin: 0;
  padding: 0 10px 2px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1.3;
}

.admin-nav-list {
  display: grid;
  gap: 1px;
}

.admin-nav-item {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--v-text-dim);
  font-family: var(--v-font);
  text-align: left;
  cursor: pointer;
  transition: background-color var(--v-transition-fast), color var(--v-transition-fast);
}

.admin-nav-item:hover {
  background: color-mix(in srgb, var(--v-text) 4%, transparent);
  color: var(--v-text);
}

.admin-nav-item.active {
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-text) 6%, transparent);
}

.admin-nav-item:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.admin-nav-icon {
  display: grid;
  place-items: center;
}

.admin-nav-icon .icon {
  width: 15px;
  height: 15px;
}

.admin-nav-item.active .admin-nav-icon {
  color: var(--v-accent);
}

.admin-nav-copy {
  min-width: 0;
}

.admin-nav-copy strong {
  display: block;
  overflow: hidden;
  font-size: var(--v-text-base);
  font-weight: 550;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-nav-item.active .admin-nav-copy strong {
  font-weight: 650;
}

.admin-nav-copy small,
.admin-nav-chevron {
  display: none;
}

.admin-nav-badge {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  line-height: 16px;
  text-align: center;
}

.admin-nav-badge.is-accent {
  background: var(--v-accent-muted);
  color: var(--v-accent-hover);
  font-weight: 600;
}

.admin-nav-badge.is-warn {
  background: var(--v-warning-bg);
  color: var(--v-warning);
  font-weight: 600;
}

.admin-mobile-back {
  display: none;
}

/* Section content */
.admin-settings-content {
  display: grid;
  gap: var(--v-space-4);
  width: min(100%, 860px);
  min-width: 0;
}

.admin-settings-content.is-wide {
  width: min(100%, 1060px);
}

.settings-save-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.settings-save-state .icon {
  width: 12px;
  height: 12px;
  color: var(--v-accent);
}

.settings-save-state.is-error {
  color: var(--v-danger-text);
}

/* Account */
.account-identity {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  padding: 16px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.account-avatar {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--v-accent-muted);
  color: var(--v-accent-hover);
  font-size: var(--v-text-md);
  font-weight: 700;
}

.account-identity-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.account-identity-copy strong {
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-lg);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-identity-copy span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.account-role {
  padding: 2px 9px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
}

.account-role.is-admin {
  background: var(--v-accent-muted);
  color: var(--v-accent-hover);
}

.account-password-fields {
  max-width: 440px;
  gap: var(--v-space-3);
}

/* Notifications */
.notification-types-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.notification-event-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
}

.notification-event-grid :deep(.v-checkbox) {
  padding: 10px 12px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
}

.notification-event-grid :deep(.v-checkbox-hint) {
  font-size: var(--v-text-sm);
}

/* Discord */
.discord-bot-fields {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v-space-3) var(--v-space-4);
}

.discord-token-field {
  grid-column: 1 / -1;
}

.discord-invite-row {
  border-top: 1px solid var(--v-divider-subtle);
}

.discord-clear-token {
  color: var(--v-danger-text);
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
  right: 5px;
  width: 30px;
  min-width: 30px;
  height: 30px;
  min-height: 30px;
  color: var(--v-text-muted);
  transform: translateY(-50%);
}

.admin-secret-toggle:hover {
  color: var(--v-text);
}

.delivery-row {
  align-items: start;
  min-height: 0;
}

.delivery-row .settings-list-mark {
  width: 28px;
  height: 28px;
  margin-top: 1px;
}

.delivery-row.is-success .settings-list-mark,
.delivery-row.is-success .delivery-status {
  color: var(--v-accent);
}

.delivery-row.is-danger .settings-list-mark,
.delivery-row.is-danger .delivery-status {
  color: var(--v-danger-text);
}

.delivery-row.is-warn .delivery-status {
  color: var(--v-warning);
}

.delivery-row .settings-list-title {
  font-size: var(--v-text-base);
  font-weight: 550;
}

.delivery-error {
  margin: 4px 0 0;
  color: var(--v-danger-text);
  font-size: var(--v-text-sm);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

/* Download history */
.download-row + .download-row {
  border-top: 1px solid var(--v-divider-subtle);
}

.download-row.is-open {
  background: color-mix(in srgb, var(--v-text) 2%, transparent);
}

.download-mark.is-share {
  background: var(--v-accent-muted);
  color: var(--v-accent-hover);
}

.download-details-chevron {
  width: 12px;
  height: 12px;
  transition: transform var(--v-transition-fast);
}

.download-row.is-open .download-details-chevron {
  transform: rotate(180deg);
}

.download-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px 16px;
  margin: 0 16px 14px 60px;
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
}

.download-detail-grid div {
  min-width: 0;
}

.download-detail-grid dt {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.download-detail-grid dd {
  margin: 2px 0 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  overflow-wrap: anywhere;
}

.download-detail-wide {
  grid-column: 1 / -1;
}

/* Shared links */
.share-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2) var(--v-space-3);
}

.share-toolbar .admin-search-wrap {
  flex: 1 1 220px;
  max-width: 320px;
}

.share-project-list {
  display: grid;
  gap: 10px;
}

.share-project-group {
  overflow: hidden;
  border: 1px solid var(--v-surface-border-soft);
  border-radius: var(--v-radius-lg);
  background: var(--v-surface-canvas);
}

.share-project-header {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto 14px;
  align-items: center;
  gap: var(--v-space-3);
  padding: 12px 16px;
  list-style: none;
  cursor: pointer;
  transition: background-color var(--v-transition-fast);
}

.share-project-header::-webkit-details-marker {
  display: none;
}

.share-project-header:hover {
  background: color-mix(in srgb, var(--v-text) 2.5%, transparent);
}

.share-project-group[open] .share-project-header {
  border-bottom: 1px solid var(--v-divider-subtle);
}

.share-project-thumb {
  width: 52px;
  height: 32px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 700;
}

.share-project-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.share-project-heading {
  min-width: 0;
}

.share-project-heading h3 {
  margin: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 600;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-project-heading p {
  margin: 2px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
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
  color: var(--v-text-muted);
  transition: transform var(--v-transition-fast);
}

.share-project-group[open] .share-project-chevron {
  transform: rotate(180deg);
}

.share-item .settings-list-title {
  font-size: var(--v-text-base);
}

.admin-show-more {
  justify-self: center;
}

/* Modals */
.admin-readonly-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
}

.admin-readonly-field span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.admin-readonly-field strong {
  color: var(--v-text-secondary);
  font-size: var(--v-text-base);
  font-weight: 600;
}

.admin-subsection {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: var(--v-space-3);
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
}

.member-access-divider {
  margin-top: var(--v-space-2);
}

.settings-option-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: var(--v-space-2);
}

/* Narrow screens: a list of sections, then one section with a back link. */
@media (max-width: 900px) {
  .admin-settings-shell {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .admin-settings-shell:not(.is-index) .admin-settings-rail {
    display: none;
  }

  .admin-settings-rail {
    position: static;
  }

  .admin-settings-nav {
    gap: 22px;
  }

  .admin-nav-group h2 {
    padding: 0 4px 4px;
  }

  .admin-nav-list {
    overflow: hidden;
    border: 1px solid var(--v-surface-border-soft);
    border-radius: var(--v-radius-lg);
    background: var(--v-surface-canvas);
    gap: 0;
  }

  .admin-nav-item {
    grid-template-columns: 32px minmax(0, 1fr) auto 14px;
    gap: 12px;
    min-height: 60px;
    padding: 10px 14px;
    border-radius: 0;
    color: var(--v-text);
  }

  .admin-nav-item + .admin-nav-item {
    border-top: 1px solid var(--v-divider-subtle);
  }

  .admin-nav-item:hover {
    background: color-mix(in srgb, var(--v-text) 3%, transparent);
  }

  .admin-nav-icon {
    width: 32px;
    height: 32px;
    border-radius: var(--v-radius-sm);
    background: var(--v-accent-muted);
    color: var(--v-accent);
  }

  .admin-nav-copy strong {
    font-size: var(--v-text-md);
    font-weight: 600;
  }

  .admin-nav-copy small {
    display: block;
    overflow: hidden;
    margin-top: 2px;
    color: var(--v-text-muted);
    font-size: var(--v-text-sm);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-nav-chevron {
    grid-column: 4;
    display: block;
    width: 13px;
    height: 13px;
    color: var(--v-text-dim);
  }

  .admin-mobile-back {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    justify-self: start;
    min-height: 40px;
    margin: -8px 0 0 -6px;
    padding: 0 10px 0 6px;
    border: 0;
    border-radius: var(--v-radius-md);
    background: transparent;
    color: var(--v-accent-hover);
    font: 600 var(--v-text-md)/1 var(--v-font);
    cursor: pointer;
  }

  .admin-mobile-back .icon {
    width: 16px;
    height: 16px;
  }

  .admin-settings-content,
  .admin-settings-content.is-wide {
    width: 100%;
  }
}

@media (max-width: 768px) {
  .admin-page {
    padding: 16px 14px 88px;
  }

  .account-identity {
    padding: 14px;
  }

  .account-password-fields {
    max-width: none;
  }

  .notification-types-head {
    align-items: stretch;
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .notification-event-grid {
    grid-template-columns: 1fr;
  }

  .discord-bot-fields {
    grid-template-columns: 1fr;
  }

  .download-detail-grid {
    grid-template-columns: 1fr 1fr;
    margin: 0 14px 14px;
  }

  .share-toolbar .admin-search-wrap {
    flex-basis: 100%;
    max-width: none;
  }

  .share-project-header {
    grid-template-columns: 44px minmax(0, 1fr) 14px;
    padding: 12px 14px;
  }

  .share-project-thumb {
    width: 44px;
    height: 28px;
  }

  .share-project-counts {
    grid-column: 2 / 3;
    grid-row: 2;
    justify-content: flex-start;
  }

  .share-project-chevron {
    grid-column: 3;
    grid-row: 1;
  }
}
</style>
