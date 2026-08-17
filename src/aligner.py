"""Выравнивание сценарий ↔ транскрипт — ЭТАП 3. Ключевой узел проекта.

Пользователь не проставляет таймкоды: он ставит тег рядом с фразой, а мы сами
находим, на какой секунде эта фраза произнесена.

Речь ≠ сценарию дословно (импровизация, оговорки, «эээ»), поэтому сопоставляем
последовательности нормализованных слов через `difflib.SequenceMatcher`:
нижний регистр, без пунктуации, ё → е. Совпавшие участки дают точную привязку
«слово сценария -> слово транскрипта»; теги внутри расхождений получают время
по ближайшему совпавшему слову.

Если якорь не нашёлся — тег ставится по ближайшему совпадению и пишется
предупреждение. Падать нельзя: один непонятый тег не должен ронять сборку.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from .config import Config
from .models import Tag, Transcript
from .parser import ScriptDoc

log = logging.getLogger(__name__)

STAGE = 3
STAGE_TITLE = "Парсер + выравнивание"

_PUNCT_RE = re.compile(r"[^\w\s-]+", re.UNICODE)

# На сколько слов в стороны ищем ближайшее совпадение, если тег попал
# в участок расхождения сценария и речи.
MAX_SEARCH_DISTANCE = 25


def normalize(text: str) -> str:
    """Приводит текст к виду для сравнения: нижний регистр, без пунктуации, ё→е."""
    cleaned = _PUNCT_RE.sub(" ", text.lower().replace("ё", "е"))
    return " ".join(cleaned.split())


def align(doc: ScriptDoc, transcript: Transcript, cfg: Config) -> list[Tag]:
    """Проставляет каждому тегу `src_time` — секунду на исходном таймлайне."""
    script_words = [normalize(word) for word in doc.speech_words]
    speech_words = [normalize(word.text) for word in transcript.words]

    if not transcript.words:
        log.warning("транскрипт пуст — теги привязать не к чему, все будут пропущены")
        return doc.tags
    if not script_words:
        log.warning("в сценарии нет слов речи — теги привязать не к чему")
        return doc.tags

    matcher = SequenceMatcher(None, script_words, speech_words, autojunk=False)
    ratio = matcher.ratio()
    mapping = _index_map(matcher, len(script_words))
    matched = sum(1 for item in mapping if item is not None)

    log.info(
        "выравнивание: сценарий %d слов, речь %d слов, совпало %d (%.0f%% похожести)",
        len(script_words),
        len(speech_words),
        matched,
        100 * ratio,
    )
    if ratio < 0.5:
        log.warning(
            "сценарий и речь совпадают лишь на %.0f%% — теги встанут приблизительно. "
            "Проверь, тот ли это сценарий, и посмотри timeline.json",
            100 * ratio,
        )

    for tag in doc.tags:
        time, similarity, distance = _resolve(tag.word_index, mapping, transcript, cfg)
        tag.src_time = time
        tag.similarity = similarity
        if time is None:
            log.warning(
                "%s: не нашёл момент в речи (якорь «%s») — тег пропущен",
                tag.raw,
                tag.anchor or tag.anchor_after,
            )
        elif similarity < cfg.tags.min_similarity:
            log.warning(
                "%s: точного совпадения нет, ставлю по ближайшему слову "
                "(%.2f с, промах %d слов, якорь «%s»)",
                tag.raw,
                time,
                distance,
                tag.anchor or tag.anchor_after,
            )
        else:
            log.info("%s -> %.2f с (якорь «%s»)", tag.raw, time, tag.anchor)

    doc.paragraph_end_times = [
        _paragraph_end(bounds, mapping, transcript) for bounds in doc.paragraphs
    ]
    return doc.tags


def _index_map(matcher: SequenceMatcher, script_length: int) -> list[int | None]:
    """Соответствие «индекс слова сценария -> индекс слова транскрипта».

    Заполняются только совпавшие участки; расхождения остаются None и
    разрешаются потом поиском ближайшего соседа.
    """
    mapping: list[int | None] = [None] * script_length
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode != "equal":
            continue
        for offset in range(i2 - i1):
            mapping[i1 + offset] = j1 + offset
    return mapping


def _resolve(
    word_index: int,
    mapping: list[int | None],
    transcript: Transcript,
    cfg: Config,
) -> tuple[float | None, float, int]:
    """Секунда для тега, стоящего перед словом сценария №word_index.

    Тег привязан к фразе ПЕРЕД ним, поэтому сначала ищем ближайшее совпавшее
    слово слева и берём его конец; если слева ничего нет — берём начало
    ближайшего слова справа.
    """
    words = transcript.words

    back_index, back_distance = _nearest(mapping, word_index - 1, step=-1)
    forward_index, forward_distance = _nearest(mapping, word_index, step=1)

    if back_index is None and forward_index is None:
        return None, 0.0, 0

    use_back = back_index is not None and (
        forward_index is None or back_distance <= forward_distance
    )
    if use_back:
        time = words[back_index].end
        distance = back_distance
    else:
        time = words[forward_index].start
        distance = forward_distance

    if distance == 0:
        similarity = 1.0
    elif distance > MAX_SEARCH_DISTANCE:
        # Ближайшее совпадение так далеко, что привязка почти наугад.
        similarity = 0.05
    else:
        similarity = max(0.1, 1.0 - 0.12 * distance)
    return time, similarity, distance


def _nearest(mapping: list[int | None], start: int, step: int) -> tuple[int | None, int]:
    """Ближайший сопоставленный индекс от start в направлении step.

    Расстояние не ограничиваем: даже далёкая привязка полезнее пропущенного
    тега. На дистанцию смотрит оценка уверенности, а не сам поиск.
    """
    index = start
    distance = 0
    while 0 <= index < len(mapping):
        if mapping[index] is not None:
            return mapping[index], distance
        index += step
        distance += 1
    return None, distance


def _paragraph_end(
    bounds: tuple[int, int], mapping: list[int | None], transcript: Transcript
) -> float | None:
    """Секунда, на которой заканчивается абзац сценария."""
    _, end_word = bounds
    index, _ = _nearest(mapping, end_word - 1, step=-1)
    if index is None:
        return None
    return transcript.words[index].end
