"""Wire adapters → Router → Orchestrator → FinalAssembler."""
from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detection.orchestrator import Orchestrator
from detection.image_classifier import ImageClassifier
from detection.router import Router
from detection.schemas import Block, Box, Document, Page, ParseError, ParseResult, Region, RegionType

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
from backend.vision import get_vision_service


class _VisionImageBackend:
    """Classify and extract a mixed image once; downstream adapters reuse its JSON."""
    def classify(self, page: Page, region: Region):
        result = get_vision_service().analyze(page, region)
        if not result:
            region.metadata["classification_status"] = "vision_unavailable"
            region.metadata["vision_error"] = "Vision analysis returned no result"
            fallback = {"vision_fallback": True}
            return [
                (RegionType.FIGURE, 0.35, {**fallback, "fallback_kind": "visual"}),
                (RegionType.SCANNED_TEXT, 0.3, {**fallback, "fallback_kind": "ocr"}),
            ]
        if result.get("error"):
            region.metadata["vision_error"] = result["error"]
            region.metadata["classification_status"] = "vision_failed"
            fallback = {"vision_fallback": True}
            return [
                (RegionType.FIGURE, 0.35, {**fallback, "fallback_kind": "visual"}),
                (RegionType.SCANNED_TEXT, 0.3, {**fallback, "fallback_kind": "ocr"}),
            ]
        region.metadata["vision_result"] = result
        from detection.image_classifier import IMAGE_LABELS
        confidence = result.get("confidence", 0.86)
        metadata = {"vision_result": result, "vision_provider": result.get("provider")}
        predictions = []
        if result.get("charts") or isinstance(result.get("chart"), dict) and result["chart"]:
            predictions.append((IMAGE_LABELS["chart"], confidence, metadata))
        if result.get("equations"):
            predictions.append((IMAGE_LABELS["equation"], confidence, metadata))
        if predictions:
            return predictions
        route = {
            "table": "table", "chart": "chart", "figure": "figure",
            "equation": "equation", "text_block": "text",
        }.get(result.get("block_type"), "text")
        label = next((key for key, value in IMAGE_LABELS.items() if value.value == route), "text")
        return [(IMAGE_LABELS[label], confidence, metadata)]


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
    """Run extraction with a bounded per-document processing deadline."""
    orchestrator = Orchestrator(
        router=build_router(),
        image_classifier=ImageClassifier(backend=_VisionImageBackend()),
        assembler=FinalAssembler(),
        timeout_seconds=180,
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
    preview = None
    payload = page.payload if isinstance(page.payload, dict) else {}
    pdf_page = payload.get("page")
    if pdf_page is not None and hasattr(pdf_page, "get_pixmap"):
        try:
            import fitz
            scale = min(1.0, 620.0 / max(float(page.width or 620), 1.0))
            pix = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            preview = "data:image/jpeg;base64," + base64.b64encode(
                pix.tobytes("jpeg", jpg_quality=68)
            ).decode("ascii")
        except Exception:
            preview = None
    elif (page.metadata or {}).get("image_path"):
        try:
            from PIL import Image
            from io import BytesIO
            image_path = page.metadata["image_path"]
            with Image.open(image_path) as source:
                frame_index = int(page.metadata.get("frame_index", 0) or 0)
                if getattr(source, "n_frames", 1) > 1:
                    source.seek(min(max(frame_index, 0), source.n_frames - 1))
                image = source.convert("RGB")
                image.thumbnail((620, 1200), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="JPEG", quality=72, optimize=True)
                preview = "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
        except Exception:
            preview = None
    safe_metadata = dict(page.metadata or {})
    safe_metadata.pop("image_path", None)
    return {
        "source": page.source,
        "number": page.number,
        "unit_type": page.unit_type,
        "width": page.width,
        "height": page.height,
        "preview": preview,
        "metadata": safe_metadata,
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
