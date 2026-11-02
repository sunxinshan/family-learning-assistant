import hashlib
import string
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import AppError


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    content: str
    content_hash: str
    variables: tuple[str, ...]

    def render(self, values: dict[str, str]) -> str:
        missing = sorted(set(self.variables) - set(values))
        if missing:
            raise AppError(
                "prompt_missing_variables",
                f"Prompt 缺少变量：{', '.join(missing)}",
                status_code=500,
            )
        try:
            return self.content.format_map(values)
        except (KeyError, ValueError) as exc:
            raise AppError("prompt_render_failed", "Prompt 变量格式错误", status_code=500) from exc


class PromptRegistry:
    def __init__(self, prompt_dir: Path) -> None:
        self.prompt_dir = Path(prompt_dir)

    def get(self, prompt_id: str, version: str = "v1") -> PromptTemplate:
        if not prompt_id.replace("_", "").replace("-", "").isalnum():
            raise AppError("invalid_prompt_id", "Prompt 标识无效", status_code=500)
        path = self.prompt_dir / f"{prompt_id}.txt"
        if not path.is_file():
            raise AppError("prompt_not_found", f"Prompt 不存在：{prompt_id}", status_code=500)
        content = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        variables = tuple(
            sorted(
                {
                    field_name
                    for _, field_name, _, _ in string.Formatter().parse(content)
                    if field_name
                }
            )
        )
        return PromptTemplate(prompt_id, version, content, digest, variables)
