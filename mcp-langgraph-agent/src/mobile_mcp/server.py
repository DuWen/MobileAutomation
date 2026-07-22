"""
MCP Server 实现模块

基于 FastMCP 框架实现移动设备控制协议的服务器端。
通过装饰器方式注册所有工具，使用 DeviceManager 管理设备连接池，
并提供设备操作、UI 交互、视觉获取和断言验证等完整功能。
支持 stdio 和 SSE 两种传输方式，可从配置文件和环境变量加载参数。
"""

import logging
from typing import Dict

from mcp.server.fastmcp import FastMCP

from src.config.settings import settings

from .tools.assertions import AssertToolkit
from .tools.device import DeviceManager
from .tools.ui import UIToolkit
from .tools.vision import VisionToolkit

logger = logging.getLogger(__name__)


class MobileAutomationServer(FastMCP):
    """移动自动化 MCP Server，继承自 FastMCP。

    通过 FastMCP 的装饰器机制注册所有工具方法，每个工具返回
    {"success": bool, "data": ...} 格式的统一响应。
    内部维护一个全局的 DeviceManager 实例管理设备连接池，
    并支持从配置文件动态加载设备列表。
    """

    def __init__(
        self,
        name: str = "mobile-automation",
        appium_url: str | None = None,
        device_config_path: str | None = None,
    ) -> None:
        """初始化移动自动化服务器。

        创建设备管理器及各个工具包实例，注册所有工具，
        并从配置文件加载可用设备列表。

        Args:
            name: 服务器名称，默认为 "mobile-automation"。
            appium_url: Appium Server 地址，为 None 时从全局配置读取。
            device_config_path: 设备配置文件路径，为 None 时从全局配置读取。
        """
        super().__init__(name=name)

        # 从全局配置读取 Appium 地址
        self._appium_url = appium_url or (
            f"http://{settings.APPIUM_HOST}:{settings.APPIUM_PORT}"
            f"{settings.APPIUM_BASE_PATH}"
        )

        # 创建设备管理器（全局共享）
        self._device_manager = DeviceManager(appium_url=self._appium_url)

        # 从配置文件加载设备列表
        config_path = device_config_path or settings.DEVICE_CONFIG_PATH
        self._load_devices_from_config(config_path)

        # 创建各工具包实例
        self._ui_toolkit = UIToolkit(self._device_manager)
        self._vision_toolkit = VisionToolkit(self._device_manager)
        self._assert_toolkit = AssertToolkit(self._device_manager)

        # 注册所有工具
        self._register_tools()
        logger.info("MCP Server 初始化完成，已注册 %d 个工具", 12)

    def _load_devices_from_config(self, config_path: str) -> None:
        """从 YAML 配置文件加载设备列表到 DeviceManager。

        解析设备配置文件，将设备注册到 DeviceManager 的预配置列表中，
        方便后续快速连接。

        Args:
            config_path: 设备配置文件路径（YAML 格式）。
        """
        import yaml

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            devices = data.get("devices", [])
            for dev in devices:
                self._device_manager.register_device_config(
                    device_id=dev.get("id", ""),
                    name=dev.get("name", ""),
                    platform=dev.get("platform", "Android"),
                    udid=dev.get("udid", ""),
                    system_port=dev.get("systemPort", 8200),
                    wda_port=dev.get("wdaPort", 8100),
                )
            logger.info("从 %s 加载了 %d 台设备配置", config_path, len(devices))
        except FileNotFoundError:
            logger.warning("设备配置文件 %s 未找到，跳过设备预加载", config_path)
        except Exception as e:
            logger.error("加载设备配置失败: %s", e)

    def _register_tools(self) -> None:
        """注册所有 MCP 工具到 FastMCP 服务器。

        使用 FastMCP 的 @tool 装饰器注册每个工具方法，
        使其可通过 MCP 协议被客户端调用。
        """
        # ---- 设备管理工具 ----

        @self.tool(
            name="connect_device",
            description="连接指定名称的设备，建立 Appium WebDriver 会话",
        )
        def connect_device(device_name: str) -> Dict:
            """连接指定名称的设备。

            建立与移动设备的 Appium 连接，初始化 WebDriver 会话。
            支持从预加载的设备配置中获取连接参数。

            Args:
                device_name: 设备名称/标识符（预配置的设备 ID 或 udid）。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
                    success 为 True 表示连接成功，data 包含设备信息。
            """
            result = self._device_manager.connect_device(device_name)
            logger.info(
                "connect_device(%s) => success=%s",
                device_name,
                result.get("success"),
            )
            return result

        @self.tool(
            name="disconnect_device",
            description="断开指定名称的设备连接，关闭 WebDriver 会话",
        )
        def disconnect_device(device_name: str) -> Dict:
            """断开指定名称的设备连接。

            关闭设备的 Appium WebDriver 会话并从连接池中移除。

            Args:
                device_name: 要断开连接的设备名称/标识符。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            result = self._device_manager.disconnect_device(device_name)
            logger.info(
                "disconnect_device(%s) => success=%s",
                device_name,
                result.get("success"),
            )
            return result

        @self.tool(
            name="get_device_info",
            description="获取指定设备的详细信息，包括系统版本、屏幕尺寸等",
        )
        def get_device_info(device_name: str) -> Dict:
            """获取指定设备的详细信息。

            查询当前连接设备的系统信息、屏幕尺寸、平台版本等。

            Args:
                device_name: 设备名称/标识符。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
                    success 为 True 时 data 包含设备详细信息。
            """
            result = self._device_manager.get_device_info(device_name)
            # 脱敏后再返回
            return result

        @self.tool(
            name="list_devices",
            description="列出所有已配置的设备及其连接状态",
        )
        def list_devices() -> Dict:
            """列出所有已配置的设备及其连接状态。

            返回预配置的设备列表和当前连接池中的设备信息。

            Returns:
                Dict: {"success": bool, "data": {"configured": [...], "connected": [...]}} 格式的响应。
            """
            return self._device_manager.list_devices()

        # ---- UI 交互工具 ----

        @self.tool(
            name="tap_element",
            description="在设备屏幕指定坐标位置执行点击操作",
        )
        def tap_element(device_name: str, x: int, y: int) -> Dict:
            """在指定坐标位置执行点击操作。

            Args:
                device_name: 设备名称/标识符。
                x: 点击位置的 x 坐标（像素）。
                y: 点击位置的 y 坐标（像素）。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.tap_element(device_name, x, y)

        @self.tool(
            name="tap_by_text",
            description="通过文本内容查找元素并执行点击操作",
        )
        def tap_by_text(device_name: str, text: str) -> Dict:
            """通过文本内容查找元素并点击。

            Args:
                device_name: 设备名称/标识符。
                text: 要查找并点击的文本内容。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.tap_by_text(device_name, text)

        @self.tool(
            name="input_text",
            description="向指定元素输入文本内容，先清除再输入",
        )
        def input_text(
            device_name: str, element_id: str, text: str
        ) -> Dict:
            """向指定元素输入文本内容。

            Args:
                device_name: 设备名称/标识符。
                element_id: 元素标识符（accessibility_id / xpath / class_name）。
                text: 要输入的文本内容。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.input_text(
                device_name, element_id, text
            )

        @self.tool(
            name="swipe",
            description="在设备屏幕上执行滑动操作，从起点滑动到终点",
        )
        def swipe(
            device_name: str,
            start_x: int,
            start_y: int,
            end_x: int,
            end_y: int,
            duration: int = 500,
        ) -> Dict:
            """在设备屏幕上执行滑动操作。

            Args:
                device_name: 设备名称/标识符。
                start_x: 滑动起点的 x 坐标。
                start_y: 滑动起点的 y 坐标。
                end_x: 滑动终点的 x 坐标。
                end_y: 滑动终点的 y 坐标。
                duration: 滑动持续时间（毫秒），默认 500ms。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.swipe(
                device_name, start_x, start_y, end_x, end_y, duration
            )

        @self.tool(
            name="long_press",
            description="在指定坐标位置执行长按操作",
        )
        def long_press(
            device_name: str, x: int, y: int, duration: int = 1000
        ) -> Dict:
            """在指定坐标位置执行长按操作。

            Args:
                device_name: 设备名称/标识符。
                x: 长按位置的 x 坐标（像素）。
                y: 长按位置的 y 坐标（像素）。
                duration: 长按持续时间（毫秒），默认 1000ms。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.long_press(device_name, x, y, duration)

        @self.tool(
            name="press_key",
            description="按下设备物理或系统按键（如返回键、Home 键、Enter 键）",
        )
        def press_key(device_name: str, key_name: str) -> Dict:
            """按下设备物理或系统按键。

            支持常见的 Android/iOS 系统按键操作。

            Args:
                device_name: 设备名称/标识符。
                key_name: 按键名称，如 "back", "home", "enter", "delete" 等。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.press_key(device_name, key_name)

        @self.tool(
            name="scroll",
            description="在设备屏幕上执行方向滚动操作（上/下/左/右）",
        )
        def scroll(
            device_name: str,
            direction: str = "down",
            distance: float = 0.5,
        ) -> Dict:
            """在设备屏幕上执行方向滚动操作。

            Args:
                device_name: 设备名称/标识符。
                direction: 滚动方向，可选 "up"/"down"/"left"/"right"，默认 "down"。
                distance: 滚动距离占屏幕比例（0.0-1.0），默认 0.5。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.scroll(
                device_name, direction, distance
            )

        @self.tool(
            name="wait_for_element",
            description="等待指定元素在设备屏幕中出现并可见",
        )
        def wait_for_element(
            device_name: str, selector: Dict, timeout: int = 10
        ) -> Dict:
            """等待指定元素出现。

            Args:
                device_name: 设备名称/标识符。
                selector: 元素选择器，如 {"by": "xpath", "value": "//button"}。
                timeout: 最大等待时间（秒），默认 10 秒。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._ui_toolkit.wait_for_element(
                device_name, selector, timeout
            )

        # ---- 视觉工具 ----

        @self.tool(
            name="take_screenshot",
            description="获取设备当前屏幕截图，返回 base64 编码的图片数据",
        )
        def take_screenshot(device_name: str) -> Dict:
            """获取设备当前屏幕截图。

            Args:
                device_name: 设备名称/标识符。

            Returns:
                Dict: {"success": bool, "data": {"screenshot": "base64字符串", ...}}。
            """
            return self._vision_toolkit.take_screenshot(device_name)

        @self.tool(
            name="get_ui_tree",
            description="获取设备当前页面的 UI 无障碍树结构（压缩后的 JSON 格式）",
        )
        def get_ui_tree(
            device_name: str, compress: bool = True
        ) -> Dict:
            """获取设备当前页面的 UI 无障碍树结构。

            Args:
                device_name: 设备名称/标识符。
                compress: 是否压缩输出（使用智能压缩器），默认为 True。

            Returns:
                Dict: {"success": bool, "data": {"tree": "...", ...}}。
            """
            return self._vision_toolkit.get_ui_tree(
                device_name, compress
            )

        # ---- 断言工具 ----

        @self.tool(
            name="assert_text_visible",
            description="断言指定文本在设备屏幕上可见，超时则断言失败",
        )
        def assert_text_visible(
            device_name: str, text: str, timeout: int = 10
        ) -> Dict:
            """断言指定文本在设备屏幕上可见。

            Args:
                device_name: 设备名称/标识符。
                text: 要断言的文本内容。
                timeout: 最大等待时间（秒），默认 10 秒。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
                    success 为 True 表示文本可见（断言通过）。
            """
            return self._assert_toolkit.assert_text_visible(
                device_name, text, timeout
            )

        @self.tool(
            name="assert_element_exists",
            description="断言指定元素在设备屏幕上存在",
        )
        def assert_element_exists(
            device_name: str, selector: Dict
        ) -> Dict:
            """断言指定元素存在。

            Args:
                device_name: 设备名称/标识符。
                selector: 元素选择器，如 {"by": "accessibility_id", "value": "btn_ok"}。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
                    success 为 True 表示元素存在（断言通过）。
            """
            return self._assert_toolkit.assert_element_exists(
                device_name, selector
            )

        @self.tool(
            name="assert_page_contains",
            description="断言当前页面源包含指定文本内容",
        )
        def assert_page_contains(
            device_name: str, text: str
        ) -> Dict:
            """断言当前页面源包含指定文本内容。

            通过检查页面源（page source）中是否包含目标文本进行断言，
            适用于 UI 树中不可见但 DOM 中存在的元素验证。

            Args:
                device_name: 设备名称/标识符。
                text: 要断言的文本内容。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
            """
            return self._assert_toolkit.assert_page_contains(
                device_name, text
            )

    def get_registered_tool_names(self) -> list[str]:
        """获取所有已注册的工具名称列表。

        Returns:
            已注册工具名称的列表。
        """
        return list(self._tool_manager._tools.keys())


def create_server(
    name: str = "mobile-automation",
    appium_url: str | None = None,
    device_config_path: str | None = None,
) -> MobileAutomationServer:
    """创建并返回 MobileAutomationServer 实例的工厂函数。

    用于快速创建服务器实例，方便在其他模块中导入和使用。

    Args:
        name: 服务器名称，默认为 "mobile-automation"。
        appium_url: Appium Server 地址，为 None 时从配置读取。
        device_config_path: 设备配置文件路径，为 None 时从配置读取。

    Returns:
        MobileAutomationServer: 配置好的移动自动化服务器实例。
    """
    return MobileAutomationServer(
        name=name,
        appium_url=appium_url,
        device_config_path=device_config_path,
    )


# 主入口：直接运行此文件时启动 MCP 服务器
if __name__ == "__main__":
    transport = settings.MCP_TRANSPORT
    server = create_server()
    logger.info("启动 MCP Server，传输方式: %s", transport)
    server.run(transport=transport)