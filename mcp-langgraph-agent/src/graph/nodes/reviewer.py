"""
审查节点模块（可选节点）。

负责审查整个测试流程的完整性和正确性，
生成测试报告摘要，并决定是否通过最终审查。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.prompts import REVIEWER_PROMPT

logger = logging.getLogger(__name__)


async def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """
    审查节点的主函数。

    该节点负责：
    1. 汇总整个测试流程的执行记录
    2. 检查所有步骤是否都已执行并通过验证
    3. 调用 LLM 审查测试流程的完整性和正确性
    4. 生成测试报告摘要
    5. 输出 reviewer_feedback 及是否通过审查

    Args:
        state: 当前 Agent 状态，包含 test_plan、executed_steps、
               verification_details 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - reviewer_feedback: 审查反馈意见
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    logger.info("[Reviewer] 开始审查整个测试流程")

    test_goal: str = state.get("test_goal", "")
    test_plan: dict = state.get("test_plan", {})
    executed_steps: list = state.get("executed_steps", [])
    verification_details: list = state.get("verification_details", [])
    total_steps: int = len(state.get("test_steps", []))
    completed_steps: int = len(executed_steps)

    # 构建 LLM 调用消息序列，使用 prompts.py 中的模板
    execution_log: str = (
        f"步骤数: {completed_steps}/{total_steps}, "
        f"执行记录: {executed_steps}"
    )
    verification_result: str = str(verification_details)
    messages = [
        {
            "role": "system",
            "content": REVIEWER_PROMPT.format(
                test_goal=test_goal,
                execution_log=execution_log,
                verification_result=verification_result,
            ),
        },
    ]

    # TODO: 在此处调用 LLM API 进行真实的审查分析
    # 当前为模拟实现，生成占位审查结果
    all_steps_executed: bool = completed_steps >= total_steps
    all_verifications_passed: bool = all(
        d.get("passed", False) for d in verification_details
    ) if verification_details else False

    if all_steps_executed and all_verifications_passed:
        feedback: str = (
            f"审查通过。所有 {total_steps} 个步骤已执行完毕，"
            f"验证全部通过。测试流程完整、正确。"
        )
        passed: bool = True
    elif all_steps_executed and not all_verifications_passed:
        feedback = (
            f"审查未通过。虽然所有 {total_steps} 个步骤已执行，"
            f"但部分验证项未通过，建议检查失败步骤并重新规划。"
        )
        passed = False
    else:
        feedback = (
            f"审查未通过。已完成 {completed_steps}/{total_steps} 个步骤，"
            f"建议补充剩余步骤后重新审查。"
        )
        passed = False

    logger.info(f"[Reviewer] 审查完成，结论: {'通过' if passed else '未通过'}")

    return {
        "reviewer_feedback": feedback,
        "node_outputs": {
            **state.get("node_outputs", {}),
            "reviewer": {
                "passed": passed,
                "feedback": feedback,
                "summary": {
                    "total_steps": total_steps,
                    "completed_steps": completed_steps,
                    "all_verifications_passed": all_verifications_passed,
                },
            },
        },
        "messages": [
            *state.get("messages", []),
            {"role": "assistant", "content": f"审查节点完成：{feedback}"},
        ],
        "total_tokens_used": state.get("total_tokens_used", 0) + 0,
    }