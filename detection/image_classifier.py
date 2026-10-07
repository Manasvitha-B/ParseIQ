"""Image-content classifier contract and routing labels.

Person 1 owns orchestration of classification. Model/OCR/image understanding internals
belong in the injected backend. Without one, image regions remain MIXED_IMAGE safely.
"""
from __future__ import annotations

from typing import Protocol
from .schemas import Page, Region, RegionType


class ImageBackend(Protocol):
    def classify(self, page: Page, region: Region) -> list[tuple[RegionType, float, dict]]: ...


IMAGE_LABELS = {
    "text": RegionType.SCANNED_TEXT, "photo": RegionType.PHOTO,
    "chart": RegionType.CHART, "diagram": RegionType.DIAGRAM,
    "screenshot": RegionType.SCREENSHOT, "equation": RegionType.EQUATION,
    "table": RegionType.TABLE, "figure": RegionType.FIGURE,
}


class ImageClassifier:
    def __init__(self, backend: ImageBackend | None = None): self.backend = backend

    def classify(self, page: Page, region: Region) -> list[Region]:
        if self.backend is None:
            region.metadata["classification_status"] = "backend_not_configured"
            return [region]
        predictions = self.backend.classify(page, region)
        if not predictions:
            region.metadata["classification_status"] = "no_prediction"
            return [region]
        # A mixed visual can be split into multiple typed regions by the backend.
        output = []
        for i, (label, confidence, metadata) in enumerate(predictions, 1):
            if label not in set(IMAGE_LABELS.values()):
                raise ValueError(f"Invalid image classification: {label}")
            output.append(Region(region.source, region.page_number,
                f"{region.region_id}-{i}", label, region.box, region.reading_order+i-1,
                confidence, {**region.metadata, **metadata, "parent_region_id": region.region_id}))
        return output
