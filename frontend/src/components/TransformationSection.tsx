import './TransformationSection.css'

const STEPS = ['DETECT', 'ROUTE', 'EXTRACT', 'ASSEMBLE'] as const

export default function TransformationSection() {
  return (
    <section id="how-it-works" className="section section-alt transform" aria-labelledby="transform-title">
      <div className="container">
        <p className="section-label">How it works</p>
        <h2 id="transform-title" className="section-title">
          From raw pages to structured output.
        </h2>
        <p className="section-sub">
          ParseIQ does not flatten documents into bags of text. It preserves layout, reading order,
          and provenance through every stage.
        </p>

        <div className="transform__stage">
          <article className="transform__pane transform__pane--raw">
            <header className="transform__pane-head">
              <span className="mono">RAW DOCUMENT</span>
              <span className="mono transform__badge">INPUT</span>
            </header>
            <div className="transform__raw-body">
              <div className="transform__noise" />
              <p className="transform__messy">
                CONFIDENTIAL… Apex Holdings CIM… revenue??? $412M approx ebitda 78…
                <br />
                <span className="transform__skew">table cells misaligned · OCR ghosts · footnote bleed</span>
                <br />
                Q3 pack / diligence — see appendix (scan quality low)
              </p>
              <ul className="transform__raw-meta mono">
                <li>mixed columns</li>
                <li>embedded chart</li>
                <li>no reading order</li>
              </ul>
            </div>
          </article>

          <div className="transform__flow" aria-hidden="true">
            {STEPS.map((step, i) => (
              <div key={step} className="transform__step">
                <span className="transform__step-num mono">{String(i + 1).padStart(2, '0')}</span>
                <span className="transform__step-name mono">{step}</span>
                {i < STEPS.length - 1 && <span className="transform__connector" />}
              </div>
            ))}
          </div>

          <article className="transform__pane transform__pane--out">
            <header className="transform__pane-head">
              <span className="mono">PARSEIQ OUTPUT</span>
              <span className="mono transform__badge transform__badge--ok">STRUCTURED</span>
            </header>
            <div className="transform__out-body">
              <pre className="transform__code mono">{`{
  "type": "heading",
  "text": "Apex Holdings — Q3 2024",
  "confidence": 0.97,
  "bbox": [72, 100, 380, 22]
}
{
  "type": "table",
  "id": "BLOCK_004",
  "provenance": "P3.table"
}`}</pre>
            </div>
          </article>
        </div>
      </div>
    </section>
  )
}
