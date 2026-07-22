#!/bin/bash
# =============================================================================
# Phase 1 环境初始化脚本
#
# 自动完成移动端自动化测试基础环境的搭建，包括：
# 1. Python 虚拟环境创建与依赖安装
# 2. Node.js / Appium Server 检查与安装
# 3. Android SDK / iOS 开发环境检查
# 4. 项目配置文件初始化
# 5. 环境验证
#
# 使用方式：
#   chmod +x scripts/setup.sh && ./scripts/setup.sh
# =============================================================================

set -e  # 遇到错误立即退出

# 获取脚本所在目录的上级目录（项目根目录）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── 颜色输出辅助函数 ──────────────────────────────────────────────────

print_info()    { echo -e "\033[34m[INFO]\033[0m $1"; }
print_success() { echo -e "\033[32m[PASS]\033[0m $1"; }
print_error()   { echo -e "\033[31m[FAIL]\033[0m $1"; }
print_warn()    { echo -e "\033[33m[WARN]\033[0m $1"; }
print_step()    { echo -e "\033[1m\033[36m==== $1 ====\033[0m"; }

# 切换到项目根目录
cd "$PROJECT_DIR"

echo ""
echo "============================================"
echo "  Phase 1: 基础环境搭建"
echo "  mcp-langgraph-agent v0.1.0"
echo "============================================"
echo ""

# ══════════════════════════════════════════════════════════════════════
# 第1步：Python 虚拟环境与依赖
# ══════════════════════════════════════════════════════════════════════
print_step "第1步：Python 虚拟环境与依赖安装"

# 检测可用的 Python 版本（优先 3.13 > 3.12 > 3.11）
PYTHON_CMD=""
for py in python3.13 python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        PY_VERSION=$($py --version 2>&1 | sed 's/Python //')
        PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
            PYTHON_CMD="$py"
            print_success "找到 Python $PY_VERSION ($py)"
            break
        else
            print_warn "Python $PY_VERSION 版本过低（需要 >=3.11），跳过"
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    print_error "未找到 Python 3.11+，请安装后重试"
    echo "  macOS: https://www.python.org/downloads/ 或 brew install python@3.13"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    print_info "使用 $PYTHON_CMD 创建虚拟环境..."
    $PYTHON_CMD -m venv venv
    print_success "虚拟环境已创建: ./venv"
else
    print_info "虚拟环境已存在，跳过创建"
fi

# 激活虚拟环境
source venv/bin/activate

# 升级 pip 并安装依赖
print_info "升级 pip 并安装项目依赖..."
pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>/dev/null || \
pip install --upgrade pip 2>/dev/null

if [ -f "requirements.txt" ]; then
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt 2>/dev/null || \
    pip install -r requirements.txt
    print_success "项目依赖安装完成"
else
    print_warn "requirements.txt 不存在，跳过依赖安装"
fi

# 安装开发模式
if [ -f "pyproject.toml" ]; then
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e ".[dev]" 2>/dev/null || \
    pip install -e ".[dev]" 2>/dev/null
    print_success "项目已以开发模式安装"
fi

# ══════════════════════════════════════════════════════════════════════
# 第2步：Node.js 与 Appium Server
# ══════════════════════════════════════════════════════════════════════
print_step "第2步：Node.js 与 Appium Server 检查"

# 检查 Node.js
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js $NODE_VERSION 已安装"
else
    print_warn "Node.js 未安装"
    echo "  请安装 Node.js (LTS): https://nodejs.org/"
    echo "  或使用 nvm: curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
    echo "  安装后请重新运行此脚本"
fi

# 检查 Appium
if command -v appium &>/dev/null; then
    APPIUM_VERSION=$(appium --version 2>/dev/null || echo "未知")
    print_success "Appium v$APPIUM_VERSION 已安装"
else
    if command -v npm &>/dev/null; then
        print_info "正在安装 Appium Server..."
        npm install -g appium
        # 安装 UiAutomator2 驱动（Android）
        appium driver install uiautomator2 2>/dev/null || true
        # 安装 XCUITest 驱动（iOS）
        appium driver install xcuitest 2>/dev/null || true
        print_success "Appium Server 及驱动已安装"
    else
        print_warn "Appium 未安装且 npm 不可用"
        echo "  请先安装 Node.js，然后运行: npm install -g appium"
        echo "  安装驱动: appium driver install uiautomator2 && appium driver install xcuitest"
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# 第3步：Android SDK / iOS 开发环境
# ══════════════════════════════════════════════════════════════════════
print_step "第3步：移动端开发环境检查"

