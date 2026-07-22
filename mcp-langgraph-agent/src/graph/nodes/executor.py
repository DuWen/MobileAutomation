"""
执行节点模块。

负责执行当前测试步骤，调用 MCP 工具（tap、input、swipe 等），
并记录执行结果和截图。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.graph.state import AgentState
from src.agents.prompts import EXECUTOR_PROMPT

logger = logging.getLogger(__name__)


async def executor_node(state: AgentState) -> Dict[str, Any]:
    """
    执行节点的主函数。

    该节点负责：
    1. 根据 current_step_index 获取当前测试步骤
    2. 调用 LLM 分析当前步骤并决定需要执行的 MCP 工具操作
    3. 调用 MCP 工具（tap、input、swipe 等）执行操作
    4. 记录执行结果、截图和状态
    5. 更新 executed_steps 列表

    Args:
        state: 当前 Agent 状态，包含 test_steps、current_step_index、
               ui_tree、screenshot_b64 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - executed_steps: 新增的执行记录
            - ui_tree: 执行后的 UI 树（可能更新）
            - screenshot_b64: 执行后的截图（可能更新）
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
            - error: 执行出错时填充的错误信息
    """
    current_step_index: int = state.get("current_step_index", 0)
    test_steps: List[str] = state.get("test_steps", [])

    if current_step_index >= len(test_steps):
        logger.warning(f"[Executor] 步骤索引 {current_step_index} 超出范围，总步骤数 {len(test_steps)}")
        return {
            "error": f"步骤索引 {current_step_index} 超出范围",
            "node_outputs": {
                **state.get("node_outputs", {}),
                "executor": {"error": "索引越界"},
            },
        }

    current_step: str = test_steps[current_step_index]
    logger.info(f"[Executor] 开始执行步骤 [{current_step_index + 1}/{len(test_steps)}]: {current_step}")

    # 构建 LLM 调用消息序列，使用 prompts.py 中的模板
    plan_context: str = str(state.get("test_plan", {}))
    history: str = str(state.get("executed_steps", [])[-3:])  # 最近 3 条历史
    messages = [
        {
            "role": "system",
            "content": EXECUTOR_PROMPT.format(
                current_step=current_step,
                ui_tree=state.get("ui_tree", ""),
                screenshot_description="有截图" if state.get("screenshot_b64") else "无截图",
                plan_context=plan_context,
                history=history,
            ),
        },
    ]

    # TODO: 在此处调用 LLM API 解析步骤并决定 MCP 工具调用
    # 当前为模拟实现，生成占位执行记录
    execution_result: dict = {
        "step": current_step,
        "step_index": current_step_index,
        "action": f"模拟执行: {current_step}",
        "result": "操作执行成功",
        "screenshot": state.get("screenshot_b64", ""),
        "passed": True,
        "timestamp": "2025-01-01T00:00:00Z",
    }

    # TODO: 在此处调用实际的 MCP 工具（如 adb tap、adb input 等）
    # 示例：await mcp_tools.tap(x=100, y=200)

    executed_step_record: dict = {
        **execution_result,
        "mcp_calls": [
            # {"tool": "tap", "params": {"x": 100, "y": 200}, "status": "success"},
        ],
    }

    logger.info(f"[Executor] 步骤 [{current_step_index + 1}/{len(test_steps)}] 执行完成，结果: {execution_result['result']}")

    return {
        "executed_steps": [executed_step_record],
        "node_outputs": {
            **state.get("node_outputs", {}),
            "executor": executed_step_record,
        },
        "messages": [
            *state.get("messages", []),
            {"role": "assistant", "content": f"执行节点完成步骤 {current_step_index + 1}: {execution_result['result']}"},
        ],
        "total_tokens_used": state.get("total_tokens_used", 0) + 0,
    }