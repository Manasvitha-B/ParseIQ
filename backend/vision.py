"""Multimodal extraction for cropped document regions.

Credentials are read only from environment variables (optionally populated from
the project .env file). No key is embedded in source code or returned in API data.
"""
from __future__ import annotations

import base64
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_local_environment() -> None:
    """Load a local .env if python-dotenv is installed; keep deployment envs native."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        load_dotenv(ROOT / "graphextract" / ".env", override=False)
    except ImportError:
        pass


def _crop_png(page: Any, region: Any) -> bytes | None:
    """Render a region in page coordinates and enhance it without discarding color."""
    if page is None or region is None:
        return None
    pdf_page = (page.payload or {}).get("page") if isinstance(page.payload, dict) else None
    if pdf_page is None or not hasattr(pdf_page, "get_pixmap"):
        return None
    try:
        import fitz
        import cv2
        import numpy as np

        clip = None
        if region.box is not None:
            clip = fitz.Rect(region.box.x0, region.box.y0, region.box.x1, region.box.y1)
            clip &= pdf_page.rect
        if clip is not None and (clip.is_empty or clip.width < 2 or clip.height < 2):
            return None
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip, alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
        enhanced = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(gray)
        enhanced = cv2.bilateralFilter(enhanced, 7, 45, 45)
        ok, encoded = cv2.imencode(".png", enhanced)
        return encoded.tobytes() if ok else None
    except Exception:
        return None


_PROMPT = """Inspect the whole supplied document crop. Extract only information visibly present; never infer missing values.
Return exactly one JSON object with keys: block_type, text, description, latex, table, chart, confidence.
block_type must be one of: text_block, table, chart, figure, equation.
Transcribe all printed and handwritten text faithfully in reading order. Put equations in standard LaTeX in `latex` (without display delimiters). For tables, `table` is an object with `matrix` (array of rows and cell strings) and `markdown`. For charts, `chart` is an object with `chart_type`, `title`, `x_axis`, `y_axis`, and `series`; each series has `name`, `labels` (array), and `values` (numeric array). Only provide chart values that are legible; use null for values that cannot be read. In `description`, concisely describe visible diagram/figure relationships and labels. Use empty strings/nulls/empty arrays for absent fields. Set confidence to a number from 0 to 1 based only on legibility. Do not include preambles or markdown fences."""


def _parse_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _normalize(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {"text_block", "table", "chart", "figure", "equation"}
    kind = str(result.get("block_type", "text_block")).lower()
    aliases = {"text": "text_block", "diagram": "figure", "flowchart": "figure", "graph": "chart", "formula": "equation"}
    kind = aliases.get(kind, kind)
    if kind not in allowed:
        kind = "text_block"
    text = result.get("text")
    if not isinstance(text, str):
        text = ""
    desc = result.get("description")
    if not isinstance(desc, str):
        desc = ""
    latex = result.get("latex")
    if not isinstance(latex, str):
        latex = ""
    if kind == "equation" and latex and not text:
        text = latex
    table = result.get("table") if isinstance(result.get("table"), dict) else {}
    chart = result.get("chart") if isinstance(result.get("chart"), dict) else {}
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    has_content = bool(text.strip() or desc.strip() or latex.strip() or table.get("matrix") or chart.get("series"))
    if has_content:
        confidence = max(confidence, 0.86)
    else:
        confidence = min(confidence, 0.4)
    return {"block_type": kind, "text": text.strip(), "description": desc.strip(), "latex": latex.strip(),
            "table": table, "chart": chart, "confidence": confidence, "provider": None, "model": None}


class VisionService:
    """Calls Gemini (preferred) or the OpenRouter-compatible vision endpoint."""

    def __init__(self) -> None:
        self._gemini_client = None
        self._gemini_key: str | None = None
        self._openrouter_client = None
        self._openrouter_key: str | None = None

    def analyze(self, page: Any, region: Any) -> dict[str, Any] | None:
        load_local_environment()
        image = _crop_png(page, region)
        if not image:
            return None
        gemini_key = os.getenv("GEMINI_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        configured = [provider for provider, key in (("gemini", gemini_key), ("openrouter", openrouter_key)) if key]
        if not configured:
            return None
        preferred = os.getenv("VISION_PROVIDER", "gemini").lower()
        if preferred in configured:
            configured.remove(preferred)
            configured.insert(0, preferred)
        last_error = "Vision provider returned invalid JSON"
        for provider in configured:
            try:
                if provider == "gemini":
                    from google import genai
                    from google.genai import types
                    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                    if self._gemini_client is None or self._gemini_key != gemini_key:
                        self._gemini_client = genai.Client(api_key=gemini_key)
                        self._gemini_key = gemini_key
                    response = self._gemini_client.models.generate_content(
                        model=model,
                        contents=[types.Part.from_bytes(data=image, mime_type="image/png"), _PROMPT],
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
                    )
                    parsed = _parse_json(response.text or "")
                else:
                    from openai import OpenAI
                    model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")
                    if self._openrouter_client is None or self._openrouter_key != openrouter_key:
                        self._openrouter_client = OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1", timeout=60)
                        self._openrouter_key = openrouter_key
                    data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
                    response = self._openrouter_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": [
                            {"type": "text", "text": _PROMPT},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ]}],
                        temperature=0,
                        max_tokens=3000,
                    )
                    parsed = _parse_json(response.choices[0].message.content or "")
                if parsed is None:
                    last_error = f"{provider} returned invalid JSON"
                    continue
                normalized = _normalize(parsed)
                normalized["provider"] = provider
                normalized["model"] = model
                return normalized
            except Exception as exc:
                # Try the other configured provider (for example, when a key has expired).
                last_error = f"{provider}: {type(exc).__name__}: {exc}"
        # Error text is surfaced in metadata without including provider secrets.
        return {"error": last_error}


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    return VisionService()

