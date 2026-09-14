# Workspace and team

Use projects for related work. Use trackers for shots and revisions.
Use Vue Dashboards for project information and resources.

## Find work and change project status

**Home → Your work** lists assigned shots that need work.
Open a shot to return to its tracker and review context.
The project list provides sorting, filtering, and status grouping.
Users with project-settings access can change status from the project card's status control.
Changing project status does not publish shot versions.

Administrators can use **Search workspace** to find projects, trackers, and files.
Enter at least two characters and select a result.
This global search control is not available to members or share visitors in alpha.13.
Use project navigation and tracker filters for those accounts.

## Add team members

Administrators manage accounts in **Settings → Team**.
A member with **Manage members** access can manage accounts only within their permitted access level.

1. Select **Add member**.
2. Enter a **Username**, **Display name**, and **Password**.
3. Choose **Account type**.
4. For a member, select the required workspace access.
5. Save the account.
6. Give the person their sign-in details through a private channel.

Usernames cannot be changed later. Users can change their password in **Settings → Account**.
Creating an account is not an email invitation or a grant to every project.

## Set project access

Workspace access and project access are separate controls.
An administrator has full workspace access. A member receives the workspace capabilities selected for their account.
These include **Projects**, **Files**, **Manage project content**, **Create projects**, **Delete projects**, and **Manage members**.

The project owner or administrator manages the project's team in project **Settings**.
Add an existing account and choose **Can view** or **Can edit**.
The creator retains owner access. Project access does not override account restrictions or read-only storage.

Members without **Manage project content** have restricted project access.
Assignments determine which shots they can see.
Their project file changes are limited to their own workspace folder.
Assigning a shot can create project membership for the assignee; review access after assigning work.

Use a member account to verify the intended view.
Do not use an administrator account to assess what a restricted user can access.
Share visitors use the separate [share-link rules](SHARING.md).

## Create a Vue Dashboard

1. Open the project.
2. Select **New → Vue Dashboard**.
3. Enter a title.
4. Select **Create Vue Dashboard**.
5. Select **Add block**.
6. Choose a block type and enter its content.

| Block | Use |
| --- | --- |
| **Text** | Write a brief, notes, or project information. |
| **Vue Trackers** | Include selected project trackers. |
| **Resources** | Add links, authorized storage files, or uploaded files. |
| **Client uploads** | Collect files in the configured project target. |

Dashboard edits save automatically. Wait for **Saved**; investigate **Could not save** before leaving the page.
Dashboard edits require project edit access.
Check a shared dashboard as a visitor; team access does not prove share access.
For incoming files, confirm the block's target and upload permissions with a small sample.

## Work with project files

Use **New → Folder** to create a folder in the current project location.
Use **New → Upload Files** to copy files from your browser's computer.
Use **New → Link from storage** to reference available files on authorized host storage.
A link depends on the original storage remaining connected.

A single click selects a sidebar file. Double-click opens it.
Open folders refresh when visible files change.
Large folders, network storage, or files still being written can take longer to update.
See [Automatic folder updates](SELF_HOSTING.md#automatic-folder-updates).

File deletion is not the same as removing a version from a tracker.
Read the confirmation for the selected operation before deleting content.
For moved project folders, use [Change a project folder](STORAGE_OPERATIONS.md#change-a-project-folder).

## Read notifications

The notification tray shows activity that your account can access.
Open a notification to return to the related content.
Use **Settings → Notifications** to select activity categories and delivery channels.
Categories include comments, status, assignments, versions, downloads, and general updates.

Discord delivery needs an administrator-configured bot and channel mapping.
Selecting Discord in personal preferences does not create that connection.
To configure it, an administrator opens **Settings → Notifications**:

1. Enter the bot's **Application ID**, **Public base URL**, and **Bot token**.
2. Save the provider settings.
3. Use **Open invite** to add the bot to the intended Discord server.
4. Give the bot access to the intended channel in Discord.
5. Use **Connect Discord channel**.
6. Select the Vue.io **Recipient**, channel ID, scope, and activity filters.
7. Save the mapping.
8. Select **Test**, then inspect **Delivery history**.

Vue.io evaluates activity using the selected recipient's visibility and preferences.
Discord messages leave your host. Use a channel whose members may receive that project information.
Keep the bot token private. Leave **Mention @everyone** off unless that notification is intentional.

## Connect an agent

An agent uses a key bound to a Vue.io user. It inherits that user's current permissions.
It does not receive unrestricted workspace access merely because it is an agent.

1. Open **Settings → Agent keys**.
2. Select **New key**, or **New personal key** for an administrator's own key.
3. Save the displayed key in the agent's private configuration.
4. Select **Copy skill** for the app-provided API instructions.
5. Configure the agent to send the key in the `X-Vueio-Agent-Key` header.

**New managed key** in this UI creates a key for the current administrator.
For a restricted agent, create a personal key while signed in as the intended member.
The full key is shown once. **Reissue** replaces its value; update the agent after reissuing.
**Reissue and copy skill** also replaces the key. It is not a read-only copy action.
Revoke keys that are no longer needed.

Agents use the application's authenticated API routes.
They remain subject to account access, project roles, assignments, and content visibility.
Host storage registration and browser-only administration do not become available through an agent key.
Do not put a key in a URL, shared document, or public issue.

## Change workspace appearance

Administrators set the team name and logo in **Settings → Team**.
Trackers can override the greeting and logo for their delivery page.
Administrators change workspace colors in **Settings → Theme**.
Check text contrast in the preview before saving changes.
These controls change presentation, not project permissions or storage.
