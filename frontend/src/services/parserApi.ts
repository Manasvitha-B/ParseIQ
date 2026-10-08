export type ParseStatus = 'idle' | 'detecting' | 'routing' | 'extracting' | 'assembling' | 'complete' | 'error'
export type BlockFlag = 'HIGH' | 'MEDIUM' | 'LOW' | 'ERROR'

export interface BBox { x: number; y: number; w: number; h: number }
export interface ParseBlock {
  id: string
  type: string
  page: number
  confidence: number
  text: string
  bbox: BBox
  provenance: string
  flag?: BlockFlag
  flags?: string[]
  content?: unknown
  metadata?: Record<string, unknown>
}
export interface ParseStructure {
  documentType: string
  language: string
  columns: number
  readingOrder: string[]
  layoutRegions: Array<{ id: string; type: string; page: number }>
}
export interface ParseResult {
  jobId: string
  status: ParseStatus | string
  demoMode: boolean
  filename: string
  pageCount: number
  processingMs: number
  stages: string[]
  blocks: ParseBlock[]
  structure: ParseStructure
  markdown: string
  json: Record<string, unknown>
  pageSizes: Record<number, { width: number; height: number }>
}

type RawObject = Record<string, unknown>
const asObject = (value: unknown): RawObject => value && typeof value === 'object' ? value as RawObject : {}
const asString = (value: unknown, fallback = ''): string => typeof value === 'string' ? value : fallback

function contentText(value: unknown): string {
  if (typeof value === 'string') return value
  const content = asObject(value)
  for (const key of ['markdown', 'latex', 'text', 'caption', 'description']) {
    if (typeof content[key] === 'string' && content[key]) return content[key] as string
  }
  const chart = asObject(content.chart)
  if (typeof chart.title === 'string') return chart.title
  return ''
}

function normalizeBBox(value: unknown): BBox {
  if (Array.isArray(value) && value.length >= 4) {
    const [x0, y0, x1, y1] = value.map((n) => Number(n) || 0)
    return { x: x0, y: y0, w: Math.max(0, x1 - x0), h: Math.max(0, y1 - y0) }
  }
  const box = asObject(value)
  return { x: Number(box.x ?? box.x0) || 0, y: Number(box.y ?? box.y0) || 0,
    w: Number(box.w ?? (Number(box.x1) - Number(box.x0))) || 0,
    h: Number(box.h ?? (Number(box.y1) - Number(box.y0))) || 0 }
}

function normalizeResult(rawValue: unknown): ParseResult {
  const raw = asObject(rawValue)
  const document = asObject(raw.document)
  const pages = Array.isArray(raw.pages) ? raw.pages : []
  const pageSizes: ParseResult['pageSizes'] = {}
  for (const value of pages) {
    const page = asObject(value)
    const number = Number(page.number) || 1
    pageSizes[number] = { width: Number(page.width) || 612, height: Number(page.height) || 792 }
  }
  const blocks = (Array.isArray(raw.blocks) ? raw.blocks : []).map((value, index): ParseBlock => {
    const block = asObject(value)
    const flags = Array.isArray(block.flags) ? block.flags.map(String) : []
    const confidence = Math.max(0, Math.min(1, Number(block.confidence) || 0))
    const semanticType = asString(block.type, asString(block.block_type, 'text_block'))
    const flagged: BlockFlag | undefined = flags.includes('extractor_error') ? 'ERROR' :
      confidence < 0.5 ? 'LOW' : confidence < 0.8 ? 'MEDIUM' : undefined
    return {
      id: asString(block.api_block_id, asString(block.block_id, `BLOCK_${String(index + 1).padStart(3, '0')}`)),
      type: semanticType,
      page: Number(block.page ?? block.page_number) || 1,
      confidence,
      text: contentText(block.content ?? block.text),
      bbox: normalizeBBox(block.bbox ?? block.box),
      provenance: [asString(block.extractor, 'extractor'), asString(block.region_id)].filter(Boolean).join(' · '),
      flag: flagged,
      flags,
      content: block.content ?? block.text,
      metadata: asObject(block.metadata),
    }
  })
  const stageObj = asObject(raw.stages)
  const stageNames = ['detect', 'route', 'extract', 'assemble']
  const stages = stageNames.map((name) => `${name}: ${asString(stageObj[name], 'unknown')}`)
  const structure: ParseStructure = {
    documentType: asString(document.file_type, 'document'), language: 'und', columns: 1,
    readingOrder: blocks.map((block) => block.id),
    layoutRegions: (Array.isArray(raw.regions) ? raw.regions : []).map((value, index) => {
      const region = asObject(value)
      return { id: asString(region.region_id, `region-${index + 1}`),
        type: asString(region.region_type, 'unknown'), page: Number(region.page_number) || 1 }
    }),
  }
  const pageCount = Number(document.page_count) || pages.length || Math.max(1, ...blocks.map((b) => b.page))
  return {
    jobId: asString(raw.job_id, asString(document.sha256, `parse-${Date.now()}`)),
    status: asString(raw.status, 'complete'), demoMode: Boolean(raw.demo_mode),
    filename: asString(document.original_filename, asString(document.filename, 'document')),
    pageCount, processingMs: Number(raw.processing_ms) || 0, stages, blocks, structure,
    markdown: asString(raw.markdown), json: asObject(raw.json_export ?? raw), pageSizes,
  }
}

async function requestJson(url: string, init?: RequestInit): Promise<unknown> {
  let response: Response
  try { response = await fetch(url, init) }
  catch { throw new Error('Could not reach the ParseIQ backend. Start it with `python -m backend.run` and retry.') }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const body = asObject(payload)
    const errors = Array.isArray(body.errors) ? body.errors : []
    const first = asObject(errors[0])
    throw new Error(asString(first.message, asString(body.detail, `Request failed (${response.status})`)))
  }
  return payload
}

export async function healthCheck(): Promise<boolean> {
  try { return (await fetch('/api/health')).ok } catch { return false }
}

export async function uploadDocument(file: File): Promise<ParseResult> {
  const form = new FormData()
  form.append('file', file)
  const result = normalizeResult(await requestJson('/api/parse', { method: 'POST', body: form }))
  result.filename = file.name
  return result
}

export async function loadSampleDocument(): Promise<ParseResult> {
  return normalizeResult(await requestJson('/api/sample'))
}
