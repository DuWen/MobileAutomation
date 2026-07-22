"""探索节点模块。

负责调用 ExplorerAgent 分析测试目标、理解用户意图，
并获取当前设备界面信息（UI 树 + 截图），为后续规划提供上下文。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.explorer import ExplorerAgent
from src.agents.llm import ModelRouter
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_explorer_agent: ExplorerAgent | None = None


def get_explorer_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
) -> ExplorerAgent:
    """获取或创建 ExplorerAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例

    Returns:
        ExplorerAgent 实例
    """
    global _explorer_agent
    if _explorer_agent is None:
        _explorer_agent = ExplorerAgent(
            model_router=model_router,
            token_tracker=token_tracker,
        )
    return _explorer_agent


async def explorer_node(state: AgentState) -> Dict[str, Any]:
    """探索节点的主函数。

    调用 ExplorerAgent 分析测试目标和界面状态，
    识别功能点和关键元素，为规划节点提供结构化上下文。

    Args:
        state: 当前 Agent 状态，包含 test_goal、device_name、ui_tree、screenshot_b64 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info(f"[Explorer] 开始探索测试目标: {state.get('test_goal', '')}")

    # 获取 Agent 实例
    agent: ExplorerAgent = get_explorer_agent()

    # 调用 Agent 执行探索
    exploration_result: Dict[str, Any] = await agent.run(
        test_goal=state.get('test_goal', ''),
        ui_tree=state.get('ui_tree', ''),
        screenshot_b64=state.get('screenshot_b64', ''),
        device_name=state.get('device_name', ''),
        history=state.get('messages', []),
    )

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(
        f"[Explorer] 探索完成，下一步: {exploration_result.get('next_action', 'unknown')}"
    )

    return {
        'node_outputs': {
            **state.get('node_outputs', {}),
            'explorer': exploration_result,
        },
        'messages': [
            *state.get('messages', []),
            {
                'role': 'assistant',
                'content': f"探索完成：{exploration_result.get('analysis', '')}",
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
