# verity-lens 常用任务（与 docs/interfaces.md、AGENTS.md、testing.md 中的命令一致）
# 用法：make <target>

PY      ?= python
VENV    := .venv
VENV_PY := $(VENV)/Scripts/python.exe   # Windows；Linux/macOS 请用 $(VENV)/bin/python
WEB     := web

.PHONY: help venv install schema-check golden hal-contract-test correctness \
        integration test api web reproduce clean

help:            ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv:            ## 创建虚拟环境
	$(PY) -m venv $(VENV)

install:         ## 安装依赖（可编辑模式）
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -e .

schema-check:    ## L1：声明式文件 Schema 校验
	$(VENV_PY) -m pytest tests/schema -q

golden:          ## L2：Golden 轨迹回归
	$(VENV_PY) -m pytest tests/golden -q

hal-contract-test: ## L4：HAL 契约测试（底座升级必跑）
	$(VENV_PY) -m pytest hal/contract_tests -q

correctness:     ## L3：科研正确性抽检
	$(VENV_PY) -m pytest tests/correctness -q

integration:     ## L4：Sidecar 工具 stdio 边界 ↔ 进程内模块 输出保真
	$(VENV_PY) -m pytest tests/integration -q

test:            ## 运行全部测试
	$(VENV_PY) -m pytest -q

api:             ## 启动 Headless API（:8000）
	$(VENV_PY) -m uvicorn orchestrator.api:app --port 8000

web:             ## 启动前端开发服务器（:5173）
	cd $(WEB) && npm run dev

reproduce:       ## 复现：从 data/raw 到 figures（占位）
	@echo "[reproduce] 按 manifest.yaml 复现；Phase 1 实现"

clean:           ## 清理缓存
	-rm -rf .pytest_cache **/__pycache__ *.egg-info 2>/dev/null || true
