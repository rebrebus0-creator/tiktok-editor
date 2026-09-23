"""Настройки модуля. Читаются из окружения, но всё можно передать явно."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

#: Подхватываем .env из текущей директории или любой родительской.
#: Уже заданные переменные окружения имеют приоритет и не затираются.
DOTENV_PATH: str = find_dotenv(usecwd=True)
load_dotenv(DOTENV_PATH, override=False)


def _env_str(name: str) -> str | None:
    """Значение переменной, где пустая строка и пробелы равны отсутствию.

    Типичный случай: в .env осталась строка `PEXELS_API_KEY=` без значения.
    Без этой нормализации ключ считался бы заданным, и вместо понятного
    «ключ не задан» пользователь ловил бы 401 от сервиса.
    """
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    pexels_api_key: str | None = Field(default_factory=lambda: _env_str("PEXELS_API_KEY"))
    pixabay_api_key: str | None = Field(default_factory=lambda: _env_str("PIXABAY_API_KEY"))
    anthropic_api_key: str | None = Field(default_factory=lambda: _env_str("ANTHROPIC_API_KEY"))

    cache_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("STOCK_MEDIA_CACHE_DIR", "./media_cache"))
    )
    enable_youtube: bool = Field(default_factory=lambda: _env_flag("STOCK_MEDIA_ENABLE_YOUTUBE"))

    request_timeout: float = 30.0
    max_workers: int = 4
    planner_model: str = "claude-opus-5"

    def enabled_providers(self) -> list[str]:
        """Провайдеры, у которых есть всё необходимое для работы."""
        return [name for name, reason in self.provider_status().items() if reason is None]

    def provider_status(self) -> dict[str, str | None]:
        """Каждый известный провайдер -> причина, по которой он выключен.

        `None` означает «работает». Нужно, чтобы CLI мог внятно объяснить,
        почему поиск вернул пустоту, вместо молчаливого списка из одного
        провайдера.
        """
        return {
            "pexels": None if self.pexels_api_key else "не задан PEXELS_API_KEY",
            "pixabay": None if self.pixabay_api_key else "не задан PIXABAY_API_KEY",
            "openverse": None,  # публичный API, ключ не нужен
            "youtube": None if self.enable_youtube else "выключен (STOCK_MEDIA_ENABLE_YOUTUBE=0)",
        }
