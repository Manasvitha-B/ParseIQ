import { useCallback, useEffect, useRef, useState, type DragEvent, type ReactNode } from 'react'
import {
  loadSampleDocument,
  uploadDocument,
  type ParseBlock,
  type ParseResult,
} from '../services/parserApi'
import './ParserDemo.css'

type OutputTab = 'structure' | 'json' | 'markdown'
type Stage = 'IDLE' | 'PROCESSING' | 'COMPLETE'
const STAGE_ORDER: Stage[] = ['PROCESSING', 'COMPLETE']

const FORMATS = ['PDF', 'IMAGE', 'XLSX', 'PPTX'] as const

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function renderBlock(block: ParseBlock): ReactNode {
  const content = object(block.content)
  if (block.type === 'table' && Array.isArray(content.matrix)) {
    const rows = content.matrix.filter(Array.isArray) as unknown[][]
    return <div className="demo__table-wrap"><table className="demo__table"><tbody>
      {rows.map((row, ri) => <tr key={ri}>{row.map((cell, ci) => ri === 0
        ? <th key={ci}>{String(cell ?? '')}</th> : <td key={ci}>{String(cell ?? '')}</td>)}</tr>)}
    </tbody></table></div>
  }
  if (block.type === 'chart' && content.chart) {
    const chart = object(content.chart)
    const series = Array.isArray(chart.series) ? chart.series.map(object) : []
    const entries = series.flatMap((s) => {
      const labels = Array.isArray(s.labels) ? s.labels : []
      const values = Array.isArray(s.values) ? s.values : []
      return values.map((value, i) => ({ label: String(labels[i] ?? i + 1), value: Number(value), name: String(s.name ?? '') }))
        .filter((item, i) => values[i] !== null && values[i] !== '' && Number.isFinite(item.value))
    })
    if (entries.length) {
      const min = Math.min(...entries.map((item) => item.value), 0)
      const max = Math.max(...entries.map((item) => item.value), 1)
      const range = Math.max(max - min, 1)
      const baseline = 25 + (max / range) * 150
      const line = String(chart.chart_type ?? '').toLowerCase().includes('line')
      const points = entries.map((item, i) => `${35 + i * (430 / Math.max(entries.length - 1, 1))},${25 + ((max - item.value) / range) * 150}`).join(' ')
      return <div className="demo__chart-wrap"><p className="demo__chart-title">{String(chart.title || block.text || 'Extracted chart')}</p>
        <svg className="demo__chart" viewBox="0 0 500 230" role="img" aria-label={String(chart.title || 'Extracted chart')}>
          <line x1="35" y1={baseline} x2="475" y2={baseline} stroke="currentColor" />
          <line x1="35" y1="25" x2="35" y2="185" stroke="currentColor" />
          {line ? <polyline points={points} fill="none" stroke="#2ee6a6" strokeWidth="3" /> : entries.map((item, i) => {
            const width = Math.min(42, 360 / entries.length)
            const x = 45 + i * (420 / entries.length)
            const height = (Math.abs(item.value) / range) * 150
            const y = item.value >= 0 ? baseline - height : baseline
            return <g key={`${item.name}-${i}`}><rect x={x} y={y} width={width} height={height} fill="#2ee6a6" />
              <text x={x + width / 2} y="205" textAnchor="middle" fontSize="9" fill="currentColor">{item.label.slice(0, 12)}</text></g>
          })}
        </svg><div className="demo__chart-labels"><span>{String(chart.x_axis ?? '')}</span><span>{String(chart.y_axis ?? '')}</span></div>
      </div>
    }
  }
  const latex = typeof content.latex === 'string' ? content.latex : ''
  if (block.type === 'equation' && latex) return <p className="demo__equation">${latex}$</p>
  return block.text ? <p className="demo__block-text">{block.text}</p> : <p className="demo__empty mono">No readable content in this region</p>
}

