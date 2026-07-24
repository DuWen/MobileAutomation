"""测试报告生成器模块。

支持将测试执行结果导出为 HTML 和 Markdown 格式的报告，
包含测试概览、步骤详情、Token 消耗统计和质量指标。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__('logging').getLogger(__name__)


# ============================================================
# 报告生成器类
# ============================================================


class ReportGenerator:
    """测试报告生成器。

    将 LangGraph 工作流的执行结果转换为可读的 HTML 或 Markdown 报告，
    包含测试概览、步骤执行详情、Token 消耗统计和最终审查结论。

    用法:
        generator = ReportGenerator(output_dir="reports")
        report_path = generator.generate(
            task_id="abc-123",
            test_goal="测试登录功能",
            executed_steps=[...],
            verifier_output={...},
            reviewer_output={...},
            token_summary={...},
            duration=45.2,
            format="html",
        )
    """

    def __init__(self, output_dir: str = "reports") -> None:
        """初始化报告生成器。

        Args:
            output_dir: 报告输出目录路径
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        task_id: str,
        test_goal: str,
        executed_steps: List[Dict[str, Any]],
        verifier_output: Dict[str, Any],
        reviewer_output: Dict[str, Any],
        token_summary: Dict[str, Any],
        duration: float,
        device_name: str = "",
        error: Optional[str] = None,
        format: str = "html",
    ) -> str:
        """生成测试报告。

        根据指定格式生成测试报告并保存到输出目录。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            executed_steps: 已执行步骤列表
            verifier_output: 验证节点输出结果（含 passed、failure_reason 等）
            reviewer_output: 审查输出结果
            token_summary: Token 消耗统计
            duration: 测试总耗时（秒）
            device_name: 设备名称
            error: 错误信息（如有）
            format: 报告格式，"html" 或 "markdown"

        Returns:
            生成的报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{task_id[:8]}_{timestamp}"

        if format == "html":
            content = self._generate_html(
                task_id, test_goal, executed_steps,
                verifier_output, reviewer_output,
                token_summary, duration, device_name, error,
            )
            filepath = self._output_dir / f"{filename}.html"
        elif format == "markdown":
            content = self._generate_markdown(
                task_id, test_goal, executed_steps,
                verifier_output, reviewer_output,
                token_summary, duration, device_name, error,
            )
            filepath = self._output_dir / f"{filename}.md"
        else:
            raise ValueError(f"不支持的报告格式: {format}，仅支持 html 和 markdown")

        filepath.write_text(content, encoding="utf-8")
        logger.info("测试报告已生成: %s", filepath)
        return str(filepath)

    def _generate_html(
        self,
        task_id: str,
        test_goal: str,
        executed_steps: List[Dict[str, Any]],
        verifier_output: Dict[str, Any],
        reviewer_output: Dict[str, Any],
        token_summary: Dict[str, Any],
        duration: float,
        device_name: str,
        error: Optional[str],
    ) -> str:
        """生成 HTML 格式报告。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            executed_steps: 已执行步骤列表
            verifier_output: 验证节点输出（含 passed、failure_reason 等）
            reviewer_output: 审查输出结果
            token_summary: Token 消耗统计
            duration: 测试总耗时
            device_name: 设备名称
            error: 错误信息

        Returns:
            HTML 报告字符串
        """
        passed_steps = sum(1 for s in executed_steps if s.get("passed", False))
        total_steps = len(executed_steps)
        pass_rate = f"{(passed_steps / total_steps * 100):.1f}%" if total_steps > 0 else "N/A"

        final_verdict = reviewer_output.get("final_verdict", "unknown")
        verdict_color = {"pass": "#28a745", "fail": "#dc3545", "unknown": "#6c757d"}.get(final_verdict, "#6c757d")
        verdict_text = {"pass": "通过", "fail": "失败", "unknown": "未知"}.get(final_verdict, "未知")

        total_tokens = token_summary.get("total_tokens", 0)
        total_cost = token_summary.get("total_cost", 0.0)
        total_records = token_summary.get("total_records", 0)

        # 步骤表格行
        steps_rows = ""
        for i, step in enumerate(executed_steps, 1):
            status_icon = "✅" if step.get("passed") else "❌"
            steps_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{step.get('action', '')}</td>
                <td>{step.get('result', '')}</td>
                <td>{status_icon}</td>
            </tr>"""

        # 验证详情
        verify_rows = ""
        if verifier_output:
            status_icon = "✅" if verifier_output.get("passed") else "❌"
            verify_rows = f"""
            <tr>
                <td>验证结果</td>
                <td>{status_icon}</td>
            </tr>"""
            failure_reason = verifier_output.get("failure_reason", "")
            if failure_reason:
                verify_rows += f"""
            <tr>
                <td>失败原因</td>
                <td>{failure_reason}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {task_id[:8]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
        .header p {{ margin: 5px 0; opacity: 0.9; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card h2 {{ margin: 0 0 15px 0; color: #333; border-bottom: 2px solid #eee; padding-bottom: 8px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }}
        .metric {{ background: #f8f9fa; border-radius: 6px; padding: 16px; text-align: center; }}
        .metric .value {{ font-size: 28px; font-weight: bold; color: #333; }}
        .metric .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
        .verdict {{ display: inline-block; padding: 6px 16px; border-radius: 20px; color: white; font-weight: bold; font-size: 14px; background: {verdict_color}; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
        tr:hover {{ background: #f8f9fa; }}
        .error {{ background: #fff5f5; border-left: 4px solid #dc3545; padding: 12px 16px; border-radius: 4px; color: #721c24; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AI 自动化测试报告</h1>
            <p>任务 ID: {task_id}</p>
            <p>测试目标: {test_goal}</p>
            <p>设备: {device_name or 'N/A'}</p>
            <p>执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="card">
            <h2>测试概览</h2>
            <div class="metrics">
                <div class="metric">
                    <div class="value">{verdict_text}</div>
                    <div class="label">最终结论</div>
                </div>
                <div class="metric">
                    <div class="value">{pass_rate}</div>
                    <div class="label">步骤通过率</div>
                </div>
                <div class="metric">
                    <div class="value">{duration:.1f}s</div>
                    <div class="label">总耗时</div>
                </div>
                <div class="metric">
                    <div class="value">{total_tokens:,}</div>
                    <div class="label">Token 消耗</div>
                </div>
                <div class="metric">
                    <div class="value">${total_cost:.4f}</div>
                    <div class="label">API 成本</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>执行步骤 ({passed_steps}/{total_steps})</h2>
            <table>
                <thead>
                    <tr><th>#</th><th>操作</th><th>结果</th><th>状态</th></tr>
                </thead>
                <tbody>
                    {steps_rows}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>验证详情</h2>
            <table>
                <thead>
                    <tr><th>检查项</th><th>结果</th></tr>
                </thead>
                <tbody>
                    {verify_rows}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Token 消耗明细</h2>
            <p>总调用次数: {total_records} 次 | 总 Token: {total_tokens:,} | 总成本: ${total_cost:.6f}</p>
            <p>审查结论: {reviewer_output.get('feedback', 'N/A')}</p>
        </div>

        {"<div class='error'>错误信息: " + error + "</div>" if error else ""}

        <div class="footer">
            <p>由 mcp-langgraph-agent 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>"""
        return html

    def _generate_markdown(
        self,
        task_id: str,
        test_goal: str,
        executed_steps: List[Dict[str, Any]],
        verifier_output: Dict[str, Any],
        reviewer_output: Dict[str, Any],
        token_summary: Dict[str, Any],
        duration: float,
        device_name: str,
        error: Optional[str],
    ) -> str:
        """生成 Markdown 格式报告。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            executed_steps: 已执行步骤列表
            verifier_output: 验证节点输出（含 passed、failure_reason 等）
            reviewer_output: 审查输出结果
            token_summary: Token 消耗统计
            duration: 测试总耗时
            device_name: 设备名称
            error: 错误信息

        Returns:
            Markdown 报告字符串
        """
        passed_steps = sum(1 for s in executed_steps if s.get("passed", False))
        total_steps = len(executed_steps)
        pass_rate = f"{(passed_steps / total_steps * 100):.1f}%" if total_steps > 0 else "N/A"

        final_verdict = reviewer_output.get("final_verdict", "unknown")
        total_tokens = token_summary.get("total_tokens", 0)
        total_cost = token_summary.get("total_cost", 0.0)

        lines = [
            "# AI 自动化测试报告",
            "",
            "| 项目 | 值 |",
            "|------|-----|",
            f"| 任务 ID | `{task_id}` |",
            f"| 测试目标 | {test_goal} |",
            f"| 设备 | {device_name or 'N/A'} |",
            f"| 最终结论 | **{final_verdict}** |",
            f"| 步骤通过率 | {pass_rate} |",
            f"| 总耗时 | {duration:.1f}s |",
            f"| Token 消耗 | {total_tokens:,} |",
            f"| API 成本 | ${total_cost:.4f} |",
            "",
            "## 执行步骤",
            "",
            "| # | 操作 | 结果 | 状态 |",
            "|---|------|------|------|",
        ]

        for i, step in enumerate(executed_steps, 1):
            status = "✅" if step.get("passed") else "❌"
            lines.append(f"| {i} | {step.get('action', '')} | {step.get('result', '')} | {status} |")

        lines.extend([
            "",
            "## 验证详情",
            "",
            "| 检查项 | 结果 |",
            "|--------|------|",
        ])

        if verifier_output:
            status = "✅" if verifier_output.get("passed") else "❌"
            lines.append(f"| 验证结果 | {status} |")
            failure_reason = verifier_output.get("failure_reason", "")
            if failure_reason:
                lines.append(f"| 失败原因 | {failure_reason} |")

        if reviewer_output.get("feedback"):
            lines.extend(["", "## 审查反馈", "", reviewer_output["feedback"]])

        if error:
            lines.extend(["", "## 错误信息", "", f"```\n{error}\n```"])

        lines.extend([
            "",
            "---",
            f"*由 mcp-langgraph-agent 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])

        return "\n".join(lines)
