"""Page and region analysis. It emits locations/types, never extracted content."""
from __future__ import annotations
from typing import Protocol
from .schemas import Document, FileType, Page, Region, RegionType, Box

class Analyzer(Protocol):
    def analyze(self, document: Document, page: Page) -> list[Region]: ...

class RegionAnalyzer:
    """Conservative geometric/structure heuristics; plug in a layout model for finer analysis."""
    def analyze(self, document: Document, page: Page) -> list[Region]:
        kind=document.file_type
        if kind in (FileType.PDF,FileType.SCANNED_PDF): return self._pdf(page)
        if kind==FileType.TXT:
            return [Region(page.source,page.number,f"p{page.number}-text",RegionType.DIGITAL_TEXT,
                metadata={"text_source":page.metadata.get("text_source")})]
        if kind==FileType.CSV:
            return [Region(page.source,page.number,"csv-table-1",RegionType.TABLE,confidence=1.0,
                metadata={"row_count":page.metadata.get("row_count"),"column_count":page.metadata.get("column_count")})]
        if kind==FileType.DOCX: return self._docx(page)
        if kind==FileType.XLSX:
            return [Region(page.source,page.number,f"sheet-{page.number}-table",RegionType.TABLE,
                metadata={"sheet_name":page.metadata.get("name"),"merged_ranges":page.metadata.get("merged_ranges",[]),
                          "row_count":page.metadata.get("max_row"),"column_count":page.metadata.get("max_column")})]
        if kind==FileType.PPTX: return self._pptx(page)
        return [Region(page.source,page.number,f"frame-{page.number}-mixed",RegionType.MIXED_IMAGE,
            metadata={"classification_required":True,"image_path":page.metadata.get("image_path"),
                      "frame_index":page.metadata.get("frame_index")})]

    def _pdf(self,page):
        data=page.payload or {}; blocks=data.get("text_blocks",[]); regions=[]
        if page.metadata.get("pdf_type")=="scanned":
            return [Region(page.source,page.number,f"p{page.number}-scan",RegionType.SCANNED_TEXT,
                metadata={"route_hint":"ocr","classification_status":"page_detected_as_scanned"})]
        for i,b in enumerate(blocks):
            x0,y0,x1,y1=b.get("bbox",(0,0,0,0))
            font_size=b.get("font_size_min",99)
            if page.height and y0<page.height*.08: typ=RegionType.HEADER
            elif page.height and y1>page.height*.92 and font_size<9: typ=RegionType.FOOTNOTE
            elif page.height and y1>page.height*.92: typ=RegionType.FOOTER
            elif page.width and (x0<page.width*.08 or x1>page.width*.92) and x1-x0<page.width*.28: typ=RegionType.SIDEBAR
            else: typ=RegionType.DIGITAL_TEXT
            regions.append(Region(page.source,page.number,f"p{page.number}-text-{i+1}",typ,
                Box(float(x0),float(y0),float(x1),float(y1)),i,.8,
                {"font_size_min":font_size,"font_names":b.get("font_names",[])}))
        if not blocks and data.get("has_text"):
            regions.append(Region(page.source,page.number,f"p{page.number}-text-1",RegionType.DIGITAL_TEXT,
                Box(0,0,float(page.width or 0),float(page.height or 0)),0,.65,
                {"layout_resolution":"page_level_fallback"}))
        # Candidate table regions are geometry-only. No cells or values are extracted here.
        pdf_page=data.get("page")
        if pdf_page is not None and hasattr(pdf_page,"find_tables"):
            try:
                for i,table in enumerate(pdf_page.find_tables()):
                    x0,y0,x1,y1=map(float,table.bbox)
                    regions.append(Region(page.source,page.number,f"p{page.number}-table-{i+1}",RegionType.TABLE,
                        Box(x0,y0,x1,y1),len(regions)+i,.6,metadata={"detector":"pdf_table_geometry",
                        "at_page_bottom":bool(page.height and y1>page.height*.86),
                        "at_page_top":bool(page.height and y0<page.height*.14)}))
            except Exception: pass
        # Heuristic two-column layout classification based only on text-block boxes.
        text=[r for r in regions if r.region_type==RegionType.DIGITAL_TEXT and r.box]
        if len(text)>=4 and page.width:
            left=[r for r in text if r.box.x0<page.width*.48]; right=[r for r in text if r.box.x0>=page.width*.48]
            if len(left)>=2 and len(right)>=2 and min(r.box.x0 for r in right)-max(r.box.x1 for r in left)>page.width*.04:
                ordered=sorted(left,key=lambda r:(r.box.y0,r.box.x0))+sorted(right,key=lambda r:(r.box.y0,r.box.x0))
                for order,r in enumerate(ordered):
                    r.region_type=RegionType.MULTI_COLUMN_TEXT; r.reading_order=order
                    r.metadata.update({"column":0 if r in left else 1,"layout":"two_column_heuristic"})
        # Image rectangles are kept as classifier candidates for figure/chart/diagram/OCR routing.
        if pdf_page is not None and hasattr(pdf_page,"get_images"):
            order=len(regions)
            for ix,img in enumerate(pdf_page.get_images(full=True)):
                for j,rect in enumerate(pdf_page.get_image_rects(img[0])):
                    regions.append(Region(page.source,page.number,f"p{page.number}-image-{ix+1}-{j+1}",RegionType.MIXED_IMAGE,
                        Box(rect.x0,rect.y0,rect.x1,rect.y1),order,metadata={"classification_required":True,"xref":img[0]})); order+=1
        elif page.metadata.get("image_count"):
            regions.append(Region(page.source,page.number,f"p{page.number}-images",RegionType.MIXED_IMAGE,
                metadata={"classification_required":True,"image_count":page.metadata["image_count"]}))
        return regions

    def _docx(self,page):
        doc=page.payload; out=[]
        for i,para in enumerate(doc.paragraphs):
            style=para.style.name if para.style else ""
            try: is_list=para._p.pPr is not None and para._p.pPr.numPr is not None
            except AttributeError: is_list=False
            # Do not put paragraph content into a region; this module only marks its type.
            out.append(Region(page.source,page.number,f"docx-p{i+1}",RegionType.DIGITAL_TEXT,
                reading_order=i,metadata={"paragraph_index":i,"style":style,"is_list":is_list,"has_content":bool(para.text.strip())}))
        for i,table in enumerate(doc.tables):
            out.append(Region(page.source,page.number,f"docx-table-{i+1}",RegionType.TABLE,reading_order=len(out),
                metadata={"table_index":i,"row_count":len(table.rows),"column_count":len(table.columns)}))
        if getattr(doc,"inline_shapes",None):
            for i,shape in enumerate(doc.inline_shapes):
                out.append(Region(page.source,page.number,f"docx-image-{i+1}",RegionType.MIXED_IMAGE,reading_order=len(out),
                    metadata={"classification_required":True,"width_emu":shape.width,"height_emu":shape.height}))
        for section_i,section in enumerate(doc.sections):
            if any(p.text.strip() for p in section.header.paragraphs):
                out.append(Region(page.source,page.number,f"docx-header-{section_i+1}",RegionType.HEADER,reading_order=-2))
            if any(p.text.strip() for p in section.footer.paragraphs):
                out.append(Region(page.source,page.number,f"docx-footer-{section_i+1}",RegionType.FOOTER,reading_order=999999))
        return out

    def _pptx(self,page):
        out=[]
        for i,shape in enumerate(page.payload.shapes):
            if getattr(shape,"has_table",False): typ=RegionType.TABLE
            elif getattr(shape,"has_chart",False): typ=RegionType.CHART
            elif getattr(shape,"has_text_frame",False): typ=RegionType.DIGITAL_TEXT
            else: typ=RegionType.MIXED_IMAGE
            box=Box(shape.left/914400,shape.top/914400,(shape.left+shape.width)/914400,(shape.top+shape.height)/914400)
            meta={"shape_index":i,"shape_name":shape.name,"shape_type":str(shape.shape_type),
                  "classification_required":typ==RegionType.MIXED_IMAGE}
            if typ==RegionType.TABLE: meta.update({"row_count":len(shape.table.rows),"column_count":len(shape.table.columns)})
            out.append(Region(page.source,page.number,f"slide-{page.number}-shape-{i+1}",typ,box,i,metadata=meta))
        return out
