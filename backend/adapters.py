"""Extractor adapters implementing the detection.router.Extractor protocol.

Each adapter yields detection.schemas.Block instances and never raises
uncaught exceptions — failures become flagged blocks or empty yields
(router wraps remaining failures as ParseError).
"""
from __future__ import annotations

import importlib.util
import io
import re
from typing import Any, Iterable

from detection.schemas import Block, Box, Document, Page, Region, RegionType


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LIST_RE = re.compile(
    r"^(\s*([-*\u2022\u25CF\u25E6]|\d+[.)]|[a-zA-Z][.)])\s+)",
)
_MATH_RE = re.compile(
    r"[=+\-*/^∑∫√∞≤≥≠≈∂∇πθλμσ∈∉→↔_{}\\]|E\s*=\s*mc|NPV|IRR|WACC",
    re.IGNORECASE,
)


def _box_list(box: Box | None) -> list[float] | None:
    if box is None:
        return None
    return [box.x0, box.y0, box.x1, box.y1]


def _region_text_hint(region: Region) -> str:
    """Analyzer sometimes passes metadata dict into text_hint — tolerate that."""
    hint = region.text_hint
    if isinstance(hint, str) and hint.strip():
        return hint.strip()
    if isinstance(hint, dict):
        for key in ("text", "text_hint", "content"):
            val = hint.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    meta = region.metadata or {}
    for key in ("text", "text_hint", "content"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _classify_text(text: str) -> str:
    text_stripped = (text or "").strip()
    if not text_stripped:
        return "paragraph"
    if _LIST_RE.match(text_stripped):
        return "list"
    lines = [ln.strip() for ln in text_stripped.splitlines() if ln.strip()]
    if len(lines) >= 2 and sum(1 for ln in lines if _LIST_RE.match(ln)) >= max(2, len(lines) // 2):
        return "list"
    if len(text_stripped) < 80 and not text_stripped.endswith((".", "?", "!")):
        return "heading"
    return "paragraph"


def _pymupdf_page(page: Page):
    payload = page.payload if isinstance(page.payload, dict) else None
    if not payload:
        return None
    pdf_page = payload.get("page")
    if pdf_page is not None and hasattr(pdf_page, "get_text"):
        return pdf_page
    return None


def _extract_text_from_page(page: Page, region: Region) -> str:
    hint = _region_text_hint(region)
    if hint:
        return hint

    pdf_page = _pymupdf_page(page)
    if pdf_page is None:
        return ""

    try:
        if region.box is not None:
            clip = (region.box.x0, region.box.y0, region.box.x1, region.box.y1)
            text = pdf_page.get_text("text", clip=clip) or ""
        else:
            text = pdf_page.get_text("text") or ""
        return text.strip()
    except Exception:
        return ""


def _make_block(
    *,
    document: Document,
    page: Page,
    region: Region,
    block_type: str,
    content: Any,
    confidence: float | None,
    extractor: str,
    flags: list[str] | None = None,
    metadata: dict | None = None,
    reading_order: int | None = None,
) -> Block:
    return Block(
        block_id=f"{region.region_id}-{block_type}",
        block_type=block_type,
        content=content,
        source=document.source if document else region.source,
        page_number=region.page_number,
        region_id=region.region_id,
        box=region.box,
        reading_order=region.reading_order if reading_order is None else reading_order,
        confidence=confidence if confidence is not None else region.confidence,
        extractor=extractor,
        metadata=dict(metadata or {}),
        flags=list(flags or []),
    )


# ---------------------------------------------------------------------------
# Text / OCR / Layout
# ---------------------------------------------------------------------------

class TextExtractorAdapter:
    """Digital text regions — PyMuPDF page text or region text_hint."""

    name = "text"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        try:
            text = _extract_text_from_page(page, region)
            if not text:
                yield _make_block(
                    document=document,
                    page=page,
                    region=region,
                    block_type="paragraph",
                    content="",
                    confidence=0.4,
                    extractor=self.name,
                    flags=["empty_region", "low_confidence"],
                    metadata={"route": "digital_text"},
                )
                return

            block_type = _classify_text(text)
            conf = 0.98 if block_type == "heading" else 0.96 if block_type == "list" else 0.95
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type=block_type,
                content=text,
                confidence=conf,
                extractor=self.name,
                metadata={"route": "digital_text", "layout_role": "body"},
            )
        except Exception as exc:
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="paragraph",
                content=_region_text_hint(region),
                confidence=0.3,
                extractor=self.name,
                flags=["extractor_error", "low_confidence"],
                metadata={"error": str(exc), "route": "digital_text"},
            )


