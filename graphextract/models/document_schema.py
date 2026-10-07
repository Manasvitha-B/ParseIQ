"""Shared extraction models for ParseAnything."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExtractionErrorCode(str, Enum):
    NONE = "NONE"
    ERR_DEGRADED_TEXT_LOW_CONFIDENCE = "ERR_DEGRADED_TEXT_LOW_CONFIDENCE"
    ERR_HANDWRITING_ILLEGIBLE = "ERR_HANDWRITING_ILLEGIBLE"
    ERR_IMAGE_BLURRY = "ERR_IMAGE_BLURRY"
    ERR_EMPTY_REGION = "ERR_EMPTY_REGION"


class BoundingBox(BaseModel):
    """Page-space rectangle in PDF points, with optional normalized coordinates."""
    page: int = Field(ge=0)
    x0: float
    y0: float
    x1: float
    y1: float
    normalized: bool = False

    def ordered(self) -> "BoundingBox":
        return BoundingBox(page=self.page, x0=min(self.x0, self.x1), y0=min(self.y0, self.y1),
                          x1=max(self.x0, self.x1), y1=max(self.y0, self.y1), normalized=self.normalized)


class TableCell(BaseModel):
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    bbox: Optional[BoundingBox] = None
    text: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_ambiguous: bool = False
    error_code: ExtractionErrorCode = ExtractionErrorCode.NONE


class TableData(BaseModel):
    cells: List[List[TableCell]] = Field(default_factory=list)
    matrix: List[List[Optional[str]]] = Field(default_factory=list)
    markdown: Optional[str] = None


class ExtractedBlock(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    block_type: Literal["table", "figure", "chart", "text_block"]
    bbox: BoundingBox
    content_raw: Optional[str] = None
    content_markdown: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_ambiguous: bool = False
    error_code: ExtractionErrorCode = ExtractionErrorCode.NONE
    error_message: Optional[str] = None
