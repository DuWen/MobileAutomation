"""
设备管理工具模块

提供设备连接、断开和基本信息查询功能。
使用 appium-python-client 的 WebDriver 管理设备连接，
并通过线程安全机制维护连接池。
"""

import threading
from typing import Dict, Optional

from appium import webdriver
from appium.webdriver.appium_service import AppiumService
from selenium.webdriver.remote.webdriver import WebDriver


class DeviceManager:
    """设备管理器，负责 Appium 设备连接的生命周期管理。

    维护一个线程安全的设备连接池，支持多设备并发连接。
    提供设备的连接、断开和基本信息查询功能。
    """

    def __init__(self) -> None:
        """初始化设备管理器，创建连接池和线程锁。"""
        # 设备连接池，key 为设备名称，value 为 WebDriver 实例
        self._connections: Dict[str, WebDriver] = {}
        # 线程锁，保证连接池操作的线程安全
        self._lock = threading.Lock()
        # Appium 服务实例（可选，用于自动启动 Appium）
        self._appium_service: Optional[AppiumService] = None

    def connect_device(self, device_name: str) -> Dict:
        """连接指定名称的设备。

        通过 Appium WebDriver 建立与设备的连接，支持 Android 和 iOS 设备。
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
                # 实际使用时需要根据设备类型（Android/iOS）调整配置
                desired_caps = {
                    "platformName": "Android",  # 或 "iOS"
                    "deviceName": device_name,
                    "udid": device_name,
                    "automationName": "UiAutomator2",  # Android 使用 UiAutomator2
                    "noReset": True,
                    "newCommandTimeout": 300,
                }

                # 创建 WebDriver 连接
                driver = webdriver.Remote(
                    command_executor="http://localhost:4723",
                    options=desired_caps,  # type: ignore
                )

                # 存入连接池
                self._connections[device_name] = driver

                # 获取设备信息
                device_info = self._get_device_info_internal(driver)

                return {
                    "success": True,
                    "data": {
                        "message": f"设备 '{device_name}' 连接成功",
                        "device_name": device_name,
                        "device_info": device_info,
                    },
                }

        except Exception as e:
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
                    # 忽略关闭时的异常
                    pass

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
                # 检查设备是否在连接池中
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
            # 获取设备窗口尺寸
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

            return {
                "success": True,
                "data": {
                    "message": f"已断开所有设备连接，共 {len(device_names)} 个设备",
                    "disconnected_count": len(device_names),
                },
            }