"""Extract displayed equations from digital or scanned PDF pages.

Native text extraction preserves the PDF's text content. Raster equations use
the configured offline OCR engine and are confidence-gated; OCR output is not
represented as symbolic LaTeX unless it already contains equation markup.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple
import re

import cv2
import fitz
import numpy as np

try:
    from models.document_schema import BoundingBox, ExtractedBlock, ExtractionErrorCode
except ModuleNotFoundError:
    from backend.models.document_schema import BoundingBox, ExtractedBlock, ExtractionErrorCode
from .ocr_extractor import OCRExtractor


class EquationExtractor:
    _MATH_CHARS = re.compile(r"[=+−×÷<>≤≥∑∫√∞∂∆πθλμσ∈∉→↔^_{}\\]")

    def __init__(self, ocr_extractor: Optional[OCRExtractor] = None, dpi: int = 220,
                 handwriting: bool = False, min_chars: int = 3):
        self.ocr = ocr_extractor or OCRExtractor(handwriting=handwriting)
        self.dpi = dpi
        self.min_chars = min_chars

    @classmethod
    def _looks_like_equation(cls, text: str) -> bool:
        value = text.strip()
        if len(value) < 2:
            return False
        math_count = len(cls._MATH_CHARS.findall(value))
        digit_count = sum(ch.isdigit() for ch in value)
        return math_count >= 1 and (digit_count > 0 or math_count >= 2)

    @staticmethod
    def _native_candidates(page: fitz.Page) -> List[Tuple[fitz.Rect, str]]:
        found: List[Tuple[fitz.Rect, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(span.get("text", "") for span in spans).strip()
                if not text:
                    continue
                rect = fitz.Rect(line["bbox"])
                # Displayed equations tend to be centered or have a larger math-symbol ratio.
                page_width = page.rect.width
                centered = abs((rect.x0 + rect.x1) / 2 - page_width / 2) < page_width * 0.22
                if EquationExtractor._looks_like_equation(text) and (centered or len(text) < 100):
                    found.append((rect, text))
        return found

    @staticmethod
    def _raster_candidates(image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        # Join glyphs into text lines, while preserving whitespace between lines.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(7, image.shape[1] // 180), 3))
        joined = cv2.dilate(binary, kernel, iterations=1)
        contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        height, width = gray.shape
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w >= 12 and 8 <= h <= max(100, height // 8) and w < width * 0.95:
                boxes.append((x, y, x + w, y + h))
        # Join nearby text-line fragments in the same row.
        boxes.sort(key=lambda box: (box[1], box[0]))
        merged: List[Tuple[int, int, int, int]] = []
        for x0, y0, x1, y1 in boxes:
            if merged and y0 <= merged[-1][3] + 5 and x0 <= merged[-1][2] + 14:
                ax0, ay0, ax1, ay1 = merged[-1]
                merged[-1] = (min(ax0, x0), min(ay0, y0), max(ax1, x1), max(ay1, y1))
            else:
                merged.append((x0, y0, x1, y1))
        return merged

    def extract(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        document = fitz.open(str(pdf_path))
        output: List[ExtractedBlock] = []
        try:
            for page_no, page in enumerate(document):
                native = self._native_candidates(page)
                for rect, text in native:
                    output.append(ExtractedBlock(
                        block_type="text_block",
                        bbox=BoundingBox(page=page_no, x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                        content_raw=text, content_markdown=f"$${text}$$",
                        data={"semantic_type": "equation", "source": "native_pdf_text"}, confidence=0.95,
                    ))
                pix = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                sx, sy = page.rect.width / pix.width, page.rect.height / pix.height
                native_boxes = [tuple(map(float, rect)) for rect, _ in native]
                for x0, y0, x1, y1 in self._raster_candidates(image):
                    box_pdf = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
                    # Skip raster candidates that overlap selectable equation text.
                    if any(self._overlap(box_pdf, box) > 0.5 for box in native_boxes):
                        continue
                    crop = image[max(0, y0 - 3):min(pix.height, y1 + 3), max(0, x0 - 3):min(pix.width, x1 + 3)]
                    if crop.size == 0:
                        continue
                    text, score = self.ocr.recognize(crop)
                    if not text.strip():
                        continue
                    decision = self.ocr.confidence.evaluate_block(crop, text, score, self.ocr.handwriting)
                    if not self._looks_like_equation(text):
                        continue
                    output.append(ExtractedBlock(
                        block_type="text_block",
                        bbox=BoundingBox(page=page_no, x0=box_pdf[0], y0=box_pdf[1], x1=box_pdf[2], y1=box_pdf[3]),
                        content_raw=decision["text"],
                        content_markdown=(f"$${decision['text']}$$" if decision["text"] else None),
                        data={"semantic_type": "equation", "source": "raster_ocr", "sharpness": decision["sharpness"]},
                        confidence=decision["confidence"], is_ambiguous=decision["is_ambiguous"],
                        error_code=decision["error_code"], error_message=decision["error_message"],
                    ))
        finally:
            document.close()
        return output

    @staticmethod
    def _overlap(a: Sequence[float], b: Sequence[float]) -> float:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
        ih = max(0.0, min(ay1, by1) - max(ay0, by0))
        inter = iw * ih
        area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
        area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
        return inter / area_a if area_a > 0 else 0.0
