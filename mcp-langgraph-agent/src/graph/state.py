"""
AgentState 定义模块。

使用 TypedDict + Annotated 实现 LangGraph 的 State 定义，
列表字段通过 operator.add 实现合并操作。
"""

from __future__ import annotations

import operator
from typing import Annotated, List, Optional, TypedDict


class AgentState(TypedDict):
    """
    LangGraph 工作流的 Agent 状态定义。

    包含测试目标、测试步骤、执行结果、UI 信息、验证结果等全部运行时状态。
    列表字段使用 Annotated + operator.add 实现跨节点的增量合并。
    """

    # ── 测试目标与步骤 ──────────────────────────────────────────────
    test_goal: str
    """用户输入的测试目标（自然语言描述）。"""

    test_steps: Annotated[List[str], operator.add]
    """规划出的测试步骤列表，规划节点生成，支持合并。"""

    current_step_index: int
    """当前执行步骤的索引（从 0 开始）。"""

    executed_steps: Annotated[List[dict], operator.add]
    """已执行步骤列表，每个元素包含 step, action, result, screenshot, passed 等字段。"""

    # ── 设备 / UI 信息 ─────────────────────────────────────────────
    ui_tree: Optional[str]
    """当前设备界面的无障碍树（Accessibility Tree）JSON 字符串。"""

    screenshot_b64: Optional[str]
    """当前设备截图的 Base64 编码字符串。"""

    device_name: str
    """被测设备名称（如 'emulator-5554' 或 'iPhone 15'）。"""

    test_plan: Optional[dict]
    """测试计划，包含步骤列表和预期结果等结构化信息。"""

    # ── 验证结果 ───────────────────────────────────────────────────
    verification_passed: bool
    """当前步骤验证是否通过。"""

    verification_details: Annotated[List[dict], operator.add]
    """验证详情列表，每条记录包含验证项、预期值、实际值、是否通过等。"""

    # ── 重试机制 ───────────────────────────────────────────────────
    retry_count: int
    """当前步骤已重试次数。"""

    max_retries: int
    """当前步骤最大允许重试次数。"""

    # ── 错误与消息 ─────────────────────────────────────────────────
    error: Optional[str]
    """错误信息，节点执行出错时填充。"""

    messages: Annotated[List[dict], operator.add]
    """对话历史消息列表，用于 LLM 调用上下文。"""

    node_outputs: dict
    """各节点的输出缓存，key 为节点名，value 为输出内容。"""

    # ── 审查 ───────────────────────────────────────────────────────
    reviewer_feedback: Optional[str]
    """审查节点的反馈意见。"""

    # ── 统计与元数据 ───────────────────────────────────────────────
    total_tokens_used: int
    """整个工作流已消耗的 Token 总数。"""

    metadata: dict
    """元数据字典，包含 task_id, start_time, device_info 等。"""