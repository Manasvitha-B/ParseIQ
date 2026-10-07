"""
P2B - Layout and Reading Order Reconstruction

Input sources:
    1. P2A extracted text elements
    2. Optional P1 routing/layout hints
    3. Optional P3 table/chart/equation objects

Output:
    Same document structure with P2B metadata added.

P2B DOES NOT:
    - perform OCR
    - extract text
    - extract tables
    - extract charts
    - calculate confidence
    - generate provenance
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .semantic_blocks import normalize_blocks


# ============================================================
# Constants
# ============================================================

REGIONS = {
    "HEADER",
    "MAIN",
    "SIDEBAR",
    "FOOTNOTE",
    "FOOTER",
}

MIN_COLUMN_GAP_RATIO = 0.10
MAX_COLUMNS = 4

HEADER_TOP_RATIO = 0.12
FOOTER_BOTTOM_RATIO = 0.92
FOOTNOTE_TOP_RATIO = 0.76

SIDEBAR_MAX_WIDTH_RATIO = 0.30
SIDEBAR_EDGE_RATIO = 0.08


# ============================================================
# Geometry
# ============================================================

def bbox(block: Dict[str, Any]) -> List[float]:
    value = block.get("bbox")

    if (
        isinstance(value, (list, tuple))
        and len(value) >= 4
    ):
        try:
            return [
                float(value[0]),
                float(value[1]),
                float(value[2]),
                float(value[3]),
            ]
        except (TypeError, ValueError):
            pass

    return [0.0, 0.0, 0.0, 0.0]


def x0(block):
    return bbox(block)[0]


def y0(block):
    return bbox(block)[1]


def x1(block):
    return bbox(block)[2]


def y1(block):
    return bbox(block)[3]


def width(block):
    return max(
        0.0,
        x1(block) - x0(block)
    )


def height(block):
    return max(
        0.0,
        y1(block) - y0(block)
    )


def center_x(block):
    return (x0(block) + x1(block)) / 2.0


def center_y(block):
    return (y0(block) + y1(block)) / 2.0


def area(block):
    return width(block) * height(block)


def vertical_overlap(a, b):
    top = max(y0(a), y0(b))
    bottom = min(y1(a), y1(b))

    overlap = max(
        0.0,
        bottom - top
    )

    denominator = max(
        1.0,
        min(height(a), height(b))
    )

    return overlap / denominator


def horizontal_overlap(a, b):
    left = max(x0(a), x0(b))
    right = min(x1(a), x1(b))

    overlap = max(
        0.0,
        right - left
    )

    denominator = max(
        1.0,
        min(width(a), width(b))
    )

    return overlap / denominator


# ============================================================
# P1 hints
# ============================================================

def apply_p1_hints(
    block: Dict[str, Any],
    p1_hints: Optional[Dict[str, Any]],
):
    """
    Apply explicit routing/layout information from P1
    when available.

    We do not require P1 to have a particular schema.
    """

    if not isinstance(p1_hints, dict):
        return block

    block_id = block.get(
        "id",
        block.get("element_id")
    )

    # Direct block mapping.
    block_hints = p1_hints.get(
        "blocks",
        {}
    )

    if isinstance(block_hints, dict) and block_id:
        hint = block_hints.get(
            block_id
        )

        if isinstance(hint, dict):
            for key in (
                "region",
                "layout_role",
                "column",
            ):
                if key in hint:
                    block[key] = hint[key]

    return block


# ============================================================
# P3 integration
# ============================================================

def extract_p3_blocks(
    p3_page: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert P3 page output into layout blocks.

    This function does NOT interpret table/chart/equation content.
    It only needs their bbox/type so P2B can place them in the
    reading order.

    Supports:
        elements
        blocks
        objects
    """

    if not isinstance(p3_page, dict):
        return []

    raw_objects = (
        p3_page.get("elements")
        or p3_page.get("blocks")
        or p3_page.get("objects")
        or []
    )

    if not isinstance(raw_objects, list):
        return []

    result = []

    for index, obj in enumerate(
        raw_objects
    ):

        if not isinstance(obj, dict):
            continue

        new_block = dict(obj)

        # Mark origin without destroying P3's fields.
        new_block["source"] = (
            new_block.get(
                "source",
                "p3"
            )
        )

        new_block["p3_type"] = (
            new_block.get("type")
        )

        # Ensure semantic type is known.
        if not new_block.get("type"):
            new_block["type"] = (
                new_block.get(
                    "semantic_type",
                    "figure"
                )
            )

        new_block.setdefault(
            "_p3_index",
            index
        )

        result.append(
            new_block
        )

    return result


