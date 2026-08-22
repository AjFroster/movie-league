import { useEffect, useState } from 'react'
import { PREFERENCES, applyPreference, resolve, storedPreference } from '../theme.js'

const LABEL = { system: 'AUTO', light: 'LIGHT', dark: 'DARK' }
const TITLE = {
  system: 'Follow your device setting',
  light: 'Always light',
  dark: 'Always dark',
}

/** Three states, not two.
 *
 *  A plain light/dark switch has no way back to "follow my device", so someone who taps it
 *  once is pinned to that choice forever -- including at night, when their phone has
 *  switched and the app has not.
 */
export default function ThemeToggle() {
  const [preference, setPreference] = useState(storedPreference)

  useEffect(() => {
    applyPreference(preference)
    if (preference !== 'system') return
    // Only while following the system: track live changes, so the app flips at sunset
    // along with the OS rather than at the next reload.
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = () => applyPreference('system')
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [preference])

  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      {PREFERENCES.map((value) => (
        <button
          key={value}
          className={`segment${value === preference ? ' selected' : ''}`}
          aria-pressed={value === preference}
          title={value === 'system' ? `${TITLE[value]} (${resolve('system')})` : TITLE[value]}
          onClick={() => setPreference(value)}
        >
          {LABEL[value]}
        </button>
      ))}
    </div>
  )
}
