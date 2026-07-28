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
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from src.config.settings import settings

# ── 配置文件日志输出 ──────────────────────────────────────────
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)
# 移除 loguru 默认 handler，重新配置同时输出到终端和文件
logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    format=settings.LOG_FORMAT,
    level=settings.LOG_LEVEL,
)
logger.add(
    sink=str(_LOG_DIR / "agent_{time:YYYY-MM-DD}.log"),
    format=settings.LOG_FORMAT,
    level=settings.LOG_LEVEL,
    rotation="00:00",       # 每天轮转
    retention="7 days",     # 保留 7 天
    encoding="utf-8",
)


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


def _determine_node_status(node_name: str, node_output: dict[str, Any]) -> str:
    """根据节点名称和输出内容判定节点执行状态。

    各节点的成功/失败判断逻辑：
    - explorer: 无 error 字段即为成功
    - planner: 生成了 test_plan 且非空即为成功
    - executor: 无 error 字段即为成功
    - verifier: verification_result 为 True 时成功，False 时失败
    - reviewer: node_outputs.reviewer.passed 为 True 时成功，False 时失败

    Args:
        node_name: 节点名称（explorer/planner/executor/verifier/reviewer）
        node_output: 节点返回的输出字典

    Returns:
        节点状态字符串：'success' | 'failed' | 'completed'
    """
    if not isinstance(node_output, dict):
        return 'completed'

    # 通用失败判断：有 error 字段
    if node_output.get('error'):
        return 'failed'

    if node_name == 'verifier':
        # verifier 的核心判断：verification_result（对齐 AgentState 字段名）
        passed = node_output.get('verification_result')
        if passed is True:
            return 'success'
        elif passed is False:
            return 'failed'
        # 检查 node_outputs.verifier.passed
        verifier_output = node_output.get('node_outputs', {}).get('verifier', {})
        if verifier_output.get('passed') is False:
            return 'failed'
        return 'completed'

    elif node_name == 'reviewer':
        # reviewer 的核心判断：node_outputs.reviewer.passed
        reviewer_output = node_output.get('node_outputs', {}).get('reviewer', {})
        if reviewer_output.get('passed') is True:
            return 'success'
        elif reviewer_output.get('passed') is False:
            return 'failed'
        return 'completed'

    elif node_name == 'planner':
        # planner 有 test_plan 且非空即为成功
        steps = node_output.get('test_plan', [])
        if steps:
            return 'success'
        return 'completed'

    elif node_name == 'executor':
        # executor 无 error 即为成功
        executor_output = node_output.get('node_outputs', {}).get('executor', {})
        if executor_output.get('error'):
            return 'failed'
        return 'success'

    elif node_name == 'explorer':
        # explorer 无 error 即为成功
        return 'success'

    return 'completed'


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
    # 节点执行日志列表，记录每个节点的输入/输出/耗时/错误
    node_logs: list[dict[str, Any]] = []

    try:
        # 获取编译后的工作流
        app = get_compiled_graph()

        # 构建初始状态（对齐 AgentState 定义）
        initial_state: dict[str, Any] = {
            'messages': [],
            'test_goal': request.app_description,
            'current_screen': '',
            'ui_tree': None,
            'screenshot_b64': None,
            'test_plan': [],
            'executed_steps': [],
            'current_step_index': 0,
            'verification_result': False,
            'failure_reason': '',
            'retry_count': 0,
            'device_name': request.device_id or 'Pixel_7_API_34',
            'device_connected': False,
            'final_report': '',
            'node_outputs': {},
            'perception_mode': 'hybrid',
            'matched_skills': None,
            'skill_context': None,
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
                # 根据节点输出判断成功/失败
                node_status = _determine_node_status(node_name, node_output)
                log_entry: dict[str, Any] = {
                    'node': node_name,
                    'status': node_status,
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'output_summary': {},
                    'mcp_calls': [],
                    'skills_matched': [],
                }
                # 安全提取输出摘要（避免大对象导致日志过大）
                if isinstance(node_output, dict):
                    for key in ('next_action', 'analysis', 'test_plan', 'verification_result',
                                'final_verdict', 'feedback', 'total_tokens_used', 'failure_reason',
                                'retry_count', 'current_step_index', 'final_report'):
                        if key in node_output:
                            val = node_output[key]
                            log_entry['output_summary'][key] = (
                                str(val)[:500] if isinstance(val, str) and len(val) > 500 else val
                            )
                    # 从 node_outputs 子字典中提取节点特有信息

                    # ── 提取 MCP 工具调用记录 ──────────────────────────
                    # executor 节点的 mcp_calls 在 node_outputs.executor 中
                    executor_output = node_output.get('node_outputs', {}).get('executor', {})
                    mcp_calls = executor_output.get('mcp_calls', [])
                    if mcp_calls:
                        log_entry['mcp_calls'] = [
                            {
                                'tool': c.get('tool', ''),
                                'params': c.get('params', {}),
                                'success': c.get('success', True),
                                'error': c.get('error'),
                            }
                            for c in mcp_calls
                        ]

                    # ── 提取 Skills 匹配记录 ──────────────────────────
                    # explorer 节点的 matched_skills 在顶层
                    matched_skills = node_output.get('matched_skills', [])
                    if matched_skills:
                        log_entry['skills_matched'] = matched_skills
                node_logs.append(log_entry)
                # 实时写入 task_store，使前端可以实时查看
                task['node_logs'] = node_logs.copy()
                task['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
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
        task['node_logs'] = node_logs

        logger.info(f"[Task {task_id}] 测试完成，耗时 {duration:.2f}s")

        # ── 生成测试报告 ──────────────────────────────────────────
        try:
            from src.utils.report_generator import ReportGenerator
            report_gen = ReportGenerator(output_dir="reports")
            executed_steps = task.get('steps', [])
            # 从 verifier 节点输出中提取验证结果
            verifier_output_data = (
                final_state.get('node_outputs', {}).get('verifier', {})
                if isinstance(final_state, dict) else {}
            )
            token_tracker_summary = (
                final_state.get('total_tokens_used', 0)
                if isinstance(final_state, dict) else 0
            )
            report_path = report_gen.generate(
                task_id=task_id,
                test_goal=request.app_description,
                executed_steps=executed_steps,
                verifier_output=verifier_output_data,
                reviewer_output=reviewer_output,
                token_summary={'total_tokens': token_tracker_summary, 'total_cost': 0.0, 'total_records': 0},
                duration=duration,
                device_name=request.device_id or 'default',
                format="html",
            )
            task['report_path'] = report_path
            logger.info(f"[Task {task_id}] 测试报告已生成: {report_path}")
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Task {task_id}] 通知发送失败: {e}")

    except Exception as e:  # noqa: BLE001
        logger.error(f"[Task {task_id}] 测试执行失败: {e}")
        task['status'] = 'failed'
        task['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        task['duration'] = time.time() - start_time
        task['error'] = str(e)
        # 保存节点日志（即使失败也要记录已执行的节点）
        task['node_logs'] = node_logs
        # 记录失败节点
        node_logs.append({
            'node': 'workflow_error',
            'status': 'failed',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'error': str(e),
            'error_type': type(e).__name__,
        })


# ------------------------------------------------------------
# 初始化函数
# ------------------------------------------------------------


async def init_device_pool() -> None:
    """初始化设备池

    从 devices.yaml 配置文件加载设备列表，不依赖 adb devices。
    这样可以同时支持 Android 和 iOS 设备配置，对齐架构设计文档。
    adb 仅用于执行层处理系统级操作（安装应用、文件推送等）。
    """
    import yaml

    device_pool.clear()

    config_path = settings.DEVICE_CONFIG_PATH
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for dev in data.get("devices", []):
            caps = dev.get("capabilities", {})
            device_pool.append({
                "device_id": dev.get("name", ""),
                "name": dev.get("name", ""),
                "platform": dev.get("platform", "Android"),
                "status": "idle",
                "udid": dev.get("udid", ""),
                "appium_port": dev.get("appium_port", 4723),
                "app_package": caps.get("appPackage", ""),
                "app_activity": caps.get("appActivity", ""),
            })
        logger.info(f"从配置文件加载了 {len(device_pool)} 台设备")
    except FileNotFoundError:
        logger.warning(f"设备配置文件 {config_path} 未找到")
    except Exception as e:  # noqa: BLE001
        logger.error(f"设备配置文件加载失败: {e}")

    logger.info(f"设备池初始化完成，共 {len(device_pool)} 台设备")


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
    from src.graph.nodes.executor import get_executor_agent
    from src.graph.workflow import get_compiled_graph

    logger.info("LangGraph Workflow 初始化中...")

    # 编译工作流图
    compiled_graph = get_compiled_graph()
    global langgraph_app
    langgraph_app = compiled_graph

    # 初始化 MCP Client 并注入到 Executor Agent 和 Explorer 节点
    try:
        import sys

        from src.mobile_mcp.client import MCPClient
        # 使用当前 Python 解释器路径，避免 "python" 命令不存在的问题
        python_executable = sys.executable
        mcp_client = MCPClient(
            server_command=python_executable,
            server_args=["-m", "src.mobile_mcp.server"],
        )
        # 注入 MCP Client 到 Executor Agent（延迟连接，实际执行时再连接）
        get_executor_agent(mcp_client=mcp_client)
        # 注入 MCP Client 到 Explorer 节点（供 HybridPerception 使用）
        from src.graph.nodes.explorer import set_mcp_client
        set_mcp_client(mcp_client)
        logger.info("MCP Client 已注入到 Executor Agent 和 Explorer 节点")
    except Exception as e:  # noqa: BLE001
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
    # 关闭时的清理逻辑：断开所有设备连接，停止 Appium 服务
    logger.info("应用关闭中，正在释放资源...")
    try:
        if hasattr(app.state, 'mcp_server') and app.state.mcp_server:
            dm = app.state.mcp_server._device_manager
            dm.disconnect_all()
            logger.info("所有设备连接已断开")
            # 停止自动启动的 Appium Server
            if dm._appium_service and dm._appium_service.is_running:
                dm._appium_service.stop()
                logger.info("Appium Server 已停止")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"资源清理时出错: {e}")
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

# 添加 CORS 中间件，允许 Dashboard 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# API 路由
# ------------------------------------------------------------


@app.get("/api/v1/tests")
async def list_tests() -> dict[str, Any]:
    """列出所有测试任务端点

    返回所有测试任务的摘要列表，支持 Dashboard 前端展示任务总览。
    """
    tasks = []
    for task_id, task in task_store.items():
        tasks.append({
            "task_id": task_id,
            "status": task.get("status", "unknown"),
            "app_description": task.get("app_description", ""),
            "device_id": task.get("device_id"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "duration": task.get("duration"),
            "summary": task.get("summary"),
            "final_verdict": task.get("final_verdict"),
        })
    # 按创建时间倒序排列
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"total": len(tasks), "tasks": tasks}


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


@app.post("/api/v1/devices/refresh")
async def refresh_devices() -> dict[str, Any]:
    """刷新设备列表端点

    重新通过 adb 检测当前连接的设备，更新设备池。
    """
    await init_device_pool()
    return {
        "total": len(device_pool),
        "devices": [
            {
                "device_id": dev["device_id"],
                "name": dev["name"],
                "platform": dev["platform"],
                "status": dev["status"],
                "udid": dev["udid"],
            }
            for dev in device_pool
        ],
    }


@app.get("/api/v1/tests/{task_id}/logs")
async def get_task_logs(task_id: str) -> dict[str, Any]:
    """获取任务执行日志端点

    返回指定任务的工作流节点执行日志，包含每个节点的状态、输出摘要和错误信息，
    用于排查测试执行过程中的问题。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return {
        "task_id": task_id,
        "status": task["status"],
        "error": task.get("error"),
        "duration": task.get("duration"),
        "node_logs": task.get("node_logs", []),
        "token_usage": task.get("token_usage"),
    }


@app.get("/api/v1/logs/service")
async def get_service_logs(
    lines: int = Query(default=200, ge=1, le=2000, description="读取的日志行数"),
    level: str = Query(default="ALL", description="过滤日志级别：ALL/DEBUG/INFO/WARNING/ERROR"),
) -> dict[str, Any]:
    """获取服务日志端点

    读取日志文件最近的指定行数，支持按日志级别过滤。
    日志文件路径：logs/agent_YYYY-MM-DD.log
    """
    import datetime

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = _LOG_DIR / f"agent_{today}.log"

    if not log_file.exists():
        return {
            "log_file": str(log_file),
            "exists": False,
            "lines": [],
            "total": 0,
        }

    try:
        with open(log_file, encoding="utf-8") as f:
            all_lines = f.readlines()

        # 取最后 N 行
        recent_lines = all_lines[-lines:]

        # 按级别过滤
        if level != "ALL":
            level_upper = level.upper()
            recent_lines = [
                line for line in recent_lines
                if f"| {level_upper:<8} |" in line
            ]

        return {
            "log_file": str(log_file),
            "exists": True,
            "lines": [line.rstrip("\n") for line in recent_lines],
            "total": len(recent_lines),
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取日志文件失败: {e}")


@app.get("/api/v1/tests/{task_id}/mcp-calls")
async def get_task_mcp_calls(task_id: str) -> dict[str, Any]:
    """获取任务的 MCP 工具调用记录端点

    从 node_logs 中提取所有 MCP 工具调用记录，便于排查 MCP 调用情况。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    node_logs = task.get("node_logs", [])
    mcp_calls: list[dict[str, Any]] = []
    for log_entry in node_logs:
        node_mcp_calls = log_entry.get("mcp_calls", [])
        if node_mcp_calls:
            mcp_calls.append({
                "node": log_entry.get("node", ""),
                "timestamp": log_entry.get("timestamp", ""),
                "calls": node_mcp_calls,
            })

    return {
        "task_id": task_id,
        "total_mcp_call_nodes": len(mcp_calls),
        "total_mcp_calls": sum(len(n["calls"]) for n in mcp_calls),
        "mcp_calls": mcp_calls,
    }


@app.get("/api/v1/tests/{task_id}/skills")
async def get_task_skills(task_id: str) -> dict[str, Any]:
    """获取任务的 Skills 匹配记录端点

    从 node_logs 中提取所有 Skills 匹配记录，便于查看知识匹配情况。
    """
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    node_logs = task.get("node_logs", [])
    skills_info: list[dict[str, Any]] = []
    for log_entry in node_logs:
        matched = log_entry.get("skills_matched", [])
        if matched:
            skills_info.append({
                "node": log_entry.get("node", ""),
                "timestamp": log_entry.get("timestamp", ""),
                "matched_skills": matched,
            })

    return {
        "task_id": task_id,
        "total_skills_nodes": len(skills_info),
        "skills_matched": skills_info,
    }


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
