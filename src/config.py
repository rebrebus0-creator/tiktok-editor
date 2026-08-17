"""Настройки монтажа.

Значения по умолчанию живут здесь. Переопределять их можно, не трогая код:

  1. `config.toml` в корне репозитория — общие настройки под свой канал;
  2. `projects/<имя>/config.toml` — настройки конкретного ролика (перекрывают общие).

Формат — TOML (читается стандартным `tomllib`, зависимостей не требует).
Полный список параметров с комментариями — в `config.example.toml`.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
PROJECTS_DIR = REPO_ROOT / "projects"

CONFIG_FILENAME = "config.toml"


# --------------------------------------------------------------------------- #
# Разделы конфига
# --------------------------------------------------------------------------- #


@dataclass
class VideoCfg:
    """Параметры финального экспорта."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_codec: str = "libx264"
    crf: int = 19
    preset: str = "medium"
    pix_fmt: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    sample_rate: int = 48000
    # Как вписывать исходник в вертикальный кадр, если он не 9:16:
    # blur (размытая подложка), pad (поля), cover (обрезать по краям).
    fit: str = "blur"
    # Положение говорящего по вертикали при вписывании: 0.0 верх, 1.0 низ.
    position_y: float = 0.5
    # Приводить итоговую громкость к стандарту вещания (-14 LUFS — норма для соцсетей).
    loudnorm: bool = True
    loudnorm_i: float = -14.0
    loudnorm_tp: float = -1.5
    loudnorm_lra: float = 11.0

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def aspect(self) -> float:
        return self.width / self.height


@dataclass
class TranscribeCfg:
    """faster-whisper. На Mac считает на CPU, поэтому int8 — компромисс скорость/качество."""

    model: str = "medium"  # "medium" быстрее, "large-v3" точнее
    language: str = "ru"
    device: str = "auto"  # auto | cpu | cuda
    compute_type: str = "int8"  # int8 | int8_float16 | float16 | float32
    beam_size: int = 5
    # VAD отсекает шум/дыхание — таймкоды слов получаются чище.
    vad_filter: bool = True
    vad_min_silence_ms: int = 400
    # На длинной речи с повторами выключение контекста спасает от зацикливания Whisper.
    condition_on_previous_text: bool = False
    # Подсказка модели: имена, термины, англицизмы — чтобы писала их правильно.
    initial_prompt: str = ""
    # Кэшировать транскрипт в <проект>/.cache — пересборка ролика идёт мгновенно.
    cache: bool = True


@dataclass
class AutocutCfg:
    """Детект тишины (FFmpeg silencedetect) и вырезание пауз."""

    enabled: bool = True
    # Порог «тишины» в дБ: тише этого уровня — считаем паузой.
    silence_db: float = -32.0
    # Паузы короче этого не трогаем вообще (иначе речь звучит рублено).
    min_silence: float = 0.45
    # Отступы вокруг речи, чтобы не срезать начало слова и хвост фразы.
    pad_before: float = 0.12
    pad_after: float = 0.20
    # Слишком короткие куски речи после нарезки склеиваем с соседями.
    min_segment: float = 0.30
    # Максимальный разрыв, через который короткий огрызок приклеивается к соседу.
    merge_gap: float = 0.40
    # Тишину, защищённую тегом [ПАУЗА], оставляем — но не длиннее этого.
    protected_pause_max: float = 2.5
    # В каком окне вокруг тега [ПАУЗА] искать саму тишину: тег стоит рядом
    # с фразой, а пауза может быть чуть раньше или чуть позже.
    pause_search: float = 2.5
    # Пороги для калибровочной таблицы в отчёте (команда cut): показывает,
    # сколько вырезалось бы при каждом значении — чтобы подобрать своё.
    calibration_db: list[float] = field(
        default_factory=lambda: [-24.0, -28.0, -32.0, -36.0, -40.0, -45.0]
    )
    calibration_min_silence: list[float] = field(
        default_factory=lambda: [0.30, 0.45, 0.60, 0.90]
    )


