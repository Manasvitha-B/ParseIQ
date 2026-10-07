"""End-to-end pipeline coordinator and final assembler hand-off."""
from __future__ import annotations

import time
from typing import Protocol, Sequence, Any
from .analyzer import Analyzer, RegionAnalyzer
from .detect import detect_file, DetectionFailure
from .image_classifier import ImageClassifier
from .loaders import load_pages, LoaderFailure
from .router import Router
from .schemas import Block, Document, Page, ParseError, ParseResult, Region, RegionType, FileType


class Assembler(Protocol):
    def assemble(self, document: Document, pages: Sequence[Page], regions: Sequence[Region],
                 blocks: Sequence[Block], errors: Sequence[ParseError]) -> Any: ...


class Orchestrator:
    def __init__(self, router: Router | None = None, analyzer: Analyzer | None = None,
                 image_classifier: ImageClassifier | None = None, assembler: Assembler | None = None,
                 *, max_file_bytes: int | None = None, max_pages: int | None = None,
                 low_confidence_threshold: float = .6, timeout_seconds: float | None = None):
        self.router = router or Router(); self.analyzer = analyzer or RegionAnalyzer()
        self.image_classifier = image_classifier or ImageClassifier(); self.assembler = assembler
        self.max_file_bytes=max_file_bytes; self.max_pages=max_pages; self.low_confidence_threshold=low_confidence_threshold
        self.timeout_seconds=timeout_seconds

    def parse(self, path: str) -> ParseResult:
        started=time.monotonic()
        try: document = detect_file(path)
        except DetectionFailure as e:
            result=ParseResult(None,errors=[ParseError(e.code,str(e),str(path),component="detect",recoverable=False)],status="failed")
            if self.assembler: result.assembler_result=self.assembler.assemble(None,[],[],[],result.errors)
            return result
        if self.max_file_bytes is not None and document.size_bytes>self.max_file_bytes:
            result=ParseResult(document,errors=[ParseError("FILE_SIZE_LIMIT",f"File exceeds {self.max_file_bytes} byte limit",document.source,
                component="orchestrator",recoverable=False)],status="failed")
            if self.assembler: result.assembler_result=self.assembler.assemble(document,[],[],[],result.errors)
            return result
        if document.file_type == FileType.UNKNOWN:
            result=ParseResult(document,errors=[ParseError("UNSUPPORTED_FORMAT","Unsupported input format",document.source,
                component="detect",recoverable=False)],status="failed")
            if self.assembler: result.assembler_result=self.assembler.assemble(document,[],[],[],result.errors)
            return result
        try: pages = load_pages(document)
        except LoaderFailure as e:
            result=ParseResult(document,errors=[ParseError(e.code,str(e),document.source,component="loader",recoverable=False)],status="failed")
            if self.assembler: result.assembler_result=self.assembler.assemble(document,[],[],[],result.errors)
            return result
        if self.max_pages is not None and len(pages)>self.max_pages:
            result=ParseResult(document,pages=pages[:self.max_pages],errors=[ParseError("PAGE_LIMIT",
                f"Document has {len(pages)} units; configured limit is {self.max_pages}",document.source,
                component="orchestrator",recoverable=False)],status="failed")
            if self.assembler: result.assembler_result=self.assembler.assemble(document,result.pages,[],[],result.errors)
            return result
        if document.file_type == FileType.PDF and pages:
            nonempty=[p.metadata.get("pdf_type") for p in pages if p.metadata.get("pdf_type")!="empty"]
            if nonempty and all(kind=="scanned" for kind in nonempty): document.file_type=FileType.SCANNED_PDF
        result = ParseResult(document, pages=pages)
        for page in pages:
            if self.timeout_seconds is not None and time.monotonic()-started>=self.timeout_seconds:
                result.errors.append(ParseError("TIMEOUT","Document processing deadline exceeded between pages",document.source,
                    page.number,component="orchestrator",recoverable=True,details={"elapsed_seconds":time.monotonic()-started}))
                break
            try: candidates = self.analyzer.analyze(document, page)
            except Exception as e:
                result.errors.append(ParseError("ANALYZER_FAILURE", str(e), document.source, page.number, component="analyzer")); continue
            if not candidates and page.metadata.get("pdf_type")!="empty":
                result.errors.append(ParseError("UNPARSEABLE_PAGE","No regions were detected on this page",document.source,
                    page.number,component="analyzer",recoverable=True))
            for region in candidates:
                if self.timeout_seconds is not None and time.monotonic()-started>=self.timeout_seconds:
                    result.errors.append(ParseError("TIMEOUT","Document processing deadline exceeded between regions",document.source,
                        page.number,region.region_id,"orchestrator",True,{"elapsed_seconds":time.monotonic()-started}))
                    break
                if region.region_type == RegionType.MIXED_IMAGE:
                    try: resolved = self.image_classifier.classify(page, region)
                    except Exception as e:
                        result.errors.append(ParseError("CLASSIFIER_FAILURE", str(e), document.source, page.number,
                            region.region_id, "image_classifier")); resolved = [region]
                else: resolved = [region]
                for typed_region in resolved:
                    result.regions.append(typed_region)
                    blocks, errors = self.router.route(document, page, typed_region)
                    for block in blocks:
                        block.metadata.setdefault("source_unit", {"unit_type":page.unit_type,**page.metadata})
                        block.metadata.setdefault("source_filename", document.source.rsplit("/",1)[-1])
                        if block.confidence is not None and block.confidence < self.low_confidence_threshold and "low_confidence" not in block.flags:
                            block.flags.append("low_confidence")
                    result.blocks.extend(blocks); result.errors.extend(errors)
                    if self.timeout_seconds is not None and time.monotonic()-started>=self.timeout_seconds:
                        result.errors.append(ParseError("TIMEOUT","Region processing exceeded document deadline",document.source,
                            page.number,typed_region.region_id,"orchestrator",True,{"elapsed_seconds":time.monotonic()-started}))
                        break
        result.blocks.sort(key=lambda b: (b.page_number, b.reading_order, b.block_id))
        if self.assembler:
            try: result.assembler_result = self.assembler.assemble(document, pages, result.regions, result.blocks, result.errors)
            except Exception as e: result.errors.append(ParseError("ASSEMBLER_FAILURE", str(e), document.source, component="assembler"))
        else:
            result.errors.append(ParseError("ASSEMBLER_NOT_REGISTERED",
                "Collected blocks are available on ParseResult.blocks; connect the final assembler module",
                document.source,component="assembler",recoverable=True))
        result.status = "partial" if result.errors else "ok"
        return result


def parse(path: str, **kwargs) -> ParseResult:
    return Orchestrator(**kwargs).parse(path)
