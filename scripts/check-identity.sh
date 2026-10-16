#!/usr/bin/env bash
# 身份可信化 CI / pre-commit 门禁（P0，见 docs/collab.md §7.8）。
#
# 用途：在 CI 或提交前强制校验协作者身份，使「写锁互斥 / committer 比对」不再依赖
#       可伪造的口头约定（VL_USER / git config），而是：
#         - set      : 必须设置 VL_USER（标识当前用户，可由团队 SSO/CI 注入）
#         - coherent : VL_USER 必须与 git committer 一致（本地 pre-commit 推荐级别）
#         - signed   : 最新提交必须通过 GPG/SSH 签名校验（最强、密码学锚定）
# 退出码：0 通过；1 身份不满足强制级别；2 用法/环境错误。
set -euo pipefail

REQUIRE="coherent"
PATH_ARG="."
ALLOWED_DOMAIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require)            REQUIRE="$2"; shift 2;;
    --path)               PATH_ARG="$2"; shift 2;;
    --allowed-email-domain) ALLOWED_DOMAIN="$2"; shift 2;;
    *) echo "[check-identity] 未知参数: $1" >&2; exit 2;;
  esac
done

# 定位 vl CLI（优先 PATH，回退 python -m orchestrator.cli）
if command -v vl >/dev/null 2>&1; then
  VL="vl"
else
  VL="python -m orchestrator.cli"
fi

echo "[check-identity] 运行: $VL identity --require $REQUIRE --json --path $PATH_ARG"
REPORT="$($VL identity --require "$REQUIRE" --json --path "$PATH_ARG")" || {
  echo "$REPORT"
  echo "[check-identity] FAIL: 身份检查未通过（--require $REQUIRE）"
  exit 1
}
echo "$REPORT"

# 可选：committer 邮箱域名白名单（与签名/committer 配合，限制为团队组织邮箱）
if [[ -n "$ALLOWED_DOMAIN" ]]; then
  EMAIL="$(printf '%s' "$REPORT" | python -c "import sys,json;print((json.load(sys.stdin).get('committer_email') or ''))" 2>/dev/null || true)"
  if [[ -n "$EMAIL" ]]; then
    DOMAIN="${EMAIL##*@}"
    if [[ "$DOMAIN" != "$ALLOWED_DOMAIN" ]]; then
      echo "[check-identity] FAIL: committer 邮箱域名 '$DOMAIN' 不在白名单 '$ALLOWED_DOMAIN'"
      exit 1
    fi
  fi
fi

echo "[check-identity] PASS"
exit 0
