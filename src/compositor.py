"""Сборка ролика через FFmpeg — ЭТАПЫ 4 и 5.

Что делает:
  * приводит всё к 1080x1920 и единому fps;
  * [ЭКРАН]  — вписывает горизонтальный скринкаст в вертикальный кадр
               (размытая подложка из самого кадра или поля);
  * [ВСТАВКА]— overlay PNG с альфа-каналом на интервале;
  * [ЗВУК]   — adelay + amix в нужной точке;
  * [МУЗЫКА] — фон с автодакингом под голос (sidechaincompress);
  * [ЗУМ]    — плавный наезд;
  * вшивает караоке-субтитры (libass) и экспортирует финал.

Каркас: сигнатуры зафиксированы, реализация появится на этапах 4-5.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .errors import StagePending
from .models import Event

log = logging.getLogger(__name__)

STAGE = 4
STAGE_TITLE = "Композитинг"


def normalize_source(src: Path, out_path: Path, cfg: Config) -> Path:
    """Приводит любой источник к целевому разрешению/fps/пиксельному формату.

    Без этого concat ломает склейку и рассинхронивает звук.
    """
    raise StagePending(STAGE, STAGE_TITLE, "нормализация источников ещё не реализована")


def burn_subtitles(video: Path, ass_path: Path, out_path: Path, cfg: Config) -> Path:
    """Вшивает .ass в видео фильтром subtitles (libass) с указанием fontsdir."""
    raise StagePending(2, "Караоке-субтитры", "вшивание субтитров ещё не реализовано")


def compose(
    video: Path,
    events: list[Event],
    out_path: Path,
    cfg: Config,
    *,
    ass_path: Path | None = None,
) -> Path:
    """Собирает финальный ролик: оверлеи, звук, музыка с дакингом, субтитры, экспорт."""
    raise StagePending(STAGE, STAGE_TITLE, "композитинг ещё не реализован")
