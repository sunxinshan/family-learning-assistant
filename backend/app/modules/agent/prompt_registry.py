import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    content: str
    content_hash: str


class PromptRegistry:
    def __init__(self, prompt_dir: Path) -> None:
        self.prompt_dir = Path(prompt_dir)

    def get(self, prompt_id: str, version: str = "v1") -> PromptTemplate:
        path = self.prompt_dir / f"{prompt_id}.txt"
        content = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return PromptTemplate(prompt_id, version, content, digest)