class OCRExtractorAdapter:
    """Scanned text — pytesseract when available, else text_hint with low confidence."""

    name = "ocr"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        try:
            text, conf, flags, meta = self._ocr(page, region)
            block_type = _classify_text(text) if text else "paragraph"
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type=block_type,
                content=text,
                confidence=conf,
                extractor=self.name,
                flags=flags,
                metadata=meta,
            )
        except Exception as exc:
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="paragraph",
                content=_region_text_hint(region),
                confidence=0.25,
                extractor=self.name,
                flags=["ocr_failed", "low_confidence"],
                metadata={"error": str(exc)},
            )

    def _ocr(self, page: Page, region: Region) -> tuple[str, float, list[str], dict]:
        hint = _region_text_hint(region)
        if importlib.util.find_spec("pytesseract") is None:
            return (
                hint,
                0.35 if hint else 0.2,
                ["ocr_unavailable", "low_confidence"] + ([] if hint else ["empty_region"]),
                {"route": "scanned_text", "engine": None},
            )

        try:
            import pytesseract
            from PIL import Image
        except Exception:
            return hint, 0.35 if hint else 0.2, ["ocr_import_failed", "low_confidence"], {"route": "scanned_text"}

        image = self._region_image(page, region)
        if image is None:
            return (
                hint,
                0.4 if hint else 0.25,
                ["ocr_no_image", "low_confidence"] + ([] if hint else ["empty_region"]),
                {"route": "scanned_text", "engine": "pytesseract"},
            )

        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            parts: list[str] = []
            scores: list[float] = []
            for i, raw in enumerate(data.get("text", [])):
                t = (raw or "").strip()
                try:
                    c = float(data["conf"][i])
                except (KeyError, IndexError, TypeError, ValueError):
                    c = -1.0
                if t and c >= 0:
                    parts.append(t)
                    scores.append(c / 100.0)
            text = " ".join(parts).strip() or hint
            conf = float(sum(scores) / len(scores)) if scores else (0.45 if hint else 0.3)
            flags = []
            if conf < 0.6:
                flags.append("low_confidence")
            if not text:
                flags.append("empty_region")
            return text, min(0.95, max(0.2, conf)), flags, {"route": "scanned_text", "engine": "pytesseract"}
        except Exception as exc:
            return hint, 0.3 if hint else 0.2, ["ocr_failed", "low_confidence"], {"error": str(exc)}

    def _region_image(self, page: Page, region: Region):
        try:
            from PIL import Image
        except Exception:
            return None

        # Image frames from loaders
        img_path = (page.metadata or {}).get("image_path")
        if img_path:
            try:
                im = Image.open(img_path)
                if region.box:
                    return im.crop((int(region.box.x0), int(region.box.y0), int(region.box.x1), int(region.box.y1)))
                return im
            except Exception:
                pass

        pdf_page = _pymupdf_page(page)
        if pdf_page is None:
            return None
        try:
            clip = None
            if region.box is not None:
                clip = (region.box.x0, region.box.y0, region.box.x1, region.box.y1)
            mat = None
            try:
                import fitz
                mat = fitz.Matrix(2, 2)
                pix = pdf_page.get_pixmap(matrix=mat, clip=clip) if clip else pdf_page.get_pixmap(matrix=mat)
            except Exception:
                pix = pdf_page.get_pixmap(clip=clip) if clip else pdf_page.get_pixmap()
            return Image.open(io.BytesIO(pix.tobytes("png")))
        except Exception:
            return None


