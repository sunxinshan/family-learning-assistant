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


def redact(value: Any) -> Any:
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(
            lambda match: f"{match.group(1) or match.group(2)}[REDACTED]", value
        )
    return value
