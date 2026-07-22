"""审查节点模块。

调用 ReviewerAgent 审查整个测试流程的完整性和正确性，
生成测试报告摘要，并决定是否通过最终审查。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.reviewer import ReviewerAgent
from src.agents.llm import ModelRouter
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_reviewer_agent: ReviewerAgent | None = None


def get_reviewer_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
) -> ReviewerAgent:
    """获取或创建 ReviewerAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例

    Returns:
        ReviewerAgent 实例
    """
    global _reviewer_agent
    if _reviewer_agent is None:
        _reviewer_agent = ReviewerAgent(
            model_router=model_router,
            token_tracker=token_tracker,
        )
    return _reviewer_agent


async def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """审查节点的主函数。

    调用 ReviewerAgent 综合分析整个测试流程，给出最终审查结论。
    审查结果中的 passed 字段会写入 node_outputs，供路由函数判断。

    Args:
        state: 当前 Agent 状态，包含 test_plan、executed_steps、
               verification_details 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - reviewer_feedback: 审查反馈意见
            - node_outputs: 更新后的节点输出缓存（含 passed 字段）
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info("[Reviewer] 开始审查整个测试流程")

    # 获取 Agent 实例
    agent: ReviewerAgent = get_reviewer_agent()

    # 调用 Agent 执行审查
    review_result: Dict[str, Any] = await agent.run(
        test_goal=state.get('test_goal', ''),
        test_plan=state.get('test_plan', {}),
        executed_steps=state.get('executed_steps', []),
        verification_details=state.get('verification_details', []),
        test_steps=state.get('test_steps', []),
    )

    # 提取审查结论
    passed: bool = review_result.get('passed', False)
    feedback: str = review_result.get('feedback', '审查完成')

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(f"[Reviewer] 审查完成，结论: {'通过' if passed else '未通过'}")

    return {
        'reviewer_feedback': feedback,
        'node_outputs': {
            **state.get('node_outputs', {}),
            'reviewer': {
                'passed': passed,
                'feedback': feedback,
                'overall_assessment': review_result.get('overall_assessment', ''),
                'quality_metrics': review_result.get('quality_metrics', {}),
                'issues_found': review_result.get('issues_found', []),
                'recommendations': review_result.get('recommendations', []),
                'coverage_analysis': review_result.get('coverage_analysis', {}),
                'final_verdict': review_result.get('final_verdict', 'need_manual_check'),
            },
        },
        'messages': [
            *state.get('messages', []),
            {
                'role': 'assistant',
                'content': f"审查节点完成：{feedback}",
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
