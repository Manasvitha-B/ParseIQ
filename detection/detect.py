"""File type detection and basic validation (extension is never trusted alone)."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from .schemas import Document, FileType


class DetectionFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message); self.code = code


def detect_file(path: str | Path) -> Document:
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file(): raise DetectionFailure("FILE_NOT_FOUND", f"Not a file: {p}")
    size = p.stat().st_size
    if not size: raise DetectionFailure("EMPTY_FILE", "File is empty")
    ext = p.suffix.lower()
    with p.open("rb") as f: head = f.read(8192)
    kind = None
    if head.startswith(b"%PDF-"): kind = FileType.PDF
    elif head.startswith(b"\x89PNG\r\n\x1a\n"): kind = FileType.PNG
    elif head.startswith(b"\xff\xd8\xff"): kind = FileType.JPG
    elif head.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")): kind = FileType.TIFF
    elif head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(p) as z:
                names = set(z.namelist())
                if "[Content_Types].xml" not in names: raise DetectionFailure("CORRUPT_ARCHIVE", "Invalid OOXML file")
                if any(n.startswith("word/") for n in names): kind = FileType.DOCX
                elif any(n.startswith("xl/") for n in names): kind = FileType.XLSX
                elif any(n.startswith("ppt/") for n in names): kind = FileType.PPTX
                else: raise DetectionFailure("UNSUPPORTED_ARCHIVE", "ZIP is not DOCX, XLSX, or PPTX")
        except zipfile.BadZipFile as e: raise DetectionFailure("CORRUPT_ARCHIVE", "Invalid ZIP/OOXML file") from e
    elif head.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        kind = {".doc": FileType.DOC, ".xls": FileType.XLS, ".ppt": FileType.PPT}.get(ext)
    elif ext in (".txt", ".csv"):
        try: p.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError) as e: raise DetectionFailure("INVALID_TEXT", "TXT/CSV must be readable UTF-8") from e
        kind = FileType.TXT if ext == ".txt" else FileType.CSV
    if kind is None:
        if ext in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"}:
            raise DetectionFailure("SIGNATURE_MISMATCH", f"Contents do not match supported extension {ext}")
        kind = FileType.UNKNOWN
    digest = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): digest.update(chunk)
    return Document(str(p.resolve()), kind, size, digest.hexdigest())
