"""
验证节点模块。

负责验证上一步执行结果是否符合预期，
使用 LLM 分析截图和 UI 树来判断执行成功与否。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.graph.state import AgentState
from src.agents.prompts import VERIFIER_PROMPT

logger = logging.getLogger(__name__)


async def verifier_node(state: AgentState) -> Dict[str, Any]:
    """
    验证节点的主函数。

    该节点负责：
    1. 获取上一步执行记录（executed_steps 的最后一条）
    2. 获取当前 UI 树和截图作为验证依据
    3. 调用 LLM 分析执行结果是否符合预期
    4. 输出验证结论（verification_passed）和验证详情

    Args:
        state: 当前 Agent 状态，包含 executed_steps、ui_tree、
               screenshot_b64、test_plan 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - verification_passed: 验证是否通过
            - verification_details: 新增的验证详情列表
            - retry_count: 验证失败时递增重试次数
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    executed_steps: List[dict] = state.get("executed_steps", [])

    if not executed_steps:
        logger.warning("[Verifier] 没有已执行步骤可供验证")
        return {
            "verification_passed": False,
            "verification_details": [
                {"check": "存在已执行步骤", "expected": True, "actual": False, "passed": False},
            ],
            "node_outputs": {
                **state.get("node_outputs", {}),
                "verifier": {"error": "无执行记录"},
            },
        }

    # 获取最后一条执行记录作为验证对象
    last_execution: dict = executed_steps[-1]
    current_step: str = last_execution.get("step", "")
    step_index: int = last_execution.get("step_index", 0)
    logger.info(f"[Verifier] 开始验证步骤 [{step_index + 1}]: {current_step}")

    # 构建 LLM 调用消息序列，使用 prompts.py 中的模板
    test_plan: dict = state.get("test_plan", {})
    verification_points: list = test_plan.get("expected_results", []) if test_plan else []
    executed_actions: str = str(last_execution)
    messages = [
        {
            "role": "system",
            "content": VERIFIER_PROMPT.format(
                verification_points=str(verification_points),
                executed_actions=executed_actions,
                ui_tree=state.get("ui_tree", ""),
                screenshot_description="有截图" if state.get("screenshot_b64") else "无截图",
            ),
        },
    ]

    # TODO: 在此处调用 LLM API 进行真实的验证分析
    # 当前为模拟实现，生成占位验证结果
    verification_details: List[dict] = [
        {
            "check": f"步骤「{current_step}」执行成功",
            "expected": "操作应成功执行",
            "actual": "操作执行成功",
            "passed": True,
        },
        {
            "check": "界面状态正确",
            "expected": "UI 状态与预期一致",
            "actual": "UI 状态正常",
            "passed": True,
        },
    ]

    verification_passed: bool = all(detail["passed"] for detail in verification_details)
    retry_count: int = state.get("retry_count", 0)

    # 如果验证失败，递增重试计数
    if not verification_passed:
        retry_count += 1
        logger.warning(f"[Verifier] 验证失败，重试次数 {retry_count}/{state.get('max_retries', 3)}")

    logger.info(f"[Verifier] 验证完成，结果: {'通过' if verification_passed else '失败'}")

    return {
        "verification_passed": verification_passed,
        "verification_details": verification_details,
        "retry_count": retry_count,
        "node_outputs": {
            **state.get("node_outputs", {}),
            "verifier": {
                "passed": verification_passed,
                "details": verification_details,
            },
        },
        "messages": [
            *state.get("messages", []),
            {
                "role": "assistant",
                "content": f"验证节点完成步骤 {step_index + 1}: {'通过' if verification_passed else '失败'}",
            },
        ],
        "total_tokens_used": state.get("total_tokens_used", 0) + 0,
    }