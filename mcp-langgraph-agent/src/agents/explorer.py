"""探索 Agent 模块。

负责分析测试目标、理解用户意图，获取当前设备界面信息，
为后续规划节点提供上下文。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent
from src.agents.llm import ModelRouter
from src.agents.prompts import EXPLORER_PROMPT
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class ExplorerAgent(BaseAgent):
    """探索 Agent，分析测试目标和界面状态。

    使用 light 层级模型进行界面元素分析和意图理解，
    识别关键功能点，为规划节点提供结构化的探索结果。

    Attributes:
        DEFAULT_MODEL_TIER: 使用 light 层级模型（简单分析任务）
    """

    DEFAULT_MODEL_TIER: str = 'light'

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """初始化 ExplorerAgent。

        Args:
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
        """
        super().__init__(
            name='explorer',
            model_router=model_router,
            token_tracker=token_tracker,
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """运行探索 Agent 的核心逻辑。

        分析测试目标和当前界面状态，识别功能点和关键元素。

        Args:
            **kwargs: 包含以下参数：
                - test_goal: 测试目标描述
                - ui_tree: 当前界面 UI 树
                - screenshot_b64: 当前界面截图 Base64
                - device_name: 设备名称
                - history: 历史操作记录

        Returns:
            探索结果字典，包含 intent_analysis, function_points,
            scope, ui_analysis 等字段
        """
        test_goal: str = kwargs.get('test_goal', '')
        ui_tree: str = kwargs.get('ui_tree', '')
        screenshot_b64: str = kwargs.get('screenshot_b64', '')
        device_name: str = kwargs.get('device_name', '')
        history: list = kwargs.get('history', [])

        # 构建消息序列
        messages = [
            {
                'role': 'system',
                'content': EXPLORER_PROMPT.format(
                    test_goal=test_goal,
                    ui_tree=ui_tree or '(未提供)',
                    screenshot_description='有截图' if screenshot_b64 else '无截图',
                    history=str(history[-5:]) if history else '[]',
                ),
            },
            {
                'role': 'user',
                'content': f'请分析测试目标「{test_goal}」在设备 {device_name} 上的可行性和关键界面元素。',
            },
        ]

        # 调用 LLM 获取分析结果
        response: str = await self.call_llm_async(
            messages=messages,
            model_tier=self.DEFAULT_MODEL_TIER,
            operation='explore',
        )

        # 解析 LLM 返回的 JSON 结果
        exploration_result: dict[str, Any] = self._parse_json_response(
            response,
            fallback={
                'analysis': f'分析测试目标「{test_goal}」的核心意图',
                'progress': 'not_started',
                'next_action': 'plan',
                'reasoning': '基于测试目标描述，建议进入规划阶段',
                'identified_elements': [],
            },
        )

        logger.info(
            f"[ExplorerAgent] 探索完成，下一步: {exploration_result.get('next_action', 'unknown')}"
        )

        return exploration_result

    def _parse_json_response(self, response: str, fallback: dict[str, Any]) -> dict[str, Any]:
        """解析 LLM 返回的 JSON 格式响应。

        尝试从 LLM 回复中提取 JSON 对象，解析失败时返回 fallback 结果。

        Args:
            response: LLM 返回的文本内容
            fallback: 解析失败时使用的默认结果

        Returns:
            解析后的字典结果
        """
        try:
            # 尝试提取 JSON 块（可能被 markdown 代码块包裹）
            text = response.strip()
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("[ExplorerAgent] LLM 返回非 JSON 格式，使用 fallback")
            return fallback
