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
import { useEffect, useState } from 'react'
import { ClerkProvider, SignIn, UserButton, useAuth, useUser } from '@clerk/react'
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

export function AuthProvider({ children }) {
  if (!accountsEnabled) return children
  return (
    <ClerkProvider publishableKey={KEY} afterSignOutUrl="/">
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

  return (
    <aside className="auth-panel">
      <div className="auth-panel-title">SIGN IN</div>
      <p className="auth-panel-note">
        Browsing public leagues. Sign in to see your own, draft, and record what you have
        watched.
      </p>
      <SignIn routing="hash" appearance={{ elements: { rootBox: { width: '100%' } } }} />
    </aside>
  )
}
