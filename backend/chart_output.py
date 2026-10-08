"""Build safe, deterministic data tables and runnable plotting code from chart JSON."""
from __future__ import annotations

import math
import base64
import threading
from io import BytesIO
from typing import Any

_MATPLOTLIB_LOCK = threading.RLock()


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
    default_kind = "line" if any(item["x_values"] for item in series) else "bar"
    kind = str(chart.get("chart_type") or default_kind).strip().lower()
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
categories = {categories!r}
series = {series!r}

fig, ax = plt.subplots(figsize=(9, 5.5))
kind = chart_type.lower()

if "pie" in kind:
    pie_series = series[0] if series else {{"labels": [], "values": [], "name": "Series 1"}}
    points = [(label, value) for label, value in zip(pie_series["labels"], pie_series["values"])
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
