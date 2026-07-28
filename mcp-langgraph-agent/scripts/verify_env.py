#!/usr/bin/env python3
"""
Phase 1 环境验证脚本

验证移动端自动化测试基础环境是否就绪，包括：
1. Python 版本与依赖包
2. Appium Server 连通性
3. Android SDK / iOS 开发环境
4. 设备连接状态
5. 启动 App 并获取 page_source 的能力

使用方式：
    source venv/bin/activate
    python scripts/verify_env.py
"""

# ruff: noqa: BLE001, PLW1510, S110

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


# 颜色输出辅助函数
def _red(text: str) -> str:
    """红色输出"""
    return f"\033[31m{text}\033[0m"

def _green(text: str) -> str:
    """绿色输出"""
    return f"\033[32m{text}\033[0m"

def _yellow(text: str) -> str:
    """黄色输出"""
    return f"\033[33m{text}\033[0m"

def _blue(text: str) -> str:
    """蓝色输出"""
    return f"\033[34m{text}\033[0m"

def _bold(text: str) -> str:
    """加粗输出"""
    return f"\033[1m{text}\033[0m"


# ============================================================
# 检查项目定义
# ============================================================

class CheckResult:
    """单项检查结果"""

    def __init__(self, name: str, passed: bool, message: str, detail: str = "") -> None:
        """初始化检查结果

        Args:
            name: 检查项名称
            passed: 是否通过
            message: 简要描述
            detail: 详细信息
        """
        self.name = name
        self.passed = passed
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        """格式化输出检查结果"""
        status = _green("PASS") if self.passed else _red("FAIL")
        line = f"  [{status}] {self.name}: {self.message}"
        if self.detail and not self.passed:
            line += f"\n         {self.detail}"
        return line


# ============================================================
# 系统环境检查
# ============================================================

