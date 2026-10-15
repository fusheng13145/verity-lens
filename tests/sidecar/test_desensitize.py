"""desensitize 侧车工具测试（Phase 4f）：脱敏 + E10 扫描守卫。

原则：除 DP 加噪（seed 可复现）外全部确定性断言；不依赖网络/外部底座。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sidecar.tools.desensitize import (
    dp_aggregate,
    field_mask,
    k_anonymity,
    run,
    scan_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

SAMPLE = [
    {"name": "张三", "sex": "M", "age": 34, "diag": "X"},
    {"name": "李四", "sex": "F", "age": 29, "diag": "Y"},
    {"name": "王五", "sex": "F", "age": 29, "diag": "Z"},
]


def test_field_mask_hash_is_reproducible_and_one_way():
    r1 = field_mask(SAMPLE, ["name"], strategy="hash", salt="s1")
    r2 = field_mask(SAMPLE, ["name"], strategy="hash", salt="s1")
    assert r1["masked_records"][0]["name"] == r2["masked_records"][0]["name"]
    # 原文不能从令牌反推，且令牌以 h_ 前缀、长度 16 哈希
    tok = r1["masked_records"][0]["name"]
    assert tok.startswith("h_") and len(tok) == 18
    assert "张三" not in tok
    # 其他字段不受影响
    assert r1["masked_records"][0]["diag"] == "X"


def test_field_mask_redact_and_generalize():
    rd = field_mask(SAMPLE, ["name"], strategy="redact")
    assert rd["masked_records"][0]["name"] == "[REDACTED]"
    gn = field_mask([{"age": 34}], ["age"], strategy="generalize")
    assert gn["masked_records"][0]["age"] == "34-"  # 个位泛化到十位下界


def test_field_mask_rejects_empty_fields():
    try:
        field_mask(SAMPLE, [])
    except ValueError as e:
        assert "fields" in str(e)
    else:
        raise AssertionError("空 fields 必须报错")


def test_k_anonymity_suppresses_unique_qi_groups():
    data = [
        {"sex": "M", "age": 34, "v": 1},
        {"sex": "F", "age": 29, "v": 2},
        {"sex": "F", "age": 29, "v": 3},
        {"sex": "F", "age": 29, "v": 4},
        {"sex": "M", "age": 40, "v": 5},
    ]
    ka = k_anonymity(data, ["sex", "age"], k=3)
    # (F,29) 出现 3 次 → 保留；(M,34)/(M,40) 各 1 次 → 抑制（共 2 条）
    assert ka["suppressed_count"] == 2
    assert ka["k_satisfied"] is False
    assert ka["unique_qi_groups"] == 3
    # 被抑制行的 QI 全部置为抑制标记
    suppressed = [r for r in ka["anonymized_records"]
                  if r["sex"] == "[SUPPRESSED]"]
    assert len(suppressed) == 2
    # 仍保留非 QI 字段（便于审计）
    assert suppressed[0]["v"] in (1, 5)


def test_k_anonymity_k2_satisfied():
    # 每组都 ≥2 → 满足 k=2
    data = [{"q": 1}, {"q": 1}, {"q": 2}, {"q": 2}]
    ka = k_anonymity(data, ["q"], k=2)
    assert ka["suppressed_count"] == 0
    assert ka["k_satisfied"] is True


def test_dp_aggregate_seed_reproducible_and_epsilon_default():
    a = dp_aggregate([1, 2, 3, 4, 5], epsilon=1.0, statistic="mean", seed=42)
    b = dp_aggregate([1, 2, 3, 4, 5], epsilon=1.0, statistic="mean", seed=42)
    assert a["noisy_value"] == b["noisy_value"]          # seed 复现
    assert a["raw_value"] == 3.0
    assert a["epsilon"] == 1.0                           # 蓝图默认 ε=1.0
    assert a["sensitivity"] == 0.8                       # (5-1)/5


def test_dp_aggregate_seed_changes_output():
    a = dp_aggregate([1, 2, 3, 4, 5], seed=1)
    b = dp_aggregate([1, 2, 3, 4, 5], seed=2)
    assert a["noisy_value"] != b["noisy_value"]          # 不同种子不同噪声


def test_dp_aggregate_statistics():
    s = dp_aggregate([10, 20, 30], statistic="sum", bounds=[0, 100], seed=7)
    assert s["raw_value"] == 60.0 and s["sensitivity"] == 100.0
    c = dp_aggregate([1, 2, 3], statistic="count", seed=1)
    assert c["raw_value"] == 3.0 and c["sensitivity"] == 1.0


def test_dp_aggregate_rejects_empty():
    try:
        dp_aggregate([])
    except ValueError:
        pass
    else:
        raise AssertionError("空 values 必须报错")


def test_scan_text_detects_phi_and_risk():
    txt = "联系 z@hospital.org 手机 13800138000 身份证 11010119900101123X 生日 1990-01-01"
    sc = scan_text(txt)
    assert sc["has_phi"] is True
    assert sc["risk_level"] == "high"
    types = {h["type"] for h in sc["hits"]}
    assert {"email", "cn_mobile", "cn_id_card", "date_of_birth"} <= types


def test_scan_text_clean_text_is_safe():
    sc = scan_text("普通实验记录，样本量 n=30，p=0.04，无个人身份信息")
    assert sc["has_phi"] is False
    assert sc["risk_level"] == "none"


def test_run_dispatch_unknown_mode():
    try:
        run("bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("未知 mode 必须报错")


# --------------------------------------------------------------------------- #
# stdio 入口（MCP 声明可执行）
# --------------------------------------------------------------------------- #
def _run_tool(module: str, payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", module],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_desensitize_stdio_scan():
    out = _run_tool("sidecar.tools.desensitize",
                    {"mode": "scan_text", "text": "email a@b.com phone 13912345678"})
    assert out["has_phi"] is True
    assert out["risk_level"] == "high"


def test_desensitize_stdio_k_anonymity():
    out = _run_tool("sidecar.tools.desensitize", {
        "mode": "k_anonymity",
        "records": [{"q": 1}, {"q": 2}, {"q": 2}],
        "quasi_identifiers": ["q"], "k": 2,
    })
    assert out["suppressed_count"] == 1
    assert out["k_satisfied"] is False


def test_desensitize_stdio_reports_incoherent_input():
    """非法输入必须显式报错（退出码 1 + error），不得静默返回。"""
    proc = subprocess.run(
        [sys.executable, "-m", "sidecar.tools.desensitize"],
        input=json.dumps({"mode": "field_mask", "records": [{}], "fields": []}),
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)
