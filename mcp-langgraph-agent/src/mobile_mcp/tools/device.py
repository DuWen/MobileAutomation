"""
设备管理工具模块

提供设备连接、断开和基本信息查询功能。
使用 appium-python-client 的 WebDriver 管理设备连接，
并通过线程安全机制维护连接池。支持 Android 和 iOS 设备，
可从 YAML 配置文件预加载设备参数。
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

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
        device_id: 设备唯一标识（对应配置文件中的 id）。
        name: 设备名称。
        platform: 平台类型（Android/iOS）。
        udid: 设备 UDID。
        system_port: Android 系统调试端口。
        wda_port: iOS WebDriverAgent 端口。
    """

    device_id: str
    name: str = ""
    platform: str = "Android"
    udid: str = ""
    system_port: int = 8200
    wda_port: int = 8100


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

    def register_device_config(
        self,
        device_id: str,
        name: str = "",
        platform: str = "Android",
        udid: str = "",
        system_port: int = 8200,
        wda_port: int = 8100,
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
        """
        config = DeviceConfig(
            device_id=device_id,
            name=name,
            platform=platform,
            udid=udid or device_id,
            system_port=system_port,
            wda_port=wda_port,
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
            return options
        else:
            # 无预配置，使用默认 Android 配置
            options = UiAutomator2Options()
            options.device_name = device_name
            options.udid = device_name
            options.set_capability("noReset", True)
            options.set_capability("newCommandTimeout", 300)
            return options

    def connect_device(self, device_name: str) -> Dict:
        """连接指定名称的设备。

        通过 Appium WebDriver 建立与设备的连接，支持 Android 和 iOS 设备。
        如果设备有预配置，自动使用正确的 Capabilities；否则使用默认配置。
        连接成功后，将 WebDriver 实例存入连接池。

        Args:
            device_name: 设备名称/标识符，如 Android 的 udid 或 iOS 的 deviceName。

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

                # 构建 Appium 连接配置
                options = self._build_capabilities(device_name)

                # 创建 WebDriver 连接
                driver = webdriver.Remote(
                    command_executor=self._appium_url,
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
            logger.error("连接设备 '%s' 失败: %s", device_name, e)
            return {
                "success": False,
                "data": {
                    "message": f"连接设备 '{device_name}' 失败: {str(e)}",
                    "device_name": device_name,
                    "error": str(e),
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

    def get_driver(self, device_name: str) -> Optional[WebDriver]:
        """获取指定设备的 WebDriver 实例。

        供内部其他模块使用，获取设备驱动以执行 UI 操作。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            Optional[WebDriver]: 设备对应的 WebDriver 实例，如果设备未连接则返回 None。
        """
        with self._lock:
            return self._connections.get(device_name)

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