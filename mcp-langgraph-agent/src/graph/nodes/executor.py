"""执行节点模块。

调用 ExecutorAgent 执行当前测试步骤，
通过 MCP Client 调用工具（tap、input、swipe 等），并记录执行结果和截图。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.graph.state import AgentState
from src.agents.executor import ExecutorAgent
from src.agents.llm import ModelRouter
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_executor_agent: ExecutorAgent | None = None


def get_executor_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
    mcp_client: Any = None,
) -> ExecutorAgent:
    """获取或创建 ExecutorAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。
    当提供 mcp_client 时，更新 Agent 的 MCP Client 引用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例
        mcp_client: MCP 客户端实例

    Returns:
        ExecutorAgent 实例
    """
    global _executor_agent
    if _executor_agent is None:
        _executor_agent = ExecutorAgent(
            model_router=model_router,
            token_tracker=token_tracker,
            mcp_client=mcp_client,
        )
    elif mcp_client is not None:
        _executor_agent.mcp_client = mcp_client
    return _executor_agent


async def executor_node(state: AgentState) -> Dict[str, Any]:
    """执行节点的主函数。

    调用 ExecutorAgent 执行当前测试步骤，通过 MCP 工具操作设备，
    记录执行结果、截图和状态。

    关键逻辑：
    - 验证通过后，步骤索引由 verifier 节点递增，executor 直接使用 current_step_index
    - 验证失败后重试，current_step_index 不变，retry_count 由 verifier 递增

    Args:
        state: 当前 Agent 状态，包含 test_plan、current_step_index、
               ui_tree、screenshot_b64 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - executed_steps: 新增的执行记录
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
            - failure_reason: 执行出错时填充的错误信息
    """
    current_step_index: int = state.get('current_step_index', 0)
    test_plan: List = state.get('test_plan', [])

    # 边界检查
    if current_step_index >= len(test_plan):
        logger.warning(
            f"[Executor] 步骤索引 {current_step_index} 超出范围，总步骤数 {len(test_plan)}"
        )
        return {
            'failure_reason': f"步骤索引 {current_step_index} 超出范围",
            'node_outputs': {
                **state.get('node_outputs', {}),
                'executor': {'error': '索引越界'},
            },
        }

    # 获取当前步骤（兼容 str 和 dict 两种格式）
    step_item = test_plan[current_step_index]
    if isinstance(step_item, dict):
        step_desc: str = step_item.get('action', '') or step_item.get('step', str(step_item))
    else:
        step_desc = str(step_item)
    logger.info(
        f"[Executor] 开始执行步骤 [{current_step_index + 1}/{len(test_plan)}]: {step_desc}"
    )

    # 获取 Agent 实例
    agent: ExecutorAgent = get_executor_agent()

    # 注入 Skill 知识上下文（由 Explorer 节点匹配并传递）
    skill_context: str = state.get('skill_context', '')
    if skill_context:
        agent.set_skill_context(skill_context)

    # 调用 Agent 执行步骤
    execution_record: Dict[str, Any] = await agent.run(
        current_step=step_desc,
        current_step_index=current_step_index,
        ui_tree=state.get('ui_tree', ''),
        screenshot_b64=state.get('screenshot_b64', ''),
        test_plan=test_plan,
        executed_steps=state.get('executed_steps', []),
        device_name=state.get('device_name', ''),
    )

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(
        f"[Executor] 步骤 [{current_step_index + 1}/{len(test_plan)}] 执行完成，"
        f"结果: {execution_record.get('result', '未知')}"
    )

    return {
        'executed_steps': [execution_record],
        'node_outputs': {
            **state.get('node_outputs', {}),
            'executor': execution_record,
        },
        'messages': [
            {
                'role': 'assistant',
                'content': (
                    f"执行步骤 {current_step_index + 1}: "
                    f"{execution_record.get('result', '完成')}"
                ),
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
