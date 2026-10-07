import { useCallback, useRef, useState, type DragEvent } from 'react'
import {
  loadSampleDocument,
  uploadDocument,
  type ParseBlock,
  type ParseResult,
} from '../services/parserApi'
import './ParserDemo.css'

type OutputTab = 'structure' | 'json' | 'markdown'
type Stage = 'IDLE' | 'DETECTING' | 'ROUTING' | 'EXTRACTING' | 'ASSEMBLING' | 'COMPLETE'

const STAGE_ORDER: Stage[] = [
  'DETECTING',
  'ROUTING',
  'EXTRACTING',
  'ASSEMBLING',
  'COMPLETE',
]

const FORMATS = ['PDF', 'IMAGE', 'XLSX', 'PPTX'] as const

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
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

  const runWithStages = useCallback(async (job: () => Promise<ParseResult>) => {
    setBusy(true)
    setError(null)
    setResult(null)
    setSelectedBlock(null)

    try {
      for (const s of STAGE_ORDER.slice(0, -1)) {
        setStage(s)
        await sleep(320)
      }
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
            {result?.demoMode && <span className="demo-badge">Demo mode</span>}
          </div>
          <p className="section-sub">
            Upload a document or load the PE diligence sample. When the backend is offline, ParseIQ
            falls back to a clearly labeled simulation.
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
              <p className="demo__drop-sub mono">or click to browse</p>
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
                            left: `${(block.bbox.x / 600) * 100}%`,
                            top: `${(block.bbox.y / 780) * 100}%`,
                            width: `${(block.bbox.w / 600) * 100}%`,
                            height: `${Math.max((block.bbox.h / 780) * 100, 2)}%`,
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
                        {block.text && <p className="demo__block-text">{block.text}</p>}
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
