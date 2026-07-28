"""
测试报告数据模型模块

定义测试报告、步骤执行结果和测试状态枚举的数据模型，
用于记录和展示移动端自动化测试的执行结果。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TestStatus(str, Enum):
    """测试状态枚举

    定义测试用例的可能执行状态。
    """

    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    PASSED = "passed"        # 通过
    FAILED = "failed"        # 失败
    ERROR = "error"          # 执行出错
    TIMEOUT = "timeout"      # 执行超时


class StepResult(BaseModel):
    """步骤执行结果数据模型

    记录单个测试步骤的执行结果，包含执行时间、截图和错误信息等。
    """

    step_index: int = Field(..., description="步骤在测试用例中的索引序号")
    action: str = Field(..., description="执行的操作动作描述")
    result: str = Field(..., description="执行结果描述信息")
    screenshot_b64: str | None = Field(default=None, description="步骤执行时截图的 Base64 编码，可选")
    passed: bool = Field(..., description="步骤是否执行通过")
    error: str | None = Field(default=None, description="步骤执行时的错误信息，无错误时为 None")
    started_at: datetime | None = Field(default=None, description="步骤开始执行的时间")
    finished_at: datetime | None = Field(default=None, description="步骤执行完成的时间")
    duration: float = Field(default=0.0, description="步骤执行耗时（秒）")


class TestReport(BaseModel):
    """测试报告数据模型

    记录单个测试用例的完整执行报告，包含设备信息、执行状态、耗时和汇总信息等。
    """

    task_id: str = Field(..., description="测试任务唯一标识符")
    test_case: str = Field(..., description="测试用例 ID 或名称")
    device: str = Field(..., description="执行测试的设备标识符")
    status: TestStatus = Field(default=TestStatus.PENDING, description="测试用例执行状态")
    started_at: datetime | None = Field(default=None, description="测试开始时间")
    finished_at: datetime | None = Field(default=None, description="测试完成时间")
    duration: float = Field(default=0.0, description="测试总耗时（秒）")
    steps: list[StepResult] = Field(default_factory=list, description="各步骤的执行结果列表")
    total_tokens: int = Field(default=0, description="AI 调用消耗的总 Token 数")
    cost: float = Field(default=0.0, description="测试执行的总成本（美元）")
    summary: str = Field(default="", description="测试执行结果总结说明")