# Android SDK 检查
if command -v adb &>/dev/null; then
    ADB_VERSION=$(adb version 2>/dev/null | head -1)
    print_success "Android SDK: $ADB_VERSION"

    # 检查连接的设备
    DEVICE_COUNT=$(adb devices 2>/dev/null | grep -c "device$" || echo "0")
    if [ "$DEVICE_COUNT" -gt 0 ]; then
        print_success "已连接 $DEVICE_COUNT 台 Android 设备/模拟器"
    else
        print_warn "无 Android 设备连接"
        echo "  启动模拟器: emulator -avd <avd_name>"
        echo "  查看可用 AVD: emulator -list-avds"
    fi
else
    # 检查常见 Android SDK 路径
    if [ -d "$HOME/Library/Android/sdk" ]; then
        print_warn "Android SDK 已安装但 adb 不在 PATH 中"
        echo "  请添加到 ~/.zshrc 或 ~/.bash_profile:"
        echo "    export ANDROID_HOME=\$HOME/Library/Android/sdk"
        echo "    export PATH=\$PATH:\$ANDROID_HOME/platform-tools:\$ANDROID_HOME/emulator"
    else
        print_warn "Android SDK 未安装"
        echo "  请安装 Android Studio: https://developer.android.com/studio"
        echo "  或仅安装 SDK Command Line Tools: https://developer.android.com/studio#command-line-tools-only"
    fi
fi

# iOS 开发环境检查
if command -v xcodebuild &>/dev/null; then
    XCODE_VERSION=$(xcodebuild -version 2>/dev/null | head -1)
    print_success "iOS 环境: $XCODE_VERSION"

    # 检查已启动的 iOS 模拟器
    if command -v xcrun &>/dev/null; then
        BOOTED_SIMS=$(xcrun simctl list devices booted 2>/dev/null | grep -c "Booted" || echo "0")
        if [ "$BOOTED_SIMS" -gt 0 ]; then
            print_success "已启动 $BOOTED_SIMS 台 iOS 模拟器"
        else
            print_warn "无 iOS 模拟器启动"
            echo "  启动模拟器: xcrun simctl boot 'iPhone 15'"
            echo "  打开模拟器 UI: open -a Simulator"
        fi
    fi
else
    print_warn "Xcode 未安装（iOS 测试不可用）"
    echo "  请安装 Xcode: https://developer.apple.com/xcode/"
fi

# ══════════════════════════════════════════════════════════════════════
# 第4步：项目配置初始化
# ══════════════════════════════════════════════════════════════════════
print_step "第4步：项目配置初始化"

# 复制 .env 配置文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success "已从 .env.example 复制到 .env"
        print_info "请编辑 .env 文件填写 LLM_API_KEY 等配置信息"
    else
        print_warn ".env.example 不存在，跳过环境变量配置"
    fi
else
    print_info ".env 文件已存在，跳过"
fi

# 创建必要的目录结构
print_info "创建必要的目录..."
mkdir -p logs
mkdir -p reports
mkdir -p screenshots
mkdir -p data
print_success "目录创建完成 (logs/ reports/ screenshots/ data/)"

# 设置脚本执行权限
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

# ══════════════════════════════════════════════════════════════════════
# 第5步：环境验证
# ══════════════════════════════════════════════════════════════════════
print_step "第5步：环境验证"

print_info "运行环境验证脚本..."
if [ -f "scripts/verify_env.py" ]; then
    python scripts/verify_env.py || true
else
    print_warn "verify_env.py 不存在，跳过环境验证"
fi

# ══════════════════════════════════════════════════════════════════════
# 完成
# ══════════════════════════════════════════════════════════════════════
echo ""
print_success "Phase 1 基础环境搭建完成！"
echo ""
echo "下一步操作："
echo "  1. 编辑 .env 文件填写 LLM_API_KEY 等配置"
echo "  2. 启动 Appium Server: appium --address 127.0.0.1 --port 4723"
echo "  3. 启动 Android 模拟器或连接真机"
echo "  4. 运行环境验证: python scripts/verify_env.py"
echo "  5. 启动开发服务器: make dev"
echo ""
