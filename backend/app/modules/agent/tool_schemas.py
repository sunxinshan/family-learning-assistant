"""Tool Calling 的参数 Schema。

字段使用 snake_case，直接作为 Provider function calling 的 JSON Schema。
注意：不包含 user_id / role 等可信身份字段，身份统一由 Executor 注入。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskCreatePreviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=180, description="学习任务名称")
    library_id: str = Field(description="词库 ID，必须来自系统提供的可用词库列表")
    selection_mode: Literal["all", "prefix", "range", "ids"] = Field(
        default="all",
        description="词条选择方式：全部、前 N 个、序号区间、指定 ID",
    )
    prefix_count: int | None = Field(
        default=None, ge=1, description="selection_mode=prefix 时的数量"
    )
    range_start: int | None = Field(
        default=None, ge=1, description="selection_mode=range 时的起始序号"
    )
    range_end: int | None = Field(
        default=None, ge=1, description="selection_mode=range 时的结束序号"
    )
    entry_ids: list[str] = Field(
        default_factory=list, description="selection_mode=ids 时的词条 ID"
    )
    task_mode: Literal["fixed", "long_term"] = Field(
        default="fixed", description="fixed 固定任务，long_term 长期任务"
    )
    words_per_group: int | None = Field(
        default=None, ge=1, description="长期任务每组词数；固定任务忽略"
    )
    repeat_until_correct: bool = Field(default=False, description="是否开启强制重做")
    dictation_mode: Literal["online", "offline"] = Field(
        default="online", description="线上/线下听写"
    )
    playback_mode: Literal["manual", "auto"] = Field(
        default="manual", description="手动/自动播放"
    )
    interval_seconds: int = Field(default=8, ge=2, le=60, description="自动播放间隔秒数")
    hint: Literal["phonetic", "meaning"] = Field(default="phonetic", description="朗读提示内容")
    repeat_count: int = Field(default=2, ge=1, le=5, description="每次朗读次数")
    speech_enabled: bool = Field(default=True, description="是否开启朗读")

    @field_validator("name", "library_id")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value
