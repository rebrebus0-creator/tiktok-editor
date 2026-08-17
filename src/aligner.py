"""Выравнивание сценарий ↔ транскрипт — ЭТАП 3. Ключевой узел проекта.

Пользователь не проставляет таймкоды: он ставит тег рядом с фразой, а мы сами
находим, на какой секунде эта фраза произнесена.

Речь ≠ сценарию дословно (импровизация, оговорки), поэтому сопоставляем
последовательности нормализованных слов (`difflib.SequenceMatcher`):
нижний регистр, без пунктуации, ё → е.

Если якорь не нашёлся — ставим тег по ближайшему совпадению и пишем
предупреждение в лог. Падать нельзя.

Каркас: сигнатуры зафиксированы, реализация появится на этапе 3.
"""

from __future__ import annotations

import logging

from .config import Config
from .errors import StagePending
from .models import Tag, Transcript
from .parser import ScriptDoc

log = logging.getLogger(__name__)

STAGE = 3
STAGE_TITLE = "Парсер + выравнивание"


def normalize(text: str) -> str:
    """Приводит текст к виду для сравнения: нижний регистр, без пунктуации, ё→е."""
    raise StagePending(STAGE, STAGE_TITLE, "нормализация текста ещё не реализована")


def align(doc: ScriptDoc, transcript: Transcript, cfg: Config) -> list[Tag]:
    """Проставляет каждому тегу `src_time` — секунду на исходном таймлайне."""
    raise StagePending(STAGE, STAGE_TITLE, "выравнивание ещё не реализовано")
