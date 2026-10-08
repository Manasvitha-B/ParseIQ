"""Enums and the standard metadata/provenance format shared by every module."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FileType(str, Enum):
    PDF = "pdf"; SCANNED_PDF = "scanned_pdf"
    PNG = "png"; JPG = "jpg"; TIFF = "tiff"; WEBP = "webp"
    DOC = "doc"; DOCX = "docx"; TXT = "txt"
    XLS = "xls"; XLSX = "xlsx"; CSV = "csv"
    PPT = "ppt"; PPTX = "pptx"; UNKNOWN = "unknown"


class RegionType(str, Enum):
    DIGITAL_TEXT = "digital_text"; SCANNED_TEXT = "scanned_text"
    TABLE = "table"; CHART = "chart"; DIAGRAM = "diagram"; FIGURE = "figure"
    EQUATION = "equation"; SCREENSHOT = "screenshot"; PHOTO = "photo"
    HEADER = "header"; FOOTER = "footer"; FOOTNOTE = "footnote"
    SIDEBAR = "sidebar"; MULTI_COLUMN_TEXT = "multi_column_text"
    MIXED_IMAGE = "mixed_image"; UNKNOWN = "unknown"


@dataclass(frozen=True)
class Box:
    x0: float; y0: float; x1: float; y1: float
    coordinate_space: str = "page_top_left"
    def __post_init__(self):
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("box end coordinates must be >= start coordinates")


@dataclass
class Document:
    source: str
    file_type: FileType
    size_bytes: int
    sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    source: str
    number: int
    unit_type: str = "page"  # page / slide / sheet / frame / flow
    width: float | None = None
    height: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: Any = field(default=None, repr=False, compare=False)


@dataclass
class Region:
    source: str
    page_number: int
    region_id: str
    region_type: RegionType
    box: Box | None = None
    reading_order: int = 0
    confidence: float | None = None
    text_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    def __post_init__(self):
        if self.page_number < 1: raise ValueError("page_number is one-based")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")


@dataclass
class Block:
    """THE standard extractor block. Every extractor returns this schema."""
    block_id: str
    block_type: str
    content: Any
    source: str
    page_number: int
    region_id: str | None = None
    box: Box | None = None
    reading_order: int = 0
    confidence: float | None = None
    extractor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    def __post_init__(self):
        if self.page_number < 1: raise ValueError("page_number is one-based")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")


@dataclass
class ParseError:
    code: str
    message: str
    source: str | None = None
    page_number: int | None = None
    region_id: str | None = None
    component: str | None = None
    recoverable: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    document: Document | None
    pages: list[Page] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    status: str = "ok"
    assembler_result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
