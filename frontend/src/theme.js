/** Light/dark theming.
 *
 *  "system" resolves to light or dark in JS, so `data-theme` is always one of two
 *  concrete values and no CSS rule has to handle its absence. The first resolution runs
 *  from an inline script in index.html, before paint -- doing it in React would flash a
 *  full white screen on this dark-first palette.
 */
export const STORAGE_KEY = 'movie-league-theme'
export const PREFERENCES = ['system', 'light', 'dark']

export function storedPreference() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return PREFERENCES.includes(saved) ? saved : 'system'
  } catch {
    // Safari in private mode throws on localStorage. A theme is not worth an error page.
    return 'system'
  }
}

export function resolve(preference) {
  if (preference === 'light' || preference === 'dark') return preference
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyPreference(preference) {
  document.documentElement.setAttribute('data-theme', resolve(preference))
  try {
    // "system" is the absence of a choice, so it is stored as the absence of a key --
    // otherwise a user who picks system is pinned to whatever it meant that day.
    if (preference === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, preference)
  } catch { /* see storedPreference */ }
}

/** Kept in sync with the above by hand; it is inlined into index.html as a string.
 *  Deliberately tiny and dependency-free: it runs before the bundle exists. */
export const THEME_BOOT_SCRIPT = `
(function () {
  try {
    var saved = localStorage.getItem('${STORAGE_KEY}');
    var dark = saved === 'dark' || (saved !== 'light' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`
