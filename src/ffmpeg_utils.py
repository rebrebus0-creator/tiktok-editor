"""Тонкая обёртка над FFmpeg/ffprobe: запуск, проверка наличия, чтение медиаданных.

Весь монтаж идёт через FFmpeg, поэтому все вызовы собраны здесь: одинаковое
логирование команд (`-v debug` покажет полную строку) и одинаковая обработка ошибок.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import FFmpegError, FFmpegNotFound

log = logging.getLogger(__name__)

# Фильтры, без которых пайплайн не соберётся (проверяются командой `check`).
REQUIRED_FILTERS = (
    "silencedetect",  # детект пауз для автореза
    "subtitles",  # вшивание караоке-субтитров (libass)
    "overlay",  # [ВСТАВКА] и [ЭКРАН]
    "sidechaincompress",  # дакинг музыки под голос
    "adelay",  # [ЗВУК] в нужной точке
    "amix",  # сведение голоса, эффектов и музыки
    "zoompan",  # [ЗУМ]
    "boxblur",  # размытая подложка под скринкаст
    "concat",  # склейка кусков речи
    "loudnorm",  # нормализация громкости на экспорте
)


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BINARY") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.environ.get("FFPROBE_BINARY") or "ffprobe"


def find_ffmpeg() -> tuple[str | None, str | None]:
    """Пути к ffmpeg и ffprobe (или None, если не найдены)."""
    return shutil.which(ffmpeg_bin()), shutil.which(ffprobe_bin())


def require_ffmpeg() -> None:
    """Падает с понятным сообщением, если FFmpeg не установлен."""
    ffmpeg, ffprobe = find_ffmpeg()
    missing = [name for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if path is None]
    if missing:
        raise FFmpegNotFound(
            f"не найдено в PATH: {', '.join(missing)}. Установка на Mac: brew install ffmpeg"
        )


@lru_cache(maxsize=2)
def version(binary: str | None = None) -> str:
    """Строка версии, например «6.1.1»."""
    binary = binary or ffmpeg_bin()
    if shutil.which(binary) is None:
        raise FFmpegNotFound(f"{binary} не найден в PATH")
    out = subprocess.run(
        [binary, "-version"], capture_output=True, text=True, check=False
    ).stdout
    first = out.splitlines()[0] if out else ""
    parts = first.split()
    return parts[2] if len(parts) > 2 else first


@lru_cache(maxsize=1)
def available_filters() -> frozenset[str]:
    """Множество имён фильтров, собранных в этой сборке FFmpeg."""
    if shutil.which(ffmpeg_bin()) is None:
        return frozenset()
    out = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    names: set[str] = set()
    for line in out.splitlines():
        # Формат строки: " T.. name  I->O  description"
        parts = line.split()
        if len(parts) >= 3 and not line.startswith("Filters:") and "=" not in parts[0]:
            names.add(parts[1])
    return frozenset(names)


def has_filter(name: str) -> bool:
    return name in available_filters()


@lru_cache(maxsize=1)
def available_encoders() -> frozenset[str]:
    if shutil.which(ffmpeg_bin()) is None:
        return frozenset()
    out = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    names: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(("V", "A", "S")) and len(parts[0]) == 6:
            names.add(parts[1])
    return frozenset(names)


def extract_audio(src: Path, out_path: Path, *, sample_rate: int = 16000) -> Path:
    """Достаёт из видео моно-WAV 16 кГц.

    Одна дорожка используется и Whisper'ом, и детектом тишины: так таймкоды
    слов и границы пауз считаются от одного и того же сигнала, и видео
    не декодируется по второму разу.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        desc=f"извлечение звука из {src.name}",
    )
    return out_path


_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?[\d.]+) dB")
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?[\d.]+) dB")


