#!/usr/bin/env bash
# =============================================================================
# MobileAutomation 一键部署脚本
#
# 用法:
#   chmod +x deploy.sh
#   ./deploy.sh              # 交互式部署（推荐新手使用）
#   ./deploy.sh --docker     # Docker 部署
#   ./deploy.sh --local      # 本地开发部署
#   ./deploy.sh --check      # 仅检查环境依赖
#   ./deploy.sh --dashboard  # 仅启动 Dashboard 前端
# =============================================================================

set -euo pipefail

# ── 颜色定义 ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── 项目路径 ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
DASHBOARD_DIR="$(dirname "${SCRIPT_DIR}")/mobile-test-dashboard"

# ── 工具函数 ──────────────────────────────────────────────────

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║       MobileAutomation 一键部署脚本 v1.0        ║"
    echo "  ║   MCP Server + LangGraph Agent 移动端自动化      ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}${BOLD}▸ $1${NC}\n"
}

print_success() {
    echo -e "${GREEN}✔ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✘ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

ask_yes_no() {
    local prompt="$1"
    local default="${2:-Y}"
    local suffix
    if [[ "$default" == "Y" ]]; then
        suffix="[Y/n]"
    else
        suffix="[y/N]"
    fi
    while true; do
        read -rp "$(echo -e "${BOLD}${prompt} ${suffix}: ${NC}")" answer
        answer="${answer:-$default}"
        case "$answer" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo -e "${YELLOW}请输入 y 或 n${NC}" ;;
        esac
    done
}

# ── 环境检查 ──────────────────────────────────────────────────

check_command() {
    if command -v "$1" &>/dev/null; then
        local version
        version=$("$1" --version 2>/dev/null | head -1 || echo "已安装")
        print_success "$1: ${version}"
        return 0
    else
        print_error "$1: 未安装"
        return 1
    fi
}

check_environment() {
    print_step "检查系统环境..."
    echo -e "操作系统: $(uname -s) $(uname -m)"
    echo -e "系统版本: $(sw_vers 2>/dev/null || cat /etc/os-release 2>/dev/null | head -1 || echo "未知")"
    echo ""

    local missing=0

    # 必需工具
    echo -e "${BOLD}必需工具:${NC}"
    check_command python3 || { missing=$((missing + 1)); print_info "  安装方式: brew install python3 或 https://www.python.org/downloads/"; }
    check_command pip3 || { missing=$((missing + 1)); print_info "  安装方式: 随 Python3 一起安装"; }
    check_command git || { missing=$((missing + 1)); print_info "  安装方式: brew install git 或 xcode-select --install"; }

    echo ""
    echo -e "${BOLD}可选工具:${NC}"
    check_command docker && check_command docker-compose || check_command docker || print_info "  Docker: 未安装 (仅 Docker 部署需要)"
    check_command node || print_info "  Node.js: 未安装 (Dashboard 开发可选)"
    check_command appium || print_info "  Appium: 未安装 (移动端测试需要，安装: npm install -g appium)"

    echo ""
    if [[ $missing -gt 0 ]]; then
        print_warning "缺少 $missing 个必需工具，请先安装"
        return 1
    else
        print_success "所有必需工具已就绪"
        return 0
    fi
}

# ── 配置 .env 文件 ───────────────────────────────────────────

configure_env() {
    print_step "配置环境变量..."

    if [[ -f "$ENV_FILE" ]]; then
        print_success ".env 文件已存在"
        if ! ask_yes_no "是否重新配置?" "N"; then
            return 0
        fi
    fi

    # 从模板复制
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        print_info "已从 .env.example 复制配置模板"
    else
        print_warning ".env.example 不存在，将创建基础配置"
        touch "$ENV_FILE"
    fi

    echo ""
    echo -e "${BOLD}请填写以下关键配置（直接回车使用默认值）:${NC}"
    echo ""

    # LLM API Key
    read -rp "$(echo -e "${CYAN}LLM API Key${NC} (必填): ")" llm_api_key
    if [[ -n "$llm_api_key" ]]; then
        sed -i.bak "s|LLM_API_KEY=.*|LLM_API_KEY=${llm_api_key}|" "$ENV_FILE" 2>/dev/null || true
    else
        print_warning "未设置 LLM API Key，Agent 将无法调用 LLM"
    fi

    # LLM Model
    read -rp "$(echo -e "${CYAN}LLM 模型${NC} [gpt-4o]: ")" llm_model
    llm_model="${llm_model:-gpt-4o}"
    sed -i.bak "s|LLM_MODEL=.*|LLM_MODEL=${llm_model}|" "$ENV_FILE" 2>/dev/null || true

    # LLM Base URL
    read -rp "$(echo -e "${CYAN}LLM Base URL${NC} [https://api.openai.com/v1]: ")" llm_base_url
    llm_base_url="${llm_base_url:-https://api.openai.com/v1}"
    if grep -q "LLM_BASE_URL" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|LLM_BASE_URL=.*|LLM_BASE_URL=${llm_base_url}|" "$ENV_FILE" 2>/dev/null || true
    else
        echo "LLM_BASE_URL=${llm_base_url}" >> "$ENV_FILE"
    fi

    # Appium
    read -rp "$(echo -e "${CYAN}Appium 地址${NC} [http://127.0.0.1:4723]: ")" appium_url
    appium_url="${appium_url:-http://127.0.0.1:4723}"
    sed -i.bak "s|APPIUM_HOST=.*|APPIUM_HOST=$(echo "$appium_url" | sed 's|http://||' | cut -d: -f1)|" "$ENV_FILE" 2>/dev/null || true
    sed -i.bak "s|APPIUM_PORT=.*|APPIUM_PORT=$(echo "$appium_url" | sed 's|http://||' | cut -d: -f2)|" "$ENV_FILE" 2>/dev/null || true

    # 飞书 Webhook（可选）
    read -rp "$(echo -e "${CYAN}飞书 Webhook URL${NC} (可选，回车跳过): ")" feishu_webhook
    if [[ -n "$feishu_webhook" ]]; then
        if grep -q "FEISHU_WEBHOOK_URL" "$ENV_FILE" 2>/dev/null; then
            sed -i.bak "s|FEISHU_WEBHOOK_URL=.*|FEISHU_WEBHOOK_URL=${feishu_webhook}|" "$ENV_FILE" 2>/dev/null || true
        else
            echo "FEISHU_WEBHOOK_URL=${feishu_webhook}" >> "$ENV_FILE"
        fi
    fi

    # 清理备份文件
    rm -f "${ENV_FILE}.bak"

    print_success ".env 配置完成"
    echo ""
    print_info "配置文件位置: ${ENV_FILE}"
    print_info "后续可手动编辑该文件修改配置"
}

# ── 安装 Python 依赖 ─────────────────────────────────────────

install_dependencies() {
    print_step "安装 Python 依赖..."

    cd "$SCRIPT_DIR"

    # 创建虚拟环境
    if [[ ! -d "venv" ]]; then
        print_info "创建 Python 虚拟环境..."
        python3 -m venv venv
        print_success "虚拟环境已创建"
    else
        print_info "虚拟环境已存在，跳过创建"
    fi

    # 激活虚拟环境
    source venv/bin/activate
    print_info "已激活虚拟环境"

    # 安装依赖
    if [[ -f "requirements.txt" ]]; then
        print_info "安装 Python 依赖包（可能需要几分钟）..."
        pip install -r requirements.txt -q
        print_success "Python 依赖安装完成"
    elif [[ -f "pyproject.toml" ]]; then
        print_info "安装项目依赖..."
        pip install -e . -q
        print_success "项目依赖安装完成"
    else
        print_warning "未找到 requirements.txt 或 pyproject.toml"
    fi

    # 安装项目自身
    if [[ -f "setup.py" ]] || [[ -f "pyproject.toml" ]]; then
        pip install -e . -q 2>/dev/null || true
    fi
}

# ── 初始化设备配置 ────────────────────────────────────────────

init_device_config() {
    print_step "初始化设备配置..."

    local device_config="${SCRIPT_DIR}/src/config/devices.yaml"
    local device_config_dir
    device_config_dir="$(dirname "$device_config")"

    if [[ ! -d "$device_config_dir" ]]; then
        mkdir -p "$device_config_dir"
    fi

    if [[ -f "$device_config" ]]; then
        print_success "设备配置文件已存在: ${device_config}"
        return 0
    fi

    print_info "创建默认设备配置文件..."

    cat > "$device_config" << 'EOF'
# 设备池配置
# 根据实际设备修改以下配置

devices:
  - id: emulator-5554
    name: Android 模拟器
    platform: android
    udid: emulator-5554

  # - id: iphone-15
  #   name: iPhone 15
  #   platform: ios
  #   udid: A1B2C3D4-E5F6-7890-ABCD-EF1234567890
EOF

    print_success "设备配置文件已创建: ${device_config}"
    print_info "请根据实际设备修改该文件"
}

# ── 创建必要目录 ─────────────────────────────────────────────

create_directories() {
    print_step "创建必要目录..."

    mkdir -p "${SCRIPT_DIR}/reports"
    mkdir -p "${SCRIPT_DIR}/data/benchmarks"
    mkdir -p "${SCRIPT_DIR}/logs"

    print_success "目录结构已创建"
}

# ── Docker 部署 ──────────────────────────────────────────────

deploy_docker() {
    print_step "Docker 部署模式..."

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        print_error "Docker 未安装，请先安装 Docker Desktop"
        print_info "安装方式: https://www.docker.com/products/docker-desktop"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        print_error "Docker 未启动，请先启动 Docker Desktop"
        exit 1
    fi

    # 配置环境变量
    configure_env

    cd "$SCRIPT_DIR"

    # 构建并启动服务
    print_info "构建并启动 Docker 服务（首次可能需要几分钟）..."
    docker-compose up -d --build

    echo ""
    print_success "Docker 服务已启动"
    echo ""
    echo -e "${BOLD}服务地址:${NC}"
    echo -e "  MCP Server:      ${CYAN}http://localhost:8000${NC}"
    echo -e "  LangGraph Agent:  ${CYAN}http://localhost:8001${NC}"
    echo -e "  Redis:            ${CYAN}localhost:6379${NC}"
    echo -e "  PostgreSQL:       ${CYAN}localhost:5432${NC}"
    echo ""
    echo -e "${BOLD}常用命令:${NC}"
    echo -e "  查看服务状态:  ${CYAN}docker-compose ps${NC}"
    echo -e "  查看日志:      ${CYAN}docker-compose logs -f langgraph-agent${NC}"
    echo -e "  停止服务:      ${CYAN}docker-compose down${NC}"
    echo -e "  重启服务:      ${CYAN}docker-compose restart${NC}"
}

# ── 本地开发部署 ─────────────────────────────────────────────

deploy_local() {
    print_step "本地开发部署模式..."

    # 环境检查
    check_environment || exit 1

    # 配置环境变量
    configure_env

    # 安装依赖
    install_dependencies

    # 初始化设备配置
    init_device_config

    # 创建必要目录
    create_directories

    echo ""
    print_success "本地部署完成"
    echo ""
    echo -e "${BOLD}启动服务:${NC}"
    echo -e "  1. 激活虚拟环境:  ${CYAN}cd ${SCRIPT_DIR} && source venv/bin/activate${NC}"
    echo -e "  2. 启动 Agent:    ${CYAN}python -m src.main${NC}"
    echo -e "  3. 启动 Dashboard: ${CYAN}./deploy.sh --dashboard${NC}"
    echo ""
    echo -e "${BOLD}API 端点:${NC}"
    echo -e "  健康检查:    ${CYAN}curl http://localhost:8000/health${NC}"
    echo -e "  运行测试:    ${CYAN}curl -X POST http://localhost:8000/api/v1/tests/run -H 'Content-Type: application/json' -d '{\"app_description\": \"测试登录功能\"}'${NC}"
    echo -e "  查看设备:    ${CYAN}curl http://localhost:8000/api/v1/devices${NC}"
    echo -e "  查看报告:    ${CYAN}curl http://localhost:8000/api/v1/tests/{task_id}/report${NC}"
}

# ── 启动 Dashboard ───────────────────────────────────────────

start_dashboard() {
    print_step "启动 Dashboard 前端..."

    if [[ ! -d "$DASHBOARD_DIR" ]]; then
        print_error "Dashboard 目录不存在: ${DASHBOARD_DIR}"
        exit 1
    fi

    # 检查端口是否被占用
    local port=3000
    if lsof -i ":${port}" &>/dev/null; then
        print_warning "端口 ${port} 已被占用，尝试 3001..."
        port=3001
    fi

    print_info "Dashboard 启动在 http://localhost:${port}"
    print_info "按 Ctrl+C 停止服务"
    echo ""

    cd "$DASHBOARD_DIR"
    python3 -m http.server "$port"
}

# ── 健康检查 ─────────────────────────────────────────────────

health_check() {
    print_step "检查服务健康状态..."

    local agent_url="${1:-http://localhost:8000}"

    # 健康检查
    if curl -sf "${agent_url}/health" &>/dev/null; then
        local health
        health=$(curl -sf "${agent_url}/health")
        print_success "Agent 服务正常"
        echo -e "  ${health}" | python3 -m json.tool 2>/dev/null || echo -e "  ${health}"
    else
        print_error "Agent 服务未响应 (${agent_url})"
        print_info "请确认服务已启动: python -m src.main"
    fi

    # 设备列表
    echo ""
    if curl -sf "${agent_url}/api/v1/devices" &>/dev/null; then
        local devices
        devices=$(curl -sf "${agent_url}/api/v1/devices")
        local device_count
        device_count=$(echo "$devices" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        print_success "设备池: ${device_count} 台设备"
    else
        print_warning "无法获取设备列表"
    fi
}

# ── 交互式部署 ───────────────────────────────────────────────

interactive_deploy() {
    print_banner

    echo -e "${BOLD}欢迎使用 MobileAutomation 部署向导！${NC}"
    echo -e "本脚本将引导你完成系统的安装和配置。"
    echo ""

    # 环境检查
    if ! check_environment; then
        echo ""
        print_error "环境检查未通过，请先安装缺少的工具后重新运行。"
        exit 1
    fi

    echo ""
    echo -e "${BOLD}请选择部署方式:${NC}"
    echo -e "  ${CYAN}1${NC}) 本地开发部署（推荐新手）"
    echo -e "  ${CYAN}2${NC}) Docker 容器部署"
    echo -e "  ${CYAN}3${NC}) 仅启动 Dashboard 前端"
    echo -e "  ${CYAN}4${NC}) 检查服务健康状态"
    echo -e "  ${CYAN}5${NC}) 退出"
    echo ""

    read -rp "$(echo -e "${BOLD}请输入选项 [1-5]: ${NC}")" choice

    case "$choice" in
        1) deploy_local ;;
        2) deploy_docker ;;
        3) start_dashboard ;;
        4) health_check ;;
        5) echo -e "\n再见！"; exit 0 ;;
        *) print_error "无效选项"; exit 1 ;;
    esac
}

# ── 主入口 ────────────────────────────────────────────────────

main() {
    case "${1:-}" in
        --docker|-d)
            print_banner
            deploy_docker
            ;;
        --local|-l)
            print_banner
            deploy_local
            ;;
        --check|-c)
            print_banner
            check_environment
            ;;
        --health)
            print_banner
            health_check "${2:-http://localhost:8000}"
            ;;
        --dashboard)
            print_banner
            start_dashboard
            ;;
        --help|-h)
            print_banner
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  (无参数)        交互式部署（推荐）"
            echo "  --docker, -d    Docker 容器部署"
            echo "  --local,  -l    本地开发部署"
            echo "  --check,  -c    仅检查环境依赖"
            echo "  --health [URL]  检查服务健康状态"
            echo "  --dashboard     仅启动 Dashboard 前端"
            echo "  --help,   -h    显示帮助信息"
            ;;
        *)
            interactive_deploy
            ;;
    esac
}

main "$@"
