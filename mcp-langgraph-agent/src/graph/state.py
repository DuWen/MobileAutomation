"""
AgentState 定义模块。

使用 TypedDict + Annotated 实现 LangGraph 的 State 定义，
列表字段通过 add_messages 和 operator.add 实现合并操作。
对齐设计文档中的 AgentState 定义。
"""

from __future__ import annotations

import operator
from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    LangGraph 工作流的 Agent 状态定义。

    包含测试目标、测试步骤、执行结果、UI 信息、验证结果等全部运行时状态。
    列表字段使用 Annotated + add_messages/operator.add 实现跨节点的增量合并。
    """

    # ── 消息历史 ──────────────────────────────────────────────────
    messages: Annotated[list, add_messages]
    """对话历史消息列表，使用 langgraph 的 add_messages 合并策略。"""

    # ── 测试目标 ──────────────────────────────────────────────────
    test_goal: str
    """用户输入的测试目标（自然语言描述）。"""

    # ── 当前页面信息 ──────────────────────────────────────────────
    current_screen: str
    """当前屏幕的文本描述（由 Explorer 节点生成）。"""

    ui_tree: Optional[str]
    """当前设备界面的无障碍树（Accessibility Tree）JSON 字符串。"""

    screenshot_b64: Optional[str]
    """当前设备截图的 Base64 编码字符串。"""

    # ── 测试计划与执行 ────────────────────────────────────────────
    test_plan: Annotated[List[dict], operator.add]
    """测试步骤计划列表，每个元素包含 action/target/value/expected 等字段。"""

    executed_steps: Annotated[List[dict], operator.add]
    """已执行步骤列表，每个元素包含 step, action, result, screenshot, passed 等字段。"""

    current_step_index: int
    """当前执行步骤的索引（从 0 开始）。"""

    # ── 验证与结果 ────────────────────────────────────────────────
    verification_result: bool
    """当前步骤验证是否通过。"""

    failure_reason: str
    """验证失败时的原因描述。"""

    retry_count: int
    """当前步骤已重试次数。"""

    # ── 设备信息 ──────────────────────────────────────────────────
    device_name: str
    """被测设备名称（如 'emulator-5554' 或 'iPhone 15'）。"""

    device_connected: bool
    """设备是否已通过 Appium 建立连接，由 Explorer 节点在首次连接后设置为 True。"""

    # ── 最终报告 ──────────────────────────────────────────────────
    final_report: str
    """测试执行完成后的最终报告文本。"""

    # ── 扩展字段（当前实现需要但设计文档未明确列出） ──────────────
    node_outputs: dict
    """各节点的输出缓存，key 为节点名，value 为输出内容。"""

    perception_mode: str
    """感知模式：ui_tree / screenshot / hybrid，默认 hybrid。"""

    matched_skills: Optional[list]
    """与测试目标匹配的 Skill 知识列表，由 Explorer 节点匹配并注入。"""

    skill_context: Optional[str]
    """格式化后的 Skill 知识文本，注入到后续节点的系统提示词中。"""

    total_tokens_used: int
    """整个工作流已消耗的 Token 总数。"""

    metadata: dict
    """元数据字典，包含 task_id, start_time, device_info 等。"""