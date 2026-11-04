.PHONY: dev test build up down logs clean deploy release

PY ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

# --- 开发 ---

dev:
	@echo "启动开发环境..."
	@cd src/web && npm run dev &
	@cd src/api && uvicorn app.main:app --reload

# --- 测试 ---

# 后端冒烟测试
test:
	$(PY) src/api/tests/smoke.py

# --- 构建与部署 ---

# 重新构建镜像（前端+后端），无缓存
build:
	@echo "重新构建镜像（无缓存）..."
	docker compose build --no-cache

# 启动服务
up:
	@echo "启动服务..."
	docker compose up -d

# 重建并重启
deploy: build up

# --- 运维 ---

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	@echo "清理..."
	docker compose down --rmi local -v
	cd src/web && rm -rf dist node_modules

# --- 发布 ---

# 打 tag 触发 CI 释出镜像到 ghcr.io：make release VERSION=1.0.0
release:
ifndef VERSION
	$(error 用法: make release VERSION=1.0.0)
endif
	git tag v$(VERSION)
	git push origin main v$(VERSION)
