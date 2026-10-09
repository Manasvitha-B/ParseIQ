"""Build safe, deterministic data tables and runnable plotting code from chart JSON."""
from __future__ import annotations

import math
import base64
import logging
import threading
from io import BytesIO
from typing import Any

_MATPLOTLIB_LOCK = threading.RLock()
_LOGGER = logging.getLogger(__name__)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cell(value: Any) -> str:
    text = "—" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_region_image(page: Any, box: Any = None) -> str | None:
    """Render a bounded source crop for visual blocks, even when vision fails."""
    try:
        from PIL import Image

        pdf_page = (page.payload or {}).get("page") if isinstance(page.payload, dict) else None
        if pdf_page is not None and hasattr(pdf_page, "get_pixmap"):
            import fitz

            clip = None
            if box is not None:
                clip = fitz.Rect(box.x0, box.y0, box.x1, box.y1) & pdf_page.rect
                if clip.is_empty or clip.width < 2 or clip.height < 2:
                    return None
            bounds = clip or pdf_page.rect
            scale = min(1.5, 1000 / max(float(bounds.width), float(bounds.height), 1))
            pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        else:
            image_path = (page.metadata or {}).get("image_path")
            if not image_path:
                return None
            with Image.open(image_path) as source:
                frame_index = int((page.metadata or {}).get("frame_index", 0) or 0)
                if getattr(source, "n_frames", 1) > 1:
                    source.seek(min(max(frame_index, 0), source.n_frames - 1))
                image = source.convert("RGB")
            if box is not None:
                x0 = max(0, min(image.width, int(box.x0)))
                y0 = max(0, min(image.height, int(box.y0)))
                x1 = max(x0, min(image.width, int(box.x1)))
                y1 = max(y0, min(image.height, int(box.y1)))
                if x1 - x0 < 2 or y1 - y0 < 2:
                    return None
                image = image.crop((x0, y0, x1, y1))

        image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception as exc:
        _LOGGER.warning("Could not render source image for page %s (%s)", getattr(page, "number", "?"), type(exc).__name__)
        return None


