import { useEffect, useState } from 'react'
import './DocumentVisualizer.css'

interface Region {
  id: string
  label: string
  className: string
}

const REGIONS: Region[] = [
  { id: 'r1', label: 'TEXT', className: 'dv__region--text' },
  { id: 'r2', label: 'COLUMN_01', className: 'dv__region--col' },
  { id: 'r3', label: 'TABLE', className: 'dv__region--table' },
  { id: 'r4', label: 'FIGURE', className: 'dv__region--figure' },
  { id: 'r5', label: 'EQUATION', className: 'dv__region--eq' },
  { id: 'r6', label: 'BLOCK_07', className: 'dv__region--block' },
]

export default function DocumentVisualizer() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      setActive((i) => (i + 1) % REGIONS.length)
    }, 1800)
    return () => window.clearInterval(id)
  }, [])

  return (
    <div className="dv" aria-hidden="true">
      <div className="dv__coords">
        <span>x:0.00</span>
        <span>y:0.00</span>
        <span>page:1</span>
        <span>dpi:150</span>
      </div>

      <div className="dv__page">
        <div className="dv__scan" />

        <div className="dv__header-lines">
          <div className="dv__line dv__line--lg" />
          <div className="dv__line dv__line--md" />
        </div>

        <div className="dv__body">
          <div className="dv__col">
            <div className="dv__line" />
            <div className="dv__line" />
            <div className="dv__line dv__line--sm" />
            <div className="dv__line" />
            <div className="dv__line dv__line--md" />
          </div>
          <div className="dv__col">
            <div className="dv__line" />
            <div className="dv__line dv__line--sm" />
            <div className="dv__line" />
            <div className="dv__line" />
          </div>
        </div>

        <div className="dv__table">
          {[0, 1, 2, 3].map((row) => (
            <div key={row} className="dv__tr">
              <span /><span /><span /><span />
            </div>
          ))}
        </div>

        <div className="dv__lower">
          <div className="dv__chart">
            <div className="dv__bar" style={{ height: '40%' }} />
            <div className="dv__bar" style={{ height: '70%' }} />
            <div className="dv__bar" style={{ height: '55%' }} />
            <div className="dv__bar" style={{ height: '85%' }} />
          </div>
          <div className="dv__eq">
            <span>E = mc² + Σᵢ αᵢ</span>
          </div>
        </div>

        {REGIONS.map((region, i) => (
          <div
            key={region.id}
            className={`dv__region ${region.className} ${i === active ? 'dv__region--active' : ''}`}
          >
            <span className="dv__bbox-label">{region.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
