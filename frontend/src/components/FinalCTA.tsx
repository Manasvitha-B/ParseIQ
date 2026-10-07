import './FinalCTA.css'

export default function FinalCTA() {
  return (
    <section className="section final-cta" aria-labelledby="cta-title">
      <div className="container final-cta__inner">
        <p className="section-label">Next step</p>
        <h2 id="cta-title" className="final-cta__title">
          Give your documents structure.
        </h2>
        <a href="#demo" className="btn btn-primary final-cta__btn">
          Launch Parser →
        </a>
        <p className="final-cta__brand mono">ParseIQ · Documents in. Intelligence-ready out.</p>
      </div>
    </section>
  )
}