export default function ParserDemo() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState<Stage>('IDLE')
  const [result, setResult] = useState<ParseResult | null>(null)
  const [tab, setTab] = useState<OutputTab>('structure')
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [visionProvider, setVisionProvider] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetch('/api/health')
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((health: { vision_provider?: string | null }) => {
        if (active) setVisionProvider(health.vision_provider ?? '')
      })
      .catch(() => { if (active) setVisionProvider('offline') })
    return () => { active = false }
  }, [])

  const runWithStages = useCallback(async (job: () => Promise<ParseResult>) => {
    setBusy(true)
    setError(null)
    setResult(null)
    setSelectedBlock(null)

    try {
      setStage('PROCESSING')
      const data = await job()
      setStage('COMPLETE')
      setResult(data)
      if (data.blocks[0]) setSelectedBlock(data.blocks[0].id)
    } catch (e) {
      setStage('IDLE')
      setError(e instanceof Error ? e.message : 'Parse failed')
    } finally {
      setBusy(false)
    }
  }, [])

  const onFile = useCallback(
    (file: File | undefined) => {
      if (!file || busy) return
      void runWithStages(() => uploadDocument(file))
    },
    [busy, runWithStages],
  )

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    onFile(e.dataTransfer.files[0])
  }

  const onSample = () => {
    if (busy) return
    void runWithStages(() => loadSampleDocument())
  }

  const activeBlock: ParseBlock | undefined = result?.blocks.find((b) => b.id === selectedBlock)

  return (
    <section id="demo" className="section section-alt demo" aria-labelledby="demo-title">
      <div className="container">
        <div className="demo__intro">
          <p className="section-label">Live demo</p>
          <div className="demo__title-row">
            <h2 id="demo-title" className="section-title">
              Parser workstation
            </h2>
            {result && <span className="demo-badge">{String(result.status).toUpperCase()}</span>}
            {visionProvider !== null && <span className="demo-badge">{visionProvider === 'offline' ? 'BACKEND OFFLINE' : visionProvider ? `VISION · ${visionProvider} CONFIGURED` : 'VISION KEY NOT CONFIGURED'}</span>}
          </div>
            <p className="section-sub">
            Upload a document or load the sample. Results below come from the ParseIQ backend and include its extracted JSON.
          </p>
        </div>

        <div className="demo__stages" aria-live="polite">
          {STAGE_ORDER.map((s) => (
            <span
              key={s}
              className={`demo__stage mono ${stage === s ? 'is-active' : ''} ${
                STAGE_ORDER.indexOf(s) < STAGE_ORDER.indexOf(stage) ? 'is-done' : ''
              }`}
            >
              {s}
            </span>
          ))}
        </div>

        <div className="demo__grid">
          {/* LEFT — upload */}
          <div className="demo__panel demo__upload">
            <p className="demo__panel-label mono">INPUT</p>
            <div
              className={`demo__drop ${dragging ? 'is-dragging' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <p className="demo__drop-title">Drop a document</p>
              <p className="demo__drop-sub mono">or click to browse · PDF, image, XLSX or PPTX</p>
              <button
                type="button"
                className="btn btn-ghost demo__browse"
                disabled={busy}
                onClick={() => inputRef.current?.click()}
              >
                Choose file
              </button>
              <input
                ref={inputRef}
                type="file"
                className="demo__file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.pptx,image/*"
                onChange={(e) => onFile(e.target.files?.[0])}
              />
            </div>

            <ul className="demo__formats" aria-label="Supported formats">
              {FORMATS.map((f) => (
                <li key={f} className="mono">
                  {f}
                </li>
              ))}
            </ul>

            <button type="button" className="btn btn-primary demo__sample" disabled={busy} onClick={onSample}>
              {busy ? 'Processing…' : 'Load Sample Document'}
            </button>

            {error && <p className="demo__error mono" role="alert">{error}</p>}
          </div>

          {/* CENTER — preview */}
          <div className="demo__panel demo__preview">
            <p className="demo__panel-label mono">DOCUMENT PREVIEW</p>
            <div className="demo__page">
              {result ? (
                <>
                  <div className="demo__page-meta mono">
                    <span>{result.filename}</span>
                    <span>
                      p.{activeBlock?.page ?? 1}/{result.pageCount}
                    </span>
                  </div>
                  <div className="demo__page-canvas">
                    {result.blocks
                      .filter((b) => b.page === (activeBlock?.page ?? result.blocks[0]?.page ?? 1))
                      .map((block) => (
                        <button
                          key={block.id}
                          type="button"
                          className={`demo__bbox ${selectedBlock === block.id ? 'is-selected' : ''}`}
                          style={{
                            left: `${(block.bbox.x / (result.pageSizes[block.page]?.width || 612)) * 100}%`,
                            top: `${(block.bbox.y / (result.pageSizes[block.page]?.height || 792)) * 100}%`,
                            width: `${(block.bbox.w / (result.pageSizes[block.page]?.width || 612)) * 100}%`,
                            height: `${Math.max((block.bbox.h / (result.pageSizes[block.page]?.height || 792)) * 100, 1)}%`,
                          }}
                          onClick={() => setSelectedBlock(block.id)}
                          title={block.id}
                        >
                          <span className="demo__bbox-tag mono">{block.type}</span>
                        </button>
                      ))}
                    {!result.blocks.length && (
                      <p className="demo__empty mono">No spatial blocks returned</p>
                    )}
                  </div>
                </>
              ) : (
                <div className="demo__placeholder">
                  <p className="mono">Awaiting document</p>
                  <p>Load a sample or upload to preview detected regions.</p>
                </div>
              )}
            </div>
          </div>

          {/* RIGHT — output */}
          <div className="demo__panel demo__output">
            <p className="demo__panel-label mono">STRUCTURED OUTPUT</p>
            <div className="demo__tabs" role="tablist" aria-label="Output format">
              {(
                [
                  ['structure', 'STRUCTURE'],
                  ['json', 'JSON'],
                  ['markdown', 'MARKDOWN'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  className={`demo__tab mono ${tab === key ? 'is-active' : ''}`}
                  onClick={() => setTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="demo__out-body" role="tabpanel">
              {!result && <p className="demo__empty mono">No output yet</p>}

              {result && tab === 'structure' && (
                <ul className="demo__blocks">
                  {result.blocks.map((block) => (
                    <li key={block.id}>
                      <button
                        type="button"
                        className={`demo__block ${selectedBlock === block.id ? 'is-selected' : ''}`}
                        onClick={() => setSelectedBlock(block.id)}
                      >
                        <div className="demo__block-top mono">
                          <span>{block.id}</span>
                          <span>TYPE {block.type}</span>
                        </div>
                        <div className="demo__block-meta mono">
                          <span>PAGE {block.page}</span>
                          <span>CONFIDENCE {Math.round(block.confidence * 100)}%</span>
                          {block.flag && <span className={`demo__flag demo__flag--${block.flag.toLowerCase()}`}>{block.flag}</span>}
                        </div>
                        {renderBlock(block)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {result && tab === 'json' && (
                <pre className="demo__code mono">{JSON.stringify(result.json, null, 2)}</pre>
              )}

              {result && tab === 'markdown' && (
                <pre className="demo__code mono">{result.markdown}</pre>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
