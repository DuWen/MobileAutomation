"""验证 Agent 模块。

负责验证执行结果是否符合预期，
使用 LLM 分析截图和 UI 树来判断执行成功与否。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.agents.llm import ModelRouter
from src.agents.prompts import VERIFIER_PROMPT
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class VerifierAgent(BaseAgent):
    """验证 Agent，验证执行结果是否符合预期。

    使用 precise 层级模型进行验证分析，
    多维度检查执行结果的正确性，生成验证详情和结论。

    Attributes:
        DEFAULT_MODEL_TIER: 使用 precise 层级模型（精确验证任务）
    """

    DEFAULT_MODEL_TIER: str = 'precise'

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """初始化 VerifierAgent。

        Args:
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
        """
        super().__init__(
            name='verifier',
            model_router=model_router,
            token_tracker=token_tracker,
        )

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """运行验证 Agent 的核心逻辑。

        分析执行结果和当前界面状态，判断步骤是否成功。

        Args:
            **kwargs: 包含以下参数：
                - execution_record: 上一步的执行记录
                - ui_tree: 当前界面 UI 树
                - screenshot_b64: 当前界面截图 Base64
                - test_plan: 测试步骤计划列表

        Returns:
            验证结果字典，包含 verification_passed, failure_reason 等字段
        """
        execution_record: dict = kwargs.get('execution_record', {})
        ui_tree: str = kwargs.get('ui_tree', '')
        screenshot_b64: str = kwargs.get('screenshot_b64', '')
        test_plan: list = kwargs.get('test_plan', [])

        # 从测试计划中提取验证点（兼容 str 和 dict 两种步骤格式）
        verification_points: list = []
        if test_plan:
            for step in test_plan:
                if isinstance(step, dict):
                    expected = step.get('expected', step.get('expected_result', ''))
                    if expected:
                        verification_points.append(expected)
                elif isinstance(step, str):
                    # 字符串步骤无法提取预期结果，跳过
                    pass

        # 构建 LLM 消息序列
        messages = [
            {
                'role': 'system',
                'content': VERIFIER_PROMPT.format(
                    verification_points=str(verification_points),
                    executed_actions=str(execution_record),
                    ui_tree=ui_tree or '(未提供)',
                    screenshot_description='有截图' if screenshot_b64 else '无截图',
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'请验证步骤「{execution_record.get("step", "未知")}」的执行结果。'
                    f'操作状态: {execution_record.get("result", "未知")}'
                ),
            },
        ]

        # 调用 LLM 进行验证分析
        response: str = await self.call_llm_async(
            messages=messages,
            model_tier=self.DEFAULT_MODEL_TIER,
            operation='verify',
        )

        # 解析 LLM 返回的验证结果
        verify_result: Dict[str, Any] = self._parse_json_response(
            response,
            fallback=self._generate_fallback_verification(execution_record, verification_points),
        )

        # 提取验证详情
        verification_details: List[Dict[str, Any]] = self._extract_verification_details(
            verify_result, execution_record, verification_points
        )

        # 判断总体是否通过
        overall_status: str = verify_result.get('overall_status', 'partial')
        execution_passed: bool = execution_record.get('passed', False)

        # MCP 执行成功时，partial 视为 passed
        # 小模型常返回 partial 而非 passed，当 MCP 已确认操作成功时应信任 MCP 结果
        if overall_status == 'partial' and execution_passed:
            verification_passed: bool = True
            logger.info(
                "[VerifierAgent] MCP 执行成功，partial 视为 passed"
            )
        else:
            verification_passed = overall_status == 'passed'

        # 生成失败原因（验证不通过时）
        failure_reason: str = ''
        if not verification_passed:
            failure_reason = verify_result.get('summary', '')
            if not failure_reason and verification_details:
                failed_items = [d.get('check', '') for d in verification_details if not d.get('passed', False)]
                failure_reason = f"验证未通过: {', '.join(failed_items)}" if failed_items else '验证未通过'

        logger.info(
            f"[VerifierAgent] 验证完成，结果: {overall_status}，"
            f"详情数: {len(verification_details)}"
        )

        return {
            'verification_passed': verification_passed,
            'failure_reason': failure_reason,
            'overall_status': overall_status,
            'summary': verify_result.get('summary', ''),
            'suggestions': verify_result.get('suggestions', []),
        }

    def _extract_verification_details(
        self,
        verify_result: Dict[str, Any],
        execution_record: Dict[str, Any],
        verification_points: List[str],
    ) -> List[Dict[str, Any]]:
        """从验证结果中提取结构化验证详情。

        统一不同格式的验证详情为标准格式。

        Args:
            verify_result: LLM 返回的验证结果
            execution_record: 执行记录
            verification_points: 验证点列表

        Returns:
            标准化的验证详情列表
        """
        details: List[Dict[str, Any]] = []

        # 从 LLM 结果中提取详情
        raw_details = verify_result.get('verification_details', [])
        if raw_details:
            for detail in raw_details:
                if isinstance(detail, dict):
                    details.append({
                        'check': detail.get('point', detail.get('check', '')),
                        'expected': detail.get('expected', ''),
                        'actual': detail.get('actual', ''),
                        'passed': detail.get('status', 'passed') == 'passed',
                        'evidence': detail.get('evidence', ''),
                    })

        # 如果没有详情，基于验证点生成
        if not details and verification_points:
            for point in verification_points:
                details.append({
                    'check': point,
                    'expected': point,
                    'actual': execution_record.get('result', '未知'),
                    'passed': execution_record.get('passed', False),
                    'evidence': '基于执行记录判断',
                })

        # 如果仍然没有详情，生成一条默认记录
        if not details:
            details.append({
                'check': f"步骤「{execution_record.get('step', '未知')}」执行成功",
                'expected': '操作应成功执行',
                'actual': execution_record.get('result', '未知'),
                'passed': execution_record.get('passed', False),
                'evidence': '基于执行记录判断',
            })

        return details

    def _generate_fallback_verification(
        self,
        execution_record: Dict[str, Any],
        verification_points: List[str],
    ) -> Dict[str, Any]:
        """生成 fallback 验证结果。

        当 LLM 返回无法解析时使用，基于执行记录中的 passed 字段生成验证结果。

        Args:
            execution_record: 执行记录
            verification_points: 验证点列表

        Returns:
            默认验证结果字典
        """
        execution_passed = execution_record.get('passed', False)
        return {
            'overall_status': 'passed' if execution_passed else 'failed',
            'verification_details': [
                {
                    'point': f"步骤「{execution_record.get('step', '未知')}」执行状态",
                    'expected': '成功执行',
                    'actual': '成功' if execution_passed else '失败',
                    'status': 'passed' if execution_passed else 'failed',
                    'evidence': '基于执行记录判断',
                }
            ],
            'summary': '验证基于执行记录判断' if execution_passed else '执行记录表明步骤失败',
            'suggestions': [] if execution_passed else ['建议重试当前步骤'],
        }

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
            logger.warning("[VerifierAgent] LLM 返回非 JSON 格式，使用 fallback")
            return fallback
