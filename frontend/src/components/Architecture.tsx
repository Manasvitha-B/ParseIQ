import { useState } from 'react'
import './Architecture.css'

interface NodeInfo {
  id: string
  label: string
  detail?: string
}

const NODES: Record<string, NodeInfo> = {
  root: { id: 'root', label: 'PARSEIQ', detail: 'Universal document ingestion engine' },
  p1: {
    id: 'p1',
    label: 'P1 ORCHESTRATOR',
    detail: 'Core parser and orchestration',
  },
  p2a: {
    id: 'p2a',
    label: 'P2A',
    detail: 'Text extraction and OCR',
  },
  p2b: {
    id: 'p2b',
    label: 'P2B',
    detail: 'Layout analysis and reading order',
  },
  p3: {
    id: 'p3',
    label: 'P3',
    detail: 'Tables, charts and mathematical expressions',
  },
  assembly: {
    id: 'assembly',
    label: 'FINAL ASSEMBLY',
    detail: 'Merge typed blocks, resolve reading order, attach provenance',
  },
  out: {
    id: 'out',
    label: 'JSON + MARKDOWN',
    detail: 'Intelligence-ready structured exports',
  },
}

export default function Architecture() {
  const [active, setActive] = useState<string>('p1')
  const info = NODES[active]

  return (
    <section className="section architecture" aria-labelledby="arch-title">
      <div className="container">
        <p className="section-label">Architecture</p>
        <h2 id="arch-title" className="section-title">
          Modular extraction graph.
        </h2>
        <p className="section-sub">
          Hover or select a module to inspect its responsibility. Routing is explicit — not a black box.
        </p>

        <div className="arch__tree">
          <button
            type="button"
            className={`arch__node arch__node--root ${active === 'root' ? 'is-active' : ''}`}
            onMouseEnter={() => setActive('root')}
            onFocus={() => setActive('root')}
            onClick={() => setActive('root')}
          >
            {NODES.root.label}
          </button>

          <div className="arch__spine" aria-hidden="true" />

          <button
            type="button"
            className={`arch__node ${active === 'p1' ? 'is-active' : ''}`}
            onMouseEnter={() => setActive('p1')}
            onFocus={() => setActive('p1')}
            onClick={() => setActive('p1')}
          >
            {NODES.p1.label}
          </button>

          <div className="arch__branch" aria-hidden="true">
            <span /><span /><span />
          </div>

          <div className="arch__row">
            {(['p2a', 'p2b', 'p3'] as const).map((id) => (
              <button
                key={id}
                type="button"
                className={`arch__node arch__node--leaf ${active === id ? 'is-active' : ''}`}
                onMouseEnter={() => setActive(id)}
                onFocus={() => setActive(id)}
                onClick={() => setActive(id)}
              >
                {NODES[id].label}
              </button>
            ))}
          </div>

          <div className="arch__spine arch__spine--short" aria-hidden="true" />

          <button
            type="button"
            className={`arch__node ${active === 'assembly' ? 'is-active' : ''}`}
            onMouseEnter={() => setActive('assembly')}
            onFocus={() => setActive('assembly')}
            onClick={() => setActive('assembly')}
          >
            {NODES.assembly.label}
          </button>

          <div className="arch__spine arch__spine--short" aria-hidden="true" />

          <button
            type="button"
            className={`arch__node arch__node--out ${active === 'out' ? 'is-active' : ''}`}
            onMouseEnter={() => setActive('out')}
            onFocus={() => setActive('out')}
            onClick={() => setActive('out')}
          >
            {NODES.out.label}
          </button>
        </div>

        <aside className="arch__detail" aria-live="polite">
          <p className="arch__detail-label mono">{info.label}</p>
          <p className="arch__detail-body">{info.detail}</p>
        </aside>
      </div>
    </section>
  )
}
