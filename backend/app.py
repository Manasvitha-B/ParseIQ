"""ParseIQ FastAPI application."""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

# Ensure ParseIQ root is importable (detection, parser, graphextract, backend)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.pipeline import parse_document, serialize_result
from backend.vision import load_local_environment

app = FastAPI(title="ParseIQ", version="1.0.0", description="Document intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sample_parse_result() -> dict[str, Any]:
    """Prebuilt PE diligence memo so demos work without an upload."""
    blocks = [
        {
            "block_id": "BLOCK_001",
            "api_block_id": "BLOCK_001",
            "type": "heading",
            "block_type": "heading",
            "content": "Confidential — Project Orion Diligence Memo",
            "text": "Confidential — Project Orion Diligence Memo",
            "page": 1,
            "bbox": [72.0, 48.0, 540.0, 78.0],
            "confidence": 0.99,
            "flags": [],
            "extractor": "text",
            "reading_order": 0,
            "region_id": "p1-text-1",
            "metadata": {"layout_role": "header"},
        },
        {
            "block_id": "BLOCK_002",
            "api_block_id": "BLOCK_002",
            "type": "paragraph",
            "block_type": "paragraph",
            "content": (
                "Revenue grew +24% YoY to $186.4m, driven by enterprise net retention of 118% "
                "and expansion in the mid-market cohort. Gross margin expanded 210 bps to 71.2%."
            ),
            "text": (
                "Revenue grew +24% YoY to $186.4m, driven by enterprise net retention of 118% "
                "and expansion in the mid-market cohort. Gross margin expanded 210 bps to 71.2%."
            ),
            "page": 1,
            "bbox": [72.0, 96.0, 540.0, 148.0],
            "confidence": 0.96,
            "flags": [],
            "extractor": "text",
            "reading_order": 1,
            "region_id": "p1-text-2",
            "metadata": {"layout_role": "body"},
        },
        {
            "block_id": "BLOCK_003",
            "api_block_id": "BLOCK_003",
            "type": "heading",
            "block_type": "heading",
            "content": "1. Debt Schedule",
            "text": "1. Debt Schedule",
            "page": 1,
            "bbox": [72.0, 168.0, 280.0, 188.0],
            "confidence": 0.98,
            "flags": [],
            "extractor": "text",
            "reading_order": 2,
            "region_id": "p1-text-3",
            "metadata": {},
        },
        {
            "block_id": "BLOCK_004",
            "api_block_id": "BLOCK_004",
            "type": "table",
            "block_type": "table",
            "content": {
                "matrix": [
                    ["Facility", "Drawn ($m)", "Rate", "Maturity"],
                    ["Term Loan B", "120.0", "SOFR+3.50%", "2029"],
                    ["Revolver", "15.0", "SOFR+3.00%", "2028"],
                    ["Holdco PIK", "40.0", "8.00% PIK", "2030"],
                ],
                "markdown": (
                    "| Facility | Drawn ($m) | Rate | Maturity |\n"
                    "| --- | --- | --- | --- |\n"
                    "| Term Loan B | 120.0 | SOFR+3.50% | 2029 |\n"
                    "| Revolver | 15.0 | SOFR+3.00% | 2028 |\n"
                    "| Holdco PIK | 40.0 | 8.00% PIK | 2030 |"
                ),
                "text": "Facility\tDrawn ($m)\tRate\tMaturity\nTerm Loan B\t120.0\tSOFR+3.50%\t2029",
            },
            "text": (
                "| Facility | Drawn ($m) | Rate | Maturity |\n"
                "| --- | --- | --- | --- |\n"
                "| Term Loan B | 120.0 | SOFR+3.50% | 2029 |\n"
                "| Revolver | 15.0 | SOFR+3.00% | 2028 |\n"
                "| Holdco PIK | 40.0 | 8.00% PIK | 2030 |"
            ),
            "page": 1,
            "bbox": [72.0, 200.0, 540.0, 310.0],
            "confidence": 0.93,
            "flags": [],
            "extractor": "table",
            "reading_order": 3,
            "region_id": "p1-table-1",
            "metadata": {"engine": "sample", "route": "table"},
        },
        {
            "block_id": "BLOCK_005",
            "api_block_id": "BLOCK_005",
            "type": "chart",
            "block_type": "chart",
            "content": {
                "caption": "Figure 2 — ARR bridge: beginning $150m → ending $186m (+24%)",
                "description": "Figure 2 — ARR bridge: beginning $150m → ending $186m (+24%)",
            },
            "text": "Figure 2 — ARR bridge: beginning $150m → ending $186m (+24%)",
            "page": 2,
            "bbox": [90.0, 120.0, 520.0, 340.0],
            "confidence": 0.88,
            "flags": [],
            "extractor": "chart",
            "reading_order": 0,
            "region_id": "p2-image-1",
            "metadata": {"visual_kind": "chart", "provenance": "region_bbox"},
        },
        {
            "block_id": "BLOCK_006",
            "api_block_id": "BLOCK_006",
            "type": "figure",
            "block_type": "figure",
            "content": {
                "caption": "Org chart — go-to-market leadership (sample figure)",
                "description": "Org chart — go-to-market leadership (sample figure)",
            },
            "text": "Org chart — go-to-market leadership (sample figure)",
            "page": 2,
            "bbox": [72.0, 360.0, 300.0, 520.0],
            "confidence": 0.90,
            "flags": [],
            "extractor": "figure",
            "reading_order": 1,
            "region_id": "p2-image-2",
            "metadata": {"visual_kind": "figure"},
        },
        {
            "block_id": "BLOCK_007",
            "api_block_id": "BLOCK_007",
            "type": "equation",
            "block_type": "equation",
            "content": {
                "latex": "EV = EBITDA \\times Multiple",
                "text": "EV = EBITDA × Multiple",
                "math_like": True,
            },
            "text": "EV = EBITDA × Multiple",
            "page": 2,
            "bbox": [72.0, 540.0, 320.0, 565.0],
            "confidence": 0.94,
            "flags": [],
            "extractor": "equation",
            "reading_order": 2,
            "region_id": "p2-eq-1",
            "metadata": {"route": "equation"},
        },
        {
            "block_id": "BLOCK_008",
            "api_block_id": "BLOCK_008",
            "type": "paragraph",
            "block_type": "paragraph",
            "content": (
                "Implied enterprise value at 12.5x LTM EBITDA is $412m. Net debt of $175m implies "
                "equity value of $237m before transaction fees."
            ),
            "text": (
                "Implied enterprise value at 12.5x LTM EBITDA is $412m. Net debt of $175m implies "
                "equity value of $237m before transaction fees."
            ),
            "page": 2,
            "bbox": [72.0, 580.0, 540.0, 630.0],
            "confidence": 0.95,
            "flags": [],
            "extractor": "text",
            "reading_order": 3,
            "region_id": "p2-text-4",
            "metadata": {},
        },
    ]

    markdown = """## Confidential — Project Orion Diligence Memo

Revenue grew +24% YoY to $186.4m, driven by enterprise net retention of 118% and expansion in the mid-market cohort. Gross margin expanded 210 bps to 71.2%.

## 1. Debt Schedule

| Facility | Drawn ($m) | Rate | Maturity |
| --- | --- | --- | --- |
| Term Loan B | 120.0 | SOFR+3.50% | 2029 |
| Revolver | 15.0 | SOFR+3.00% | 2028 |
| Holdco PIK | 40.0 | 8.00% PIK | 2030 |

![chart](Figure 2 — ARR bridge: beginning $150m → ending $186m (+24%))

![figure](Org chart — go-to-market leadership (sample figure))

$$
EV = EBITDA × Multiple
$$

Implied enterprise value at 12.5x LTM EBITDA is $412m. Net debt of $175m implies equity value of $237m before transaction fees.
"""

    document = {
        "source": "sample://project-orion-diligence.pdf",
        "filename": "project-orion-diligence.pdf",
        "file_type": "pdf",
        "size_bytes": 248320,
        "sha256": "sample0000000000000000000000000000000000000000000000000000000000",
        "metadata": {"demo": True, "title": "Project Orion Diligence Memo"},
        "page_count": 2,
        "region_count": 8,
        "block_count": len(blocks),
    }

    pipeline_stages = {
        "detect": {"status": "ok", "file_type": "pdf"},
        "route": {"status": "ok", "regions": 8},
        "extract": {"status": "ok", "blocks": len(blocks)},
        "assemble": {"status": "ok", "markdown_chars": len(markdown), "enrichment": "sample"},
    }

    return {
        "status": "ok",
        "document": document,
        "blocks": blocks,
        "markdown": markdown.strip() + "\n",
        "json_export": {
            "document": document,
            "blocks": [
                {
                    "id": b["api_block_id"],
                    "type": b["type"],
                    "text": b["text"],
                    "content": b["content"],
                    "page": b["page"],
                    "bbox": b["bbox"],
                    "confidence": b["confidence"],
                    "extractor": b["extractor"],
                    "reading_order": b["reading_order"],
                    "flags": b["flags"],
                    "metadata": b["metadata"],
                }
                for b in blocks
            ],
            "markdown": markdown.strip() + "\n",
        },
        "errors": [],
        "pipeline_stages": pipeline_stages,
        "stages": {
            "detect": "ok",
            "route": "ok",
            "extract": "ok",
            "assemble": "ok",
            "detail": pipeline_stages,
        },
        "pages": [
            {"number": 1, "width": 612.0, "height": 792.0, "unit_type": "page", "metadata": {"pdf_type": "digital"}},
            {"number": 2, "width": 612.0, "height": 792.0, "unit_type": "page", "metadata": {"pdf_type": "digital"}},
        ],
        "regions": [],
        "metadata": {"sample": True},
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    load_local_environment()
    provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openrouter" if os.getenv("OPENROUTER_API_KEY") else None
    return {"status": "ok", "service": "ParseIQ", "vision_provider": provider,
            "vision_configured": provider is not None}


@app.get("/api/sample")
def sample() -> dict[str, Any]:
    return _sample_parse_result()


@app.post("/api/parse")
async def parse(file: UploadFile = File(...)) -> JSONResponse:
    """Accept a multipart upload, run the pipeline, return structured JSON."""
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="parseiq-") as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        try:
            result = parse_document(tmp_path)
            payload = serialize_result(result)
        except Exception as exc:
            # Truly unexpected — still return structured JSON (HTTP 200)
            payload = {
                "status": "failed",
                "document": {"filename": file.filename},
                "blocks": [],
                "markdown": "",
                "json_export": {},
                "errors": [
                    {
                        "code": "PIPELINE_CRASH",
                        "message": str(exc),
                        "component": "api",
                        "recoverable": False,
                        "details": {"exception_type": type(exc).__name__},
                    }
                ],
                "pipeline_stages": {
                    "detect": {"status": "failed"},
                    "route": {"status": "skipped"},
                    "extract": {"status": "skipped"},
                    "assemble": {"status": "skipped"},
                },
                "stages": {
                    "detect": "failed",
                    "route": "skipped",
                    "extract": "skipped",
                    "assemble": "skipped",
                },
                "metadata": {"traceback": traceback.format_exc()[-2000:]},
            }

        # Attach upload name for clients
        if isinstance(payload.get("document"), dict) and file.filename:
            payload["document"].setdefault("original_filename", file.filename)

        return JSONResponse(content=payload, status_code=200)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "ParseIQ",
        "docs": "/docs",
        "health": "/api/health",
        "sample": "/api/sample",
        "parse": "POST /api/parse",
    }
