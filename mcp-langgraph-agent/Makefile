# Makefile - 常用命令集合
#
# 提供安装依赖、启动开发服务器、代码检查、测试运行和 Docker 管理等常用操作的快捷命令。

.PHONY: help install dev lint test docker-up docker-down clean

# 默认目标：显示帮助信息
help:  # 显示所有可用命令的帮助信息
	@echo "可用命令:"
	@echo "  make install     - 安装 Python 依赖"
	@echo "  make dev         - 启动开发服务器"
	@echo "  make lint        - 运行代码检查（ruff + mypy）"
	@echo "  make test        - 运行测试用例"
	@echo "  make docker-up   - 启动 Docker 容器"
	@echo "  make docker-down - 停止 Docker 容器"
	@echo "  make clean       - 清理缓存和临时文件"

# 安装 Python 依赖
install:  # 安装项目依赖（开发模式）
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -e ".[dev]"

# 启动开发服务器
dev:  # 以开发模式启动 MCP Server 和 LangGraph Agent
	@echo "启动开发服务器..."
	python -m src.mobile_mcp.server &
	python -m src.main &
	@echo "开发服务器已启动：MCP Server (8000), LangGraph Agent (8001)"

# 运行代码检查
lint:  # 使用 ruff 和 mypy 进行代码风格和类型检查
	@echo "运行 ruff 代码检查..."
	ruff check src/ tests/
	@echo "运行 mypy 类型检查..."
	mypy src/ tests/

# 运行测试
test:  # 运行 pytest 测试用例并生成覆盖率报告
	@echo "运行测试用例..."
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

# 启动 Docker 容器
docker-up:  # 使用 docker-compose 启动所有服务（后台运行）
	@echo "启动 Docker 容器..."
	docker-compose up -d
	@echo "所有服务已启动"

# 停止 Docker 容器
docker-down:  # 停止并移除 Docker 容器
	@echo "停止 Docker 容器..."
	docker-compose down
	@echo "所有服务已停止"

# 清理缓存和临时文件
clean:  # 清理 __pycache__、.pytest_cache、.coverage 等缓存文件
	@echo "清理缓存文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ dist/ build/
	@echo "缓存清理完成"