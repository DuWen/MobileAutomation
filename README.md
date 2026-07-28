# MobileAutomation

> AI 驱动的移动端自动化测试系统 —— 基于自建 MCP Server + LangGraph Agent + Appium 的多 Agent 协作方案

MobileAutomation 让你用一句自然语言描述测试目标（例如"用 test@qq.com 登录后验证首页显示用户名"），系统会自动完成界面探索、测试步骤规划、操作执行、结果验证和最终审查，全程无需编写测试脚本。

## 核心特性

- **自然语言驱动** —— 用中文/英文描述测试目标，LLM 自动生成并执行测试步骤
- **多 Agent 协作** —— Explorer / Planner / Executor / Verifier / Reviewer 五节点工作流，各司其职
- **自建 MCP Server** —— 基于 JSON-RPC 2.0 协议暴露 12 个移动端操作工具，LLM 通过标准协议调用
- **多级页面自适应** —— Executor 每步刷新 UI 树；失败超限时自动回到 Explorer 重新感知 + Planner 重新规划剩余步骤
- **混合感知降本** —— 无障碍树优先（Token 消耗仅为截图的 1/10~1/50），信息不足时自动降级到截图
- **UI 树智能压缩** —— 属性白名单 + 冗余容器提升 + 可选 aggressive 模式过滤装饰性叶子节点
- **多平台支持** —— Android（UiAutomator2）/ iOS（XCUITest）统一通过 devices.yaml 配置
- **可视化 Dashboard** —— 实时节点执行日志、MCP 调用记录、Token 使用统计、设备池状态
- **Checkpoint 持久化** —— LangGraph MemorySaver 支持任务中断恢复

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        编排层 (LangGraph)                    │
│   StateGraph: explorer → planner → executor → verifier     │
│                          ↑                    ↓             │
│                       reviewer ← 条件路由                    │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP 协议 (JSON-RPC 2.0)
┌──────────────────────────────┴──────────────────────────────┐
│                        Agent 层 (LLM)                        │
│   Explorer / Planner / Executor / Verifier / Reviewer       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                       工具层 (MCP Server)                     │
│   connect_device / tap_element / input_text / swipe /       │
│   get_ui_tree / take_screenshot / assert_text_visible ...   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                     执行层 (Appium + adb)                     │
│        Appium Server + UiAutomator2 / XCUITest              │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                       设备层 (Device Pool)                    │
│            Android 模拟器/真机 · iOS 模拟器/真机              │
└─────────────────────────────────────────────────────────────┘
```

### 工作流拓扑

```
START → explorer → planner → executor → verifier → 条件路由
                                                  ↓
                                           通过: executor(下一步) / reviewer(全部完成)
                                           失败: executor(重试, 最多3次)
                                                 ↓ (重试超限)
                                           explorer(重新感知, replan_count++) / END(超限)
                                                 ↓
                                           planner(增量规划) → executor → ...
                                           reviewer: passed→END / rejected→planner
```

- `MAX_RETRIES = 3` —— 单步骤最大重试次数
- `MAX_REPLAN_COUNT = 2` —— 最大重新规划次数（防死循环）

## 项目结构

```
MobileAutomation/
├── mcp-langgraph-agent/          # 核心服务（Python）
│   ├── src/
│   │   ├── main.py               # FastAPI 入口（REST API）
│   │   ├── graph/                # LangGraph 工作流
│   │   │   ├── state.py          # AgentState 共享状态
│   │   │   ├── workflow.py       # StateGraph 构建与路由
│   │   │   └── nodes/            # 5 个节点实现
│   │   ├── agents/               # Agent 与 LLM 路由
│   │   │   ├── prompts.py        # 提示词模板
│   │   │   └── llm.py            # ModelRouter
│   │   ├── mobile_mcp/           # MCP Server + Client
│   │   │   ├── server.py         # FastMCP Server（12 个工具）
│   │   │   ├── client.py         # MCP Client
│   │   │   └── tools/            # 设备/UI/视觉/断言工具包
│   │   ├── config/               # 配置文件
│   │   │   ├── devices.yaml      # 设备池
│   │   │   ├── llm.yaml          # LLM 模型路由
│   │   │   └── settings.py       # Pydantic Settings
│   │   ├── skills/               # 测试技能知识库（Markdown）
│   │   └── utils/                # 感知/压缩/脱敏/Token 追踪
│   ├── scripts/                  # 环境初始化脚本
│   ├── tests/                    # 单元测试
│   ├── docker-compose.yml        # 一键启动全栈服务
│   ├── Dockerfile.*              # MCP / LangGraph / Appium 镜像
│   ├── Makefile                  # 常用命令快捷方式
│   └── requirements.txt
├── mobile-test-dashboard/        # 可视化前端（纯 HTML）
├── ai-mobile-test-guide/         # 架构设计文档
│   └── plan-c-mcp-langgraph.html # 完整设计方案（权威文档）
└── scripts/                      # 顶层工具脚本
```

## 快速开始

### 环境要求

- Python ≥ 3.11
- Node.js LTS（用于 Appium Server）
- Appium ≥ 2.0 + UiAutomator2 驱动（Android）/ XCUITest 驱动（iOS）
- Android Studio（提供 SDK 与模拟器）或 Xcode（iOS 开发）
- LLM API Key（OpenAI / Anthropic / Ollama）

### 一键初始化

```bash
cd mcp-langgraph-agent
chmod +x scripts/setup.sh && ./scripts/setup.sh
```

脚本会自动完成：Python 虚拟环境创建、依赖安装、Appium 检查、Android/iOS 环境检测、配置文件初始化、环境验证。

### 手动配置

1. **复制环境变量模板**

   ```bash
   cd mcp-langgraph-agent
   cp .env.example .env
   ```

2. **编辑 `.env` 填入 LLM API Key**

   ```ini
   LLM_PROVIDER=openai
   LLM_API_KEY=sk-your-api-key-here
   LLM_MODEL=gpt-4o
   ```

3. **配置设备池** —— 编辑 `src/config/devices.yaml`

   ```yaml
   devices:
     - name: "Pixel_7_API_34"
       platform: "Android"
       udid: "emulator-5554"
       appium_port: 4723
       capabilities:
         automationName: "UiAutomator2"
         platformVersion: "14"
         appPackage: "com.example.myapp"
         appActivity: ".MainActivity"
         noReset: true
         newCommandTimeout: 300
   ```

4. **（可选）配置 LLM 路由** —— 编辑 `src/config/llm.yaml`

   ```yaml
   llm:
     provider: "openai"
     default_model: "gpt-4o"
     fallback_model: "gpt-4o-mini"
     routing:
       - pattern: "简单.*(点击|返回|输入)"
         model: "gpt-4o-mini"
       - pattern: "分析|判断|异常"
         model: "gpt-4o"
   ```

### 启动服务

**方式一：本地开发**

```bash
cd mcp-langgraph-agent
source venv/bin/activate
make dev   # 同时启动 MCP Server (8000) 和 LangGraph Agent (8001)
```

**方式二：Docker Compose**

```bash
cd mcp-langgraph-agent
docker-compose up -d   # 启动 MCP Server + LangGraph Agent + Redis + PostgreSQL
```

### 运行测试

```bash
# 启动 Appium Server
appium --address 127.0.0.1 --port 4723

