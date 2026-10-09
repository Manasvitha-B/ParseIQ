"""Extractor adapters implementing the detection.router.Extractor protocol.

Each adapter yields detection.schemas.Block instances and never raises
uncaught exceptions — failures become flagged blocks or empty yields
(router wraps remaining failures as ParseError).
"""
from __future__ import annotations

import importlib.util
import io
import re
from dataclasses import replace
from typing import Any, Iterable

from detection.schemas import Block, Box, Document, Page, Region, RegionType
from backend.vision import get_vision_service
from backend.chart_output import chart_artifacts, render_chart_image, render_region_image


def _vision_result(page: Page, region: Region) -> dict | None:
    cached = (region.metadata or {}).get("vision_result")
    if isinstance(cached, dict):
        return cached
    # ImageClassifier has already tried this crop. Avoid paying/waiting for a
    # second identical request when the provider reported an error.
    if (region.metadata or {}).get("vision_error"):
        return None
    result = get_vision_service().analyze(page, region)
    if isinstance(result, dict) and not result.get("error"):
        region.metadata["vision_result"] = result
        return result
    if isinstance(result, dict) and result.get("error"):
        region.metadata["vision_error"] = result["error"]
    return None


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
_SUPERSCRIPTS = str.maketrans({"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
                               "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"})


