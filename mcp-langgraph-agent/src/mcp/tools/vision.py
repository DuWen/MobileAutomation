"""
视觉工具模块

提供截图和 UI 无障碍树获取等视觉相关功能。
支持截图后的 base64 编码传输，以及无障碍树的获取和压缩处理。
"""

import base64
import json
from typing import Dict, Optional

from io import BytesIO

from PIL import Image

from .device import DeviceManager


class VisionToolkit:
    """视觉工具包，封装截图和 UI 结构获取相关操作。

    提供设备屏幕截图（返回 base64 编码）、无障碍树获取与压缩等功能，
    用于视觉定位和 UI 结构分析。
    """

    # 截图压缩质量（1-100），数值越小压缩率越高
    SCREENSHOT_QUALITY: int = 60
    # 截图最大尺寸（像素），超过则按比例缩放
    SCREENSHOT_MAX_SIZE: int = 1920

    def __init__(self, device_manager: DeviceManager) -> None:
        """初始化视觉工具包。

        Args:
            device_manager: 设备管理器实例，用于获取设备 WebDriver。
        """
        self._device_manager = device_manager

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
                - data.format: 图片格式（如 "png"）
                - data.size: 原始图片大小（字节）
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 获取原始截图数据（base64）
            screenshot_base64 = driver.get_screenshot_as_base64()

            # 解码并进行压缩处理
            screenshot_data = base64.b64decode(screenshot_base64)
            compressed_data = self._compress_image(screenshot_data)

            # 重新编码为 base64
            compressed_base64 = base64.b64encode(compressed_data).decode(
                "utf-8"
            )

            return {
                "success": True,
                "data": {
                    "screenshot": compressed_base64,
                    "format": "png",
                    "original_size": len(screenshot_data),
                    "compressed_size": len(compressed_data),
                    "device_name": device_name,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"截图失败: {str(e)}",
                    "device_name": device_name,
                    "error": str(e),
                },
            }

    def get_ui_tree(
        self, device_name: str, compress: bool = True
    ) -> Dict:
        """获取设备当前页面的 UI 无障碍树结构。

        通过 Appium 获取页面源（page source），即 XML 格式的无障碍树。
        可选择压缩输出以减小数据传输量，去除不必要的属性信息。

        Args:
            device_name: 设备名称/标识符。
            compress: 是否压缩输出，为 True 时移除冗余属性以减小数据量。
                默认为 True。

        Returns:
            Dict: 操作结果，包含 success 和 data 字段。
                - success: 是否成功
                - data.tree: UI 无障碍树结构（XML 字符串）
                - data.compressed: 是否已压缩
        """
        driver = self._device_manager.get_driver(device_name)
        if driver is None:
            return {
                "success": False,
                "data": {"message": f"设备 '{device_name}' 未连接"},
            }

        try:
            # 获取页面源（XML 格式的无障碍树）
            page_source = driver.page_source

            if compress:
                # 压缩处理：移除冗余属性
                page_source = self._compress_ui_tree(page_source)

            return {
                "success": True,
                "data": {
                    "tree": page_source,
                    "compressed": compress,
                    "size": len(page_source),
                    "device_name": device_name,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "data": {
                    "message": f"获取 UI 树失败: {str(e)}",
                    "device_name": device_name,
                    "error": str(e),
                },
            }

    def _compress_image(self, image_data: bytes) -> bytes:
        """内部方法：压缩图片数据以减小传输大小。

        通过调整图片尺寸和降低质量来压缩图片。如果图片尺寸超过
        最大限制，则按比例缩放；然后调整质量参数进行压缩。

        Args:
            image_data: 原始图片的二进制数据。

        Returns:
            bytes: 压缩后的图片二进制数据。
        """
        try:
            # 打开图片
            img = Image.open(BytesIO(image_data))

            # 如果图片尺寸超过最大限制，按比例缩放
            original_width, original_height = img.size
            if max(original_width, original_height) > self.SCREENSHOT_MAX_SIZE:
                ratio = self.SCREENSHOT_MAX_SIZE / max(
                    original_width, original_height
                )
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                img = img.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS
                )

            # 保存压缩后的图片
            output = BytesIO()
            # 转换为 RGB 模式（移除 alpha 通道）以减小大小
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(output, format="PNG", optimize=True)
            compressed_data = output.getvalue()

            # 如果 PNG 压缩后仍然较大，尝试 JPEG 格式
            if len(compressed_data) > 500 * 1024:  # 超过 500KB
                output_jpeg = BytesIO()
                # 对于 JPEG，需要先转换为 RGB
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(
                    output_jpeg,
                    format="JPEG",
                    quality=self.SCREENSHOT_QUALITY,
                    optimize=True,
                )
                compressed_data = output_jpeg.getvalue()

            return compressed_data

        except Exception:
            # 压缩失败时返回原始数据
            return image_data

    def _compress_ui_tree(self, xml_content: str) -> str:
        """内部方法：压缩 UI 无障碍树 XML 内容。

        移除不必要的 XML 属性（如坐标偏移、冗余描述等），
        保留核心结构信息以减小数据量。

        Args:
            xml_content: 原始 XML 格式的无障碍树内容。

        Returns:
            str: 压缩后的 XML 内容。
        """
        try:
            # 保留关键属性，移除冗余属性
            # 需要保留的属性列表
            keep_attributes = [
                "class",
                "text",
                "resource-id",
                "content-desc",
                "bounds",
                "clickable",
                "focusable",
                "enabled",
                "checked",
                "selected",
                "index",
                "package",
            ]

            # 使用简单字符串替换方法移除不需要的属性
            # 注意：这是简化实现，实际使用中建议使用 XML 解析器
            import re

            def _clean_attributes(match):
                """清理匹配标签中的属性，只保留需要的属性。"""
                tag = match.group(0)
                # 找到所有属性
                attr_pattern = r'(\w+(?:-\w+)*)\s*=\s*"([^"]*)"'
                attrs = re.findall(attr_pattern, tag)

                # 提取标签名
                tag_name_match = re.match(r"<(\w+)", tag)
                tag_name = (
                    tag_name_match.group(1) if tag_name_match else "node"
                )

                # 只保留需要的属性
                kept_attrs = []
                for attr_name, attr_value in attrs:
                    if attr_name in keep_attributes:
                        kept_attrs.append(f'{attr_name}="{attr_value}"')

                # 重建标签
                if kept_attrs:
                    return f"<{tag_name} {' '.join(kept_attrs)}>"
                else:
                    return f"<{tag_name}>"

            # 处理开始标签
            compressed = re.sub(
                r"<(\w+)([^>]*?)>", _clean_attributes, xml_content
            )

            return compressed

        except Exception:
            # 压缩失败时返回原始内容
            return xml_content