class LayoutExtractorAdapter:
    """Header / footer / footnote / sidebar / multi_column — text with layout role."""

    name = "layout"

    _ROLE_MAP = {
        RegionType.HEADER: "header",
        RegionType.FOOTER: "footer",
        RegionType.FOOTNOTE: "footnote",
        RegionType.SIDEBAR: "sidebar",
        RegionType.MULTI_COLUMN_TEXT: "multi_column",
        RegionType.DIGITAL_TEXT: "body",
    }

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        try:
            text = _extract_text_from_page(page, region)
            role = self._ROLE_MAP.get(region.region_type, region.region_type.value)
            block_type = _classify_text(text) if text else "paragraph"
            if role in ("header", "footer", "footnote"):
                # Prefer explicit layout block types for assembly
                if role == "header":
                    block_type = "heading" if text and len(text) < 120 else block_type
            flags = []
            conf = 0.92 if text else 0.4
            if not text:
                flags.extend(["empty_region", "low_confidence"])
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type=block_type,
                content=text,
                confidence=conf,
                extractor=self.name,
                flags=flags,
                metadata={
                    "layout_role": role,
                    "route": "layout",
                    "column": (region.metadata or {}).get("column"),
                },
            )
        except Exception as exc:
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="paragraph",
                content=_region_text_hint(region),
                confidence=0.3,
                extractor=self.name,
                flags=["extractor_error", "low_confidence"],
                metadata={"error": str(exc), "layout_role": region.region_type.value},
            )


# ---------------------------------------------------------------------------
# Tables / charts / figures / equations / diagrams
# ---------------------------------------------------------------------------

class TableExtractorAdapter:
    """Try pdfplumber tables; else stub structured table from text_hint."""

    name = "table"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        try:
            matrix, flags, conf, engine = self._extract_matrix(page, region)
            markdown = self._to_markdown(matrix)
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="table",
                content={
                    "matrix": matrix,
                    "markdown": markdown,
                    "text": "\n".join("\t".join(c or "" for c in row) for row in matrix),
                },
                confidence=conf,
                extractor=self.name,
                flags=flags,
                metadata={"route": "table", "engine": engine, "bbox": _box_list(region.box)},
            )
        except Exception as exc:
            hint = _region_text_hint(region)
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="table",
                content={"matrix": [[hint]] if hint else [["[table]"]], "markdown": hint or "| [table] |", "text": hint},
                confidence=0.35,
                extractor=self.name,
                flags=["table_stub", "extractor_error", "low_confidence"],
                metadata={"error": str(exc)},
            )

    def _extract_matrix(self, page: Page, region: Region) -> tuple[list[list[str]], list[str], float, str | None]:
        hint = _region_text_hint(region)

        # Prefer pdfplumber if available
        if importlib.util.find_spec("pdfplumber") is not None:
            try:
                import pdfplumber
                path = page.source
                with pdfplumber.open(path) as pdf:
                    if 0 < page.number <= len(pdf.pages):
                        pl_page = pdf.pages[page.number - 1]
                        tables = pl_page.extract_tables() or []
                        best = self._pick_table(tables, region)
                        if best:
                            matrix = [[(c or "").strip() for c in row] for row in best]
                            return matrix, [], 0.9, "pdfplumber"
            except Exception:
                pass

        # PyMuPDF find_tables when page exposes it
        pdf_page = _pymupdf_page(page)
        if pdf_page is not None and hasattr(pdf_page, "find_tables"):
            try:
                finder = pdf_page.find_tables()
                tables = list(getattr(finder, "tables", finder) or [])
                for table in tables:
                    bbox = getattr(table, "bbox", None)
                    if region.box and bbox and not self._overlaps(region.box, bbox):
                        continue
                    extracted = table.extract() if hasattr(table, "extract") else None
                    if extracted:
                        matrix = [[(c or "").strip() if c is not None else "" for c in row] for row in extracted]
                        return matrix, [], 0.85, "pymupdf"
            except Exception:
                pass

        # Stub from text_hint
        if hint:
            rows = [ln.split("\t") if "\t" in ln else re.split(r"\s{2,}", ln) for ln in hint.splitlines() if ln.strip()]
            if not rows:
                rows = [[hint]]
            return rows, ["table_stub", "low_confidence"], 0.45, "text_hint_stub"

        return [["[table — structured extraction unavailable]"]], ["table_stub", "low_confidence"], 0.35, None

    @staticmethod
    def _overlaps(box: Box, bbox) -> bool:
        try:
            x0, y0, x1, y1 = map(float, bbox)
        except Exception:
            return True
        return not (box.x1 < x0 or box.x0 > x1 or box.y1 < y0 or box.y0 > y1)

    @staticmethod
    def _pick_table(tables: list, region: Region):
        if not tables:
            return None
        if region.box is None:
            return tables[0]
        # Prefer first non-empty
        for t in tables:
            if t and any(any(c for c in row) for row in t):
                return t
        return tables[0]

    @staticmethod
    def _to_markdown(matrix: list[list[str]]) -> str:
        if not matrix:
            return ""
        width = max(len(row) for row in matrix)
        rows = [row + [""] * (width - len(row)) for row in matrix]
        header = rows[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)


