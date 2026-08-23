const URL = import.meta.env.VITE_STRIPE_TIP_URL

/** A tip jar, absent entirely unless a link is configured.
 *
 *  A Stripe Payment Link rather than a Checkout session: Stripe hosts the payment page, so
 *  there is no key in this bundle, no webhook to verify, no redirect to trust and nothing
 *  about a payment stored here. Anonymous on purpose -- the app never learns who paid, and
 *  Stripe's dashboard is the only record.
 *
 *  VITE_ variables are inlined at BUILD time, not read at runtime. Unset, this whole
 *  component is dead-code-eliminated and ships zero bytes; set, the URL is baked into the
 *  bundle. Setting it in a hosted server's environment does nothing, because `dist/` was
 *  already built. It has to be present in the build step.
 */
export default function SupportLink() {
  // Absolute https only. A link pasted without its scheme would otherwise resolve as a
  // relative path and quietly send people to a 404 inside this app.
  if (!URL || !URL.startsWith('https://')) return null

  return (
    <p className="support">
      <a className="support-link" href={URL} target="_blank" rel="noopener noreferrer">
        Buy me a coffee
      </a>{' '}
      if this is useful to you. It is a hobby project and there is nothing to unlock.
    </p>
  )
}
