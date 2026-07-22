"""
全局配置模块

使用 Pydantic Settings 从环境变量和 .env 文件中加载配置。
所有配置项均有默认值，支持通过环境变量覆盖。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局应用配置类

    从环境变量和 .env 文件加载所有配置项。
    配置项按功能模块分组：应用基础、LLM、MCP Server、Appium、设备池、Redis、PostgreSQL、Skills、日志。
    """

    # ------------------------------------------------------------
    # 应用基础配置
    # ------------------------------------------------------------
    APP_NAME: str = "mcp-langgraph-agent"
    """应用名称"""
    APP_VERSION: str = "0.1.0"
    """应用版本号"""
    DEBUG: bool = False
    """是否开启调试模式"""

    # ------------------------------------------------------------
    # LLM 配置
    # ------------------------------------------------------------
    LLM_PROVIDER: str = "openai"
    """LLM 提供商，可选值：openai / anthropic"""
    LLM_API_KEY: str = ""
    """LLM API 密钥"""
    LLM_MODEL: str = "gpt-4o"
    """LLM 模型名称"""
    LLM_MAX_TOKENS: int = 4096
    """LLM 每次请求的最大 token 数"""
    LLM_TEMPERATURE: float = 0.7
    """LLM 采样温度参数"""

    # ------------------------------------------------------------
    # MCP Server 配置
    # ------------------------------------------------------------
    MCP_SERVER_HOST: str = "0.0.0.0"
    """MCP Server 监听地址"""
    MCP_SERVER_PORT: int = 8000
    """MCP Server 监听端口"""
    MCP_TRANSPORT: str = "stdio"
    """MCP 传输层协议，可选值：stdio / http"""

    # ------------------------------------------------------------
    # Appium 配置
    # ------------------------------------------------------------
    APPIUM_HOST: str = "127.0.0.1"
    """Appium Server 地址"""
    APPIUM_PORT: int = 4723
    """Appium Server 端口"""
    APPIUM_BASE_PATH: str = "/wd/hub"
    """Appium 基础路径"""

    # ------------------------------------------------------------
    # 设备池配置
    # ------------------------------------------------------------
    DEVICE_POOL_SIZE: int = 2
    """设备池最大并发设备数"""
    DEVICE_CONFIG_PATH: str = "src/config/devices.yaml"
    """设备池配置文件路径"""

    # ------------------------------------------------------------
    # Redis 配置
    # ------------------------------------------------------------
    REDIS_HOST: str = "127.0.0.1"
    """Redis 服务器地址"""
    REDIS_PORT: int = 6379
    """Redis 服务器端口"""
    REDIS_PASSWORD: str = ""
    """Redis 密码（为空时不使用密码认证）"""

    # ------------------------------------------------------------
    # PostgreSQL 配置
    # ------------------------------------------------------------
    POSTGRES_HOST: str = "127.0.0.1"
    """PostgreSQL 服务器地址"""
    POSTGRES_PORT: int = 5432
    """PostgreSQL 服务器端口"""
    POSTGRES_DB: str = "mcp_agent"
    """PostgreSQL 数据库名称"""
    POSTGRES_USER: str = "postgres"
    """PostgreSQL 用户名"""
    POSTGRES_PASSWORD: str = ""
    """PostgreSQL 密码"""

    # ------------------------------------------------------------
    # Skills 配置
    # ------------------------------------------------------------
    SKILLS_DIR: str = "skills"
    """技能（Skills）目录路径"""

    # ------------------------------------------------------------
    # 日志配置
    # ------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    """日志级别，可选值：DEBUG / INFO / WARNING / ERROR / CRITICAL"""
    LOG_FORMAT: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}"
    """日志输出格式（loguru 格式）"""

    # Pydantic Settings 配置：从 .env 文件加载，忽略未识别的额外字段
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 全局单例配置实例
settings = Settings()