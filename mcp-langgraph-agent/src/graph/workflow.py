"""
LangGraph 工作流构建模块。

构建完整的 StateGraph，包含 5 个节点（explorer, planner, executor, verifier, reviewer）
以及条件路由逻辑，实现端到端的移动端自动化测试流程。
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import AgentState
from src.graph.nodes.explorer import explorer_node
from src.graph.nodes.planner import planner_node
from src.graph.nodes.executor import executor_node
from src.graph.nodes.verifier import verifier_node
from src.graph.nodes.reviewer import reviewer_node

logger = logging.getLogger(__name__)


# ── 路由决策函数 ─────────────────────────────────────────────────


def route_after_verifier(state: AgentState) -> Literal["executor", "reviewer", "__end__"]:
    """验证节点后的路由决策函数。

    根据验证结果和重试次数决定下一步走向：
    - passed (验证通过):
        - 还有下一步 → "executor"（继续执行）
        - 所有步骤完成 → "reviewer"（进入审查）
    - failed (验证失败):
        - retry_count < max_retries → "executor"（重试当前步骤）
        - retry_count >= max_retries → "__end__"（重试超限，结束流程）

    注意：verifier 节点已经负责递增 current_step_index（通过时）
    和 retry_count（失败时），此处只做路由判断。

    Args:
        state: 当前 Agent 状态，包含 verification_passed、retry_count、
               max_retries、current_step_index、test_steps 等字段。

    Returns:
        Literal["executor", "reviewer", "__end__"]: 下一步的目标节点名称。
    """
    verification_passed: bool = state.get("verification_passed", False)
    retry_count: int = state.get("retry_count", 0)
    max_retries: int = state.get("max_retries", 3)
    current_step_index: int = state.get("current_step_index", 0)
    total_steps: int = len(state.get("test_steps", []))

    logger.info(
        f"[路由] verifier -> "
        f"验证通过={verification_passed}, "
        f"重试={retry_count}/{max_retries}, "
        f"步骤索引={current_step_index}/{total_steps}"
    )

    if verification_passed:
        # 验证通过：verifier 已将 current_step_index 递增
        # 检查是否还有下一步
        if current_step_index < total_steps:
            logger.info(f"[路由] 下一步 -> executor (步骤 {current_step_index + 1}/{total_steps})")
            return "executor"
        else:
            logger.info("[路由] 下一步 -> reviewer (所有步骤执行完毕)")
            return "reviewer"
    else:
        # 验证失败：检查是否可重试
        if retry_count < max_retries:
            logger.info(f"[路由] 下一步 -> executor (重试第 {retry_count}/{max_retries} 次)")
            return "executor"
        else:
            logger.warning(f"[路由] 结束 -> END (重试超限 {max_retries} 次)")
            return END


def route_after_reviewer(state: AgentState) -> Literal["planner", "__end__"]:
    """审查节点后的路由决策函数。

    根据审查结果决定下一步走向：
    - approved (审查通过) → "__end__"（结束流程）
    - rejected (审查未通过) → "planner"（驳回重新规划）

    Args:
        state: 当前 Agent 状态，包含 reviewer_feedback、node_outputs 等字段。

    Returns:
        Literal["planner", "__end__"]: 下一步的目标节点名称。
    """
    reviewer_output: dict = state.get("node_outputs", {}).get("reviewer", {})
    passed: bool = reviewer_output.get("passed", False)

    logger.info(f"[路由] reviewer -> 审查通过={passed}")

    if passed:
        logger.info("[路由] 结束 -> END (审查通过)")
        return END
    else:
        logger.info("[路由] 下一步 -> planner (审查未通过，重新规划)")
        return "planner"


# ── 工作流构建函数 ───────────────────────────────────────────────


def build_workflow() -> StateGraph:
    """构建完整的 LangGraph StateGraph 工作流。

    注册 5 个节点并设置条件路由逻辑：
    1. explorer  - 探索节点：调用 ExplorerAgent 分析测试目标，理解用户意图
    2. planner   - 规划节点：调用 PlannerAgent 生成详细的测试步骤计划
    3. executor  - 执行节点：调用 ExecutorAgent 执行当前测试步骤
    4. verifier  - 验证节点：调用 VerifierAgent 验证执行结果
    5. reviewer  - 审查节点：调用 ReviewerAgent 审查整个测试流程

    流程拓扑：
        explorer -> planner -> executor -> verifier -> (条件路由)
            ↑                          ↓            ↓
            |                     (失败重试)    (通过/完成)
            |                          ↓            ↓
            +------ planner <--- reviewer     executor / END

    路由逻辑：
        - verifier -> passed & 还有下一步: executor
        - verifier -> passed & 所有完成:   reviewer
        - verifier -> failed & 可重试:     executor
        - verifier -> failed & 超限:       END
        - reviewer -> approved:            END
        - reviewer -> rejected:            planner

    Returns:
        CompiledStateGraph: 编译后的可执行 LangGraph 应用实例。
    """
    logger.info("[Workflow] 开始构建 StateGraph")

    # 创建状态图，指定状态模式为 AgentState
    workflow: StateGraph = StateGraph(AgentState)

    # ── 注册节点 ───────────────────────────────────────────────────
    workflow.add_node("explorer", explorer_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("reviewer", reviewer_node)

    logger.info("[Workflow] 已注册 5 个节点: explorer, planner, executor, verifier, reviewer")

    # ── 设置入口点 ─────────────────────────────────────────────────
    workflow.set_entry_point("explorer")

    # ── 添加边 ─────────────────────────────────────────────────────
    # explorer -> planner: 探索完成后进入规划
    workflow.add_edge("explorer", "planner")

    # planner -> executor: 规划完成后进入执行
    workflow.add_edge("planner", "executor")

    # executor -> verifier: 执行完成后进入验证
    workflow.add_edge("executor", "verifier")

    # verifier -> 条件路由: 根据验证结果决定下一步
    workflow.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "executor": "executor",
            "reviewer": "reviewer",
            END: END,
        },
    )

    # reviewer -> 条件路由: 根据审查结果决定下一步
    workflow.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "planner": "planner",
            END: END,
        },
    )

    logger.info("[Workflow] 边和条件路由设置完成")

    # ── 编译工作流 ─────────────────────────────────────────────────
    # 使用 MemorySaver 作为内存中的检查点存储，支持状态持久化和历史回溯
    memory_saver: MemorySaver = MemorySaver()
    app = workflow.compile(checkpointer=memory_saver)

    logger.info("[Workflow] StateGraph 编译完成")

    return app


# ── 便捷函数 ─────────────────────────────────────────────────────


def get_compiled_graph():
    """获取编译后的可执行工作流图。

    便捷函数，直接返回 build_workflow() 的编译结果，
    供外部入口点直接调用。

    Returns:
        CompiledStateGraph: 编译后的可执行图实例。
    """
    return build_workflow()