def volume_stats(src: Path) -> dict[str, float | None]:
    """Средняя и пиковая громкость дорожки (ffmpeg volumedetect).

    Нужна, чтобы понять, адекватен ли порог тишины: если порог выше средней
    громкости речи, авторез вырежет саму речь.
    """
    proc = run_raw(
        ["-i", str(src), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        desc=f"замер громкости {src.name}",
        loglevel="info",
    )
    text = proc.stderr or ""
    mean = _MEAN_VOLUME_RE.search(text)
    peak = _MAX_VOLUME_RE.search(text)
    return {
        "mean_volume_db": float(mean.group(1)) if mean else None,
        "max_volume_db": float(peak.group(1)) if peak else None,
    }


def run(
    args: list[str],
    *,
    desc: str | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Запускает ffmpeg. `args` — только аргументы, без имени бинарника."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    return _run(cmd, desc=desc or "ffmpeg", capture=capture, check=check)


def run_raw(
    args: list[str],
    *,
    desc: str | None = None,
    loglevel: str = "info",
) -> subprocess.CompletedProcess:
    """Запуск ffmpeg с нужным уровнем логов и БЕЗ падения на ненулевом коде.

    Нужен там, где полезная информация приходит именно в stderr —
    например `silencedetect` печатает найденные паузы на уровне info.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", loglevel, *args]
    return _run(cmd, desc=desc or "ffmpeg", capture=True, check=False)


def _run(cmd: list[str], *, desc: str, capture: bool, check: bool) -> subprocess.CompletedProcess:
    log.debug("$ %s", " ".join(_quote(part) for part in cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FFmpegNotFound(
            f"{cmd[0]} не найден в PATH. Установка на Mac: brew install ffmpeg"
        ) from exc

    if check and proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-15:]
        raise FFmpegError(
            f"{desc}: FFmpeg вернул код {proc.returncode}\n" + "\n".join(tail)
        )
    return proc


def _quote(part: str) -> str:
    return f'"{part}"' if " " in part else part


# --------------------------------------------------------------------------- #
# ffprobe
# --------------------------------------------------------------------------- #


@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    has_video: bool
    has_audio: bool
    sample_rate: int | None
    video_codec: str | None
    audio_codec: str | None

    @property
    def is_vertical(self) -> bool:
        return bool(self.width and self.height and self.height > self.width)

    def summary(self) -> str:
        bits: list[str] = []
        if self.has_video and self.width and self.height:
            fps = f"@{self.fps:.3g}fps" if self.fps else ""
            bits.append(f"{self.width}x{self.height}{fps}")
        if self.has_audio:
            rate = f" {self.sample_rate}Hz" if self.sample_rate else ""
            bits.append(f"звук {self.audio_codec or '?'}{rate}")
        elif self.has_video:
            bits.append("без звука")
        bits.append(f"{self.duration:.1f}с")
        return ", ".join(bits)


def probe(path: Path | str) -> dict:
    """Сырой JSON от ffprobe."""
    path = Path(path)
    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = _run(cmd, desc=f"ffprobe {path.name}", capture=True, check=True)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe вернул не-JSON для {path}") from exc


def media_info(path: Path | str) -> MediaInfo:
    """Разобранные параметры файла: длительность, размер кадра, fps, наличие дорожек."""
    path = Path(path)
    data = probe(path)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = _float(data.get("format", {}).get("duration"))
    if duration is None:
        for stream in (video, audio):
            duration = duration or _float((stream or {}).get("duration"))
    return MediaInfo(
        path=path,
        duration=duration or 0.0,
        width=_int((video or {}).get("width")),
        height=_int((video or {}).get("height")),
        fps=_fps((video or {}).get("avg_frame_rate")) or _fps((video or {}).get("r_frame_rate")),
        has_video=video is not None,
        has_audio=audio is not None,
        sample_rate=_int((audio or {}).get("sample_rate")),
        video_codec=(video or {}).get("codec_name"),
        audio_codec=(audio or {}).get("codec_name"),
    )


def duration(path: Path | str) -> float:
    return media_info(path).duration


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fps(value) -> float | None:
    """«30000/1001» -> 29.97."""
    if not value or not isinstance(value, str) or "/" not in value:
        return _float(value)
    num, _, den = value.partition("/")
    num_f, den_f = _float(num), _float(den)
    if not num_f or not den_f:
        return None
    return num_f / den_f
