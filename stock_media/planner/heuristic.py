"""Планировщик без нейронки: запасной вариант, когда нет ключа Anthropic.

Работает тупо, но предсказуемо: режет текст на предложения и чистит
стоп-слова. Годится для тестов и как fallback, чтобы модуль не падал.
"""

from __future__ import annotations

import re

from ..models import MediaKind, Orientation, SearchQuery
from .base import Planner

_SENTENCE_SPLIT = re.compile(r"[.!?\n;]+")
_WORD = re.compile(r"[\w\-']+", re.UNICODE)

# Служебные слова, которые только мешают поиску по стокам.
_STOPWORDS = {
    "и", "в", "на", "с", "что", "это", "как", "для", "не", "но", "а", "по",
    "the", "a", "an", "of", "and", "to", "in", "on", "for", "with", "is", "it",
}


class HeuristicPlanner(Planner):
    def plan(
        self,
        brief: str,
        *,
        kind: MediaKind = MediaKind.VIDEO,
        orientation: Orientation = Orientation.PORTRAIT,
        max_queries: int = 6,
    ) -> list[SearchQuery]:
        queries: list[SearchQuery] = []
        for sentence in _SENTENCE_SPLIT.split(brief):
            sentence = sentence.strip()
            if not sentence:
                continue
            words = [w for w in _WORD.findall(sentence.lower()) if w not in _STOPWORDS]
            if not words:
                continue
            queries.append(
                SearchQuery(
                    text=" ".join(words[:5]),
                    kind=kind,
                    orientation=orientation,
                    scene_hint=sentence,
                )
            )
            if len(queries) >= max_queries:
                break
        return queries
