#!/bin/bash
# 测试运行脚本
#
# 支持按设备、测试文件、测试用例和报告生成方式运行自动化测试。
# 提供命令行参数解析，灵活控制测试执行流程。

set -e  # 遇到错误立即退出

# 获取脚本所在目录的上级目录（项目根目录）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 默认参数值
DEVICE=""
TEST_FILE=""
TEST_CASE=""
REPORT_DIR="reports"

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

# 显示使用帮助
print_usage() {
    echo "用法: $0 [选项]"
    echo "选项:"
    echo "  --device <id>      指定测试设备 ID（必填）"
    echo "  --test-file <path> 指定测试文件路径"
    echo "  --test-case <id>   指定测试用例 ID"
    echo "  --report <dir>     指定报告输出目录（默认: reports）"
    echo "  -h, --help         显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 --device emulator-5554"
    echo "  $0 --device emulator-5554 --test-file tests/test_login.py"
    echo "  $0 --device emulator-5554 --test-case test_login_success --report ./custom_reports"
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --device)
                DEVICE="$2"
                shift 2
                ;;
            --test-file)
                TEST_FILE="$2"
                shift 2
                ;;
            --test-case)
                TEST_CASE="$2"
                shift 2
                ;;
            --report)
                REPORT_DIR="$2"
                shift 2
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                print_usage
                exit 1
                ;;
        esac
    done
}

# 检查环境变量
check_env() {
    # 检查是否在虚拟环境中
    if [ -z "$VIRTUAL_ENV" ]; then
        if [ -d "$PROJECT_DIR/venv" ]; then
            print_info "激活虚拟环境..."
            source "$PROJECT_DIR/venv/bin/activate"
        else
            print_error "未找到虚拟环境，请先运行 scripts/setup.sh"
            exit 1
        fi
    fi

    # 检查必要的环境变量
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_error "未找到 .env 文件，请先运行 scripts/setup.sh"
        exit 1
    fi

    # 加载环境变量
    source "$PROJECT_DIR/.env" 2>/dev/null || true
}

# 运行测试
run_tests() {
    print_info "开始运行测试..."
    print_info "设备: $DEVICE"
    print_info "测试文件: ${TEST_FILE:-全部}"
    print_info "测试用例: ${TEST_CASE:-全部}"
    print_info "报告目录: $REPORT_DIR"

    # 创建报告输出目录
    mkdir -p "$PROJECT_DIR/$REPORT_DIR"

    # 切换到项目根目录
    cd "$PROJECT_DIR"

    # 构建 pytest 命令
    PYTEST_CMD="pytest tests/ -v"

    # 添加设备参数
    if [ -n "$DEVICE" ]; then
        PYTEST_CMD="$PYTEST_CMD --device=$DEVICE"
    fi

    # 添加测试文件过滤
    if [ -n "$TEST_FILE" ]; then
        PYTEST_CMD="pytest $TEST_FILE -v"
    fi

    # 添加测试用例过滤
    if [ -n "$TEST_CASE" ]; then
        PYTEST_CMD="$PYTEST_CMD -k $TEST_CASE"
    fi

    # 添加报告输出
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    REPORT_FILE="$PROJECT_DIR/$REPORT_DIR/test_report_$TIMESTAMP.html"
    PYTEST_CMD="$PYTEST_CMD --html=$REPORT_FILE --self-contained-html"

    print_info "执行命令: $PYTEST_CMD"

    # 执行测试
    if eval "$PYTEST_CMD"; then
        print_success "测试执行完成！"
        print_success "测试报告: $REPORT_FILE"
        return 0
    else
        print_error "测试执行失败，请查看报告了解详情"
        print_error "测试报告: $REPORT_FILE"
        return 1
    fi
}

# 主函数
main() {
    parse_args "$@"

    # 验证必填参数
    if [ -z "$DEVICE" ]; then
        print_error "缺少必填参数: --device"
        print_usage
        exit 1
    fi

    # 检查环境
    check_env

    # 运行测试
    run_tests
}

# 执行主函数
main "$@"