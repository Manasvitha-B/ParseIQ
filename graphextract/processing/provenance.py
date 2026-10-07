"""Coordinate helpers for reliable provenance and region masking."""
from __future__ import annotations

from typing import Iterable, Sequence, Tuple

try:
    from models.document_schema import BoundingBox
except ImportError:  # Supports importing this file from a package-aware path.
    from backend.models.document_schema import BoundingBox

Box = Tuple[float, float, float, float]


def normalize_bbox(box: Sequence[float], page_width: float, page_height: float, page: int = 0) -> BoundingBox:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be positive")
    x0, y0, x1, y1 = map(float, box)
    return BoundingBox(page=page, x0=max(0.0, min(1.0, x0 / page_width)),
                       y0=max(0.0, min(1.0, y0 / page_height)),
                       x1=max(0.0, min(1.0, x1 / page_width)),
                       y1=max(0.0, min(1.0, y1 / page_height)), normalized=True).ordered()


def scale_bbox(box: Sequence[float], source_size: Tuple[float, float], target_size: Tuple[float, float]) -> Box:
    sw, sh = source_size
    tw, th = target_size
    if min(sw, sh) <= 0:
        raise ValueError("Source dimensions must be positive")
    x0, y0, x1, y1 = map(float, box)
    return x0 * tw / sw, y0 * th / sh, x1 * tw / sw, y1 * th / sh


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def intersects(a: Sequence[float], b: Sequence[float], threshold: float = 0.0) -> bool:
    return bbox_iou(a, b) > threshold if threshold > 0 else (
        min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]))


def mask_regions(image, boxes: Iterable[Sequence[float]], value: int = 255):
    """Return a copy with boxes painted white, useful before page text OCR."""
    import cv2
    result = image.copy()
    height, width = result.shape[:2]
    for box in boxes:
        x0, y0, x1, y1 = map(int, box)
        cv2.rectangle(result, (max(0, x0), max(0, y0)), (min(width - 1, x1), min(height - 1, y1)), value, -1)
    return result
