"""
MCP Server 实现模块

基于 FastMCP 框架实现移动设备控制协议的服务器端。
通过装饰器方式注册所有工具，使用 DeviceManager 管理设备连接池，
并提供设备操作、UI 交互、视觉获取和断言验证等完整功能。
"""

from typing import Dict

from mcp.server.fastmcp import FastMCP

from .tools.assert import AssertToolkit
from .tools.device import DeviceManager
from .tools.ui import UIToolkit
from .tools.vision import VisionToolkit


class MobileAutomationServer(FastMCP):
    """移动自动化 MCP Server，继承自 FastMCP。

    通过 FastMCP 的装饰器机制注册所有工具方法，每个工具返回
    {"success": bool, "data": ...} 格式的统一响应。
    内部维护一个全局的 DeviceManager 实例管理设备连接池。
    """

    def __init__(self, name: str = "mobile-automation") -> None:
        """初始化移动自动化服务器。

        创建设备管理器及各个工具包实例，并注册所有工具。

        Args:
            name: 服务器名称，默认为 "mobile-automation"。
        """
        super().__init__(name=name)

        # 创建设备管理器（全局共享）
        self._device_manager = DeviceManager()
        # 创建各工具包实例
        self._ui_toolkit = UIToolkit(self._device_manager)
        self._vision_toolkit = VisionToolkit(self._device_manager)
        self._assert_toolkit = AssertToolkit(self._device_manager)

        # 注册所有工具
        self._register_tools()

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

            Args:
                device_name: 设备名称/标识符（如 Android udid 或 iOS deviceName）。

            Returns:
                Dict: {"success": bool, "data": {...}} 格式的响应。
                    success 为 True 表示连接成功，data 包含设备信息。
            """
            return self._device_manager.connect_device(device_name)

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
            return self._device_manager.disconnect_device(device_name)

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
            return self._device_manager.get_device_info(device_name)

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
            description="获取设备当前页面的 UI 无障碍树结构（XML 格式）",
        )
        def get_ui_tree(
            device_name: str, compress: bool = True
        ) -> Dict:
            """获取设备当前页面的 UI 无障碍树结构。

            Args:
                device_name: 设备名称/标识符。
                compress: 是否压缩输出（移除冗余属性），默认为 True。

            Returns:
                Dict: {"success": bool, "data": {"tree": "XML字符串", ...}}。
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


def create_server() -> MobileAutomationServer:
    """创建并返回 MobileAutomationServer 实例的工厂函数。

    用于快速创建服务器实例，方便在其他模块中导入和使用。

    Returns:
        MobileAutomationServer: 配置好的移动自动化服务器实例。
    """
    return MobileAutomationServer()


# 主入口：直接运行此文件时启动 MCP 服务器
if __name__ == "__main__":
    server = create_server()
    # 启动 MCP 服务器（默认使用 stdio 传输）
    server.run(transport="stdio")