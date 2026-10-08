# ParseIQ
ParseIQ is a single-document parsing engine built for AI-native document understanding. The project targets the core challenge in enterprise document ingestion: turning messy real-world business files into clean, structured, faithful output that can be searched, reasoned over, and cited by AI systems.

This repository is designed as a hackathon-ready prototype for a unified parser that accepts PDF, images, Office files, HTML, Markdown, email, and other business artifacts, then returns typed blocks with page provenance, reading order, confidence, and structured export formats.

## Live Demo

Deployment link: [Add your deployment URL here](#)

---

## 1. Background

Modern AI systems are only as good as the text they can read. In finance, legal, and operations workflows, bad parsing creates real downstream failure:

- tables are read with the wrong row/column alignment
- scanned contracts are invisible because they have no text layer
- charts and equations are flattened or discarded
- reading order becomes scrambled across multi-column layouts
- figures, footnotes, and attachments are lost
- AI answers sound confident but cite the wrong source

Open-source parsers such as Docling, Marker, MinerU, olmOCR, and OCR pipelines handle many clean PDFs well, but they still break on the kinds of files businesses actually hold: phone photos, faxed scans, mixed-format documents, page-spanning tables, tracked changes, embedded attachments, and chart-heavy reports.

ParseIQ aims to do better by using a unified pipeline:

- detect the file type and page characteristics
- route each page or region to the appropriate extractor
- preserve page, bounding box, and reading-order provenance
- emit structured output for AI consumption rather than flat text alone

---

## 2. Problem

The challenge is to build a single parser that converts business files into clean structured output while satisfying both fidelity and usability.

### Fidelity
Every word, table cell, figure, equation, and section header must be correct, complete, and in natural reading order. Nothing should be invented. Low-confidence or unreadable content should be flagged explicitly rather than silently guessed.

### Usability by AI
The output must be structured so an AI can:

- search by block type and page
- reason over tables, equations, and figure data
- attribute answers to exact source regions
- filter low-confidence sections for human review

### Real-world failure modes

- Invisible content from scanned PDFs and images
- Broken tables with merged cells or multi-page continuation
- Missing charts, diagrams, and math extraction
- Distorted reading order from headers, footers, sidebars, or footnotes
- No provenance: no page / bounding box / confidence metadata
- Format sprawl: different tools for DOCX, PPTX, XLSX, HTML, email, attachments

---

## 3. Challenge Statement

Build a parser that takes any supported business file and returns structured output that satisfies:

1. Accuracy across text, tables, figures, math, reading order, and provenance
2. Production practicality under runtime, cost, and robustness constraints
3. Graceful failure for unsupported or corrupt files

### Supported input coverage

The parser should accept:

- PDFs: digital and scanned, including rotated/skewed pages and mixed files
- Images: PNG, JPG, TIFF, HEIC
- Office: DOCX/DOC, PPTX/PPT, XLSX/XLS/CSV
- Web and text: HTML, Markdown, TXT, RTF
- Email: EML/MSG with nested attachments parsed recursively

Unsupported, encrypted, or corrupt inputs must fail gracefully with a structured error rather than crashing.

---

## 4. Expected Output

The parser should return output in a form like this:

- Markdown in natural reading order with running headers and footers removed from the body
- HTML or Markdown tables with proper row/column structure
- Figures and charts as typed blocks with captions and extracted values
- Math as LaTeX
- JSON listing every block with:
  - block type
  - page number
  - bounding box
  - confidence
  - reading order position
  - source provenance

### Example output pattern

```json
{
  "status": "ok",
  "document": {
    "filename": "financial_statement.pdf",
    "file_type": "pdf"
  },
  "blocks": [
    {
      "type": "table",
      "page": 2,
      "bbox": [72, 180, 520, 360],
      "confidence": 0.94,
      "content": "...",
      "reading_order": 7
    }
  ],
  "markdown": "...",
  "errors": []
}
```

---

## 5. Proposed Solution

ParseIQ follows a modular pipeline to handle diverse document types and content classes.

### 5.1 Detect and route

The system identifies:

- file type and document class
- page type (digital PDF, scanned page, image, Office document, email)
- region type (text, table, chart, figure, equation, diagram, layout)

Each page or region is routed to the correct extractor.

### 5.2 Extract and assemble

The extraction layer produces typed blocks such as:

- headings
- paragraphs
- lists
- tables
- figures
- captions
- equations
- headers and footers
- footnotes

Blocks are placed in reading order and merged across page breaks when applicable.

### 5.3 Flag and fail safe

When extraction is uncertain:

- low-confidence blocks are flagged
- missing or unreadable regions are reported explicitly
- unsupported input does not crash the pipeline

---

## 6. Architecture

This project is split into a few logically distinct layers:

```text
Input file
   ↓
Detection + classification
   ↓
Router / page-region dispatch
   ↓
Specialized extractors
   ↓
Assembler + final output
   ↓
JSON / Markdown / UI
```

### Repository structure

```text
ParseIQ/
├── backend/
│   ├── adapters.py
│   ├── app.py
│   ├── assembler.py
│   ├── chart_output.py
│   ├── pipeline.py
│   ├── run.py
│   └── vision.py
├── detection/
│   ├── analyzer.py
│   ├── detect.py
│   ├── image_classifier.py
│   ├── loaders.py
│   ├── main.py
│   ├── orchestrator.py
│   ├── router.py
│   └── schemas.py
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   └── ...
├── graphextract/
│   ├── extractors/
│   ├── models/
│   ├── processing/
│   └── requirements.txt
├── parser/
│   ├── document_structure.py
│   ├── reading_order.py
│   ├── semantic_blocks.py
│   └── ...
├── samples/
├── tests/
├── .env.example
├── .gitignore
├── dev.ps1
├── requirements.txt
├── README.md
└── ...
```

### Key components

- `backend/` — API layer, orchestrator, adapters, and final serialization
- `detection/` — region detection, routing, schemas, and classifier logic
- `graphextract/` — vision and graph-oriented extraction utilities
- `parser/` — reading-order and semantic block logic
- `frontend/` — demo UI to visualize parsed output

---

## 7. Tech Stack

### Backend

- Python
- FastAPI
- Uvicorn
- PyMuPDF
- pdfplumber
- Pillow
- OpenCV
- Tesseract / OCR support
- Pydantic
- NumPy / Pandas / Matplotlib
- Gemini or OpenRouter-compatible multimodal services

### Frontend

- React
- TypeScript
- Vite

---

## 8. Output contract

The parser is intended to emit a structured result with the following qualities:

- typed blocks per semantic unit
- page number and bounding box for every block
- reading order across pages and sections
- confidence score per block
- Markdown for human-friendly review
- JSON for machine-readable downstream use
- robust error handling for unsupported or corrupt documents

This matches the core needs of AI systems and human reviewers.

---

## 9. Running the project

### 1. Create a Python virtual environment

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Configure environment variables

Copy the sample environment file:

```bash
copy .env.example .env
```

or:

```bash
cp .env.example .env
```

Then add a vision provider key, for example:

```env
VISION_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

or:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=qwen/qwen3-vl-30b-a3b-instruct
```

### 5. Start the app

#### PowerShell helper

```powershell
pwsh ./dev.ps1
```

#### Manual backend

```bash
python -m backend.run
```

#### Manual frontend

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

---

## 10. API endpoints

The backend exposes a FastAPI app with a minimal document-processing interface.

### Health check

```bash
curl http://127.0.0.1:8000/api/health
```

### Demo sample

```bash
curl http://127.0.0.1:8000/api/sample
```

### File upload parser

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -F "file=@path/to/document.pdf"
```

The interactive docs are available at:

```text
http://127.0.0.1:8000/docs
```
## 11. Suggested next improvements

- strengthen table merging across page breaks
- improve chart value extraction from visual plots
- handle equation recognition and LaTeX formatting better
- add more robust OCR fallback for scans and skewed pages
- create an evaluation harness against benchmark data
- add provenance-review tooling for human validation

---

