"""Agent 模块导出。

导出所有 Agent 类和模型路由器，供外部直接引用。
"""

from src.agents.base import BaseAgent
from src.agents.executor import ExecutorAgent
from src.agents.explorer import ExplorerAgent
from src.agents.llm import ModelConfig, ModelRouter, register_provider
from src.agents.planner import PlannerAgent
from src.agents.prompts import (
    EXECUTOR_PROMPT,
    EXPLORER_PROMPT,
    PLANNER_PROMPT,
    REVIEWER_PROMPT,
    SYSTEM_PROMPT,
    VERIFIER_PROMPT,
)
from src.agents.reviewer import ReviewerAgent
from src.agents.verifier import VerifierAgent

__all__ = [
    'EXECUTOR_PROMPT',
    'EXPLORER_PROMPT',
    'PLANNER_PROMPT',
    'REVIEWER_PROMPT',
    'SYSTEM_PROMPT',
    'VERIFIER_PROMPT',
    'BaseAgent',
    'ExecutorAgent',
    'ExplorerAgent',
    'ModelConfig',
    'ModelRouter',
    'PlannerAgent',
    'ReviewerAgent',
    'VerifierAgent',
    'register_provider',
]
