"""Доменные модели: то, чем модуль обменивается с внешним кодом.

Это единственный контракт, который видит основной софт. Провайдеры,
планировщик и ранжирование — внутренняя кухня, их можно менять свободно,
пока эти модели остаются прежними.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class MediaKind(str, Enum):
    VIDEO = "video"
    PHOTO = "photo"


class Orientation(str, Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    SQUARE = "square"
    ANY = "any"


class SearchQuery(BaseModel):
    """Один конкретный поисковый запрос к провайдерам.

    Планировщик превращает текст сценария в список таких запросов.
    """

    text: str
    kind: MediaKind = MediaKind.VIDEO
    orientation: Orientation = Orientation.PORTRAIT
    min_duration: float | None = Field(default=None, description="сек, только для видео")
    max_duration: float | None = Field(default=None, description="сек, только для видео")
    limit: int = 10
    # Кусок сценария, под который ищем. Нужен для ранжирования и отладки.
    scene_hint: str | None = None


class MediaAsset(BaseModel):
    """Найденный медиафайл. `local_path` заполняется после скачивания."""

    provider: str
    provider_id: str
    kind: MediaKind
    url: HttpUrl
    preview_url: HttpUrl | None = None
    width: int
    height: int
    duration: float | None = None
    author: str | None = None
    source_page: HttpUrl | None = None
    license: str | None = None
    tags: list[str] = Field(default_factory=list)
    query: SearchQuery | None = None

    #: произвольные данные провайдера (например, таймкоды фрагмента YouTube)
    extra: dict[str, Any] = Field(default_factory=dict)

    local_path: Path | None = None
    sha256: str | None = None
    score: float = 0.0

    @property
    def uid(self) -> str:
        return f"{self.provider}:{self.provider_id}"

    @property
    def orientation(self) -> Orientation:
        if self.width == self.height:
            return Orientation.SQUARE
        return Orientation.PORTRAIT if self.height > self.width else Orientation.LANDSCAPE
