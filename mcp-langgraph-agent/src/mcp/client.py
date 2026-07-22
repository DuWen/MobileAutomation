"""
MCP Client 封装模块

提供 MCPClient 类，通过 JSON-RPC 协议与 MCP Server 通信。
支持 stdio 和 http 两种传输方式，包含错误处理、重试机制
以及连接管理的上下文管理器。
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aiohttp

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
    """MCP 客户端，通过 JSON-RPC 协议与 MCP Server 通信。

    支持 stdio（子进程管道）和 http（HTTP 服务）两种传输方式。
    提供异步调用工具、连接管理和重试机制。

    Attributes:
        transport: 传输方式，可选 "stdio" 或 "http"。
        server_url: HTTP 传输方式下的服务器 URL。
        max_retries: 最大重试次数。
        retry_delay: 重试间隔（秒）。
    """

    def __init__(
        self,
        transport: str = "stdio",
        server_url: str = "http://localhost:8000",
        command: str = "python",
        args: Optional[list] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """初始化 MCP 客户端。

        Args:
            transport: 传输方式，可选 "stdio"（子进程）或 "http"（HTTP 服务）。
                默认为 "stdio"。
            server_url: HTTP 传输方式下的服务器基础 URL，默认为 "http://localhost:8000"。
            command: stdio 传输方式下启动子进程的命令，默认为 "python"。
            args: stdio 传输方式下启动子进程的命令行参数列表。
            max_retries: 调用工具时的最大重试次数，默认为 3。
            retry_delay: 重试间隔时间（秒），默认为 1.0 秒。
        """
        self.transport = transport
        self.server_url = server_url.rstrip("/")
        self.command = command
        self.args = args or []
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # stdio 传输内部状态
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stdin: Optional[asyncio.StreamWriter] = None
        self._stdout: Optional[asyncio.StreamReader] = None
        self._request_id: int = 0

        # HTTP 传输内部状态
        self._session: Optional[aiohttp.ClientSession] = None

        # 连接状态标志
        self._connected: bool = False

    async def connect(self) -> None:
        """建立与 MCP Server 的连接。

        根据传输方式选择连接策略：
        - stdio: 启动子进程并通过标准输入/输出通信。
        - http: 创建 aiohttp 会话。

        Raises:
            MCPConnectionError: 连接失败时抛出。
        """
        if self._connected:
            logger.warning("客户端已连接，跳过重复连接")
            return

        try:
            if self.transport == "stdio":
                await self._connect_stdio()
            elif self.transport == "http":
                await self._connect_http()
            else:
                raise MCPConnectionError(
                    f"不支持的传输方式: {self.transport}"
                )

            self._connected = True
            logger.info(
                "MCP 客户端已连接（传输方式: %s）", self.transport
            )

        except Exception as e:
            raise MCPConnectionError(
                f"连接 MCP Server 失败: {str(e)}"
            ) from e

    async def _connect_stdio(self) -> None:
        """内部方法：通过 stdio 方式连接 MCP Server。

        启动一个子进程运行 MCP Server，并绑定标准输入/输出流。
        """
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._stdin = self._process.stdin
        self._stdout = self._process.stdout

        if self._stdin is None or self._stdout is None:
            raise MCPConnectionError("无法创建子进程的 stdio 管道")

        logger.debug(
            "stdio 子进程已启动: %s %s", self.command, " ".join(self.args)
        )

    async def _connect_http(self) -> None:
        """内部方法：通过 HTTP 方式连接 MCP Server。

        创建 aiohttp 客户端会话，用于后续的 HTTP 请求。
        """
        self._session = aiohttp.ClientSession()
        logger.debug("HTTP 会话已创建，服务器 URL: %s", self.server_url)

    async def disconnect(self) -> None:
        """断开与 MCP Server 的连接。

        清理资源：
        - stdio: 关闭子进程的 stdin，等待子进程退出。
        - http: 关闭 aiohttp 会话。
        """
        if not self._connected:
            return

        try:
            if self.transport == "stdio":
                await self._disconnect_stdio()
            elif self.transport == "http":
                await self._disconnect_http()

            self._connected = False
            logger.info("MCP 客户端已断开连接")

        except Exception as e:
            logger.error("断开连接时发生错误: %s", str(e))
            self._connected = False

    async def _disconnect_stdio(self) -> None:
        """内部方法：断开 stdio 连接。

        关闭子进程的 stdin 流，等待进程退出。
        """
        if self._stdin:
            try:
                self._stdin.close()
            except Exception:
                pass

        if self._process and self._process.returncode is None:
            try:
                # 等待进程退出，设置超时
                await asyncio.wait_for(
                    self._process.wait(), timeout=5.0
                )
            except asyncio.TimeoutError:
                # 超时则强制终止
                self._process.kill()
                await self._process.wait()

        self._process = None
        self._stdin = None
        self._stdout = None

    async def _disconnect_http(self) -> None:
        """内部方法：断开 HTTP 连接。

        关闭 aiohttp 客户端会话。
        """
        if self._session:
            await self._session.close()
            self._session = None

    async def call_tool(
        self, tool_name: str, **kwargs: Any
    ) -> Dict:
        """调用 MCP Server 上注册的工具。

        通过 JSON-RPC 协议向服务器发送工具调用请求，
        支持自动重试机制。

        Args:
            tool_name: 要调用的工具名称，对应 server.py 中注册的工具名。
            **kwargs: 工具的参数，以关键字参数形式传入。

        Returns:
            Dict: 工具执行结果，格式为 {"success": bool, "data": {...}}。

        Raises:
            MCPConnectionError: 连接异常时抛出。
            MCPToolError: 工具调用返回错误时抛出。
        """
        if not self._connected:
            raise MCPConnectionError("客户端未连接，请先调用 connect()")

        # 构造 JSON-RPC 请求
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": kwargs,
            },
            "id": self._request_id,
        }

        # 执行调用（带重试）
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if self.transport == "stdio":
                    result = await self._call_stdio(request)
                elif self.transport == "http":
                    result = await self._call_http(request)
                else:
                    raise MCPConnectionError(
                        f"不支持的传输方式: {self.transport}"
                    )

                # 检查 JSON-RPC 响应中是否有错误
                if "error" in result and result["error"] is not None:
                    error_info = result["error"]
                    raise MCPToolError(
                        message=(
                            f"工具 '{tool_name}' 调用失败: "
                            f"{error_info.get('message', '未知错误')}"
                        ),
                        tool_name=tool_name,
                        result=result,
                    )

                # 返回结果中的 result 字段
                return result.get("result", result)

            except MCPToolError:
                # 工具错误不重试，直接抛出
                raise
            except (MCPConnectionError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    logger.warning(
                        "调用工具 '%s' 失败（第 %d/%d 次），"
                        "%.1f 秒后重试: %s",
                        tool_name,
                        attempt,
                        self.max_retries,
                        wait_time,
                        str(e),
                    )
                    await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    logger.warning(
                        "调用工具 '%s' 出现异常（第 %d/%d 次）: %s",
                        tool_name,
                        attempt,
                        self.max_retries,
                        str(e),
                    )
                    await asyncio.sleep(self.retry_delay)
                continue

        # 所有重试均失败
        error_msg = (
            f"调用工具 '{tool_name}' 在 {self.max_retries} 次重试后"
            f"仍失败: {last_error}"
        )
        logger.error(error_msg)
        raise MCPConnectionError(error_msg) from last_error

    async def _call_stdio(self, request: Dict) -> Dict:
        """内部方法：通过 stdio 发送 JSON-RPC 请求并接收响应。

        Args:
            request: JSON-RPC 请求字典。

        Returns:
            Dict: JSON-RPC 响应字典。

        Raises:
            MCPConnectionError: 读写子进程管道失败时抛出。
        """
        if self._stdin is None or self._stdout is None:
            raise MCPConnectionError("stdio 管道未初始化")

        try:
            # 发送请求（JSON 格式，以换行符结尾）
            request_str = json.dumps(request, ensure_ascii=False) + "\n"
            self._stdin.write(request_str.encode("utf-8"))
            await self._stdin.drain()

            # 读取响应（JSON 格式，以换行符结尾）
            response_line = await asyncio.wait_for(
                self._stdout.readline(), timeout=30.0
            )

            if not response_line:
                raise MCPConnectionError(
                    "从子进程读取到空响应，可能进程已退出"
                )

            response = json.loads(response_line.decode("utf-8"))
            return response

        except asyncio.TimeoutError:
            raise MCPConnectionError("等待 MCP 响应超时（30 秒）")
        except json.JSONDecodeError as e:
            raise MCPConnectionError(
                f"解析 MCP 响应 JSON 失败: {str(e)}"
            )

    async def _call_http(self, request: Dict) -> Dict:
        """内部方法：通过 HTTP 发送 JSON-RPC 请求并接收响应。

        Args:
            request: JSON-RPC 请求字典。

        Returns:
            Dict: JSON-RPC 响应字典。

        Raises:
            MCPConnectionError: HTTP 请求失败时抛出。
        """
        if self._session is None:
            raise MCPConnectionError("HTTP 会话未初始化")

        try:
            url = f"{self.server_url}/mcp"
            async with self._session.post(
                url,
                json=request,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise MCPConnectionError(
                        f"MCP Server 返回 HTTP {response.status}: "
                        f"{error_text}"
                    )

                result = await response.json()
                return result

        except asyncio.TimeoutError:
            raise MCPConnectionError("HTTP 请求 MCP Server 超时（30 秒）")
        except aiohttp.ClientError as e:
            raise MCPConnectionError(
                f"HTTP 请求 MCP Server 失败: {str(e)}"
            )

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