def chart_artifacts(chart: dict[str, Any]) -> dict[str, str]:
    """Return `data_table_markdown` and a standalone Matplotlib program."""
    source_series = chart.get("series") if isinstance(chart.get("series"), list) else []
    series: list[dict[str, Any]] = []
    categories: list[str] = []
    for index, source in enumerate(source_series, 1):
        if not isinstance(source, dict):
            continue
        raw_labels = source.get("labels") if isinstance(source.get("labels"), list) else []
        raw_values = source.get("values") if isinstance(source.get("values"), list) else []
        raw_x_values = source.get("x_values") if isinstance(source.get("x_values"), list) else []
        labels = [str(raw_labels[i]) if i < len(raw_labels) and raw_labels[i] is not None else str(i + 1)
                  for i in range(len(raw_values))]
        values = [_number(value) for value in raw_values]
        x_values = [_number(raw_x_values[i]) if i < len(raw_x_values) else _number(labels[i])
                    for i in range(len(raw_values))]
        name = str(source.get("name") or f"Series {index}")
        estimated = bool(source.get("estimated", chart.get("estimated", False)))
        series.append({"name": name, "labels": labels, "values": values,
                       "x_values": x_values, "estimated": estimated})
        for label in labels:
            if label not in categories:
                categories.append(label)

    title = str(chart.get("title") or "Extracted chart")
    x_axis = str(chart.get("x_axis") or "Category")
    y_axis = str(chart.get("y_axis") or "Value")
    x_ticks = [value for item in chart.get("x_ticks", []) if (value := _number(item)) is not None] \
        if isinstance(chart.get("x_ticks"), list) else []
    y_ticks = [value for item in chart.get("y_ticks", []) if (value := _number(item)) is not None] \
        if isinstance(chart.get("y_ticks"), list) else []
    default_kind = "line" if any(item["x_values"] for item in series) else "bar"
    kind = str(chart.get("chart_type") or default_kind).strip().lower()
    pie_points: list[tuple[str, float | None]] = []
    if len(series) > 1 and all(len(item["values"]) == 1 for item in series):
        for item in series:
            label = item["labels"][0]
            if item["name"] and not item["name"].lower().startswith("series "):
                label = item["name"]
            pie_points.append((label, item["values"][0]))
    elif series:
        pie_points = list(zip(series[0]["labels"], series[0]["values"]))
    lookup = [dict(zip(item["labels"], item["values"])) for item in series]
    columns = [item["name"] + (" (estimated)" if item["estimated"] else "") for item in series]
    if not columns:
        columns = [y_axis]
    rows = ["| " + " | ".join([x_axis, *columns]) + " |",
            "| " + " | ".join(["---"] * (len(columns) + 1)) + " |"]
    for category in categories:
        cells = []
        for index, item in enumerate(series):
            value = lookup[index].get(category)
            rendered = "—" if value is None else f"{value:g}"
            if value is not None and item["estimated"]:
                rendered = "~" + rendered
            cells.append(rendered)
        rows.append("| " + " | ".join([_cell(category), *cells]) + " |")
    table = "\n".join(rows)

    # repr() creates valid Python literals and keeps source labels/titles safe.
    code = f'''import matplotlib.pyplot as plt

title = {title!r}
chart_type = {kind!r}
x_label = {x_axis!r}
y_label = {y_axis!r}
x_ticks = {x_ticks!r}
y_ticks = {y_ticks!r}
categories = {categories!r}
series = {series!r}

fig, ax = plt.subplots(figsize=(9, 5.5))
kind = chart_type.lower()

if "pie" in kind:
    points = [(label, value) for label, value in {pie_points!r}
              if value is not None and value >= 0]
    if points and sum(value for _, value in points) > 0:
        ax.pie([value for _, value in points], labels=[label for label, _ in points],
               autopct="%1.1f%%", startangle=90, textprops={{"fontsize": 9}})
        ax.axis("equal")
    else:
        ax.text(0.5, 0.5, "No legible numeric values", ha="center", va="center")
elif "line" in kind or "scatter" in kind:
    for item in series:
        x_values = item.get("x_values", [])
        points = [(x_values[index] if index < len(x_values) and x_values[index] is not None else label, value)
                  for index, (label, value) in enumerate(zip(item["labels"], item["values"]))
                  if value is not None]
        if not points:
            continue
        labels, values = zip(*points)
        if "scatter" in kind:
            ax.scatter(labels, values, label=item["name"], s=48)
        else:
            ax.plot(labels, values, marker="o", linewidth=2, label=item["name"])
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if x_ticks:
        ax.set_xticks(x_ticks)
    if y_ticks:
        ax.set_yticks(y_ticks)
    ax.grid(True, linestyle="--", alpha=0.35)
    if len(series) > 1:
        ax.legend()
else:
    width = 0.8 / max(len(series), 1)
    positions = {{label: index for index, label in enumerate(categories)}}
    bottom = [0.0] * len(categories)
    for series_index, item in enumerate(series):
        values_by_label = dict(zip(item["labels"], item["values"]))
        values = [values_by_label.get(label) for label in categories]
        if "stack" in kind:
            heights = [float("nan") if value is None else value for value in values]
            ax.bar(range(len(categories)), heights, width=0.8, bottom=bottom,
                   label=item["name"], alpha=0.85)
            bottom = [base + (0.0 if value is None else value) for base, value in zip(bottom, values)]
        else:
            offset = (series_index - (len(series) - 1) / 2) * width
            xs = [positions[label] + offset for label in categories]
            ax.bar(xs, [float("nan") if value is None else value for value in values],
                   width=width, label=item["name"], alpha=0.85)
    ax.set_xticks(range(len(categories)), categories, rotation=25, ha="right")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if y_ticks:
        ax.set_yticks(y_ticks)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    if len(series) > 1:
        ax.legend()

ax.set_title(title)
if not any(value is not None for item in series for value in item["values"]):
    ax.text(0.5, 0.5, "No legible numeric values were extracted", transform=ax.transAxes,
            ha="center", va="center")
fig.tight_layout()
plt.show()
'''
    return {"data_table_markdown": table, "python_code": code}


def render_chart_image(chart: dict[str, Any]) -> str | None:
    """Run our generated Matplotlib program headlessly and return its PNG output.

    Only the deterministic program produced by ``chart_artifacts`` is executed;
    document/model-provided Python source is never passed to ``exec``.
    """
    try:
        source_series = chart.get("series") if isinstance(chart.get("series"), list) else []
        if not any(_number(value) is not None
                   for item in source_series if isinstance(item, dict)
                   for value in (item.get("values") if isinstance(item.get("values"), list) else [])):
            return None
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        with _MATPLOTLIB_LOCK:
            namespace: dict[str, Any] = {"__name__": "_parseiq_chart_render_"}
            # Generated source calls show(); in a headless server that should be a no-op.
            original_show = plt.show
            plt.show = lambda *args, **kwargs: None
            try:
                code = chart_artifacts(chart)["python_code"]
                exec(compile(code, "<ParseIQ generated chart>", "exec"), namespace, namespace)
                figure = namespace.get("fig")
                if figure is None:
                    return None
                output = BytesIO()
                figure.savefig(output, format="png", dpi=120, bbox_inches="tight")
                plt.close(figure)
                return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
            finally:
                plt.show = original_show
    except Exception:
        return None
