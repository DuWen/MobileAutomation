"""执行 Agent 模块。

负责执行当前测试步骤，调用 MCP 工具（tap、input、swipe 等），
并记录执行结果和截图。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

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

    # MCP 工具名映射表：LLM 常用的工具名 → MCP Server 注册的工具名
    TOOL_NAME_MAP: dict[str, str] = {
        'mobile_tap': 'tap_element',
        'mobile_input_text': 'input_text',
        'mobile_swipe': 'swipe',
        'mobile_swipe_element': 'swipe_element',
        'mobile_click': 'tap_element',
        'mobile_type': 'input_text',
        'tap': 'tap_element',
        'click': 'tap_element',
        'input': 'input_text',
        'type': 'input_text',
        'swipe': 'swipe',
        'swipe_element': 'swipe_element',
        'drag_element': 'swipe_element',
        'scroll': 'scroll',
        'screenshot': 'take_screenshot',
        'get_ui_tree': 'get_ui_tree',
        'assert_text': 'assert_text_visible',
    }

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

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """运行执行 Agent 的核心逻辑。

        分析当前测试步骤，调用 LLM 决定需要执行的操作，
        然后通过 MCP 工具执行操作并记录结果。

        Args:
            **kwargs: 包含以下参数：
                - current_step: 当前步骤描述（字符串）
                - current_step_index: 当前步骤索引
                - ui_tree: 当前界面 UI 树
                - screenshot_b64: 当前界面截图 Base64
                - test_plan: 测试步骤计划（列表或字典）
                - executed_steps: 已执行的步骤历史

        Returns:
            执行结果字典，包含 step, action, result, passed 等字段
        """
        current_step: str = kwargs.get('current_step', '')
        current_step_index: int = kwargs.get('current_step_index', 0)
        ui_tree: str = kwargs.get('ui_tree', '')
        screenshot_b64: str = kwargs.get('screenshot_b64', '')
        test_plan = kwargs.get('test_plan', [])
        executed_steps: list = kwargs.get('executed_steps', [])
        # 当前设备名称，所有 MCP 工具调用都需要此参数
        device_name: str = kwargs.get('device_name', '')

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
        action_result: dict[str, Any] = self._parse_json_response(
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
        mcp_calls: list[dict[str, Any]] = []
        tool_actions = action_result.get('tool_actions', [])

        # 如果有 MCP Client，执行工具调用
        if self.mcp_client and tool_actions:
            mcp_calls = await self._execute_mcp_tools(tool_actions, device_name)
        elif self.mcp_client and not tool_actions:
            # 没有明确的工具调用时，尝试从 action_performed 推断
            inferred_calls = self._infer_tool_calls(
                action_result.get('action_performed', ''), current_step, device_name
            )
            if inferred_calls:
                mcp_calls = await self._execute_mcp_tools(inferred_calls, device_name)

        # 判断 passed：严格基于 MCP 调用结果，忽略 LLM 返回的 status
        passed: bool = False
        failed_tools: list[str] = []

        if mcp_calls:
            # 有 MCP 调用时，检查所有调用是否真正成功
            all_mcp_success = all(
                call.get('success', False) for call in mcp_calls
            )
            passed = all_mcp_success
            if not passed:
                failed_tools = [
                    call.get('tool', '') for call in mcp_calls if not call.get('success', False)
                ]
                logger.warning(
                    f"[ExecutorAgent] MCP 工具调用失败: {failed_tools}"
                )
        else:
            # 没有 MCP 调用，标记为未执行
            passed = False
            if not self.mcp_client:
                logger.warning("[ExecutorAgent] 无 MCP Client，步骤未真正执行")
            else:
                logger.warning("[ExecutorAgent] 无法推断任何工具调用，步骤未执行")

        # 基于 MCP 实际调用结果生成 result，不使用 LLM 幻觉的 ui_changes
        actual_result: str = self._get_actual_result(mcp_calls, action_result)

        # 收集 MCP 调用中的错误信息
        error_info: str | None = action_result.get('error_info')
        if not passed and mcp_calls:
            # 补充 MCP 失败的详细错误信息
            mcp_errors = [
                f"{call.get('tool', '')}: {call.get('error', '') or call.get('result', {}).get('data', {}).get('message', '未知错误')}"
                for call in mcp_calls if not call.get('success', False)
            ]
            mcp_error_str = '; '.join(mcp_errors)
            error_info = mcp_error_str if not error_info else f"{error_info}; {mcp_error_str}"

        execution_record: dict[str, Any] = {
            'step': current_step,
            'step_index': current_step_index,
            'action': action_result.get('action_performed', current_step),
            'result': actual_result,
            'screenshot': screenshot_b64,
            'passed': passed,
            'mcp_calls': mcp_calls,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'error': error_info,
        }

        logger.info(
            f"[ExecutorAgent] 步骤 [{current_step_index + 1}] 执行完成，"
            f"状态: {'passed' if passed else 'failed'}, MCP 调用: {len(mcp_calls)}"
        )

        return execution_record

    async def _execute_mcp_tools(
        self, tool_actions: list[dict[str, Any]], device_name: str = ''
    ) -> list[dict[str, Any]]:
        """执行 MCP 工具调用列表。

        依次调用每个工具，自动映射工具名并注入 device_name，
        记录调用结果，支持失败后继续执行。

        Args:
            tool_actions: 工具调用列表，每个包含 tool 和 params 字段
            device_name: 当前设备名称，所有 MCP 工具的第一参数都需要

        Returns:
            工具调用结果列表
        """
        results: list[dict[str, Any]] = []

        for action in tool_actions:
            raw_name: str = action.get('tool', '')
            # 映射工具名：LLM 可能使用 mobile_tap 等非标准名，需转为 MCP 注册名
            tool_name: str = self.TOOL_NAME_MAP.get(raw_name, raw_name)
            params: dict[str, Any] = action.get('params', {})

            if not tool_name:
                continue

            if tool_name != raw_name:
                logger.info(
                    f"[ExecutorAgent] 工具名映射: {raw_name} -> {tool_name}"
                )

            # 自动注入 device_name：所有 MCP 工具都需要此参数
            # LLM 经常遗漏，必须强制补充
            if device_name and 'device_name' not in params:
                params['device_name'] = device_name

            try:
                result = await self.mcp_client.call_tool(tool_name, params)
                # 检查 MCP 工具返回结果是否表示失败
                mcp_success = True
                if isinstance(result, dict):
                    mcp_success = result.get('success', True)
                results.append({
                    'tool': tool_name,
                    'params': params,
                    'status': 'success' if mcp_success else 'failed',
                    'result': result,
                    'success': mcp_success,  # 基于工具返回的 success 字段
                })
                if mcp_success:
                    logger.info(f"[ExecutorAgent] MCP 工具 {tool_name} 调用成功")
                else:
                    error_msg = result.get('data', {}).get('message', '未知错误') if isinstance(result, dict) else '未知错误'
                    logger.warning(f"[ExecutorAgent] MCP 工具 {tool_name} 返回失败: {error_msg}")
            except Exception as e:  # noqa: BLE001
                results.append({
                    'tool': tool_name,
                    'params': params,
                    'status': 'error',
                    'error': str(e),
                    'success': False,
                })
                logger.warning(f"[ExecutorAgent] MCP 工具 {tool_name} 调用失败: {e}")

        return results

    def _get_actual_result(
        self, mcp_calls: list[dict], action_result: dict
    ) -> str:
        """基于 MCP 实际调用结果生成执行结果描述。

        当 MCP 调用存在时，使用真实调用结果；否则使用 LLM 返回的 ui_changes。
        避免 LLM 幻觉导致 MCP 失败时仍记录"成功"。

        Args:
            mcp_calls: MCP 工具调用结果列表
            action_result: LLM 返回的操作结果

        Returns:
            实际执行结果描述
        """
        if not mcp_calls:
            return action_result.get('ui_changes', '未执行任何操作')

        results = []
        for call in mcp_calls:
            tool = call.get('tool', 'unknown')
            if call.get('success', False):
                # 成功时使用 MCP 返回的消息
                result_data = call.get('result', {})
                if isinstance(result_data, dict):
                    msg = result_data.get('data', {}).get('message', f'{tool} 成功')
                else:
                    msg = f'{tool} 成功'
                results.append(msg)
            else:
                # 失败时使用 MCP 返回的错误信息
                error = call.get('error', '')
                if not error:
                    result_data = call.get('result', {})
                    if isinstance(result_data, dict):
                        error = result_data.get('data', {}).get('message', '未知错误')
                    else:
                        error = '未知错误'
                results.append(f'{tool} 失败: {error}')

        return '; '.join(results)

    def _infer_tool_calls(
        self, action_performed: str, current_step: str, device_name: str = ''
    ) -> list[dict[str, Any]]:
        """从操作描述推断 MCP 工具调用。

        当 LLM 没有返回明确的 tool_actions 时，从步骤描述中推断。
        关键：从步骤描述中提取精确的 by/value/text 参数，
        而非将整段描述作为定位值。

        步骤描述常见格式：
        - "输入 -> 账号输入框 (resource-id: com.xxx:id/et_account) (admin1)"
        - "点击 -> 登录按钮 (text: 登录)"
        - "滑动 -> 向下滚动"

        Args:
            action_performed: LLM 返回的操作描述
            current_step: 当前步骤描述
            device_name: 当前设备名称

        Returns:
            推断的工具调用列表
        """
        calls: list[dict[str, Any]] = []
        step_lower = current_step.lower()

        # 从步骤描述中提取定位参数
        locator = self._extract_locator_from_step(current_step)
        input_text_value = self._extract_input_text_from_step(current_step)

        if 'tap' in step_lower or '点击' in current_step or 'click' in step_lower:
            calls.append({
                'tool': 'tap_element',
                'params': {
                    'device_name': device_name,
                    'by': locator['by'],
                    'value': locator['value'],
                },
            })
        elif 'input' in step_lower or '输入' in current_step or 'type' in step_lower:
            calls.append({
                'tool': 'input_text',
                'params': {
                    'device_name': device_name,
                    'by': locator['by'],
                    'value': locator['value'],
                    'text': input_text_value,
                },
            })
        elif 'swipe' in step_lower or '滑动' in current_step:
            # 不再硬编码 0,0,0,0 坐标（会导致无效滑动但显示成功）
            # swipe 需要精确坐标，推断路径无法获取，跳过让 LLM 通过 tool_actions 自行决定
            logger.warning(
                "[ExecutorAgent] swipe 操作需要精确坐标或元素定位，"
                "推断路径无法生成有效参数，跳过推断"
            )

        return calls

    def _extract_locator_from_step(self, step: str) -> dict[str, str]:
        """从步骤描述中提取元素定位参数。

        按优先级解析步骤描述中的定位信息：
        1. resource-id 模式: "(resource-id: com.xxx:id/et_account)" → by=id
        2. xpath 模式: "(xpath: //node[@text='xxx'])" → by=xpath
        3. accessibility_id 模式: "(accessibility_id: btn_login)" → by=accessibility_id
        4. text 模式: "(text: 登录)" → by=text
        5. 纯括号内容: "(admin1)" → 当作 input 的 text 而非定位值
        6. 默认: 使用步骤中的关键词作为 text 定位

        Args:
            step: 步骤描述字符串

        Returns:
            包含 by 和 value 的定位字典
        """
        import re

        # 优先匹配 resource-id
        rid_match = re.search(r'resource-id[:\s]+([^\s)\]]+)', step)
        if rid_match:
            return {'by': 'id', 'value': rid_match.group(1).strip()}

        # 匹配 xpath
        xpath_match = re.search(r'xpath[:\s]+(//[^)\]]+)', step)
        if xpath_match:
            return {'by': 'xpath', 'value': xpath_match.group(1).strip()}

        # 匹配 accessibility_id
        aid_match = re.search(r'accessibility_id[:\s]+([^\s)\]]+)', step)
        if aid_match:
            return {'by': 'accessibility_id', 'value': aid_match.group(1).strip()}

        # 匹配显式 text 定位: "(text: 登录)"
        text_match = re.search(r'\btext[:\s]+([^)\]]+)', step)
        if text_match:
            return {'by': 'text', 'value': text_match.group(1).strip()}

        # 默认：提取箭头或步骤中的目标描述词作为 text 定位值
        # 如 "输入 -> 账号输入框 (admin1)" → value="账号输入框"
        arrow_match = re.search(r'[->→]+\s*([^(]+)', step)
        if arrow_match:
            target = arrow_match.group(1).strip()
            # 移除尾部的动作词
            for word in ['输入', '点击', '滑动', '长按', 'tap', 'click', 'input']:
                target = re.sub(rf'\b{word}\b', '', target, flags=re.IGNORECASE).strip()
            if target:
                return {'by': 'text', 'value': target}

        # 最终回退：使用整段描述（但限制长度避免过长）
        return {'by': 'text', 'value': step[:50]}

    def _extract_input_text_from_step(self, step: str) -> str:
        """从步骤描述中提取要输入的文本内容。

        解析步骤中最后一个括号内的值作为输入文本：
        - "账号输入框 (resource-id: com.xxx:id/et_account) (admin1)" → "admin1"
        - "输入密码 (123456)" → "123456"

        排除 resource-id / xpath / text 等定位描述的括号。

        Args:
            step: 步骤描述字符串

        Returns:
            提取到的输入文本，未找到则返回空字符串
        """
        import re

        # 查找所有括号内容
        paren_groups = re.findall(r'\(([^)]+)\)', step)
        for group in reversed(paren_groups):
            group = group.strip()
            # 跳过定位描述
            if group.startswith('resource-id:') or group.startswith('xpath:') or \
               group.startswith('accessibility_id:') or group.startswith('text:'):
                continue
            # 剩余的括号内容视为输入文本
            return group

        return ''

    def _parse_json_response(self, response: str, fallback: dict[str, Any]) -> dict[str, Any]:
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
