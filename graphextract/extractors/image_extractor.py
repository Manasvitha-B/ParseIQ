"""Offline OCR wrapper with preprocessing, backend adapters and confidence gating."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    import pytesseract
except Exception:
    pytesseract = None

from models.document_schema import BoundingBox, ExtractedBlock, ExtractionErrorCode
from processing.confidence import ConfidenceEngine


class OCRExtractor:
    def __init__(self, engine: str = "auto", confidence_engine: Optional[ConfidenceEngine] = None,
                 handwriting: bool = False, trocr_model: Optional[str] = None):
        self.engine = engine.lower()
        self.confidence = confidence_engine or ConfidenceEngine()
        self.handwriting = handwriting
        self.trocr_model = trocr_model
        self._reader = None
        self._last_error: Optional[str] = None

    @staticmethod
    def _tesseract_available() -> bool:
        configured = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
        candidates = [configured] if configured else []
        candidates.extend([
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ])
        if shutil.which("tesseract"):
            return True
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return True
        return False

    @staticmethod
    def preprocess(image: np.ndarray) -> np.ndarray:
        if image is None or image.size == 0:
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        denoised = cv2.bilateralFilter(clahe, 9, 50, 50)
        return cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 11)

    def _initialize(self):
        if self._reader is not None:
            return
        if self.engine in ("auto", "paddle"):
            try:
                from paddleocr import PaddleOCR
                self._reader = ("paddle", PaddleOCR(use_angle_cls=True, lang="en", show_log=False))
                return
            except (ImportError, Exception):
                if self.engine == "paddle":
                    raise RuntimeError("PaddleOCR requested but unavailable")
        if self.engine in ("auto", "tesseract"):
            if pytesseract is None:
                if self.engine == "tesseract":
                    raise RuntimeError("pytesseract requested but unavailable")
                self._reader = ("unavailable", None)
                self._last_error = "No OCR backend is available in this environment."
                return
            if not self._tesseract_available():
                if self.engine == "tesseract":
                    raise RuntimeError("Tesseract is not installed or not in PATH. Install Tesseract OCR or set TESSERACT_CMD.")
                self._reader = ("unavailable", None)
                self._last_error = "Tesseract is not installed or not in PATH. OCR output is unavailable."
                return
            self._reader = ("tesseract", pytesseract)
            return
        if self.engine == "trocr":
            if not self.trocr_model:
                raise RuntimeError("Set trocr_model to a locally cached Hugging Face TrOCR model directory")
            try:
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel
                import torch
                processor = TrOCRProcessor.from_pretrained(self.trocr_model, local_files_only=True)
                model = VisionEncoderDecoderModel.from_pretrained(self.trocr_model, local_files_only=True)
                model.eval()
                self._reader = ("trocr", (processor, model, torch))
                return
            except (ImportError, OSError) as exc:
                raise RuntimeError("TrOCR dependencies/model are unavailable offline") from exc
        if self.engine == "auto":
            self._reader = ("unavailable", None)
            self._last_error = "No OCR backend is available in this environment."
            return
        raise RuntimeError("No supported local OCR engine is installed")

    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        self._initialize()
        if self._reader is None or self._reader[0] == "unavailable":
            return "", 0.0
        kind, reader = self._reader
        prepared = self.preprocess(image)
        if kind == "paddle":
            result = reader.ocr(prepared, cls=True) or []
            rows = result[0] if result and result[0] else []
            texts = [str(row[1][0]) for row in rows]
            scores = [float(row[1][1]) for row in rows]
            return "\n".join(texts), float(np.mean(scores)) if scores else 0.0
        if kind == "trocr":
            processor, model, torch = reader
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            inputs = processor(images=rgb, return_tensors="pt").pixel_values
            with torch.inference_mode():
                generated = model.generate(inputs, output_scores=True, return_dict_in_generate=True)
            text = processor.batch_decode(generated.sequences, skip_special_tokens=True)[0].strip()
            scores = generated.scores
            if scores:
                token_conf = [float(torch.softmax(step[0], dim=-1).max().item()) for step in scores]
                confidence = float(np.mean(token_conf))
            else:
                confidence = 0.0
            return text, confidence
        data = reader.image_to_data(prepared, output_type=reader.Output.DICT, config="--psm 6")
        pairs = [(str(t).strip(), float(c) / 100.0) for t, c in zip(data["text"], data["conf"])
                 if str(t).strip() and float(c) >= 0]
        return " ".join(t for t, _ in pairs), float(np.mean([c for _, c in pairs])) if pairs else 0.0

    def _bbox_for_image(self, image: np.ndarray, bbox: Optional[BoundingBox] = None) -> BoundingBox:
        if bbox is not None:
            return bbox
        height, width = image.shape[:2]
        return BoundingBox(page=0, x0=0.0, y0=0.0, x1=float(width), y1=float(height))

    def _extract_image(self, image: np.ndarray, bbox: Optional[BoundingBox] = None,
                       block_id: Optional[str] = None) -> ExtractedBlock:
        if image is None or image.size == 0:
            result = {"text": None, "confidence": 0.0, "is_ambiguous": True,
                      "error_code": ExtractionErrorCode.ERR_EMPTY_REGION, "error_message": "The image region is empty."}
        else:
            text, score = self.recognize(image)
            if not text:
                result = {
                    "text": None,
                    "confidence": 0.0,
                    "is_ambiguous": True,
                    "error_code": ExtractionErrorCode.ERR_DEGRADED_TEXT_LOW_CONFIDENCE,
                    "error_message": self._last_error or "OCR is unavailable in this environment.",
                }
            else:
                result = self.confidence.evaluate_block(image, text, score, self.handwriting)
        resolved_bbox = self._bbox_for_image(image, bbox)
        return ExtractedBlock(id=block_id or __import__("uuid").uuid4(), block_type="text_block", bbox=resolved_bbox,
                              content_raw=result["text"], content_markdown=result["text"], confidence=result["confidence"],
                              is_ambiguous=result["is_ambiguous"], error_code=result["error_code"],
                              error_message=result.get("error_message"))

    def extract_from_pdf(self, pdf_path: Union[str, Path]) -> List[ExtractedBlock]:
        import fitz
        doc = fitz.open(str(pdf_path))
        blocks: List[ExtractedBlock] = []
        try:
            for page_no, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                blocks.append(self._extract_image(image, BoundingBox(
                    page=page_no, x0=0.0, y0=0.0, x1=float(page.rect.width), y1=float(page.rect.height)
                )))
        finally:
            doc.close()
        return blocks

    def extract(self, image_or_path: Union[np.ndarray, str, Path], bbox: Optional[BoundingBox] = None,
                block_id: Optional[str] = None):
        if isinstance(image_or_path, (str, Path)):
            path = Path(image_or_path)
            if path.suffix.lower() == ".pdf":
                return self.extract_from_pdf(path)
            image = cv2.imread(str(path))
            if image is None:
                raise FileNotFoundError(f"Could not load image from '{path}'")
            return self._extract_image(image, bbox=bbox, block_id=block_id)
        if image_or_path is None:
            raise ValueError("Image input is empty")
        return self._extract_image(np.asarray(image_or_path), bbox=bbox, block_id=block_id)
