"""规划节点模块。

调用 PlannerAgent 基于探索结果生成详细的测试步骤计划，
将自然语言测试目标转换为可执行的步骤序列。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.planner import PlannerAgent
from src.agents.llm import ModelRouter
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_planner_agent: PlannerAgent | None = None


def get_planner_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
) -> PlannerAgent:
    """获取或创建 PlannerAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例

    Returns:
        PlannerAgent 实例
    """
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = PlannerAgent(
            model_router=model_router,
            token_tracker=token_tracker,
        )
    return _planner_agent


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """规划节点的主函数。

    调用 PlannerAgent 生成结构化测试步骤计划。

    Args:
        state: 当前 Agent 状态，包含 test_goal、node_outputs 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - test_plan: 生成的测试计划
            - test_steps: 生成的测试步骤列表
            - current_step_index: 重置为 0
            - retry_count: 重置为 0（新计划开始）
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info("[Planner] 开始规划测试步骤")

    # 获取 Agent 实例
    agent: PlannerAgent = get_planner_agent()

    # 注入 Skill 知识上下文（由 Explorer 节点匹配并传递）
    skill_context: str = state.get('skill_context', '')
    if skill_context:
        agent.set_skill_context(skill_context)

    # 提取探索结果
    explorer_output: dict = state.get('node_outputs', {}).get('explorer', {})

    # 调用 Agent 执行规划
    plan_result: Dict[str, Any] = await agent.run(
        test_goal=state.get('test_goal', ''),
        ui_tree=state.get('ui_tree', ''),
        screenshot_b64=state.get('screenshot_b64', ''),
        exploration_result=explorer_output,
    )

    # 提取测试计划和步骤
    test_plan: dict = plan_result.get('test_plan', {})
    test_steps: list = plan_result.get('test_steps', [])

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(f"[Planner] 规划完成，共 {len(test_steps)} 个步骤")

    return {
        'test_plan': test_plan,
        'test_steps': test_steps,
        'current_step_index': 0,
        'retry_count': 0,
        'node_outputs': {
            **state.get('node_outputs', {}),
            'planner': test_plan,
        },
        'messages': [
            *state.get('messages', []),
            {
                'role': 'assistant',
                'content': f"规划完成，生成 {len(test_steps)} 个测试步骤",
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