# ============================================================
# Duplicate handling
# ============================================================

def same_bbox(a, b, tolerance=2.0):
    """
    Check whether two blocks occupy essentially the same bbox.
    """

    ba = bbox(a)
    bb = bbox(b)

    return all(
        abs(ba[i] - bb[i]) <= tolerance
        for i in range(4)
    )


def is_duplicate_p3_block(
    p3_block,
    p2a_blocks
):
    """
    Prevent a P3 visual object from being inserted twice
    if it already corresponds to an upstream block.
    """

    for text_block in p2a_blocks:

        if same_bbox(
            p3_block,
            text_block
        ):
            return True

    return False


# ============================================================
# Header detection
# ============================================================

def detect_headers(
    blocks,
    page_height
):
    """
    Detect page-level headers.

    Strong signals:
        - explicit P1 region
        - explicit layout_role
        - position near top
    """

    headers = []

    for block in blocks:

        explicit_region = str(
            block.get(
                "region",
                ""
            )
        ).upper()

        role = str(
            block.get(
                "layout_role",
                ""
            )
        ).upper()

        if explicit_region == "HEADER":
            headers.append(block)
            continue

        if role == "HEADER":
            headers.append(block)
            continue

        if y0(block) <= (
            page_height
            * HEADER_TOP_RATIO
        ):
            headers.append(block)

    return headers


# ============================================================
# Footer detection
# ============================================================

def detect_footers(
    blocks,
    page_height
):
    """
    Detect page-level footers.
    """

    footers = []

    for block in blocks:

        explicit_region = str(
            block.get(
                "region",
                ""
            )
        ).upper()

        role = str(
            block.get(
                "layout_role",
                ""
            )
        ).upper()

        if explicit_region == "FOOTER":
            footers.append(block)
            continue

        if role == "FOOTER":
            footers.append(block)
            continue

        if y0(block) >= (
            page_height
            * FOOTER_BOTTOM_RATIO
        ):
            footers.append(block)

    return footers


# ============================================================
# Footnote detection
# ============================================================

def looks_like_footnote_marker(text):
    """
    Detect common footnote notation.
    """

    if not text:
        return False

    stripped = text.strip()

    prefixes = (
        "[1]",
        "[2]",
        "[3]",
        "[4]",
        "[5]",
        "[6]",
        "[7]",
        "[8]",
        "[9]",
        "(1)",
        "(2)",
        "(3)",
        "1.",
        "2.",
        "3.",
        "4.",
        "5.",
        "* ",
        "†",
        "‡",
    )

    return stripped.startswith(prefixes)


def detect_footnotes(
    blocks,
    page_height
):
    """
    Detect likely footnotes.

    Footnotes occupy the lower page area but are
    above the footer.
    """

    footnotes = []

    lower_zone = (
        page_height
        * FOOTNOTE_TOP_RATIO
    )

    footer_zone = (
        page_height
        * FOOTER_BOTTOM_RATIO
    )

    for block in blocks:

        explicit_region = str(
            block.get(
                "region",
                ""
            )
        ).upper()

        role = str(
            block.get(
                "layout_role",
                ""
            )
        ).upper()

        text = str(
            block.get(
                "text",
                block.get(
                    "content",
                    ""
                )
            )
        )

        if explicit_region == "FOOTNOTE":
            footnotes.append(block)
            continue

        if role == "FOOTNOTE":
            footnotes.append(block)
            continue

        if (
            y0(block) >= lower_zone
            and y1(block) < footer_zone
        ):
            footnotes.append(block)
            continue

        if looks_like_footnote_marker(
            text
        ):
            footnotes.append(block)

    return footnotes


