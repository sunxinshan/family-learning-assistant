from datetime import datetime

from pydantic import Field

from app.api.schemas import CamelModel


class WordEntryIn(CamelModel):
    word: str = Field(min_length=1, max_length=200)
    phonetic: str = ""
    part_of_speech: str = ""
    meanings: list[str] = Field(min_length=1)
    example: str = ""
    example_translation: str = ""


class WordEntryOut(WordEntryIn):
    id: str


class VocabularyCreate(CamelModel):
    subject: str
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    tags: list[str] = []
    entries: list[WordEntryIn] = []
    visibility: str | None = None


class VocabularyUpdate(CamelModel):
    subject: str
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    tags: list[str] = []
    category: str | None = None


class VocabularyOut(CamelModel):
    id: str
    owner_id: str | None
    subject: str
    name: str
    description: str
    tags: list[str]
    visibility: str
    published: bool
    entries: list[WordEntryOut]
    created_at: datetime
    updated_at: datetime


class VocabularyVisibilityUpdate(CamelModel):
    visibility: str


class SubjectOut(CamelModel):
    code: str
    display_name: str
