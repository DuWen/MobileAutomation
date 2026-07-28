"""设备池管理模块。

管理多设备连接池，支持设备的注册、获取、释放和健康检查。
使用 asyncio.Lock 保证线程安全，支持从 YAML 配置文件加载设备列表。
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DeviceInfo:
    """设备信息。

    描述一个移动设备的基本信息和连接参数。

    Attributes:
        device_id: 设备唯一标识（如 udid）
        name: 设备名称
        platform: 平台类型（android/ios）
        platform_version: 操作系统版本
        host: 设备连接主机地址
        port: Appium 服务端口
        system_port: 系统调试端口
        capabilities: 额外的 Desired Capabilities 配置
        is_connected: 是否已连接
        last_health_check: 最近一次健康检查时间
        is_healthy: 设备是否健康可用
        in_use: 是否正在被使用
        acquired_at: 设备被获取的时间
    """
    device_id: str
    name: str
    platform: str
    platform_version: str = ''
    host: str = '127.0.0.1'
    port: int = 4723
    system_port: int = 8200
    capabilities: dict[str, Any] = field(default_factory=dict)
    is_connected: bool = False
    last_health_check: datetime | None = None
    is_healthy: bool = True
    in_use: bool = False
    acquired_at: datetime | None = None


class DevicePool:
    """设备连接池管理器。

    管理多设备连接池，支持设备注册、获取、释放操作。
    使用 asyncio.Lock 保证线程安全，支持最大池大小限制，
    提供设备健康检查功能，支持从 YAML 配置文件加载设备列表。

    Attributes:
        max_size: 池的最大容量
        devices: 设备字典，以 device_id 为键
        lock: 异步锁，保证线程安全
    """

    def __init__(self, max_size: int = 10) -> None:
        """初始化设备池。

        Args:
            max_size: 池的最大容量，默认 10
        """
        self.max_size: int = max_size
        self.devices: dict[str, DeviceInfo] = {}
        self.lock: asyncio.Lock = asyncio.Lock()

    async def register_device(self, device: DeviceInfo) -> bool:
        """注册设备到设备池。

        将设备添加到池中，如果池已满或设备已存在则注册失败。

        Args:
            device: 设备信息对象

        Returns:
            注册成功返回 True，否则返回 False

        Raises:
            ValueError: 设备信息无效（缺少 device_id）
        """
        if not device.device_id:
            raise ValueError("设备 ID 不能为空")

        async with self.lock:
            # 检查是否已存在
            if device.device_id in self.devices:
                return False

            # 检查池容量
            if len(self.devices) >= self.max_size:
                return False

            # 注册设备
            self.devices[device.device_id] = device
            return True

    async def unregister_device(self, device_id: str) -> bool:
        """从设备池中移除设备。

        Args:
            device_id: 设备唯一标识

        Returns:
            移除成功返回 True，设备不存在返回 False
        """
        async with self.lock:
            if device_id not in self.devices:
                return False
            del self.devices[device_id]
            return True

    async def acquire_device(
        self,
        platform: str | None = None,
        preferred_device_id: str | None = None,
        timeout: float = 30.0,
    ) -> DeviceInfo | None:
        """获取一个可用设备。

        从池中获取一个空闲、健康的设备。如果指定了 preferred_device_id，
        则优先获取该设备。支持按平台过滤。

        Args:
            platform: 可选的平台过滤条件（android/ios）
            preferred_device_id: 优先获取的设备 ID
            timeout: 等待可用设备的超时时间（秒），默认 30 秒

        Returns:
            可用的设备信息，如果超时或没有可用设备则返回 None
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < timeout:
            async with self.lock:
                # 如果指定了优先设备，先尝试获取
                if preferred_device_id and preferred_device_id in self.devices:
                    device = self.devices[preferred_device_id]
                    if not device.in_use and device.is_healthy and device.is_connected:
                        # 检查平台匹配
                        if platform is None or device.platform == platform:
                            device.in_use = True
                            device.acquired_at = datetime.now()
                            return device

                # 查找第一个空闲、健康的设备
                for device in self.devices.values():
                    if not device.in_use and device.is_healthy and device.is_connected:
                        if platform is None or device.platform == platform:
                            device.in_use = True
                            device.acquired_at = datetime.now()
                            return device

            # 没有可用设备，等待一段时间后重试
            await asyncio.sleep(1.0)

        return None

    async def release_device(self, device_id: str) -> bool:
        """释放设备，将其归还到设备池。

        Args:
            device_id: 设备唯一标识

        Returns:
            释放成功返回 True，设备不存在或未被使用返回 False
        """
        async with self.lock:
            if device_id not in self.devices:
                return False

            device = self.devices[device_id]
            if not device.in_use:
                return False

            # 释放设备
            device.in_use = False
            device.acquired_at = None
            return True

    async def health_check(self, device_id: str) -> bool:
        """对指定设备执行健康检查。

        检查设备连接状态，更新健康状态和时间戳。
        当前实现为模拟检查，实际使用时需要替换为真实的
        Appium 连接检查逻辑。

        Args:
            device_id: 设备唯一标识

        Returns:
            设备健康返回 True，否则返回 False
        """
        async with self.lock:
            if device_id not in self.devices:
                return False

            device = self.devices[device_id]
            device.last_health_check = datetime.now()

            try:
                # 模拟健康检查 - 实际使用时替换为真实的连接检查
                # 例如：发送 Appium 健康检查请求
                is_healthy = await self._check_device_connectivity(device)
                device.is_healthy = is_healthy
                device.is_connected = is_healthy
                return is_healthy
            except Exception:  # noqa: BLE001
                device.is_healthy = False
                device.is_connected = False
                return False

    async def health_check_all(self) -> dict[str, bool]:
        """对所有设备执行健康检查。

        Returns:
            设备 ID 到健康状态的映射字典
        """
        results: dict[str, bool] = {}
        # 获取所有设备 ID 的快照
        async with self.lock:
            device_ids = list(self.devices.keys())

        for device_id in device_ids:
            results[device_id] = await self.health_check(device_id)

        return results

    async def get_available_devices(self, platform: str | None = None) -> list[DeviceInfo]:
        """获取当前可用的设备列表。

        Args:
            platform: 可选的平台过滤条件

        Returns:
            可用设备列表
        """
        async with self.lock:
            available = []
            for device in self.devices.values():
                if not device.in_use and device.is_healthy and device.is_connected:
                    if platform is None or device.platform == platform:
                        available.append(device)
            return available

    async def get_device_count(self) -> dict[str, int]:
        """获取设备池的统计信息。

        Returns:
            包含各状态设备数量的字典
        """
        async with self.lock:
            total = len(self.devices)
            in_use = sum(1 for d in self.devices.values() if d.in_use)
            healthy = sum(1 for d in self.devices.values() if d.is_healthy)
            connected = sum(1 for d in self.devices.values() if d.is_connected)
            android = sum(1 for d in self.devices.values() if d.platform == 'android')
            ios = sum(1 for d in self.devices.values() if d.platform == 'ios')

            return {
                'total': total,
                'in_use': in_use,
                'idle': total - in_use,
                'healthy': healthy,
                'unhealthy': total - healthy,
                'connected': connected,
                'disconnected': total - connected,
                'android': android,
                'ios': ios,
                'max_size': self.max_size,
            }

    async def load_from_yaml(self, yaml_path: str) -> int:
        """从 YAML 配置文件加载设备列表。

        注意：当前实现使用 JSON 格式替代 YAML。
        如需 YAML 支持，请安装 PyYAML 依赖。

        Args:
            yaml_path: YAML 配置文件路径

        Returns:
            成功加载的设备数量
        """

        loaded_count = 0
        try:
            # 先尝试以 JSON 格式读取
            with open(yaml_path, encoding='utf-8') as f:
                content = f.read().strip()

            # 尝试解析 JSON
            try:
                config = json.loads(content)
            except json.JSONDecodeError:
                # 如果不是 JSON，尝试使用 yaml 解析
                try:
                    import yaml
                    config = yaml.safe_load(content)
                except ImportError:
                    raise ImportError("需要安装 PyYAML 来解析 YAML 文件: pip install pyyaml")

            devices_config = config.get('devices', [])
            for device_cfg in devices_config:
                device = DeviceInfo(
                    device_id=device_cfg.get('device_id', ''),
                    name=device_cfg.get('name', ''),
                    platform=device_cfg.get('platform', 'android'),
                    platform_version=device_cfg.get('platform_version', ''),
                    host=device_cfg.get('host', '127.0.0.1'),
                    port=device_cfg.get('port', 4723),
                    system_port=device_cfg.get('system_port', 8200),
                    capabilities=device_cfg.get('capabilities', {}),
                    is_connected=True,
                    is_healthy=True,
                )
                if await self.register_device(device):
                    loaded_count += 1

            return loaded_count

        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件不存在: {yaml_path}")
        except Exception as e:
            raise RuntimeError(f"加载设备配置失败: {e}") from e

    async def _check_device_connectivity(self, device: DeviceInfo) -> bool:
        """检查设备连接性（模拟实现）。

        实际使用时，此方法应发送 Appium 请求验证设备是否可达。
        当前实现为模拟，始终返回 True。

        Args:
            device: 设备信息

        Returns:
            设备可达返回 True
        """
        # 模拟连接检查 - 实际使用时替换为 Appium 连接验证
        await asyncio.sleep(0.1)
        return True

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """直接获取设备信息（非线程安全）。

        仅用于读取设备信息，不涉及设备获取/释放操作。

        Args:
            device_id: 设备唯一标识

        Returns:
            设备信息，如果不存在则返回 None
        """
        return self.devices.get(device_id)
