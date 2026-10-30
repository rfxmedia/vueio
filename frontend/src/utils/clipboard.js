function copyWithSelection(text) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand?.('copy')
  textarea.remove()
  if (!copied) throw new Error('Clipboard is unavailable')
}

// Copy text, or a promise of text that is still loading. Safari allows the
// copy after a click only when the click starts it, so a pending value goes to
// the clipboard at once and the browser waits for it.
export async function copyText(value) {
  const text = Promise.resolve(value)
  if (navigator.clipboard?.write && typeof ClipboardItem === 'function') {
    const blob = text.then(result => new Blob([result], { type: 'text/plain' }))
    blob.catch(() => {})
    try {
      await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })])
      return
    } catch {
      // A value that failed to load is the error to report.
      await text
    }
  }
  const resolved = await text
  try {
    await navigator.clipboard.writeText(resolved)
  } catch {
    copyWithSelection(resolved)
  }
}
