import { useEffect, useState } from 'react'
import { PREFERENCES, applyPreference, resolve, storedPreference } from '../theme.js'

/** Half-filled circle (auto), sun (light), moon (dark).
 *  Inline SVG rather than emoji or unicode glyphs -- ☀/☾ render at wildly different
 *  weights across platforms, and half of them are colour emoji on Windows. */
const ICON = {
  system: (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" />
    </svg>
  ),
  light: (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="3.25" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
        <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15" />
        <path d="M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M12.95 3.05l-1.06 1.06M4.11 11.89l-1.06 1.06" />
      </g>
    </svg>
  ),
  dark: (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M13.2 10.3A5.6 5.6 0 0 1 5.7 2.8a5.6 5.6 0 1 0 7.5 7.5z"
            fill="currentColor" />
    </svg>
  ),
}

const NEXT = { system: 'light', light: 'dark', dark: 'system' }
const DESCRIBE = { system: 'Following your device', light: 'Light', dark: 'Dark' }

/** One button that cycles auto → light → dark → auto.
 *
 *  Three states behind one control, rather than a plain light/dark switch: without a way
 *  back to "follow my device", one tap pins you forever -- including at night, when the
 *  phone has switched and the app has not.
 */
export default function ThemeToggle() {
  const [preference, setPreference] = useState(storedPreference)

  useEffect(() => {
    applyPreference(preference)
    if (preference !== 'system') return
    // Only while following the device: track live changes so the app flips at sunset
    // along with the OS rather than at the next reload.
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = () => applyPreference('system')
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [preference])

  const now = preference === 'system'
    ? `${DESCRIBE.system} (${resolve('system')})`
    : DESCRIBE[preference]

  return (
    <button
      className="theme-toggle"
      title={`Theme: ${now}. Click for ${DESCRIBE[NEXT[preference]].toLowerCase()}.`}
      aria-label={`Theme: ${now}. Click to switch.`}
      onClick={() => setPreference(NEXT[preference])}
    >
      {ICON[preference]}
    </button>
  )
}

export { PREFERENCES }
