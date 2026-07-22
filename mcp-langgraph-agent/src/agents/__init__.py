"""Agent 模块导出。

导出所有 Agent 类和模型路由器，供外部直接引用。
"""

from src.agents.base import BaseAgent
from src.agents.explorer import ExplorerAgent
from src.agents.planner import PlannerAgent
from src.agents.executor import ExecutorAgent
from src.agents.verifier import VerifierAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.llm import ModelRouter, ModelConfig, register_provider
from src.agents.prompts import (
    SYSTEM_PROMPT,
    EXPLORER_PROMPT,
    PLANNER_PROMPT,
    EXECUTOR_PROMPT,
    VERIFIER_PROMPT,
    REVIEWER_PROMPT,
)

__all__ = [
    'BaseAgent',
    'ExplorerAgent',
    'PlannerAgent',
    'ExecutorAgent',
    'VerifierAgent',
    'ReviewerAgent',
    'ModelRouter',
    'ModelConfig',
    'register_provider',
    'SYSTEM_PROMPT',
    'EXPLORER_PROMPT',
    'PLANNER_PROMPT',
    'EXECUTOR_PROMPT',
    'VERIFIER_PROMPT',
    'REVIEWER_PROMPT',
]
