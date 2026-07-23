"""混合感知策略模块。

实现无障碍树优先 + 截图降级的混合感知策略。
优先获取 UI 无障碍树（Token 消耗极低），当无障碍树获取失败
或信息不足时自动降级到截图模式（Token 消耗高但信息更全面）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 感知模式枚举
# ============================================================


class PerceptionMode(Enum):
    """感知模式。

    定义设备界面信息获取的策略模式：
    - UI_TREE: 优先使用无障碍树（Token 消耗低）
    - SCREENSHOT: 使用截图模式（Token 消耗高，信息全面）
    - HYBRID: 混合模式，UI 树优先，截图降级
    """

    UI_TREE = "ui_tree"
    SCREENSHOT = "screenshot"
    HYBRID = "hybrid"


# ============================================================
# 感知结果数据结构
# ============================================================


@dataclass
class PerceptionResult:
    """感知结果。

    封装混合感知策略获取到的界面信息，包括 UI 树和截图。

    Attributes:
        ui_tree: 精简后的无障碍树 JSON 字符串
        screenshot_b64: 截图 Base64 编码字符串
        mode: 实际使用的感知模式
        ui_tree_available: 无障碍树是否成功获取
        screenshot_available: 截图是否成功获取
        ui_tree_size_bytes: UI 树数据大小（字节）
        screenshot_size_bytes: 截图数据大小（字节）
    """

    ui_tree: str
    screenshot_b64: str
    mode: PerceptionMode
    ui_tree_available: bool
    screenshot_available: bool
    ui_tree_size_bytes: int = 0
    screenshot_size_bytes: int = 0


# ============================================================
# HybridPerception 类
# ============================================================


class HybridPerception:
    """混合感知策略。

    实现 UI 树优先 + 截图降级的混合感知策略：
    1. 优先尝试获取 UI 无障碍树（Token 消耗仅为截图的 1/10~1/50）
    2. 如果 UI 树获取失败，自动降级到截图模式
    3. 在验证等关键场景，可同时获取两种信息

    降级条件：
    - get_ui_tree 返回失败
    - UI 树元素数量过少（空页面或解析异常）
    - 用户明确指定截图模式

    用法:
        perception = HybridPerception(mcp_client=client)
        result = await perception.perceive("emulator-5554")
        if result.ui_tree_available:
            # 使用 UI 树进行分析
            ...
        elif result.screenshot_available:
            # 降级使用截图分析
            ...
    """

    # UI 树元素数量阈值：低于此值认为信息不足
    MIN_UI_TREE_ELEMENTS: int = 3
    # 截图最大宽度
    SCREENSHOT_MAX_WIDTH: int = 1080
    # 截图压缩质量
    SCREENSHOT_QUALITY: int = 75

    def __init__(self, mcp_client: Any = None) -> None:
        """初始化混合感知策略。

        Args:
            mcp_client: MCP 客户端实例，用于调用 get_ui_tree 和 take_screenshot 工具
        """
        self._mcp_client = mcp_client

    async def perceive(
        self,
        device_name: str,
        mode: PerceptionMode = PerceptionMode.HYBRID,
        force_screenshot: bool = False,
    ) -> PerceptionResult:
        """获取设备当前界面的感知信息。

        根据指定的感知模式获取 UI 树和/或截图信息。
        在 HYBRID 模式下，优先获取 UI 树，失败时自动降级到截图。

        Args:
            device_name: 设备名称/标识符
            mode: 感知模式，默认 HYBRID
            force_screenshot: 是否强制获取截图（即使 UI 树成功）

        Returns:
            PerceptionResult: 感知结果，包含 UI 树和截图信息
        """
        ui_tree: str = ""
        screenshot_b64: str = ""
        ui_tree_available: bool = False
        screenshot_available: bool = False
        ui_tree_size: int = 0
        screenshot_size: int = 0

        # 根据模式获取信息
        if mode in (PerceptionMode.UI_TREE, PerceptionMode.HYBRID):
            # 尝试获取 UI 树
            ui_tree, ui_tree_available, ui_tree_size = await self._get_ui_tree(device_name)

        if mode in (PerceptionMode.SCREENSHOT, PerceptionMode.HYBRID):
            # 判断是否需要截图
            need_screenshot = (
                mode == PerceptionMode.SCREENSHOT
                or force_screenshot
                or (mode == PerceptionMode.HYBRID and not ui_tree_available)
            )
            if need_screenshot:
                screenshot_b64, screenshot_available, screenshot_size = await self._get_screenshot(
                    device_name
                )

        # 确定实际使用的模式
        actual_mode = mode
        if mode == PerceptionMode.HYBRID:
            if ui_tree_available and not screenshot_available:
                actual_mode = PerceptionMode.UI_TREE
            elif not ui_tree_available and screenshot_available:
                actual_mode = PerceptionMode.SCREENSHOT
            elif ui_tree_available and screenshot_available:
                actual_mode = PerceptionMode.HYBRID

        result = PerceptionResult(
            ui_tree=ui_tree,
            screenshot_b64=screenshot_b64,
            mode=actual_mode,
            ui_tree_available=ui_tree_available,
            screenshot_available=screenshot_available,
            ui_tree_size_bytes=ui_tree_size,
            screenshot_size_bytes=screenshot_size,
        )

        logger.info(
            "[HybridPerception] 感知完成: mode=%s, ui_tree=%s(%dB), screenshot=%s(%dB)",
            actual_mode.value,
            ui_tree_available,
            ui_tree_size,
            screenshot_available,
            screenshot_size,
        )

        return result

    async def _get_ui_tree(self, device_name: str) -> tuple[str, bool, int]:
        """获取 UI 无障碍树。

        调用 MCP 工具获取并压缩 UI 树，检查结果有效性。

        Args:
            device_name: 设备名称

        Returns:
            (ui_tree_json, 是否成功, 数据大小字节) 的元组
        """
        if not self._mcp_client:
            logger.warning("[HybridPerception] MCP 客户端未配置，无法获取 UI 树")
            return "", False, 0

        try:
            result = await self._mcp_client.call_tool(
                "get_ui_tree",
                {"device_name": device_name, "compress": True},
            )

            if isinstance(result, dict) and result.get("success"):
                tree_data = result.get("data", {})
                ui_tree = tree_data.get("tree", "")
                size = tree_data.get("compressed_size", len(ui_tree))

                # 检查 UI 树元素数量是否足够
                if self._is_ui_tree_sufficient(ui_tree):
                    return ui_tree, True, size
                else:
                    logger.warning("[HybridPerception] UI 树元素不足，可能需要降级到截图")
                    return ui_tree, False, size
            else:
                error_msg = result.get("data", {}).get("message", "未知错误") if isinstance(result, dict) else str(result)
                logger.warning("[HybridPerception] 获取 UI 树失败: %s", error_msg)
                return "", False, 0

        except Exception as e:
            logger.warning("[HybridPerception] 获取 UI 树异常: %s", e)
            return "", False, 0

    async def _get_screenshot(self, device_name: str) -> tuple[str, bool, int]:
        """获取设备截图。

        调用 MCP 工具获取压缩后的截图。

        Args:
            device_name: 设备名称

        Returns:
            (screenshot_base64, 是否成功, 数据大小字节) 的元组
        """
        if not self._mcp_client:
            logger.warning("[HybridPerception] MCP 客户端未配置，无法获取截图")
            return "", False, 0

        try:
            result = await self._mcp_client.call_tool(
                "take_screenshot",
                {"device_name": device_name},
            )

            if isinstance(result, dict) and result.get("success"):
                data = result.get("data", {})
                screenshot = data.get("screenshot", "")
                size = data.get("compressed_size", 0)
                return screenshot, True, size
            else:
                error_msg = result.get("data", {}).get("message", "未知错误") if isinstance(result, dict) else str(result)
                logger.warning("[HybridPerception] 获取截图失败: %s", error_msg)
                return "", False, 0

        except Exception as e:
            logger.warning("[HybridPerception] 获取截图异常: %s", e)
            return "", False, 0

    def _is_ui_tree_sufficient(self, ui_tree: str) -> bool:
        """检查 UI 树信息是否足够用于分析。

        通过简单的元素计数判断 UI 树是否包含足够的交互信息。

        Args:
            ui_tree: UI 树 JSON 字符串

        Returns:
            UI 树信息是否足够
        """
        if not ui_tree:
            return False

        try:
            import json
            data = json.loads(ui_tree)
            compressed_tree = data.get("compressed_tree", {})

            # 递归计算元素数量
            def count_elements(node: dict) -> int:
                count = 1
                for child in node.get("children", []):
                    count += count_elements(child)
                return count

            element_count = count_elements(compressed_tree) if compressed_tree else 0
            return element_count >= self.MIN_UI_TREE_ELEMENTS

        except (json.JSONDecodeError, AttributeError):
            return False

    def estimate_token_savings(self, result: PerceptionResult) -> Dict[str, Any]:
        """估算当前感知策略相比纯截图模式的 Token 节省量。

        基于 UI 树和截图的数据大小估算 Token 节省比例。
        经验值：1 字节约等于 0.25 Token，截图的视觉 Token 约为
        同等文本的 5-10 倍。

        Args:
            result: 感知结果

        Returns:
            节省估算字典，包含 estimated_tokens_savings、savings_ratio 等
        """
        ui_tree_tokens = result.ui_tree_size_bytes * 0.25 if result.ui_tree_available else 0
        screenshot_tokens = result.screenshot_size_bytes * 2.0 if result.screenshot_available else 0

        # 纯截图模式的估算
        screenshot_only_tokens = screenshot_tokens if result.screenshot_available else (
            result.screenshot_size_bytes * 2.0 if result.screenshot_size_bytes > 0 else 50000
        )

        actual_tokens = ui_tree_tokens + screenshot_tokens
        savings = screenshot_only_tokens - actual_tokens
        savings_ratio = savings / screenshot_only_tokens if screenshot_only_tokens > 0 else 0

        return {
            "ui_tree_tokens": int(ui_tree_tokens),
            "screenshot_tokens": int(screenshot_tokens),
            "total_tokens": int(actual_tokens),
            "screenshot_only_tokens": int(screenshot_only_tokens),
            "estimated_tokens_savings": int(savings),
            "savings_ratio": round(savings_ratio, 2),
            "mode_used": result.mode.value,
        }
