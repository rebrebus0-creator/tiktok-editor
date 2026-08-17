"""Карта перевода времени и сборка событий — ЭТАПЫ 1 и 3.

После вырезания пауз все таймкоды съезжают: то, что в исходнике звучало на
40-й секунде, в готовом ролике окажется, например, на 31-й. TimeMap переводит
исходное время в финальное — через неё прогоняются и таймкоды тегов, и слова
для субтитров.

Каркас: TimeMap реализован (он нужен уже на этапе 1), сборка событий — этап 3.
"""

from __future__ import annotations

import bisect
import logging

from .config import Config
from .models import Event, KeepSegment, Tag, Transcript, Word

log = logging.getLogger(__name__)

STAGE = 3
STAGE_TITLE = "Парсер + выравнивание"


class TimeMap:
    """Перевод таймкодов: исходное видео -> видео после вырезания пауз.

    Строится из списка оставленных кусков. Время внутри куска сдвигается на
    сумму длительностей всех вырезанных кусков перед ним; время, попавшее
    в вырезанную дыру, прижимается к ближайшей границе.
    """

    def __init__(self, segments: list[KeepSegment]) -> None:
        self.segments = [seg for seg in segments if seg.duration > 0]
        self._starts: list[float] = []
        self._offsets: list[float] = []
        elapsed = 0.0
        for seg in self.segments:
            self._starts.append(seg.start)
            self._offsets.append(elapsed)
            elapsed += seg.duration
        self.total = elapsed

    @property
    def is_identity(self) -> bool:
        """True, если резать нечего (авторез выключен) — перевод не нужен."""
        return not self.segments

    def to_final(self, src_time: float) -> float:
        """Исходная секунда -> секунда в собранном ролике."""
        if self.is_identity:
            return max(0.0, src_time)

        index = bisect.bisect_right(self._starts, src_time) - 1
        if index < 0:
            # Точка раньше первого куска — прижимаем к началу ролика.
            return 0.0

        seg = self.segments[index]
        if src_time <= seg.end:
            return self._offsets[index] + (src_time - seg.start)

        # Точка попала в вырезанную паузу — ставим на стык кусков.
        return self._offsets[index] + seg.duration

    def to_source(self, final_time: float) -> float:
        """Обратный перевод: секунда ролика -> секунда исходника."""
        if self.is_identity:
            return max(0.0, final_time)

        index = bisect.bisect_right(self._offsets, final_time) - 1
        index = max(0, min(index, len(self.segments) - 1))
        seg = self.segments[index]
        return seg.start + (final_time - self._offsets[index])

    def covers(self, src_time: float) -> bool:
        """Осталась ли эта точка исходника в ролике (не попала ли под нож)."""
        if self.is_identity:
            return True
        index = bisect.bisect_right(self._starts, src_time) - 1
        if index < 0:
            return False
        return src_time <= self.segments[index].end

    def map_words(self, words: list[Word]) -> list[Word]:
        """Переводит таймкоды слов в финальный таймлайн (для субтитров)."""
        mapped: list[Word] = []
        for word in words:
            start = self.to_final(word.start)
            end = self.to_final(word.end)
            if end <= start:
                # Слово целиком попало в вырезанный кусок — в субтитрах его не будет.
                continue
            mapped.append(Word(text=word.text, start=start, end=end, probability=word.probability))
        return mapped

    def map_transcript(self, transcript: Transcript) -> Transcript:
        return Transcript(
            words=self.map_words(transcript.words),
            segments=[],
            language=transcript.language,
            duration=self.total or transcript.duration,
            source=transcript.source,
            model=transcript.model,
        )


