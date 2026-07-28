"""
视觉工具模块

提供截图和 UI 无障碍树获取等视觉相关功能。
支持截图后的 base64 编码传输，以及无障碍树的获取和智能压缩处理。
压缩模块使用 xml_compressor 实现高压缩率的 UI 树精简。
"""

import base64
import logging
import os
import time

from src.utils.screenshot import compress_screenshot as _compress_screenshot
from src.utils.xml_compressor import compress_xml

from .device import DeviceManager

logger = logging.getLogger(__name__)


class VisionToolkit:
    """视觉工具包，封装截图和 UI 结构获取相关操作。

    提供设备屏幕截图（返回 base64 编码）、无障碍树获取与压缩等功能，
    用于视觉定位和 UI 结构分析。
    """

    # 截图最大宽度（像素），超过则按比例缩放
    SCREENSHOT_MAX_WIDTH: int = 720
    # 截图 JPEG 压缩质量（1-100）
    SCREENSHOT_QUALITY: int = 60

    def __init__(self, device_manager: DeviceManager) -> None:
        """初始化视觉工具包。

        Args:
            device_manager: 设备管理器实例，用于获取设备 WebDriver。
        """
        self._device_manager = device_manager

    def _check_device(self, device_name: str):
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

    def _save_screenshot_to_file(self, screenshot_base64: str, device_name: str) -> str:
        """将截图 base64 数据解码后保存为本地 JPEG 文件。

        基于项目根目录创建 screenshots/ 目录，文件名格式为
        {device_name}_{timestamp}.jpg。

        Args:
            screenshot_base64: base64 编码的截图数据。
            device_name: 设备名称，用于构造文件名。

        Returns:
            保存的截图文件绝对路径；保存失败时返回空字符串。
        """
        try:
            # 基于当前文件位置推导项目根目录（与 device.py 中 APPIUM_HOME 推导方式一致）
            this_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(this_dir)))
            )
            screenshots_dir = os.path.join(project_root, "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)

            # 构造文件名: {device_name}_{timestamp}.jpg
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            safe_device_name = device_name.replace(" ", "_").replace("/", "_")
            filename = f"{safe_device_name}_{timestamp}.jpg"
            file_path = os.path.join(screenshots_dir, filename)

            # 解码 base64 并写入文件
            image_data = base64.b64decode(screenshot_base64)
            with open(file_path, "wb") as f:
                f.write(image_data)

            logger.info("截图已保存到本地文件: %s", file_path)
            return file_path
        except Exception as e:  # noqa: BLE001
            logger.error("截图保存到本地文件失败: %s", e)
            return ""

    def take_screenshot(self, device_name: str) -> dict:
        """获取设备当前屏幕截图，并保存到本地文件。

        通过 Appium WebDriver 截取设备屏幕，返回 base64 编码的图片数据。
        截图会自动进行压缩处理以减小传输大小，同时保存到本地 screenshots/ 目录。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: 是否成功
                - data.screenshot: base64 编码的截图数据
                - data.format: 图片格式（如 "jpeg"）
                - data.original_size: 原始图片大小（字节）
                - data.compressed_size: 压缩后大小（字节）
                - data.file_path: 截图保存的本地文件路径
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            # 获取原始截图数据（base64）
            screenshot_base64 = driver.get_screenshot_as_base64()

            # 使用 screenshot 工具模块进行压缩
            compressed_base64 = _compress_screenshot(
                screenshot_base64,
                max_width=self.SCREENSHOT_MAX_WIDTH,
                quality=self.SCREENSHOT_QUALITY,
            )

            original_size = len(base64.b64decode(screenshot_base64))
            compressed_size = len(base64.b64decode(compressed_base64))

            # 将截图保存到本地文件
            file_path = self._save_screenshot_to_file(compressed_base64, device_name)

            return {
                "success": True,
                "data": {
                    "screenshot": compressed_base64,
                    "format": "jpeg",
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": round(compressed_size / original_size, 4) if original_size > 0 else 0,
                    "device_name": device_name,
                    "file_path": file_path,
                },
            }
        except Exception as e:  # noqa: BLE001
            logger.error("截图失败: %s", e)
            return {
                "success": False,
                "data": {"message": f"截图失败: {e!s}", "device_name": device_name, "error": str(e)},
            }

    def get_ui_tree(
        self, device_name: str, compress: bool = True, aggressive: bool = False
    ) -> dict:
        """获取设备当前页面的 UI 无障碍树结构。

        通过 Appium 获取页面源（page source），即 XML 格式的无障碍树。
        开启压缩时使用 xml_compressor 智能压缩器，实现 95%+ 压缩率。

        Args:
            device_name: 设备名称/标识符。
            compress: 是否压缩输出，为 True 时使用智能压缩器输出 JSON 格式。
                默认为 True。
            aggressive: 是否启用激进过滤模式，过滤无交互/无文本的装饰性
                叶子节点（如纯装饰 ImageView）。默认 False 保持向后兼容。
                启用后可进一步降低 Token 消耗，但状态语义类（ProgressBar/
                Switch/TextView 等）始终保留。仅在 compress=True 时生效。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: 是否成功
                - data.tree: UI 无障碍树结构（压缩后为 JSON 字符串，未压缩为 XML 字符串）
                - data.compressed: 是否已压缩
                - data.aggressive: 是否启用了激进过滤模式
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            page_source = driver.page_source

            if compress:
                # 使用 xml_compressor 进行智能压缩（输出 JSON 格式）
                compressed_tree = compress_xml(page_source, aggressive=aggressive)
                return {
                    "success": True,
                    "data": {
                        "tree": compressed_tree,
                        "format": "json",
                        "compressed": True,
                        "aggressive": aggressive,
                        "original_size": len(page_source),
                        "compressed_size": len(compressed_tree),
                        "device_name": device_name,
                    },
                }
            else:
                return {
                    "success": True,
                    "data": {
                        "tree": page_source,
                        "format": "xml",
                        "compressed": False,
                        "aggressive": False,
                        "size": len(page_source),
                        "device_name": device_name,
                    },
                }
        except Exception as e:  # noqa: BLE001
            logger.error("获取 UI 树失败: %s", e)
            return {
                "success": False,
                "data": {"message": f"获取 UI 树失败: {e!s}", "device_name": device_name, "error": str(e)},
            }
