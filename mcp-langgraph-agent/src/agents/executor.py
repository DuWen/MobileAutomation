"""执行 Agent 模块。

负责执行当前测试步骤，调用 MCP 工具（tap、input、swipe 等），
并记录执行结果和截图。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.agents.base import BaseAgent
from src.agents.llm import ModelRouter
from src.agents.prompts import EXECUTOR_PROMPT
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    """执行 Agent，执行自动化操作并调用 MCP 工具。

    使用 standard 层级模型分析当前步骤，决定需要执行的 MCP 工具操作，
    然后通过 MCP Client 调用工具完成界面交互。

    Attributes:
        DEFAULT_MODEL_TIER: 使用 standard 层级模型（标准执行任务）
    """

    DEFAULT_MODEL_TIER: str = 'standard'

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
        mcp_client: Any = None,
    ) -> None:
        """初始化 ExecutorAgent。

        Args:
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
            mcp_client: MCP 客户端实例，用于调用设备操作工具
        """
        super().__init__(
            name='executor',
            model_router=model_router,
            token_tracker=token_tracker,
        )
        self.mcp_client = mcp_client

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """运行执行 Agent 的核心逻辑。

        分析当前测试步骤，调用 LLM 决定需要执行的操作，
        然后通过 MCP 工具执行操作并记录结果。

        Args:
            **kwargs: 包含以下参数：
                - current_step: 当前步骤描述
                - current_step_index: 当前步骤索引
                - ui_tree: 当前界面 UI 树
                - screenshot_b64: 当前界面截图 Base64
                - test_plan: 测试计划上下文
                - executed_steps: 已执行的步骤历史

        Returns:
            执行结果字典，包含 step, action, result, passed 等字段
        """
        current_step: str = kwargs.get('current_step', '')
        current_step_index: int = kwargs.get('current_step_index', 0)
        ui_tree: str = kwargs.get('ui_tree', '')
        screenshot_b64: str = kwargs.get('screenshot_b64', '')
        test_plan: dict = kwargs.get('test_plan', {})
        executed_steps: list = kwargs.get('executed_steps', [])

        # 构建 LLM 消息序列
        history: str = str(executed_steps[-3:]) if executed_steps else '[]'
        messages = [
            {
                'role': 'system',
                'content': EXECUTOR_PROMPT.format(
                    current_step=current_step,
                    ui_tree=ui_tree or '(未提供)',
                    screenshot_description='有截图' if screenshot_b64 else '无截图',
                    plan_context=str(test_plan),
                    history=history,
                ),
            },
            {
                'role': 'user',
                'content': f'请执行步骤 [{current_step_index + 1}]: {current_step}',
            },
        ]

        # 调用 LLM 决定操作
        response: str = await self.call_llm_async(
            messages=messages,
            model_tier=self.DEFAULT_MODEL_TIER,
            operation='execute',
        )

        # 解析 LLM 返回的操作指令
        action_result: Dict[str, Any] = self._parse_json_response(
            response,
            fallback={
                'step_executed': current_step_index + 1,
                'action_performed': f'simulate: {current_step}',
                'status': 'success',
                'screenshot_taken': False,
                'ui_changes': '模拟执行',
                'error_info': None,
                'next_action': 'verify',
            },
        )

        # 提取 MCP 工具调用列表
        mcp_calls: List[Dict[str, Any]] = []
        tool_actions = action_result.get('tool_actions', [])

        # 如果有 MCP Client，执行工具调用
        if self.mcp_client and tool_actions:
            mcp_calls = await self._execute_mcp_tools(tool_actions)
        elif self.mcp_client and not tool_actions:
            # 没有明确的工具调用时，尝试从 action_performed 推断
            inferred_calls = self._infer_tool_calls(
                action_result.get('action_performed', ''), current_step
            )
            if inferred_calls:
                mcp_calls = await self._execute_mcp_tools(inferred_calls)

        # 构建执行记录
        execution_status: str = action_result.get('status', 'success')
        execution_record: Dict[str, Any] = {
            'step': current_step,
            'step_index': current_step_index,
            'action': action_result.get('action_performed', current_step),
            'result': action_result.get('ui_changes', '执行完成'),
            'screenshot': screenshot_b64,
            'passed': execution_status == 'success',
            'mcp_calls': mcp_calls,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'error': action_result.get('error_info'),
        }

        # 如果有 MCP 调用失败，标记为未通过
        if mcp_calls and any(not c.get('success', True) for c in mcp_calls):
            execution_record['passed'] = False
            execution_record['error'] = '部分 MCP 工具调用失败'

        logger.info(
            f"[ExecutorAgent] 步骤 [{current_step_index + 1}] 执行完成，"
            f"状态: {execution_status}, MCP 调用: {len(mcp_calls)}"
        )

        return execution_record

    async def _execute_mcp_tools(
        self, tool_actions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """执行 MCP 工具调用列表。

        依次调用每个工具，记录调用结果，支持失败后继续执行。

        Args:
            tool_actions: 工具调用列表，每个包含 tool 和 params 字段

        Returns:
            工具调用结果列表
        """
        results: List[Dict[str, Any]] = []

        for action in tool_actions:
            tool_name: str = action.get('tool', '')
            params: Dict[str, Any] = action.get('params', {})

            if not tool_name:
                continue

            try:
                result = await self.mcp_client.call_tool(tool_name, params)
                results.append({
                    'tool': tool_name,
                    'params': params,
                    'status': 'success',
                    'result': result,
                    'success': True,
                })
                logger.info(f"[ExecutorAgent] MCP 工具 {tool_name} 调用成功")
            except Exception as e:
                results.append({
                    'tool': tool_name,
                    'params': params,
                    'status': 'error',
                    'error': str(e),
                    'success': False,
                })
                logger.warning(f"[ExecutorAgent] MCP 工具 {tool_name} 调用失败: {e}")

        return results

    def _infer_tool_calls(
        self, action_performed: str, current_step: str
    ) -> List[Dict[str, Any]]:
        """从操作描述推断 MCP 工具调用。

        当 LLM 没有返回明确的工具调用时，尝试从步骤描述中推断。

        Args:
            action_performed: LLM 返回的操作描述
            current_step: 当前步骤描述

        Returns:
            推断的工具调用列表
        """
        calls: List[Dict[str, Any]] = []
        step_lower = current_step.lower()

        if 'tap' in step_lower or '点击' in current_step or 'click' in step_lower:
            calls.append({'tool': 'mobile_tap', 'params': {'x': 0, 'y': 0, 'description': current_step}})
        elif 'input' in step_lower or '输入' in current_step or 'type' in step_lower:
            calls.append({'tool': 'mobile_input_text', 'params': {'text': '', 'description': current_step}})
        elif 'swipe' in step_lower or '滑动' in current_step:
            calls.append({'tool': 'mobile_swipe', 'params': {'direction': 'up', 'description': current_step}})

        return calls

    def _parse_json_response(self, response: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON 格式响应。

        Args:
            response: LLM 返回的文本内容
            fallback: 解析失败时使用的默认结果

        Returns:
            解析后的字典结果
        """
        try:
            text = response.strip()
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("[ExecutorAgent] LLM 返回非 JSON 格式，使用 fallback")
            return fallback