# ============================================================
# Sidebar detection
# ============================================================

def detect_sidebars(
    blocks,
    page_width,
    page_height
):
    """
    Detect narrow blocks at page edges.

    Important:
    We don't classify every narrow block as a sidebar.
    Explicit P1/P2B hints always take priority.
    """

    sidebars = []

    for block in blocks:

        explicit_region = str(
            block.get(
                "region",
                ""
            )
        ).upper()

        role = str(
            block.get(
                "layout_role",
                ""
            )
        ).upper()

        if explicit_region == "SIDEBAR":
            sidebars.append(block)
            continue

        if role == "SIDEBAR":
            sidebars.append(block)
            continue

        if page_width <= 0:
            continue

        width_ratio = (
            width(block)
            / page_width
        )

        if width_ratio > (
            SIDEBAR_MAX_WIDTH_RATIO
        ):
            continue

        left_ratio = (
            x0(block)
            / page_width
        )

        right_ratio = (
            x1(block)
            / page_width
        )

        near_left = (
            left_ratio
            <= SIDEBAR_EDGE_RATIO
        )

        near_right = (
            right_ratio
            >= 1.0 - SIDEBAR_EDGE_RATIO
        )

        if near_left or near_right:
            sidebars.append(block)

    return sidebars


# ============================================================
# Column detection
# ============================================================

def find_column_splits(
    blocks,
    page_width
):
    """
    Find meaningful horizontal gaps between blocks.

    Returns x-coordinate split positions.

    This is more robust than simply splitting at page_width / 2.
    """

    if (
        page_width <= 0
        or len(blocks) < 2
    ):
        return []

    intervals = []

    for block in blocks:

        intervals.append(
            (
                x0(block),
                x1(block)
            )
        )

    # Candidate gaps are produced from the
    # right edge of one block to the left
    # edge of another.
    candidate_gaps = []

    for i, first in enumerate(
        intervals
    ):

        for j, second in enumerate(
            intervals
        ):

            if i == j:
                continue

            left = min(
                first[1],
                second[1]
            )

            right = max(
                first[0],
                second[0]
            )

            if right <= left:
                continue

            gap = right - left

            if gap >= (
                page_width
                * MIN_COLUMN_GAP_RATIO
            ):
                candidate_gaps.append(
                    (
                        gap,
                        (left + right) / 2.0
                    )
                )

    if not candidate_gaps:
        return []

    # Largest gaps are strongest column separators.
    candidate_gaps.sort(
        reverse=True
    )

    splits = []

    for gap, split in candidate_gaps:

        if any(
            abs(split - existing)
            < page_width * 0.05
            for existing in splits
        ):
            continue

        splits.append(split)

        if len(splits) >= (
            MAX_COLUMNS - 1
        ):
            break

    return sorted(splits)


def assign_columns(
    blocks,
    page_width
):
    """
    Assign each main block to a column.
    """

    if not blocks:
        return blocks, 1

    splits = find_column_splits(
        blocks,
        page_width
    )

    boundaries = [
        0.0,
        *splits,
        float(page_width)
    ]

    column_count = (
        len(boundaries) - 1
    )

    for block in blocks:

        # Explicit P1/P2B column takes priority.
        if "column" in block:

            try:
                block["column"] = int(
                    block["column"]
                )
                continue
            except (
                TypeError,
                ValueError
            ):
                pass

        cx = center_x(block)

        assigned = 0

        for index in range(
            column_count
        ):

            if (
                boundaries[index]
                <= cx
                < boundaries[index + 1]
            ):
                assigned = index
                break

        block["column"] = assigned

    return blocks, column_count


# ============================================================
# Region assignment
# ============================================================

