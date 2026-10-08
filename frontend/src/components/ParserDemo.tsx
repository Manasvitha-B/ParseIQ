import { useCallback, useEffect, useRef, useState, type DragEvent, type ReactNode } from 'react'
import {
  loadSampleDocument,
  uploadDocument,
  type ParseBlock,
  type ParseResult,
} from '../services/parserApi'
import './ParserDemo.css'

type OutputTab = 'plots' | 'structure' | 'preview' | 'json' | 'markdown'
type Stage = 'IDLE' | 'PROCESSING' | 'COMPLETE'
const STAGE_ORDER: Stage[] = ['PROCESSING', 'COMPLETE']

const FORMATS = ['PDF', 'IMAGE', 'XLSX', 'PPTX'] as const

function readableLabel(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function isPlotImage(value: unknown): value is string {
  return typeof value === 'string' &&
    /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$/.test(value)
}

function parseMarkdownTable(value: string): string[][] | null {
  const rows = value.split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith('|') && line.endsWith('|'))
    .map((line) => line.slice(1, -1).split('|').map((cell) => cell.trim()))
  if (rows.length < 2 || !rows[1].every((cell) => /^:?-{3,}:?$/.test(cell))) return null
  return [rows[0], ...rows.slice(2)]
}

function JsonPreviewValue({ label, value }: { label: string; value: unknown }) {
  if (label === 'python_code') return null

  if (label === 'plot_image') {
    return isPlotImage(value)
      ? <figure className="demo__preview-plot">
        <figcaption className="demo__preview-label">Rendered chart</figcaption>
        <img src={value} alt="Chart generated from the extracted document data" />
      </figure>
      : <p className="demo__preview-muted">No chart image was generated for this extraction.</p>
  }

  if (label === 'data_table_markdown' && typeof value === 'string') {
    const rows = parseMarkdownTable(value)
    if (rows) return <section className="demo__preview-section">
      <h4 className="demo__preview-heading">Extracted Data</h4>
      <div className="demo__table-wrap"><table className="demo__table">
        <thead><tr>{rows[0].map((cell, index) => <th key={index}>{cell}</th>)}</tr></thead>
        <tbody>{rows.slice(1).map((row, rowIndex) => <tr key={rowIndex}>
          {row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
        </tr>)}</tbody>
      </table></div>
    </section>
  }

  if (value === null || typeof value !== 'object') {
    const displayValue = value === null ? 'Not provided'
      : typeof value === 'boolean' ? value ? 'Yes' : 'No'
        : String(value)
    return <div className="demo__preview-field">
      <span className="demo__preview-label">{readableLabel(label)}</span>
      <span className="demo__preview-value">{displayValue}</span>
    </div>
  }

  if (Array.isArray(value)) {
    if (value.length > 0 && value.every(Array.isArray)) {
      const rows = value as unknown[][]
      return <section className="demo__preview-section">
        <h4 className="demo__preview-heading">{readableLabel(label)}</h4>
        <div className="demo__table-wrap"><table className="demo__table">
          <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) =>
            rowIndex === 0
              ? <th key={cellIndex}>{String(cell ?? '')}</th>
              : <td key={cellIndex}>{String(cell ?? '')}</td>,
          )}</tr>)}</tbody>
        </table></div>
      </section>
    }

    return <section className="demo__preview-section">
      <h4 className="demo__preview-heading">{readableLabel(label)} <span>{value.length}</span></h4>
      {value.length
        ? <div className={value.every((item) => item !== null && typeof item === 'object') ? 'demo__preview-cards' : 'demo__preview-list'}>
          {value.map((item, index) => <JsonPreviewValue
            key={index}
            label={item !== null && typeof item === 'object' && !Array.isArray(item) && typeof (item as Record<string, unknown>).name === 'string'
              ? String((item as Record<string, unknown>).name)
              : String(index + 1)}
            value={item}
          />)}
        </div>
        : <p className="demo__preview-muted">No items</p>}
    </section>
  }

  const entries = Object.entries(value as Record<string, unknown>)
  const tableHeaders = (value as Record<string, unknown>).headers
  const tableRows = (value as Record<string, unknown>).rows
  const displayEntries = entries.filter(([key]) => !['headers', 'rows', 'python_code', 'plot_image'].includes(key))
  const plotImage = (value as Record<string, unknown>).plot_image
  return <section className="demo__preview-section">
    <h4 className="demo__preview-heading">{readableLabel(label)}</h4>
    {displayEntries.length > 0 && (
      <div className="demo__preview-fields">
        {displayEntries.map(([key, child]) =>
          <JsonPreviewValue key={key} label={key} value={child} />,
        )}
      </div>
    )}
    {plotImage !== undefined && <JsonPreviewValue label="plot_image" value={plotImage} />}
    {Array.isArray(tableHeaders) && Array.isArray(tableRows) && (
      <div className="demo__table-wrap"><table className="demo__table">
        <thead><tr>{tableHeaders.map((header, index) => <th key={index}>{String(header ?? '')}</th>)}</tr></thead>
        <tbody>{tableRows.map((row, rowIndex) => <tr key={rowIndex}>
          {(Array.isArray(row) ? row : [row]).map((cell, cellIndex) => <td key={cellIndex}>{String(cell ?? '')}</td>)}
        </tr>)}</tbody>
      </table></div>
    )}
    {!entries.length && <p className="demo__preview-muted">No details</p>}
  </section>
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function pieSlicePath(cx: number, cy: number, radius: number, start: number, end: number): string {
  const point = (angle: number) => ({
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  })
  const from = point(start)
  const to = point(end)
  const largeArc = end - start > Math.PI ? 1 : 0
  return `M ${cx} ${cy} L ${from.x} ${from.y} A ${radius} ${radius} 0 ${largeArc} 1 ${to.x} ${to.y} Z`
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
    const normalizedSeries = series.map((s, index) => {
      const labels = Array.isArray(s.labels) ? s.labels : []
      const values = Array.isArray(s.values) ? s.values : []
      return {
        name: String(s.name ?? `Series ${index + 1}`),
        estimated: Boolean(s.estimated ?? chart.estimated),
        xValues: Array.isArray(s.x_values) ? s.x_values.map((value) => value === null ? null : Number(value)) : [],
        points: values.map((value, i) => ({
          label: String(labels[i] ?? i + 1),
          value: value === null || value === '' ? null : Number(value),
          x: Array.isArray(s.x_values) && s.x_values[i] !== null && Number.isFinite(Number(s.x_values[i])) ? Number(s.x_values[i]) : null,
        })).filter((item) => item.value === null || Number.isFinite(item.value)),
      }
    })
    const categories = [...new Set(normalizedSeries.flatMap((item) => item.points.map((point) => point.label)))]
    const allValues = normalizedSeries.flatMap((item) => item.points.map((point) => point.value))
      .filter((value): value is number => value !== null)
    const min = Math.min(...allValues, 0)
    const max = Math.max(...allValues, 1)
    const range = Math.max(max - min, 1)
    const y = (value: number) => 190 - ((value - min) / range) * 145
    const numericX = normalizedSeries.flatMap((item) => item.points.map((point) => point.x)).filter((value): value is number => value !== null)
    const minX = Math.min(...numericX, 0)
    const maxX = Math.max(...numericX, 1)
    const x = (label: string, value: number | null) => numericX.length
      ? 48 + (((value ?? minX) - minX) / Math.max(maxX - minX, 1)) * 420
      : 48 + categories.indexOf(label) * (420 / Math.max(categories.length - 1, 1))
    const colors = ['#2ee6a6', '#60a5fa', '#f59e0b', '#c084fc', '#fb7185', '#22d3ee']
    const chartType = String(chart.chart_type ?? (normalizedSeries.some((item) => item.xValues.length) ? 'line' : 'bar')).toLowerCase()
    const pie = chartType.includes('pie')
    const line = chartType.includes('line')
    const scatter = chartType.includes('scatter')
    const plotImage = typeof content.plot_image === 'string' ? content.plot_image : ''
    const code = typeof content.python_code === 'string' ? content.python_code : ''
    const table = typeof content.data_table_markdown === 'string' ? content.data_table_markdown : ''
    const chartTable = <div className="demo__table-wrap"><table className="demo__table">
      <thead><tr><th>{String(chart.x_axis || 'Category')}</th>{normalizedSeries.map((item) => <th key={item.name}>{item.name}{item.estimated ? ' (estimated)' : ''}</th>)}</tr></thead>
      <tbody>{categories.map((category) => <tr key={category}><th>{category}</th>{normalizedSeries.map((item) => {
        const value = item.points.find((point) => point.label === category)?.value ?? null
        return <td key={item.name}>{value === null ? '—' : `${item.estimated ? '~' : ''}${value}`}</td>
      })}</tr>)}</tbody>
    </table></div>
    let pieAngle = -Math.PI / 2
    const pieValues = normalizedSeries[0]?.points.filter((point) => point.value !== null && point.value >= 0) ?? []
    const pieTotal = pieValues.reduce((sum, point) => sum + (point.value ?? 0), 0)
    const svg = allValues.length > 0 && (
      <svg className="demo__chart" viewBox="0 0 500 250" role="img" aria-label={String(chart.title || 'Extracted chart')}>
        {pie && pieTotal > 0 ? <>
          {pieValues.map((point, index) => {
            const end = pieAngle + ((point.value ?? 0) / pieTotal) * Math.PI * 2
            const path = pieSlicePath(150, 125, 92, pieAngle, end)
            pieAngle = end
            return <g key={`${point.label}-${index}`}>
              <path d={path} fill={colors[index % colors.length]} stroke="#101820" strokeWidth="1" />
              <text x="280" y={36 + index * 25} fontSize="11" fill="currentColor">{point.label}: {point.value}</text>
            </g>
          })}
        </> : <>
          <line x1="38" y1={y(0)} x2="480" y2={y(0)} stroke="currentColor" opacity="0.5" />
          <line x1="38" y1="35" x2="38" y2="190" stroke="currentColor" opacity="0.5" />
          {line || scatter ? normalizedSeries.map((item, seriesIndex) => {
            const points = item.points.filter((point) => point.value !== null)
            const coords = points.map((point) => `${x(point.label, point.x)},${y(point.value as number)}`)
            return <g key={item.name}>
              {line && coords.length > 1 && <polyline points={coords.join(' ')} fill="none" stroke={colors[seriesIndex % colors.length]} strokeWidth="3" />}
              {points.map((point) => <circle key={point.label} cx={x(point.label, point.x)} cy={y(point.value as number)} r="4" fill={colors[seriesIndex % colors.length]} />)}
            </g>
          }) : normalizedSeries.flatMap((item, seriesIndex) => item.points.map((point) => {
            if (point.value === null) return null
            const categoryIndex = categories.indexOf(point.label)
            const groupWidth = Math.min(34, 400 / Math.max(categories.length, 1))
            const width = groupWidth / Math.max(normalizedSeries.length, 1)
            const x0 = 42 + categoryIndex * (420 / Math.max(categories.length, 1)) + seriesIndex * width
            const zeroY = y(0)
            const pointY = y(point.value)
            return <rect key={`${item.name}-${point.label}`} x={x0} y={Math.min(zeroY, pointY)} width={width - 2} height={Math.max(Math.abs(zeroY - pointY), 1)} fill={colors[seriesIndex % colors.length]} />
          }))}
          {categories.map((category, index) => <text key={category} x={48 + index * (420 / Math.max(categories.length - 1, 1))} y="215" textAnchor="middle" fontSize="9" fill="currentColor">{category.slice(0, 15)}</text>)}
        </>}
      </svg>
    )
    return <div className="demo__chart-wrap">
      <p className="demo__chart-title">{String(chart.title || block.text || 'Extracted chart')}</p>
      {plotImage ? <div className="demo__matplotlib-output"><p className="demo__render-label mono">MATPLOTLIB OUTPUT</p><img className="demo__matplotlib-image" src={plotImage} alt={`Rendered plot: ${String(chart.title || 'extracted chart')}`} /></div> : svg || <p className="demo__empty mono">No legible numeric values; see the source page and transcription.</p>}
      <div className="demo__chart-labels"><span>{String(chart.x_axis ?? '')}</span><span>{String(chart.y_axis ?? '')}</span></div>
      {block.text && <p className="demo__block-text">{block.text}</p>}
      {chartTable}
      {table && <details className="demo__chart-details"><summary>Markdown data table</summary><pre className="demo__code mono">{table}</pre></details>}
      {code && <details className="demo__chart-details"><summary>Runnable Matplotlib code</summary><pre className="demo__code mono"><code>{code}</code></pre></details>}
    </div>
  }
  const latex = typeof content.latex === 'string' ? content.latex : ''
  if (block.type === 'equation' && latex) return <div className="demo__equation">
    <div className="demo__equation-display">{`$$ ${latex} $$`}</div>
    {block.text && block.text !== latex && <p className="demo__block-text">{block.text}</p>}
    <details className="demo__chart-details"><summary>LaTeX source</summary><pre className="demo__code mono"><code>{latex}</code></pre></details>
  </div>
  if (['figure', 'diagram'].includes(block.type)) {
    const description = String(content.description ?? content.caption ?? '')
    return <div className="demo__block-text">
      {block.text && <p>{block.text}</p>}
      {description && description !== block.text && <p>{description}</p>}
    </div>
  }
  return block.text ? <p className="demo__block-text">{block.text}</p> : <p className="demo__empty mono">No readable content in this region</p>
}

