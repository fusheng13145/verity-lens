"""Sidecar 工具：确定性图表生成（科研产物，analysis → figures）。

工程纪律（design-blueprint.md §2.8 / tool-calling.md）：
- 图表是科研产出，必须由确定性工具生成，模型不得自行产出像素；
- 相同输入必须得到相同输出（不含时间戳、随机等不确定因素）；
- 纯标准库实现（不依赖 matplotlib），保证可复现且零额外依赖。

用法：
    plot.bar_chart(csv_path, out_path, title="...")
    plot.line_chart(csv_path, out_path, title="...")
返回写入的文件路径；输入非法时抛 ``ValueError``（不静默返回）。
"""
from __future__ import annotations

import csv
from pathlib import Path

TOOL_SPEC = {
    "name": "plot",
    "description": "确定性图表生成：把 CSV 统计结果渲染为 SVG 矢量图（analysis → figures）",
    "input_schema": {
        "type": "object",
        "properties": {
            "csv_path": {"type": "string", "description": "输入 CSV 路径（首列为标签，其余列为数值）"},
            "out_path": {"type": "string", "description": "输出 SVG 路径（建议 figures/ 下）"},
            "kind": {"type": "string", "enum": ["bar", "line"], "default": "bar"},
            "title": {"type": "string", "default": ""},
        },
        "required": ["csv_path", "out_path"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "out_path": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
    },
}


def _load_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _to_floats(values: list[str]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"数值列解析失败: {v!r} — {exc}")
    return out


def _svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def bar_chart(csv_path, out_path, *, title: str = "", width: int = 640, height: int = 400) -> Path:
    """从 CSV 生成柱状图 SVG（首列标签，第二列数值）。"""
    header, rows = _load_csv(Path(csv_path))
    if not rows or len(header) < 2:
        raise ValueError("bar_chart 需要至少两列（标签, 数值）的 CSV")
    labels = [r[0] for r in rows]
    values = _to_floats([r[1] for r in rows])

    pad = 48
    plot_w = width - pad * 2
    plot_h = height - pad * 2
    vmax = max(values)
    vmin = min(0.0, min(values))
    span = (vmax - vmin) or 1.0
    n = len(values)
    slot = plot_w / max(n, 1)
    bar_w = slot * 0.6

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    if title:
        parts.append(f'<text x="{pad}" y="24" font-size="16">{_svg_escape(title)}</text>')
    # 基线
    base_y = height - pad
    parts.append(f'<line x1="{pad}" y1="{base_y}" x2="{width - pad}" y2="{base_y}" stroke="#888"/>')
    for i, (lab, val) in enumerate(zip(labels, values)):
        x = pad + slot * i + (slot - bar_w) / 2
        h = (val - vmin) / span * plot_h
        y = base_y - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="#2b6cb0"/>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" font-size="11" '
            f'text-anchor="middle">{val:.2f}</text>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{base_y + 16:.1f}" font-size="11" '
            f'text-anchor="middle">{_svg_escape(str(lab))}</text>'
        )
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    return out


def line_chart(csv_path, out_path, *, title: str = "", width: int = 640, height: int = 400) -> Path:
    """从 CSV 生成折线图 SVG（首列标签/x，其余列各为一条序列）。"""
    header, rows = _load_csv(Path(csv_path))
    if not rows or len(header) < 2:
        raise ValueError("line_chart 需要至少两列（x, y...）的 CSV")
    xs = list(range(len(rows)))
    series: list[tuple[str, list[float]]] = []
    for col in range(1, len(header)):
        series.append((header[col], _to_floats([r[col] for r in rows])))

    pad = 48
    plot_w = width - pad * 2
    plot_h = height - pad * 2
    all_vals = [v for _, vs in series for v in vs]
    vmax = max(all_vals) if all_vals else 1.0
    vmin = min(0.0, min(all_vals)) if all_vals else 0.0
    span = (vmax - vmin) or 1.0
    n = len(rows)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    if title:
        parts.append(f'<text x="{pad}" y="24" font-size="16">{_svg_escape(title)}</text>')
    base_y = height - pad
    parts.append(f'<line x1="{pad}" y1="{base_y}" x2="{width - pad}" y2="{base_y}" stroke="#888"/>')
    colors = ("#2b6cb0", "#c53030", "#2f855a", "#d69e2e")
    for si, (name, vals) in enumerate(series):
        pts = []
        for i, val in enumerate(vals):
            x = pad + (plot_w * i / max(n - 1, 1))
            y = base_y - (val - vmin) / span * plot_h
            pts.append(f"{x:.1f},{y:.1f}")
        color = colors[si % len(colors)]
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(
            f'<text x="{pad}" y="{40 + si * 16}" font-size="12" fill="{color}">{_svg_escape(name)}</text>'
        )
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    return out


def render(csv_path, out_path, *, kind: str = "bar", title: str = "") -> Path:
    """按 kind 分派到 bar / line；CLI 与编排层统一入口。"""
    if kind == "line":
        return line_chart(csv_path, out_path, title=title)
    if kind == "bar":
        return bar_chart(csv_path, out_path, title=title)
    raise ValueError(f"未知图表类型: {kind}（可选 bar / line）")
