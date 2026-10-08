"""Final assembly of ParseResult into API-ready document payloads."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from detection.schemas import Block, Box, Document, Page, ParseError, Region

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Map extractor / block_type strings → semantic vocabulary used in markdown/JSON
_SEMANTIC_MAP = {
    "heading": "heading",
    "title": "heading",
    "paragraph": "paragraph",
    "text": "paragraph",
    "caption": "paragraph",
    "list": "list",
    "list_item": "list",
    "bullet": "list",
    "table": "table",
    "figure": "figure",
    "image": "figure",
    "photo": "figure",
    "screenshot": "figure",
    "chart": "chart",
    "diagram": "diagram",
    "equation": "equation",
    "formula": "equation",
    "math": "equation",
    "header": "heading",
    "footer": "paragraph",
    "footnote": "paragraph",
}


def _box_to_list(box: Box | None) -> list[float] | None:
    if box is None:
        return None
    return [float(box.x0), float(box.y0), float(box.x1), float(box.y1)]


def _content_as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("markdown", "text", "caption", "description", "latex"):
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                return val
        matrix = content.get("matrix")
        if isinstance(matrix, list):
            return "\n".join("\t".join(str(c or "") for c in row) for row in matrix)
        return str(content)
    return str(content)


def _semantic_type(block: Block) -> str:
    raw = (block.block_type or "paragraph").strip().lower()
    mapped = _SEMANTIC_MAP.get(raw)
    if mapped:
        return mapped
    # layout role override
    role = (block.metadata or {}).get("layout_role")
    if isinstance(role, str) and role.lower() in ("header",):
        return "heading"
    return "paragraph"


def _block_dict(block: Block, index: int) -> dict[str, Any]:
    semantic = _semantic_type(block)
    bid = block.block_id or f"BLOCK_{index + 1:03d}"
    return {
        "block_id": bid,
        "type": semantic,
        "block_type": block.block_type,
        "content": block.content,
        "text": _content_as_text(block.content),
        "page": block.page_number,
        "bbox": _box_to_list(block.box),
        "confidence": block.confidence,
        "flags": list(block.flags or []),
        "extractor": block.extractor,
        "reading_order": block.reading_order,
        "region_id": block.region_id,
        "metadata": dict(block.metadata or {}),
    }


def _try_enrich_with_parser(block_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optional P2B enrichment via local parser package (stdlib name collision safe)."""
    try:
        semantic_mod = importlib.import_module("parser.semantic_blocks")
        normalize_blocks = getattr(semantic_mod, "normalize_blocks", None)
        if callable(normalize_blocks):
            # Adapt to dicts with 'type' / 'text' keys expected by P2B
            adapted = []
            for b in block_dicts:
                adapted.append({
                    **b,
                    "type": b.get("block_type") or b.get("type"),
                    "text": b.get("text") or _content_as_text(b.get("content")),
                    "bbox": b.get("bbox") or [0, 0, 0, 0],
                })
            normalized = normalize_blocks(adapted)
            if isinstance(normalized, list) and normalized:
                out = []
                for orig, norm in zip(block_dicts, normalized):
                    merged = dict(orig)
                    if isinstance(norm, dict):
                        st = norm.get("semantic_type")
                        if st:
                            merged["semantic_type"] = st
                            # Prefer lowercase semantic for API type when available
                            merged["type"] = str(st).lower()
                    out.append(merged)
                block_dicts = out
    except Exception:
        pass

    try:
        reading_mod = importlib.import_module("parser.reading_order")
        reconstruct = getattr(reading_mod, "reconstruct_reading_order", None)
        process_page = getattr(reading_mod, "process_page", None)
        if callable(reconstruct):
            # reconstruct_reading_order may expect page-level structures; soft-apply if signature fits
            try:
                ordered = reconstruct(block_dicts)
                if isinstance(ordered, list) and ordered:
                    for i, b in enumerate(ordered):
                        if isinstance(b, dict) and "reading_order" not in b:
                            b["reading_order"] = i
                    return ordered
            except TypeError:
                pass
        if callable(process_page):
            try:
                # Best-effort: wrap as a single page document fragment
                page_doc = {"page_number": 1, "elements": block_dicts, "blocks": block_dicts}
                result = process_page(page_doc)
                if isinstance(result, dict):
                    elems = result.get("blocks") or result.get("elements")
                    if isinstance(elems, list) and elems:
                        return elems
            except Exception:
                pass
    except Exception:
        pass

    return block_dicts


