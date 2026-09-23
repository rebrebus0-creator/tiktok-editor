"""Планировщик: текст сценария -> список поисковых запросов."""

from __future__ import annotations

import abc

from ..models import MediaKind, Orientation, SearchQuery


class Planner(abc.ABC):
    @abc.abstractmethod
    def plan(
        self,
        brief: str,
        *,
        kind: MediaKind = MediaKind.VIDEO,
        orientation: Orientation = Orientation.PORTRAIT,
        max_queries: int = 6,
    ) -> list[SearchQuery]:
        """Разобрать бриф/сценарий на конкретные поисковые запросы."""
