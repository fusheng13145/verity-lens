"""确定性绘图工具测试（对应审计 P0-3 的「真实产物生成器」）。

验证：bar/line 图表生成确定性、产物为真实图像（可被 gates._looks_like_image 识别）、
非法输入抛 ValueError。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator import gates
from sidecar.tools import plot


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.write_text("\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8")


def test_bar_chart_produces_real_image(tmp_path):
    csv = tmp_path / "data.csv"
    _write_csv(csv, [["group", "value"], ["A", "1.2"], ["B", "2.3"], ["C", "0.8"]])
    out = tmp_path / "figures" / "bar.svg"
    res = plot.bar_chart(csv, out, title="Effect size")
    assert res.exists()
    text = out.read_text(encoding="utf-8")
    assert "<svg" in text and "polyline" not in text
    # 产物须被写作门禁的实质图像检查识别
    assert gates._looks_like_image(out) is True


def test_bar_chart_deterministic(tmp_path):
    csv = tmp_path / "data.csv"
    _write_csv(csv, [["g", "v"], ["A", "1.0"], ["B", "2.0"]])
    out1 = plot.bar_chart(csv, tmp_path / "a.svg")
    out2 = plot.bar_chart(csv, tmp_path / "b.svg")
    assert out1.read_text() == out2.read_text()


def test_line_chart_produces_real_image(tmp_path):
    csv = tmp_path / "data.csv"
    _write_csv(csv, [["t", "x", "y"], ["1", "0.1", "0.9"], ["2", "0.4", "0.5"]])
    out = plot.line_chart(csv, tmp_path / "figures" / "line.svg", title="Trend")
    assert gates._looks_like_image(out) is True
    assert "polyline" in out.read_text()


def test_bar_chart_rejects_bad_csv(tmp_path):
    csv = tmp_path / "bad.csv"
    _write_csv(csv, [["g"], ["A"]])  # 缺少数值列
    with pytest.raises(ValueError):
        plot.bar_chart(csv, tmp_path / "x.svg")


def test_bar_chart_rejects_nonnumeric(tmp_path):
    csv = tmp_path / "bad.csv"
    _write_csv(csv, [["g", "v"], ["A", "not_a_number"]])
    with pytest.raises(ValueError):
        plot.bar_chart(csv, tmp_path / "x.svg")
