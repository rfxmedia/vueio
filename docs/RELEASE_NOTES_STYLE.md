# Vueio release notes

The GitHub Release body is also the changelog owners read inside Vueio. Write
for the person running a media workspace, not for the people who authored the
commits.

## Required writing style

Always write release notes in the ASD-STE100 Simplified Technical English
style. Apply these rules to every heading, bullet, warning, and update
instruction:

- Use short, direct sentences. Keep a sentence at 20 words or fewer when
  practical.
- Use the active voice and the simple present tense. State who or what does the
  action.
- Give one main idea in each sentence. Put conditions before the action when a
  condition is necessary.
- Use common, concrete words. Use one term for one meaning, and use that same
  term throughout the notes.
- Do not use idioms, slang, contractions, marketing language, vague modifiers,
  or unnecessary technical jargon.
- Keep noun groups short. Spell out an uncommon abbreviation the first time
  that it appears.
- Use exact interface labels, commands, product names, and required technical
  terms when changing them would reduce accuracy.

For example, write “Vueio now groups related notifications. This makes the
list easier to scan.” Do not write “We have supercharged the notification
experience for effortless productivity.”

Use these headings when they apply:

- **New** — capabilities users can now rely on.
- **Improved** — visible workflow, performance, or reliability changes.
- **Fixed** — user-facing problems that are resolved.
- **Before you update** — required preparation, known limitations, migration
  time, or behavior that may surprise an owner.

Keep each item short and concrete. State what changed and why it matters. Avoid
commit hashes, internal component names, issue-tracker shorthand, marketing
claims, and raw test output. If no preparation is required, write “Nothing —
the updater handles this release automatically.”

Rollback must be described honestly whenever migrations or compatibility are
relevant: `vueioctl rollback` restores the pre-update backup, so Vueio data
created after that backup is lost. Project files and media are not modified.
