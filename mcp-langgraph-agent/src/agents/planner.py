"""规划 Agent 模块。

基于探索结果生成详细的测试步骤计划，
将自然语言测试目标转换为可执行的结构化步骤序列。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.agents.llm import ModelRouter
from src.agents.prompts import PLANNER_PROMPT
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """规划 Agent，生成结构化测试步骤。

    使用 standard 层级模型进行测试步骤规划，
    将测试目标分解为可执行的步骤序列，包含预期结果和超时设置。

    Attributes:
        DEFAULT_MODEL_TIER: 使用 standard 层级模型（标准规划任务）
    """

    DEFAULT_MODEL_TIER: str = 'standard'

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """初始化 PlannerAgent。

        Args:
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
        """
        super().__init__(
            name='planner',
            model_router=model_router,
            token_tracker=token_tracker,
        )

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """运行规划 Agent 的核心逻辑。

        基于探索结果生成详细的测试步骤计划。

        Args:
            **kwargs: 包含以下参数：
                - test_goal: 测试目标描述
                - ui_tree: 当前界面 UI 树
                - screenshot_b64: 当前界面截图 Base64
                - exploration_result: 探索节点的输出结果
                - executed_steps: 已执行步骤列表（重新规划场景传入）
                - is_replan: 是否为重新规划场景

        Returns:
            测试计划字典，包含 goal, steps, expected_results 等字段
        """
        test_goal: str = kwargs.get('test_goal', '')
        ui_tree: str = kwargs.get('ui_tree', '')
        screenshot_b64: str = kwargs.get('screenshot_b64', '')
        exploration_result: dict = kwargs.get('exploration_result', {})
        executed_steps: list = kwargs.get('executed_steps', None) or []
        is_replan: bool = kwargs.get('is_replan', False)

        # 构建消息序列
        messages = [
            {
                'role': 'system',
                'content': PLANNER_PROMPT.format(
                    test_goal=test_goal,
                    ui_tree=ui_tree or '(未提供)',
                    screenshot_description='有截图' if screenshot_b64 else '无截图',
                    exploration_result=str(exploration_result),
                    executed_steps_context=str(executed_steps) if is_replan else '(无)',
                    replan_instruction=(
                        '## 重新规划场景\n'
                        '前置步骤已部分执行（见上方"已执行步骤"），请基于当前界面 UI 树\n'
                        '和已通过步骤，仅规划**剩余未完成**的步骤。不要重复规划已通过步骤。\n'
                        '步骤编号从 1 开始重新计数。'
                    ) if is_replan else '(无)'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'请基于探索分析结果，为测试目标「{test_goal}」生成详细的测试步骤计划。'
                    f'确保每个步骤都包含操作类型、目标元素、参数和预期结果。'
                ),
            },
        ]

        # 调用 LLM 获取规划结果
        response: str = await self.call_llm_async(
            messages=messages,
            model_tier=self.DEFAULT_MODEL_TIER,
            operation='plan',
        )

        # 解析 LLM 返回的 JSON 结果
        plan_result: Dict[str, Any] = self._parse_json_response(
            response,
            fallback=self._generate_fallback_plan(test_goal),
        )

        # 从规划结果中提取步骤列表
        test_steps: List[str] = self._extract_steps(plan_result)
        expected_results: List[str] = plan_result.get('verification_points', [])

        # 构建结构化测试计划
        test_plan: Dict[str, Any] = {
            'goal': test_goal,
            'steps': test_steps,
            'expected_results': expected_results,
            'preconditions': plan_result.get('preconditions', []),
            'cleanup': plan_result.get('cleanup', []),
            'estimated_duration': f'{len(test_steps) * 1.5:.0f} 分钟',
        }

        logger.info(f"[PlannerAgent] 规划完成，共 {len(test_steps)} 个步骤")

        return {
            'test_plan': test_plan,
            'test_steps': test_steps,
            'raw_plan': plan_result,
        }

    def _extract_steps(self, plan_result: Dict[str, Any]) -> List[str]:
        """从规划结果中提取步骤描述列表。

        支持多种步骤格式：steps 数组中的 step 对象或纯字符串。

        Args:
            plan_result: LLM 返回的规划结果

        Returns:
            步骤描述字符串列表
        """
        steps: List[str] = []
        raw_steps = plan_result.get('steps', [])

        for step in raw_steps:
            if isinstance(step, dict):
                # 结构化步骤格式：提取关键信息组合为描述
                action = step.get('action', 'unknown')
                target = step.get('target', '')
                params = step.get('params', '')
                step_num = step.get('step_number', len(steps) + 1)
                step_desc = f"步骤 {step_num}: {action}"
                if target:
                    step_desc += f" -> {target}"
                if params:
                    step_desc += f" ({params})"
                steps.append(step_desc)
            elif isinstance(step, str):
                steps.append(step)

        return steps

    def _generate_fallback_plan(self, test_goal: str) -> Dict[str, Any]:
        """生成 fallback 测试计划。

        当 LLM 返回无法解析时使用，提供基本的测试步骤框架。

        Args:
            test_goal: 测试目标描述

        Returns:
            默认测试计划字典
        """
        return {
            'test_goal_restatement': test_goal,
            'preconditions': ['应用已安装并启动', '设备连接正常'],
            'steps': [
                {'step_number': 1, 'action': 'tap', 'target': '应用图标', 'params': '', 'expected_result': '应用启动成功', 'timeout': 10},
                {'step_number': 2, 'action': 'tap', 'target': '目标功能入口', 'params': '', 'expected_result': '功能页面加载', 'timeout': 10},
                {'step_number': 3, 'action': 'assert', 'target': '功能验证点', 'params': '', 'expected_result': '验证通过', 'timeout': 5},
            ],
            'verification_points': ['应用正常启动', '目标功能可访问', '功能验证通过'],
            'cleanup': [],
        }

    def _parse_json_response(self, response: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON 格式响应。

        尝试从 LLM 回复中提取 JSON 对象，解析失败时返回 fallback 结果。

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
            logger.warning("[PlannerAgent] LLM 返回非 JSON 格式，使用 fallback")
            return fallback
