/** Hand a fetched blob to the browser as a file save.
 *
 *  Via fetch rather than a plain `<a href>` so the request carries the bearer token, and
 *  so a failure shows in the UI instead of navigating the tab to a JSON error page.
 */
export function saveBlob({ blob, filename }) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoking in the same tick cancels the save in some browsers; one turn of the loop is
  // enough for the click to have been handed off.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
