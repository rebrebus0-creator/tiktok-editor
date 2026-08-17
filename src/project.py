"""Работа со структурой проекта.

Проект — это папка, в которой лежит всё для одного ролика:

    projects/<имя>/
        raw/          основное видео (говорящая голова)
        screencasts/  записи экрана для [ЭКРАН]
        inserts/      картинки/иконки для [ВСТАВКА]
        sounds/       звуковые эффекты для [ЗВУК]
        music/        фоновые треки для [МУЗЫКА]
        script.txt    размеченный сценарий
        output/       готовый ролик
        .cache/       транскрипт и промежуточные файлы (создаётся автоматически)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectError

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

MEDIA_DIRS = ("raw", "screencasts", "inserts", "sounds", "music")
SUBDIRS = (*MEDIA_DIRS, "output")

# Какая папка и какие расширения соответствуют типу тега.
ASSET_DIRS: dict[str, tuple[str, set[str]]] = {
    "screen": ("screencasts", VIDEO_EXT),
    "insert": ("inserts", IMAGE_EXT | VIDEO_EXT),
    "sound": ("sounds", AUDIO_EXT),
    "music": ("music", AUDIO_EXT),
}

EXAMPLE_SCRIPT = """\
Привет! Меня зовут Иван, и за сорок секунд я покажу,
как собрать вертикальный ролик, не открывая монтажку. [ЗУМ]

Смотри, вот мой сценарий. [ЭКРАН: demo.mp4]
Я просто пишу текст своей речи и ставлю теги в квадратных скобках —
софт сам находит, на какой секунде я это произнёс. [ЭКРАН СТОП]

Первое правило: [ВСТАВКА: pravilo1.png 3с] снимай одним дублем и не бойся оговорок.
Паузы и запинки программа вырежет сама.

Второе правило: держи паузу перед главной мыслью. [ПАУЗА]
Именно в этой тишине зритель успевает понять, что ты сказал. [ЗВУК: whoosh.mp3]

[МУЗЫКА: lofi.mp3]
Подписывайся, если хочешь так же — по семь роликов в день без монтажёра.
[МУЗЫКА СТОП]
"""


@dataclass
class Project:
    """Папка проекта + доступ к её содержимому."""

    path: Path

    # ------------------------------------------------------------------ #
    # Пути
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def raw_dir(self) -> Path:
        return self.path / "raw"

    @property
    def screencasts_dir(self) -> Path:
        return self.path / "screencasts"

    @property
    def inserts_dir(self) -> Path:
        return self.path / "inserts"

    @property
    def sounds_dir(self) -> Path:
        return self.path / "sounds"

    @property
    def music_dir(self) -> Path:
        return self.path / "music"

    @property
    def output_dir(self) -> Path:
        return self.path / "output"

    @property
    def cache_dir(self) -> Path:
        return self.path / ".cache"

    @property
    def script_path(self) -> Path:
        return self.path / "script.txt"

    @property
    def log_path(self) -> Path:
        return self.output_dir / "build.log"

    def output_video(self) -> Path:
        return self.output_dir / f"{self.name}.mp4"

    # ------------------------------------------------------------------ #
    # Создание и загрузка
    # ------------------------------------------------------------------ #

    @classmethod
    def create(cls, path: Path, *, with_example_script: bool = True) -> "Project":
        """Создаёт структуру папок проекта. Существующие файлы не трогает."""
        project = cls(Path(path).expanduser().resolve())
        project.path.mkdir(parents=True, exist_ok=True)
        for name in SUBDIRS:
            directory = project.path / name
            directory.mkdir(exist_ok=True)
            keep = directory / ".gitkeep"
            if not keep.exists():
                keep.touch()

        if with_example_script and not project.script_path.exists():
            project.script_path.write_text(EXAMPLE_SCRIPT, encoding="utf-8")
        return project

    @classmethod
    def load(cls, path: Path) -> "Project":
        """Открывает существующий проект и проверяет минимальную комплектность."""
        project = cls(Path(path).expanduser().resolve())
        if not project.path.is_dir():
            raise ProjectError(f"папка проекта не найдена: {project.path}")

        for name in MEDIA_DIRS:
            directory = project.path / name
            if not directory.is_dir():
                log.warning("нет папки %s/ — создаю пустую", name)
                directory.mkdir(parents=True, exist_ok=True)
        project.output_dir.mkdir(exist_ok=True)
        return project

    # ------------------------------------------------------------------ #
    # Содержимое
    # ------------------------------------------------------------------ #

    def raw_video(self) -> Path:
        """Исходное видео из raw/. Ожидается ровно один файл."""
        videos = sorted(
            item
            for item in self.raw_dir.glob("*")
            if item.is_file() and item.suffix.lower() in VIDEO_EXT
        )
        if not videos:
            raise ProjectError(
                f"в {self.raw_dir} нет видео "
                f"({', '.join(sorted(VIDEO_EXT))}) — положи туда исходную запись"
            )
        if len(videos) > 1:
            names = ", ".join(video.name for video in videos)
            raise ProjectError(
                f"в raw/ несколько видео ({names}). Оставь одно "
                f"или укажи нужное через --raw"
            )
        return videos[0]

    def script_text(self) -> str:
        if not self.script_path.is_file():
            raise ProjectError(f"нет файла сценария: {self.script_path}")
        text = self.script_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ProjectError(f"сценарий пустой: {self.script_path}")
        return text

    def find_asset(self, kind: str, filename: str) -> Path | None:
        """Ищет файл ассета для тега. Возвращает None, если не нашли.

        Не падает намеренно: по правилам проекта пропавший ассет — это
        предупреждение в лог, а не остановка рендера.
        """
        if not filename:
            return None

        dirname, extensions = ASSET_DIRS.get(kind, ("", set()))
        candidate = Path(filename).expanduser()
        if candidate.is_absolute() and candidate.is_file():
            return candidate

        search_dirs = [self.path / dirname] if dirname else []
        search_dirs.append(self.path)

        for directory in search_dirs:
            if not directory.is_dir():
                continue
            exact = directory / filename
            if exact.is_file():
                return exact
            # Регистр и расширение могут не совпасть — ищем мягче.
            wanted = Path(filename).stem.lower()
            for item in sorted(directory.iterdir()):
                if not item.is_file():
                    continue
                if item.name.lower() == filename.lower():
                    return item
                if item.stem.lower() == wanted and (
                    not extensions or item.suffix.lower() in extensions
                ):
                    return item
        return None

    def assets(self, kind: str) -> list[Path]:
        """Все файлы подходящего типа в папке ассетов — для команды info."""
        dirname, extensions = ASSET_DIRS.get(kind, ("", set()))
        directory = self.path / dirname if dirname else self.path
        if not directory.is_dir():
            return []
        return sorted(
            item
            for item in directory.iterdir()
            if item.is_file() and item.suffix.lower() in extensions
        )


def discover_projects(root: Path) -> list[Project]:
    """Все проекты внутри папки — для batch-режима."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ProjectError(f"папка не найдена: {root}")

    found: list[Project] = []
    for item in sorted(root.iterdir()):
        if item.is_dir() and (item / "script.txt").is_file():
            found.append(Project(item))
    return found
