"""Единые исключения пайплайна.

Правило проекта: на несовпадении тега / отсутствующем ассете НЕ падаем —
пишем предупреждение в лог и продолжаем. Исключения ниже — только для
ситуаций, когда продолжать физически нечем (нет FFmpeg, нет исходного видео).
"""

from __future__ import annotations


class EditorError(Exception):
    """Базовая ошибка монтажёра. Ловится в CLI и печатается без стектрейса."""


class ProjectError(EditorError):
    """Проблема со структурой проекта: нет raw/, нет script.txt, несколько исходников."""


class ConfigError(EditorError):
    """Некорректный config.toml."""


class FFmpegError(EditorError):
    """FFmpeg вернул ненулевой код возврата."""


class FFmpegNotFound(FFmpegError):
    """FFmpeg или ffprobe не найдены в PATH."""


class StagePending(EditorError):
    """Этап пайплайна ещё не реализован (заглушка каркаса).

    Используется только на время поэтапной сборки: CLI ловит её и печатает
    понятное сообщение, какой этап нужно собрать следующим.
    """

    def __init__(self, stage: int, title: str, detail: str = "") -> None:
        self.stage = stage
        self.title = title
        self.detail = detail
        message = f"Этап {stage} ({title}) ещё не реализован"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)
