"""
规划节点模块。

基于探索结果生成详细的测试步骤计划，
将自然语言测试目标转换为可执行的步骤序列。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.graph.state import AgentState
from src.agents.prompts import PLANNER_PROMPT

logger = logging.getLogger(__name__)


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    规划节点的主函数。

    该节点负责：
    1. 接收探索节点的输出（对测试目标的理解和界面分析）
    2. 调用 LLM 生成结构化的测试步骤计划
    3. 输出 test_plan（包含步骤列表和预期结果）

    Args:
        state: 当前 Agent 状态，包含 test_goal、node_outputs 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - test_plan: 生成的测试计划
            - test_steps: 生成的测试步骤列表
            - current_step_index: 重置为 0
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info("[Planner] 开始规划测试步骤")

    # 从状态中提取探索结果
    test_goal: str = state.get("test_goal", "")
    explorer_output: dict = state.get("node_outputs", {}).get("explorer", {})

    # 构建 LLM 调用消息序列，使用 prompts.py 中的模板
    messages = [
        {
            "role": "system",
            "content": PLANNER_PROMPT.format(
                test_goal=test_goal,
                ui_tree=state.get("ui_tree", ""),
                screenshot_description="有截图" if state.get("screenshot_b64") else "无截图",
                exploration_result=str(explorer_output),
            ),
        },
    ]

    # TODO: 在此处调用 LLM API 生成真实的测试计划
    # 当前为模拟实现，返回占位测试计划
    test_steps: List[str] = [
        f"步骤 1: 打开应用并进入目标功能页面",
        f"步骤 2: 执行核心操作 - {test_goal}",
        f"步骤 3: 验证操作结果是否符合预期",
        f"步骤 4: 恢复初始状态或清理",
    ]

    test_plan: dict = {
        "goal": test_goal,
        "steps": test_steps,
        "expected_results": [
            "应用正常打开，目标功能页面可见",
            "核心操作执行成功，无异常",
            "结果与预期一致",
            "状态恢复成功",
        ],
        "estimated_duration": "5 分钟",
    }

    logger.info(f"[Planner] 规划完成，共 {len(test_steps)} 个步骤")

    return {
        "test_plan": test_plan,
        "test_steps": test_steps,
        "current_step_index": 0,
        "node_outputs": {
            **state.get("node_outputs", {}),
            "planner": test_plan,
        },
        "messages": [
            *state.get("messages", []),
            {"role": "assistant", "content": f"规划节点完成，生成 {len(test_steps)} 个测试步骤"},
        ],
        "total_tokens_used": state.get("total_tokens_used", 0) + 0,
    }