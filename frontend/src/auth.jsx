/** Sign-in, or the absence of it.
 *
 *  Mirrors the backend deliberately: with no VITE_CLERK_PUBLISHABLE_KEY the app runs in
 *  local mode -- no provider, no sign-in wall, no token -- and the server treats every
 *  request as the single local user. Set the key and the same screens require a real
 *  account. Nothing in between, and no toggle that "disables auth" on a real deployment:
 *  the server refuses to start in local mode unless it is on SQLite and localhost.
 */
import { useEffect, useState } from 'react'
import { ClerkProvider, Show, SignIn, UserButton, useAuth, useUser } from '@clerk/react'
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
    // Leaving a stale provider behind after unmount would sign later requests with a
    // token from a session that has gone.
    return () => setTokenProvider(async () => null)
  }, [getToken])

  if (!isLoaded || !ready) return <div className="state-msg">Signing in…</div>
  return children
}

export function AuthProvider({ children }) {
  if (!accountsEnabled) return children

  return (
    <ClerkProvider publishableKey={KEY} afterSignOutUrl="/">
      <TokenBridge>
        {/* v6 replaced <SignedIn>/<SignedOut> with <Show when="...">. */}
        <Show when="signed-in">{children}</Show>
        <Show when="signed-out">
          <div className="signin-page">
            <h1 className="league-wordmark"><span className="header-mark" />Movie League</h1>
            <p className="league-subtitle">Sign in to see your leagues.</p>
            <SignIn routing="hash" />
          </div>
        </Show>
      </TokenBridge>
    </ClerkProvider>
  )
}

/** The account chip for the header. Renders nothing at all in local mode. */
export function AccountBadge() {
  if (!accountsEnabled) return null
  return <UserButton afterSignOutUrl="/" />
}

/** The signed-in person's display name, or null in local mode. */
export function useDisplayName() {
  if (!accountsEnabled) return null
  // eslint-disable-next-line react-hooks/rules-of-hooks -- accountsEnabled is a
  // build-time constant, so this branch never changes across renders.
  const { user } = useUser()
  return user?.firstName || user?.primaryEmailAddress?.emailAddress || null
}
