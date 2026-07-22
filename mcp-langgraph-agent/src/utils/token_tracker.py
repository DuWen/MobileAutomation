"""Token 消耗追踪模块。

追踪 LLM 调用的 Token 使用情况，包括每次调用的消耗统计、
各模型消耗汇总、以及成本估算功能。
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List


# ============================================================
# 模型定价表（每千 Token 的价格，单位：美元）
# 参考各模型官方定价，如有变动请及时更新
# ============================================================
_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    'gpt-4o':                {'input': 0.005,  'output': 0.015},
    'gpt-4o-mini':           {'input': 0.00015, 'output': 0.0006},
    'gpt-4-turbo':           {'input': 0.01,   'output': 0.03},
    'gpt-3.5-turbo':         {'input': 0.001,  'output': 0.002},
    'claude-3-5-sonnet':     {'input': 0.003,  'output': 0.015},
    'claude-3-sonnet':       {'input': 0.003,  'output': 0.015},
    'claude-3-haiku':        {'input': 0.00025,'output': 0.00125},
    'claude-3-opus':         {'input': 0.015,  'output': 0.075},
    'claude-3-5-haiku':      {'input': 0.0008, 'output': 0.004},
}


@dataclass
class TokenUsageRecord:
    """单次 LLM 调用的 Token 消耗记录。

    Attributes:
        timestamp: 调用时间戳（秒）
        model: 使用的模型名称
        model_tier: 模型层级（light/standard/precise）
        prompt_tokens: 提示词消耗的 Token 数
        completion_tokens: 补全消耗的 Token 数
        total_tokens: 总 Token 消耗数
        cost: 估算成本（美元）
        operation: 操作描述（如 "explore", "plan", "execute" 等）
    """
    timestamp: float
    model: str
    model_tier: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    operation: str = ''


class TokenTracker:
    """Token 消耗追踪器。

    记录并统计所有 LLM 调用的 Token 使用情况，提供成本估算和报告导出功能。
    使用线程安全的 defaultdict 存储记录，支持并发调用。

    Attributes:
        records: Token 消耗记录列表
        session_start: 当前会话开始时间戳
    """

    def __init__(self) -> None:
        """初始化 Token 追踪器。"""
        self.records: List[TokenUsageRecord] = []
        self.session_start: float = time.time()

    def add_record(
        self,
        model: str,
        model_tier: str,
        prompt_tokens: int,
        completion_tokens: int,
        operation: str = '',
    ) -> TokenUsageRecord:
        """添加一条 Token 消耗记录。

        自动计算总 Token 数和成本，并记录当前时间戳。

        Args:
            model: 使用的模型名称
            model_tier: 模型层级（light/standard/precise）
            prompt_tokens: 提示词 Token 数
            completion_tokens: 补全 Token 数
            operation: 操作描述

        Returns:
            创建的 TokenUsageRecord 实例
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        record = TokenUsageRecord(
            timestamp=time.time(),
            model=model,
            model_tier=model_tier,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            operation=operation,
        )
        self.records.append(record)
        return record

    def get_summary(self) -> Dict:
        """获取累积统计摘要。

        计算所有记录的汇总数据，包括总消耗、各模型消耗等。

        Returns:
            包含统计信息的字典，包含：
            - total_records: 总调用次数
            - total_prompt_tokens: 总提示词 Token 数
            - total_completion_tokens: 总补全 Token 数
            - total_tokens: 总 Token 数
            - total_cost: 总成本（美元）
            - by_model: 按模型分组的统计
            - by_tier: 按层级分组的统计
            - session_duration: 会话持续时间（秒）
        """
        if not self.records:
            return {
                'total_records': 0,
                'total_prompt_tokens': 0,
                'total_completion_tokens': 0,
                'total_tokens': 0,
                'total_cost': 0.0,
                'by_model': {},
                'by_tier': {},
                'session_duration': time.time() - self.session_start,
            }

        # 按模型分组统计
        by_model: Dict[str, Dict] = defaultdict(
            lambda: {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'cost': 0.0}
        )
        # 按层级分组统计
        by_tier: Dict[str, Dict] = defaultdict(
            lambda: {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'cost': 0.0}
        )

        total_prompt = 0
        total_completion = 0
        total_tokens = 0
        total_cost = 0.0

        for r in self.records:
            by_model[r.model]['calls'] += 1
            by_model[r.model]['prompt_tokens'] += r.prompt_tokens
            by_model[r.model]['completion_tokens'] += r.completion_tokens
            by_model[r.model]['total_tokens'] += r.total_tokens
            by_model[r.model]['cost'] += r.cost

            by_tier[r.model_tier]['calls'] += 1
            by_tier[r.model_tier]['prompt_tokens'] += r.prompt_tokens
            by_tier[r.model_tier]['completion_tokens'] += r.completion_tokens
            by_tier[r.model_tier]['total_tokens'] += r.total_tokens
            by_tier[r.model_tier]['cost'] += r.cost

            total_prompt += r.prompt_tokens
            total_completion += r.completion_tokens
            total_tokens += r.total_tokens
            total_cost += r.cost

        return {
            'total_records': len(self.records),
            'total_prompt_tokens': total_prompt,
            'total_completion_tokens': total_completion,
            'total_tokens': total_tokens,
            'total_cost': round(total_cost, 6),
            'by_model': dict(by_model),
            'by_tier': dict(by_tier),
            'session_duration': round(time.time() - self.session_start, 2),
        }

    def get_records(self, operation: str | None = None) -> List[TokenUsageRecord]:
        """获取 Token 消耗记录列表。

        Args:
            operation: 可选的操作描述过滤条件

        Returns:
            TokenUsageRecord 记录列表
        """
        if operation:
            return [r for r in self.records if r.operation == operation]
        return list(self.records)

    def export_report(self, format: str = 'json') -> str:
        """导出消耗报告。

        将 Token 消耗统计导出为指定格式的字符串。

        Args:
            format: 导出格式，支持 'json' 和 'text'

        Returns:
            格式化的报告字符串

        Raises:
            ValueError: 不支持的导出格式
        """
        summary = self.get_summary()

        if format == 'json':
            # 将记录中的 dataclass 转换为字典
            records_dict = [
                {
                    'timestamp': r.timestamp,
                    'model': r.model,
                    'model_tier': r.model_tier,
                    'prompt_tokens': r.prompt_tokens,
                    'completion_tokens': r.completion_tokens,
                    'total_tokens': r.total_tokens,
                    'cost': r.cost,
                    'operation': r.operation,
                }
                for r in self.records
            ]
            report = {
                'summary': summary,
                'records': records_dict,
            }
            return json.dumps(report, ensure_ascii=False, indent=2)

        elif format == 'text':
            lines = [
                '=' * 60,
                'Token 消耗报告',
                '=' * 60,
                f'总调用次数: {summary["total_records"]}',
                f'总提示词 Token: {summary["total_prompt_tokens"]:,}',
                f'总补全 Token: {summary["total_completion_tokens"]:,}',
                f'总 Token 消耗: {summary["total_tokens"]:,}',
                f'总成本: ${summary["total_cost"]:.6f}',
                f'会话时长: {summary["session_duration"]:.2f} 秒',
                '',
                '--- 按模型分组 ---',
            ]
            for model, stats in summary['by_model'].items():
                lines.append(f'  {model}:')
                lines.append(f'    调用次数: {stats["calls"]}')
                lines.append(f'    Token: {stats["total_tokens"]:,} (prompt: {stats["prompt_tokens"]:,}, completion: {stats["completion_tokens"]:,})')
                lines.append(f'    成本: ${stats["cost"]:.6f}')

            lines.extend([
                '',
                '--- 按层级分组 ---',
            ])
            for tier, stats in summary['by_tier'].items():
                lines.append(f'  {tier}:')
                lines.append(f'    调用次数: {stats["calls"]}')
                lines.append(f'    Token: {stats["total_tokens"]:,} (prompt: {stats["prompt_tokens"]:,}, completion: {stats["completion_tokens"]:,})')
                lines.append(f'    成本: ${stats["cost"]:.6f}')

            lines.append('=' * 60)
            return '\n'.join(lines)

        else:
            raise ValueError(f"不支持的导出格式: {format}，仅支持 'json' 和 'text'")

    def reset(self) -> None:
        """重置追踪器，清空所有记录并重置会话时间。"""
        self.records.clear()
        self.session_start = time.time()

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """估算单次调用的成本。

        根据模型定价表计算输入和输出 Token 的成本。

        Args:
            model: 模型名称
            prompt_tokens: 提示词 Token 数
            completion_tokens: 补全 Token 数

        Returns:
            估算成本（美元）
        """
        pricing = _MODEL_PRICING.get(model, {'input': 0.002, 'output': 0.002})
        input_cost = (prompt_tokens / 1000) * pricing['input']
        output_cost = (completion_tokens / 1000) * pricing['output']
        return round(input_cost + output_cost, 8)