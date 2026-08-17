"""Транскрипция исходного видео (faster-whisper) — ЭТАП 1.

Задача модуля: получить список слов с таймкодами на ИСХОДНОМ таймлайне.
От этого зависит всё остальное — и субтитры, и привязка тегов к речи,
поэтому запускается с `word_timestamps=True`.

Каркас: сигнатуры зафиксированы, реализация появится на этапе 1.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .errors import StagePending
from .models import Transcript

log = logging.getLogger(__name__)

STAGE = 1
STAGE_TITLE = "Транскрипция + авторез"


def transcribe(
    video: Path,
    cfg: Config,
    *,
    cache_path: Path | None = None,
    force: bool = False,
) -> Transcript:
    """Распознаёт речь и возвращает слова с таймкодами.

    video      — исходное видео из raw/
    cache_path — куда класть/откуда брать готовый транскрипт (.cache/transcript.json)
    force      — игнорировать кэш и распознать заново
    """
    raise StagePending(STAGE, STAGE_TITLE, "распознавание речи ещё не подключено")


def load_cached(cache_path: Path) -> Transcript | None:
    """Читает транскрипт из кэша, если он есть и не битый."""
    if not cache_path.is_file():
        return None
    try:
        return Transcript.load(cache_path)
    except Exception as exc:  # кэш — вещь одноразовая, битый просто игнорируем
        log.warning("кэш транскрипта не читается (%s) — распознаю заново", exc)
        return None
