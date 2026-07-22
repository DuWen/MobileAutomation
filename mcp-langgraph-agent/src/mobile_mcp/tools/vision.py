"""
视觉工具模块

提供截图和 UI 无障碍树获取等视觉相关功能。
支持截图后的 base64 编码传输，以及无障碍树的获取和智能压缩处理。
压缩模块使用 xml_compressor 实现高压缩率的 UI 树精简。
"""

import base64
import logging
from typing import Dict



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

        Args:
            device_name: 设备名称/标识符。

        Returns:
            WebDriver 实例，设备未连接时返回 None。
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            logger.warning("设备 '%s' 未连接", device_name)
        return driver

    def take_screenshot(self, device_name: str) -> Dict:
        """获取设备当前屏幕截图。

        通过 Appium WebDriver 截取设备屏幕，返回 base64 编码的图片数据。
        截图会自动进行压缩处理以减小传输大小。

        Args:
            device_name: 设备名称/标识符。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: 是否成功
                - data.screenshot: base64 编码的截图数据
                - data.format: 图片格式（如 "jpeg"）
                - data.original_size: 原始图片大小（字节）
                - data.compressed_size: 压缩后大小（字节）
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

            return {
                "success": True,
                "data": {
                    "screenshot": compressed_base64,
                    "format": "jpeg",
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": round(compressed_size / original_size, 4) if original_size > 0 else 0,
                    "device_name": device_name,
                },
            }
        except Exception as e:
            logger.error("截图失败: %s", e)
            return {
                "success": False,
                "data": {"message": f"截图失败: {str(e)}", "device_name": device_name, "error": str(e)},
            }

    def get_ui_tree(
        self, device_name: str, compress: bool = True
    ) -> Dict:
        """获取设备当前页面的 UI 无障碍树结构。

        通过 Appium 获取页面源（page source），即 XML 格式的无障碍树。
        开启压缩时使用 xml_compressor 智能压缩器，实现 95%+ 压缩率。

        Args:
            device_name: 设备名称/标识符。
            compress: 是否压缩输出，为 True 时使用智能压缩器输出 JSON 格式。
                默认为 True。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: 是否成功
                - data.tree: UI 无障碍树结构（压缩后为 JSON 字符串，未压缩为 XML 字符串）
                - data.compressed: 是否已压缩
        """
        driver = self._check_device(device_name)
        if driver is None:
            return {"success": False, "data": {"message": f"设备 '{device_name}' 未连接"}}

        try:
            page_source = driver.page_source

            if compress:
                # 使用 xml_compressor 进行智能压缩（输出 JSON 格式）
                compressed_tree = compress_xml(page_source)
                return {
                    "success": True,
                    "data": {
                        "tree": compressed_tree,
                        "format": "json",
                        "compressed": True,
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
                        "size": len(page_source),
                        "device_name": device_name,
                    },
                }
        except Exception as e:
            logger.error("获取 UI 树失败: %s", e)
            return {
                "success": False,
                "data": {"message": f"获取 UI 树失败: {str(e)}", "device_name": device_name, "error": str(e)},
            }
