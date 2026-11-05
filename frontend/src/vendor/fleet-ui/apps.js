/* App registry for the shared header — vendored from fleet-ui.
 *
 * In the author's setup this lists every local tool that shares the header. The
 * public build ships only shipyard itself; add entries ({id, label, port, blurb})
 * to link sibling apps.
 *
 * PORTS, NOT URLS. Each entry resolves against the browser's current hostname and
 * scheme at render time, because a hardcoded localhost points at whichever machine
 * is reading the page.
 */

export const FLEET_APPS = [
  { id: 'shipyard', label: 'Shipyard', port: 8845,
    blurb: 'projects, goals, what is owed' },
]

/** Absolute URL for an app, resolved against whoever is doing the reading. */
export function appUrl(app, hostname, protocol) {
  const loc = typeof window !== 'undefined' ? window.location : null
  const host = hostname || (loc ? loc.hostname : 'localhost')
  if (app.url && !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(host)) return app.url
  // `protocol` already carries its trailing colon, hence the bare `//`.
  const scheme = protocol || (loc ? loc.protocol : 'http:')
  return `${scheme}//${host}:${app.port}`
}
