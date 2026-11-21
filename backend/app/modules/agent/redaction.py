import re
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|authorization|token|cookie|password|passwd|secret|credential)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(Bearer\s+)[A-Za-z0-9._~+/=-]+|(sk-)[A-Za-z0-9_-]+",
    re.IGNORECASE,
)


def redact(value: Any, *, allow_keys: frozenset[str] | set[str] | None = None) -> Any:
    """递归脱敏。

    allow_keys 用于放行“名字像凭证、实际是业务数据”的键，例如 token_usage
    （只统计 token 用量，不含任何凭证）。默认不放行，行为与之前一致。
    """
    allowed = {str(key).lower() for key in allow_keys} if allow_keys else set()

    def walk(node: Any, trusted: bool = False) -> Any:
        if isinstance(node, list):
            return [walk(item, trusted) for item in node]
        if isinstance(node, dict):
            result: dict[Any, Any] = {}
            for key, item in node.items():
                name = str(key).lower()
                if trusted or name in allowed or not _SENSITIVE_KEY.search(name):
                    result[key] = walk(item, trusted or name in allowed)
                else:
                    result[key] = "[REDACTED]"
            return result
        if isinstance(node, str):
            return _SENSITIVE_VALUE.sub(
                lambda match: f"{match.group(1) or match.group(2)}[REDACTED]", node
            )
        return node

    return walk(value)
