"""
FastAPI 应用入口

提供 RESTful API 接口，用于触发移动端自动化测试任务、查询任务状态与报告、管理设备池。
应用启动时通过 lifespan 上下文管理器初始化设备池、MCP Server 和 LangGraph workflow。
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from src.config.settings import settings


# ------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------


class TestRunRequest(BaseModel):
    """测试运行请求模型

    包含运行测试所需的所有参数，如测试目标应用的描述、设备选择策略等。
    """

    app_description: str
    """待测试应用的描述信息"""
    device_id: str | None = None
    """指定设备 ID，为空时由设备池自动分配"""
    timeout: int = 300
    """测试超时时间（秒）"""


class TestStatusResponse(BaseModel):
    """测试状态响应模型"""

    task_id: str
    """任务唯一标识"""
    status: str
    """当前状态：pending / running / completed / failed"""
    device_id: str | None = None
    """分配的设备 ID"""
    created_at: str | None = None
    """任务创建时间"""
    updated_at: str | None = None
    """最后更新时间"""


class TestReportResponse(BaseModel):
    """测试报告响应模型"""

    task_id: str
    """任务唯一标识"""
    status: str
    """任务最终状态"""
    summary: str | None = None
    """测试摘要"""
    steps: list[dict[str, Any]] = []
    """测试步骤详情"""
    screenshots: list[str] = []
    """截图文件路径列表"""
    duration: float | None = None
    """测试耗时（秒）"""
    error: str | None = None
    """错误信息（如有）"""


class DeviceInfo(BaseModel):
    """设备信息模型"""

    device_id: str
    """设备唯一标识"""
    name: str
    """设备名称"""
    platform: str
    """平台类型"""
    status: str = "idle"
    """当前状态：idle / busy / offline"""
    udid: str
    """设备 UDID"""


# ------------------------------------------------------------
# 全局状态占位
# 生产环境应替换为真实的设备池、MCP Client 和 Workflow 实例
# ------------------------------------------------------------

# 内存任务存储（仅用于演示，生产环境应使用 Redis 或 PostgreSQL）
task_store: dict[str, dict[str, Any]] = {}
# 设备列表（从配置文件加载）
device_pool: list[dict[str, Any]] = []


# ------------------------------------------------------------
# 初始化函数
# ------------------------------------------------------------


async def init_device_pool() -> None:
    """初始化设备池

    从 devices.yaml 配置文件加载设备列表并存入全局设备池。
    """
    import yaml

    config_path = settings.DEVICE_CONFIG_PATH
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        device_pool.clear()
        for dev in data.get("devices", []):
            device_pool.append(
                {
                    "device_id": dev["id"],
                    "name": dev["name"],
                    "platform": dev["platform"],
                    "status": "idle",
                    "udid": dev["udid"],
                }
            )
        logger.info(f"设备池初始化完成，共加载 {len(device_pool)} 台设备")
    except FileNotFoundError:
        logger.warning(f"设备配置文件 {config_path} 未找到，设备池为空")
    except Exception as e:
        logger.error(f"设备池初始化失败: {e}")


async def init_mcp_server() -> None:
    """初始化 MCP Server 连接

    根据配置的传输层协议（stdio/http）建立与 MCP Server 的连接。
    当前为占位实现，后续接入真实的 MCP SDK。
    """
    logger.info(
        f"MCP Server 初始化中: host={settings.MCP_SERVER_HOST}, "
        f"port={settings.MCP_SERVER_PORT}, transport={settings.MCP_TRANSPORT}"
    )
    # TODO: 接入真实的 MCP Client 初始化逻辑
    await asyncio.sleep(0.1)
    logger.info("MCP Server 连接已建立（模拟）")


async def init_langgraph_workflow() -> None:
    """初始化 LangGraph Workflow

    构建并编译基于 LangGraph 的自动化测试工作流图。
    当前为占位实现，后续接入真实的 LangGraph 图构建逻辑。
    """
    logger.info("LangGraph Workflow 初始化中...")
    # TODO: 接入真实的 LangGraph 图构建与编译逻辑
    await asyncio.sleep(0.1)
    logger.info("LangGraph Workflow 初始化完成（模拟）")


# ------------------------------------------------------------
# Lifespan 上下文管理器
# ------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """应用生命周期管理

    启动时依次初始化设备池、MCP Server 和 LangGraph Workflow；
    关闭时执行资源清理。
    """
    logger.info("应用启动中...")
    await init_device_pool()
    await init_mcp_server()
    await init_langgraph_workflow()
    logger.info("应用启动完成")
    yield
    # 关闭时的清理逻辑
    logger.info("应用关闭中，正在释放资源...")
    device_pool.clear()
    task_store.clear()
    logger.info("资源已释放，应用关闭完成")


# ------------------------------------------------------------
# FastAPI 应用实例化
# ------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# ------------------------------------------------------------
# API 路由
# ------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """健康检查端点

    返回应用运行状态与基本配置信息，用于负载均衡器或监控系统的健康探测。
    """
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
    }


@app.post("/api/v1/tests/run")
async def run_test(request: TestRunRequest) -> dict[str, Any]:
    """运行测试端点

    接收测试运行请求，创建任务并返回任务 ID。
    测试任务将在后台异步执行。
    """
    task_id = str(uuid.uuid4())
    task_store[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "app_description": request.app_description,
        "device_id": request.device_id,
        "timeout": request.timeout,
        "created_at": str(asyncio.get_event_loop().time()),
        "updated_at": str(asyncio.get_event_loop().time()),
    }
    logger.info(f"测试任务已创建: task_id={task_id}, app={request.app_description}")

    # TODO: 将任务提交到后台工作队列执行
    # 当前仅做占位响应，后续接入 LangGraph workflow 执行器

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "测试任务已创建，正在排队等待执行",
    }


@app.get("/api/v1/tests/{task_id}")
async def get_test_status(task_id: str) -> TestStatusResponse:
    """获取测试状态端点

    根据任务 ID 查询测试任务的当前执行状态。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return TestStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        device_id=task.get("device_id"),
        created_at=task.get("created_at"),
        updated_at=task.get("updated_at"),
    )


@app.get("/api/v1/tests/{task_id}/report")
async def get_test_report(task_id: str) -> TestReportResponse:
    """获取测试报告端点

    根据任务 ID 获取完整的测试报告，包含测试步骤、截图和耗时等信息。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    # TODO: 从持久化存储中加载真实报告数据
    return TestReportResponse(
        task_id=task["task_id"],
        status=task["status"],
        summary="测试尚未完成，暂无报告数据",
        steps=[],
        screenshots=[],
        duration=None,
        error=None,
    )


@app.get("/api/v1/devices")
async def list_devices() -> list[DeviceInfo]:
    """列出设备端点

    返回设备池中所有设备的状态信息，包括设备名称、平台、当前状态等。
    """
    return [
        DeviceInfo(
            device_id=dev["device_id"],
            name=dev["name"],
            platform=dev["platform"],
            status=dev["status"],
            udid=dev["udid"],
        )
        for dev in device_pool
    ]


# ------------------------------------------------------------
# 启动入口
# ------------------------------------------------------------


def main() -> None:
    """应用启动入口

    使用 uvicorn 启动 FastAPI 应用，监听地址和端口从配置中读取。
    """
    uvicorn.run(
        "src.main:app",
        host=settings.MCP_SERVER_HOST,
        port=settings.MCP_SERVER_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()