"""
设备管理工具模块

提供设备连接、断开和基本信息查询功能。
使用 appium-python-client 的 WebDriver 管理设备连接，
并通过线程安全机制维护连接池。支持 Android 和 iOS 设备，
可从 YAML 配置文件预加载设备参数。
"""

import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.request import urlopen
from urllib.error import URLError

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.common import AppiumOptions
from appium.webdriver.appium_service import AppiumService
from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)


@dataclass
class DeviceConfig:
    """设备预配置信息。

    存储从配置文件加载的设备连接参数，在建立 Appium 连接时使用。

    Attributes:
        device_id: 设备唯一标识（对应配置文件中的 name）。
        name: 设备名称。
        platform: 平台类型（Android/iOS）。
        udid: 设备 UDID。
        system_port: Android 系统调试端口。
        wda_port: iOS WebDriverAgent 端口。
        app_package: Android 包名 或 iOS bundle ID。
        app_activity: Android 启动 Activity。
        appium_port: Appium Server 端口。
        capabilities: 额外的 Appium Capabilities（来自配置文件）。
    """

    device_id: str
    name: str = ""
    platform: str = "Android"
    udid: str = ""
    system_port: int = 8200
    wda_port: int = 8100
    app_package: str = ""
    app_activity: str = ""
    appium_port: int = 4723
    capabilities: Optional[Dict] = None