class ChartExtractorAdapter:
    name = "chart"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        yield from _typed_visual_block(
            self.name, "chart", document, page, region,
            default_caption="[chart]",
            extra_meta={"visual_kind": "chart"},
        )


class FigureExtractorAdapter:
    name = "figure"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        yield from _typed_visual_block(
            self.name, "figure", document, page, region,
            default_caption="[figure]",
            extra_meta={"visual_kind": "figure"},
        )


class DiagramExtractorAdapter:
    name = "diagram"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        yield from _typed_visual_block(
            self.name, "diagram", document, page, region,
            default_caption="[diagram]",
            extra_meta={"visual_kind": "diagram"},
        )


class EquationExtractorAdapter:
    """Produce equation blocks; detect math-like text; never crash."""

    name = "equation"

    def extract(self, document: Document, page: Page, region: Region) -> Iterable[Block]:
        try:
            text = _extract_text_from_page(page, region)
            math_like = bool(text and _MATH_RE.search(text))
            flags = []
            conf = 0.9 if math_like else 0.7 if text else 0.4
            if not text:
                text = _region_text_hint(region) or "[equation]"
                flags.append("equation_stub" if text == "[equation]" else "text_hint_fallback")
                conf = 0.45
            if text and not math_like and "equation_stub" not in flags:
                flags.append("math_heuristic_weak")
                conf = min(conf, 0.65)
            if conf < 0.6:
                flags.append("low_confidence")
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="equation",
                content={"latex": None, "text": text, "math_like": math_like},
                confidence=conf,
                extractor=self.name,
                flags=flags,
                metadata={"route": "equation", "bbox": _box_list(region.box)},
            )
        except Exception as exc:
            yield _make_block(
                document=document,
                page=page,
                region=region,
                block_type="equation",
                content={"latex": None, "text": _region_text_hint(region) or "[equation]", "math_like": False},
                confidence=0.3,
                extractor=self.name,
                flags=["extractor_error", "low_confidence"],
                metadata={"error": str(exc)},
            )


def _typed_visual_block(
    extractor_name: str,
    block_type: str,
    document: Document,
    page: Page,
    region: Region,
    *,
    default_caption: str,
    extra_meta: dict | None = None,
) -> Iterable[Block]:
    try:
        caption = _region_text_hint(region) or _extract_text_from_page(page, region) or default_caption
        flags = []
        conf = 0.88
        if caption == default_caption:
            flags.append(f"{block_type}_stub")
            conf = 0.55
            flags.append("low_confidence")
        meta = {"route": block_type, "bbox": _box_list(region.box), "provenance": "region_bbox"}
        if extra_meta:
            meta.update(extra_meta)
        yield _make_block(
            document=document,
            page=page,
            region=region,
            block_type=block_type,
            content={"caption": caption, "description": caption},
            confidence=conf,
            extractor=extractor_name,
            flags=flags,
            metadata=meta,
        )
    except Exception as exc:
        yield _make_block(
            document=document,
            page=page,
            region=region,
            block_type=block_type,
            content={"caption": default_caption, "description": default_caption},
            confidence=0.3,
            extractor=extractor_name,
            flags=["extractor_error", "low_confidence"],
            metadata={"error": str(exc), **(extra_meta or {})},
        )
