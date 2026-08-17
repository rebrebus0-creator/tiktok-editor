"""Настройка логирования: цветная консоль + опциональный файл лога.

Каждый шаг пайплайна логируется — это требование проекта: когда ролик
собрался криво, нужно по логу понять, на каком шаге поехало.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_LEVEL_COLORS = {
    logging.DEBUG: "\033[90m",  # серый
    logging.INFO: "\033[36m",  # голубой
    logging.WARNING: "\033[33m",  # жёлтый
    logging.ERROR: "\033[31m",  # красный
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _color_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class _ConsoleFormatter(logging.Formatter):
    def __init__(self, color: bool) -> None:
        super().__init__("%(message)s")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"

        prefix = {
            logging.DEBUG: "  ",
            logging.INFO: "  ",
            logging.WARNING: "! ",
            logging.ERROR: "x ",
            logging.CRITICAL: "x ",
        }.get(record.levelno, "  ")

        module = record.name.split(".")[-1]
        if not self.color:
            return f"{prefix}[{module}] {message}"

        color = _LEVEL_COLORS.get(record.levelno, "")
        return f"{color}{prefix}{_RESET}\033[90m[{module}]{_RESET} {color if record.levelno >= logging.WARNING else ''}{message}{_RESET if record.levelno >= logging.WARNING else ''}"


def setup_logging(verbose: bool = False, log_file: Path | None = None) -> None:
    """Инициализирует корневой логгер. Вызывается один раз из CLI."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(_ConsoleFormatter(_color_enabled(sys.stderr)))
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")
        )
        root.addHandler(file_handler)

    # faster-whisper и av любят сыпать в лог на INFO — приглушаем.
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("libav").setLevel(logging.ERROR)


def heading(title: str) -> None:
    """Печатает заголовок этапа — визуальный разделитель в консоли.

    Идёт в stdout вместе с остальным отчётом (логи — в stderr),
    чтобы вывод не перемешивался при перенаправлении.
    """
    stream = sys.stdout
    line = f"── {title} " + "─" * max(0, 62 - len(title))
    if _color_enabled(stream):
        print(f"\n{_BOLD}{line}{_RESET}", file=stream)
    else:
        print(f"\n{line}", file=stream)