class DeviceManager:
    """设备管理器，负责 Appium 设备连接的生命周期管理。

    维护一个线程安全的设备连接池，支持多设备并发连接。
    提供设备的连接、断开和基本信息查询功能。
    支持从配置文件预加载设备参数，自动构建正确的 Desired Capabilities。
    """

    def __init__(self, appium_url: str = "http://localhost:4723") -> None:
        """初始化设备管理器，创建连接池和线程锁。

        Args:
            appium_url: Appium Server 地址，默认为 "http://localhost:4723"。
        """
        # 设备连接池，key 为设备名称，value 为 WebDriver 实例
        self._connections: Dict[str, WebDriver] = {}
        # 线程锁，保证连接池操作的线程安全
        self._lock = threading.Lock()
        # Appium 服务实例（可选，用于自动启动 Appium）
        self._appium_service: Optional[AppiumService] = None
        # Appium Server 地址
        self._appium_url = appium_url
        # 设备预配置表，key 为 device_id，value 为 DeviceConfig
        self._device_configs: Dict[str, DeviceConfig] = {}
        # 标记 Appium Server 是否已启动（本次进程内）
        self._appium_started: bool = False

    def _is_appium_running(self) -> bool:
        """检查 Appium Server 是否已在运行。

        通过尝试访问 Appium 的 status 端点判断服务是否可用。

        Returns:
            Appium Server 是否可达。
        """
        try:
            status_url = f"{self._appium_url}/status"
            with urlopen(status_url, timeout=3) as resp:
                return resp.status == 200
        except (URLError, OSError):
            return False

    @staticmethod
    def _get_appium_home() -> str:
        """获取 APPIUM_HOME 路径。

        优先使用环境变量中已有的 APPIUM_HOME，否则基于项目根目录推导。
        驱动也安装在此路径下，确保 Appium Server 能找到已安装的驱动。

        Returns:
            APPIUM_HOME 的绝对路径。
        """
        # 如果环境变量已设置，直接使用
        existing = os.environ.get("APPIUM_HOME")
        if existing and os.path.isdir(existing):
            return existing

        # 基于当前文件位置推导项目根目录
        # 文件路径: <project_root>/mcp-langgraph-agent/src/mobile_mcp/tools/device.py
        # 需要上溯 4 级到达 MobileAutomation/ 目录
        this_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(this_dir)))
        )
        candidate = os.path.join(project_root, ".appium_home")

        # 如果候选路径不存在驱动，检查上级目录（兼容不同的 cwd 场景）
        if not os.path.exists(os.path.join(candidate, "node_modules")):
            parent_candidate = os.path.join(os.path.dirname(project_root), ".appium_home")
            if os.path.exists(os.path.join(parent_candidate, "node_modules")):
                return parent_candidate

        return candidate

    @staticmethod
    def _ensure_android_env() -> None:
        """确保 ANDROID_HOME 和 ANDROID_SDK_ROOT 环境变量已设置。

        UIAutomator2 驱动要求这两个变量之一存在才能定位 Android SDK。
        如果未设置，自动检测 macOS 常见的 SDK 安装路径并注入环境变量。
        """
        if os.environ.get("ANDROID_HOME") and os.environ.get("ANDROID_SDK_ROOT"):
            return

        # 常见 macOS Android SDK 路径
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Library", "Android", "sdk"),
            os.path.join(home, "Android", "Sdk"),
            "/usr/local/share/android-sdk",
        ]

        sdk_path = None
        for path in candidates:
            if os.path.isdir(path):
                sdk_path = path
                break

        if sdk_path:
            os.environ.setdefault("ANDROID_HOME", sdk_path)
            os.environ.setdefault("ANDROID_SDK_ROOT", sdk_path)
            logger.info("ANDROID_HOME 已设置为: %s", sdk_path)
        else:
            logger.warning(
                "未找到 Android SDK，请设置 ANDROID_HOME 环境变量。"
                "常见路径: ~/Library/Android/sdk"
            )

    def _start_appium_server(self) -> bool:
        """自动启动 Appium Server。

        优先使用 AppiumService（appium-python-client 内置）启动，
        如果失败则回退到子进程方式。启动后等待最多 15 秒确认服务就绪。

        Returns:
            Appium Server 是否启动成功。
        """
        if self._appium_started:
            return True

        # 统一计算 APPIUM_HOME 路径，确保驱动目录一致
        appium_home = self._get_appium_home()
        os.makedirs(appium_home, exist_ok=True)
        os.environ["APPIUM_HOME"] = appium_home
        logger.info("APPIUM_HOME 设置为: %s", appium_home)

        # 方式 1：使用 AppiumService（需要 appium npm 包已安装）
        try:
            self._appium_service = AppiumService()
            self._appium_service.start(
                args=[
                    "--address", "127.0.0.1",
                    "--port", "4723",
                    "--base-path", "/wd/hub",
                ],
                timeout_ms=15000,
                env=os.environ.copy(),
            )
            if self._appium_service.is_running:
                logger.info("Appium Server 已通过 AppiumService 启动")
                self._appium_started = True
                return True
        except Exception as e:
            logger.warning("AppiumService 启动失败: %s，尝试子进程方式", e)

        # 方式 2：子进程方式启动
        try:
            env = os.environ.copy()
            proc = subprocess.Popen(
                ["appium", "--address", "127.0.0.1", "--port", "4723", "--base-path", "/wd/hub"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            # 等待 Appium 启动
            import time
            for _ in range(15):
                time.sleep(1)
                if self._is_appium_running():
                    logger.info("Appium Server 已通过子进程启动 (PID=%d)", proc.pid)
                    self._appium_started = True
                    return True

            logger.error("Appium Server 子进程启动超时")
            return False
        except FileNotFoundError:
            logger.error("未找到 appium 命令，请确保已安装: npm install -g appium")
            return False
        except Exception as e:
            logger.error("Appium Server 子进程启动失败: %s", e)
            return False

    def register_device_config(
        self,
        device_id: str,
        name: str = "",
        platform: str = "Android",
        udid: str = "",
        system_port: int = 8200,
        wda_port: int = 8100,
        app_package: str = "",
        app_activity: str = "",
        appium_port: int = 4723,
        capabilities: Optional[Dict] = None,
    ) -> None:
        """注册设备预配置信息。

        将设备连接参数保存到预配置表中，后续调用 connect_device 时
        可自动从配置中获取连接参数，无需手动指定。

        Args:
            device_id: 设备唯一标识。
            name: 设备名称。
            platform: 平台类型（Android/iOS）。
            udid: 设备 UDID。
            system_port: Android 系统调试端口。
            wda_port: iOS WebDriverAgent 端口。
            app_package: Android 包名 或 iOS bundle ID。
            app_activity: Android 启动 Activity。
            appium_port: Appium Server 端口。
            capabilities: 额外的 Appium Capabilities 字典。
        """
        config = DeviceConfig(
            device_id=device_id,
            name=name,
            platform=platform,
            udid=udid or device_id,
            system_port=system_port,
            wda_port=wda_port,
            app_package=app_package,
            app_activity=app_activity,
            appium_port=appium_port,
            capabilities=capabilities,
        )
        self._device_configs[device_id] = config
        logger.debug("注册设备配置: %s (%s)", device_id, platform)

    def _build_capabilities(self, device_name: str) -> AppiumOptions:
        """根据设备名称和预配置构建 Appium Desired Capabilities。

        优先从预配置表中获取参数，如果找不到则使用默认 Android 配置。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            AppiumOptions: 构建好的 Appium 连接选项。
        """
        config = self._device_configs.get(device_name)

        if config and config.platform.lower() == "ios":
            # iOS 设备配置
            options = AppiumOptions()
            options.platform_name = "iOS"
            options.device_name = config.name or device_name
            options.udid = config.udid or device_name
            options.automation_name = "XCUITest"
            # 注入配置文件中的 capabilities
            if config.capabilities:
                for k, v in config.capabilities.items():
                    options.set_capability(k, v)
            options.set_capability("noReset", True)
            options.set_capability("newCommandTimeout", 300)
            options.set_capability("wdaLocalPort", config.wda_port)
            return options
        elif config:
            # Android 设备配置（有预配置）
            options = UiAutomator2Options()
            options.device_name = config.name or device_name
            options.udid = config.udid or device_name
            options.set_capability("systemPort", config.system_port)
            options.set_capability("noReset", True)
            options.set_capability("newCommandTimeout", 300)
            # 注入 appPackage / appActivity
            if config.app_package:
                options.set_capability("appPackage", config.app_package)
            if config.app_activity:
                options.set_capability("appActivity", config.app_activity)
            # 注入配置文件中的额外 capabilities
            if config.capabilities:
                for k, v in config.capabilities.items():
                    if k not in ("appPackage", "appActivity", "noReset", "newCommandTimeout"):
                        options.set_capability(k, v)
            return options
        else:
            # 无预配置，使用默认 Android 配置
            options = UiAutomator2Options()
            options.device_name = device_name
            options.udid = device_name
            options.set_capability("noReset", True)
            options.set_capability("newCommandTimeout", 300)
            return options

    @staticmethod
    def _kill_uiautomator2(udid: str) -> None:
        """强制终止设备上的 UiAutomator2 进程。

        当旧会话未被正确关闭时，UiAutomator2 Server 会继续占用 systemPort，
        导致新会话无法启动。通过 adb 强制停止 io.appium.uiautomator2.server
        及其 shell 进程来释放端口。

        Args:
            udid: 设备的 UDID（如 emulator-5554）。
        """
        packages_to_kill = [
            "io.appium.uiautomator2.server",
            "io.appium.uiautomator2.server.test",
        ]
        for pkg in packages_to_kill:
            try:
                subprocess.run(
                    ["adb", "-s", udid, "shell", "am", "force-stop", pkg],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        logger.info("已清理设备 %s 上的残留 UiAutomator2 进程", udid)

    def connect_device(
        self,
        platform: str,
        device_name: str,
        app_package: str = "",
        app_activity: str = "",
        appium_port: int = 4723,
    ) -> Dict:
        """连接移动设备并启动指定 App。

        通过 Appium WebDriver 建立与设备的连接，支持 Android 和 iOS 设备。
        优先使用调用方传入的参数，缺失时从预配置中补充。

        Args:
            platform: 平台类型，"Android" 或 "iOS"。
            device_name: 设备名称或 UDID。
            app_package: Android 包名 或 iOS bundle ID。
            app_activity: Android 启动 Activity（iOS 可留空）。
            appium_port: Appium Server 端口，默认 4723。

        Returns:
            Dict: 包含连接结果的字典。
                - success: 是否成功
                - data: 成功时返回设备信息，失败时返回错误信息
        """
        try:
            with self._lock:
                # 检查设备是否已连接
                if device_name in self._connections:
                    return {
                        "success": True,
                        "data": {
                            "message": f"设备 '{device_name}' 已存在连接",
                            "device_name": device_name,
                        },
                    }

                # 确保 Android SDK 环境变量已设置
                self._ensure_android_env()

                # 清理残留 UiAutomator2 进程，释放可能被占用的 systemPort
                config = self._device_configs.get(device_name)
                udid = config.udid if config else device_name
                self._kill_uiautomator2(udid)

                # 确保 Appium Server 已启动
                if not self._is_appium_running():
                    logger.info("Appium Server 未运行，尝试自动启动...")
                    if not self._start_appium_server():
                        return {
                            "success": False,
                            "data": {
                                "message": f"Appium Server 启动失败，无法连接设备 '{device_name}'。"
                                           f"请手动启动: appium --address 127.0.0.1 --port 4723 --base-path /wd/hub",
                                "device_name": device_name,
                            },
                        }

                # 构建 Appium 连接配置（基于预配置）
                options = self._build_capabilities(device_name)

                # 用调用方传入的参数覆盖/补充预配置
                config = self._device_configs.get(device_name)
                # platform 优先使用传入值
                if platform and platform.lower() == "ios":
                    options.platform_name = "iOS"
                    options.automation_name = "XCUITest"
                # appPackage / appActivity 优先使用传入值，否则从预配置取
                pkg = app_package or (config.app_package if config else "")
                act = app_activity or (config.app_activity if config else "")
                if pkg:
                    options.set_capability("appPackage", pkg)
                if act:
                    options.set_capability("appActivity", act)

                # 构建动态 Appium Server URL（支持不同端口）
                appium_url = f"http://127.0.0.1:{appium_port}/wd/hub"

                # 创建 WebDriver 连接
                driver = webdriver.Remote(
                    command_executor=appium_url,
                    options=options,
                )

                # 存入连接池
                self._connections[device_name] = driver

                # 获取设备信息
                device_info = self._get_device_info_internal(driver)

                logger.info("设备 '%s' 连接成功", device_name)
                return {
                    "success": True,
                    "data": {
                        "message": f"设备 '{device_name}' 连接成功",
                        "device_name": device_name,
                        "device_info": device_info,
                    },
                }

        except Exception as e:
            error_str = str(e)
            logger.error("连接设备 '%s' 失败: %s", device_name, e)

            # 如果是 systemPort 被占用的错误，尝试再次清理后重试一次
            if "busy" in error_str.lower() or "systemPort" in error_str.lower():
                logger.info("[DeviceManager] 检测到端口占用，尝试二次清理并重连...")
                udid = config.udid if config else device_name
                self._kill_uiautomator2(udid)
                import time
                time.sleep(2)  # 等待端口释放
                try:
                    with self._lock:
                        options = self._build_capabilities(device_name)
                        config = self._device_configs.get(device_name)
                        if platform and platform.lower() == "ios":
                            options.platform_name = "iOS"
                            options.automation_name = "XCUITest"
                        pkg = app_package or (config.app_package if config else "")
                        act = app_activity or (config.app_activity if config else "")
                        if pkg:
                            options.set_capability("appPackage", pkg)
                        if act:
                            options.set_capability("appActivity", act)
                        appium_url = f"http://127.0.0.1:{appium_port}/wd/hub"
                        driver = webdriver.Remote(
                            command_executor=appium_url,
                            options=options,
                        )
                        self._connections[device_name] = driver
                        device_info = self._get_device_info_internal(driver)
                        logger.info("设备 '%s' 重连成功", device_name)
                        return {
                            "success": True,
                            "data": {
                                "message": f"设备 '{device_name}' 重连成功（端口清理后）",
                                "device_name": device_name,
                                "device_info": device_info,
                            },
                        }
                except Exception as retry_e:
                    logger.error("设备 '%s' 重连仍失败: %s", device_name, retry_e)

            return {
                "success": False,
                "data": {
                    "message": f"连接设备 '{device_name}' 失败: {error_str}",
                    "device_name": device_name,
                    "error": error_str,
                },
            }

    def disconnect_device(self, device_name: str) -> Dict:
        """断开指定名称的设备连接。

        从连接池中移除设备，并关闭对应的 WebDriver 会话。

        Args:
            device_name: 要断开连接的设备名称/标识符。

        Returns:
            Dict: 包含断开连接结果的字典。
                - success: 是否成功
                - data: 操作结果信息
        """
        try:
            with self._lock:
                # 检查设备是否在连接池中
                if device_name not in self._connections:
                    return {
                        "success": False,
                        "data": {
                            "message": f"设备 '{device_name}' 未连接",
                            "device_name": device_name,
                        },
                    }

                # 获取并关闭 WebDriver
                driver = self._connections.pop(device_name)
                try:
                    driver.quit()
                except Exception:
                    pass

                logger.info("设备 '%s' 已断开连接", device_name)
                return {
                    "success": True,
                    "data": {
                        "message": f"设备 '{device_name}' 已断开连接",
                        "device_name": device_name,
                    },
                }

        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"断开设备 '{device_name}' 失败: {str(e)}",
                    "device_name": device_name,
                    "error": str(e),
                },
            }

    def get_device_info(self, device_name: str) -> Dict:
        """获取指定设备的详细信息。

        查询当前连接设备的系统信息、屏幕尺寸、平台版本等。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            Dict: 包含设备信息的字典。
                - success: 是否成功
                - data: 成功时返回设备详细信息，失败时返回错误信息
        """
        try:
            with self._lock:
                if device_name not in self._connections:
                    return {
                        "success": False,
                        "data": {
                            "message": f"设备 '{device_name}' 未连接",
                            "device_name": device_name,
                        },
                    }

                driver = self._connections[device_name]
                device_info = self._get_device_info_internal(driver)

                return {
                    "success": True,
                    "data": {
                        "device_name": device_name,
                        **device_info,
                    },
                }

        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"获取设备 '{device_name}' 信息失败: {str(e)}",
                    "device_name": device_name,
                    "error": str(e),
                },
            }

    def list_devices(self) -> Dict:
        """列出所有已配置的设备及其连接状态。

        返回预配置的设备列表和当前连接池中的设备名称。

        Returns:
            Dict: 包含配置设备列表和连接设备列表的字典。
        """
        configured = []
        for dev_id, config in self._device_configs.items():
            configured.append({
                "device_id": dev_id,
                "name": config.name,
                "platform": config.platform,
                "udid": config.udid,
                "connected": dev_id in self._connections,
            })

        return {
            "success": True,
            "data": {
                "configured": configured,
                "connected": list(self._connections.keys()),
            },
        }

    def _is_session_alive(self, driver: WebDriver) -> bool:
        """检查 WebDriver 会话是否仍然有效。

        使用 Appium 兼容的健康检查方式，确保真正向服务端发请求验证：
        1. 检查 session_id 是否存在（本地属性，零开销）
        2. 通过 lightweight Appium 命令验证会话存活（必须经过网络）
        不使用 driver.current_url（移动端无 URL 概念），
        不使用 driver.capabilities（本地缓存，无法感知服务端会话死亡）。

        Args:
            driver: Appium WebDriver 实例。

        Returns:
            会话是否仍然有效。
        """
        try:
            # 快速检查：session_id 是否存在（本地属性，无网络开销）
            if not driver.session_id:
                return False

            # 方式1：查询 Appium 活跃会话列表，确认当前 session 在列
            try:
                from selenium.webdriver.remote.command import Command
                response = driver.command_executor.execute(
                    Command.GET_ALL_SESSIONS
                )
                active_sessions = response.get('value', [])
                for session in active_sessions:
                    if session.get('id') == driver.session_id:
                        return True
                # session 不在活跃列表中 → 服务端已失效
                logger.info(
                    "会话 %s 不在 Appium 活跃列表中，判定失效",
                    driver.session_id[:8],
                )
                return False
            except Exception:
                pass

            # 方式2：执行轻量级 Appium 命令验证会话存活
            # mobile:getDeviceTime 非常轻量，仅获取设备时间
            try:
                driver.execute_script("mobile: getDeviceTime")
                return True
            except Exception:
                logger.info(
                    "会话 %s 执行 mobile:getDeviceTime 失败，判定失效",
                    driver.session_id[:8],
                )
                return False

        except Exception:
            return False

    def get_driver(self, device_name: str) -> Optional[WebDriver]:
        """获取指定设备的 WebDriver 实例（含会话健康检查）。

        供内部其他模块使用，获取设备驱动以执行 UI 操作。
        当发现会话已失效时，自动从连接池移除并返回 None，
        上层调用方可据此触发重连。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            Optional[WebDriver]: 设备对应的 WebDriver 实例，
                如果设备未连接或会话已失效则返回 None。
        """
        with self._lock:
            driver = self._connections.get(device_name)
            if driver is not None and not self._is_session_alive(driver):
                logger.warning(
                    "设备 '%s' 的 Appium 会话已失效，从连接池移除", device_name
                )
                try:
                    driver.quit()
                except Exception:
                    pass
                self._connections.pop(device_name, None)
                return None
            return driver

    def ensure_connected(
        self,
        device_name: str,
        platform: str = "Android",
        app_package: str = "",
        app_activity: str = "",
        appium_port: int = 4723,
    ) -> Optional[WebDriver]:
        """确保设备已连接且会话有效，失效时自动重连。

        先检查现有会话是否存活，如果失效则清理后重新建立连接。
        供各 Toolkit 的 _check_device 调用，实现透明的自动重连。

        Args:
            device_name: 设备名称/标识符。
            platform: 平台类型，"Android" 或 "iOS"。
            app_package: Android 包名 或 iOS bundle ID。
            app_activity: Android 启动 Activity。
            appium_port: Appium Server 端口。

        Returns:
            Optional[WebDriver]: 有效的 WebDriver 实例，重连失败时返回 None。
        """
        driver = self.get_driver(device_name)
        if driver is not None:
            return driver

        # 会话失效或不存在，尝试重连
        logger.info("设备 '%s' 会话不可用，尝试自动重连...", device_name)
        config = self._device_configs.get(device_name)
        udid = config.udid if config else device_name
        self._kill_uiautomator2(udid)

        result = self.connect_device(
            platform=platform,
            device_name=device_name,
            app_package=app_package or (config.app_package if config else ""),
            app_activity=app_activity or (config.app_activity if config else ""),
            appium_port=appium_port,
        )

        if result.get("success"):
            logger.info("设备 '%s' 自动重连成功", device_name)
            return self._connections.get(device_name)
        else:
            logger.error("设备 '%s' 自动重连失败: %s", device_name, result.get("data", {}).get("message", ""))
            return None

    def _get_device_info_internal(self, driver: WebDriver) -> Dict:
        """内部方法：从 WebDriver 获取设备信息。

        Args:
            driver: Appium WebDriver 实例。

        Returns:
            Dict: 设备详细信息字典。
        """
        try:
            window_size = driver.get_window_size()
            return {
                "platform": driver.capabilities.get("platformName", "未知"),
                "platform_version": driver.capabilities.get(
                    "platformVersion", "未知"
                ),
                "device_name": driver.capabilities.get("deviceName", "未知"),
                "udid": driver.capabilities.get("udid", "未知"),
                "screen_width": window_size.get("width", 0),
                "screen_height": window_size.get("height", 0),
                "automation_name": driver.capabilities.get(
                    "automationName", "未知"
                ),
                "app_package": driver.capabilities.get("appPackage", ""),
                "app_activity": driver.capabilities.get("appActivity", ""),
            }
        except Exception:
            return {
                "platform": "未知",
                "platform_version": "未知",
                "device_name": "未知",
                "screen_width": 0,
                "screen_height": 0,
            }

    def disconnect_all(self) -> Dict:
        """断开所有设备的连接。

        遍历连接池，关闭所有 WebDriver 会话并清空连接池。

        Returns:
            Dict: 操作结果，包含成功断开的设备数量。
        """
        with self._lock:
            device_names = list(self._connections.keys())
            for name in device_names:
                try:
                    driver = self._connections.pop(name)
                    driver.quit()
                except Exception:
                    pass

            logger.info("已断开所有设备连接，共 %d 个设备", len(device_names))
            return {
                "success": True,
                "data": {
                    "message": f"已断开所有设备连接，共 {len(device_names)} 个设备",
                    "disconnected_count": len(device_names),
                },
            }