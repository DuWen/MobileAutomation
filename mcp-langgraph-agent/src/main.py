"""
FastAPI 应用入口

提供 RESTful API 接口，用于触发移动端自动化测试任务、查询任务状态与报告、管理设备池。
应用启动时通过 lifespan 上下文管理器初始化设备池、MCP Server 和 LangGraph workflow。
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
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
    quality_metrics: dict[str, Any] | None = None
    """质量指标"""
    token_usage: dict[str, Any] | None = None
    """Token 使用统计"""


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
# 全局状态
# ------------------------------------------------------------

# 内存任务存储（仅用于演示，生产环境应使用 Redis 或 PostgreSQL）
task_store: dict[str, dict[str, Any]] = {}
# 设备列表（从配置文件加载）
device_pool: list[dict[str, Any]] = []
# LangGraph 编译后的工作流实例
langgraph_app: Any = None


# ------------------------------------------------------------
# 工作流运行器
# ------------------------------------------------------------


async def run_workflow_task(task_id: str, request: TestRunRequest) -> None:
    """后台运行 LangGraph 工作流任务。

    构建初始状态，调用 LangGraph 工作流执行测试，
    完成后更新任务状态和报告。

    Args:
        task_id: 任务唯一标识
        request: 测试运行请求参数
    """
    import time

    from src.graph.workflow import get_compiled_graph

    task = task_store.get(task_id)
    if not task:
        return

    # 更新任务状态为运行中
    task['status'] = 'running'
    task['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    start_time = time.time()

    try:
        # 获取编译后的工作流
        app = get_compiled_graph()

        # 构建初始状态
        initial_state: dict[str, Any] = {
            'test_goal': request.app_description,
            'test_steps': [],
            'current_step_index': 0,
            'executed_steps': [],
            'ui_tree': None,
            'screenshot_b64': None,
            'device_name': request.device_id or 'default',
            'test_plan': None,
            'verification_passed': False,
            'verification_details': [],
            'retry_count': 0,
            'max_retries': 3,
            'error': None,
            'messages': [],
            'node_outputs': {},
            'reviewer_feedback': None,
            'total_tokens_used': 0,
            'metadata': {
                'task_id': task_id,
                'start_time': start_time,
                'device_id': request.device_id,
                'timeout': request.timeout,
            },
        }

        # 执行工作流，使用 task_id 作为线程 ID 以支持检查点
        config = {'configurable': {'thread_id': task_id}}
        final_state = None

        # 流式执行工作流，获取最终状态
        async for event in app.astream(initial_state, config):
            # 记录每个节点的事件
            for node_name, node_output in event.items():
                logger.info(f"[Task {task_id}] 节点 {node_name} 执行完成")
            final_state = node_output if event else None

        # 如果没有获取到最终状态，尝试从检查点获取
        if final_state is None:
            checkpoint = await app.aget_state(config)
            if checkpoint and checkpoint.values:
                final_state = checkpoint.values

        # 计算耗时
        duration = time.time() - start_time

        # 提取审查结果
        reviewer_output = (
            final_state.get('node_outputs', {}).get('reviewer', {})
            if isinstance(final_state, dict) else {}
        )

        # 更新任务状态为完成
        task['status'] = 'completed'
        task['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        task['duration'] = duration
        task['summary'] = reviewer_output.get('feedback', '测试完成')
        task['steps'] = final_state.get('executed_steps', []) if isinstance(final_state, dict) else []
        task['quality_metrics'] = reviewer_output.get('quality_metrics', {})
        task['token_usage'] = {'total_tokens_used': final_state.get('total_tokens_used', 0)} if isinstance(final_state, dict) else {}
        task['final_verdict'] = reviewer_output.get('final_verdict', 'need_manual_check')

        logger.info(f"[Task {task_id}] 测试完成，耗时 {duration:.2f}s")

        # ── 生成测试报告 ──────────────────────────────────────────
        try:
            from src.utils.report_generator import ReportGenerator
            report_gen = ReportGenerator(output_dir="reports")
            executed_steps = task.get('steps', [])
            verification_details = (
                final_state.get('verification_details', [])
                if isinstance(final_state, dict) else []
            )
            token_tracker_summary = (
                final_state.get('total_tokens_used', 0)
                if isinstance(final_state, dict) else 0
            )
            report_path = report_gen.generate(
                task_id=task_id,
                test_goal=request.app_description,
                executed_steps=executed_steps,
                verification_details=verification_details,
                reviewer_output=reviewer_output,
                token_summary={'total_tokens': token_tracker_summary, 'total_cost': 0.0, 'total_records': 0},
                duration=duration,
                device_name=request.device_id or 'default',
                format="html",
            )
            task['report_path'] = report_path
            logger.info(f"[Task {task_id}] 测试报告已生成: {report_path}")
        except Exception as e:
            logger.warning(f"[Task {task_id}] 报告生成失败: {e}")

        # ── 记录性能基准 ──────────────────────────────────────────
        try:
            from src.utils.benchmark import BenchmarkRunner
            bench_runner = BenchmarkRunner(data_dir="data/benchmarks")
            step_count = len(executed_steps) if executed_steps else 0
            passed_steps = sum(1 for s in executed_steps if s.get('passed', False)) if executed_steps else 0
            bench_result = bench_runner.record_benchmark(
                task_id=task_id,
                test_goal=request.app_description,
                duration=duration,
                step_count=step_count,
                passed_steps=passed_steps,
                total_tokens=token_tracker_summary,
                total_cost=0.0,
                verdict=task.get('final_verdict', 'unknown'),
            )
            task['benchmark'] = {
                'tokens_per_step': bench_result.tokens_per_step,
                'duration_per_step': bench_result.duration_per_step,
                'pass_rate': bench_result.pass_rate,
            }
        except Exception as e:
            logger.warning(f"[Task {task_id}] 基准记录失败: {e}")

        # ── 发送通知 ──────────────────────────────────────────────
        try:
            from src.utils.notifier import Notifier
            notifier = Notifier(
                feishu_webhook_url=settings.FEISHU_WEBHOOK_URL,
                slack_webhook_url=settings.SLACK_WEBHOOK_URL,
            )
            if notifier.enabled:
                pass_rate_str = f"{(passed_steps / step_count * 100):.0f}%" if step_count > 0 else "N/A"
                notifier.notify_test_completed(
                    task_id=task_id,
                    test_goal=request.app_description,
                    verdict=task.get('final_verdict', 'unknown'),
                    duration=duration,
                    pass_rate=pass_rate_str,
                    total_tokens=token_tracker_summary,
                )
        except Exception as e:
            logger.warning(f"[Task {task_id}] 通知发送失败: {e}")

    except Exception as e:
        logger.error(f"[Task {task_id}] 测试执行失败: {e}")
        task['status'] = 'failed'
        task['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        task['duration'] = time.time() - start_time
        task['error'] = str(e)


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
    """初始化 MCP Server

    创建 MobileAutomationServer 实例，从配置加载设备列表，
    为后续通过 MCP 协议调用工具做准备。
    """
    from src.mobile_mcp.server import create_server

    logger.info(
        f"MCP Server 初始化中: host={settings.MCP_SERVER_HOST}, "
        f"port={settings.MCP_SERVER_PORT}, transport={settings.MCP_TRANSPORT}"
    )
    app.state.mcp_server = create_server()
    logger.info("MCP Server 实例已创建")


async def init_langgraph_workflow() -> None:
    """初始化 LangGraph Workflow

    构建并编译基于 LangGraph 的自动化测试工作流图，
    同时初始化各节点的 Agent 实例。
    """
    from src.graph.workflow import get_compiled_graph
    from src.graph.nodes.executor import get_executor_agent

    logger.info("LangGraph Workflow 初始化中...")

    # 编译工作流图
    compiled_graph = get_compiled_graph()
    global langgraph_app
    langgraph_app = compiled_graph

    # 初始化 MCP Client 并注入到 Executor Agent
    try:
        from src.mobile_mcp.client import MCPClient
        mcp_client = MCPClient(
            server_command="python",
            server_args=["-m", "src.mobile_mcp.server"],
        )
        # 注入 MCP Client 到 Executor Agent（延迟连接，实际执行时再连接）
        get_executor_agent(mcp_client=mcp_client)
        logger.info("MCP Client 已注入到 Executor Agent")
    except Exception as e:
        logger.warning(f"MCP Client 初始化失败（将使用模拟模式）: {e}")

    logger.info("LangGraph Workflow 初始化完成")


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

    接收测试运行请求，创建任务并在后台异步执行 LangGraph 工作流。
    """
    import time

    task_id = str(uuid.uuid4())
    task_store[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "app_description": request.app_description,
        "device_id": request.device_id,
        "timeout": request.timeout,
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    logger.info(f"测试任务已创建: task_id={task_id}, app={request.app_description}")

    # 启动后台工作流任务
    asyncio.create_task(run_workflow_task(task_id, request))

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "测试任务已创建，正在后台执行",
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

    return TestReportResponse(
        task_id=task["task_id"],
        status=task["status"],
        summary=task.get("summary"),
        steps=task.get("steps", []),
        screenshots=[],
        duration=task.get("duration"),
        error=task.get("error"),
        quality_metrics=task.get("quality_metrics"),
        token_usage=task.get("token_usage"),
    )


@app.get("/api/v1/tests/{task_id}/report/file")
async def get_test_report_file(task_id: str):
    """下载测试报告文件端点

    根据任务 ID 返回生成的 HTML 或 Markdown 报告文件。
    """
    from fastapi.responses import FileResponse

    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    report_path = task.get("report_path")
    if not report_path:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 的报告文件尚未生成")

    path = Path(report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"报告文件不存在: {report_path}")

    media_type = "text/html" if path.suffix == ".html" else "text/markdown"
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
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