def assign_regions(
    blocks,
    page_width,
    page_height
):
    """
    Assign:

        HEADER
        MAIN
        SIDEBAR
        FOOTNOTE
        FOOTER
    """

    headers = detect_headers(
        blocks,
        page_height
    )

    footers = detect_footers(
        blocks,
        page_height
    )

    footnotes = detect_footnotes(
        blocks,
        page_height
    )

    sidebars = detect_sidebars(
        blocks,
        page_width,
        page_height
    )

    header_ids = {
        id(block)
        for block in headers
    }

    footer_ids = {
        id(block)
        for block in footers
    }

    footnote_ids = {
        id(block)
        for block in footnotes
    }

    sidebar_ids = {
        id(block)
        for block in sidebars
    }

    for block in blocks:

        # Explicit upstream information wins.
        existing = str(
            block.get(
                "region",
                ""
            )
        ).upper()

        if existing in REGIONS:
            continue

        identity = id(block)

        if identity in header_ids:
            block["region"] = "HEADER"

        elif identity in footer_ids:
            block["region"] = "FOOTER"

        elif identity in footnote_ids:
            block["region"] = "FOOTNOTE"

        elif identity in sidebar_ids:
            block["region"] = "SIDEBAR"

        else:
            block["region"] = "MAIN"

    return blocks


# ============================================================
# Sorting
# ============================================================

def sort_vertical(blocks):
    """
    Sort within one column/region.

    Main criterion:
        top to bottom

    Tie-break:
        left to right
    """

    return sorted(
        blocks,
        key=lambda block: (
            y0(block),
            x0(block)
        )
    )


def sort_region(blocks):
    """
    Sort a non-column region.
    """

    return sort_vertical(
        blocks
    )


# ============================================================
# Main reading-order reconstruction
# ============================================================

def reconstruct_reading_order(
    elements,
    page_width,
    page_height
):
    """
    Reconstruct logical page reading order.

    Ordering:

        HEADER
          ↓
        MAIN column 0
          ↓
        MAIN column 1
          ↓
        MAIN column 2...
          ↓
        SIDEBAR
          ↓
        FOOTNOTE
          ↓
        FOOTER

    The output remains spatially traceable through bbox.
    """

    if not elements:
        return []

    blocks = [
        dict(element)
        for element in elements
        if isinstance(element, dict)
    ]

    blocks = normalize_blocks(
        blocks
    )

    blocks = assign_regions(
        blocks,
        page_width,
        page_height
    )

    headers = []
    main = []
    sidebars = []
    footnotes = []
    footers = []

    for block in blocks:

        region = str(
            block.get(
                "region",
                "MAIN"
            )
        ).upper()

        if region == "HEADER":
            headers.append(block)

        elif region == "SIDEBAR":
            sidebars.append(block)

        elif region == "FOOTNOTE":
            footnotes.append(block)

        elif region == "FOOTER":
            footers.append(block)

        else:
            main.append(block)

    # --------------------------------------------------------
    # Main columns
    # --------------------------------------------------------

    main, column_count = assign_columns(
        main,
        page_width
    )

    columns = [
        []
        for _ in range(column_count)
    ]

    for block in main:

        column = block.get(
            "column",
            0
        )

        try:
            column = int(column)
        except (
            TypeError,
            ValueError
        ):
            column = 0

        column = max(
            0,
            min(
                column,
                column_count - 1
            )
        )

        block["column"] = column

        columns[column].append(
            block
        )

    ordered_main = []

    for column in columns:

        column.sort(
            key=lambda block: (
                y0(block),
                x0(block)
            )
        )

        ordered_main.extend(
            column
        )

    # --------------------------------------------------------
    # Other regions
    # --------------------------------------------------------

    headers = sort_region(
        headers
    )

    sidebars = sort_region(
        sidebars
    )

    footnotes = sort_region(
        footnotes
    )

    footers = sort_region(
        footers
    )

    # --------------------------------------------------------
    # Global reading order
    # --------------------------------------------------------

    ordered = (
        headers
        + ordered_main
        + sidebars
        + footnotes
        + footers
    )

    for reading_order, block in enumerate(
        ordered
    ):

        block["reading_order"] = (
            reading_order
        )

        block["layout_role"] = (
            block.get(
                "region",
                "MAIN"
            )
        )

    return ordered


