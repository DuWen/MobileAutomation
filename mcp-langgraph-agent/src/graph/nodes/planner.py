"""规划节点模块。

调用 PlannerAgent 基于探索结果生成详细的测试步骤计划，
将自然语言测试目标转换为可执行的步骤序列。
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.llm import ModelRouter
from src.agents.planner import PlannerAgent
from src.graph.state import AgentState
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


async def planner_node(state: AgentState) -> dict[str, Any]:
    """规划节点的主函数。

    调用 PlannerAgent 生成结构化测试步骤计划。
    test_plan 字段为 list[dict] 类型，使用 operator.add 合并，
    因此返回的是步骤列表而非单个对象。

    Args:
        state: 当前 Agent 状态，包含 test_goal、node_outputs 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - test_plan: 生成的测试步骤列表（list[dict]，对齐 AgentState 定义）
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

    # ── 增量规划：检测是否为重新规划场景 ─────────────────────────
    # 当 verifier 失败超限后路由到 explorer 再到 planner 时，
    # state.executed_steps 非空，此时应保留已通过步骤，仅规划剩余步骤
    executed_steps: list[dict] = state.get('executed_steps', [])
    is_replan: bool = bool(executed_steps)

    # 统计已通过的步骤数（作为新计划的起始索引）
    passed_steps_count: int = sum(
        1 for s in executed_steps if isinstance(s, dict) and s.get('passed', False)
    ) if executed_steps else 0

    if is_replan:
        logger.info(
            f"[Planner] 检测到重新规划场景：已执行 {len(executed_steps)} 步，"
            f"其中 {passed_steps_count} 步通过，仅规划剩余步骤"
        )

    # 调用 Agent 执行规划（传入已执行步骤作为上下文）
    plan_result: dict[str, Any] = await agent.run(
        test_goal=state.get('test_goal', ''),
        ui_tree=state.get('ui_tree', ''),
        screenshot_b64=state.get('screenshot_b64', ''),
        exploration_result=explorer_output,
        executed_steps=executed_steps if is_replan else None,
        is_replan=is_replan,
    )

    # 提取测试步骤列表
    # Agent 可能返回 test_steps 或 test_plan，统一转为 list[dict]
    test_steps: list[dict] = plan_result.get('test_steps', [])
    if not test_steps:
        # 兼容 Agent 返回 test_plan 为 dict 包含 steps 的情况
        plan_dict: dict = plan_result.get('test_plan', {})
        if isinstance(plan_dict, dict):
            test_steps = plan_dict.get('steps', [])
        elif isinstance(plan_dict, list):
            test_steps = plan_dict

    # 重新规划场景：新计划只包含剩余步骤（test_plan 已被 replace_if_non_empty
    # 整体替换），current_step_index 从 0 开始
    # 首次规划场景：current_step_index 也从 0 开始
    new_step_index: int = 0

    # 获取本轮 Token 消耗
    token_summary: dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    plan_mode_desc = "重新规划（仅剩余步骤）" if is_replan else "首次规划"
    logger.info(
        f"[Planner] {plan_mode_desc}完成，共 {len(test_steps)} 个步骤"
    )

    return {
        'test_plan': test_steps,
        'current_step_index': new_step_index,
        'retry_count': 0,
        'node_outputs': {
            **state.get('node_outputs', {}),
            'planner': {
                'total_steps': len(test_steps),
                'steps': test_steps,
                'is_replan': is_replan,
                'passed_steps_before_replan': passed_steps_count,
            },
        },
        'messages': [
            {
                'role': 'assistant',
                'content': (
                    f"{'重新规划' if is_replan else '规划'}完成，"
                    f"生成 {len(test_steps)} 个测试步骤"
                ),
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
