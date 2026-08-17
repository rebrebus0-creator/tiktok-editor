"""Генерация караоке-субтитров .ass — ЭТАП 2.

Из слов с таймкодами собираем плашки по 2-3 слова, внутри плашки текущее
слово подсвечивается (ASS-тег \\k). Стиль (шрифт, размер, цвета, положение)
берётся из config.subtitles, файл шрифта — из assets/fonts (передаётся
в FFmpeg через `fontsdir`).

Каркас: сигнатуры зафиксированы, реализация появится на этапе 2.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .errors import StagePending
from .models import Word

log = logging.getLogger(__name__)

STAGE = 2
STAGE_TITLE = "Караоке-субтитры"


def group_words(words: list[Word], cfg: Config) -> list[list[Word]]:
    """Разбивает поток слов на плашки субтитров."""
    raise StagePending(STAGE, STAGE_TITLE, "группировка слов ещё не реализована")


def build_ass(words: list[Word], out_path: Path, cfg: Config) -> Path:
    """Пишет .ass с караоке-подсветкой. Таймкоды — уже финальные."""
    raise StagePending(STAGE, STAGE_TITLE, "генерация .ass ещё не реализована")


def to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR& (в ASS порядок байтов обратный)."""
    raise StagePending(STAGE, STAGE_TITLE, "конвертация цвета ещё не реализована")
