import { useEffect, useState } from 'react'
import './Navbar.css'

const LINKS = [
  { href: '#how-it-works', label: 'How It Works' },
  { href: '#capabilities', label: 'Capabilities' },
  { href: '#pipeline', label: 'Pipeline' },
  { href: '#demo', label: 'Demo' },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`nav ${scrolled ? 'nav--scrolled' : ''}`}>
      <div className="nav__inner container">
        <a href="#" className="nav__brand" aria-label="ParseIQ home">
          <span className="nav__mark" aria-hidden="true" />
          <span className="nav__name">ParseIQ</span>
        </a>

        <nav className={`nav__links ${open ? 'nav__links--open' : ''}`} aria-label="Primary">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="nav__link"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <a href="#demo" className="btn btn-primary nav__cta" onClick={() => setOpen(false)}>
            Launch Parser
          </a>
        </nav>

        <button
          type="button"
          className="nav__toggle"
          aria-expanded={open}
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          <span />
          <span />
        </button>
      </div>
    </header>
  )
}
