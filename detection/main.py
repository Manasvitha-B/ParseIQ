"""CLI smoke path with deliberately non-extracting module stubs."""
from __future__ import annotations
import argparse
from .orchestrator import Orchestrator
from .router import Router
from .schemas import Block

class StubExtractor:
    """Confirms route wiring only; it does not read or interpret source content."""
    def __init__(self,name): self.name=name
    def extract(self,document,page,region):
        yield Block(f"{region.region_id}-stub",region.region_type.value,
            {"stub":True,"message":"Replace with the specialist extractor"},document.source,
            region.page_number,region.region_id,region.box,region.reading_order,
            region.confidence,self.name,{"integration_stub":True})

def make_demo_router():
    router=Router()
    for name in ("text","ocr","table","chart","diagram","figure","equation","layout"):
        router.register(name,StubExtractor(name))
    return router

def main(argv=None):
    parser=argparse.ArgumentParser(description="Person 1 document parser/orchestrator wiring")
    parser.add_argument("file",help="Source document or image")
    parser.add_argument("--no-stubs",action="store_true",help="Run without demo extractor adapters")
    args=parser.parse_args(argv)
    result=Orchestrator(router=None if args.no_stubs else make_demo_router()).parse(args.file)
    print(f"status={result.status} file_type={result.document.file_type.value if result.document else 'unknown'} "
          f"pages={len(result.pages)} regions={len(result.regions)} blocks={len(result.blocks)} errors={len(result.errors)}")
    for error in result.errors:
        print(f"{error.code}: {error.message} (page={error.page_number}, region={error.region_id})")
    return 0 if result.status=="ok" else 1

if __name__=="__main__": raise SystemExit(main())
