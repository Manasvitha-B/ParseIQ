import { mockParseResult } from '../data/mockParserData'

export type ParseStatus =
  | 'idle'
  | 'detecting'
  | 'routing'
  | 'extracting'
  | 'assembling'
  | 'complete'
  | 'error'

export type BlockFlag = 'HIGH' | 'MEDIUM' | 'LOW' | 'ERROR'

export interface BBox {
  x: number
  y: number
  w: number
  h: number
}

export interface ParseBlock {
  id: string
  type: string
  page: number
  confidence: number
  text: string
  bbox: BBox
  provenance: string
  flag?: BlockFlag
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
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function tryFetchJson<T>(url: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, init)
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

function asDemo(result: ParseResult): ParseResult {
  return { ...result, demoMode: true }
}

function normalizeResult(raw: Partial<ParseResult> & Record<string, unknown>): ParseResult {
  return {
    jobId: String(raw.jobId ?? raw.job_id ?? 'unknown'),
    status: String(raw.status ?? 'complete'),
    demoMode: false,
    filename: String(raw.filename ?? raw.file_name ?? 'document'),
    pageCount: Number(raw.pageCount ?? raw.page_count ?? 1),
    processingMs: Number(raw.processingMs ?? raw.processing_ms ?? 0),
    stages: (raw.stages as string[]) ?? mockParseResult.stages,
    blocks: (raw.blocks as ParseBlock[]) ?? [],
    structure: (raw.structure as ParseStructure) ?? mockParseResult.structure,
    markdown: String(raw.markdown ?? ''),
    json: (raw.json as Record<string, unknown>) ?? raw,
  }
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch('/api/health', { method: 'GET' })
    return res.ok
  } catch {
    return false
  }
}

export async function uploadDocument(file: File): Promise<ParseResult> {
  const form = new FormData()
  form.append('file', file)

  const raw = await tryFetchJson<Partial<ParseResult>>('/api/parse', {
    method: 'POST',
    body: form,
  })

  if (raw) {
    return normalizeResult({ ...raw, filename: file.name })
  }

  await delay(900)
  return asDemo({
    ...mockParseResult,
    filename: file.name,
    jobId: `demo-upload-${Date.now()}`,
  })
}

export async function getParsingResult(jobId?: string): Promise<ParseResult> {
  if (jobId) {
    const raw = await tryFetchJson<Partial<ParseResult>>(`/api/parse/${encodeURIComponent(jobId)}`)
    if (raw) return normalizeResult(raw)
  }

  const raw = await tryFetchJson<Partial<ParseResult>>('/api/parse')
  if (raw) return normalizeResult(raw)

  await delay(400)
  return asDemo({
    ...mockParseResult,
    jobId: jobId ?? mockParseResult.jobId,
  })
}

export async function loadSampleDocument(): Promise<ParseResult> {
  const raw = await tryFetchJson<Partial<ParseResult>>('/api/sample')
  if (raw) return normalizeResult(raw)

  await delay(1100)
  return asDemo({
    ...mockParseResult,
    jobId: `demo-sample-${Date.now()}`,
  })
}
