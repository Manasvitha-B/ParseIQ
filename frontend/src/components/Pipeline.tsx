import './Pipeline.css'

const STAGES = [
  {
    num: '01',
    title: 'DETECT & ROUTE',
    input: 'PDF · IMAGE · XLSX · PPTX',
    processing: 'Format sniff · page raster · module routing',
    output: 'Route plan → P2A / P2B / P3',
  },
  {
    num: '02',
    title: 'EXTRACT & ASSEMBLE',
    input: 'Routed page regions',
    processing: 'OCR · layout · tables · charts · equations',
    output: 'Typed blocks + reading order',
  },
  {
    num: '03',
    title: 'FLAG & FAIL SAFE',
    input: 'Assembled document graph',
    processing: 'Confidence gates · provenance checks',
    output: 'JSON + Markdown · flagged gaps',
  },
]

export default function Pipeline() {
  return (
    <section id="pipeline" className="section section-alt pipeline" aria-labelledby="pipeline-title">
      <div className="container">
        <p className="section-label">Pipeline</p>
        <h2 id="pipeline-title" className="section-title">
          One document. Three stages.
        </h2>
        <p className="section-sub">
          A linear, auditable path from bytes on disk to intelligence-ready structure — with fail-safes
          at every handoff.
        </p>

        <div className="pipeline__track" role="list">
          {STAGES.map((stage, i) => (
            <div key={stage.num} className="pipeline__stage" role="listitem">
              <div className="pipeline__head">
                <span className="pipeline__num mono">{stage.num}</span>
                <h3 className="pipeline__name">{stage.title}</h3>
              </div>

              <dl className="pipeline__io">
                <div>
                  <dt className="mono">INPUT</dt>
                  <dd>{stage.input}</dd>
                </div>
                <div>
                  <dt className="mono">PROCESSING</dt>
                  <dd>{stage.processing}</dd>
                </div>
                <div>
                  <dt className="mono">OUTPUT</dt>
                  <dd>{stage.output}</dd>
                </div>
              </dl>

              {i < STAGES.length - 1 && (
                <div className="pipeline__connector" aria-hidden="true">
                  <svg viewBox="0 0 80 12" preserveAspectRatio="none">
                    <line
                      className="pipeline__line"
                      x1="0"
                      y1="6"
                      x2="80"
                      y2="6"
                      stroke="currentColor"
                      strokeWidth="1"
                      strokeDasharray="4 3"
                    />
                  </svg>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
