"""Extract embedded figures and rasterized visual regions from PDFs."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import cv2
import fitz
import numpy as np
from models.document_schema import BoundingBox, ExtractedBlock


class ImageExtractor:
    def __init__(self, output_dir: str | Path = "assets", min_size: int = 45, dpi: int = 180):
        self.output_dir, self.min_size, self.dpi = Path(output_dir), min_size, dpi
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _classify(image: np.ndarray) -> str:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        edges = cv2.Canny(gray, 60, 160)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40,
                                minLineLength=max(20, min(gray.shape[:2]) // 4), maxLineGap=8)
        horizontal_vertical = 0
        if lines is not None:
            normalized = np.asarray(lines).reshape(-1, 4)
            horizontal_vertical = sum(
                1
                for line in normalized
                if min(abs(int(line[3]) - int(line[1])), abs(int(line[2]) - int(line[0]))) < 5
            )
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
        variance = float(np.var(hist / max(1.0, hist.sum())))
        return "chart" if horizontal_vertical >= 2 and variance > 0.0002 else "figure"

    def extract(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        doc = fitz.open(str(pdf_path))
        blocks: List[ExtractedBlock] = []
        try:
            for page_no, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                page_img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                scale_x, scale_y = page.rect.width / pix.width, page.rect.height / pix.height
                candidates = []
                for info in page.get_image_info(xrefs=True):
                    rect = fitz.Rect(info["bbox"])
                    x0, y0, x1, y1 = [int(v) for v in (rect.x0/scale_x, rect.y0/scale_y, rect.x1/scale_x, rect.y1/scale_y)]
                    if x1-x0 >= self.min_size and y1-y0 >= self.min_size:
                        candidates.append((x0, y0, x1, y1))
                if not candidates:
                    gray = cv2.cvtColor(page_img, cv2.COLOR_RGB2GRAY)
                    _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
                    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    candidates = [cv2.boundingRect(c) for c in contours]
                    candidates = [(x, y, x+w, y+h) for x, y, w, h in candidates
                                  if w >= self.min_size and h >= self.min_size and w*h > 2500]
                for index, (x0, y0, x1, y1) in enumerate(candidates):
                    crop = page_img[max(0,y0):min(pix.height,y1), max(0,x0):min(pix.width,x1)]
                    if crop.size == 0: continue
                    out = self.output_dir / f"page_{page_no+1}_visual_{index+1}.png"
                    cv2.imwrite(str(out), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
                    kind = self._classify(crop)
                    blocks.append(ExtractedBlock(block_type=kind, bbox=BoundingBox(page=page_no,
                        x0=x0*scale_x, y0=y0*scale_y, x1=x1*scale_x, y1=y1*scale_y),
                        content_raw=None, content_markdown=f"![{kind}]({out.as_posix()})",
                        data={"asset_path": str(out), "width": x1-x0, "height": y1-y0}, confidence=1.0))
        finally:
            doc.close()
        return blocks

    def extract_from_pdf(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        return self.extract(pdf_path)
