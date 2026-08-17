"""Общие структуры данных, которыми обмениваются модули пайплайна.

Поток данных:

    transcribe -> Transcript(Word[])      слова с таймкодами ИСХОДНОГО видео
    parser     -> Tag[]                   теги сценария с якорным текстом
    aligner    -> Tag.src_time            тег привязан к секунде исходника
    autocut    -> KeepSegment[]           куски речи, которые остаются
    timeline   -> TimeMap + Event[]       таймкоды переведены в ФИНАЛЬНЫЙ таймлайн
    compositor -> mp4
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# Транскрипт
# --------------------------------------------------------------------------- #


@dataclass
class Word:
    """Слово с таймкодами. Основа всего: и субтитров, и привязки тегов."""

    text: str
    start: float
    end: float
    probability: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Segment:
    """Фраза целиком — как её вернул Whisper (для читаемого лога и отладки)."""

    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    """Результат распознавания исходного видео."""

    words: list[Word] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0
    source: str = ""
    model: str = ""
    # Приметы исходника и настроек распознавания: по ним проверяется,
    # не устарел ли кэш (сменили видео или модель — считаем заново).
    source_size: int = 0
    source_mtime: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_to_jsonable(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "Transcript":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            words=[Word(**w) for w in data.get("words", [])],
            segments=[
                Segment(
                    text=s["text"],
                    start=s["start"],
                    end=s["end"],
                    words=[Word(**w) for w in s.get("words", [])],
                )
                for s in data.get("segments", [])
            ],
            language=data.get("language", ""),
            duration=data.get("duration", 0.0),
            source=data.get("source", ""),
            model=data.get("model", ""),
            source_size=data.get("source_size", 0),
            source_mtime=data.get("source_mtime", 0.0),
            params=data.get("params", {}),
        )


# --------------------------------------------------------------------------- #
# Теги сценария
# --------------------------------------------------------------------------- #


@dataclass
class Tag:
    """Один тег из script.txt.

    kind        — тип из config.tags.names ("screen", "insert", ...)
    raw         — как тег написан в сценарии, например "[ВСТАВКА: chart.png 3с]"
    argument    — имя файла или иной аргумент ("chart.png")
    duration    — длительность из тега в секундах, если указана
    anchor      — слова речи ПЕРЕД тегом: по ним ищем момент в транскрипте
    anchor_after— слова речи ПОСЛЕ тега (запасной якорь, если тег в начале абзаца)
    word_index  — сколько слов речи стоит в сценарии перед тегом; это и есть
                  «адрес» тега, который выравнивание переводит в секунды
    paragraph   — номер абзаца: [ЭКРАН] без стоп-тега действует до конца абзаца
    src_time    — секунда ИСХОДНОГО видео (заполняет aligner)
    similarity  — насколько уверенно нашли якорь (0..1)
    """

    kind: str
    raw: str
    argument: str = ""
    duration: float | None = None
    anchor: str = ""
    anchor_after: str = ""
    word_index: int = 0
    paragraph: int = 0
    src_time: float | None = None
    similarity: float = 0.0

    @property
    def resolved(self) -> bool:
        return self.src_time is not None


# --------------------------------------------------------------------------- #
# Нарезка и таймлайн
# --------------------------------------------------------------------------- #


@dataclass
class KeepSegment:
    """Кусок ИСХОДНОГО видео, который остаётся в ролике после автореза."""

    start: float
    end: float
    protected: bool = False  # тишина, защищённая тегом [ПАУЗА]

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Event:
    """Событие на ФИНАЛЬНОМ таймлайне — то, что реально применяет compositor."""

    kind: str
    start: float
    end: float | None = None
    source: Path | None = None
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        return None if self.end is None else max(0.0, self.end - self.start)


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {key: _to_jsonable(value) for key, value in asdict(obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {key: _to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(item) for item in obj]
    return obj
