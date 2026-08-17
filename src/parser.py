"""Парсер размеченного сценария — ЭТАП 3.

Из script.txt достаём:
  * теги в квадратных скобках и их аргументы;
  * якорный текст вокруг каждого тега (по нему aligner найдёт момент в речи);
  * чистый текст речи без тегов (его сопоставляем с транскриптом).

Имена тегов берутся из config.tags.names — их можно переименовать,
не трогая код.

Каркас: сигнатуры зафиксированы, реализация появится на этапе 3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import Config
from .errors import StagePending
from .models import Tag

log = logging.getLogger(__name__)

STAGE = 3
STAGE_TITLE = "Парсер + выравнивание"


@dataclass
class ScriptDoc:
    """Разобранный сценарий."""

    tags: list[Tag] = field(default_factory=list)
    # Текст речи без тегов — то, что реально будет произнесено.
    speech_text: str = ""
    # Номера абзацев по позиции символа: [ЭКРАН] без стоп-тега живёт до конца абзаца.
    paragraphs: list[str] = field(default_factory=list)


def parse_script(text: str, cfg: Config) -> ScriptDoc:
    """Разбирает размеченный сценарий."""
    raise StagePending(STAGE, STAGE_TITLE, "парсер сценария ещё не реализован")


def parse_duration(token: str) -> float | None:
    """«3с», «3.5s», «2 сек» -> секунды. Не число -> None."""
    raise StagePending(STAGE, STAGE_TITLE, "разбор длительности ещё не реализован")
