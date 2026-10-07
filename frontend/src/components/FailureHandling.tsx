import './FailureHandling.css'

const STATES = [
  {
    level: 'HIGH',
    className: 'fail--high',
    meaning: 'Extraction trusted for automated downstream use.',
    example: 'Native text heading · confidence 0.98',
  },
  {
    level: 'MEDIUM',
    className: 'fail--medium',
    meaning: 'Usable with review. Ambiguous phrasing or layout edge cases.',
    example: 'Guidance language · confidence 0.72',
  },
  {
    level: 'LOW',
    className: 'fail--low',
    meaning: 'Surface to a human. OCR or structure uncertain.',
    example: 'Scan footnote · confidence 0.41',
  },
  {
    level: 'ERROR',
    className: 'fail--error',
    meaning: 'Do not invent content. Flag the gap and stop guessing.',
    example: 'Unreadable region · confidence 0.12',
  },
]

export default function FailureHandling() {
  return (
    <section className="section section-alt failure" aria-labelledby="failure-title">
      <div className="container">
        <p className="section-label">Failure handling</p>
        <h2 id="failure-title" className="section-title">
          Don&apos;t guess. Flag.
        </h2>
        <p className="section-sub">
          ParseIQ prefers an explicit failure over a confident hallucination. Confidence bands drive
          routing — not silent fills.
        </p>

        <div className="failure__grid" role="list">
          {STATES.map((s) => (
            <article key={s.level} className={`failure__item ${s.className}`} role="listitem">
              <header className="failure__head">
                <span className="failure__level mono">{s.level}</span>
                <span className="failure__meter" aria-hidden="true" />
              </header>
              <p className="failure__meaning">{s.meaning}</p>
              <p className="failure__example mono">{s.example}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
