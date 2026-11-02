from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.api.schemas import CamelModel


class DictationConfig(CamelModel):
    mode: Literal["online", "offline"] = "online"
    playback_mode: Literal["auto", "manual"] = "manual"
    interval_seconds: int = Field(default=5, ge=2, le=60)
    hint: Literal["phonetic", "meaning"] = "phonetic"
    repeat_count: int = Field(default=2, ge=1, le=5)


class TaskCreate(CamelModel):
    name: str = Field(min_length=1, max_length=180)
    type: Literal["vocabulary", "dictation"] = "dictation"
    mode: Literal["fixed", "long_term"] = "long_term"
    library_id: str
    selected_entry_ids: list[str] = Field(min_length=1)
    words_per_group: int = Field(default=5, ge=1)
    repeat_until_correct: bool = False
    dictation: DictationConfig | None = None

    @model_validator(mode="after")
    def validate_v1_type(self) -> "TaskCreate":
        if self.type != "dictation":
            raise ValueError("V1 只开放听写任务")
        if self.dictation is None:
            self.dictation = DictationConfig()
        return self


class TaskUpdate(CamelModel):
    name: str = Field(min_length=1, max_length=180)
    words_per_group: int | None = Field(default=None, ge=1)
    repeat_until_correct: bool | None = None
    dictation: DictationConfig | None = None


class SnapshotEntryOut(CamelModel):
    id: str
    word: str
    phonetic: str
    part_of_speech: str
    meanings: list[str]
    example: str
    example_translation: str


class TaskConfigOut(CamelModel):
    question_count: int
    words_per_group: int
    total_groups: int
    repeat_until_correct: bool
    dictation: DictationConfig | None


class TaskOut(CamelModel):
    id: str
    user_id: str
    name: str
    subject: str
    type: Literal["vocabulary", "dictation"]
    mode: Literal["fixed", "long_term"]
    status: Literal["in_progress", "completed"]
    progress: int
    target_count: int
    library_id: str
    library_name: str
    config: TaskConfigOut
    snapshot: list[SnapshotEntryOut]
    created_at: datetime
    updated_at: datetime
