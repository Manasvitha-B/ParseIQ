"""
P2B - Semantic Block Processing

Responsibilities:
    - Normalize P2A semantic types
    - Preserve P3 semantic types
    - Detect simple equations when possible
    - Never remove P2A/P3 metadata

Does NOT:
    - perform OCR
    - extract text
    - calculate confidence
    - generate provenance
    - extract tables/charts
"""

import re


SEMANTIC_TYPES = {
    "HEADING",
    "PARAGRAPH",
    "LIST",
    "TABLE",
    "FIGURE",
    "EQUATION",
}


TYPE_MAP = {
    "heading": "HEADING",
    "title": "HEADING",

    "paragraph": "PARAGRAPH",
    "text": "PARAGRAPH",
    "caption": "PARAGRAPH",

    "list": "LIST",
    "list_item": "LIST",
    "bullet": "LIST",

    "table": "TABLE",

    "figure": "FIGURE",
    "image": "FIGURE",
    "chart": "FIGURE",
    "diagram": "FIGURE",

    "equation": "EQUATION",
    "formula": "EQUATION",
    "math": "EQUATION",
}


def normalize_type(value):
    """
    Convert a type from P2A/P3 into the common semantic vocabulary.
    """

    if value is None:
        return None

    value = str(value).strip().lower()

    return TYPE_MAP.get(value)


def get_text(block):
    """
    Support both the current P2A 'text' field and possible
    future 'content' fields.
    """

    value = block.get("text")

    if value is None:
        value = block.get("content")

    if isinstance(value, str):
        return value.strip()

    return ""


def looks_like_equation(text):
    """
    Conservative equation heuristic.

    P3 remains responsible for real equation extraction.
    This only catches obvious mathematical text that P2A
    may have classified as paragraph.
    """

    if not text:
        return False

    strong_symbols = (
        "∑",
        "∫",
        "√",
        "∞",
        "≤",
        "≥",
        "≠",
        "≈",
        "∂",
        "∇",
        "π",
        "∏",
    )

    if any(symbol in text for symbol in strong_symbols):
        return True

    # x = 2 + 3
    # y = mx + c
    # E = mc^2
    simple_equation = re.fullmatch(
        r"""
        \s*
        [A-Za-z]
        \s*=\s*
        [A-Za-z0-9\s+\-*/().^]+
        \s*
        """,
        text,
        re.VERBOSE,
    )

    return simple_equation is not None


def classify_block(block):
    """
    Determine P2B's normalized semantic type.

    Priority:

        P3 explicit type
            ↓
        P2A explicit type
            ↓
        obvious equation
            ↓
        paragraph
    """

    # P3 may explicitly provide a semantic type.
    p3_type = normalize_type(
        block.get("p3_type")
    )

    if p3_type:
        return p3_type

    # Preserve explicit P3 object classification.
    if block.get("source") == "p3":
        explicit = normalize_type(
            block.get("type")
        )

        if explicit:
            return explicit

    # P2A classification.
    original_type = normalize_type(
        block.get("type")
    )

    if original_type:
        return original_type

    # Conservative equation detection.
    text = get_text(block)

    if looks_like_equation(text):
        return "EQUATION"

    return "PARAGRAPH"


def normalize_block(block):
    """
    Create a P2B-compatible block while preserving all
    upstream fields.

    No confidence or provenance is recalculated.
    """

    normalized = dict(block)

    semantic_type = classify_block(
        normalized
    )

    normalized["semantic_type"] = semantic_type

    # Keep the original 'type' because P1/P3 may depend on it.
    # Add normalized semantic_type separately.

    return normalized


def normalize_blocks(blocks):
    """
    Normalize a list of blocks.
    """

    return [
        normalize_block(block)
        for block in blocks
        if isinstance(block, dict)
    ]