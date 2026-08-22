/** Sign-in, or the absence of it.
 *
 *  Mirrors the backend deliberately: with no VITE_CLERK_PUBLISHABLE_KEY the app runs in
 *  local mode -- no provider, no sign-in, no token -- and the server treats every request
 *  as the single local user. Set the key and identity becomes real.
 *
 *  Signing in is NOT a wall. A visitor with no account still gets the app and every public
 *  league; signing in adds their own leagues and the ability to change anything. Gating the
 *  whole app behind a login made public leagues unreachable, which defeated the point of
 *  having them.
 */
import { useEffect, useState, useSyncExternalStore } from 'react'
import {
  ClerkProvider, SignInButton, SignUpButton, UserButton, useAuth, useUser,
} from '@clerk/react'
import { setTokenProvider } from './api.js'

const KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

export const accountsEnabled = Boolean(KEY)

/** Hands api.js a function that mints a fresh Clerk token per request.
 *
 *  Per request rather than once: Clerk session tokens are short-lived by design, so
 *  caching one here would start returning 401s a minute later. `getToken` serves from
 *  Clerk's own cache and only refreshes when it needs to.
 */
function TokenBridge({ children }) {
  const { getToken, isLoaded } = useAuth()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setTokenProvider(() => getToken())
    setReady(true)
    // Leaving a stale provider behind would sign later requests with a token from a
    // session that has gone.
    return () => setTokenProvider(async () => null)
  }, [getToken])

  // Render nothing until the token provider is installed. Rendering children first would
  // fire the league request unauthenticated and show a signed-in user only public
  // leagues for a beat before correcting itself.
  if (!isLoaded || !ready) return <div className="state-msg">Loading…</div>
  return children
}

// Clerk renders its modal in a portal at the document root, inside its own styling
// system -- this app's CSS variables are not in scope there, so the palette has to be
// handed over explicitly and re-handed whenever the theme changes. Mirrors styles.css.
const CLERK_PALETTE = {
  dark: {
    colorBackground: '#121218', colorInputBackground: '#0a0a0f',
    colorText: '#e4e7f5', colorTextSecondary: '#8890ab', colorInputText: '#e4e7f5',
    colorPrimary: '#e0a339', colorNeutral: '#e4e7f5',
  },
  light: {
    colorBackground: '#ffffff', colorInputBackground: '#f7f6f3',
    colorText: '#15151c', colorTextSecondary: '#565c70', colorInputText: '#15151c',
    colorPrimary: '#9a6206', colorNeutral: '#15151c',
  },
}

/** The resolved theme, read from the DOM attribute the app already owns.
 *
 *  Subscribing to the attribute rather than lifting theme into React state: it is set by
 *  an inline script before React exists, so the DOM is the source of truth and a copy in
 *  state would be a second one to keep in sync.
 */
function useResolvedTheme() {
  return useSyncExternalStore(
    (onChange) => {
      const observer = new MutationObserver(onChange)
      observer.observe(document.documentElement,
                      { attributes: true, attributeFilter: ['data-theme'] })
      return () => observer.disconnect()
    },
    () => document.documentElement.getAttribute('data-theme') || 'dark',
    () => 'dark',
  )
}

export function AuthProvider({ children }) {
  if (!accountsEnabled) return children
  // eslint-disable-next-line react-hooks/rules-of-hooks -- accountsEnabled is a
  // build-time constant, so this branch never changes across renders.
  const theme = useResolvedTheme()
  const appearance = {
    variables: { ...(CLERK_PALETTE[theme] || CLERK_PALETTE.dark), borderRadius: '2px' },
  }
  return (
    <ClerkProvider publishableKey={KEY} afterSignOutUrl="/" appearance={appearance}>
      <TokenBridge>{children}</TokenBridge>
    </ClerkProvider>
  )
}

/** Whether the viewer is signed in. Always true in local mode, where there is one user. */
export function useSignedIn() {
  if (!accountsEnabled) return true
  // eslint-disable-next-line react-hooks/rules-of-hooks -- accountsEnabled is a
  // build-time constant, so this branch never changes across renders.
  const { isSignedIn } = useAuth()
  return Boolean(isSignedIn)
}

/** The signed-in person's display name, or null. */
export function useDisplayName() {
  if (!accountsEnabled) return null
  // eslint-disable-next-line react-hooks/rules-of-hooks -- see useSignedIn.
  const { user } = useUser()
  return user?.firstName || user?.primaryEmailAddress?.emailAddress || null
}

/** The account chip. Renders nothing in local mode, where there is nobody to switch to. */
export function AccountBadge() {
  if (!accountsEnabled) return null
  return <UserButton afterSignOutUrl="/" />
}

/** The side panel: sign-in when signed out, who you are when signed in.
 *  Renders nothing in local mode -- there is one user and no account to manage. */
export function AuthPanel() {
  if (!accountsEnabled) return null
  // eslint-disable-next-line react-hooks/rules-of-hooks -- see useSignedIn.
  const signedIn = useSignedIn()
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const name = useDisplayName()

  if (signedIn) {
    return (
      <aside className="auth-panel">
        <div className="auth-panel-title">SIGNED IN</div>
        <div className="auth-panel-who">
          <AccountBadge />
          <span className="auth-panel-name">{name}</span>
        </div>
        <p className="auth-panel-note">
          Your leagues are listed above the public ones. Only you can change them.
        </p>
      </aside>
    )
  }

  // A modal rather than an embedded <SignIn/>. Clerk's card carries a header, social
  // buttons, a divider, the form and a footer, and sizes itself around 400px -- it
  // overflowed the column and dwarfed the thing it sits beside. The modal is the same
  // flow at a fraction of the resting footprint, and Clerk sizes it against the viewport.
  return (
    <aside className="auth-panel">
      <div className="auth-panel-title">SIGN IN</div>
      <p className="auth-panel-note">
        You are browsing public leagues. Sign in to see your own, draft, and record what
        you have watched.
      </p>
      <div className="auth-panel-actions">
        <SignInButton mode="modal">
          <button className="btn btn-primary">SIGN IN</button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="btn">CREATE ACCOUNT</button>
        </SignUpButton>
      </div>
    </aside>
  )
}
