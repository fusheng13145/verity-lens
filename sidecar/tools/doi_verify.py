"""Sidecar 工具：DOI 校验（确定性 + 网络降级）。

用途（design-blueprint.md §2.7）。
约束：引用有效性目标 ≥95%；网络不可用时返回 exists=False + error，
      由编排层决定是否阻断（不静默通过，也不把失败当成"已验证"）。
"""
from __future__ import annotations

import re

CROSSREF_API = "https://api.crossref.org/works/{doi}"

# DOI 基本格式（不含空格，含合法字符）
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$", re.IGNORECASE)


def normalize(doi: str) -> str:
    """归一化 DOI：去空格、去 https://doi.org/ 前缀、转小写。"""
    d = (doi or "").strip()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d, flags=re.IGNORECASE)
    return d.strip().lower()


def is_valid_format(doi: str) -> bool:
    """仅做格式检查（离线可用）。"""
    return bool(DOI_RE.match(normalize(doi)))


def run(doi: str, timeout: float = 10.0, expected_title: str | None = None) -> dict:
    """校验 DOI 存在性（在线）；可传入期望标题做元数据匹配。"""
    d = normalize(doi)
    if not is_valid_format(d):
        return {"doi": d, "exists": False, "metadata_match": None, "error": "DOI 格式非法"}

    try:
        import httpx
    except ImportError:
        return {
            "doi": d,
            "exists": False,
            "metadata_match": None,
            "error": "缺少 httpx 依赖，无法在线校验",
        }

    try:
        resp = httpx.get(CROSSREF_API.format(doi=d), timeout=timeout)
    except Exception as exc:
        return {
            "doi": d,
            "exists": False,
            "metadata_match": None,
            "error": f"网络请求失败: {exc}",
        }

    if resp.status_code != 200:
        return {
            "doi": d,
            "exists": False,
            "metadata_match": None,
            "error": f"Crossref 返回 {resp.status_code}",
        }

    metadata_match = None
    if expected_title:
        try:
            title = (resp.json().get("message") or {}).get("title") or [""]
            actual = str(title[0]).strip().lower()
            metadata_match = actual == str(expected_title).strip().lower()
        except Exception:
            metadata_match = None

    return {"doi": d, "exists": True, "metadata_match": metadata_match, "error": None}


if __name__ == "__main__":
    import sys

    from sidecar.tools._stdio import serve

    sys.exit(serve(run))
