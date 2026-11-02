import hashlib
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppError


class LocalFileStorage:
    def __init__(self, root: str, max_bytes: int) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, user_id: str) -> tuple[str, int, str]:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".xlsx", ".csv"}:
            raise AppError("unsupported_file", "仅支持 .xlsx 或 .csv 文件")
        user_dir = self.root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{hashlib.sha256((upload.filename or '').encode()).hexdigest()[:16]}{suffix}"
        target = user_dir / safe_name
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > self.max_bytes:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise AppError("file_too_large", "文件超过大小限制", status_code=413)
                digest.update(chunk)
                output.write(chunk)
        return str(target), size, digest.hexdigest()

    def delete(self, storage_key: str) -> None:
        Path(storage_key).unlink(missing_ok=True)