function renderPlotBlock(block: ParseBlock): ReactNode {
  const content = object(block.content)
  const chart = object(content.chart)
  const title = String(chart.title || content.caption || `Chart on page ${block.page}`)
  const image = typeof content.plot_image === 'string' ? content.plot_image : ''
  return <article className="demo__plot-card" key={block.id}>
    <div className="demo__plot-heading"><h3>{title}</h3><span className="mono">PAGE {block.page}</span></div>
    {image ? <img className="demo__plot-image" src={image} alt={`Matplotlib plot: ${title}`} /> : <div className="demo__plot-fallback">{renderBlock(block)}</div>}
  </article>
}

export default function ParserDemo() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState<Stage>('IDLE')
  const [result, setResult] = useState<ParseResult | null>(null)
  const [tab, setTab] = useState<OutputTab>('structure')
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [showOriginalPage, setShowOriginalPage] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
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
      const initialBlock = data.blocks.find((block) => block.type === 'chart') ?? data.blocks[0]
      setCurrentPage(initialBlock?.page ?? 1)
      setTab(data.blocks.some((block) => block.type === 'chart') ? 'plots' : 'structure')
      if (initialBlock) {
        setSelectedBlock(initialBlock.id)
        setShowOriginalPage(initialBlock.type !== 'chart')
      }
    } catch (e) {
      setStage('IDLE')
      setError(e instanceof Error ? e.message : 'Parse failed')
    } finally {
      setBusy(false)
      // Browsers suppress change events when the same file is selected twice
      // unless the native input is cleared after the request completes.
      if (inputRef.current) inputRef.current.value = ''
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
  const previewPage = currentPage
  const previewSize = result?.pageSizes[previewPage] ?? { width: 612, height: 792 }

  const goToPage = (pageNumber: number) => {
    if (!result || pageNumber < 1 || pageNumber > result.pageCount) return
    setCurrentPage(pageNumber)
    const firstOnPage = result.blocks.find((block) => block.page === pageNumber && block.type === 'chart')
      ?? result.blocks.find((block) => block.page === pageNumber)
    setSelectedBlock(firstOnPage?.id ?? null)
    setShowOriginalPage(firstOnPage?.type !== 'chart')
  }

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
                    <span className="demo__page-meta-actions">
                      <span>p.{previewPage}/{result.pageCount}</span>
                      {result.pageCount > 1 && <span className="demo__page-nav"><button type="button" aria-label="Previous page" disabled={previewPage <= 1} onClick={() => goToPage(previewPage - 1)}>‹</button><button type="button" aria-label="Next page" disabled={previewPage >= result.pageCount} onClick={() => goToPage(previewPage + 1)}>›</button></span>}
                      {activeBlock?.type === 'chart' && <button type="button" className="demo__preview-toggle" onClick={() => setShowOriginalPage((value) => !value)}>{showOriginalPage ? 'Show digital graph' : 'Show source image'}</button>}
                    </span>
                  </div>
                  {activeBlock?.type === 'chart' && !showOriginalPage ? (
                    <div className="demo__page-chart">{renderBlock(activeBlock)}</div>
                  ) : (
                    <div className="demo__page-canvas" style={{ aspectRatio: `${previewSize.width} / ${previewSize.height}` }}>
                      {result.pagePreviews[previewPage] && (
                        <img className="demo__page-image" src={result.pagePreviews[previewPage]} alt={`Page ${previewPage} of ${result.filename}`} />
                      )}
                      {result.blocks
                        .filter((b) => b.page === previewPage)
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
                            onClick={() => { setSelectedBlock(block.id); setCurrentPage(block.page); setShowOriginalPage(block.type !== 'chart') }}
                            title={block.id}
                          >
                            <span className="demo__bbox-tag mono">{block.type}</span>
                          </button>
                        ))}
                      {!result.blocks.length && (
                        <p className="demo__empty mono">No spatial blocks returned</p>
                      )}
                    </div>
                  )}
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
                  ['plots', 'PLOTS'],
                  ['structure', 'STRUCTURE'],
                  ['preview', 'PREVIEW'],
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
                      <article className={`demo__block-card ${selectedBlock === block.id ? 'is-selected' : ''}`}>
                        <button type="button" className="demo__block" onClick={() => { setSelectedBlock(block.id); setCurrentPage(block.page); setShowOriginalPage(block.type !== 'chart') }}>
                          <div className="demo__block-top mono">
                            <span>{block.id}</span>
                            <span>TYPE {block.type}</span>
                          </div>
                          <div className="demo__block-meta mono">
                            <span>PAGE {block.page}</span>
                            <span>CONFIDENCE {Math.round(block.confidence * 100)}%</span>
                            {block.flag && <span className={`demo__flag demo__flag--${block.flag.toLowerCase()}`}>{block.flag}</span>}
                          </div>
                        </button>
                        <div className="demo__block-content">{renderBlock(block)}</div>
                      </article>
                    </li>
                  ))}
                </ul>
              )}

              {result && tab === 'plots' && (
                <div className="demo__plots">
                  {result.blocks.filter((block) => block.type === 'chart').map(renderPlotBlock)}
                  {!result.blocks.some((block) => block.type === 'chart') && <p className="demo__empty mono">No charts were extracted from this document.</p>}
                </div>
              )}

              {result && tab === 'preview' && (
                <div className="demo__json-preview" aria-label="Readable preview of all generated JSON data">
                  <p className="demo__preview-intro">Extracted results from {result.filename}</p>
                  {Object.entries(result.json).map(([key, value]) =>
                    <JsonPreviewValue key={key} label={key} value={value} />,
                  )}
                </div>
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
