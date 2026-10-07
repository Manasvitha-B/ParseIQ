"""Detect chart regions and record visual cues with page-space provenance.

This module detects candidate plot areas; it does not claim to recover numeric
series values without a chart digitization model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import fitz
import numpy as np

try:
    from backend.models.document_schema import BoundingBox, ExtractedBlock
except ModuleNotFoundError:
    from models.document_schema import BoundingBox, ExtractedBlock


class ChartExtractor:
    def __init__(self, output_dir: str | Path = "assets/charts", dpi: int = 180,
                 min_width: int = 100, min_height: int = 80):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dpi = dpi
        self.min_width = min_width
        self.min_height = min_height

    @staticmethod
    def _merge_overlapping(boxes: List[Tuple[int, int, int, int]], gap: int = 6) -> List[Tuple[int, int, int, int]]:
        merged: List[Tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda b: (b[1], b[0])):
            x0, y0, x1, y1 = box
            match = None
            for i, (ax0, ay0, ax1, ay1) in enumerate(merged):
                if x0 <= ax1 + gap and x1 + gap >= ax0 and y0 <= ay1 + gap and y1 + gap >= ay0:
                    match = i
                    break
            if match is None:
                merged.append(box)
            else:
                ax0, ay0, ax1, ay1 = merged[match]
                merged[match] = (min(ax0, x0), min(ay0, y0), max(ax1, x1), max(ay1, y1))
        return merged

    @staticmethod
    def _visual_cues(crop: np.ndarray) -> Dict[str, Any]:
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
        edges = cv2.Canny(gray, 50, 150)
        min_line = max(25, min(gray.shape[:2]) // 4)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35,
                                minLineLength=min_line, maxLineGap=8)
        horizontal = vertical = 0
        if lines is not None:
            normalized = np.asarray(lines).reshape(-1, 4)
            for line in normalized:
                x0, y0, x1, y1 = map(int, line[:4])
                dx, dy = abs(x1 - x0), abs(y1 - y0)
                if dy <= max(2, dx * 0.08):
                    horizontal += 1
                if dx <= max(2, dy * 0.08):
                    vertical += 1
        # Histogram entropy is a compact measure of tonal/color variation.
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).ravel().astype(np.float64)
        probs = hist / max(float(hist.sum()), 1.0)
        nz = probs[probs > 0]
        entropy = float(-(nz * np.log2(nz)).sum())
        return {"horizontal_lines": horizontal, "vertical_lines": vertical,
                "histogram_entropy": entropy, "axes_detected": horizontal > 0 and vertical > 0}

    def _page_candidates(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=45,
                                minLineLength=max(self.min_width, image.shape[1] // 12), maxLineGap=12)
        if lines is None:
            return []
        boxes = []
        normalized = np.asarray(lines).reshape(-1, 4)
        for line in normalized:
            x0, y0, x1, y1 = map(int, line[:4])
            dx, dy = abs(x1 - x0), abs(y1 - y0)
            if dy <= 3 and dx >= self.min_width:
                # Pair long horizontal and vertical plot axes via connected edge components below.
                boxes.append((min(x0, x1), max(0, y0 - 2), max(x0, x1), y0 + 2))
            elif dx <= 3 and dy >= self.min_height:
                boxes.append((max(0, x0 - 2), min(y0, y1), x0 + 2, max(y0, y1)))
        if not boxes:
            return []
        # Expand line fragments to enclosing components so the candidate includes plotted marks.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, image.shape[1] // 100), 9))
        joined = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        components = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w >= self.min_width and h >= self.min_height:
                components.append((x, y, x + w, y + h))
        return self._merge_overlapping(components or boxes)

    def extract(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        document = fitz.open(str(pdf_path))
        output: List[ExtractedBlock] = []
        try:
            for page_no, page in enumerate(document):
                pix = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                sx, sy = page.rect.width / pix.width, page.rect.height / pix.height
                for index, (x0, y0, x1, y1) in enumerate(self._page_candidates(image)):
                    crop = image[max(0, y0):min(pix.height, y1), max(0, x0):min(pix.width, x1)]
                    if crop.size == 0:
                        continue
                    cues = self._visual_cues(crop)
                    # Require a plausible pair of plot axes to avoid promoting every image to a chart.
                    if not cues["axes_detected"]:
                        continue
                    path = self.output_dir / f"page_{page_no + 1}_chart_{index + 1}.png"
                    cv2.imwrite(str(path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
                    output.append(ExtractedBlock(
                        block_type="chart",
                        bbox=BoundingBox(page=page_no, x0=x0 * sx, y0=y0 * sy, x1=x1 * sx, y1=y1 * sy),
                        content_raw=None,
                        content_markdown=f"![Chart]({path.as_posix()})",
                        data={"asset_path": str(path), "visual_cues": cues,
                              "series_values_extracted": False},
                        confidence=0.7,
                    ))
        finally:
            document.close()
        return output
