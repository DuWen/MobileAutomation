"""Agent 基类模块。

提供所有 Agent 的基础抽象类，封装 LLM 调用的通用逻辑，
包括模型路由、Token 追踪和系统提示词注入等功能。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.agents.llm import ModelRouter
from src.agents.prompts import SYSTEM_PROMPT
from src.utils.token_tracker import TokenTracker


class BaseAgent(ABC):
    """Agent 基类，提供 LLM 调用的基础封装。

    所有具体的 Agent 节点（探索、规划、执行、验证、审查）都应继承此类。
    封装了 LLM 调用、Token 追踪、系统提示词注入等通用功能。

    Attributes:
        name: Agent 名称
        model_router: 模型路由实例，用于三级模型路由
        token_tracker: Token 消耗追踪器
        system_prompt: 系统级提示词，定义 Agent 角色和行为规范
    """

    # 模型层级映射：各 Agent 节点使用不同层级的模型
    # light: 简单任务
    # standard: 标准任务
    # precise: 精确任务
    DEFAULT_MODEL_TIER: str = 'standard'

    def __init__(
        self,
        name: str,
        model_router: ModelRouter | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """初始化 BaseAgent。

        Args:
            name: Agent 名称，用于标识和日志
            model_router: 模型路由实例，如果为 None 则自动创建
            token_tracker: Token 消耗追踪器，如果为 None 则自动创建
        """
        self.name: str = name
        self.model_router: ModelRouter = model_router or ModelRouter()
        self.token_tracker: TokenTracker = token_tracker or TokenTracker()
        self.system_prompt: str = SYSTEM_PROMPT

    def call_llm(
        self,
        messages: List[Dict[str, str]],
        model_tier: str | None = None,
        operation: str = '',
    ) -> str:
        """调用 LLM 获取回复。

        封装了模型路由、调用执行、Token 追踪的完整流程。
        自动注入系统提示词到消息开头。

        Args:
            messages: 对话消息列表，每项包含 role 和 content 字段
            model_tier: 模型层级（light/standard/precise），
                如果为 None 则使用 DEFAULT_MODEL_TIER
            operation: 操作描述，用于 Token 追踪记录

        Returns:
            LLM 返回的文本回复内容

        Raises:
            ValueError: 消息列表为空或格式错误
            RuntimeError: LLM 调用失败（网络错误、API 错误等）
        """
        if not messages:
            raise ValueError("消息列表不能为空")

        # 确定使用的模型层级
        tier = model_tier or self.DEFAULT_MODEL_TIER

        # 注入系统提示词：如果消息列表的第一个不是 system 角色，则插入
        if not messages or messages[0].get('role') != 'system':
            messages_with_system = [
                {'role': 'system', 'content': self.system_prompt},
                *messages,
            ]
        else:
            messages_with_system = list(messages)

        # 通过模型路由调用 LLM
        model_name, response_content, usage = self.model_router.call(
            messages=messages_with_system,
            tier=tier,
        )

        # 追踪 Token 消耗
        if usage:
            self.token_tracker.add_record(
                model=model_name,
                model_tier=tier,
                prompt_tokens=usage.get('prompt_tokens', 0),
                completion_tokens=usage.get('completion_tokens', 0),
                operation=operation or self.name,
            )

        return response_content

    async def call_llm_async(
        self,
        messages: List[Dict[str, str]],
        model_tier: str | None = None,
        operation: str = '',
    ) -> str:
        """异步调用 LLM 获取回复。

        异步版本的 call_llm，适用于需要并发调用 LLM 的场景。

        Args:
            messages: 对话消息列表，每项包含 role 和 content 字段
            model_tier: 模型层级（light/standard/precise），
                如果为 None 则使用 DEFAULT_MODEL_TIER
            operation: 操作描述，用于 Token 追踪记录

        Returns:
            LLM 返回的文本回复内容

        Raises:
            ValueError: 消息列表为空或格式错误
            RuntimeError: LLM 调用失败
        """
        if not messages:
            raise ValueError("消息列表不能为空")

        # 确定使用的模型层级
        tier = model_tier or self.DEFAULT_MODEL_TIER

        # 注入系统提示词
        if not messages or messages[0].get('role') != 'system':
            messages_with_system = [
                {'role': 'system', 'content': self.system_prompt},
                *messages,
            ]
        else:
            messages_with_system = list(messages)

        # 异步调用模型路由
        model_name, response_content, usage = await self.model_router.call_async(
            messages=messages_with_system,
            tier=tier,
        )

        # 追踪 Token 消耗
        if usage:
            self.token_tracker.add_record(
                model=model_name,
                model_tier=tier,
                prompt_tokens=usage.get('prompt_tokens', 0),
                completion_tokens=usage.get('completion_tokens', 0),
                operation=operation or self.name,
            )

        return response_content

    def set_system_prompt(self, prompt: str) -> None:
        """设置自定义系统提示词。

        允许在运行时替换默认的系统提示词模板。

        Args:
            prompt: 新的系统提示词内容
        """
        self.system_prompt = prompt

    def get_token_summary(self) -> Dict[str, Any]:
        """获取当前会话的 Token 消耗统计摘要。

        Returns:
            Token 消耗统计摘要字典
        """
        return self.token_tracker.get_summary()

    @abstractmethod
    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """运行 Agent 的核心逻辑（抽象方法）。

        子类必须实现此方法，定义具体的 Agent 处理逻辑。

        Args:
            **kwargs: 运行时参数，具体取决于子类实现

        Returns:
            包含处理结果的字典
        """
        ...