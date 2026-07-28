"""
UI 交互工具模块

封装基于 Appium 的 UI 操作，包括点击、输入、滑动、长按、按键等。
支持多种元素定位策略（xpath, accessibility_id, class_name），
并提供按文本查找并点击的便捷方法，以及方向滚动和系统按键操作。
"""

import logging

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

logger = logging.getLogger(__name__)

# Android 按键码映射表
_ANDROID_KEYCODE_MAP: dict[str, int] = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "delete": 67,
    "tab": 61,
    "space": 62,
    "escape": 111,
    "menu": 82,
    "search": 84,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "camera": 27,
    "recent_apps": 187,
}


class UIToolkit:
    """UI 操作工具包，提供设备 UI 交互的核心方法。

    封装了 Appium WebDriver 的常用 UI 操作，包括点击、输入文本、
    滑动、长按、按键等，并支持多种元素定位策略。
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

    def _check_device(self, device_name: str) -> WebDriver | None:
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

    def tap_element(
        self,
        device_name: str,
        by: str,
        value: str,
        use_bounds_fallback: bool = True,
    ) -> dict:
        """通过定位策略查找并点击元素。

        支持多种定位策略（id / xpath / accessibility_id / text），
        找到元素后执行点击操作。当策略定位失败且 use_bounds_fallback
        为 True 时，自动降级为从 UI 树解析 bounds 执行坐标点击。

        Args:
            device_name: 设备名称/标识符。
            by: 定位方式 — "id" | "xpath" | "accessibility_id" | "text"。
            value: 定位值。
            use_bounds_fallback: 找不到元素时是否尝试用文本匹配 bounds 降级点击。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        strategy_map = {
            "id": AppiumBy.ID,
            "xpath": AppiumBy.XPATH,
            "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
            "text": AppiumBy.ANDROID_UIAUTOMATOR,
        }

        try:
            if by == "text":
                # Android 特有：通过 UiSelector 按文本查找
                selector = f'new UiSelector().textContains("{value}")'
                element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
            else:
                strategy = strategy_map.get(by)
                if strategy is None:
                    return {
                        "success": False,
                        "data": {"message": f"不支持的定位方式: {by}", "by": by, "value": value},
                    }
                element = driver.find_element(strategy, value)
            element.click()
            return {
                "success": True,
                "data": {"message": f"点击 [{by}={value}] 成功", "by": by, "value": value},
            }
        except NoSuchElementException:
            if use_bounds_fallback and by in ("text", "accessibility_id"):
                return self._tap_by_bounds_fallback(driver, value)
            return {
                "success": False,
                "data": {"message": f"未找到元素 [{by}={value}]", "by": by, "value": value},
            }
        except Exception as e:  # noqa: BLE001
            if use_bounds_fallback and by in ("text", "accessibility_id"):
                return self._tap_by_bounds_fallback(driver, value)
            logger.error("点击 [%s=%s] 失败: %s", by, value, e)
            return {
                "success": False,
                "data": {"message": f"点击 [{by}={value}] 失败: {e!s}", "by": by, "value": value},
            }

    def _tap_by_bounds_fallback(self, driver: WebDriver, text: str) -> dict:
        """通过文本在 UI 树中查找 bounds，执行坐标点击（降级方案）。

        当策略定位失败时，从 page_source 的 XML 中解析包含目标文本的
        元素 bounds 属性，计算中心坐标后执行坐标点击。

        Args:
            driver: Appium WebDriver 实例。
            text: 要查找的文本内容。

        Returns:
            Dict: 操作结果。
        """
        import re

        try:
            xml = driver.page_source
            pattern = rf'text="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            match = re.search(pattern, xml)
            if match:
                x1, y1, x2, y2 = map(int, match.groups())
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                driver.tap([(cx, cy)])
                return {
                    "success": True,
                    "data": {"message": f"通过坐标回退点击 [{text}] @ ({cx},{cy})", "x": cx, "y": cy},
                }
            return {
                "success": False,
                "data": {"message": f"文本 [{text}] 未在 UI 树中找到", "text": text},
            }
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "data": {"message": f"坐标降级点击失败: {e!s}", "text": text},
            }

    def tap_by_text(
        self, device_name: str, text: str
    ) -> dict:
        """通过文本内容查找元素并点击。

        使用 xpath 或 accessibility_id 定位包含指定文本的元素，
        找到后执行点击操作。

        Args:
            device_name: 设备名称/标识符。
            text: 要查找并点击的文本内容。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            element = self._find_element_by_text(driver, text)
            if element is None:
                return {
                    "success": False,
                    "data": {"message": f"未找到包含文本 '{text}' 的元素", "text": text},
                }

            element.click()
            return {
                "success": True,
                "data": {"message": f"点击文本 '{text}' 成功", "text": text},
            }
        except Exception as e:  # noqa: BLE001
            logger.error("点击文本 '%s' 失败: %s", text, e)
            return {
                "success": False,
                "data": {"message": f"点击文本 '{text}' 失败: {e!s}", "text": text, "error": str(e)},
            }

    def input_text(
        self,
        device_name: str,
        by: str,
        value: str,
        text: str,
    ) -> dict:
        """向指定元素输入文本内容。

        先通过定位策略找到元素，清除现有文本，再输入目标文本。
        支持与 tap_element 相同的定位策略：id / xpath / accessibility_id / text。

        Args:
            device_name: 设备名称/标识符。
            by: 定位方式 — "id" | "xpath" | "accessibility_id" | "text"。
            value: 定位值。
            text: 要输入的文本内容。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        if not value:
            return {"success": False, "data": {"message": "定位值 value 不能为空", "by": by}}

        try:
            # 与 tap_element 相同的定位策略
            strategy_map = {
                "id": AppiumBy.ID,
                "xpath": AppiumBy.XPATH,
                "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
                "text": AppiumBy.ANDROID_UIAUTOMATOR,
            }

            if by == "text":
                selector = f'new UiSelector().textContains("{value}")'
                element = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, selector)
            else:
                strategy = strategy_map.get(by)
                if strategy is None:
                    return {
                        "success": False,
                        "data": {"message": f"不支持的定位方式: {by}", "by": by, "value": value},
                    }
                element = driver.find_element(strategy, value)

            element.clear()
            element.send_keys(text)

            return {
                "success": True,
                "data": {"message": f"向元素 [{by}={value}] 输入文本成功", "by": by, "value": value, "text": text},
            }
        except NoSuchElementException:
            return {
                "success": False,
                "data": {"message": f"未找到元素 [{by}={value}]", "by": by, "value": value},
            }
        except Exception as e:  # noqa: BLE001
            logger.error("向元素 [%s=%s] 输入文本失败: %s", by, value, e)
            return {
                "success": False,
                "data": {"message": f"向元素 [{by}={value}] 输入文本失败: {e!s}", "by": by, "value": value, "error": str(e)},
            }

    def swipe(
        self,
        device_name: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: int = 500,
    ) -> dict:
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
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            # 使用 W3C Actions API 的 driver.swipe 进行坐标式滑动
            # mobile: swipeGesture 只支持 direction+percent（不支持任意坐标），不适合本场景
            driver.swipe(start_x, start_y, end_x, end_y, duration)

            return {
                "success": True,
                "data": {
                    "message": "滑动操作成功",
                    "start_x": start_x, "start_y": start_y,
                    "end_x": end_x, "end_y": end_y,
                    "duration": duration,
                },
            }
        except Exception as e:  # noqa: BLE001
            logger.error("滑动操作失败: %s", e)
            return {
                "success": False,
                "data": {
                    "message": f"滑动操作失败: {e!s}",
                    "start_x": start_x, "start_y": start_y,
                    "end_x": end_x, "end_y": end_y,
                    "error": str(e),
                },
            }

    def long_press(
        self, device_name: str, x: int, y: int, duration: int = 1000
    ) -> dict:
        """在指定坐标位置执行长按操作。

        通过 Appium 的 mobile: longClickGesture 执行长按，
        适用于触发上下文菜单、拖拽等场景。

        Args:
            device_name: 设备名称/标识符。
            x: 长按位置的 x 坐标（像素）。
            y: 长按位置的 y 坐标（像素）。
            duration: 长按持续时间（毫秒），默认 1000ms。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            driver.execute_script(
                "mobile: longClickGesture",
                {"x": x, "y": y, "duration": duration},
            )
            return {
                "success": True,
                "data": {"message": f"在坐标 ({x}, {y}) 执行长按成功", "x": x, "y": y, "duration": duration},
            }
        except Exception as e:  # noqa: BLE001
            logger.error("长按坐标 (%d, %d) 失败: %s", x, y, e)
            return {
                "success": False,
                "data": {"message": f"长按坐标 ({x}, {y}) 失败: {e!s}", "x": x, "y": y, "error": str(e)},
            }

    def press_key(self, device_name: str, key_name: str) -> dict:
        """按下设备物理或系统按键。

        支持常见的 Android 系统按键（back、home、enter 等），
        iOS 设备暂不支持此功能。

        Args:
            device_name: 设备名称/标识符。
            key_name: 按键名称，如 "back", "home", "enter", "delete" 等。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        keycode = _ANDROID_KEYCODE_MAP.get(key_name.lower())
        if keycode is None:
            return {
                "success": False,
                "data": {
                    "message": f"不支持的按键名称: '{key_name}'，支持的按键: {list(_ANDROID_KEYCODE_MAP.keys())}",
                    "key_name": key_name,
                },
            }

        try:
            driver.press_keycode(keycode)
            return {
                "success": True,
                "data": {"message": f"按键 '{key_name}' 按下成功", "key_name": key_name, "keycode": keycode},
            }
        except Exception as e:  # noqa: BLE001
            logger.error("按键 '%s' 按下失败: %s", key_name, e)
            return {
                "success": False,
                "data": {"message": f"按键 '{key_name}' 按下失败: {e!s}", "key_name": key_name, "error": str(e)},
            }

    def scroll(
        self, device_name: str, direction: str = "down", distance: float = 0.5
    ) -> dict:
        """在设备屏幕上执行方向滚动操作。

        通过 Appium 的 mobile: scrollGesture 实现方向滚动，
        支持 up/down/left/right 四个方向。

        Args:
            device_name: 设备名称/标识符。
            direction: 滚动方向，可选 "up"/"down"/"left"/"right"，默认 "down"。
            distance: 滚动距离占屏幕比例（0.0-1.0），默认 0.5。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        valid_directions = {"up", "down", "left", "right"}
        if direction.lower() not in valid_directions:
            return {
                "success": False,
                "data": {
                    "message": f"无效的滚动方向: '{direction}'，可选: {list(valid_directions)}",
                    "direction": direction,
                },
            }

        try:
            driver.execute_script(
                "mobile: scrollGesture",
                {
                    "direction": direction.lower(),
                    "percent": distance,
                },
            )
            return {
                "success": True,
                "data": {"message": f"向 {direction} 方向滚动成功", "direction": direction, "distance": distance},
            }
        except Exception as e:  # noqa: BLE001
            logger.error("滚动操作失败: %s", e)
            return {
                "success": False,
                "data": {"message": f"滚动操作失败: {e!s}", "direction": direction, "error": str(e)},
            }

    def wait_for_element(
        self,
        device_name: str,
        selector: dict,
        timeout: int = 10,
    ) -> dict:
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
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            by = self._parse_by_strategy(selector.get("by", "xpath"))
            value = selector.get("value", "")

            if not value:
                return {"success": False, "data": {"message": "选择器缺少 'value' 字段"}}

            wait = WebDriverWait(driver, timeout, poll_frequency=self.DEFAULT_POLL_FREQUENCY)
            element = wait.until(ec.visibility_of_element_located((by, value)))

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
                "data": {"message": f"等待元素超时（{timeout} 秒）", "selector": selector, "timeout": timeout},
            }
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "data": {"message": f"等待元素失败: {e!s}", "selector": selector, "error": str(e)},
            }

    def _find_element(
        self, driver: WebDriver, element_id: str
    ) -> WebElement | None:
        """内部方法：通过多种定位策略查找元素。

        按照 accessibility_id -> xpath -> class_name 的顺序依次尝试定位。

        Args:
            driver: Appium WebDriver 实例。
            element_id: 元素标识符。

        Returns:
            Optional[WebElement]: 找到的元素对象，未找到则返回 None。
        """
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
    ) -> WebElement | None:
        """内部方法：通过文本内容查找元素。

        使用多种 xpath 策略匹配文本，包括完全匹配和包含匹配。

        Args:
            driver: Appium WebDriver 实例。
            text: 要查找的文本内容。

        Returns:
            Optional[WebElement]: 找到的元素对象，未找到则返回 None。
        """
        text_xpath_strategies = [
            f'//*[@text="{text}"]',
            f'//*[contains(@text, "{text}")]',
            f'//*[@content-desc="{text}"]',
            f'//*[contains(@content-desc, "{text}")]',
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

    def _get_element_info(self, element: WebElement) -> dict:
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
        except Exception:  # noqa: BLE001
            return {
                "tag": "未知",
                "text": "",
                "location": {"x": 0, "y": 0},
                "size": {"width": 0, "height": 0},
            }
