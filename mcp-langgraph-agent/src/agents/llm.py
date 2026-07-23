"""LLM 调用封装模块。

实现三级模型路由（light/standard/precise），支持 OpenAI 和 Anthropic 两种 Provider，
提供异步调用、超时和重试机制、以及 Token 消耗追踪功能。
所有 Provider 均调用真实 API，通过 settings 读取 API Key 和 Base URL。
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from src.config.settings import settings

logger = logging.getLogger(__name__)

# ============================================================
# 类型定义
# ============================================================

# LLM 调用返回类型：(模型名称, 响应内容, Token 使用情况)
LLMResponse = Tuple[str, str, Dict[str, int]]

# 消息格式：{"role": "system"|"user"|"assistant", "content": "..."}
Message = Dict[str, str]


# ============================================================
# 模型路由配置
# ============================================================

@dataclass
class ModelConfig:
    """模型配置。

    定义单个模型的名称、Provider 和 API 参数。

    Attributes:
        model_name: 模型名称（如 "gpt-4o-mini", "claude-3-5-sonnet"）
        provider: 提供商名称（"openai" 或 "anthropic"）
        max_tokens: 最大输出 Token 数
        temperature: 温度参数，控制随机性
        timeout: 请求超时时间（秒）
        retry_count: 最大重试次数
        retry_delay: 重试间隔（秒）
    """
    model_name: str
    provider: str
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: int = 60
    retry_count: int = 3
    retry_delay: float = 1.0


# ============================================================
# 三级模型路由映射
# ============================================================

# 模型层级配置映射
# light: 用于简单任务（界面元素分析），使用 GPT-4o-mini 或 Claude Haiku
# standard: 用于标准任务（规划、执行），使用 Claude 3.5 Sonnet
# precise: 用于精确任务（验证、审查），使用 GPT-4o
_TIER_CONFIG: Dict[str, ModelConfig] = {
    'light': ModelConfig(
        model_name='gpt-4o-mini',
        provider='openai',
        max_tokens=2048,
        temperature=0.1,
        timeout=30,
        retry_count=2,
        retry_delay=0.5,
    ),
    'standard': ModelConfig(
        model_name='claude-3-5-sonnet',
        provider='anthropic',
        max_tokens=4096,
        temperature=0.1,
        timeout=60,
        retry_count=3,
        retry_delay=1.0,
    ),
    'precise': ModelConfig(
        model_name='gpt-4o',
        provider='openai',
        max_tokens=4096,
        temperature=0.05,
        timeout=60,
        retry_count=3,
        retry_delay=1.0,
    ),
}


# ============================================================
# LLM Provider 客户端（真实 API 调用）
# ============================================================

class OpenAIProvider:
    """OpenAI API 调用封装。

    使用 openai SDK 调用 Chat Completion API，
    支持自定义 base_url 以兼容第三方 API（LM Studio、Ollama 等）。
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """初始化 OpenAI Provider。

        Args:
            api_key: OpenAI API 密钥，如果为 None 则从 settings 读取
            base_url: API 基础地址，用于兼容第三方 API
        """
        self.api_key: str = api_key or settings.LLM_API_KEY
        self.base_url: str = base_url or (settings.LLM_BASE_URL or 'https://api.openai.com/v1')
        self._client = None
        self._async_client = None

    def _get_client(self) -> Any:
        """获取或创建 OpenAI 同步客户端实例。"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def _get_async_client(self) -> Any:
        """获取或创建 OpenAI 异步客户端实例。"""
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._async_client

    def call(self, model: str, messages: List[Message], **kwargs: Any) -> Dict[str, Any]:
        """同步调用 OpenAI Chat Completion API。

        Args:
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他 API 参数（max_tokens, temperature 等）

        Returns:
            API 响应字典，包含 choices 和 usage 字段
        """
        client = self._get_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.1),
        )
        return {
            'choices': [
                {
                    'message': {
                        'role': response.choices[0].message.role,
                        'content': response.choices[0].message.content or '',
                    },
                    'finish_reason': response.choices[0].finish_reason,
                }
            ],
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                'completion_tokens': response.usage.completion_tokens if response.usage else 0,
                'total_tokens': response.usage.total_tokens if response.usage else 0,
            },
            'model': response.model,
        }

    async def call_async(self, model: str, messages: List[Message], **kwargs: Any) -> Dict[str, Any]:
        """异步调用 OpenAI Chat Completion API。

        Args:
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他 API 参数

        Returns:
            API 响应字典
        """
        client = self._get_async_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.1),
        )
        return {
            'choices': [
                {
                    'message': {
                        'role': response.choices[0].message.role,
                        'content': response.choices[0].message.content or '',
                    },
                    'finish_reason': response.choices[0].finish_reason,
                }
            ],
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                'completion_tokens': response.usage.completion_tokens if response.usage else 0,
                'total_tokens': response.usage.total_tokens if response.usage else 0,
            },
            'model': response.model,
        }


class AnthropicProvider:
    """Anthropic API 调用封装。

    使用 anthropic SDK 调用 Messages API。
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """初始化 Anthropic Provider。

        Args:
            api_key: Anthropic API 密钥，如果为 None 则从 settings 读取
            base_url: API 基础地址
        """
        self.api_key: str = api_key or settings.LLM_API_KEY
        self.base_url: str = base_url or (settings.LLM_BASE_URL or None)
        self._client = None
        self._async_client = None

    def _get_client(self) -> Any:
        """获取或创建 Anthropic 同步客户端实例。"""
        if self._client is None:
            from anthropic import Anthropic
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = Anthropic(**kwargs)
        return self._client

    def _get_async_client(self) -> Any:
        """获取或创建 Anthropic 异步客户端实例。"""
        if self._async_client is None:
            from anthropic import AsyncAnthropic
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._async_client = AsyncAnthropic(**kwargs)
        return self._async_client

    @staticmethod
    def _split_system_message(messages: List[Message]) -> Tuple[str, List[Message]]:
        """将 system 消息从消息列表中分离。

        Anthropic API 要求 system 参数单独传递。

        Args:
            messages: 原始消息列表

        Returns:
            (system_prompt, non_system_messages) 元组
        """
        system_prompt = ''
        non_system = []
        for m in messages:
            if m.get('role') == 'system':
                system_prompt = m.get('content', '')
            else:
                non_system.append(m)
        return system_prompt, non_system

    def call(self, model: str, messages: List[Message], **kwargs: Any) -> Dict[str, Any]:
        """同步调用 Anthropic Messages API。

        Args:
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他 API 参数

        Returns:
            API 响应字典
        """
        client = self._get_client()
        system_prompt, non_system = self._split_system_message(messages)
        response = client.messages.create(
            model=model,
            system=system_prompt,
            messages=non_system,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.1),
        )
        return {
            'content': [{'type': b.type, 'text': b.text} for b in response.content],
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
            },
            'model': response.model,
        }

    async def call_async(self, model: str, messages: List[Message], **kwargs: Any) -> Dict[str, Any]:
        """异步调用 Anthropic Messages API。

        Args:
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他 API 参数

        Returns:
            API 响应字典
        """
        client = self._get_async_client()
        system_prompt, non_system = self._split_system_message(messages)
        response = await client.messages.create(
            model=model,
            system=system_prompt,
            messages=non_system,
            max_tokens=kwargs.get('max_tokens', 4096),
            temperature=kwargs.get('temperature', 0.1),
        )
        return {
            'content': [{'type': b.type, 'text': b.text} for b in response.content],
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
            },
            'model': response.model,
        }


