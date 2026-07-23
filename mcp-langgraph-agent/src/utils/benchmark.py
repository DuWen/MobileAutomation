"""性能基准测试模块。

提供测试执行的性能度量与基准记录功能，包括单条用例执行时间、
Token 消耗效率、步骤通过率等关键指标的采集与趋势分析。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__('logging').getLogger(__name__)


# ============================================================
# 性能指标数据结构
# ============================================================


@dataclass
class BenchmarkResult:
    """单次测试性能基准结果。

    Attributes:
        task_id: 任务 ID
        test_goal: 测试目标描述
        duration: 测试总耗时（秒）
        step_count: 总步骤数
        passed_steps: 通过步骤数
        pass_rate: 步骤通过率（0~1）
        total_tokens: Token 消耗总量
        total_cost: API 成本（美元）
        tokens_per_step: 每步骤平均 Token 消耗
        cost_per_step: 每步骤平均成本
        duration_per_step: 每步骤平均耗时（秒）
        verdict: 最终结论
        timestamp: 记录时间戳
    """

    task_id: str
    test_goal: str
    duration: float
    step_count: int
    passed_steps: int
    pass_rate: float
    total_tokens: int
    total_cost: float
    tokens_per_step: float
    cost_per_step: float
    duration_per_step: float
    verdict: str
    timestamp: float = field(default_factory=time.time)


# ============================================================
# 性能基准测试器类
# ============================================================


class BenchmarkRunner:
    """性能基准测试器。

    采集测试执行的性能指标，保存历史记录，
    支持与历史基准对比分析。

    用法:
        runner = BenchmarkRunner(data_dir="data/benchmarks")
        result = runner.record_benchmark(
            task_id="abc",
            test_goal="测试登录",
            duration=45.2,
            step_count=5,
            passed_steps=4,
            total_tokens=12000,
            total_cost=0.15,
            verdict="pass",
        )
        summary = runner.get_summary()
    """

    def __init__(self, data_dir: str = "data/benchmarks") -> None:
        """初始化性能基准测试器。

        Args:
            data_dir: 基准数据存储目录
        """
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._history: List[BenchmarkResult] = []
        self._load_history()

    def record_benchmark(
        self,
        task_id: str,
        test_goal: str,
        duration: float,
        step_count: int,
        passed_steps: int,
        total_tokens: int,
        total_cost: float,
        verdict: str,
    ) -> BenchmarkResult:
        """记录一次测试的性能基准数据。

        根据步骤数计算每步骤的平均指标，并保存到历史记录。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            duration: 测试总耗时（秒）
            step_count: 总步骤数
            passed_steps: 通过步骤数
            total_tokens: Token 消耗总量
            total_cost: API 成本（美元）
            verdict: 最终结论

        Returns:
            BenchmarkResult 实例
        """
        pass_rate = passed_steps / step_count if step_count > 0 else 0.0
        tokens_per_step = total_tokens / step_count if step_count > 0 else 0.0
        cost_per_step = total_cost / step_count if step_count > 0 else 0.0
        duration_per_step = duration / step_count if step_count > 0 else 0.0

        result = BenchmarkResult(
            task_id=task_id,
            test_goal=test_goal,
            duration=duration,
            step_count=step_count,
            passed_steps=passed_steps,
            pass_rate=round(pass_rate, 4),
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            tokens_per_step=round(tokens_per_step, 1),
            cost_per_step=round(cost_per_step, 6),
            duration_per_step=round(duration_per_step, 2),
            verdict=verdict,
        )

        self._history.append(result)
        self._save_result(result)
        logger.info(
            "[Benchmark] 已记录: task=%s, duration=%.1fs, tokens=%d, cost=$%.4f, verdict=%s",
            task_id[:8], duration, total_tokens, total_cost, verdict,
        )
        return result

    def get_summary(self, last_n: int = 0) -> Dict[str, Any]:
        """获取基准统计摘要。

        计算历史记录的各项指标的统计值（均值、最值等）。

        Args:
            last_n: 只统计最近 N 条记录，0 表示全部

        Returns:
            统计摘要字典
        """
        records = self._history[-last_n:] if last_n > 0 else self._history

        if not records:
            return {
                "total_runs": 0,
                "avg_duration": 0.0,
                "avg_tokens": 0,
                "avg_cost": 0.0,
                "avg_pass_rate": 0.0,
                "avg_tokens_per_step": 0.0,
                "avg_cost_per_step": 0.0,
                "avg_duration_per_step": 0.0,
            }

        n = len(records)
        return {
            "total_runs": n,
            "avg_duration": round(sum(r.duration for r in records) / n, 2),
            "avg_tokens": round(sum(r.total_tokens for r in records) / n, 0),
            "avg_cost": round(sum(r.total_cost for r in records) / n, 6),
            "avg_pass_rate": round(sum(r.pass_rate for r in records) / n, 4),
            "avg_tokens_per_step": round(sum(r.tokens_per_step for r in records) / n, 1),
            "avg_cost_per_step": round(sum(r.cost_per_step for r in records) / n, 6),
            "avg_duration_per_step": round(sum(r.duration_per_step for r in records) / n, 2),
            "best_duration": min(r.duration for r in records),
            "worst_duration": max(r.duration for r in records),
            "best_pass_rate": max(r.pass_rate for r in records),
            "worst_pass_rate": min(r.pass_rate for r in records),
            "pass_count": sum(1 for r in records if r.verdict == "pass"),
            "fail_count": sum(1 for r in records if r.verdict == "fail"),
        }

    def compare_with_baseline(
        self,
        result: BenchmarkResult,
        baseline_last_n: int = 5,
    ) -> Dict[str, Any]:
        """将结果与历史基准对比分析。

        计算当前结果与历史均值之间的偏差百分比。

        Args:
            result: 待对比的基准结果
            baseline_last_n: 使用最近 N 条记录作为基准

        Returns:
            对比分析字典
        """
        baseline = self.get_summary(last_n=baseline_last_n)
        if baseline["total_runs"] == 0:
            return {"comparison": "no_baseline", "result": "no_history"}

        duration_delta = (
            (result.duration - baseline["avg_duration"]) / baseline["avg_duration"] * 100
            if baseline["avg_duration"] > 0 else 0
        )
        tokens_delta = (
            (result.total_tokens - baseline["avg_tokens"]) / baseline["avg_tokens"] * 100
            if baseline["avg_tokens"] > 0 else 0
        )
        cost_delta = (
            (result.total_cost - baseline["avg_cost"]) / baseline["avg_cost"] * 100
            if baseline["avg_cost"] > 0 else 0
        )

        return {
            "comparison": "compared",
            "baseline_runs": baseline["total_runs"],
            "duration_delta_pct": round(duration_delta, 1),
            "tokens_delta_pct": round(tokens_delta, 1),
            "cost_delta_pct": round(cost_delta, 1),
            "duration_assessment": "faster" if duration_delta < -10 else "slower" if duration_delta > 10 else "normal",
            "cost_assessment": "cheaper" if cost_delta < -10 else "more_expensive" if cost_delta > 10 else "normal",
        }

    def _save_result(self, result: BenchmarkResult) -> None:
        """将单条基准结果追加保存到 JSONL 文件。

        Args:
            result: 基准结果
        """
        filepath = self._data_dir / "benchmarks.jsonl"
        record = {
            "task_id": result.task_id,
            "test_goal": result.test_goal,
            "duration": result.duration,
            "step_count": result.step_count,
            "passed_steps": result.passed_steps,
            "pass_rate": result.pass_rate,
            "total_tokens": result.total_tokens,
            "total_cost": result.total_cost,
            "tokens_per_step": result.tokens_per_step,
            "cost_per_step": result.cost_per_step,
            "duration_per_step": result.duration_per_step,
            "verdict": result.verdict,
            "timestamp": result.timestamp,
        }
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _load_history(self) -> None:
        """从 JSONL 文件加载历史基准记录。"""
        filepath = self._data_dir / "benchmarks.jsonl"
        if not filepath.exists():
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    self._history.append(BenchmarkResult(
                        task_id=data["task_id"],
                        test_goal=data["test_goal"],
                        duration=data["duration"],
                        step_count=data["step_count"],
                        passed_steps=data["passed_steps"],
                        pass_rate=data["pass_rate"],
                        total_tokens=data["total_tokens"],
                        total_cost=data["total_cost"],
                        tokens_per_step=data["tokens_per_step"],
                        cost_per_step=data["cost_per_step"],
                        duration_per_step=data["duration_per_step"],
                        verdict=data["verdict"],
                        timestamp=data.get("timestamp", 0),
                    ))
            logger.info("[Benchmark] 已加载 %d 条历史记录", len(self._history))
        except Exception as e:
            logger.warning("[Benchmark] 加载历史记录失败: %s", e)
