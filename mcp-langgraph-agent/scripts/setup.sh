#!/bin/bash
"""
环境初始化脚本

自动创建 Python 虚拟环境、安装项目依赖、配置环境变量和创建必要的目录结构。
在首次克隆项目或重置开发环境时执行此脚本。
"""

set -e  # 遇到错误立即退出

# 获取脚本所在目录的上级目录（项目根目录）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 颜色输出辅助函数
print_info() {
    echo -e "\033[34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

print_error() {
    echo -e "\033[31m[ERROR]\033[0m $1"
}

# 切换到项目根目录
cd "$PROJECT_DIR"

print_info "开始初始化项目环境..."

# 第1步：创建 Python 虚拟环境
print_info "正在创建 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "虚拟环境已创建: ./venv"
else
    print_info "虚拟环境已存在，跳过创建"
fi

# 激活虚拟环境
source venv/bin/activate

# 第2步：升级 pip 并安装项目依赖
print_info "正在安装项目依赖..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    print_success "项目依赖安装完成"
else
    print_info "requirements.txt 不存在，跳过依赖安装"
fi

# 第3步：复制环境变量配置文件
print_info "正在配置环境变量..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success "已从 .env.example 复制到 .env"
        print_info "请编辑 .env 文件填写必要的配置信息"
    else
        print_info ".env.example 不存在，跳过环境变量配置"
    fi
else
    print_info ".env 文件已存在，跳过"
fi

# 第4步：创建必要的目录结构
print_info "正在创建必要的目录..."
mkdir -p logs
mkdir -p reports
mkdir -p screenshots
mkdir -p data
print_success "目录创建完成"

# 第5步：设置脚本执行权限
print_info "正在设置脚本执行权限..."
chmod +x scripts/*.sh
print_success "脚本执行权限已设置"

print_success "项目环境初始化完成！"
echo ""
echo "下一步操作："
echo "  1. 编辑 .env 文件填写配置信息"
echo "  2. 运行 source venv/bin/activate 激活虚拟环境"
echo "  3. 运行 make dev 启动开发服务器"