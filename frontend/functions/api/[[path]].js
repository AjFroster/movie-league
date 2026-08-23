/** Proxies /api/* through to Cloud Run, so the browser only ever sees one origin.
 *
 *  This is what keeps `api.js` untouched: it asks for a relative `/api`, which in
 *  development the Vite proxy handles and in production this does. Same-origin also means
 *  there is no CORS preflight on any request, and no browser-visible dependency on the
 *  backend's hostname.
 *
 *  A _redirects rule cannot do this job. Its 200 rewrites resolve within the site; sending
 *  a request to another host needs a Function.
 *
 *  API_ORIGIN is set per environment in the Pages dashboard, e.g.
 *  https://movie-league-xxxxxxxx.a.run.app -- no trailing slash.
 */
export async function onRequest({ request, env }) {
  if (!env.API_ORIGIN) {
    return new Response('API_ORIGIN is not set on this Pages environment.', { status: 500 })
  }

  const incoming = new URL(request.url)
  const target = new URL(incoming.pathname + incoming.search, env.API_ORIGIN)

  // Rebuilt rather than passed through: a Request carries its original URL, and cloning it
  // with a new one is the only way to redirect it without losing method, headers or body.
  return fetch(new Request(target, request))
}