def build_events(
    doc,
    time_map: TimeMap,
    cfg: Config,
    project,
    final_duration: float,
) -> list[Event]:
    """Превращает выровненные теги в события ФИНАЛЬНОГО таймлайна.

    Здесь решаются вопросы длительности ([ЭКРАН] без стоп-тега — до конца
    абзаца, [ВСТАВКА] без числа — cfg.insert.default_duration) и ищутся файлы
    ассетов. Пропавший файл или неразрешённый тег — предупреждение и пропуск,
    а не остановка сборки.
    """
    tags = sorted(
        (tag for tag in doc.tags if tag.resolved),
        key=lambda item: (item.word_index, item.paragraph),
    )
    events: list[Event] = []

    for position, tag in enumerate(tags):
        start = time_map.to_final(tag.src_time)

        if tag.kind == "screen":
            end = _screen_end(tag, tags[position + 1 :], doc, time_map, final_duration)
            _append_media(events, "screen", tag, start, end, project, cfg, final_duration)

        elif tag.kind == "insert":
            duration = tag.duration or cfg.insert.default_duration
            _append_media(
                events, "insert", tag, start, start + duration, project, cfg, final_duration
            )

        elif tag.kind == "sound":
            _append_media(events, "sound", tag, start, None, project, cfg, final_duration)

        elif tag.kind == "music":
            end = _music_end(tag, tags[position + 1 :], time_map, final_duration)
            _append_media(events, "music", tag, start, end, project, cfg, final_duration)

        elif tag.kind == "zoom":
            duration = tag.duration or cfg.zoom.duration
            events.append(
                Event(
                    kind="zoom",
                    start=start,
                    end=min(final_duration, start + duration),
                    params={"tag": tag.raw},
                )
            )

        elif tag.kind in ("pause", "screen_stop", "music_stop"):
            # [ПАУЗА] отрабатывает раньше — в авторезе; стоп-теги закрывают
            # интервалы соседних тегов и своих событий не порождают.
            continue

    events.sort(key=lambda item: item.start)
    log.info(
        "события таймлайна: %d (%s)",
        len(events),
        ", ".join(f"{event.kind}@{event.start:.1f}с" for event in events) or "нет",
    )
    return events


def _append_media(
    events: list[Event],
    kind: str,
    tag: Tag,
    start: float,
    end: float | None,
    project,
    cfg: Config,
    final_duration: float,
) -> None:
    """Добавляет событие с файлом-ассетом, если файл нашёлся."""
    source = project.find_asset(kind, tag.argument)
    if source is None:
        log.warning(
            "%s: файл «%s» не найден — событие пропущено",
            tag.raw,
            tag.argument or "(не указан)",
        )
        return

    start = max(0.0, min(start, final_duration))
    if end is not None:
        end = max(0.0, min(end, final_duration))
        if end - start < 0.05:
            log.warning(
                "%s: интервал схлопнулся после вырезания пауз (%.2f-%.2f с) — пропускаю",
                tag.raw,
                start,
                end,
            )
            return

    events.append(Event(kind=kind, start=start, end=end, source=source, params={"tag": tag.raw}))


def _screen_end(
    tag: Tag,
    following: list[Tag],
    doc,
    time_map: TimeMap,
    final_duration: float,
) -> float:
    """Докуда показывать скринкаст: явная длительность, стоп-тег или конец абзаца."""
    if tag.duration:
        return time_map.to_final(tag.src_time) + tag.duration

    for other in following:
        if other.kind in ("screen_stop", "screen"):
            return time_map.to_final(other.src_time)

    if tag.paragraph < len(doc.paragraph_end_times):
        paragraph_end = doc.paragraph_end_times[tag.paragraph]
        if paragraph_end is not None:
            return time_map.to_final(paragraph_end)

    return final_duration


def _music_end(
    tag: Tag, following: list[Tag], time_map: TimeMap, final_duration: float
) -> float:
    """Музыка играет до [МУЗЫКА СТОП], до следующего [МУЗЫКА] или до конца ролика."""
    for other in following:
        if other.kind in ("music_stop", "music"):
            return time_map.to_final(other.src_time)
    return final_duration
