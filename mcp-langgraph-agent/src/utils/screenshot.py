"""截图压缩工具模块。

提供移动端截图的压缩功能，包括调整尺寸和降低 JPEG 质量，
以减少传输和存储开销。
"""

import base64
from io import BytesIO

from PIL import Image


def compress_screenshot(
    b64_str: str,
    max_width: int = 720,
    quality: int = 60,
) -> str:
    """压缩截图：调整尺寸和降低 JPEG 质量。

    将 base64 编码的截图解码后，按指定最大宽度等比例缩放，
    再以 JPEG 格式重新编码，以显著减小数据量。

    Args:
        b64_str: 原始截图的 base64 编码字符串（不含 data:image 前缀）
        max_width: 压缩后的最大宽度（像素），默认 720
        quality: JPEG 压缩质量（1-100），默认 60

    Returns:
        压缩后截图的 base64 编码字符串（不含 data:image 前缀）

    Raises:
        ValueError: 输入的 base64 字符串无效或无法解码为图片
        ImportError: 缺少 Pillow 依赖

    Example:
        >>> compressed = compress_screenshot(original_b64, max_width=480, quality=50)
        >>> len(compressed) < len(original_b64)
        True
    """
    try:
        # 解码 base64 为二进制数据
        image_data = base64.b64decode(b64_str)
    except Exception as e:
        raise ValueError(f"无效的 base64 编码字符串: {e}") from e

    try:
        # 打开图片
        img = Image.open(BytesIO(image_data))
    except Exception as e:
        raise ValueError(f"无法解码图片数据: {e}") from e

    # 转换为 RGB 模式（JPEG 不支持 RGBA/透明度通道）
    if img.mode in ('RGBA', 'LA', 'P'):
        # 创建白色背景，保留透明度信息
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])  # 使用 Alpha 通道作为蒙版
            img = background
        else:
            img = img.convert('RGB')

    # 按最大宽度等比例缩放
    original_width, original_height = img.size
    if original_width > max_width:
        scale_ratio = max_width / original_width
        new_width = max_width
        new_height = int(original_height * scale_ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 以 JPEG 格式压缩并编码为 base64
    buffer = BytesIO()
    try:
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
    except Exception as e:
        raise ValueError(f"图片压缩失败: {e}") from e

    compressed_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return compressed_b64


def get_screenshot_size(b64_str: str) -> int:
    """获取 base64 编码截图的大小（字节）。

    Args:
        b64_str: base64 编码的截图字符串

    Returns:
        原始数据大小（字节数）

    Example:
        >>> size = get_screenshot_size(b64_str)
        >>> print(f"截图大小: {size / 1024:.1f} KB")
    """
    return len(base64.b64decode(b64_str))


def estimate_compression_ratio(
    original_b64: str,
    compressed_b64: str,
) -> float:
    """估算压缩率。

    计算原始截图和压缩后截图的大小比例。

    Args:
        original_b64: 原始截图的 base64 编码
        compressed_b64: 压缩后截图的 base64 编码

    Returns:
        压缩率（压缩后大小 / 原始大小），小于 1 表示压缩有效

    Example:
        >>> ratio = estimate_compression_ratio(orig, comp)
        >>> print(f"压缩率: {ratio:.1%}, 节省: {(1-ratio):.1%}")
    """
    original_size = get_screenshot_size(original_b64)
    compressed_size = get_screenshot_size(compressed_b64)
    if original_size == 0:
        return 1.0
    return compressed_size / original_size
