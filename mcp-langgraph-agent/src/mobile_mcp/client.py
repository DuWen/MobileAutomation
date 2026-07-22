"""
MCP Client 封装模块

提供 MCPClient 类，通过 MCP SDK 与 MCP Server 通信。
支持 stdio 传输方式，包含错误处理、重试机制
以及连接管理的上下文管理器。
"""

import asyncio
import importlib
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """MCP 客户端异常基类。

    封装所有 MCP 客户端操作中可能出现的异常场景。
    """

    pass


class MCPConnectionError(MCPClientError):
    """MCP 连接异常，表示与服务器的连接出现问题。"""

    pass


class MCPToolError(MCPClientError):
    """MCP 工具调用异常，表示工具执行时返回错误。"""

    def __init__(
        self, message: str, tool_name: str, result: Optional[Dict] = None
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
    提供工具发现和调用功能。

    Attributes:
        server_command: 启动 MCP Server 的命令。
        server_args: 启动 MCP Server 的命令行参数。
        max_retries: 最大重试次数。
        retry_delay: 重试间隔（秒）。
    """

    def __init__(
        self,
        server_command: str = "python",
        server_args: Optional[list] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """初始化 MCP 客户端。

        Args:
            server_command: 启动 MCP Server 的命令，默认为 "python"。
            server_args: 启动 MCP Server 的命令行参数列表。
            max_retries: 调用工具时的最大重试次数，默认为 3。
            retry_delay: 重试间隔时间（秒），默认为 1.0 秒。
        """
        self.server_command = server_command
        self.server_args = server_args or ["-m", "src.mcp.server"]
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 连接状态
        self._session: Optional[Any] = None
        self._read_stream: Optional[Any] = None
        self._write_stream: Optional[Any] = None
        self._connected: bool = False

    async def connect(self) -> None:
        """建立与 MCP Server 的连接。

        通过 stdio 传输方式启动 MCP Server 并建立 ClientSession。

        Raises:
            MCPConnectionError: 连接失败时抛出。
        """
        if self._connected:
            logger.warning("客户端已连接，跳过重复连接")
            return

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command=self.server_command,
                args=self.server_args,
            )

            # 建立 stdio 连接
            self._read_stream, self._write_stream = await self._connect_stdio(
                server_params
            )

            # 创建 ClientSession
            self._session = ClientSession(
                self._read_stream, self._write_stream
            )
            await self._session.__aenter__()

            # 初始化会话
            await self._session.initialize()

            self._connected = True
            logger.info("MCP 客户端已连接")

        except ImportError as e:
            raise MCPConnectionError(
                f"MCP SDK 未安装，请执行 pip install mcp: {str(e)}"
            ) from e
        except Exception as e:
            raise MCPConnectionError(
                f"连接 MCP Server 失败: {str(e)}"
            ) from e

    async def _connect_stdio(self, server_params: Any) -> Any:
        """通过 stdio 方式连接 MCP Server。

        Args:
            server_params: StdioServerParameters 实例。

        Returns:
            (read_stream, write_stream) 元组。
        """
        from mcp.client.stdio import stdio_client

        read_stream, write_stream = await stdio_client(server_params).__aenter__()
        return read_stream, write_stream

    async def disconnect(self) -> None:
        """断开与 MCP Server 的连接。

        清理 ClientSession 和 stdio 连接资源。
        """
        if not self._connected:
            return

        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None

            self._read_stream = None
            self._write_stream = None
            self._connected = False
            logger.info("MCP 客户端已断开连接")

        except Exception as e:
            logger.error("断开连接时发生错误: %s", str(e))
            self._connected = False

    async def list_tools(self) -> list[Dict]:
        """获取 MCP Server 上注册的所有工具列表。

        Returns:
            工具信息字典列表，每个字典包含 name、description 等字段。

        Raises:
            MCPConnectionError: 连接异常时抛出。
        """
        if not self._connected or self._session is None:
            raise MCPConnectionError("客户端未连接，请先调用 connect()")

        try:
            result = await self._session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                }
                for tool in result.tools
            ]
        except Exception as e:
            raise MCPConnectionError(
                f"获取工具列表失败: {str(e)}"
            ) from e

    async def call_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict:
        """调用 MCP Server 上注册的工具。

        通过 MCP SDK 的 call_tool 方法向服务器发送工具调用请求，
        支持自动重试机制。

        Args:
            tool_name: 要调用的工具名称，对应 server.py 中注册的工具名。
            arguments: 工具参数字典。

        Returns:
            Dict: 工具执行结果。

        Raises:
            MCPConnectionError: 连接异常时抛出。
            MCPToolError: 工具调用返回错误时抛出。
        """
        if not self._connected or self._session is None:
            raise MCPConnectionError("客户端未连接，请先调用 connect()")

        arguments = arguments or {}

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._session.call_tool(tool_name, arguments)

                # 解析返回内容
                if hasattr(result, "content") and result.content:
                    # 获取第一个内容项的文本
                    content = result.content[0]
                    if hasattr(content, "text"):
                        try:
                            parsed = json.loads(content.text)
                            return parsed
                        except json.JSONDecodeError:
                            return {"success": True, "data": {"message": content.text}}
                    return {"success": True, "data": {"raw": str(content)}}

                return {"success": True, "data": {}}

            except MCPToolError:
                raise
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    logger.warning(
                        "调用工具 '%s' 失败（第 %d/%d 次），%.1f 秒后重试: %s",
                        tool_name, attempt, self.max_retries, wait_time, str(e),
                    )
                    await asyncio.sleep(wait_time)
                continue

        error_msg = (
            f"调用工具 '{tool_name}' 在 {self.max_retries} 次重试后"
            f"仍失败: {last_error}"
        )
        logger.error(error_msg)
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
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """异步上下文管理器出口。

        退出上下文时自动断开连接。

        Args:
            exc_type: 异常类型。
            exc_val: 异常值。
            exc_tb: 异常回溯。
        """
        await self.disconnect()
