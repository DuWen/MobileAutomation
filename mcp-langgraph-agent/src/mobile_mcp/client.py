"""
MCP Client 封装模块

提供 MCPClient 类，通过 MCP SDK 与 MCP Server 通信。
支持 stdio 传输方式，包含错误处理、重试机制、
连接超时以及自动重连功能。
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 连接超时时间（秒）
CONNECT_TIMEOUT: float = 15.0
# 单次工具调用超时时间（秒）
CALL_TIMEOUT: float = 30.0


class MCPClientError(Exception):
    """MCP 客户端异常基类。

    封装所有 MCP 客户端操作中可能出现的异常场景。
    """



class MCPConnectionError(MCPClientError):
    """MCP 连接异常，表示与服务器的连接出现问题。"""



class MCPToolError(MCPClientError):
    """MCP 工具调用异常，表示工具执行时返回错误。"""

    def __init__(
        self, message: str, tool_name: str, result: dict | None = None
    ) -> None:
        """初始化工具调用异常。

        Args:
            message: 异常描述信息。
            tool_name: 出错的工具名称。
            result: 工具返回的原始结果字典（可选）。
        """
        super().__init__(message)
        self.tool_name = tool_name
        self.result = result


class MCPClient:
    """MCP 客户端，通过 stdio 与 MCP Server 通信。

    使用 MCP SDK 的 ClientSession 和 stdio_client 建立连接，
    提供工具发现和调用功能。支持自动重连和超时控制。

    Attributes:
        server_command: 启动 MCP Server 的命令。
        server_args: 启动 MCP Server 的命令行参数。
        max_retries: 最大重试次数。
        retry_delay: 重试间隔（秒）。
    """

    def __init__(
        self,
        server_command: str = "python",
        server_args: list | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        connect_timeout: float = CONNECT_TIMEOUT,
    ) -> None:
        """初始化 MCP 客户端。

        Args:
            server_command: 启动 MCP Server 的命令，默认为 "python"。
            server_args: 启动 MCP Server 的命令行参数列表。
            max_retries: 调用工具时的最大重试次数，默认为 3。
            retry_delay: 重试间隔时间（秒），默认为 1.0 秒。
            connect_timeout: 连接超时时间（秒），默认为 15 秒。
        """
        self.server_command = server_command
        self.server_args = server_args or ["-m", "src.mcp.server"]
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connect_timeout = connect_timeout

        # 连接状态
        self._session: Any | None = None
        self._stdio_cm: Any | None = None  # stdio_client 上下文管理器
        self._session_cm: Any | None = None  # ClientSession 上下文管理器
        self._read_stream: Any | None = None
        self._write_stream: Any | None = None
        self._connected: bool = False
        self._connecting: bool = False  # 防止并发连接

    async def connect(self) -> None:
        """建立与 MCP Server 的连接。

        通过 stdio 传输方式启动 MCP Server 并建立 ClientSession。
        带超时控制，防止子进程启动失败时无限挂起。

        Raises:
            MCPConnectionError: 连接失败时抛出。
        """
        if self._connected:
            logger.warning("[MCPClient] 客户端已连接，跳过重复连接")
            return

        if self._connecting:
            logger.warning("[MCPClient] 正在连接中，跳过重复连接请求")
            return

        self._connecting = True
        try:
            await asyncio.wait_for(self._do_connect(), timeout=self.connect_timeout)
        except TimeoutError:
            # 超时后清理资源
            await self._cleanup()
            raise MCPConnectionError(
                f"连接 MCP Server 超时（{self.connect_timeout}s），"
                f"请检查 server_command={self.server_command} 和 "
                f"server_args={self.server_args} 是否正确"
            ) from None
        except MCPConnectionError:
            await self._cleanup()
            raise
        except Exception as e:
            await self._cleanup()
            raise MCPConnectionError(
                f"连接 MCP Server 失败: {e!s}"
            ) from e
        finally:
            self._connecting = False

    async def _do_connect(self) -> None:
        """执行实际连接逻辑（内部方法）。

        依次完成：stdio 连接 → 创建 ClientSession → 初始化会话。

        Raises:
            ImportError: MCP SDK 未安装。
            MCPConnectionError: 连接各阶段失败。
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as e:
            raise MCPConnectionError(
                f"MCP SDK 未安装，请执行 pip install mcp: {e!s}"
            ) from e

        server_params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
        )

        logger.info(
            "[MCPClient] 正在启动 MCP Server 子进程: %s %s",
            self.server_command, " ".join(self.server_args),
        )

        # 建立 stdio 连接（保存上下文管理器以便后续清理）
        self._stdio_cm = stdio_client(server_params)
        self._read_stream, self._write_stream = await self._stdio_cm.__aenter__()

        # 创建 ClientSession（保存上下文管理器以便后续清理）
        self._session_cm = ClientSession(self._read_stream, self._write_stream)
        self._session = await self._session_cm.__aenter__()

        # 初始化会话
        await self._session.initialize()

        self._connected = True
        logger.info("[MCPClient] 已成功连接到 MCP Server")

    async def _cleanup(self) -> None:
        """清理连接资源（内部方法）。

        安全退出所有上下文管理器，确保子进程被终止。
        """
        for cm, name in [(self._session_cm, "session"), (self._stdio_cm, "stdio")]:
            if cm is not None:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception as e:  # noqa: BLE001
                    logger.warning("[MCPClient] 清理 %s 时出错: %s", name, e)

        self._session = None
        self._session_cm = None
        self._stdio_cm = None
        self._read_stream = None
        self._write_stream = None
        self._connected = False

    async def disconnect(self) -> None:
        """断开与 MCP Server 的连接。

        清理 ClientSession 和 stdio 连接资源。
        """
        if not self._connected and not self._session_cm and not self._stdio_cm:
            return

        try:
            await self._cleanup()
            logger.info("[MCPClient] 已断开连接")
        except Exception as e:  # noqa: BLE001
            logger.error("[MCPClient] 断开连接时发生错误: %s", str(e))
            self._connected = False

    async def _ensure_connected(self) -> None:
        """确保客户端已连接，未连接时自动建立连接。

        连接失败时记录警告但不抛出异常，让上层代码可以降级处理。

        Returns:
            None
        """
        if not self._connected or self._session is None:
            try:
                logger.info("[MCPClient] 未连接，自动建立连接...")
                await self.connect()
            except MCPConnectionError as e:
                logger.warning("[MCPClient] 自动连接失败: %s", e)
                raise

    async def list_tools(self) -> list[dict]:
        """获取 MCP Server 上注册的所有工具列表。

        Returns:
            工具信息字典列表，每个字典包含 name、description 等字段。

        Raises:
            MCPConnectionError: 连接异常时抛出。
        """
        await self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                self._session.list_tools(), timeout=CALL_TIMEOUT,
            )
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                }
                for tool in result.tools
            ]
        except TimeoutError:
            raise MCPConnectionError("获取工具列表超时")
        except Exception as e:
            self._connected = False  # 标记为断开，下次自动重连
            raise MCPConnectionError(
                f"获取工具列表失败: {e!s}"
            ) from e

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict:
        """调用 MCP Server 上注册的工具。

        通过 MCP SDK 的 call_tool 方法向服务器发送工具调用请求，
        支持自动重试机制和超时控制。

        Args:
            tool_name: 要调用的工具名称，对应 server.py 中注册的工具名。
            arguments: 工具参数字典。

        Returns:
            Dict: 工具执行结果。

        Raises:
            MCPConnectionError: 连接异常时抛出。
            MCPToolError: 工具调用返回错误时抛出。
        """
        arguments = arguments or {}

        try:
            await self._ensure_connected()
        except MCPConnectionError:
            # 连接失败，返回降级结果而非崩溃
            logger.warning("[MCPClient] 无法连接，工具 %s 调用降级", tool_name)
            return {
                "success": False,
                "data": {"message": f"MCP 客户端未连接，工具 {tool_name} 调用降级"},
            }

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(tool_name, arguments),
                    timeout=CALL_TIMEOUT,
                )

                # 解析返回内容
                if hasattr(result, "content") and result.content:
                    content = result.content[0]
                    if hasattr(content, "text"):
                        try:
                            parsed = json.loads(content.text)
                            return parsed
                        except json.JSONDecodeError:
                            return {"success": True, "data": {"message": content.text}}
                    return {"success": True, "data": {"raw": str(content)}}

                return {"success": True, "data": {}}

            except TimeoutError:
                last_error = TimeoutError(f"工具 {tool_name} 调用超时")
                logger.warning(
                    "[MCPClient] 调用工具 '%s' 超时（第 %d/%d 次）",
                    tool_name, attempt, self.max_retries,
                )
            except MCPToolError:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    logger.warning(
                        "[MCPClient] 调用工具 '%s' 失败（第 %d/%d 次），"
                        "%.1f 秒后重试: %s",
                        tool_name, attempt, self.max_retries, wait_time, str(e),
                    )
                    await asyncio.sleep(wait_time)
                    # 重试前尝试重连
                    self._connected = False
                    try:
                        await self._ensure_connected()
                    except MCPConnectionError:
                        pass
                continue

        error_msg = (
            f"调用工具 '{tool_name}' 在 {self.max_retries} 次重试后"
            f"仍失败: {last_error}"
        )
        logger.error("[MCPClient] %s", error_msg)
        raise MCPConnectionError(error_msg) from last_error

    async def __aenter__(self) -> "MCPClient":
        """异步上下文管理器入口。

        进入上下文时自动建立连接。

        Returns:
            MCPClient: 已连接的客户端实例。
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """异步上下文管理器出口。

        退出上下文时自动断开连接。

        Args:
            exc_type: 异常类型。
            exc_val: 异常值。
            exc_tb: 异常回溯。
        """
        await self.disconnect()
