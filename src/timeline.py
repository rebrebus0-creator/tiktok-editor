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
from .errors import StagePending
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


def build_events(tags: list[Tag], time_map: TimeMap, cfg: Config, project) -> list[Event]:
    """Превращает выровненные теги в события финального таймлайна.

    Здесь же решаются вопросы длительности: [ЭКРАН] без стоп-тега — до конца
    абзаца, [ВСТАВКА] без длительности — cfg.insert.default_duration, и т.д.
    """
    raise StagePending(STAGE, STAGE_TITLE, "сборка событий таймлайна ещё не реализована")