@dataclass
class SubtitlesCfg:
    """Караоке-субтитры (.ass, подсветка текущего слова)."""

    enabled: bool = True
    font_name: str = "Montserrat ExtraBold"
    # Файл шрифта в assets/fonts. Пустая строка — брать системный по font_name.
    font_file: str = "Montserrat-ExtraBold.ttf"
    font_size: int = 84
    bold: bool = True
    uppercase: bool = True
    # Цвета в привычном #RRGGBB, в ASS-формат конвертируются автоматически.
    primary_color: str = "#FFFFFF"  # ещё не произнесённое слово
    highlight_color: str = "#FFE000"  # слово, которое звучит сейчас
    outline_color: str = "#000000"
    outline: float = 6.0
    shadow: float = 2.0
    # 2 = снизу по центру (нумерация как на цифровой клавиатуре), 5 = центр экрана.
    alignment: int = 2
    margin_v: int = 520  # поднимаем над интерфейсом TikTok/Reels
    margin_h: int = 90
    # Сколько слов держим в одной «плашке» субтитра.
    # 18 символов при кегле 84 — примерно ширина кадра 1080; длиннее libass
    # переносит на вторую строку.
    max_words: int = 3
    max_chars: int = 18
    # Если между словами пауза длиннее — начинаем новую плашку.
    max_gap: float = 0.7
    min_duration: float = 0.5


@dataclass
class ScreenCfg:
    """[ЭКРАН] — скринкаст вместо говорящей головы."""

    # blur  — вписать по ширине, фон — размытый кадр самого скринкаста (стиль Reels)
    # pad   — вписать по ширине, поля залить цветом
    # cover — заполнить кадр целиком с обрезкой краёв
    mode: str = "blur"
    blur_sigma: int = 30
    pad_color: str = "#000000"
    # Масштаб скринкаста внутри кадра (1.0 = вся ширина 1080).
    scale: float = 1.0
    # Вертикальное положение центра скринкаста: 0.0 — верх, 0.5 — центр, 1.0 — низ.
    position_y: float = 0.42
    # Звук скринкаста: mute | mix (подмешать к голосу) | replace
    audio: str = "mute"
    audio_volume: float = 0.5
    # Сколько секунд показывать, если в теге не указана длительность и нет [ЭКРАН СТОП]:
    # 0 = до конца абзаца сценария.
    default_duration: float = 0.0


@dataclass
class InsertCfg:
    """[ВСТАВКА] — картинка/иконка оверлеем."""

    default_duration: float = 3.0
    # center | top | bottom | top-left | top-right | bottom-left | bottom-right
    position: str = "center"
    margin: int = 90
    # Максимальные доли кадра, до которых ужимается картинка.
    max_width: float = 0.75
    max_height: float = 0.45
    fade: float = 0.2


@dataclass
class SoundCfg:
    """[ЗВУК] — разовый звуковой эффект."""

    volume: float = 0.8


@dataclass
class MusicCfg:
    """[МУЗЫКА] / [МУЗЫКА СТОП] — фоновый трек с автодакингом под голос."""

    volume: float = 0.20
    # Дакинг: музыка автоматически тише, когда звучит голос (sidechaincompress).
    duck: bool = True
    duck_ratio: float = 8.0  # сила приглушения
    duck_threshold: float = 0.03  # уровень голоса, с которого срабатывает
    duck_attack_ms: float = 20.0
    duck_release_ms: float = 350.0
    fade_in: float = 0.8
    fade_out: float = 1.2
    # Зациклить трек, если он короче отрезка, на котором играет.
    loop: bool = True


@dataclass
class ZoomCfg:
    """[ЗУМ] — плавный наезд для акцента."""

    amount: float = 1.18  # во сколько раз наезжаем
    ramp: float = 0.9  # длительность самого наезда, сек
    duration: float = 2.5  # сколько держим зум, если в теге не задано иначе
    # Точка, к которой наезжаем (доли кадра). По умолчанию — лицо в верхней трети.
    focus_x: float = 0.5
    focus_y: float = 0.38


