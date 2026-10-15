import React, { useEffect, useMemo, useState } from 'react'
import { marked } from 'marked'
import { Loading } from './ui'

const MARKDOWN = /\.(md|markdown|rst)$/i

/* A repo's own documents, read in place.

   Deliberately read-only, unlike the argument editor. An argument is shipyard's
   own artifact and it owns the write; ARCHITECTURE.md and the ADRs belong to the
   repo and to whatever wrote them. Showing them without offering to edit is the
   honest boundary. */
export function DocPage({ pid, path, onClose }) {
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setDoc(null); setError(null)
    fetch(`/api/projects/${encodeURIComponent(pid)}/doc?path=${encodeURIComponent(path)}`)
      .then(r => r.json().then(b => r.ok ? b : Promise.reject(b.detail || 'could not read that')))
      .then(setDoc)
      .catch(e => setError(String(e)))
  }, [pid, path])

  const isDoc = MARKDOWN.test(path)
  const { html, toc } = useMemo(
    () => (doc && isDoc ? render(stripFrontmatter(doc.body)) : { html: '', toc: [] }),
    [doc, isDoc])

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <button onClick={onClose}
        className="mb-5 text-meta text-faint transition hover:text-accent">
        ← {pid}
      </button>

      {error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-body text-danger">
          {error}
        </p>
      ) : !doc ? (
        <Loading />
      ) : (
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_13rem]">
          <div className="min-w-0">
            <header className="mb-8">
              <h1 className="text-page font-medium tracking-tight">{title(doc)}</h1>
              <code className="mt-1 block text-meta text-faint">
                {doc.path}
              </code>
            </header>

            {isDoc ? (
              <article className="md-prose" dangerouslySetInnerHTML={{ __html: html }} />
            ) : (
              /* A source file is not prose. Running it through a markdown parser
                 mangles it — indented lines become code blocks, `#` becomes a
                 heading, underscores become emphasis. */
              <div className="md-prose md-source">
                <pre data-lang={path.split('.').pop()}><code>{doc.body}</code></pre>
              </div>
            )}
          </div>

          {toc.length > 2 && (
            <aside className="hidden lg:block">
              <div className="sticky top-24">
                <p className="mb-2 fleet-label">On this page</p>
                <nav className="space-y-1 border-l border-border">
                  {toc.map(h => (
                    <a key={h.id} href={`#${h.id}`}
                      onClick={e => {
                        // The app routes on the hash, so a bare anchor href would
                        // navigate away from the document instead of scrolling in it.
                        e.preventDefault()
                        document.getElementById(h.id)
                          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                      }}
                      className={`block truncate border-l-2 border-transparent text-micro leading-relaxed text-faint transition
                          hover:border-accent hover:text-accent ${h.level === 3 ? 'pl-5' : 'pl-3'}`}>
                      {h.text}
                    </a>
                  ))}
                </nav>
              </div>
            </aside>
          )}
        </div>
      )}
    </main>
  )
}

/* The document's own H1 is a better title than its filename — "Development Protocol
   1.0" beats "0001-development-protocol.md". Falls back to the name. */
function title(doc) {
  const m = /^#\s+(.+)$/m.exec(stripFrontmatter(doc.body) || '')
  return m ? m[1].trim() : doc.name
}

function slug(text) {
  return String(text).toLowerCase().trim()
    .replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 60) || 'section'
}

/* marked gives correct HTML; what it does not give is the structure a document
   *reader* needs. Rather than override its renderer — which changes shape between
   versions — the output is walked once in the DOM we already have. */
function render(md) {
  const doc = new DOMParser().parseFromString(marked.parse(md, { breaks: false }), 'text/html')

  // Tables carry their own width and must scroll rather than force the page to.
  doc.querySelectorAll('table').forEach(t => {
    const wrap = doc.createElement('div')
    wrap.className = 'md-table-wrap'
    t.replaceWith(wrap)
    wrap.appendChild(t)
  })

  // Name the language on the frame. 62 of the fenced blocks in these repos are
  // shell, and knowing that without reading the first line is most of the value.
  doc.querySelectorAll('pre > code[class*="language-"]').forEach(c => {
    const lang = (c.className.match(/language-([\w+#-]+)/) || [])[1]
    if (lang && lang !== 'text') c.parentElement.setAttribute('data-lang', lang)
  })

  const toc = []
  const seen = new Set()
  doc.querySelectorAll('h2, h3').forEach(h => {
    let id = slug(h.textContent)
    while (seen.has(id)) id += '-x'
    seen.add(id)
    h.id = id
    toc.push({ id, text: h.textContent, level: h.tagName === 'H3' ? 3 : 2 })
    const a = doc.createElement('a')
    a.className = 'md-anchor'
    a.href = `#${id}`
    a.textContent = '#'
    h.appendChild(a)
  })

  return { html: doc.body.innerHTML, toc }
}

/* ADRs and manifests often open with YAML frontmatter, which marked renders as a
   stray horizontal rule and a run-on paragraph. */
function stripFrontmatter(body) {
  const s = String(body || '')
  if (!s.startsWith('---\n')) return s
  const end = s.indexOf('\n---', 4)
  return end === -1 ? s : s.slice(end + 4).replace(/^\n+/, '')
}
