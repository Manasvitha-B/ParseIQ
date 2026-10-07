"""
P2B - Document Structure

Builds document-level relationships from already extracted
and ordered page elements.

Does not perform extraction or OCR.
"""

from typing import Any, Dict, List


def get_text(block):
    value = block.get("text")

    if value is None:
        value = block.get("content")

    if isinstance(value, str):
        return value.strip()

    return ""


def build_sections(document):
    """
    Build a lightweight section structure from ordered headings.

    Example:

        HEADING
        PARAGRAPH
        PARAGRAPH
        HEADING
        PARAGRAPH

    becomes:

        Section 1
            paragraph
            paragraph

        Section 2
            paragraph
    """

    sections = []
    current = None
    section_number = 0

    for page in document.get(
        "pages",
        []
    ):

        page_number = page.get(
            "page_number"
        )

        for element in page.get(
            "elements",
            []
        ):

            semantic_type = str(
                element.get(
                    "semantic_type",
                    element.get(
                        "type",
                        ""
                    )
                )
            ).upper()

            if semantic_type == "HEADING":

                section_number += 1

                current = {
                    "section_id": (
                        f"section_{section_number}"
                    ),
                    "heading": get_text(
                        element
                    ),
                    "heading_page": page_number,
                    "elements": [],
                }

                sections.append(
                    current
                )

            elif current is not None:

                current["elements"].append(
                    {
                        "page": page_number,
                        "reading_order": element.get(
                            "reading_order"
                        ),
                        "element": element,
                    }
                )

    return sections


def add_document_structure(
    document
):
    """
    Add P2B document-level structure.

    Existing document data remains untouched.
    """

    result = dict(document)

    result["document_structure"] = {
        "sections": build_sections(
            document
        )
    }

    return result