@dataclass
class TagsCfg:
    """Имена тегов сценария. Меняются здесь — парсер читает их отсюда."""

    names: dict[str, list[str]] = field(
        default_factory=lambda: {
            "screen": ["ЭКРАН", "SCREEN"],
            "screen_stop": ["ЭКРАН СТОП", "SCREEN STOP"],
            "insert": ["ВСТАВКА", "INSERT"],
            "sound": ["ЗВУК", "SFX", "SOUND"],
            "music": ["МУЗЫКА", "MUSIC"],
            "music_stop": ["МУЗЫКА СТОП", "MUSIC STOP"],
            "pause": ["ПАУЗА", "PAUSE"],
            "zoom": ["ЗУМ", "ZOOM"],
        }
    )
    # Сколько слов перед тегом берём как «якорь» для поиска момента в транскрипте.
    anchor_words: int = 6
    # Порог похожести якоря и транскрипта (0..1). Ниже — пишем предупреждение в лог.
    min_similarity: float = 0.55

    def alias_map(self) -> dict[str, str]:
        """{нормализованный алиас -> тип тега}. Более длинные алиасы важнее:
        «МУЗЫКА СТОП» не должна распознаться как «МУЗЫКА»."""
        pairs: list[tuple[str, str]] = []
        for kind, aliases in self.names.items():
            for alias in aliases:
                pairs.append((" ".join(alias.upper().split()), kind))
        pairs.sort(key=lambda item: len(item[0]), reverse=True)
        return dict(pairs)


@dataclass
class Config:
    video: VideoCfg = field(default_factory=VideoCfg)
    transcribe: TranscribeCfg = field(default_factory=TranscribeCfg)
    autocut: AutocutCfg = field(default_factory=AutocutCfg)
    subtitles: SubtitlesCfg = field(default_factory=SubtitlesCfg)
    screen: ScreenCfg = field(default_factory=ScreenCfg)
    insert: InsertCfg = field(default_factory=InsertCfg)
    sound: SoundCfg = field(default_factory=SoundCfg)
    music: MusicCfg = field(default_factory=MusicCfg)
    zoom: ZoomCfg = field(default_factory=ZoomCfg)
    tags: TagsCfg = field(default_factory=TagsCfg)

    # Откуда фактически прочитаны настройки (для лога).
    sources: list[Path] = field(default_factory=list)

    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, project_dir: Path | None = None) -> "Config":
        """Дефолты -> config.toml в корне -> config.toml проекта."""
        cfg = cls()
        candidates = [REPO_ROOT / CONFIG_FILENAME]
        if project_dir is not None:
            candidates.append(Path(project_dir) / CONFIG_FILENAME)

        for path in candidates:
            if not path.is_file():
                continue
            try:
                with path.open("rb") as handle:
                    data = tomllib.load(handle)
            except tomllib.TOMLDecodeError as exc:
                # Битый конфиг лучше показать сразу, чем молча рендерить не тем.
                from .errors import ConfigError

                raise ConfigError(f"{path}: не читается как TOML — {exc}") from exc
            _apply(cfg, data, path)
            cfg.sources.append(path)
            log.debug("конфиг подхвачен: %s", path)

        return cfg

    def font_path(self) -> Path | None:
        """Абсолютный путь к файлу шрифта субтитров, если он положен в assets/fonts."""
        if not self.subtitles.font_file:
            return None
        candidate = Path(self.subtitles.font_file)
        if not candidate.is_absolute():
            candidate = FONTS_DIR / candidate
        return candidate if candidate.is_file() else None


# --------------------------------------------------------------------------- #
# Слияние TOML в датаклассы
# --------------------------------------------------------------------------- #


def _apply(target: Any, data: dict[str, Any], source: Path, prefix: str = "") -> None:
    known = {f.name for f in fields(target)}
    for key, value in data.items():
        if key not in known or key == "sources":
            log.warning("%s: неизвестный параметр «%s%s» — пропускаю", source.name, prefix, key)
            continue

        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value, source, prefix=f"{key}.")
        elif isinstance(current, dict) and isinstance(value, dict):
            # Словари (например имена тегов) обновляем по ключам, а не заменяем целиком.
            current.update(value)
        else:
            setattr(target, key, _coerce(current, value))


def _coerce(current: Any, value: Any) -> Any:
    """TOML не различает 1 и 1.0 — приводим int к float там, где ждём float."""
    if isinstance(current, float) and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(current, int) and not isinstance(current, bool) and isinstance(value, float):
        return int(value)
    return value
