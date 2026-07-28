"""告警通知模块。

支持将测试完成、成本超限等事件推送到飞书 Webhook 或 Slack Webhook，
实现实时通知集成。
"""

from __future__ import annotations

import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# 通知渠道枚举
# ============================================================


class NotificationChannel(Enum):
    """通知渠道枚举。"""

    FEISHU = "feishu"
    SLACK = "slack"


# ============================================================
# 通知事件类型
# ============================================================


class NotificationEvent(Enum):
    """通知事件类型。"""

    TEST_COMPLETED = "test_completed"
    TEST_FAILED = "test_failed"
    COST_ALERT = "cost_alert"
    DEVICE_OFFLINE = "device_offline"


# ============================================================
# 通知器类
# ============================================================


class Notifier:
    """告警通知器。

    支持飞书和 Slack Webhook 两种通知渠道，
    将测试事件以结构化消息推送到指定渠道。

    用法:
        notifier = Notifier(
            feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            slack_webhook_url="https://hooks.slack.com/services/xxx",
        )
        notifier.notify_test_completed(task_id="abc", verdict="pass", duration=45.2)
        notifier.notify_cost_alert(total_cost=6.5, threshold=5.0)
    """

    def __init__(
        self,
        feishu_webhook_url: str = "",
        slack_webhook_url: str = "",
    ) -> None:
        """初始化告警通知器。

        Args:
            feishu_webhook_url: 飞书 Webhook URL，为空时禁用飞书通知
            slack_webhook_url: Slack Webhook URL，为空时禁用 Slack 通知
        """
        self._feishu_webhook_url = feishu_webhook_url
        self._slack_webhook_url = slack_webhook_url

    @property
    def enabled(self) -> bool:
        """检查是否有可用的通知渠道。"""
        return bool(self._feishu_webhook_url or self._slack_webhook_url)

    def notify_test_completed(
        self,
        task_id: str,
        test_goal: str,
        verdict: str,
        duration: float,
        pass_rate: str = "",
        total_tokens: int = 0,
        total_cost: float = 0.0,
    ) -> dict[str, bool]:
        """发送测试完成通知。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            verdict: 最终结论（pass/fail/unknown）
            duration: 测试耗时（秒）
            pass_rate: 步骤通过率
            total_tokens: Token 消耗总量
            total_cost: API 成本（美元）

        Returns:
            各渠道发送结果字典 {"feishu": bool, "slack": bool}
        """
        verdict_emoji = {"pass": "✅", "fail": "❌", "unknown": "❓"}.get(verdict, "❓")
        verdict_text = {"pass": "通过", "fail": "失败", "unknown": "未知"}.get(verdict, "未知")

        title = f"{verdict_emoji} AI 测试完成 - {verdict_text}"
        content_lines = [
            f"**任务 ID**: {task_id}",
            f"**测试目标**: {test_goal}",
            f"**最终结论**: {verdict_text}",
            f"**总耗时**: {duration:.1f}s",
        ]
        if pass_rate:
            content_lines.append(f"**步骤通过率**: {pass_rate}")
        if total_tokens:
            content_lines.append(f"**Token 消耗**: {total_tokens:,}")
        if total_cost > 0:
            content_lines.append(f"**API 成本**: ${total_cost:.4f}")

        return self._send_all(title, "\n".join(content_lines), NotificationEvent.TEST_COMPLETED)

    def notify_test_failed(
        self,
        task_id: str,
        test_goal: str,
        error: str,
        duration: float = 0.0,
    ) -> dict[str, bool]:
        """发送测试失败通知。

        Args:
            task_id: 任务 ID
            test_goal: 测试目标描述
            error: 错误信息
            duration: 已执行耗时

        Returns:
            各渠道发送结果字典
        """
        title = "❌ AI 测试失败"
        content_lines = [
            f"**任务 ID**: {task_id}",
            f"**测试目标**: {test_goal}",
            f"**错误信息**: {error}",
        ]
        if duration > 0:
            content_lines.append(f"**已执行耗时**: {duration:.1f}s")

        return self._send_all(title, "\n".join(content_lines), NotificationEvent.TEST_FAILED)

    def notify_cost_alert(
        self,
        total_cost: float,
        threshold: float,
        total_records: int = 0,
    ) -> dict[str, bool]:
        """发送成本告警通知。

        Args:
            total_cost: 累计成本（美元）
            threshold: 告警阈值
            total_records: 总调用次数

        Returns:
            各渠道发送结果字典
        """
        title = "⚠️ 成本告警"
        content_lines = [
            f"**累计成本**: ${total_cost:.6f}",
            f"**告警阈值**: ${threshold:.2f}",
            f"**超出比例**: {((total_cost - threshold) / threshold * 100):.1f}%",
        ]
        if total_records:
            content_lines.append(f"**总调用次数**: {total_records}")

        return self._send_all(title, "\n".join(content_lines), NotificationEvent.COST_ALERT)

    def _send_all(
        self,
        title: str,
        content: str,
        event: NotificationEvent,
    ) -> dict[str, bool]:
        """通过所有已配置的渠道发送通知。

        Args:
            title: 通知标题
            content: 通知内容
            event: 事件类型

        Returns:
            各渠道发送结果字典
        """
        results: dict[str, bool] = {}

        if self._feishu_webhook_url:
            results["feishu"] = self._send_feishu(title, content, event)

        if self._slack_webhook_url:
            results["slack"] = self._send_slack(title, content, event)

        if not results:
            logger.info("[Notifier] 无可用通知渠道，跳过发送: %s", title)

        return results

    def _send_feishu(
        self,
        title: str,
        content: str,
        event: NotificationEvent,
    ) -> bool:
        """发送飞书 Webhook 通知。

        使用飞书自定义机器人 Webhook 发送富文本消息。

        Args:
            title: 消息标题
            content: 消息内容
            event: 事件类型

        Returns:
            是否发送成功
        """
        try:
            import urllib.request

            # 飞书富文本消息格式
            payload = json.dumps({
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": self._feishu_color_for_event(event),
                    },
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }, ensure_ascii=False).encode("utf-8")

            req = urllib.request.Request(
                self._feishu_webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("code", -1) == 0:
                    logger.info("[Notifier] 飞书通知发送成功: %s", title)
                    return True
                else:
                    logger.warning("[Notifier] 飞书通知发送失败: %s", result.get("msg", ""))
                    return False

        except Exception as e:  # noqa: BLE001
            logger.warning("[Notifier] 飞书通知发送异常: %s", e)
            return False

    def _send_slack(
        self,
        title: str,
        content: str,
        event: NotificationEvent,
    ) -> bool:
        """发送 Slack Webhook 通知。

        Args:
            title: 消息标题
            content: 消息内容
            event: 事件类型

        Returns:
            是否发送成功
        """
        try:
            import urllib.request

            payload = json.dumps({
                "text": title,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": title},
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": content},
                    },
                ],
            }, ensure_ascii=False).encode("utf-8")

            req = urllib.request.Request(
                self._slack_webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("[Notifier] Slack 通知发送成功: %s", title)
                    return True
                else:
                    logger.warning("[Notifier] Slack 通知发送失败: HTTP %d", resp.status)
                    return False

        except Exception as e:  # noqa: BLE001
            logger.warning("[Notifier] Slack 通知发送异常: %s", e)
            return False

    def _feishu_color_for_event(self, event: NotificationEvent) -> str:
        """根据事件类型返回飞书消息卡片颜色模板。

        Args:
            event: 事件类型

        Returns:
            飞书卡片颜色模板名称
        """
        color_map = {
            NotificationEvent.TEST_COMPLETED: "green",
            NotificationEvent.TEST_FAILED: "red",
            NotificationEvent.COST_ALERT: "orange",
            NotificationEvent.DEVICE_OFFLINE: "red",
        }
        return color_map.get(event, "blue")