def check_python_version() -> CheckResult:
    """检查 Python 版本是否满足要求（>=3.11）"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    passed = version.major >= 3 and version.minor >= 11
    if passed:
        return CheckResult("Python 版本", True, f"Python {version_str} (>=3.11)")
    else:
        return CheckResult(
            "Python 版本", False, f"Python {version_str} (<3.11)",
            "请安装 Python 3.11+：https://www.python.org/downloads/"
        )


def check_required_packages() -> list[CheckResult]:
    """检查项目必需的 Python 包是否已安装"""
    required_packages = [
        ("fastapi", "FastAPI Web 框架"),
        ("uvicorn", "ASGI 服务器"),
        ("pydantic", "数据验证库"),
        ("pydantic_settings", "Pydantic Settings 配置管理"),
        ("langgraph", "LangGraph 工作流框架"),
        ("langchain_core", "LangChain 核心模块"),
        ("mcp", "MCP 协议库"),
        ("httpx", "异步 HTTP 客户端"),
        ("appium", "Appium Python 客户端"),
        ("PIL", "Pillow 图片处理"),
        ("yaml", "PyYAML 配置解析"),
        ("redis", "Redis 客户端"),
        ("loguru", "日志库"),
        ("sqlalchemy", "SQLAlchemy 数据库 ORM"),
        ("prometheus_client", "Prometheus 监控客户端"),
    ]

    results: list[CheckResult] = []
    for pkg_name, description in required_packages:
        try:
            mod = importlib.import_module(pkg_name)
            version = getattr(mod, "__version__", "未知")
            results.append(CheckResult(pkg_name, True, f"{description} (v{version})"))
        except ImportError:
            results.append(CheckResult(
                pkg_name, False, f"{description} 未安装",
                "请运行: pip install -r requirements.txt"
            ))
    return results


def check_project_structure() -> CheckResult:
    """检查项目骨架目录结构是否完整"""
    project_dir = Path(__file__).parent.parent
    required_dirs = [
        "src", "src/agents", "src/config", "src/graph", "src/graph/nodes",
        "src/mobile_mcp", "src/mobile_mcp/tools", "src/models",
        "src/utils", "tests", "scripts",
    ]
    required_files = [
        "src/main.py", "src/config/settings.py", "src/mobile_mcp/server.py",
        "src/mobile_mcp/client.py", "src/mobile_mcp/tools/device.py",
        "src/mobile_mcp/tools/ui.py", "src/mobile_mcp/tools/vision.py",
        "src/mobile_mcp/tools/assertions.py", "src/graph/workflow.py",
        "src/graph/state.py", "src/agents/base.py", "src/agents/executor.py",
        "pyproject.toml", "requirements.txt", ".env.example",
    ]

    missing_dirs = [d for d in required_dirs if not (project_dir / d).is_dir()]
    missing_files = [f for f in required_files if not (project_dir / f).is_file()]

    if not missing_dirs and not missing_files:
        return CheckResult("项目骨架", True, f"目录({len(required_dirs)})和文件({len(required_files)})完整")
    else:
        details = []
        if missing_dirs:
            details.append(f"缺失目录: {missing_dirs}")
        if missing_files:
            details.append(f"缺失文件: {missing_files}")
        return CheckResult(
            "项目骨架", False, "项目结构不完整",
            "; ".join(details)
        )


def check_env_file() -> CheckResult:
    """检查 .env 配置文件是否存在"""
    project_dir = Path(__file__).parent.parent
    env_path = project_dir / ".env"

    if env_path.is_file():
        return CheckResult(".env 配置", True, ".env 文件已存在")
    else:
        return CheckResult(
            ".env 配置", False, ".env 文件不存在",
            "请运行: cp .env.example .env 并填写配置信息"
        )


# ============================================================
# Appium 与设备环境检查
# ============================================================

def check_appium_server() -> CheckResult:
    """检查 Appium Server 是否可用"""
    # 检查 appium 命令是否存在
    appium_path = shutil.which("appium")
    if appium_path:
        try:
            result = subprocess.run(
                ["appium", "--version"], capture_output=True, text=True, timeout=10
            )
            version = result.stdout.strip()
            return CheckResult("Appium Server", True, f"Appium v{version} 已安装")
        except Exception:
            return CheckResult("Appium Server", True, "Appium 已安装（版本未知）")

    # 检查 Appium 是否在 Docker 中运行
    try:
        import httpx
        response = httpx.get("http://127.0.0.1:4723/wd/hub/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            version = data.get("value", {}).get("build", {}).get("version", "未知")
            return CheckResult("Appium Server", True, f"Appium Server v{version} 正在运行")
    except Exception:
        pass

    # 检查 npm 是否可用（可安装 Appium）
    npm_path = shutil.which("npm")
    if npm_path:
        return CheckResult(
            "Appium Server", False, "Appium 未安装但 npm 可用",
            "请运行: npm install -g appium"
        )
    else:
        return CheckResult(
            "Appium Server", False, "Appium 未安装且 npm 不可用",
            "请先安装 Node.js: https://nodejs.org/ 然后运行: npm install -g appium"
        )


def check_android_sdk() -> CheckResult:
    """检查 Android SDK 是否已安装"""
    adb_path = shutil.which("adb")

    # 检查 ANDROID_HOME 环境变量
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not android_home:
        # 尝试常见路径
        common_paths = [
            Path.home() / "Library/Android/sdk",
            Path.home() / "Android/Sdk",
            Path("/usr/local/share/android-sdk"),
        ]
        for p in common_paths:
            if p.is_dir():
                android_home = str(p)
                break

    if adb_path:
        try:
            result = subprocess.run(
                ["adb", "version"], capture_output=True, text=True, timeout=10
            )
            version_line = result.stdout.strip().split('\n')[0]
            return CheckResult(
                "Android SDK", True,
                f"{version_line}" + (f" (ANDROID_HOME={android_home})" if android_home else "")
            )
        except Exception:
            return CheckResult("Android SDK", True, "adb 已安装")

    if android_home:
        return CheckResult(
            "Android SDK", False, "ANDROID_HOME 已配置但 adb 不可用",
            f"ANDROID_HOME={android_home}, 请检查 PATH 配置"
        )

    return CheckResult(
        "Android SDK", False, "Android SDK 未安装",
        "请安装 Android Studio 或 SDK Command Line Tools: https://developer.android.com/studio"
    )


def check_ios_env() -> CheckResult:
    """检查 iOS 开发环境是否可用"""
    xcodebuild_path = shutil.which("xcodebuild")
    if not xcodebuild_path:
        return CheckResult("iOS 环境", False, "Xcode 未安装", "请安装 Xcode: https://developer.apple.com/xcode/")

    try:
        result = subprocess.run(
            ["xcodebuild", "-version"], capture_output=True, text=True, timeout=10
        )
        version_info = result.stdout.strip().split('\n')[0]
        return CheckResult("iOS 环境", True, f"Xcode {version_info}")
    except Exception:
        return CheckResult("iOS 环境", True, "Xcode 已安装")


def check_connected_devices() -> CheckResult:
    """检查是否有 Android/iOS 设备或模拟器已连接"""
    adb_path = shutil.which("adb")
    connected_devices: list[str] = []

    # Android 设备
    if adb_path:
        try:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                if "device" in line and "List of devices" not in line:
                    device_id = line.split()[0]
                    connected_devices.append(f"Android: {device_id}")
        except Exception:
            pass

    # iOS 模拟器
    xcrun_path = shutil.which("xcrun")
    if xcrun_path:
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "booted"],
                capture_output=True, text=True, timeout=10
            )
            booted = result.stdout.strip()
            if "Booted" in booted and len(booted.split('\n')) > 1:
                for line in booted.split('\n'):
                    if "Booted" in line and "(" in line:
                        connected_devices.append(f"iOS Simulator: {line.strip()}")
        except Exception:
            pass

    if connected_devices:
        return CheckResult("设备连接", True, f"已连接 {len(connected_devices)} 台设备: {connected_devices}")
    else:
        return CheckResult(
            "设备连接", False, "无已连接的设备",
            "请启动 Android 模拟器 (adb) 或 iOS 模拟器 (xcrun simctl boot)"
        )


# ============================================================
# 功能验证：启动 App 并获取 page_source
# ============================================================

def verify_appium_connect_and_get_source() -> CheckResult:
    """验证能否通过 Appium 连接设备并获取 page_source

    这是 Phase 1 的核心交付物验证。
    尝试连接 Appium Server，创建 WebDriver 会话，获取 page_source。
    """
    try:
        from appium import webdriver
        from appium.options.android import UiAutomator2Options

        from src.config.settings import settings
    except ImportError as e:
        return CheckResult(
            "Appium page_source", False, f"依赖未安装: {e}",
            "请运行: pip install -r requirements.txt"
        )

    appium_url = f"http://{settings.APPIUM_HOST}:{settings.APPIUM_PORT}{settings.APPIUM_BASE_PATH}"

    # 尝试连接 Appium Server
    try:
        import httpx
        response = httpx.get(f"{appium_url}/status", timeout=5)
        if response.status_code != 200:
            return CheckResult(
                "Appium page_source", False, "Appium Server 未运行",
                f"请启动 Appium Server: appium --address {settings.APPIUM_HOST} --port {settings.APPIUM_PORT}"
            )
    except Exception:
        return CheckResult(
            "Appium page_source", False, "Appium Server 不可达",
            f"请启动 Appium Server 或检查配置: {appium_url}"
        )

    # 检查设备配置
    devices_yaml_path = Path(__file__).parent.parent / settings.DEVICE_CONFIG_PATH
    if not devices_yaml_path.is_file():
        return CheckResult(
            "Appium page_source", False, "设备配置文件不存在",
            f"请创建: {settings.DEVICE_CONFIG_PATH}"
        )

    # 尝试创建 WebDriver 会话（需要设备连接）
    # 查找第一个可用的 Android 设备
    adb_path = shutil.which("adb")
    if not adb_path:
        return CheckResult(
            "Appium page_source", False, "adb 不可用，无法自动检测设备",
            "请安装 Android SDK 并启动模拟器"
        )

    try:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')
        device_id = None
        for line in lines[1:]:
            if "device" in line and "List of devices" not in line:
                device_id = line.split()[0]
                break

        if not device_id:
            return CheckResult(
                "Appium page_source", False, "无已连接的 Android 设备",
                "请启动模拟器: emulator -avd <name> 或连接真机"
            )

        # 尝试获取 page_source（使用最简单的配置）
        options = UiAutomator2Options()
        options.device_name = device_id
        options.udid = device_id
        options.set_capability("noReset", True)
        options.set_capability("newCommandTimeout", 60)
        # 不指定 appPackage/appActivity，使用当前前台应用
        options.set_capability("skipDeviceInitialization", True)
        options.set_capability("skipServerInstallation", True)

        driver = webdriver.Remote(command_executor=appium_url, options=options)
        page_source = driver.page_source

        # 获取截图验证
        screenshot_b64 = driver.get_screenshot_as_base64()

        driver.quit()

        source_size = len(page_source)
        screenshot_size = len(screenshot_b64)

        return CheckResult(
            "Appium page_source", True,
            f"成功获取 page_source ({source_size} bytes) 和截图 ({screenshot_size} bytes)",
            f"设备: {device_id}, page_source 前100字符: {page_source[:100]}"
        )

    except Exception as e:
        return CheckResult(
            "Appium page_source", False, f"获取 page_source 失败: {e}",
            "请确认 Appium Server 已启动且设备已连接"
        )


# ============================================================
# MCP Server 基础功能验证
# ============================================================

def verify_mcp_server_creation() -> CheckResult:
    """验证 MCP Server 能否正常创建和初始化"""
    try:
        from src.mobile_mcp.server import create_server
        server = create_server()
        tool_names = server.get_registered_tool_names()
        expected_tools = [
            "connect_device", "disconnect_device", "get_device_info", "list_devices",
            "tap_element", "tap_by_text", "input_text", "swipe",
            "long_press", "press_key", "scroll", "wait_for_element",
            "take_screenshot", "get_ui_tree",
            "assert_text_visible", "assert_element_exists", "assert_page_contains",
        ]
        registered_count = len(tool_names)
        missing_tools = [t for t in expected_tools if t not in tool_names]

        if missing_tools:
            return CheckResult(
                "MCP Server", False,
                f"已注册 {registered_count} 个工具，缺少: {missing_tools}",
                "请检查 src/mobile_mcp/server.py 的工具注册逻辑"
            )
        else:
            return CheckResult(
                "MCP Server", True,
                f"已注册 {registered_count} 个工具，包含所有预期工具"
            )
    except Exception as e:
        return CheckResult(
            "MCP Server", False, f"MCP Server 创建失败: {e}",
            "请检查依赖安装和代码配置"
        )


def verify_langgraph_workflow() -> CheckResult:
    """验证 LangGraph 工作流能否正常构建和编译"""
    try:
        from src.graph.workflow import build_workflow
        app = build_workflow()
        return CheckResult(
            "LangGraph Workflow", True,
            f"工作流构建成功，节点: {list(app.nodes.keys()) if hasattr(app, 'nodes') else '已编译'}"
        )
    except Exception as e:
        return CheckResult(
            "LangGraph Workflow", False, f"工作流构建失败: {e}",
            "请检查 src/graph/ 模块代码"
        )


def verify_config_loading() -> CheckResult:
    """验证配置模块能否正常加载"""
    try:
        from src.config.settings import settings
        return CheckResult(
            "配置模块", True,
            f"APP_NAME={settings.APP_NAME}, VERSION={settings.APP_VERSION}, "
            f"APPIUM={settings.APPIUM_HOST}:{settings.APPIUM_PORT}"
        )
    except Exception as e:
        return CheckResult(
            "配置模块", False, f"配置加载失败: {e}",
            "请检查 .env 文件和 src/config/settings.py"
        )


def verify_utils_modules() -> CheckResult:
    """验证工具模块能否正常加载"""
    try:
        from src.utils.redact import redact_sensitive
        from src.utils.screenshot import (
            compress_screenshot,  # noqa: F401 - 验证模块可导入
        )
        from src.utils.token_tracker import TokenTracker
        from src.utils.xml_compressor import compress_xml

        # 测试 XML 压缩（使用足够大的 XML 确保压缩生效）
        test_xml = '<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]"><node class="android.widget.LinearLayout" bounds="[0,0][1080,2400]"><node class="android.widget.Button" text="Login" bounds="[0,0][100,50]" clickable="true" enabled="true"/><node class="android.widget.EditText" text="" bounds="[100,0][500,50]" clickable="true" enabled="true" resource-id="com.example:id/username"/><node class="android.widget.TextView" text="Hello World" bounds="[0,100][1080,200]"/></node></node></hierarchy>'
        compressed = compress_xml(test_xml)
        # 验证压缩后是有效的 JSON
        import json as _json
        parsed = _json.loads(compressed)
        assert "compressed_tree" in parsed, "压缩结果应包含 compressed_tree 字段"

        # 测试脱敏
        redacted = redact_sensitive("password: my_secret_pwd")
        assert "secret" not in redacted, "脱敏应隐藏密码"

        # 测试 Token Tracker
        tracker = TokenTracker()
        tracker.add_record("gpt-4o", "precise", 100, 50, "test")
        summary = tracker.get_summary()
        assert summary["total_tokens"] == 150, "Token 统计应正确"

        return CheckResult("工具模块", True, "XML压缩/截图/脱敏/Token追踪模块均正常")
    except Exception as e:
        return CheckResult(
            "工具模块", False, f"工具模块验证失败: {e}",
            "请检查 src/utils/ 模块代码"
        )


# ============================================================
# 主验证流程
# ============================================================

def run_all_checks() -> dict[str, list[CheckResult]]:
    """运行所有环境验证检查

    Returns:
        按分类组织的检查结果字典
    """
    categories: dict[str, list[CheckResult]] = {}

    # ── Python 环境 ──
    categories["Python 环境"] = [
        check_python_version(),
        *check_required_packages(),
    ]

    # ── 项目结构 ──
    categories["项目结构"] = [
        check_project_structure(),
        check_env_file(),
    ]

    # ── 外部环境 ──
    categories["外部环境"] = [
        check_appium_server(),
        check_android_sdk(),
        check_ios_env(),
        check_connected_devices(),
    ]

    # ── 模块功能 ──
    categories["模块功能"] = [
        verify_config_loading(),
        verify_mcp_server_creation(),
        verify_langgraph_workflow(),
        verify_utils_modules(),
    ]

    # ── 交付物验证 ──
    categories["交付物验证"] = [
        verify_appium_connect_and_get_source(),
    ]

    return categories


def print_report(categories: dict[str, list[CheckResult]]) -> tuple[int, int]:
    """打印验证报告

    Args:
        categories: 检查结果分类字典

    Returns:
        (通过数, 失败数) 的元组
    """
    total_passed = 0
    total_failed = 0

    print(_bold("\n" + "=" * 70))
    print(_bold("  Phase 1 基础环境验证报告"))
    print(_bold("  mcp-langgraph-agent v0.1.0"))
    print(_bold("=" * 70 + "\n"))

    for category, results in categories.items():
        print(_blue(f"\n── {category} ──"))
        for result in results:
            print(result)
            if result.passed:
                total_passed += 1
            else:
                total_failed += 1

    print(_bold("\n" + "=" * 70))
    print(_bold(f"  总计: {total_passed + total_failed} 项检查"))
    print(_green(f"  通过: {total_passed}"))
    print(_red(f"  失败: {total_failed}"))

    if total_failed == 0:
        print(_green(_bold("\n  ALL CHECKS PASSED - Phase 1 基础环境就绪!")))
    else:
        print(_yellow(_bold(f"\n  {total_failed} 项检查未通过，请按提示修复后重试")))
    print(_bold("=" * 70 + "\n"))

    return total_passed, total_failed


def save_report_json(categories: dict[str, list[CheckResult]]) -> None:
    """将验证报告保存为 JSON 文件

    Args:
        categories: 检查结果分类字典
    """
    report_dir = Path(__file__).parent.parent / "reports"
    report_dir.mkdir(exist_ok=True)

    report_data = {}
    for category, results in categories.items():
        report_data[category] = [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "detail": r.detail,
            }
            for r in results
        ]

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"env_verify_{timestamp}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"验证报告已保存到: {report_path}")


def main() -> None:
    """验证脚本主入口"""
    # 添加项目根目录到 Python 路径
    project_dir = str(Path(__file__).parent.parent)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    # 运行所有检查
    categories = run_all_checks()

    # 打印报告
    passed, failed = print_report(categories)

    # 保存 JSON 报告
    save_report_json(categories)

    # 返回退出码
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
