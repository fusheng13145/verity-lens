"""scripts/reproduce.py 单元测试（审计 #11 真实可复现比对）。"""
import json

import scripts.reproduce as reproduce
from pathlib import Path


def _make_ws(tmp_path: Path) -> Path:
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "exp1.csv").write_text(
        "label,value\na,1\nb,2\nc,3\n", encoding="utf-8"
    )
    return tmp_path


def test_baseline_established_then_consistent(tmp_path):
    ws = _make_ws(tmp_path)
    code1 = reproduce.main(["--workspace", str(ws)])
    assert code1 == 0
    # 第二次应判为 consistent（基线已持久化）
    code2 = reproduce.main(["--workspace", str(ws)])
    assert code2 == 0
    base = json.loads((ws / ".verity" / "reproduce_baseline.json").read_text(encoding="utf-8"))
    assert "figures/exp1.svg" in base


def test_drift_detected_and_nonzero_exit(tmp_path):
    ws = _make_ws(tmp_path)
    assert reproduce.main(["--workspace", str(ws)]) == 0  # establish
    # 改变数据 → 图变化 → 漂移
    (ws / "data" / "raw" / "exp1.csv").write_text(
        "label,value\na,10\nb,20\nc,30\n", encoding="utf-8"
    )
    assert reproduce.main(["--workspace", str(ws)]) == 1


def test_update_refreshes_baseline(tmp_path):
    ws = _make_ws(tmp_path)
    assert reproduce.main(["--workspace", str(ws)]) == 0
    (ws / "data" / "raw" / "exp1.csv").write_text(
        "label,value\na,10\nb,20\nc,30\n", encoding="utf-8"
    )
    # --update 刷新基线，不报错
    assert reproduce.main(["--workspace", str(ws), "--update"]) == 0
    # 之后再次复现应一致
    assert reproduce.main(["--workspace", str(ws)]) == 0


def test_no_data_is_noop(tmp_path):
    assert reproduce.main(["--workspace", str(tmp_path)]) == 0
