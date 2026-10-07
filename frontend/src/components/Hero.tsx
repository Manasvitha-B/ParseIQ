import DocumentVisualizer from './DocumentVisualizer'
import './Hero.css'

export default function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="container hero__grid">
        <div className="hero__copy">
          <p className="section-label hero__eyebrow">
            DATAQUEST 3.0 · DOCUMENT INTELLIGENCE ENGINE
          </p>
          <h1 id="hero-heading" className="hero__title">
            Turn messy documents into structured intelligence.
          </h1>
          <p className="hero__sub">
            ParseIQ extracts, understands and reconstructs complex documents while preserving
            structure, spatial context and provenance.
          </p>
          <div className="hero__actions">
            <a href="#demo" className="btn btn-primary">
              Try the Parser →
            </a>
            <a href="#pipeline" className="btn btn-ghost">
              Explore the Pipeline
            </a>
          </div>
          <p className="hero__tagline mono">Documents in. Intelligence-ready out.</p>
        </div>
        <div className="hero__visual">
          <DocumentVisualizer />
        </div>
      </div>
    </section>
  )
}