# ============================================================
# Provider 注册表
# ============================================================

# Provider 工厂映射
_PROVIDER_REGISTRY: Dict[str, Callable[[], Any]] = {
    'openai': lambda: OpenAIProvider(),
    'anthropic': lambda: AnthropicProvider(),
}


def register_provider(name: str, factory: Callable[[], Any]) -> None:
    """注册自定义 Provider。

    允许扩展系统以支持新的 LLM Provider。

    Args:
        name: Provider 名称
        factory: Provider 实例工厂函数

    Example:
        >>> register_provider('ollama', lambda: OllamaProvider())
    """
    _PROVIDER_REGISTRY[name] = factory


# ============================================================
# ModelRouter 类
# ============================================================

class ModelRouter:
    """三级模型路由器。

    根据任务复杂度选择不同的模型层级：
    - light: 用于简单任务（界面元素分析），使用 GPT-4o-mini 或 Claude Haiku
    - standard: 用于标准任务（规划、执行），使用 Claude 3.5 Sonnet
    - precise: 用于精确任务（验证、审查），使用 GPT-4o

    支持 OpenAI 和 Anthropic 两种 Provider，提供异步调用、
    超时和重试机制、以及 Token 消耗追踪。

    当 settings.LLM_MODEL 配置了自定义模型时，所有层级统一使用该模型。
    """

    def __init__(self, provider_overrides: Dict[str, str] | None = None) -> None:
        """初始化模型路由器。

        如果 settings 中配置了 LLM_MODEL，则所有层级统一使用该模型，
        便于使用本地模型（如 LM Studio、Ollama）。

        Args:
            provider_overrides: 可选的 Provider 覆盖配置。
                例如 {'light': 'anthropic'} 将 light 层级改为使用 Anthropic。
        """
        # 初始化 Provider 实例缓存
        self._providers: Dict[str, Any] = {}

        # 应用 Provider 覆盖配置
        if provider_overrides:
            for tier, provider_name in provider_overrides.items():
                if tier in _TIER_CONFIG:
                    _TIER_CONFIG[tier].provider = provider_name

        # 如果 settings 中配置了自定义模型，统一所有层级使用该模型
        configured_model = settings.LLM_MODEL
        configured_provider = settings.LLM_PROVIDER
        if configured_model and configured_model not in ('gpt-4o', 'gpt-4o-mini', 'claude-3-5-sonnet'):
            for tier in _TIER_CONFIG:
                _TIER_CONFIG[tier].model_name = configured_model
                _TIER_CONFIG[tier].provider = configured_provider
            logger.info(
                f"使用自定义模型配置: model={configured_model}, provider={configured_provider}"
            )

    def _get_provider(self, provider_name: str) -> Any:
        """获取或创建 Provider 实例。

        Args:
            provider_name: Provider 名称（"openai" 或 "anthropic"）

        Returns:
            Provider 实例

        Raises:
            ValueError: 不支持的 Provider 类型
        """
        if provider_name not in self._providers:
            factory = _PROVIDER_REGISTRY.get(provider_name)
            if factory is None:
                raise ValueError(f"不支持的 Provider: {provider_name}，支持的 Provider: {list(_PROVIDER_REGISTRY.keys())}")
            self._providers[provider_name] = factory()
        return self._providers[provider_name]

    def call(
        self,
        messages: List[Message],
        tier: str = 'standard',
    ) -> LLMResponse:
        """同步调用 LLM。

        根据模型层级选择对应的模型配置，调用相应的 Provider，
        并在失败时自动重试。

        Args:
            messages: 对话消息列表
            tier: 模型层级（light/standard/precise）

        Returns:
            (模型名称, 响应内容, Token 使用情况) 的元组

        Raises:
            ValueError: 不支持的模型层级
            RuntimeError: 所有重试均失败
        """
        config = _TIER_CONFIG.get(tier)
        if config is None:
            raise ValueError(f"不支持的模型层级: {tier}，支持的层级: {list(_TIER_CONFIG.keys())}")

        provider = self._get_provider(config.provider)

        last_error: Exception | None = None
        for attempt in range(config.retry_count + 1):
            try:
                response = provider.call(
                    model=config.model_name,
                    messages=messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                )
                return self._parse_response(response, config.provider, config.model_name)
            except Exception as e:
                last_error = e
                logger.warning(f"[ModelRouter] LLM 调用失败 (attempt {attempt + 1}/{config.retry_count + 1}): {e}")
                if attempt < config.retry_count:
                    time.sleep(config.retry_delay * (attempt + 1))

        raise RuntimeError(f"LLM 调用失败，已重试 {config.retry_count} 次: {last_error}")

    async def call_async(
        self,
        messages: List[Message],
        tier: str = 'standard',
    ) -> LLMResponse:
        """异步调用 LLM。

        异步版本的 call，适用于需要并发调用 LLM 的场景。

        Args:
            messages: 对话消息列表
            tier: 模型层级（light/standard/precise）

        Returns:
            (模型名称, 响应内容, Token 使用情况) 的元组

        Raises:
            ValueError: 不支持的模型层级
            RuntimeError: 所有重试均失败
        """
        config = _TIER_CONFIG.get(tier)
        if config is None:
            raise ValueError(f"不支持的模型层级: {tier}，支持的层级: {list(_TIER_CONFIG.keys())}")

        provider = self._get_provider(config.provider)

        last_error: Exception | None = None
        for attempt in range(config.retry_count + 1):
            try:
                response = await provider.call_async(
                    model=config.model_name,
                    messages=messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                )
                return self._parse_response(response, config.provider, config.model_name)
            except Exception as e:
                last_error = e
                logger.warning(f"[ModelRouter] 异步 LLM 调用失败 (attempt {attempt + 1}/{config.retry_count + 1}): {e}")
                if attempt < config.retry_count:
                    await asyncio.sleep(config.retry_delay * (attempt + 1))

        raise RuntimeError(f"LLM 异步调用失败，已重试 {config.retry_count} 次: {last_error}")

    def _parse_response(
        self,
        response: Dict[str, Any],
        provider: str,
        model_name: str,
    ) -> LLMResponse:
        """解析 Provider 的响应为统一格式。

        不同 Provider 的响应格式不同，此方法将其统一解析。

        Args:
            response: Provider 返回的原始响应字典
            provider: Provider 名称
            model_name: 模型名称

        Returns:
            (模型名称, 响应内容, Token 使用情况) 的元组
        """
        content: str = ''
        usage: Dict[str, int] = {}

        if provider == 'openai':
            choices = response.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '')
            usage = response.get('usage', {})

        elif provider == 'anthropic':
            content_blocks = response.get('content', [])
            if content_blocks:
                content = content_blocks[0].get('text', '')
            raw_usage = response.get('usage', {})
            usage = {
                'prompt_tokens': raw_usage.get('input_tokens', 0),
                'completion_tokens': raw_usage.get('output_tokens', 0),
                'total_tokens': raw_usage.get('input_tokens', 0) + raw_usage.get('output_tokens', 0),
            }

        if not content:
            content = ''

        return model_name, content, usage

    def get_available_tiers(self) -> List[str]:
        """获取所有可用的模型层级列表。"""
        return list(_TIER_CONFIG.keys())

    def get_tier_config(self, tier: str) -> ModelConfig | None:
        """获取指定层级的模型配置。"""
        return _TIER_CONFIG.get(tier)
