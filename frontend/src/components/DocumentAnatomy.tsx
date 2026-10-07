import { useState } from 'react'
import './DocumentAnatomy.css'

interface AnatomyLabel {
  id: string
  label: string
  position: string
  region: string
  explanation: string
}

const LABELS: AnatomyLabel[] = [
  {
    id: 'text',
    label: 'TEXT',
    position: 'anatomy__pin--tl',
    region: 'anatomy__hot--title',
    explanation: 'Native text layers and glyph runs with character-level bounding boxes.',
  },
  {
    id: 'ocr',
    label: 'OCR',
    position: 'anatomy__pin--tr',
    region: 'anatomy__hot--body',
    explanation: 'Fallback OCR for scanned or image-only regions with confidence scoring.',
  },
  {
    id: 'layout',
    label: 'LAYOUT',
    position: 'anatomy__pin--ml',
    region: 'anatomy__hot--cols',
    explanation: 'Column detection, margins, and spatial document coordinates.',
  },
  {
    id: 'order',
    label: 'READING ORDER',
    position: 'anatomy__pin--mr',
    region: 'anatomy__hot--cols',
    explanation: 'Human reading sequence reconstructed across multi-column layouts.',
  },
  {
    id: 'table',
    label: 'TABLE',
    position: 'anatomy__pin--bl',
    region: 'anatomy__hot--table',
    explanation: 'Cell structure, headers, and numeric cell typing preserved as tables.',
  },
  {
    id: 'chart',
    label: 'CHART',
    position: 'anatomy__pin--bm',
    region: 'anatomy__hot--chart',
    explanation: 'Figure regions classified and linked to nearby captions.',
  },
  {
    id: 'equation',
    label: 'EQUATION',
    position: 'anatomy__pin--br',
    region: 'anatomy__hot--eq',
    explanation: 'Mathematical expressions isolated for specialized extraction.',
  },
  {
    id: 'prov',
    label: 'PROVENANCE',
    position: 'anatomy__pin--lt',
    region: 'anatomy__hot--title',
    explanation: 'Every block traces back to page, module, and source region.',
  },
  {
    id: 'conf',
    label: 'CONFIDENCE',
    position: 'anatomy__pin--rt',
    region: 'anatomy__hot--body',
    explanation: 'Per-block confidence enables downstream fail-safe routing.',
  },
]

export default function DocumentAnatomy() {
  const [active, setActive] = useState<string | null>(null)
  const current = LABELS.find((l) => l.id === active)

  return (
    <section id="capabilities" className="section anatomy" aria-labelledby="anatomy-title">
      <div className="container">
        <p className="section-label">Capabilities</p>
        <h2 id="anatomy-title" className="section-title">
          Document anatomy, fully instrumented.
        </h2>
        <p className="section-sub">
          Hover a label to highlight the corresponding region. ParseIQ treats structure as a
          first-class signal — not an afterthought.
        </p>

        <div className="anatomy__stage">
          {LABELS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`anatomy__pin mono ${item.position} ${active === item.id ? 'is-active' : ''}`}
              onMouseEnter={() => setActive(item.id)}
              onFocus={() => setActive(item.id)}
              onMouseLeave={() => setActive(null)}
              onBlur={() => setActive(null)}
              aria-describedby="anatomy-explain"
            >
              {item.label}
            </button>
          ))}

          <div className="anatomy__doc" role="img" aria-label="Document preview with annotated regions">
            <div className={`anatomy__hot anatomy__hot--title ${current?.region === 'anatomy__hot--title' ? 'is-lit' : ''}`} />
            <div className={`anatomy__hot anatomy__hot--body ${current?.region === 'anatomy__hot--body' ? 'is-lit' : ''}`} />
            <div className={`anatomy__hot anatomy__hot--cols ${current?.region === 'anatomy__hot--cols' ? 'is-lit' : ''}`} />
            <div className={`anatomy__hot anatomy__hot--table ${current?.region === 'anatomy__hot--table' ? 'is-lit' : ''}`} />
            <div className={`anatomy__hot anatomy__hot--chart ${current?.region === 'anatomy__hot--chart' ? 'is-lit' : ''}`} />
            <div className={`anatomy__hot anatomy__hot--eq ${current?.region === 'anatomy__hot--eq' ? 'is-lit' : ''}`} />

            <div className="anatomy__fake-title" />
            <div className="anatomy__fake-lines">
              <span /><span /><span /><span />
            </div>
            <div className="anatomy__fake-table" />
            <div className="anatomy__fake-lower">
              <div className="anatomy__fake-chart" />
              <div className="anatomy__fake-eq" />
            </div>
          </div>
        </div>

        <p id="anatomy-explain" className="anatomy__explain mono" aria-live="polite">
          {current ? current.explanation : 'Select a capability label to inspect the region.'}
        </p>
      </div>
    </section>
  )
}