# 启动 Android 模拟器或连接真机
emulator -avd Pixel_7_API_34   # 或 adb connect <device_ip>

# 通过 REST API 触发测试任务
curl -X POST http://localhost:8001/api/v1/tests/run \
  -H "Content-Type: application/json" \
  -d '{
    "app_description": "测试用户登录流程，用 test@qq.com 和密码登录后验证首页显示用户名",
    "device_id": "Pixel_7_API_34",
    "timeout": 300
  }'

# 查询任务状态
curl http://localhost:8001/api/v1/tests/{task_id}

# 获取测试报告
curl http://localhost:8001/api/v1/tests/{task_id}/report
```

## REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tests/run` | 提交测试任务 |
| GET | `/api/v1/tests` | 列出所有任务 |
| GET | `/api/v1/tests/{task_id}` | 查询任务状态 |
| GET | `/api/v1/tests/{task_id}/report` | 获取测试报告 |
| GET | `/api/v1/tests/{task_id}/report/file` | 下载报告文件 |
| GET | `/api/v1/tests/{task_id}/logs` | 获取节点执行日志 |
| GET | `/api/v1/tests/{task_id}/mcp-calls` | 获取 MCP 工具调用记录 |
| GET | `/api/v1/tests/{task_id}/skills` | 获取 Skills 匹配记录 |
| GET | `/api/v1/devices` | 列出设备池 |
| POST | `/api/v1/devices/refresh` | 刷新设备列表 |
| GET | `/api/v1/logs/service` | 获取服务日志 |
| GET | `/health` | 健康检查 |

## MCP 工具一览

| 工具 | 说明 |
|------|------|
| `connect_device` | 连接设备并启动 App，建立 Appium 会话 |
| `disconnect_device` | 断开设备连接 |
| `tap_element` | 点击元素（支持 id/xpath/accessibility_id/text 定位 + bounds 降级） |
| `input_text` | 在指定元素中输入文本 |
| `swipe` | 滑动操作 |
| `get_ui_tree` | 获取 UI 无障碍树（支持 compress 与 aggressive 过滤） |
| `take_screenshot` | 截图并保存到 `screenshots/` 目录 |
| `assert_text_visible` | 断言文本可见性 |
| `assert_element_exists` | 断言元素存在性 |
| `press_key` | 按键操作（返回、Home 等） |
| `get_device_info` | 获取设备信息 |
| `list_devices` | 列出已连接设备 |

## 开发命令

```bash
make install    # 安装依赖（开发模式）
make dev        # 启动开发服务器
make lint       # 代码检查（ruff + mypy）
make test       # 运行测试用例
make docker-up  # 启动 Docker 容器
make docker-down # 停止 Docker 容器
make clean      # 清理缓存
```

## 关键设计文档

设计文档已迁移至 GitHub Wiki，不再纳入主仓库版本控制：

- [plan-c-mcp-langgraph](https://github.com/DuWen/MobileAutomation/wiki/plan‑c‑mcp‑langgraph) —— 完整架构设计方案（**任何架构和接口变更以该文档为准**）
- [plan-c-design-deployment](https://github.com/DuWen/MobileAutomation/wiki/plan‑c‑design‑deployment) —— 设计与部署方案
- [ai-mobile-test-guide](https://github.com/DuWen/MobileAutomation/wiki/ai‑mobile‑test‑guide) —— AI 移动端测试指南总览

## 技术栈

| 层 | 技术 |
|----|------|
| 编排层 | LangGraph StateGraph + MemorySaver |
| Agent 层 | LangChain + OpenAI / Anthropic / Ollama |
| 工具层 | MCP (JSON-RPC 2.0, stdio 传输) + FastMCP |
| 执行层 | Appium 2.0 + UiAutomator2 / XCUITest |
| Web 框架 | FastAPI + Uvicorn |
| 数据验证 | Pydantic v2 + pydantic-settings |
| 缓存/队列 | Redis |
| 数据库 | PostgreSQL (asyncpg + SQLAlchemy) |
| 监控 | Prometheus Client + Loguru |
| 容器化 | Docker + docker-compose |

## License

MIT
