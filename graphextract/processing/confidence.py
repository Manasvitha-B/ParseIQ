"""Image quality and OCR confidence gating."""
from __future__ import annotations

from typing import Any, Dict, Optional
import cv2
import numpy as np
try:
    from models.document_schema import ExtractionErrorCode
except ModuleNotFoundError:
    from backend.models.document_schema import ExtractionErrorCode


class ConfidenceEngine:
    def __init__(self, blur_threshold: float = 60.0, confidence_threshold: float = 0.65):
        self.blur_threshold = blur_threshold
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def calculate_sharpness(crop: np.ndarray) -> float:
        if crop is None or crop.size == 0:
            return 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def evaluate_block(self, crop: np.ndarray, extracted_text: str, model_confidence: float,
                       handwriting: bool = False) -> Dict[str, Any]:
        sharpness = self.calculate_sharpness(crop)
        score = float(np.clip(model_confidence, 0.0, 1.0))
        code = ExtractionErrorCode.NONE
        message: Optional[str] = None
        ambiguous = False
        text: Optional[str] = (extracted_text or "").strip() or None
        if crop is None or crop.size == 0:
            code, message, ambiguous, text = ExtractionErrorCode.ERR_EMPTY_REGION, "The image region is empty.", True, None
        elif sharpness < self.blur_threshold:
            code, message, ambiguous, text = ExtractionErrorCode.ERR_IMAGE_BLURRY, "Image sharpness is below the reliable threshold.", True, None
        elif score < self.confidence_threshold:
            code = ExtractionErrorCode.ERR_HANDWRITING_ILLEGIBLE if handwriting else ExtractionErrorCode.ERR_DEGRADED_TEXT_LOW_CONFIDENCE
            message = "OCR confidence is below the reliable threshold."
            ambiguous, text = True, None
        elif text is None:
            code, message, ambiguous = ExtractionErrorCode.ERR_EMPTY_REGION, "OCR returned no text.", True
        return {"text": text, "confidence": score, "sharpness": sharpness, "is_ambiguous": ambiguous,
                "error_code": code, "error_message": message}
