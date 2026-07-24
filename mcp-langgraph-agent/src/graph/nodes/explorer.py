"""探索节点模块。

负责调用 ExplorerAgent 分析测试目标、理解用户意图，
并获取当前设备界面信息（UI 树 + 截图），为后续规划提供上下文。
同时集成 SkillManager 匹配相关技能知识，通过 HybridPerception
获取混合感知信息。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.graph.state import AgentState
from src.agents.explorer import ExplorerAgent
from src.agents.llm import ModelRouter
from src.skills.manager import SkillManager
from src.utils.perception import HybridPerception, PerceptionMode
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# 全局 Agent 实例缓存（延迟初始化）
_explorer_agent: ExplorerAgent | None = None
_skill_manager: SkillManager | None = None
_mcp_client: Any = None  # MCP 客户端实例，由 init_langgraph_workflow 注入


def get_explorer_agent(
    model_router: ModelRouter | None = None,
    token_tracker: TokenTracker | None = None,
) -> ExplorerAgent:
    """获取或创建 ExplorerAgent 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        model_router: 模型路由实例
        token_tracker: Token 追踪器实例

    Returns:
        ExplorerAgent 实例
    """
    global _explorer_agent
    if _explorer_agent is None:
        _explorer_agent = ExplorerAgent(
            model_router=model_router,
            token_tracker=token_tracker,
        )
    return _explorer_agent


def set_mcp_client(mcp_client: Any) -> None:
    """设置 MCP 客户端实例，供 HybridPerception 使用。

    Args:
        mcp_client: MCP 客户端实例
    """
    global _mcp_client
    _mcp_client = mcp_client


def get_skill_manager(skills_dir: str | None = None) -> SkillManager:
    """获取或创建 SkillManager 单例。

    延迟初始化模式，首次调用时创建实例，后续复用。

    Args:
        skills_dir: Skills 目录路径

    Returns:
        SkillManager 实例
    """
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager(skills_dir=skills_dir)
    return _skill_manager


async def explorer_node(state: AgentState) -> Dict[str, Any]:
    """探索节点的主函数。

    调用 ExplorerAgent 分析测试目标和界面状态，
    识别功能点和关键元素，为规划节点提供结构化上下文。
    同时匹配 Skills 知识并注入到后续节点中。

    流程：
    1. 使用 HybridPerception 获取界面感知信息
    2. 使用 SkillManager 匹配与测试目标相关的技能
    3. 将 Skill 知识注入到 Agent 的系统提示词中
    4. 调用 ExplorerAgent 执行探索分析

    Args:
        state: 当前 Agent 状态，包含 test_goal、device_name 等字段。

    Returns:
        dict: 包含以下字段的字典，用于更新 AgentState：
            - node_outputs: 更新后的节点输出缓存
            - messages: 新增的对话消息
            - total_tokens_used: 本轮消耗的 Token 数
            - skill_context: 格式化的 Skill 知识文本
            - ui_tree: 混合感知获取的 UI 树
            - screenshot_b64: 混合感知获取的截图
    """
    test_goal: str = state.get('test_goal', '')
    logger.info(f"[Explorer] 开始探索测试目标: {test_goal}")

    # ── 1. 匹配 Skills 知识 ────────────────────────────────────
    from src.config.settings import settings
    skill_manager = get_skill_manager(skills_dir=settings.SKILLS_DIR)
    matched_skills = skill_manager.match_skills(test_goal, top_k=3)
    skill_context = skill_manager.format_skills_for_prompt(matched_skills)

    if matched_skills:
        logger.info(
            f"[Explorer] 匹配到 {len(matched_skills)} 个 Skills: "
            f"{[s.name for s in matched_skills]}"
        )

    # ── 2. 混合感知获取界面信息 ────────────────────────────────
    device_name: str = state.get('device_name', '')
    perception_mode_str: str = state.get('perception_mode', 'hybrid')

    # 将字符串映射为 PerceptionMode 枚举
    mode_map = {
        'ui_tree': PerceptionMode.UI_TREE,
        'screenshot': PerceptionMode.SCREENSHOT,
        'hybrid': PerceptionMode.HYBRID,
    }
    perception_mode = mode_map.get(perception_mode_str, PerceptionMode.HYBRID)

    # 优先使用 state 中已有的 UI 信息，仅在没有时调用感知
    ui_tree: str = state.get('ui_tree') or ''
    screenshot_b64: str = state.get('screenshot_b64') or ''

    # 如果设备名可用，先尝试通过 MCP 连接设备（确保 Appium 会话已建立）
    device_connected: bool = state.get('device_connected', False)
    if device_name and not device_connected and _mcp_client:
        try:
            # 从设备池配置获取平台信息，而非 AgentState 中不存在的 device_platform 字段
            device_platform: str = 'Android'  # 默认值
            try:
                from src.main import device_pool
                for dev in device_pool:
                    if dev.get('name') == device_name or dev.get('device_id') == device_name:
                        device_platform = dev.get('platform', 'Android')
                        break
            except ImportError:
                pass

            connect_result = await _mcp_client.call_tool(
                "connect_device",
                {
                    "platform": device_platform,
                    "device_name": device_name,
                },
            )
            if isinstance(connect_result, dict) and connect_result.get("success"):
                logger.info(f"[Explorer] 设备 '{device_name}' 连接成功")
                device_connected = True
            else:
                error_msg = (
                    connect_result.get("data", {}).get("message", "未知错误")
                    if isinstance(connect_result, dict) else str(connect_result)
                )
                logger.warning(f"[Explorer] 设备 '{device_name}' 连接失败: {error_msg}")
        except Exception as e:
            logger.warning(f"[Explorer] 设备连接异常: {e}")

    # 如果两者都缺失且设备已连接，尝试通过 HybridPerception 获取
    if not ui_tree and not screenshot_b64 and device_name and device_connected:
        try:
            perception = HybridPerception(mcp_client=_mcp_client)
            result = await perception.perceive(device_name, mode=perception_mode)
            ui_tree = result.ui_tree
            screenshot_b64 = result.screenshot_b64
            logger.info(
                f"[Explorer] 混合感知完成: mode={result.mode.value}, "
                f"ui_tree={result.ui_tree_available}, screenshot={result.screenshot_available}"
            )
        except Exception as e:
            logger.warning(f"[Explorer] 混合感知获取失败: {e}")

    # ── 3. 注入 Skill 知识到 Agent ─────────────────────────────
    agent: ExplorerAgent = get_explorer_agent()
    if skill_context:
        agent.set_skill_context(skill_context)

    # ── 4. 调用 Agent 执行探索 ─────────────────────────────────
    exploration_result: Dict[str, Any] = await agent.run(
        test_goal=test_goal,
        ui_tree=ui_tree,
        screenshot_b64=screenshot_b64,
        device_name=device_name,
        history=state.get('messages', []),
    )

    # 获取本轮 Token 消耗
    token_summary: Dict[str, Any] = agent.get_token_summary()
    tokens_used: int = token_summary.get('total_tokens', 0)

    logger.info(
        f"[Explorer] 探索完成，下一步: {exploration_result.get('next_action', 'unknown')}"
    )

    # 构建返回结果
    result: Dict[str, Any] = {
        'node_outputs': {
            **state.get('node_outputs', {}),
            'explorer': exploration_result,
        },
        'messages': [
            {
                'role': 'assistant',
                'content': f"探索完成：{exploration_result.get('analysis', '')}",
            },
        ],
        'total_tokens_used': state.get('total_tokens_used', 0) + tokens_used,
        'skill_context': skill_context,
        'matched_skills': [{'name': s.name, 'tags': s.tags} for s in matched_skills],
        'device_connected': device_connected,
    }

    # 仅在有新感知数据时更新
    if ui_tree:
        result['ui_tree'] = ui_tree
    if screenshot_b64:
        result['screenshot_b64'] = screenshot_b64

    return result
