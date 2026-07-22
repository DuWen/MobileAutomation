"""
UI 交互工具模块

封装基于 Appium 的 UI 操作，包括点击、输入、滑动等。
支持多种元素定位策略（xpath, accessibility_id, class_name），
并提供按文本查找并点击的便捷方法。
"""

from typing import Dict, Optional

from appium.webdriver import WebElement
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from .device import DeviceManager


class UIToolkit:
    """UI 操作工具包，提供设备 UI 交互的核心方法。

    封装了 Appium WebDriver 的常用 UI 操作，包括点击、输入文本、
    滑动等，并支持多种元素定位策略。
    """

    # 默认等待超时时间（秒）
    DEFAULT_TIMEOUT: int = 10
    # 默认轮询间隔（秒）
    DEFAULT_POLL_FREQUENCY: float = 0.5

    def __init__(self, device_manager: DeviceManager) -> None:
        """初始化 UI 工具包。

        Args:
            device_manager: 设备管理器实例，用于获取设备 WebDriver。
        """
        self._device_manager = device_manager

    def tap_element(
        self, device_name: str, x: int, y: int
    ) -> Dict:
        """在指定坐标位置执行点击操作。

        通过坐标点（x, y）在设备屏幕上执行点击，适用于无法通过
        元素定位器找到元素时的后备方案。

        Args:
            device_name: 设备名称/标识符。
            x: 点击位置的 x 坐标（像素）。
            y: 点击位置的 y 坐标（像素）。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 使用 Appium 的 TouchAction 或 W3C Actions 执行点击
            driver.execute_script(
                "mobile: clickGesture", {"x": x, "y": y}
            )
            return {
                "success": True,
                "data": {
                    "message": f"在坐标 ({x}, {y}) 执行点击成功",
                    "x": x,
                    "y": y,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"点击坐标 ({x}, {y}) 失败: {str(e)}",
                    "x": x,
                    "y": y,
                    "error": str(e),
                },
            }

    def tap_by_text(
        self, device_name: str, text: str
    ) -> Dict:
        """通过文本内容查找元素并点击。

        使用 xpath 或 accessibility_id 定位包含指定文本的元素，
        找到后执行点击操作。

        Args:
            device_name: 设备名称/标识符。
            text: 要查找并点击的文本内容。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 尝试多种定位策略查找文本元素
            element = self._find_element_by_text(driver, text)
            if element is None:
                return {
                    "success": False,
                    "data": {
                        "message": f"未找到包含文本 '{text}' 的元素",
                        "text": text,
                    },
                }

            # 执行点击
            element.click()
            return {
                "success": True,
                "data": {
                    "message": f"点击文本 '{text}' 成功",
                    "text": text,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"点击文本 '{text}' 失败: {str(e)}",
                    "text": text,
                    "error": str(e),
                },
            }

    def input_text(
        self, device_name: str, element_id: str, text: str
    ) -> Dict:
        """向指定元素输入文本内容。

        先清除元素的现有文本，再输入目标文本。
        支持通过 accessibility_id、xpath 或 class_name 定位元素。

        Args:
            device_name: 设备名称/标识符。
            element_id: 元素标识符，可以是 accessibility_id、xpath 或 class_name。
            text: 要输入的文本内容。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 查找元素
            element = self._find_element(driver, element_id)
            if element is None:
                return {
                    "success": False,
                    "data": {
                        "message": f"未找到元素 '{element_id}'",
                        "element_id": element_id,
                    },
                }

            # 清除现有文本并输入新文本
            element.clear()
            element.send_keys(text)

            return {
                "success": True,
                "data": {
                    "message": f"向元素 '{element_id}' 输入文本成功",
                    "element_id": element_id,
                    "text": text,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"向元素 '{element_id}' 输入文本失败: {str(e)}",
                    "element_id": element_id,
                    "text": text,
                    "error": str(e),
                },
            }

    def swipe(
        self,
        device_name: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: int = 500,
    ) -> Dict:
        """在设备屏幕上执行滑动操作。

        从起始坐标 (start_x, start_y) 滑动到结束坐标 (end_x, end_y)，
        常用于页面滚动、列表滑动等场景。

        Args:
            device_name: 设备名称/标识符。
            start_x: 滑动起点的 x 坐标。
            start_y: 滑动起点的 y 坐标。
            end_x: 滑动终点的 x 坐标。
            end_y: 滑动终点的 y 坐标。
            duration: 滑动持续时间（毫秒），默认 500ms。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 使用 W3C Actions API 执行滑动
            driver.execute_script(
                "mobile: swipeGesture",
                {
                    "left": start_x,
                    "top": start_y,
                    "width": end_x - start_x,
                    "height": end_y - start_y,
                    "duration": duration,
                    "direction": "custom",
                },
            )

            return {
                "success": True,
                "data": {
                    "message": "滑动操作成功",
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "duration": duration,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"滑动操作失败: {str(e)}",
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "error": str(e),
                },
            }

    def _find_element(
        self, driver: WebDriver, element_id: str
    ) -> Optional[WebElement]:
        """内部方法：通过多种定位策略查找元素。

        按照 accessibility_id -> xpath -> class_name 的顺序依次尝试定位。

        Args:
            driver: Appium WebDriver 实例。
            element_id: 元素标识符。

        Returns:
            Optional[WebElement]: 找到的元素对象，未找到则返回 None。
        """
        # 定位策略列表，按优先级排序
        locators = [
            (AppiumBy.ACCESSIBILITY_ID, element_id),
            (AppiumBy.XPATH, element_id),
            (AppiumBy.CLASS_NAME, element_id),
        ]

        for by, value in locators:
            try:
                element = driver.find_element(by, value)
                if element:
                    return element
            except NoSuchElementException:
                continue

        return None

    def _find_element_by_text(
        self, driver: WebDriver, text: str
    ) -> Optional[WebElement]:
        """内部方法：通过文本内容查找元素。

        使用多种 xpath 策略匹配文本，包括完全匹配和包含匹配。

        Args:
            driver: Appium WebDriver 实例。
            text: 要查找的文本内容。

        Returns:
            Optional[WebElement]: 找到的元素对象，未找到则返回 None。
        """
        # 文本匹配的 xpath 策略列表
        text_xpath_strategies = [
            # 精确匹配 text 属性
            f'//*[@text="{text}"]',
            # 包含匹配 text 属性
            f'//*[contains(@text, "{text}")]',
            # 精确匹配 content-desc 属性
            f'//*[@content-desc="{text}"]',
            # 包含匹配 content-desc 属性
            f'//*[contains(@content-desc, "{text}")]',
            # 匹配 value 属性
            f'//*[@value="{text}"]',
        ]

        for xpath in text_xpath_strategies:
            try:
                element = driver.find_element(AppiumBy.XPATH, xpath)
                if element:
                    return element
            except NoSuchElementException:
                continue

        return None

    def wait_for_element(
        self,
        device_name: str,
        selector: Dict,
        timeout: int = 10,
    ) -> Dict:
        """等待指定元素出现。

        使用 WebDriverWait 实现显式等待，直到元素在 DOM 中可见。

        Args:
            device_name: 设备名称/标识符。
            selector: 元素选择器字典，包含 'by'（定位策略）和 'value'（定位值）。
                例如: {"by": "accessibility_id", "value": "btn_ok"}
            timeout: 最大等待时间（秒），默认 10 秒。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 解析选择器
            by = self._parse_by_strategy(selector.get("by", "xpath"))
            value = selector.get("value", "")

            if not value:
                return {
                    "success": False,
                    "data": {"message": "选择器缺少 'value' 字段"},
                }

            # 等待元素可见
            wait = WebDriverWait(
                driver, timeout, poll_frequency=self.DEFAULT_POLL_FREQUENCY
            )
            element = wait.until(
                ec.visibility_of_element_located((by, value))
            )

            # 获取元素信息
            element_info = self._get_element_info(element)

            return {
                "success": True,
                "data": {
                    "message": f"元素已出现（等待 {timeout} 秒）",
                    "selector": selector,
                    "element": element_info,
                },
            }
        except TimeoutException:
            return {
                "success": False,
                "data": {
                    "message": f"等待元素超时（{timeout} 秒）",
                    "selector": selector,
                    "timeout": timeout,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"等待元素失败: {str(e)}",
                    "selector": selector,
                    "error": str(e),
                },
            }

    def _parse_by_strategy(self, strategy: str) -> AppiumBy:
        """内部方法：将字符串定位策略转换为 AppiumBy 枚举值。

        Args:
            strategy: 定位策略字符串，如 "xpath", "accessibility_id", "class_name", "id"。

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

    def _get_element_info(self, element: WebElement) -> Dict:
        """内部方法：获取元素的详细信息。

        Args:
            element: WebElement 实例。

        Returns:
            Dict: 元素信息字典，包含标签、文本、位置、尺寸等。
        """
        try:
            return {
                "tag": element.tag_name,
                "text": element.text,
                "location": element.location,
                "size": element.size,
                "is_displayed": element.is_displayed(),
                "is_enabled": element.is_enabled(),
                "is_selected": element.is_selected(),
                "content_desc": element.get_attribute("content-desc"),
            }
        except Exception:
            return {
                "tag": "未知",
                "text": "",
                "location": {"x": 0, "y": 0},
                "size": {"width": 0, "height": 0},
            }