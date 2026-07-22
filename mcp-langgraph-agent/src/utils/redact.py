"""敏感信息脱敏模块。

提供对日志和输出中的敏感信息进行脱敏处理的功能，
确保在日志记录和调试输出时不会泄露用户隐私数据。
"""

import re
from typing import Dict, List, Tuple


# 敏感信息脱敏规则列表
# 每项为 (正则表达式模式, 替换模板)
_REDACT_RULES: List[Tuple[re.Pattern, str]] = [
    # 手机号（中国大陆）：11位数字，可带 +86 前缀
    (re.compile(r'(?:(?:\+?86)?1[3-9]\d{9})(?!\d)'), '***手机号***'),
    # 邮箱地址
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '***邮箱***'),
    # 密码字段（JSON 格式中的密码值）
    (re.compile(r'"(?:password|passwd|pwd|secret)"\s*:\s*"[^"]+"', re.IGNORECASE), '"***密码***"'),
    # 密码字段（YAML/Toml 格式）
    (re.compile(r'(?:password|passwd|pwd|secret)\s*[:=]\s*[^\s,;\}\]]+', re.IGNORECASE), '***密码***'),
    # 令牌字段（各种 token）
    (re.compile(r'"(?:token|access_token|refresh_token|api_key|apikey|auth_token)"\s*:\s*"[^"]+"', re.IGNORECASE), '"***令牌***"'),
    # 令牌字段（非 JSON 格式）
    (re.compile(r'(?:token|access_token|refresh_token|api_key|apikey|auth_token)\s*[:=]\s*[^\s,;\}\]]+', re.IGNORECASE), '***令牌***'),
    # API Key 格式（如 sk-xxx, api-xxx 等）
    (re.compile(r'\b(?:sk-[a-zA-Z0-9]{20,48}|api-[a-zA-Z0-9]{20,48}|pk-[a-zA-Z0-9]{20,48})\b'), '***API_KEY***'),
    # 身份证号（中国大陆）：18位数字
    (re.compile(r'\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'), '***身份证号***'),
    # 银行卡号：16-19位数字
    (re.compile(r'\b(?:62|60|58|56|55|54|53|52|51|50|49|48|47|46|45|44|43|42|41|40)\d{14,17}\b'), '***银行卡号***'),
    # Bearer Token 认证头
    (re.compile(r'Bearer\s+[a-zA-Z0-9._-]+'), 'Bearer ***令牌***'),
    # Basic 认证头
    (re.compile(r'Basic\s+[a-zA-Z0-9=+/]+'), 'Basic ***认证信息***'),
    # 私钥内容（多行文本中的私钥块）
    (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----'), '***私钥已脱敏***'),
    # URL 中的认证信息（如 https://user:pass@host.com）
    (re.compile(r'(https?://)[^:@/:]+:[^@/:]+@'), r'\1***:***@'),
    # 验证码（6位数字）
    (re.compile(r'\b\d{6}\b(?=\s*(?:验证码|验证|captcha|otp|验证码|验证))\b', re.IGNORECASE), '***验证码***'),
]


def redact_sensitive(text: str) -> str:
    """脱敏处理：将文本中的敏感信息替换为 ***。

    对输入文本应用所有已定义的脱敏规则，依次匹配并替换。
    适用于日志输出前的安全过滤，防止敏感信息泄露。

    Args:
        text: 原始文本，可能包含敏感信息

    Returns:
        脱敏后的安全文本

    Example:
        >>> redact_sensitive("用户手机号是13800138000")
        '用户手机号是***手机号***'
        >>> redact_sensitive("password: my_secret_pwd")
        '***密码***'
    """
    result = text
    for pattern, replacement in _REDACT_RULES:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: Dict, keys_to_redact: List[str] | None = None) -> Dict:
    """对字典中指定键的值进行脱敏处理。

    递归遍历字典，对指定键名（或所有常见敏感键名）的值进行脱敏。
    适用于结构化日志数据的脱敏。

    Args:
        data: 待脱敏的字典数据
        keys_to_redact: 需要脱敏的键名列表。
            如果为 None，则使用默认的敏感键名列表

    Returns:
        脱敏后的字典副本

    Example:
        >>> redact_dict({"user": {"password": "secret123"}})
        {'user': {'password': '***密码***'}}
    """
    # 默认的敏感键名
    sensitive_keys = keys_to_redact or [
        'password', 'passwd', 'pwd', 'secret', 'token',
        'access_token', 'refresh_token', 'api_key', 'apikey',
        'auth_token', 'private_key', 'secret_key',
    ]

    result: Dict = {}
    for key, value in data.items():
        # 检查当前键是否敏感键名
        if isinstance(key, str) and key.lower() in [k.lower() for k in sensitive_keys]:
            result[key] = '***已脱敏***'
        # 递归处理嵌套字典
        elif isinstance(value, dict):
            result[key] = redact_dict(value, keys_to_redact)
        elif isinstance(value, str):
            result[key] = redact_sensitive(value)
        elif isinstance(value, list):
            # 处理列表中的字典和字符串
            result[key] = [
                redact_dict(item, keys_to_redact) if isinstance(item, dict)
                else redact_sensitive(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value

    return result


def add_redact_rule(pattern: str, replacement: str | None = None) -> None:
    """动态添加自定义脱敏规则。

    允许在运行时添加新的脱敏规则，扩展脱敏能力。

    Args:
        pattern: 正则表达式模式字符串
        replacement: 替换文本，默认为 '***自定义***'

    Example:
        >>> add_redact_rule(r'\\bSSN-\\d{9}\\b')
        >>> redact_sensitive("SSN-123456789")
        '***自定义***'
    """
    compiled = re.compile(pattern)
    replacement_text = replacement or '***自定义***'
    _REDACT_RULES.insert(0, (compiled, replacement_text))