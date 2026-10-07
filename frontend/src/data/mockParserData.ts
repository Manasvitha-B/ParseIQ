import type { ParseResult } from '../services/parserApi'

/** Realistic PE diligence sample used when the backend is unavailable. */
export const mockParseResult: ParseResult = {
  jobId: 'demo-pe-diligence-001',
  status: 'complete',
  demoMode: true,
  filename: 'Apex_Holdings_CIM_excerpt.pdf',
  pageCount: 4,
  processingMs: 1840,
  stages: ['DETECTING', 'ROUTING', 'EXTRACTING', 'ASSEMBLING', 'COMPLETE'],
  blocks: [
    {
      id: 'BLOCK_001',
      type: 'heading',
      page: 1,
      confidence: 0.98,
      text: 'Confidential Information Memorandum',
      bbox: { x: 72, y: 64, w: 420, h: 28 },
      provenance: 'P2A.text',
    },
    {
      id: 'BLOCK_002',
      type: 'heading',
      page: 1,
      confidence: 0.97,
      text: 'Apex Holdings — Q3 2024 Diligence Pack',
      bbox: { x: 72, y: 100, w: 380, h: 22 },
      provenance: 'P2A.text',
    },
    {
      id: 'BLOCK_003',
      type: 'paragraph',
      page: 1,
      confidence: 0.94,
      text: 'Apex Holdings operates a vertically integrated specialty chemicals platform across North America and Western Europe. The business generates approximately $412M in trailing twelve-month revenue with adjusted EBITDA of $78M (18.9% margin).',
      bbox: { x: 72, y: 140, w: 468, h: 72 },
      provenance: 'P2A.ocr',
    },
    {
      id: 'BLOCK_004',
      type: 'table',
      page: 2,
      confidence: 0.91,
      text: 'Financial Summary FY22–FY24',
      bbox: { x: 72, y: 120, w: 468, h: 160 },
      provenance: 'P3.table',
      metadata: {
        rows: 5,
        cols: 4,
        headers: ['Metric', 'FY22', 'FY23', 'FY24'],
      },
    },
    {
      id: 'BLOCK_005',
      type: 'figure',
      page: 2,
      confidence: 0.88,
      text: 'Revenue by Segment — stacked bar chart',
      bbox: { x: 72, y: 310, w: 280, h: 180 },
      provenance: 'P3.chart',
    },
    {
      id: 'BLOCK_006',
      type: 'equation',
      page: 3,
      confidence: 0.85,
      text: 'EBITDA_adj = Operating Income + D&A + SBC − NCI',
      bbox: { x: 96, y: 200, w: 360, h: 32 },
      provenance: 'P3.equation',
    },
    {
      id: 'BLOCK_007',
      type: 'paragraph',
      page: 4,
      confidence: 0.96,
      text: 'Revenue increased by 24%.',
      bbox: { x: 72, y: 180, w: 220, h: 18 },
      provenance: 'P2A.text',
    },
    {
      id: 'BLOCK_008',
      type: 'paragraph',
      page: 4,
      confidence: 0.72,
      text: 'Management guidance implies mid-teens organic growth through FY26, subject to feedstock volatility.',
      bbox: { x: 72, y: 210, w: 468, h: 40 },
      provenance: 'P2A.ocr',
      flag: 'MEDIUM',
    },
    {
      id: 'BLOCK_009',
      type: 'paragraph',
      page: 4,
      confidence: 0.41,
      text: '[illegible scan region — customer concentration footnote]',
      bbox: { x: 72, y: 280, w: 300, h: 36 },
      provenance: 'P2A.ocr',
      flag: 'LOW',
    },
    {
      id: 'BLOCK_010',
      type: 'paragraph',
      page: 4,
      confidence: 0.12,
      text: '',
      bbox: { x: 72, y: 340, w: 180, h: 24 },
      provenance: 'P1.route',
      flag: 'ERROR',
    },
  ],
  structure: {
    documentType: 'CIM / Diligence Pack',
    language: 'en',
    columns: 2,
    readingOrder: [
      'BLOCK_001',
      'BLOCK_002',
      'BLOCK_003',
      'BLOCK_004',
      'BLOCK_005',
      'BLOCK_006',
      'BLOCK_007',
      'BLOCK_008',
      'BLOCK_009',
      'BLOCK_010',
    ],
    layoutRegions: [
      { id: 'COLUMN_01', type: 'column', page: 1 },
      { id: 'COLUMN_02', type: 'column', page: 1 },
    ],
  },
  markdown: `# Confidential Information Memorandum

## Apex Holdings — Q3 2024 Diligence Pack

Apex Holdings operates a vertically integrated specialty chemicals platform across North America and Western Europe. The business generates approximately **$412M** in trailing twelve-month revenue with adjusted EBITDA of **$78M** (18.9% margin).

### Financial Summary FY22–FY24

| Metric | FY22 | FY23 | FY24 |
|--------|------|------|------|
| Revenue ($M) | 298 | 341 | 412 |
| Adj. EBITDA ($M) | 52 | 64 | 78 |
| Margin (%) | 17.4 | 18.8 | 18.9 |
| CapEx ($M) | 18 | 22 | 29 |

### Revenue by Segment

*[Figure: stacked bar — Specialty / Commodity / Services]*

### Bridge Formula

$$
EBITDA_{adj} = Operating\\ Income + D\\&A + SBC - NCI
$$

### Key Finding (p.4)

Revenue increased by 24%.

> Management guidance implies mid-teens organic growth through FY26, subject to feedstock volatility.

⚠ Low-confidence region flagged on customer concentration footnote.
`,
  json: {
    document: {
      id: 'demo-pe-diligence-001',
      title: 'Apex Holdings — Q3 2024 Diligence Pack',
      type: 'CIM',
      pages: 4,
    },
    extractions: {
      revenue_ttm_usd_m: 412,
      ebitda_adj_usd_m: 78,
      ebitda_margin_pct: 18.9,
      revenue_growth_yoy_pct: 24,
    },
    tables: [
      {
        id: 'BLOCK_004',
        name: 'Financial Summary FY22–FY24',
        headers: ['Metric', 'FY22', 'FY23', 'FY24'],
        rows: [
          ['Revenue ($M)', '298', '341', '412'],
          ['Adj. EBITDA ($M)', '52', '64', '78'],
          ['Margin (%)', '17.4', '18.8', '18.9'],
          ['CapEx ($M)', '18', '22', '29'],
        ],
      },
    ],
    flags: [
      { blockId: 'BLOCK_008', level: 'MEDIUM', reason: 'Ambiguous guidance language' },
      { blockId: 'BLOCK_009', level: 'LOW', reason: 'OCR confidence below threshold' },
      { blockId: 'BLOCK_010', level: 'ERROR', reason: 'Unreadable scan region' },
    ],
  },
}

export const mockHealthOffline = false
