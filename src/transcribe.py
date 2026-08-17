"""Транскрипция исходного видео (faster-whisper) — ЭТАП 1.

Задача модуля: получить список слов с таймкодами на ИСХОДНОМ таймлайне.
От этого зависит всё остальное — и субтитры, и привязка тегов к речи,
поэтому запускается с `word_timestamps=True`.

Результат кладётся в `<проект>/.cache/transcript.json`: распознавание —
самая долгая часть пайплайна, и пересобирать ролик после правки сценария
нужно без повторного прогона модели.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import ffmpeg_utils
from .config import Config
from .errors import EditorError
from .models import Segment, Transcript, Word

log = logging.getLogger(__name__)

STAGE = 1
STAGE_TITLE = "Транскрипция + авторез"

# Whisper всё равно работает на 16 кГц моно — извлекаем звук сразу в этом виде.
WHISPER_SAMPLE_RATE = 16000


def transcribe(
    video: Path,
    cfg: Config,
    *,
    cache_path: Path | None = None,
    force: bool = False,
    audio_path: Path | None = None,
) -> Transcript:
    """Распознаёт речь и возвращает слова с таймкодами.

    video      — исходное видео из raw/
    cache_path — куда класть/откуда брать готовый транскрипт (.cache/transcript.json)
    force      — игнорировать кэш и распознать заново
    audio_path — уже извлечённая дорожка (если её готовит оркестратор)
    """
    video = Path(video)
    if cache_path is not None and cfg.transcribe.cache and not force:
        cached = load_cached(cache_path)
        if cached is not None and _cache_is_fresh(cached, video, cfg):
            log.info(
                "транскрипт взят из кэша: %d слов, %s",
                len(cached.words),
                cache_path.name,
            )
            return cached
        if cached is not None:
            log.info("кэш транскрипта устарел (сменился исходник или настройки) — распознаю заново")

    audio = Path(audio_path) if audio_path else None
    if audio is None:
        target = (cache_path.parent if cache_path else video.parent) / "audio.wav"
        audio = ffmpeg_utils.extract_audio(video, target, sample_rate=WHISPER_SAMPLE_RATE)

    transcript = _run_whisper(video, audio, cfg)

    if cache_path is not None and cfg.transcribe.cache:
        transcript.save(cache_path)
        log.debug("транскрипт сохранён в кэш: %s", cache_path)
    return transcript


def _run_whisper(video: Path, audio: Path, cfg: Config) -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover — проверяется командой check
        raise EditorError(
            "faster-whisper не установлен: pip install -r requirements.txt"
        ) from exc

    settings = cfg.transcribe
    duration = ffmpeg_utils.duration(audio)
    log.info(
        "распознавание: модель %s (%s, %s), %.1f с звука",
        settings.model,
        settings.compute_type,
        settings.device,
        duration,
    )
    log.info("если модель ещё не скачана, первый запуск займёт несколько минут")

    started = time.monotonic()
    try:
        model = WhisperModel(
            settings.model,
            device=settings.device,
            compute_type=settings.compute_type,
        )
    except Exception as exc:
        raise EditorError(
            f"не удалось загрузить модель «{settings.model}» "
            f"({settings.device}/{settings.compute_type}): {exc}"
        ) from exc

    segments_iter, info = model.transcribe(
        str(audio),
        language=settings.language or None,
        beam_size=settings.beam_size,
        word_timestamps=True,
        vad_filter=settings.vad_filter,
        vad_parameters={"min_silence_duration_ms": settings.vad_min_silence_ms},
        condition_on_previous_text=settings.condition_on_previous_text,
        initial_prompt=settings.initial_prompt or None,
    )

    words: list[Word] = []
    segments: list[Segment] = []
    reported = 0.0

    # segments_iter — ленивый генератор: модель считает по мере обхода.
    for raw_segment in segments_iter:
        segment_words = [
            Word(
                text=word.word.strip(),
                start=float(word.start),
                end=float(word.end),
                probability=float(getattr(word, "probability", 1.0) or 0.0),
            )
            for word in (raw_segment.words or [])
            if word.word and word.word.strip()
        ]
        words.extend(segment_words)
        segments.append(
            Segment(
                text=raw_segment.text.strip(),
                start=float(raw_segment.start),
                end=float(raw_segment.end),
                words=segment_words,
            )
        )
        if raw_segment.end - reported >= 15.0:
            reported = raw_segment.end
            log.info("  распознано %.0f с из %.0f", reported, duration)

    elapsed = time.monotonic() - started
    if not segments:
        log.warning("речь не распознана — проверь, что в исходнике есть звук")
    elif not words:
        # Без таймкодов слов не будет ни субтитров, ни привязки тегов —
        # раскладываем текст сегмента равномерно, чтобы пайплайн не встал.
        log.warning("модель не вернула таймкоды слов — раскладываю текст по сегментам")
        words = _words_from_segments(segments)

    transcript = Transcript(
        words=words,
        segments=segments,
        language=getattr(info, "language", settings.language) or settings.language,
        duration=duration,
        source=str(video),
        model=settings.model,
        source_size=video.stat().st_size if video.exists() else 0,
        source_mtime=video.stat().st_mtime if video.exists() else 0.0,
        params=_cache_key(cfg),
    )
    log.info(
        "распознано: %d слов, %d фраз, язык %s, за %.0f с (%.1fx реального времени)",
        len(transcript.words),
        len(transcript.segments),
        transcript.language,
        elapsed,
        (duration / elapsed) if elapsed > 0 else 0.0,
    )
    _log_quality(transcript)
    return transcript


def _words_from_segments(segments: list[Segment]) -> list[Word]:
    """Запасной вариант: равномерно раскладываем слова внутри фразы."""
    words: list[Word] = []
    for segment in segments:
        tokens = segment.text.split()
        if not tokens:
            continue
        step = (segment.end - segment.start) / len(tokens)
        for index, token in enumerate(tokens):
            start = segment.start + index * step
            words.append(Word(text=token, start=start, end=start + step, probability=0.0))
    return words


def _log_quality(transcript: Transcript) -> None:
    """Предупреждает о словах, в которых модель не уверена."""
    if not transcript.words:
        return
    probs = [word.probability for word in transcript.words if word.probability > 0]
    if not probs:
        return
    average = sum(probs) / len(probs)
    weak = [word for word in transcript.words if 0 < word.probability < 0.5]
    log.info("средняя уверенность распознавания: %.2f", average)
    if len(weak) > len(transcript.words) * 0.15:
        log.warning(
            "%d слов из %d распознаны неуверенно — субтитры стоит вычитать; "
            "помогает model = \"large-v3\" или initial_prompt с терминами",
            len(weak),
            len(transcript.words),
        )


def _cache_key(cfg: Config) -> dict:
    """Настройки, при смене которых кэш недействителен."""
    settings = cfg.transcribe
    return {
        "model": settings.model,
        "language": settings.language,
        "compute_type": settings.compute_type,
        "beam_size": settings.beam_size,
        "vad_filter": settings.vad_filter,
        "vad_min_silence_ms": settings.vad_min_silence_ms,
        "condition_on_previous_text": settings.condition_on_previous_text,
        "initial_prompt": settings.initial_prompt,
    }


def _cache_is_fresh(cached: Transcript, video: Path, cfg: Config) -> bool:
    if not video.exists():
        return True
    stat = video.stat()
    if cached.source_size and cached.source_size != stat.st_size:
        return False
    if cached.source_mtime and abs(cached.source_mtime - stat.st_mtime) > 1.0:
        return False
    if cached.params and cached.params != _cache_key(cfg):
        return False
    return True


def load_cached(cache_path: Path) -> Transcript | None:
    """Читает транскрипт из кэша, если он есть и не битый."""
    if not cache_path.is_file():
        return None
    try:
        return Transcript.load(cache_path)
    except Exception as exc:  # кэш — вещь одноразовая, битый просто игнорируем
        log.warning("кэш транскрипта не читается (%s) — распознаю заново", exc)
        return None
