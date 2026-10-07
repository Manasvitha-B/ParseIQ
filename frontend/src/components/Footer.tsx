import './Footer.css'

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__inner">
        <div className="footer__brand">
          <span className="footer__mark" aria-hidden="true" />
          <span className="footer__name">ParseIQ</span>
        </div>
        <p className="footer__tag mono">DATAQUEST 3.0 · Document Intelligence Engine</p>
        <nav className="footer__links" aria-label="Footer">
          <a href="#how-it-works">How It Works</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#pipeline">Pipeline</a>
          <a href="#demo">Demo</a>
        </nav>
        <p className="footer__copy mono">© {new Date().getFullYear()} ParseIQ. Technical demo.</p>
      </div>
    </footer>
  )
}
