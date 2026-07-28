"""Skills 管理器模块。

负责从磁盘加载 Markdown 格式的 Skills 知识文档，
根据测试目标自动匹配最相关的 Skill，并将 Skill 内容
注入到 Agent 的系统提示词中，指导 LLM 的测试行为。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构定义
# ============================================================


@dataclass
class Skill:
    """技能知识文档。

    每个 Skill 对应一个 Markdown 文件，包含特定测试场景的
    指导知识，包括适用场景、测试要点、常见问题和断言策略。

    Attributes:
        name: 技能名称，基于文件名生成（如 "login"）
        file_path: Markdown 文件的路径
        content: 文件的完整内容
        keywords: 从内容中提取的关键词列表，用于匹配
        tags: 从文件头部元数据提取的标签
    """

    name: str
    file_path: Path
    content: str
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ============================================================
# SkillManager 类
# ============================================================


class SkillManager:
    """Skills 知识库管理器。

    从指定目录加载所有 Markdown 格式的 Skill 文件，
    根据测试目标自动匹配最相关的 Skills，并提供
    格式化的 Skill 内容注入到 Agent 提示词中。

    用法:
        manager = SkillManager(skills_dir="src/skills")
        matched = manager.match_skills("测试用户登录流程")
        prompt = manager.format_skills_for_prompt(matched)
    """

    def __init__(self, skills_dir: str | None = None) -> None:
        """初始化 SkillManager。

        从指定目录加载所有 .md 文件作为 Skill 知识文档。

        Args:
            skills_dir: Skills 目录路径，为 None 时使用默认路径 "skills"
        """
        self._skills_dir = Path(skills_dir or "skills")
        self._skills: dict[str, Skill] = {}
        self._load_skills()

    # ── 加载与解析 ──────────────────────────────────────────────

    def _load_skills(self) -> None:
        """从磁盘加载所有 Skill 文件。

        扫描 Skills 目录下的所有 .md 文件，解析为 Skill 对象。
        加载失败的文件会被跳过并记录警告日志。
        """
        if not self._skills_dir.exists():
            logger.warning("Skills 目录不存在: %s，将使用空知识库", self._skills_dir)
            return

        md_files = list(self._skills_dir.glob("*.md"))
        if not md_files:
            logger.warning("Skills 目录中没有找到 .md 文件: %s", self._skills_dir)
            return

        for md_file in md_files:
            try:
                skill = self._parse_skill_file(md_file)
                self._skills[skill.name] = skill
                logger.info("已加载 Skill: %s (关键词: %s)", skill.name, skill.keywords[:5])
            except Exception as e:  # noqa: BLE001
                logger.warning("加载 Skill 文件失败 %s: %s", md_file, e)

        logger.info("共加载 %d 个 Skills", len(self._skills))

    def _parse_skill_file(self, file_path: Path) -> Skill:
        """解析单个 Markdown 文件为 Skill 对象。

        从文件名生成 Skill 名称，从文件内容提取关键词和标签。

        Args:
            file_path: Markdown 文件路径

        Returns:
            解析后的 Skill 对象
        """
        name = file_path.stem
        content = file_path.read_text(encoding="utf-8")
        keywords = self._extract_keywords(content)
        tags = self._extract_tags(content)

        return Skill(
            name=name,
            file_path=file_path,
            content=content,
            keywords=keywords,
            tags=tags,
        )

    def _extract_keywords(self, content: str) -> list[str]:
        """从 Skill 内容中提取关键词。

        提取标题、适用场景、列表项中的关键短语，用于后续匹配。
        同时对提取的文本进行子串分割，增加匹配覆盖度。

        Args:
            content: Markdown 文件内容

        Returns:
            去重后的关键词列表
        """
        keywords: list[str] = []

        # 提取所有标题文本（去掉 # 前缀）
        headings = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
        for heading in headings:
            # 去掉标题中的 "Skill" 后缀
            heading = re.sub(r'\s+Skill$', '', heading)
            # 分割复合标题
            parts = re.split(r'[，,、/|]', heading)
            for part in parts:
                cleaned = part.strip()
                if cleaned and len(cleaned) <= 20:
                    keywords.append(cleaned)

        # 提取 "适用场景" 章节下的行内关键词
        # 匹配 "## 适用场景" 后的文本行（到下一个 ## 标题为止）
        scenario_match = re.search(
            r'^##\s+适用场景\s*\n(.*?)(?=^##|\Z)',
            content,
            re.MULTILINE | re.DOTALL,
        )
        if scenario_match:
            scenario_text = scenario_match.group(1).strip()
            # 按 / 和换行分割场景关键词
            parts = re.split(r'[/\n]', scenario_text)
            for part in parts:
                cleaned = part.strip()
                if cleaned and len(cleaned) <= 20:
                    keywords.append(cleaned)

        # 提取列表项中的短文本（不超过 15 字符）
        list_items = re.findall(r'^[-*]\s+(.+)$', content, re.MULTILINE)
        for item in list_items:
            # 去掉子描述，只取开头关键词
            first_part = item.split('：')[0].split(':')[0].split('，')[0].strip()
            if first_part and len(first_part) <= 15:
                keywords.append(first_part)

        # 去重，保持顺序
        seen: set = set()
        unique: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique

    def _extract_tags(self, content: str) -> list[str]:
        """从 Skill 文件头部提取元数据标签。

        解析 Markdown 文件顶部的 YAML front matter 或
        第一行标题中的标签信息。

        Args:
            content: Markdown 文件内容

        Returns:
            标签列表
        """
        tags: list[str] = []

        # 尝试提取 YAML front matter 中的 tags
        front_matter = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if front_matter:
            tag_line = re.search(r'tags:\s*\[(.+?)\]', front_matter.group(1))
            if tag_line:
                tags.extend(t.strip() for t in tag_line.group(1).split(','))

        # 从标题中提取标签（如 "# 登录测试 Skill" -> "登录测试"）
        title_match = re.search(r'^#\s+(.+?)(?:\s+Skill)?$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            if title not in tags:
                tags.append(title)

        return tags

    # ── 匹配 ────────────────────────────────────────────────────

    def match_skills(
        self,
        test_goal: str,
        top_k: int = 3,
        threshold: float = 0.1,
    ) -> list[Skill]:
        """根据测试目标匹配最相关的 Skills。

        使用关键词重叠度计算相关性分数，返回得分最高的
        top_k 个 Skills。匹配逻辑：
        1. 分词：将测试目标拆分为中文词组和英文单词
        2. 打分：计算每个 Skill 的关键词与测试目标的重叠度
        3. 排序：按得分降序返回

        Args:
            test_goal: 用户的测试目标描述（自然语言）
            top_k: 最多返回的 Skill 数量，默认 3
            threshold: 最低匹配分数阈值，低于此值的 Skill 不会被返回

        Returns:
            匹配到的 Skill 列表，按相关度降序排列
        """
        if not self._skills:
            return []

        # 提取测试目标中的关键词
        goal_tokens = self._tokenize(test_goal)

        scored: list[tuple[float, Skill]] = []
        for skill in self._skills.values():
            score = self._compute_relevance(goal_tokens, skill)
            if score >= threshold:
                scored.append((score, skill))

        # 按分数降序排序
        scored.sort(key=lambda x: x[0], reverse=True)

        matched = [skill for _, skill in scored[:top_k]]
        if matched:
            logger.info(
                "匹配到 %d 个 Skills: %s",
                len(matched),
                [s.name for s in matched],
            )
        return matched

    def _tokenize(self, text: str) -> list[str]:
        """将文本拆分为关键词 token 列表。

        支持中英文混合文本，中文按字/词分割，英文按空格分割。

        Args:
            text: 待拆分的文本

        Returns:
            token 列表
        """
        tokens: list[str] = []

        # 提取英文单词
        english_words = re.findall(r'[a-zA-Z]{2,}', text)
        tokens.extend(w.lower() for w in english_words)

        # 提取中文词组（2-4字）和单字
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_chars:
            # 添加 2-4 字的子串作为词组
            for length in range(2, min(5, len(segment) + 1)):
                for i in range(len(segment) - length + 1):
                    tokens.append(segment[i:i + length])
            # 也添加单个字
            for char in segment:
                tokens.append(char)

        return tokens

    def _compute_relevance(self, goal_tokens: list[str], skill: Skill) -> float:
        """计算测试目标与 Skill 的相关性分数。

        基于 goal_tokens 与 skill.keywords 的重叠度和子串包含关系计算。
        支持：
        1. 精确匹配：goal_token == keyword
        2. 子串包含：goal_token 包含 keyword 或 keyword 包含 goal_token

        分数 = 命中关键词数 / 总关键词数（避免长 Skill 偏置）。

        Args:
            goal_tokens: 测试目标的 token 列表
            skill: 待评估的 Skill 对象

        Returns:
            相关性分数 [0, 1]
        """
        if not skill.keywords:
            return 0.0

        goal_set = set(goal_tokens)

        hits = 0
        for keyword in skill.keywords:
            # 精确匹配
            if keyword in goal_set:
                hits += 1
                continue
            # 子串包含：goal token 包含关键词
            for token in goal_set:
                if keyword in token or token in keyword:
                    hits += 1
                    break

        if hits == 0:
            return 0.0

        # 使用命中率，避免长 Skill 偏置
        score = hits / len(skill.keywords)
        return min(score, 1.0)

    # ── 格式化与注入 ────────────────────────────────────────────

    def format_skills_for_prompt(self, skills: list[Skill]) -> str:
        """将匹配到的 Skills 格式化为可注入提示词的文本。

        每个 Skill 的内容以分隔线包裹，确保 LLM 能清晰识别
        知识文档的边界。

        Args:
            skills: 要格式化的 Skill 列表

        Returns:
            格式化后的文本，可直接拼接到系统提示词中
        """
        if not skills:
            return ""

        parts: list[str] = []
        for i, skill in enumerate(skills, 1):
            parts.append(f"### 相关技能知识 [{i}]: {skill.name}")
            parts.append(skill.content)
            parts.append("---")

        return "\n".join(parts)

    def build_skill_enhanced_prompt(
        self,
        base_prompt: str,
        test_goal: str,
        top_k: int = 3,
    ) -> str:
        """构建增强 Skill 知识后的完整提示词。

        匹配与测试目标相关的 Skills，将知识内容注入到
        基础提示词的末尾。

        Args:
            base_prompt: 基础系统提示词
            test_goal: 测试目标描述
            top_k: 最多匹配的 Skill 数量

        Returns:
            增强后的完整提示词
        """
        matched = self.match_skills(test_goal, top_k=top_k)
        if not matched:
            return base_prompt

        skill_text = self.format_skills_for_prompt(matched)
        enhanced = f"{base_prompt}\n\n## 相关技能知识（请参考以下知识指导测试行为）\n{skill_text}"

        return enhanced

    # ── 查询接口 ────────────────────────────────────────────────

    def get_skill(self, name: str) -> Skill | None:
        """按名称获取 Skill。

        Args:
            name: Skill 名称（对应文件名，不含 .md 后缀）

        Returns:
            Skill 对象，不存在则返回 None
        """
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """列出所有已加载的 Skill 名称。

        Returns:
            Skill 名称列表
        """
        return list(self._skills.keys())

    def reload(self) -> None:
        """重新加载所有 Skill 文件。

        清空当前缓存，重新从磁盘加载所有 .md 文件。
        适用于运行时动态更新 Skill 知识库。
        """
        self._skills.clear()
        self._load_skills()
