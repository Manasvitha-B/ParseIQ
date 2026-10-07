"""Native and scanned table extraction with cell-level OCR provenance."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple
import cv2
import fitz
import numpy as np
from models.document_schema import BoundingBox, ExtractedBlock, ExtractionErrorCode, TableCell
from .ocr_extractor import OCRExtractor


class TableExtractor:
    def __init__(self, ocr_extractor: Optional[OCRExtractor] = None, dpi: int = 200):
        self.ocr = ocr_extractor or OCRExtractor()
        self.dpi = dpi

    @staticmethod
    def _markdown(matrix: List[List[Optional[str]]]) -> str:
        if not matrix: return ""
        rows = [[(value or "").replace("|", "\\|").replace("\n", " ") for value in row] for row in matrix]
        width = max(map(len, rows))
        rows = [row + [""] * (width-len(row)) for row in rows]
        return "\n".join(["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"]*width) + " |"] +
                         ["| " + " | ".join(row) + " |" for row in rows[1:]])

    def _block(self, page_no: int, bbox: Sequence[float], matrix, cell_rows, confidence: float) -> ExtractedBlock:
        markdown = self._markdown(matrix)
        return ExtractedBlock(
            block_type="table",
            bbox=BoundingBox(page=page_no, x0=float(bbox[0]), y0=float(bbox[1]), x1=float(bbox[2]), y1=float(bbox[3])),
            content_raw="\n".join("\t".join(c or "" for c in r) for r in matrix),
            content_markdown=markdown,
            data={"matrix": matrix, "cells": [[c.dict() for c in row] for row in cell_rows]},
            confidence=confidence,
            is_ambiguous=confidence < 0.65,
            error_code=ExtractionErrorCode.ERR_DEGRADED_TEXT_LOW_CONFIDENCE if confidence < 0.65 else ExtractionErrorCode.NONE,
        )

    def _ocr_grid(self, image: np.ndarray, page_no: int, origin: Tuple[int,int], scale: float) -> List[ExtractedBlock]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)
        h, w = binary.shape
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15,w//30),1)))
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1,max(15,h//30))))
        grid = cv2.add(horizontal, vertical)
        contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) > 0.01*w*h]
        if not boxes: return []
        x0,y0 = min(x for x,y,bw,bh in boxes), min(y for x,y,bw,bh in boxes)
        x1,y1 = max(x+bw for x,y,bw,bh in boxes), max(y+bh for x,y,bw,bh in boxes)
        # Merge aligned detected horizontal/vertical line coordinates into a rectangular grid.
        row_lines = self._line_centers(horizontal, axis=1)
        col_lines = self._line_centers(vertical, axis=0)
        row_lines = [v for v in row_lines if y0-3 <= v <= y1+3]
        col_lines = [v for v in col_lines if x0-3 <= v <= x1+3]
        if len(row_lines) < 2 or len(col_lines) < 2: return []
        row_lines, col_lines = sorted(row_lines), sorted(col_lines)
        matrix, cells, scores = [], [], []
        ox, oy = origin
        for ri, (ya,yb) in enumerate(zip(row_lines, row_lines[1:])):
            row, cell_row = [], []
            for ci, (xa,xb) in enumerate(zip(col_lines, col_lines[1:])):
                pad = 2
                crop = image[max(0,ya+pad):min(h,yb-pad), max(0,xa+pad):min(w,xb-pad)]
                text, conf = self.ocr.recognize(crop) if crop.size else ("",0.0)
                checked = self.ocr.confidence.evaluate_block(crop, text, conf, self.ocr.handwriting)
                val = checked["text"]
                row.append(val)
                scores.append(checked["confidence"])
                cell_row.append(TableCell(row=ri,column=ci,text=val,confidence=checked["confidence"],
                    is_ambiguous=checked["is_ambiguous"],error_code=checked["error_code"],
                    bbox=BoundingBox(page=page_no,x0=(ox+xa)/scale,y0=(oy+ya)/scale,x1=(ox+xb)/scale,y1=(oy+yb)/scale)))
            matrix.append(row); cells.append(cell_row)
        confidence = float(np.mean(scores)) if scores else 0.0
        return [self._block(page_no, ((ox+x0)/scale,(oy+y0)/scale,(ox+x1)/scale,(oy+y1)/scale), matrix,cells,confidence)]

    @staticmethod
    def _line_centers(mask: np.ndarray, axis: int) -> List[int]:
        projection = np.count_nonzero(mask, axis=axis)
        threshold = max(4, int(mask.shape[1-axis] * 0.2))
        active = np.flatnonzero(projection >= threshold)
        groups=[]
        for value in active:
            if not groups or value > groups[-1][-1]+2: groups.append([int(value)])
            else: groups[-1].append(int(value))
        return [int(np.mean(g)) for g in groups]

    def extract(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        output: List[ExtractedBlock] = []
        doc = fitz.open(str(pdf_path))
        try:
            for page_no,page in enumerate(doc):
                found_native = False
                try:
                    import pdfplumber
                    with pdfplumber.open(str(pdf_path)) as pdf:
                        for table in pdf.pages[page_no].find_tables():
                            raw = table.extract() or []
                            if not raw: continue
                            matrix=[[str(c).strip() if c is not None else None for c in row] for row in raw]
                            cells=[]
                            for ri,row in enumerate(matrix):
                                cell_row=[]
                                row_obj=table.rows[ri] if ri < len(table.rows) else None
                                for ci,v in enumerate(row):
                                    cell_bbox=None
                                    if row_obj is not None and ci < len(row_obj.cells) and row_obj.cells[ci]:
                                        cx0,ctop,cx1,cbottom=row_obj.cells[ci]
                                        cell_bbox=BoundingBox(page=page_no,x0=cx0,y0=ctop,x1=cx1,y1=cbottom)
                                    cell_row.append(TableCell(row=ri,column=ci,text=v,bbox=cell_bbox))
                                cells.append(cell_row)
                            x0,top,x1,bottom=table.bbox
                            output.append(self._block(page_no,(x0,top,x1,bottom),matrix,cells,1.0)); found_native=True
                except ImportError:
                    pass
                if not found_native:
                    pix=page.get_pixmap(matrix=fitz.Matrix(self.dpi/72,self.dpi/72),alpha=False)
                    img=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,pix.n)
                    scale=self.dpi/72.0
                    output.extend(self._ocr_grid(img,page_no,(0,0),scale))
        finally: doc.close()
        return output

    def extract_from_pdf(self, pdf_path: str | Path) -> List[ExtractedBlock]:
        return self.extract(pdf_path)
