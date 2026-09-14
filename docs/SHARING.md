# Sharing and delivery

Share a specific target with people who do not have a Vue.io account.
Use project membership for ongoing team work.

## Choose the correct share target

| Target | Recipient access |
| --- | --- |
| Project | The project's share-visible content. This is broader than one tracker or file. |
| Vue Dashboard | The selected dashboard and its permitted content. |
| Tracker | Published shot versions and the tracker tools enabled for share visitors. |
| File | The selected file. |
| Folder | The selected folder's permitted contents. Upload options depend on the folder type. |
| File request | Upload-only access to the selected folder. Existing contents stay private. |

Links use current content and permissions. They are not frozen copies of a delivery.
A share does not grant administrator access.
A broad project or folder share can expose more material than a single-file link.

## Create a review link

Remote recipients need a reachable HTTPS address for your Vue.io host.
The host, media storage, and network must remain available.
[Configure remote access](SELF_HOSTING.md#internet-exposure) before sending internet links.

1. Open the target's share action. For a project, use **Share project** in its menu.
2. Confirm the target shown at the top of the dialog.
3. Set **Expiration date**. New links default to 30 days.
4. Set **Password protection** if required.
5. Enable **Allow downloads** if recipients need source files. New links have downloads off by default.
6. Select **Create link**.
7. Select **Copy**.
8. Open the link in a signed-out browser window.
9. Confirm the content, password behavior, and permitted actions.

A password protects entry to the link. It does not identify a particular person.
Anyone who receives the link and password can use them until access ends.
Disabling downloads restricts source-file downloads. It does not disable frame capture in alpha.13.
It also cannot prevent screen recording or copying displayed material.

## Review as a recipient

Open the link and enter its password if required.
Open the intended media, move to the relevant time, and submit a comment.
Enter a name if Vue.io asks for one. A visitor-supplied name is not a verified account identity.
Viewer tools depend on the share target, media type, and tracker settings.

If a new version is missing, ask the owner to check its publication state.
**Awaiting publication** and **Internal** versions do not appear in shares.
[Version publication](REVIEW_WORKFLOW.md#control-which-versions-appear-in-shares)

## Set up a delivery page

1. Open the tracker **Settings**.
2. Enable **Delivery mode**.
3. Set **Greeting override**, **Delivery notes**, or a delivery logo if needed.
4. Add the required delivery links. The tracker accepts up to four.
5. Save the settings.
6. Create a tracker share with **Allow downloads** enabled.
7. Check the resulting link as a signed-out visitor.

The share opens a delivery page. **View tracker** opens its review view.
**Download all** packages the latest share-visible versions, not all revisions or every project file.
Published-version order can differ from internal version order after an older version is republished.

Wait for package preparation and the browser download to finish.
Check the downloaded filenames and contents before treating the delivery as complete.
Captured frames, source media, and comment attachments are different outputs.
A successful preview does not prove that a source download contains the intended delivery.

## Request incoming files

1. Open the intended folder's share action.
2. Enable **Request files**.
3. Set the expiration and optional password.
4. Select **Create link**.
5. Open the link as a signed-out visitor.
6. Enter the requested name.
7. Use **Choose files** or **Choose folder** to upload a small sample.
8. Confirm **Done**, then check that the file appears in the host's intended folder.

A file request enables uploads and disables downloads.
It does not let recipients browse existing folder contents.
Where offered, **Allow file uploads** on a normal folder share is different: recipients can also see its shared contents.
A Vue Dashboard can also include a **Client uploads** block for its configured target.

Keep the upload page open until transfers finish. **Retry** retries a failed item.
**Cancel** stops an active item; **Cancel all** stops active items in the list.
**Clear completed** clears finished entries from the list, not files already uploaded.
Resumable transfer support does not guarantee recovery after every browser or network failure.

Read [Upload safety limits](SELF_HOSTING.md#upload-safety-limits) before a large transfer.
A reverse proxy or tunnel can impose lower limits than Vue.io.

## Change or end access

For project-linked shares, open the share dialog and select **Active shares**.
Use **Edit** to change access options. Use **Revoke** to stop future access.
Administrators can manage workspace links in **Settings → Shared links**.

The edit form can remove expiration: a blank expiration leaves the link available until revoked.
A blank password removes password protection. Check both fields before saving.
Revoking a link cannot recall files already downloaded.
Do not post private links or passwords in public support requests.

## Inspect download records

Administrators can open **Settings → Download history**.
Search the records and inspect the source, transfer details, and recorded result.
History is limited to 180 days and 10,000 events.
A server record does not prove that the recipient verified or retained the file.
