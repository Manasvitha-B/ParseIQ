"""Central route table and per-region fallback/failure isolation."""
from __future__ import annotations

from typing import Iterable, Protocol
from .schemas import Block, Document, ParseError, Region, RegionType


class Extractor(Protocol):
    name: str
    def extract(self, document: Document, page, region: Region) -> Iterable[Block]: ...


ROUTES = {
    RegionType.DIGITAL_TEXT: "text", RegionType.SCANNED_TEXT: "ocr",
    RegionType.TABLE: "table", RegionType.CHART: "chart", RegionType.DIAGRAM: "diagram",
    RegionType.FIGURE: "figure", RegionType.PHOTO: "figure", RegionType.SCREENSHOT: "figure",
    RegionType.EQUATION: "equation", RegionType.HEADER: "layout", RegionType.FOOTER: "layout",
    RegionType.FOOTNOTE: "layout", RegionType.SIDEBAR: "layout", RegionType.MULTI_COLUMN_TEXT: "layout",
}


class Router:
    def __init__(self, extractors: dict[str, Extractor] | None = None): self.extractors = dict(extractors or {})
    def register(self, route: str, extractor: Extractor, replace: bool = False):
        if route in self.extractors and not replace: raise ValueError(f"Extractor already registered: {route}")
        if not callable(getattr(extractor, "extract", None)): raise TypeError("extractor must implement extract(document, page, region)")
        self.extractors[route] = extractor
    def route(self, document: Document, page, region: Region) -> tuple[list[Block], list[ParseError]]:
        route = ROUTES.get(region.region_type)
        if region.region_type == RegionType.MIXED_IMAGE:
            return [], [ParseError("CLASSIFICATION_REQUIRED", "Mixed image must be classified/split before extraction",
                document.source, region.page_number, region.region_id, "image_classifier", True)]
        if route is None:
            return [], [ParseError("NO_ROUTE", f"No route for region type {region.region_type.value}",
                document.source, region.page_number, region.region_id, "router", True)]
        extractor = self.extractors.get(route)
        if extractor is None:
            # Semantic digital text may be handled by layout module as a fallback.
            fallback = "layout" if route == "text" else None
            extractor = self.extractors.get(fallback) if fallback else None
            if extractor is None:
                return [], [ParseError("EXTRACTOR_UNAVAILABLE", f"No extractor registered for '{route}'",
                    document.source, region.page_number, region.region_id, route, True)]
        try:
            blocks = list(extractor.extract(document, page, region))
            for block in blocks:
                if not isinstance(block, Block): raise TypeError("Extractor output must use schemas.Block")
                block.source = block.source or region.source
                block.region_id = block.region_id or region.region_id
                block.box = block.box or region.box
                if block.confidence is None: block.confidence = region.confidence
                block.extractor = block.extractor or getattr(extractor, "name", route)
                if block.confidence is None and "confidence_unavailable" not in block.flags: block.flags.append("confidence_unavailable")
            return blocks, []
        except Exception as exc:
            marker=str(exc).split(":",1)[0]
            code="TIMEOUT" if isinstance(exc,TimeoutError) else marker if marker.isupper() and len(marker)<50 else "EXTRACTOR_FAILURE"
            return [], [ParseError(code, str(exc), document.source, region.page_number,
                region.region_id, route, True, {"exception_type": type(exc).__name__})]