# ============================================================
# Public page API
# ============================================================

def process_page(
    p2a_page: Dict[str, Any],
    p1_page: Optional[Dict[str, Any]] = None,
    p3_page: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process one real page.

    INPUT:
        Actual P2A page dictionary.

    Optional:
        P1 routing/layout information.
        P3 visual-object information.

    OUTPUT:
        Same page dictionary with P2B information added.
    """

    result = dict(p2a_page)

    dimensions = p2a_page.get(
        "page_dimensions",
        {}
    )

    page_width = float(
        dimensions.get(
            "width",
            0
        )
    )

    page_height = float(
        dimensions.get(
            "height",
            0
        )
    )

    p2a_elements = p2a_page.get(
        "elements",
        []
    )

    if not isinstance(
        p2a_elements,
        list
    ):
        p2a_elements = []

    elements = []

    # --------------------------------------------------------
    # P2A elements
    # --------------------------------------------------------

    for element in p2a_elements:

        if not isinstance(
            element,
            dict
        ):
            continue

        new_element = dict(
            element
        )

        new_element = apply_p1_hints(
            new_element,
            p1_page
        )

        elements.append(
            new_element
        )

    # --------------------------------------------------------
    # P3 elements
    # --------------------------------------------------------

    p3_elements = extract_p3_blocks(
        p3_page
    )

    for p3_element in p3_elements:

        if is_duplicate_p3_block(
            p3_element,
            elements
        ):
            continue

        elements.append(
            p3_element
        )

    # --------------------------------------------------------
    # Reconstruct order
    # --------------------------------------------------------

    ordered = reconstruct_reading_order(
        elements,
        page_width,
        page_height
    )

    result["elements"] = ordered

    # Useful summary metadata.
    result["p2b"] = {
        "processed": True,
        "element_count": len(ordered),
        "column_count": (
            max(
                (
                    int(
                        e.get(
                            "column",
                            0
                        )
                    )
                    for e in ordered
                    if e.get(
                        "region"
                    ) == "MAIN"
                ),
                default=0
            ) + 1
        ),
    }

    return result


# ============================================================
# Public document API
# ============================================================

def process_document(
    p2a_document: Dict[str, Any],
    p1_document: Optional[Dict[str, Any]] = None,
    p3_document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a complete document using actual upstream data.

    p2a_document:
        Output of P2A extractor.py.

    p1_document:
        Optional P1 routing/layout metadata.

    p3_document:
        Optional P3 tables/charts/equations.
    """

    if not isinstance(
        p2a_document,
        dict
    ):
        raise TypeError(
            "p2a_document must be a dictionary"
        )

    result = dict(
        p2a_document
    )

    p2a_pages = p2a_document.get(
        "pages",
        []
    )

    if not isinstance(
        p2a_pages,
        list
    ):
        p2a_pages = []

    p1_pages = []

    if isinstance(
        p1_document,
        dict
    ):
        p1_pages = p1_document.get(
            "pages",
            []
        )

    p3_pages = []

    if isinstance(
        p3_document,
        dict
    ):
        p3_pages = p3_document.get(
            "pages",
            []
        )

    processed_pages = []

    for index, p2a_page in enumerate(
        p2a_pages
    ):

        page_number = p2a_page.get(
            "page_number",
            index + 1
        )

        p1_page = None
        p3_page = None

        # Match by page number rather than blindly
        # relying on array position.
        for candidate in p1_pages:

            if (
                isinstance(candidate, dict)
                and candidate.get(
                    "page_number"
                ) == page_number
            ):
                p1_page = candidate
                break

        for candidate in p3_pages:

            if (
                isinstance(candidate, dict)
                and candidate.get(
                    "page_number"
                ) == page_number
            ):
                p3_page = candidate
                break

        processed_page = process_page(
            p2a_page,
            p1_page,
            p3_page
        )

        processed_pages.append(
            processed_page
        )

    result["pages"] = processed_pages

    return result