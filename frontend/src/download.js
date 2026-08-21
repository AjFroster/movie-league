/** Hand a fetched blob to the browser as a file save.
 *
 *  Downloads go through fetch rather than a plain `<a href="/api/export">` so the request
 *  carries whatever headers the API needs -- a bearer token, once there is one -- and so a
 *  failure surfaces as an error in the UI instead of navigating the tab to a JSON error page.
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
