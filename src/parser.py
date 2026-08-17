"""Парсер размеченного сценария — ЭТАП 3.

Из script.txt достаём:
  * теги в квадратных скобках, их аргументы и длительности;
  * «адрес» каждого тега — сколько слов речи стоит перед ним
    (по этому адресу выравнивание найдёт секунду в транскрипте);
  * чистый текст речи без тегов — его сопоставляем с транскриптом.

Имена тегов берутся из config.tags.names — их можно переименовать
и добавлять синонимы, не трогая код.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .config import Config
from .models import Tag

log = logging.getLogger(__name__)

STAGE = 3
STAGE_TITLE = "Парсер + выравнивание"

TAG_RE = re.compile(r"\[([^\]\n]{1,200})\]")
PARAGRAPH_RE = re.compile(r"\n\s*\n")

# «3с», «3.5s», «2 сек», «4 секунды»
DURATION_RE = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(с|c|сек|секунд[аыу]?|s|sec|secs?|seconds?)?\.?$",
    re.IGNORECASE,
)


@dataclass
class ScriptDoc:
    """Разобранный сценарий."""

    tags: list[Tag] = field(default_factory=list)
    # Слова речи без тегов — то, что реально будет произнесено.
    speech_words: list[str] = field(default_factory=list)
    # Границы абзацев в словах: [(первое слово, следующее за последним), ...].
    # [ЭКРАН] без стоп-тега действует до конца своего абзаца.
    paragraphs: list[tuple[int, int]] = field(default_factory=list)
    # Секунды конца абзацев на исходном таймлайне (заполняет aligner).
    paragraph_end_times: list[float | None] = field(default_factory=list)

    @property
    def speech_text(self) -> str:
        return " ".join(self.speech_words)


def parse_script(text: str, cfg: Config) -> ScriptDoc:
    """Разбирает размеченный сценарий."""
    aliases = cfg.tags.alias_map()
    anchor_size = cfg.tags.anchor_words

    doc = ScriptDoc()
    words: list[str] = []
    unknown: list[str] = []

    for paragraph_index, paragraph in enumerate(PARAGRAPH_RE.split(text.strip())):
        first_word = len(words)
        cursor = 0
        for match in TAG_RE.finditer(paragraph):
            words.extend(paragraph[cursor : match.start()].split())
            tag = _build_tag(match, aliases, paragraph_index, len(words))
            if tag is None:
                unknown.append(match.group(0))
            else:
                doc.tags.append(tag)
            cursor = match.end()
        words.extend(paragraph[cursor:].split())
        doc.paragraphs.append((first_word, len(words)))

    doc.speech_words = words
    doc.paragraph_end_times = [None] * len(doc.paragraphs)

    # Якоря нужны только для лога и отчёта — сама привязка идёт по индексу слова.
    for tag in doc.tags:
        start = max(0, tag.word_index - anchor_size)
        tag.anchor = " ".join(words[start : tag.word_index])
        tag.anchor_after = " ".join(words[tag.word_index : tag.word_index + anchor_size])

    for raw in unknown:
        log.warning("неизвестный тег %s — пропускаю (имена тегов: config.tags.names)", raw)

    counts: dict[str, int] = {}
    for tag in doc.tags:
        counts[tag.kind] = counts.get(tag.kind, 0) + 1
    log.info(
        "сценарий: %d слов, %d абзацев, тегов %d (%s)",
        len(words),
        len(doc.paragraphs),
        len(doc.tags),
        ", ".join(f"{kind}: {count}" for kind, count in sorted(counts.items())) or "нет",
    )
    return doc


def _build_tag(
    match: re.Match, aliases: dict[str, str], paragraph_index: int, word_index: int
) -> Tag | None:
    body = " ".join(match.group(1).split())
    upper = body.upper()

    # alias_map отсортирован от длинных к коротким: «МУЗЫКА СТОП» проверяется
    # раньше, чем «МУЗЫКА», иначе стоп-тег распознался бы как включение музыки.
    for alias, kind in aliases.items():
        if upper == alias:
            rest = ""
        elif upper.startswith(alias + ":") or upper.startswith(alias + " "):
            rest = body[len(alias) :].lstrip(" :").strip()
        else:
            continue

        argument, duration = _split_argument(rest)
        return Tag(
            kind=kind,
            raw=match.group(0),
            argument=argument,
            duration=duration,
            word_index=word_index,
            paragraph=paragraph_index,
        )
    return None


def _split_argument(rest: str) -> tuple[str, float | None]:
    """Отделяет длительность от имени файла: «chart.png 3с» -> («chart.png», 3.0).

    Длительность может быть написана и в два слова («4 сек»), поэтому сначала
    пробуем два последних токена, потом один.
    """
    if not rest:
        return "", None
    tokens = rest.split()
    for tail in (2, 1):
        if len(tokens) >= tail:
            duration = parse_duration(" ".join(tokens[-tail:]))
            if duration is not None:
                return " ".join(tokens[:-tail]), duration
    return rest, None


def parse_duration(token: str) -> float | None:
    """«3с», «3.5s», «2 сек» -> секунды. Не длительность -> None."""
    match = DURATION_RE.match(token.strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None
