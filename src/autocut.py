"""Детект тишины и вырезание пауз — ЭТАП 1.

Логика:
  1. FFmpeg `silencedetect` находит интервалы тишины;
  2. интервалы, защищённые тегом [ПАУЗА], из вырезания исключаются;
  3. вокруг речи оставляем padding, чтобы не срубить начало слова;
  4. слишком короткие огрызки склеиваем с соседями.

Главный принцип: лучше оставить лишнюю десятую долю секунды, чем
откусить первый слог. Все спорные решения пишутся в лог.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import ffmpeg_utils
from .config import Config
from .models import KeepSegment

log = logging.getLogger(__name__)

STAGE = 1
STAGE_TITLE = "Транскрипция + авторез"

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")

# Если после нарезки осталось меньше этой доли исходника — почти наверняка
# порог тишины выбран неверно (тихий микрофон, шумная комната).
SUSPICIOUS_KEEP_RATIO = 0.2


def detect_silence(
    media: Path,
    cfg: Config,
    *,
    silence_db: float | None = None,
    min_silence: float | None = None,
    total_duration: float | None = None,
    quiet: bool = False,
) -> list[tuple[float, float]]:
    """Интервалы тишины (start, end) по данным FFmpeg silencedetect."""
    media = Path(media)
    noise = cfg.autocut.silence_db if silence_db is None else silence_db
    length = cfg.autocut.min_silence if min_silence is None else min_silence
    total = total_duration if total_duration is not None else ffmpeg_utils.duration(media)

    proc = ffmpeg_utils.run_raw(
        [
            "-i",
            str(media),
            "-vn",
            "-af",
            f"silencedetect=noise={noise}dB:d={length}",
            "-f",
            "null",
            "-",
        ],
        desc=f"детект тишины ({noise}dB, {length}s)",
        loglevel="info",
    )

    silences: list[tuple[float, float]] = []
    pending: float | None = None
    for line in (proc.stderr or "").splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            pending = max(0.0, float(start_match.group(1)))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and pending is not None:
            end = min(total, float(end_match.group(1)))
            if end > pending:
                silences.append((pending, end))
            pending = None

    if pending is not None and total > pending:
        # Ролик закончился тишиной — silencedetect не печатает для неё silence_end.
        silences.append((pending, total))

    log.log(
        logging.DEBUG if quiet else logging.INFO,
        "тишина: найдено %d интервалов при пороге %s dB и длине от %s с",
        len(silences),
        noise,
        length,
    )
    return silences


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
    settings = cfg.autocut
    if total_duration <= 0:
        return []
    if not settings.enabled:
        log.info("авторез выключен в конфиге — оставляю исходник целиком")
        return [KeepSegment(0.0, total_duration)]

    speech = _invert(silences, total_duration)
    if not speech:
        log.error(
            "речь не найдена вообще: при пороге %s dB весь ролик считается тишиной. "
            "Оставляю исходник целиком — понизь autocut.silence_db (например до -40)",
            settings.silence_db,
        )
        return [KeepSegment(0.0, total_duration)]

    # Отступы вокруг речи: начало слова часто тише порога и попадает в «тишину».
    padded = [
        KeepSegment(
            start=max(0.0, start - settings.pad_before),
            end=min(total_duration, end + settings.pad_after),
        )
        for start, end in speech
    ]

    for timestamp in protected or []:
        kept = _protected_pause(timestamp, silences, cfg)
        if kept is not None:
            padded.append(kept)

    segments = _merge(padded)
    segments = _drop_tiny(segments, cfg)

    kept_duration = sum(segment.duration for segment in segments)
    removed = total_duration - kept_duration
    log.info(
        "нарезка: %d кусков, оставляем %.1f с из %.1f с (вырезано %.1f с, %.0f%%)",
        len(segments),
        kept_duration,
        total_duration,
        removed,
        100.0 * removed / total_duration if total_duration else 0.0,
    )
    if kept_duration < total_duration * SUSPICIOUS_KEEP_RATIO:
        log.warning(
            "вырезано больше %d%% — похоже, порог тишины слишком высокий. "
            "Понизь autocut.silence_db (сейчас %s dB) и посмотри калибровочную таблицу в отчёте",
            int(100 * (1 - SUSPICIOUS_KEEP_RATIO)),
            settings.silence_db,
        )
    elif removed < 0.05:
        log.warning(
            "не вырезано ничего: пауз длиннее %s с при пороге %s dB не нашлось. "
            "Подними autocut.silence_db (например до -28) или уменьши autocut.min_silence",
            settings.min_silence,
            settings.silence_db,
        )
    return segments


def _invert(silences: list[tuple[float, float]], total: float) -> list[tuple[float, float]]:
    """Дополнение тишины до полной длительности = интервалы речи."""
    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in sorted(silences):
        start = max(0.0, min(start, total))
        end = max(0.0, min(end, total))
        if start > cursor:
            speech.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total:
        speech.append((cursor, total))
    return [(start, end) for start, end in speech if end > start]


def _protected_pause(
    timestamp: float, silences: list[tuple[float, float]], cfg: Config
) -> KeepSegment | None:
    """Тишина под тегом [ПАУЗА]: оставляем, но не длиннее protected_pause_max.

    Тег стоит рядом с фразой, а сама пауза может оказаться и чуть позже
    (держим паузу после фразы), и чуть раньше (пауза была перед ней), поэтому
    ищем ближайшую тишину в окне pause_search секунд.
    """
    limit = cfg.autocut.protected_pause_max
    window = cfg.autocut.pause_search

    def distance(interval: tuple[float, float]) -> float:
        start, end = interval
        if start <= timestamp <= end:
            return 0.0
        return start - timestamp if start > timestamp else timestamp - end

    candidates = [item for item in silences if distance(item) <= window]
    if not candidates:
        log.warning(
            "[ПАУЗА] на %.2f с: тишины ближе %.1f с нет — тег ни на что не влияет",
            timestamp,
            window,
        )
        return None

    # Ближайшая; при равном расстоянии предпочитаем ту, что после фразы.
    start, end = min(candidates, key=lambda item: (distance(item), item[0] < timestamp))
    kept = KeepSegment(start=start, end=min(end, start + limit), protected=True)
    log.info(
        "[ПАУЗА] на %.2f с: оставляю тишину %.2f-%.2f с",
        timestamp,
        kept.start,
        kept.end,
    )
    return kept


def _merge(segments: list[KeepSegment]) -> list[KeepSegment]:
    """Склеивает пересекающиеся и соприкасающиеся куски."""
    merged: list[KeepSegment] = []
    for segment in sorted(segments, key=lambda item: item.start):
        if merged and segment.start <= merged[-1].end:
            previous = merged[-1]
            previous.end = max(previous.end, segment.end)
            previous.protected = previous.protected or segment.protected
        else:
            merged.append(KeepSegment(segment.start, segment.end, segment.protected))
    return merged


def _drop_tiny(segments: list[KeepSegment], cfg: Config) -> list[KeepSegment]:
    """Убирает огрызки короче min_segment.

    Огрызок рядом с соседом (щелчок, вздох, разорванное слово) приклеиваем
    к нему вместе с разрывом; одиноко стоящий — выбрасываем с предупреждением,
    потому что на склейке он даёт заметный дёрганый кадр.
    """
    settings = cfg.autocut
    result: list[KeepSegment] = []
    for index, segment in enumerate(segments):
        if segment.duration >= settings.min_segment or segment.protected:
            result.append(segment)
            continue

        gap_before = segment.start - result[-1].end if result else None
        following = segments[index + 1] if index + 1 < len(segments) else None
        gap_after = following.start - segment.end if following else None

        if gap_before is not None and gap_before <= settings.merge_gap and (
            gap_after is None or gap_before <= gap_after
        ):
            result[-1].end = segment.end
        elif gap_after is not None and gap_after <= settings.merge_gap:
            following.start = segment.start
        else:
            log.warning(
                "выброшен короткий кусок %.2f-%.2f с (%.2f с): "
                "если там была речь — увеличь autocut.pad_before/pad_after",
                segment.start,
                segment.end,
                segment.duration,
            )
    return result


def render_cut(video: Path, segments: list[KeepSegment], out_path: Path, cfg: Config) -> Path:
    """Режет и склеивает куски речи в одно видео без пауз.

    Склейка идёт одним проходом через trim/concat: это покадрово точно и
    не зависит от расположения ключевых кадров, в отличие от нарезки на
    файлы и последующего concat-демуксера.
    """
    video = Path(video)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise ValueError("нечего рендерить: список кусков пуст")

    total = ffmpeg_utils.duration(video)
    if len(segments) == 1 and segments[0].start <= 0.05 and segments[0].end >= total - 0.05:
        # Резать нечего — копируем потоки без перекодирования.
        log.info("вырезать нечего — копирую исходник без перекодирования")
        ffmpeg_utils.run(
            ["-i", str(video), "-c", "copy", "-movflags", "+faststart", str(out_path)],
            desc="копирование исходника",
        )
        return out_path

    graph = build_concat_graph(segments)

    log.info("склейка %d кусков -> %s", len(segments), out_path.name)
    ffmpeg_utils.run_filter_complex(
        graph,
        input_args=["-i", str(video)],
        output_args=[
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            cfg.video.video_codec,
            "-crf",
            str(cfg.video.crf),
            "-preset",
            cfg.video.preset,
            "-pix_fmt",
            cfg.video.pix_fmt,
            "-c:a",
            cfg.video.audio_codec,
            "-b:a",
            cfg.video.audio_bitrate,
            "-ar",
            str(cfg.video.sample_rate),
            "-movflags",
            "+faststart",
            str(out_path),
        ],
        desc="нарезка и склейка",
        script_dir=out_path.parent,
    )
    return out_path


def build_concat_graph(segments: list[KeepSegment]) -> str:
    """Фильтрограф «вырезать куски и склеить» для trim/atrim + concat."""
    parts: list[str] = []
    labels: list[str] = []
    for index, segment in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={segment.start:.3f}:end={segment.end:.3f},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
        parts.append(
            f"[0:a]atrim=start={segment.start:.3f}:end={segment.end:.3f},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )
        labels.append(f"[v{index}][a{index}]")
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[vout][aout]")
    return ";".join(parts)


def calibrate(
    media: Path,
    cfg: Config,
    total_duration: float,
) -> dict[str, list[dict]]:
    """Прогоняет детект тишины на разных порогах — таблица для подбора настроек.

    Один прогон даёт готовый ответ на вопрос «какой порог ставить»: видно,
    сколько процентов ролика вырезается при каждом значении.
    """
    result: dict[str, list[dict]] = {"silence_db": [], "min_silence": []}

    for level in cfg.autocut.calibration_db:
        silences = detect_silence(
            media, cfg, silence_db=level, total_duration=total_duration, quiet=True
        )
        result["silence_db"].append(
            _calibration_row({"silence_db": level}, silences, total_duration, cfg)
        )

    for length in cfg.autocut.calibration_min_silence:
        silences = detect_silence(
            media, cfg, min_silence=length, total_duration=total_duration, quiet=True
        )
        result["min_silence"].append(
            _calibration_row({"min_silence": length}, silences, total_duration, cfg)
        )

    return result


def _calibration_row(
    params: dict, silences: list[tuple[float, float]], total: float, cfg: Config
) -> dict:
    speech = _invert(silences, total)
    padded = _merge(
        [
            KeepSegment(
                max(0.0, start - cfg.autocut.pad_before),
                min(total, end + cfg.autocut.pad_after),
            )
            for start, end in speech
        ]
    )
    kept = sum(segment.duration for segment in padded)
    return {
        **params,
        "silences": len(silences),
        "segments": len(padded),
        "kept_seconds": round(kept, 2),
        "removed_seconds": round(total - kept, 2),
        "removed_percent": round(100.0 * (total - kept) / total, 1) if total else 0.0,
    }


def stats(
    segments: list[KeepSegment],
    silences: list[tuple[float, float]],
    total_duration: float,
) -> dict:
    """Сводка по нарезке для отчёта."""
    kept = sum(segment.duration for segment in segments)
    cuts = _cuts_between(segments, total_duration)
    return {
        "total_seconds": round(total_duration, 2),
        "kept_seconds": round(kept, 2),
        "removed_seconds": round(total_duration - kept, 2),
        "removed_percent": round(100.0 * (total_duration - kept) / total_duration, 1)
        if total_duration
        else 0.0,
        "segments": len(segments),
        "silences_found": len(silences),
        "cuts": len(cuts),
        "longest_cut": round(max((end - start for start, end in cuts), default=0.0), 2),
        "longest_silence": round(max((end - start for start, end in silences), default=0.0), 2),
    }


def _cuts_between(segments: list[KeepSegment], total: float) -> list[tuple[float, float]]:
    """Вырезанные интервалы — дополнение оставленных кусков."""
    cuts: list[tuple[float, float]] = []
    cursor = 0.0
    for segment in segments:
        if segment.start > cursor:
            cuts.append((cursor, segment.start))
        cursor = max(cursor, segment.end)
    if cursor < total - 0.01:
        cuts.append((cursor, total))
    return cuts
