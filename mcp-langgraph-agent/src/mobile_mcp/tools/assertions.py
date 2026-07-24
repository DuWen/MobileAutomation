"""
断言工具模块

提供测试断言相关的功能，包括文本可见性断言、元素存在性断言、
页面内容断言以及元素等待功能。使用 Appium 的 WebDriverWait
实现显式等待机制。
"""

import logging
from typing import Dict, Optional

from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from .device import DeviceManager

logger = logging.getLogger(__name__)


class AssertToolkit:
    """断言工具包，提供 UI 测试断言方法。

    封装了基于 Appium WebDriver 的文本可见性断言、元素存在性断言、
    页面内容断言和元素等待功能，支持超时配置和多种定位策略。
    """

    # 默认轮询间隔（秒）
    DEFAULT_POLL_FREQUENCY: float = 0.5

    def __init__(self, device_manager: DeviceManager) -> None:
        """初始化断言工具包。

        Args:
            device_manager: 设备管理器实例，用于获取设备 WebDriver。
        """
        self._device_manager = device_manager

    def _check_device(self, device_name: str) -> Optional[WebDriver]:
        """检查设备是否已连接并返回 WebDriver 实例。

        使用 ensure_connected 替代直接 get_driver，当会话失效时自动重连。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            WebDriver 实例，设备未连接且重连失败时返回 None。
        """
        driver = self._device_manager.ensure_connected(device_name)
        if driver is None:
            logger.warning("设备 '%s' 未连接且重连失败", device_name)
        return driver

    def assert_text_visible(
        self, device_name: str, text: str, timeout: int = 10
    ) -> Dict:
        """断言指定文本在设备屏幕上可见。

        在指定超时时间内轮询查找包含目标文本的元素，如果能找到
        则认为断言通过，否则断言失败。

        Args:
            device_name: 设备名称/标识符。
            text: 要断言的文本内容。
            timeout: 最大等待时间（秒），默认 10 秒。

        Returns:
            Dict: 断言结果，包含 success 和 data 字段。
                - success: True 表示文本可见（断言通过），False 表示不可见
                - data.message: 断言结果描述
                - data.text: 目标文本
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"断言失败：设备 '{device_name}' 未连接", "text": text, "assertion": "text_visible"},
            }

        try:
            wait = WebDriverWait(driver, timeout, poll_frequency=self.DEFAULT_POLL_FREQUENCY)
            xpath = f'//*[contains(@text, "{text}") or contains(@content-desc, "{text}")]'
            wait.until(ec.presence_of_element_located((AppiumBy.XPATH, xpath)))

            return {
                "success": True,
                "data": {
                    "message": f"断言通过：文本 '{text}' 在 {timeout} 秒内可见",
                    "text": text,
                    "timeout": timeout,
                    "assertion": "text_visible",
                },
            }

        except TimeoutException:
            return {
                "success": False,
                "data": {
                    "message": f"断言失败：文本 '{text}' 在 {timeout} 秒内未出现",
                    "text": text,
                    "timeout": timeout,
                    "assertion": "text_visible",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"断言文本可见性时发生错误: {str(e)}",
                    "text": text,
                    "error": str(e),
                    "assertion": "text_visible",
                },
            }

    def assert_element_exists(
        self, device_name: str, selector: Dict
    ) -> Dict:
        """断言指定元素在设备屏幕上存在。

        使用给定的选择器在页面中查找元素，如果存在则认为断言通过。
        与 wait_for_element 不同，此方法不等待，而是立即检查。

        Args:
            device_name: 设备名称/标识符。
            selector: 元素选择器字典，包含 'by'（定位策略）和 'value'（定位值）。
                例如: {"by": "accessibility_id", "value": "btn_ok"}
                支持定位策略: xpath, accessibility_id, class_name, id

        Returns:
            Dict: 断言结果，包含 success 和 data 字段。
                - success: True 表示元素存在（断言通过），False 表示不存在
                - data.message: 断言结果描述
                - data.selector: 使用的选择器
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"断言失败：设备 '{device_name}' 未连接", "selector": selector, "assertion": "element_exists"},
            }

        try:
            by = self._parse_by_strategy(selector.get("by", "xpath"))
            value = selector.get("value", "")

            if not value:
                return {
                    "success": False,
                    "data": {"message": "断言失败：选择器缺少 'value' 字段", "selector": selector, "assertion": "element_exists"},
                }

            element = driver.find_element(by, value)

            return {
                "success": True,
                "data": {
                    "message": f"断言通过：元素 '{value}' 存在",
                    "selector": selector,
                    "element_text": element.text,
                    "is_displayed": element.is_displayed(),
                    "assertion": "element_exists",
                },
            }

        except NoSuchElementException:
            return {
                "success": False,
                "data": {
                    "message": f"断言失败：元素 '{selector.get('value', '')}' 不存在",
                    "selector": selector,
                    "assertion": "element_exists",
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"断言元素存在性时发生错误: {str(e)}",
                    "selector": selector,
                    "error": str(e),
                    "assertion": "element_exists",
                },
            }

    def assert_page_contains(
        self, device_name: str, text: str
    ) -> Dict:
        """断言当前页面源包含指定文本内容。

        通过检查页面源（page source）中是否包含目标文本进行断言，
        适用于 UI 树中不可见但 DOM 中存在的元素验证。

        Args:
            device_name: 设备名称/标识符。
            text: 要断言的文本内容。

        Returns:
            Dict: 断言结果，包含 success 和 data 字段。
                - success: True 表示页面包含目标文本（断言通过）
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"断言失败：设备 '{device_name}' 未连接", "text": text, "assertion": "page_contains"},
            }

        try:
            page_source = driver.page_source

            if text in page_source:
                return {
                    "success": True,
                    "data": {
                        "message": f"断言通过：页面源包含文本 '{text}'",
                        "text": text,
                        "assertion": "page_contains",
                    },
                }
            else:
                return {
                    "success": False,
                    "data": {
                        "message": f"断言失败：页面源不包含文本 '{text}'",
                        "text": text,
                        "assertion": "page_contains",
                    },
                }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"断言页面内容时发生错误: {str(e)}",
                    "text": text,
                    "error": str(e),
                    "assertion": "page_contains",
                },
            }

    def wait_for_element(
        self,
        device_name: str,
        selector: Dict,
        timeout: int = 10,
    ) -> Dict:
        """等待指定元素在设备屏幕上出现并可见。

        在指定超时时间内轮询等待元素变为可见状态，
        可用于在操作前确保元素已就绪。

        Args:
            device_name: 设备名称/标识符。
            selector: 元素选择器字典，包含 'by'（定位策略）和 'value'（定位值）。
            timeout: 最大等待时间（秒），默认 10 秒。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: True 表示元素在超时前出现
                - data.message: 等待结果描述
                - data.selector: 使用的选择器
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"等待失败：设备 '{device_name}' 未连接", "selector": selector},
            }

        try:
            by = self._parse_by_strategy(selector.get("by", "xpath"))
            value = selector.get("value", "")

            if not value:
                return {
                    "success": False,
                    "data": {"message": "等待失败：选择器缺少 'value' 字段", "selector": selector},
                }

            wait = WebDriverWait(driver, timeout, poll_frequency=self.DEFAULT_POLL_FREQUENCY)
            element = wait.until(ec.visibility_of_element_located((by, value)))

            element_info = {
                "tag": element.tag_name,
                "text": element.text,
                "location": element.location,
                "size": element.size,
                "is_enabled": element.is_enabled(),
                "content_desc": element.get_attribute("content-desc"),
            }

            return {
                "success": True,
                "data": {
                    "message": f"等待成功：元素 '{value}' 已出现（等待 {timeout} 秒内）",
                    "selector": selector,
                    "element": element_info,
                    "timeout": timeout,
                },
            }

        except TimeoutException:
            return {
                "success": False,
                "data": {
                    "message": f"等待超时：元素 '{selector.get('value', '')}' 在 {timeout} 秒内未出现",
                    "selector": selector,
                    "timeout": timeout,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"等待元素时发生错误: {str(e)}",
                    "selector": selector,
                    "error": str(e),
                },
            }

    def _parse_by_strategy(self, strategy: str) -> AppiumBy:
        """内部方法：将字符串定位策略转换为 AppiumBy 枚举值。

        Args:
            strategy: 定位策略字符串。

        Returns:
            AppiumBy: 对应的 AppiumBy 枚举值。
        """
        strategy_map = {
            "xpath": AppiumBy.XPATH,
            "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
            "class_name": AppiumBy.CLASS_NAME,
            "id": AppiumBy.ID,
            "android_uiautomator": AppiumBy.ANDROID_UIAUTOMATOR,
            "ios_predicate": AppiumBy.IOS_PREDICATE,
            "ios_class_chain": AppiumBy.IOS_CLASS_CHAIN,
        }
        return strategy_map.get(strategy.lower(), AppiumBy.XPATH)
