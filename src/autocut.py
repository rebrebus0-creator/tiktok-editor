"""Детект тишины и вырезание пауз — ЭТАП 1.

Логика:
  1. FFmpeg `silencedetect` находит интервалы тишины;
  2. интервалы, защищённые тегом [ПАУЗА], из вырезания исключаются;
  3. вокруг речи оставляем padding, чтобы не срубить начало слова;
  4. слишком короткие огрызки склеиваем с соседями.

Каркас: сигнатуры зафиксированы, реализация появится на этапе 1.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .errors import StagePending
from .models import KeepSegment

log = logging.getLogger(__name__)

STAGE = 1
STAGE_TITLE = "Транскрипция + авторез"


def detect_silence(video: Path, cfg: Config) -> list[tuple[float, float]]:
    """Интервалы тишины (start, end) по данным FFmpeg silencedetect."""
    raise StagePending(STAGE, STAGE_TITLE, "детект тишины ещё не подключён")


def plan_keep_segments(
    silences: list[tuple[float, float]],
    total_duration: float,
    cfg: Config,
    *,
    protected: list[float] | None = None,
) -> list[KeepSegment]:
    """Считает, какие куски исходника остаются в ролике.

    protected — таймкоды тегов [ПАУЗА]: тишина, накрывающая такую точку,
    не вырезается (обрезается лишь до protected_pause_max).
    """
    raise StagePending(STAGE, STAGE_TITLE, "планирование нарезки ещё не реализовано")


def render_cut(video: Path, segments: list[KeepSegment], out_path: Path, cfg: Config) -> Path:
    """Режет и склеивает куски речи в одно видео без пауз.

    Все сегменты приводятся к одному fps/разрешению до concat — иначе
    склейка рассинхронит звук.
    """
    raise StagePending(STAGE, STAGE_TITLE, "нарезка и склейка ещё не реализованы")
