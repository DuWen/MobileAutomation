"""审查 Agent 模块。

负责审查整个测试流程的完整性和正确性，
生成测试报告摘要，并决定是否通过最终审查。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from src.agents.base import BaseAgent
from src.agents.llm import ModelRouter
from src.agents.prompts import REVIEWER_PROMPT
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """审查 Agent，审查测试流程的完整性和质量。

    使用 precise 层级模型进行最终审查分析，
    综合评估测试覆盖率、成功率和质量指标。

    Attributes:
        DEFAULT_MODEL_TIER: 使用 precise 层级模型（精确审查任务）
    """

    DEFAULT_MODEL_TIER: str = 'precise'

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """初始化 ReviewerAgent。

        Args:
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
        """
        super().__init__(
            name='reviewer',
            model_router=model_router,
            token_tracker=token_tracker,
        )

    async def run(self, **kwargs: Any) -> Dict[str, Any]:
        """运行审查 Agent 的核心逻辑。

        综合分析整个测试流程的执行记录和验证结果，给出最终审查结论。

        Args:
            **kwargs: 包含以下参数：
                - test_goal: 原始测试目标
                - test_plan: 测试计划
                - executed_steps: 已执行的步骤列表
                - verification_details: 验证详情列表
                - test_steps: 测试步骤列表

        Returns:
            审查结果字典，包含 passed, feedback, summary 等字段
        """
        test_goal: str = kwargs.get('test_goal', '')
        test_plan: dict = kwargs.get('test_plan', {})  # noqa: F841 - 保留以备后续使用
        executed_steps: list = kwargs.get('executed_steps', [])
        verification_details: list = kwargs.get('verification_details', [])
        test_steps: list = kwargs.get('test_steps', [])

        total_steps: int = len(test_steps)
        completed_steps: int = len(executed_steps)

        # 构建执行日志摘要
        execution_log: str = (
            f"步骤数: {completed_steps}/{total_steps}, "
            f"执行记录: {executed_steps}"
        )
        verification_result: str = str(verification_details)

        # 构建 LLM 消息序列
        messages = [
            {
                'role': 'system',
                'content': REVIEWER_PROMPT.format(
                    test_goal=test_goal,
                    execution_log=execution_log,
                    verification_result=verification_result,
                ),
            },
            {
                'role': 'user',
                'content': '请审查整个测试流程的完整性和质量，给出最终结论。',
            },
        ]

        # 调用 LLM 进行审查分析
        response: str = await self.call_llm_async(
            messages=messages,
            model_tier=self.DEFAULT_MODEL_TIER,
            operation='review',
        )

        # 解析 LLM 返回的审查结果
        review_result: Dict[str, Any] = self._parse_json_response(
            response,
            fallback=self._generate_fallback_review(
                test_goal, total_steps, completed_steps, verification_details
            ),
        )

        # 提取审查结论
        overall_assessment: str = review_result.get('overall_assessment', 'inconclusive')
        passed: bool = overall_assessment in ('passed', 'pass')
        feedback: str = review_result.get('summary', '审查完成')

        # 计算质量指标
        quality_metrics: Dict[str, Any] = self._calculate_quality_metrics(
            executed_steps, verification_details, total_steps
        )

        logger.info(
            f"[ReviewerAgent] 审查完成，结论: {overall_assessment}，"
            f"通过: {passed}"
        )

        return {
            'passed': passed,
            'feedback': feedback,
            'overall_assessment': overall_assessment,
            'quality_metrics': quality_metrics,
            'issues_found': review_result.get('issues_found', []),
            'recommendations': review_result.get('recommendations', []),
            'coverage_analysis': review_result.get('coverage_analysis', {}),
            'final_verdict': review_result.get('final_verdict', 'need_manual_check'),
        }

    def _calculate_quality_metrics(
        self,
        executed_steps: list,
        verification_details: list,
        total_steps: int,
    ) -> Dict[str, Any]:
        """计算测试质量指标。

        综合执行和验证数据，计算成功率、通过率等指标。

        Args:
            executed_steps: 已执行的步骤列表
            verification_details: 验证详情列表
            total_steps: 总步骤数

        Returns:
            质量指标字典
        """
        completed_steps = len(executed_steps)
        failed_steps = sum(1 for s in executed_steps if not s.get('passed', True))
        passed_steps = completed_steps - failed_steps

        # 计算验证通过率
        passed_verifications = sum(
            1 for d in verification_details if d.get('passed', False)
        )
        total_verifications = len(verification_details)

        execution_success_rate: float = (
            passed_steps / completed_steps if completed_steps > 0 else 0.0
        )
        verification_pass_rate: float = (
            passed_verifications / total_verifications if total_verifications > 0 else 0.0
        )

        return {
            'execution_success_rate': round(execution_success_rate, 4),
            'verification_pass_rate': round(verification_pass_rate, 4),
            'total_steps': total_steps,
            'completed_steps': completed_steps,
            'failed_steps': failed_steps,
            'passed_verifications': passed_verifications,
            'total_verifications': total_verifications,
        }

    def _generate_fallback_review(
        self,
        test_goal: str,
        total_steps: int,
        completed_steps: int,
        verification_details: list,
    ) -> Dict[str, Any]:
        """生成 fallback 审查结果。

        当 LLM 返回无法解析时使用，基于执行和验证数据直接判断。

        Args:
            test_goal: 测试目标
            total_steps: 总步骤数
            completed_steps: 已完成步骤数
            verification_details: 验证详情列表

        Returns:
            默认审查结果字典
        """
        all_steps_executed: bool = completed_steps >= total_steps
        all_verifications_passed: bool = all(
            d.get('passed', False) for d in verification_details
        ) if verification_details else False

        if all_steps_executed and all_verifications_passed:
            overall_assessment = 'passed'
            feedback = (
                f"审查通过。所有 {total_steps} 个步骤已执行完毕，验证全部通过。"
            )
            final_verdict = 'pass'
        elif all_steps_executed and not all_verifications_passed:
            overall_assessment = 'partial'
            feedback = (
                "部分通过。所有步骤已执行，但部分验证项未通过。"
            )
            final_verdict = 'need_manual_check'
        else:
            overall_assessment = 'failed'
            feedback = (
                f"审查未通过。已完成 {completed_steps}/{total_steps} 个步骤。"
            )
            final_verdict = 'fail'

        return {
            'overall_assessment': overall_assessment,
            'summary': feedback,
            'issues_found': [],
            'recommendations': [],
            'final_verdict': final_verdict,
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
            logger.warning("[ReviewerAgent] LLM 返回非 JSON 格式，使用 fallback")
            return fallback
