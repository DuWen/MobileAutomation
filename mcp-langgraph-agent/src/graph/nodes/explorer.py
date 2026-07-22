"""
探索节点模块。

负责调用 LLM 分析测试目标、理解用户意图，
并获取当前设备界面信息（UI 树 + 截图），为后续规划提供上下文。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.prompts import EXPLORER_PROMPT

logger = logging.getLogger(__name__)


async def explorer_node(state: AgentState) -> Dict[str, Any]:
    """
    探索节点的主函数。

    该节点负责：
    1. 接收用户输入的测试目标（自然语言）
    2. 调用 LLM 分析测试目标，理解用户意图
    3. 获取当前设备界面信息（UI 无障碍树 + 截图）
    4. 输出对测试目标的理解和对界面元素的分析

    Args:
        state: 当前 Agent 状态，包含 test_goal、device_name 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info(f"[Explorer] 开始探索测试目标: {state.get('test_goal', '')}")

    # 提取当前状态中的关键信息
    test_goal: str = state.get("test_goal", "")
    device_name: str = state.get("device_name", "")

    # 构建 LLM 调用消息序列，使用 prompts.py 中的模板
    messages = [
        {
            "role": "system",
            "content": EXPLORER_PROMPT.format(
                test_goal=test_goal,
                ui_tree=state.get("ui_tree", ""),
                screenshot_description="有截图" if state.get("screenshot_b64") else "无截图",
                history=str(state.get("messages", [])[-5:] if state.get("messages") else []),
            ),
        },
    ]

    # TODO: 在此处调用实际的 LLM API（如 OpenAI / Claude）
    # 当前为模拟实现，返回占位分析结果
    exploration_result = {
        "intent_analysis": f"分析测试目标「{test_goal}」的核心意图",
        "function_points": ["功能点 1", "功能点 2", "功能点 3"],
        "scope": "功能测试",
        "ui_analysis": f"设备 {device_name} 的当前界面元素分析",
    }

    # 模拟获取设备 UI 信息
    ui_tree: str = state.get("ui_tree") or ""
    screenshot_b64: str = state.get("screenshot_b64") or ""

    logger.info(f"[Explorer] 探索完成，识别到 {len(exploration_result['function_points'])} 个功能点")

    return {
        "node_outputs": {
            **state.get("node_outputs", {}),
            "explorer": exploration_result,
        },
        "messages": [
            *state.get("messages", []),
            {"role": "assistant", "content": f"探索节点完成：{exploration_result}"},
        ],
        "total_tokens_used": state.get("total_tokens_used", 0) + 0,
    }