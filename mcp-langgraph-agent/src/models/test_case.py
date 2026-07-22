"""
测试用例数据模型模块

定义测试用例和测试步骤的数据模型，用于描述移动端自动化测试的测试场景。
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class TestStep(BaseModel):
    """测试步骤数据模型

    描述单个测试操作步骤，包含操作动作、目标元素、参数和预期结果。
    """

    id: str = Field(..., description="步骤唯一标识符")
    action: str = Field(..., description="操作动作，如 click、input、swipe 等")
    target: str = Field(..., description="目标元素定位器，如 XPath 或 Accessibility ID")
    params: dict = Field(default_factory=dict, description="操作参数，如输入文本、滑动距离等")
    expected: str = Field(..., description="预期结果描述")
    timeout: int = Field(default=30, description="步骤超时时间（秒），默认 30 秒")


class TestCase(BaseModel):
    """测试用例数据模型

    描述一个完整的测试用例，包含基本信息、测试步骤、标签和优先级等属性。
    """

    id: str = Field(..., description="测试用例唯一标识符")
    name: str = Field(..., description="测试用例名称")
    description: str = Field(default="", description="测试用例描述信息")
    goal: str = Field(..., description="测试用例的测试目标")
    steps: List[TestStep] = Field(default_factory=list, description="测试步骤列表")
    tags: List[str] = Field(default_factory=list, description="测试用例标签列表，用于分类和筛选")
    priority: str = Field(default="medium", description="测试用例优先级：high / medium / low")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")