"""Skills 知识库模块。

提供 Skills 管理器，负责加载、匹配和注入 Skills 知识到 Agent 提示词中。
Skills 是 Markdown 格式的结构化知识文档，指导 LLM 在特定测试场景下的行为。
"""

from src.skills.manager import SkillManager

__all__ = ["SkillManager"]
