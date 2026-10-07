import { useState } from 'react'
import './ConfidencePanel.css'

const BLOCK = {
  id: 'BLOCK_007',
  text: 'Revenue increased by 24%.',
  page: 4,
  bbox: '[72, 180, 220, 18]',
  confidence: 0.96,
}

export default function ConfidencePanel() {
  const [lit, setLit] = useState(false)

  return (
    <section className="section confidence" aria-labelledby="confidence-title">
      <div className="container confidence__grid">
        <div>
          <p className="section-label">Confidence & provenance</p>
          <h2 id="confidence-title" className="section-title">
            Every claim is addressable.
          </h2>
          <p className="section-sub">
            Click a structured block to highlight its source region. Downstream systems can trust —
            or escalate — with full spatial context.
          </p>

          <button
            type="button"
            className={`confidence__block ${lit ? 'is-active' : ''}`}
            onClick={() => setLit((v) => !v)}
            aria-pressed={lit}
          >
            <p className="confidence__quote">“{BLOCK.text}”</p>
            <dl className="confidence__meta mono">
              <div>
                <dt>PAGE</dt>
                <dd>{BLOCK.page}</dd>
              </div>
              <div>
                <dt>BBOX</dt>
                <dd>{BLOCK.bbox}</dd>
              </div>
              <div>
                <dt>CONFIDENCE</dt>
                <dd>{BLOCK.confidence.toFixed(2)}</dd>
              </div>
              <div>
                <dt>ID</dt>
                <dd>{BLOCK.id}</dd>
              </div>
            </dl>
          </button>
        </div>

        <div className="confidence__doc" aria-hidden="true">
          <div className="confidence__page">
            <div className="confidence__lines">
              <span /><span /><span /><span /><span />
            </div>
            <div className={`confidence__highlight ${lit ? 'is-lit' : ''}`}>
              <span className="mono">BLOCK_007</span>
              Revenue increased by 24%.
            </div>
            <div className="confidence__lines">
              <span /><span /><span />
            </div>
          </div>
          <p className="confidence__hint mono">
            {lit ? 'Source region highlighted on page 4' : 'Click the block to highlight on document'}
          </p>
        </div>
      </div>
    </section>
  )
}
