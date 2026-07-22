"""验证节点模块。

调用 VerifierAgent 验证执行结果是否符合预期，
使用 LLM 分析截图和 UI 树来判断执行成功与否。
验证通过后自动递增步骤索引，验证失败则递增重试计数。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.graph.state import AgentState
from src.agents.verifier import VerifierAgent
from src.agents.llm import ModelRouter
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_verifier_agent: VerifierAgent | None = None


def get_verifier_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
) -> VerifierAgent:
    """获取或创建 VerifierAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例

    Returns:
        VerifierAgent 实例
    """
    global _verifier_agent
    if _verifier_agent is None:
        _verifier_agent = VerifierAgent(
            model_router=model_router,
            token_tracker=token_tracker,
        )
    return _verifier_agent


async def verifier_node(state: AgentState) -> Dict[str, Any]:
    """验证节点的主函数。

    调用 VerifierAgent 验证上一步执行结果，并根据验证结果更新步骤索引和重试计数：

    - 验证通过：递增 current_step_index，重置 retry_count 为 0
    - 验证失败：保持 current_step_index 不变，递增 retry_count

    Args:
        state: 当前 Agent 状态，包含 executed_steps、ui_tree、
               screenshot_b64、test_plan 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - verification_passed: 验证是否通过
            - verification_details: 新增的验证详情列表
            - current_step_index: 验证通过时递增，失败时不变
            - retry_count: 验证失败时递增，通过时重置为 0
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
    """
    executed_steps: List[dict] = state.get('executed_steps', [])

    # 边界检查
    if not executed_steps:
        logger.warning("[Verifier] 没有已执行步骤可供验证")
        return {
            'verification_passed': False,
            'verification_details': [
                {
                    'check': '存在已执行步骤',
                    'expected': True,
                    'actual': False,
                    'passed': False,
                    'evidence': '无执行记录',
                },
            ],
            'node_outputs': {
                **state.get('node_outputs', {}),
                'verifier': {'error': '无执行记录'},
            },
        }

    # 获取最后一条执行记录
    last_execution: dict = executed_steps[-1]
    current_step: str = last_execution.get('step', '')
    step_index: int = last_execution.get('step_index', 0)
    logger.info(f"[Verifier] 开始验证步骤 [{step_index + 1}]: {current_step}")

    # 获取 Agent 实例
    agent: VerifierAgent = get_verifier_agent()

    # 调用 Agent 执行验证
    verify_result: Dict[str, Any] = await agent.run(
        execution_record=last_execution,
        ui_tree=state.get('ui_tree', ''),
        screenshot_b64=state.get('screenshot_b64', ''),
        test_plan=state.get('test_plan', {}),
        verification_points=(
            state.get('test_plan', {}).get('expected_results', [])
            if state.get('test_plan') else []
        ),
    )

    # 提取验证结果
    verification_passed: bool = verify_result.get('verification_passed', False)
    verification_details: List[dict] = verify_result.get('verification_details', [])

    # 根据验证结果更新步骤索引和重试计数
    current_step_index: int = state.get('current_step_index', 0)
    retry_count: int = state.get('retry_count', 0)

    if verification_passed:
        # 验证通过：递增步骤索引，重置重试计数
        current_step_index += 1
        retry_count = 0
        logger.info(
            f"[Verifier] 验证通过，步骤索引递增到 {current_step_index}"
        )
    else:
        # 验证失败：保持步骤索引不变，递增重试计数
        retry_count += 1
        logger.warning(
            f"[Verifier] 验证失败，重试次数 {retry_count}/{state.get('max_retries', 3)}"
        )

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(
        f"[Verifier] 验证完成，结果: {'通过' if verification_passed else '失败'}"
    )

    return {
        'verification_passed': verification_passed,
        'verification_details': verification_details,
        'current_step_index': current_step_index,
        'retry_count': retry_count,
        'node_outputs': {
            **state.get('node_outputs', {}),
            'verifier': {
                'passed': verification_passed,
                'details': verification_details,
                'overall_status': verify_result.get('overall_status', ''),
                'summary': verify_result.get('summary', ''),
                'suggestions': verify_result.get('suggestions', []),
            },
        },
        'messages': [
            *state.get('messages', []),
            {
                'role': 'assistant',
                'content': (
                    f"验证步骤 {step_index + 1}: "
                    f"{'通过' if verification_passed else '失败'}"
                ),
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
    }