def _to_markdown(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for b in sorted(blocks, key=lambda x: (x.get("page") or 0, x.get("reading_order") or 0, x.get("block_id") or "")):
        sem = (b.get("type") or "paragraph").lower()
        text = b.get("text") or _content_as_text(b.get("content"))
        content = b.get("content")

        if sem == "heading":
            parts.append(f"## {text}\n")
        elif sem == "list":
            for line in (text or "").splitlines() or [text]:
                line = (line or "").strip()
                if not line:
                    continue
                if line.startswith(("-", "*", "•")):
                    parts.append(f"{line}")
                else:
                    parts.append(f"- {line}")
            parts.append("")
        elif sem == "table":
            md = ""
            if isinstance(content, dict) and content.get("markdown"):
                md = content["markdown"]
            else:
                md = text
            parts.append(md)
            parts.append("")
        elif sem == "equation":
            parts.append(f"$$\n{text}\n$$\n")
        elif sem in ("figure", "chart", "diagram"):
            description = text
            if isinstance(content, dict):
                description = content.get("description") or content.get("caption") or text
            if sem == "chart" and isinstance(content, dict) and isinstance(content.get("chart"), dict):
                chart_json = json.dumps(content["chart"], ensure_ascii=False, indent=2)
                parts.append(f"**Chart:** {description}\n\n```json\n{chart_json}\n```\n")
            else:
                parts.append(f"**{sem.title()}:** {description}\n")
        else:
            if text:
                parts.append(text)
                parts.append("")
    return "\n".join(parts).strip() + ("\n" if parts else "")


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


class FinalAssembler:
    """Assemble detection pipeline outputs into a serializable document dict."""

    def assemble(
        self,
        document: Document | None,
        pages: Sequence[Page],
        regions: Sequence[Region],
        blocks: Sequence[Block],
        errors: Sequence[ParseError],
    ) -> dict[str, Any]:
        error_list = [_error_dict(e) for e in errors]
        status = "failed" if document is None and error_list else ("partial" if error_list else "ok")
        if document is not None and not blocks and error_list:
            # Detection/load failed hard
            non_recoverable = any(not e.recoverable for e in errors)
            if non_recoverable:
                status = "failed"

        block_dicts = [_block_dict(b, i) for i, b in enumerate(blocks)]
        # Stable BLOCK_NNN ids for API consumers when ids are region-derived
        for i, bd in enumerate(block_dicts):
            if not bd["block_id"] or bd["block_id"].startswith("p"):
                bd["api_block_id"] = f"BLOCK_{i + 1:03d}"
            else:
                bd["api_block_id"] = bd["block_id"] if bd["block_id"].startswith("BLOCK_") else f"BLOCK_{i + 1:03d}"

        enriched = _try_enrich_with_parser(block_dicts)
        markdown = _to_markdown(enriched)

        doc_meta: dict[str, Any] = {}
        if document is not None:
            doc_meta = {
                "source": document.source,
                "filename": Path(document.source).name,
                "file_type": document.file_type.value if hasattr(document.file_type, "value") else str(document.file_type),
                "size_bytes": document.size_bytes,
                "sha256": document.sha256,
                "metadata": dict(document.metadata or {}),
                "page_count": len(pages),
                "region_count": len(regions),
                "block_count": len(enriched),
            }

        json_export = {
            "document": doc_meta,
            "blocks": [
                {
                    "id": b.get("api_block_id") or b.get("block_id"),
                    "type": b.get("type"),
                    "text": b.get("text"),
                    "content": b.get("content"),
                    "page": b.get("page"),
                    "bbox": b.get("bbox"),
                    "confidence": b.get("confidence"),
                    "extractor": b.get("extractor"),
                    "reading_order": b.get("reading_order"),
                    "flags": b.get("flags"),
                    "metadata": b.get("metadata"),
                }
                for b in enriched
            ],
            "markdown": markdown,
        }

        pipeline_stages = {
            "detect": {
                "status": "ok" if document is not None else "failed",
                "file_type": doc_meta.get("file_type"),
            },
            "route": {
                "status": "ok" if regions else ("skipped" if status == "failed" else "empty"),
                "regions": len(regions),
            },
            "extract": {
                "status": "ok" if blocks else ("partial" if regions else "skipped"),
                "blocks": len(blocks),
            },
            "assemble": {
                "status": "ok",
                "markdown_chars": len(markdown),
                "enrichment": "parser" if any("semantic_type" in b for b in enriched) else "builtin",
            },
        }

        # Surface stage failures from error components
        for err in errors:
            comp = (err.component or "").lower()
            if comp in ("detect", "loader") and pipeline_stages["detect"]["status"] == "ok":
                pipeline_stages["detect"]["status"] = "failed" if not err.recoverable else "partial"
            if comp in ("router", "analyzer", "image_classifier"):
                pipeline_stages["route"]["status"] = "partial"
            if (comp and "extract" in comp) or comp in (
                "text", "ocr", "table", "chart", "figure", "equation", "diagram", "layout",
            ):
                pipeline_stages["extract"]["status"] = "partial"
            if comp == "assembler":
                pipeline_stages["assemble"]["status"] = "partial"

        return {
            "status": status,
            "document": doc_meta,
            "blocks": enriched,
            "markdown": markdown,
            "json_export": json_export,
            "errors": error_list,
            "pipeline_stages": pipeline_stages,
        }