def _equation_latex(text: str) -> str:
    """Normalize common Unicode math glyphs while preserving existing LaTeX."""
    value = (text or "").strip().strip("$")
    if not value or "\\" in value:
        return value
    value = re.sub(r"([A-Za-z0-9)\]])([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda match: f"{match.group(1)}^{{{match.group(2).translate(_SUPERSCRIPTS)}}}", value)
    value = value.translate(_SUPERSCRIPTS)
    replacements = {"×": r"\times", "÷": r"\div", "≤": r"\leq", "≥": r"\geq",
                    "≠": r"\ne", "≈": r"\approx", "∞": r"\infty", "√": r"\sqrt{}",
                    "∑": r"\sum", "∫": r"\int", "∂": r"\partial", "∇": r"\nabla",
                    "π": r"\pi", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
                    "σ": r"\sigma", "→": r"\to", "↔": r"\leftrightarrow"}
    for symbol, command in replacements.items():
        value = value.replace(symbol, command)
    value = re.sub(r"(?<![\\\w])([A-Za-z0-9]+)\s*/\s*([A-Za-z0-9]+)(?![\\\w])", r"\\frac{\1}{\2}", value)
    return value


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


def _classify_text(text: str, metadata: dict | None = None) -> str:
    text_stripped = (text or "").replace("\u200b", "").strip()
    if not text_stripped:
        return "paragraph"
    if _LIST_RE.match(text_stripped):
        return "list"
    lines = [ln.strip() for ln in text_stripped.splitlines() if ln.strip()]
    if len(lines) >= 2 and sum(1 for ln in lines if _LIST_RE.match(ln)) >= max(2, len(lines) // 2):
        return "list"
    meta = metadata or {}
    page_size = float(meta.get("page_font_size", 0) or 0)
    font_size = float(meta.get("font_size_max", meta.get("font_size_avg", 0)) or 0)
    is_heading = bool(meta.get("heading_candidate"))
    is_heading = is_heading or (page_size > 0 and font_size >= page_size * 1.18 and len(text_stripped) <= 150)
    is_heading = is_heading or (float(meta.get("bold_fraction", 0) or 0) >= .55 and len(text_stripped) <= 150)
    if is_heading:
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


def _chart_blocks(
    document: Document, page: Page, region: Region, visual: dict, extractor: str,
) -> Iterable[Block]:
    """Create one independently renderable chart block per plot in a vision result."""
    charts = visual.get("charts") if isinstance(visual.get("charts"), list) else []
    if not charts and isinstance(visual.get("chart"), dict):
        charts = [visual["chart"]]
    charts = [chart for chart in charts if isinstance(chart, dict)]
    confidence = max(0.86, min(1.0, float(visual.get("confidence", 0.86))))
    base = region.box or Box(0, 0, float(page.width or 0), float(page.height or 0))
    for index, chart_value in enumerate(charts, start=1):
        chart = dict(chart_value)
        normalized_box = chart.pop("bbox_norm", None)
        chart_region = replace(region, metadata=dict(region.metadata or {}))
        if isinstance(normalized_box, (list, tuple)) and len(normalized_box) == 4:
            try:
                nx0, ny0, nx1, ny1 = (max(0.0, min(1.0, float(value))) for value in normalized_box)
                x0, y0, x1, y1 = base.x0 + nx0 * (base.x1 - base.x0), base.y0 + ny0 * (base.y1 - base.y0), base.x0 + nx1 * (base.x1 - base.x0), base.y0 + ny1 * (base.y1 - base.y0)
                if x1 > x0 and y1 > y0:
                    chart_region.box = Box(x0, y0, x1, y1)
            except (TypeError, ValueError):
                pass
        if len(charts) > 1:
            chart_region.region_id = f"{region.region_id}-chart-{index}"
            chart_region.reading_order = region.reading_order + index - 1
        caption = str(chart.get("title") or f"Extracted chart {index}")
        text = str(visual.get("text") or "").strip()
        content = {"text": text or caption, "caption": caption,
                   "description": str(visual.get("description") or ""), "chart": chart,
                   **chart_artifacts(chart), "plot_image": render_chart_image(chart),
                   "source_image": render_region_image(page, chart_region.box)}
        metadata = {"route": "chart", "bbox": _box_list(chart_region.box),
                    "provenance": "vision_chart_bbox" if chart_region.box != region.box else "region_bbox",
                    "visual_kind": "chart", "vision_model": visual.get("model"),
                    "vision_provider": visual.get("provider")}
        yield _make_block(document=document, page=page, region=chart_region, block_type="chart",
                          content=content, confidence=confidence, extractor=extractor,
                          metadata=metadata)


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

            block_type = _classify_text(text, region.metadata)
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
            vision = _vision_result(page, region)
            if vision:
                kind = str(vision.get("block_type") or "text_block")
                text = str(vision.get("text") or "").strip()
                description = str(vision.get("description") or "").strip()
                latex = str(vision.get("latex") or "").strip()
                confidence = max(0.0, min(1.0, float(vision.get("confidence", 0.86))))
                base_meta = {"route": "vision_handwriting", "engine": vision.get("provider", "vision"),
                             "vision_model": vision.get("model"), "vision_result": vision}
                if kind == "table" and vision.get("table"):
                    content = dict(vision["table"])
                    content["text"] = text or str(content.get("markdown") or "")
                    yield _make_block(document=document, page=page, region=region, block_type="table",
                        content=content, confidence=confidence, extractor=self.name, metadata=base_meta)
                    return
                if kind == "chart" and (vision.get("charts") or isinstance(vision.get("chart"), dict)):
                    yield from _chart_blocks(document, page, region, vision, self.name)
                    return
                if kind == "equation" and (latex or text):
                    yield _make_block(document=document, page=page, region=region, block_type="equation",
                        content={"latex": latex or _equation_latex(text), "text": text or latex, "math_like": True},
                        confidence=confidence, extractor=self.name, metadata=base_meta)
                    return
                if kind == "figure" and (description or text):
                    yield _make_block(document=document, page=page, region=region, block_type="figure",
                        content={"text": text or description, "caption": description or text,
                                 "description": description or text}, confidence=confidence,
                        extractor=self.name, metadata=base_meta)
                    return
                if text:
                    yield _make_block(document=document, page=page, region=region,
                        block_type=_classify_text(text, region.metadata), content=text,
                        confidence=confidence, extractor=self.name, metadata=base_meta)
                    return
            text, conf, flags, meta = self._ocr(page, region)
            block_type = _classify_text(text, region.metadata) if text else "paragraph"
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
        def ai_fallback(local_text: str = "", local_score: float = 0.0):
            vision = _vision_result(page, region)
            if vision:
                text = vision.get("text") or vision.get("latex") or vision.get("description") or ""
                if vision.get("block_type") == "table" and vision.get("table"):
                    text = vision["table"].get("markdown") or text
                if text:
                    return text, max(0.86, float(vision.get("confidence", 0.86))), [], {
                        "route": "scanned_text", "engine": vision.get("provider", "vision"),
                        "vision_model": vision.get("model"), "vision_result": vision,
                        "local_ocr_confidence": local_score,
                    }
            return None
        if importlib.util.find_spec("pytesseract") is None:
            ai = ai_fallback(hint, 0.0)
            if ai:
                return ai
            return (hint, 0.35 if hint else 0.2,
                    ["ocr_unavailable", "low_confidence"] + ([] if hint else ["empty_region"]),
                    {"route": "scanned_text", "engine": None,
                     "vision_error": (region.metadata or {}).get("vision_error")})

        try:
            import pytesseract
            from PIL import Image
        except Exception:
            return hint, 0.35 if hint else 0.2, ["ocr_import_failed", "low_confidence"], {"route": "scanned_text"}

        image = self._region_image(page, region)
        if image is None:
            ai = ai_fallback(hint, 0.0)
            if ai:
                return ai
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
            if conf < 0.7 or not text:
                ai = ai_fallback(text, conf)
                if ai:
                    return ai
            flags = []
            if conf < 0.6:
                flags.append("low_confidence")
            if not text:
                flags.append("empty_region")
            return text, min(0.95, max(0.2, conf)), flags, {"route": "scanned_text", "engine": "pytesseract"}
        except Exception as exc:
            ai = ai_fallback(hint, 0.0)
            if ai:
                return ai
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
                with Image.open(img_path) as source:
                    frame_index = int((page.metadata or {}).get("frame_index", 0) or 0)
                    if getattr(source, "n_frames", 1) > 1:
                        source.seek(min(max(frame_index, 0), source.n_frames - 1))
                    im = source.copy()
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
            block_type = _classify_text(text, region.metadata) if text else "paragraph"
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
                metadata={"route": "table", "engine": engine, "bbox": _box_list(region.box),
                          "vision_error": (region.metadata or {}).get("vision_error")},
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

        # Use vision only when native table extraction did not return cells.
        visual = _vision_result(page, region)
        if visual and isinstance(visual.get("table"), dict):
            matrix = visual["table"].get("matrix")
            if isinstance(matrix, list) and matrix:
                clean = [[str(cell if cell is not None else "").strip() for cell in row]
                         for row in matrix if isinstance(row, list)]
                if clean:
                    return clean, [], max(0.86, float(visual.get("confidence", 0.86))), "vision"

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
            visual = (region.metadata or {}).get("vision_result")
            if isinstance(visual, dict) and visual.get("equations"):
                equations = [item for item in visual["equations"] if isinstance(item, dict)]
                base = region.box or Box(0, 0, float(page.width or 0), float(page.height or 0))
                confidence = max(0.0, min(1.0, float(visual.get("confidence", 0.86))))
                for index, equation in enumerate(equations, start=1):
                    equation_region = replace(region, metadata=dict(region.metadata or {}))
                    normalized_box = equation.get("bbox_norm")
                    if isinstance(normalized_box, (list, tuple)) and len(normalized_box) == 4:
                        try:
                            nx0, ny0, nx1, ny1 = (max(0.0, min(1.0, float(value))) for value in normalized_box)
                            x0 = base.x0 + nx0 * (base.x1 - base.x0)
                            y0 = base.y0 + ny0 * (base.y1 - base.y0)
                            x1 = base.x0 + nx1 * (base.x1 - base.x0)
                            y1 = base.y0 + ny1 * (base.y1 - base.y0)
                            if x1 > x0 and y1 > y0:
                                equation_region.box = Box(x0, y0, x1, y1)
                        except (TypeError, ValueError):
                            pass
                    if len(equations) > 1:
                        equation_region.region_id = f"{region.region_id}-equation-{index}"
                        equation_region.reading_order = region.reading_order + index - 1
                    latex = str(equation.get("latex") or "").strip()
                    text = str(equation.get("text") or "").strip()
                    if not latex:
                        latex = _equation_latex(text)
                    if not text:
                        text = latex
                    if not latex and not text:
                        continue
                    yield _make_block(
                        document=document, page=page, region=equation_region, block_type="equation",
                        content={"latex": latex, "text": text, "math_like": True,
                                 "source_image": render_region_image(page, equation_region.box)},
                        confidence=confidence, extractor=self.name,
                        metadata={"route": "vision_equation", "vision_model": visual.get("model"),
                                  "vision_provider": visual.get("provider"), "bbox": _box_list(equation_region.box)},
                    )
                return

            text = _extract_text_from_page(page, region)
            math_like = bool(text and _MATH_RE.search(text))
            if math_like:
                yield _make_block(
                    document=document, page=page, region=region, block_type="equation",
                    content={"latex": _equation_latex(text), "text": text, "math_like": True,
                             "source_image": render_region_image(page, region.box)},
                    confidence=0.95, extractor=self.name,
                    metadata={"route": "equation", "source": "native_pdf_text", "bbox": _box_list(region.box)},
                )
                return
            if not isinstance(visual, dict):
                visual = _vision_result(page, region)
            if visual and (visual.get("latex") or visual.get("text")):
                latex = visual.get("latex") or _equation_latex(visual.get("text") or "")
                yield _make_block(
                    document=document, page=page, region=region, block_type="equation",
                    content={"latex": latex, "text": visual.get("text") or latex, "math_like": True,
                             "source_image": render_region_image(page, region.box)},
                    confidence=max(0.86, float(visual.get("confidence", 0.86))), extractor=self.name,
                    metadata={"route": "equation", "vision_model": visual.get("model"),
                              "vision_provider": visual.get("provider"), "bbox": _box_list(region.box)},
                )
                return
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
                content={"latex": _equation_latex(text) if math_like else None, "text": text, "math_like": math_like,
                         "source_image": render_region_image(page, region.box)},
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
                content={"latex": None, "text": _region_text_hint(region) or "[equation]", "math_like": False,
                         "source_image": render_region_image(page, region.box)},
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
        visual = _vision_result(page, region)
        visual_type = str((visual or {}).get("block_type") or "").strip().lower()
        if visual_type in {"text", "text_block"}:
            visual_type = "text"
        elif visual_type not in {"table", "chart", "figure", "equation"}:
            visual_type = block_type
        output_type = visual_type or block_type
        if output_type == "chart" and visual:
            charts = visual.get("charts") if isinstance(visual.get("charts"), list) else []
            if charts or isinstance(visual.get("chart"), dict):
                yield from _chart_blocks(document, page, region, visual, extractor_name)
                return
        caption = ((visual or {}).get("description") or (visual or {}).get("text") or
                   _region_text_hint(region) or _extract_text_from_page(page, region) or default_caption)
        flags = []
        conf = max(0.86, float(visual.get("confidence", 0.86))) if visual else 0.88
        if caption == default_caption:
            flags.append(f"{block_type}_stub")
            conf = 0.55
            flags.append("low_confidence")
        meta = {"route": output_type, "bbox": _box_list(region.box), "provenance": "region_bbox"}
        if visual:
            meta.update({"vision_model": visual.get("model"), "vision_provider": visual.get("provider")})
        elif (region.metadata or {}).get("vision_error"):
            meta["vision_error"] = region.metadata["vision_error"]
        if extra_meta:
            meta.update(extra_meta)
        if visual and visual_type:
            meta["visual_kind"] = output_type
        if output_type == "table" and visual and visual.get("table"):
            content = visual["table"]
            content.update({"text": visual.get("text") or caption})
        elif output_type == "chart" and visual:
            chart = visual.get("chart", {})
            content = {"text": visual.get("text") or caption, "caption": caption,
                       "description": visual.get("description", ""), "chart": chart,
                       **chart_artifacts(chart), "plot_image": render_chart_image(chart),
                       "source_image": render_region_image(page, region.box)}
        elif output_type == "equation" and visual:
            content = {"latex": visual.get("latex", ""), "text": visual.get("text", caption), "math_like": True}
        elif output_type == "text" and visual:
            content = {"text": visual.get("text", caption), "description": visual.get("description", "")}
        else:
            content = {"text": (visual or {}).get("text") or caption,
                       "caption": caption,
                       "description": (visual or {}).get("description") or caption}
        if output_type in {"figure", "diagram"}:
            content["source_image"] = render_region_image(page, region.box)
        yield _make_block(
            document=document,
            page=page,
            region=region,
            block_type=output_type,
            content=content,
            confidence=conf,
            extractor=extractor_name,
            flags=flags,
            metadata=meta,
        )
    except Exception as exc:
        content = {"caption": default_caption, "description": default_caption}
        if block_type in {"chart", "figure", "diagram"}:
            content["source_image"] = render_region_image(page, region.box)
        yield _make_block(
            document=document,
            page=page,
            region=region,
            block_type=block_type,
            content=content,
            confidence=0.3,
            extractor=extractor_name,
            flags=["extractor_error", "low_confidence"],
            metadata={"error": str(exc), **(extra_meta or {})},
        )
