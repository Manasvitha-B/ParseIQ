"""Wire adapters → Router → Orchestrator → FinalAssembler."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detection.orchestrator import Orchestrator
from detection.router import Router
from detection.schemas import Block, Box, Document, Page, ParseError, ParseResult, Region

from backend.adapters import (
    ChartExtractorAdapter,
    DiagramExtractorAdapter,
    EquationExtractorAdapter,
    FigureExtractorAdapter,
    LayoutExtractorAdapter,
    OCRExtractorAdapter,
    TableExtractorAdapter,
    TextExtractorAdapter,
)
from backend.assembler import FinalAssembler


def build_router() -> Router:
    router = Router()
    router.register("text", TextExtractorAdapter())
    router.register("ocr", OCRExtractorAdapter())
    router.register("layout", LayoutExtractorAdapter())
    router.register("table", TableExtractorAdapter())
    router.register("chart", ChartExtractorAdapter())
    router.register("figure", FigureExtractorAdapter())
    router.register("equation", EquationExtractorAdapter())
    router.register("diagram", DiagramExtractorAdapter())
    return router


def parse_document(path: str) -> ParseResult:
    """Run the full P1→extract→assemble pipeline with a 55s soft deadline."""
    orchestrator = Orchestrator(
        router=build_router(),
        assembler=FinalAssembler(),
        timeout_seconds=55,
    )
    return orchestrator.parse(path)


def _box_dict(box: Box | None) -> list[float] | None:
    if box is None:
        return None
    return [float(box.x0), float(box.y0), float(box.x1), float(box.y1)]


def _document_dict(document: Document | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "source": document.source,
        "filename": Path(document.source).name,
        "file_type": document.file_type.value if hasattr(document.file_type, "value") else str(document.file_type),
        "size_bytes": document.size_bytes,
        "sha256": document.sha256,
        "metadata": dict(document.metadata or {}),
    }


def _page_dict(page: Page) -> dict[str, Any]:
    # Intentionally omit payload (PyMuPDF page objects are not JSON-serializable)
    return {
        "source": page.source,
        "number": page.number,
        "unit_type": page.unit_type,
        "width": page.width,
        "height": page.height,
        "metadata": dict(page.metadata or {}),
    }


def _region_dict(region: Region) -> dict[str, Any]:
    text_hint = region.text_hint
    if not isinstance(text_hint, str):
        text_hint = None
    return {
        "source": region.source,
        "page_number": region.page_number,
        "region_id": region.region_id,
        "region_type": region.region_type.value if hasattr(region.region_type, "value") else str(region.region_type),
        "box": _box_dict(region.box),
        "reading_order": region.reading_order,
        "confidence": region.confidence,
        "text_hint": text_hint,
        "metadata": dict(region.metadata or {}) if isinstance(region.metadata, dict) else {},
    }


def _block_dict(block: Block) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "block_type": block.block_type,
        "content": block.content,
        "source": block.source,
        "page_number": block.page_number,
        "region_id": block.region_id,
        "box": _box_dict(block.box),
        "reading_order": block.reading_order,
        "confidence": block.confidence,
        "extractor": block.extractor,
        "metadata": dict(block.metadata or {}),
        "flags": list(block.flags or []),
    }


def _error_dict(err: ParseError) -> dict[str, Any]:
    return {
        "code": err.code,
        "message": err.message,
        "source": err.source,
        "page_number": err.page_number,
        "region_id": err.region_id,
        "component": err.component,
        "recoverable": err.recoverable,
        "details": dict(err.details or {}),
    }


def serialize_result(result: ParseResult) -> dict[str, Any]:
    """Convert ParseResult to an API-safe dict (no page payloads)."""
    assembled = result.assembler_result
    if isinstance(assembled, dict):
        payload = dict(assembled)
    else:
        payload = {
            "status": result.status,
            "document": _document_dict(result.document) or {},
            "blocks": [_block_dict(b) for b in result.blocks],
            "markdown": "",
            "json_export": {},
            "errors": [_error_dict(e) for e in result.errors],
            "pipeline_stages": {},
        }

    # Prefer assembler status when present; fall back to orchestrator status
    payload.setdefault("status", result.status)
    if result.status == "failed":
        payload["status"] = "failed"
    elif result.status == "partial" and payload.get("status") == "ok":
        payload["status"] = "partial"

    payload["pages"] = [_page_dict(p) for p in result.pages]
    payload["regions"] = [_region_dict(r) for r in result.regions]
    payload["raw_errors"] = [_error_dict(e) for e in result.errors]
    payload["metadata"] = dict(result.metadata or {})

    # Stages progress for UI
    stages = payload.get("pipeline_stages") or {}
    payload["stages"] = {
        "detect": stages.get("detect", {}).get("status", "unknown"),
        "route": stages.get("route", {}).get("status", "unknown"),
        "extract": stages.get("extract", {}).get("status", "unknown"),
        "assemble": stages.get("assemble", {}).get("status", "unknown"),
        "detail": stages,
    }
    return payload
