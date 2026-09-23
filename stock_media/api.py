"""Публичный интерфейс модуля.

Всё, что нужно знать основному софту:

    from stock_media import StockMediaClient

    client = StockMediaClient()
    assets = client.collect("Сценарий про утреннюю пробежку в городе", per_query=2)
    for a in assets:
        print(a.local_path, a.score)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .cache import MediaCache
from .config import Settings
from .errors import DownloadError, MissingCredentials, ProviderError
from .models import MediaAsset, MediaKind, Orientation, SearchQuery
from .planner import Planner, build_planner
from .providers import Provider, build_providers
from .ranking import rank

log = logging.getLogger(__name__)


class StockMediaClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        providers: list[Provider] | None = None,
        planner: Planner | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.providers = providers if providers is not None else build_providers(self.settings)
        self.planner = planner or build_planner(self.settings)
        self.cache = MediaCache(self.settings)

    # --- шаг 1: сценарий -> запросы -------------------------------------

    def plan(
        self,
        brief: str,
        *,
        kind: MediaKind = MediaKind.VIDEO,
        orientation: Orientation = Orientation.PORTRAIT,
        max_queries: int = 6,
    ) -> list[SearchQuery]:
        return self.planner.plan(
            brief, kind=kind, orientation=orientation, max_queries=max_queries
        )

    # --- шаг 2: запросы -> ассеты ----------------------------------------

    def search(self, query: SearchQuery, *, top: int | None = None) -> list[MediaAsset]:
        """Опросить всех подходящих провайдеров и отранжировать результат."""
        usable = [p for p in self.providers if query.kind.value in p.supports]
        results: list[MediaAsset] = []

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as pool:
            for provider, found in zip(usable, pool.map(_safe_search(query), usable)):
                log.debug("%s вернул %d результатов", provider.name, len(found))
                results.extend(found)

        for asset in results:
            asset.query = query

        ranked = rank(_dedupe(results), query)
        return ranked[:top] if top else ranked

    # --- шаг 3: ассеты -> файлы на диске ---------------------------------

    def download(self, assets: list[MediaAsset]) -> list[MediaAsset]:
        """Скачать всё, что смогли. Упавшие ассеты просто не попадут в ответ."""
        by_name = {p.name: p for p in self.providers}
        downloaded: list[MediaAsset] = []
        for asset in assets:
            try:
                downloaded.append(self.cache.fetch(asset, by_name.get(asset.provider)))
            except (DownloadError, ProviderError) as exc:
                log.warning("не скачали %s: %s", asset.uid, exc)
        return downloaded

    # --- всё вместе -------------------------------------------------------

    def collect(
        self,
        brief: str,
        *,
        kind: MediaKind = MediaKind.VIDEO,
        orientation: Orientation = Orientation.PORTRAIT,
        max_queries: int = 6,
        per_query: int = 2,
    ) -> list[MediaAsset]:
        """Полный проход: бриф -> запросы -> поиск -> отбор -> скачивание."""
        assets: list[MediaAsset] = []
        for query in self.plan(
            brief, kind=kind, orientation=orientation, max_queries=max_queries
        ):
            query.limit = max(query.limit, per_query * 3)
            assets.extend(self.search(query, top=per_query))
        return self.download(_dedupe(assets))


def _safe_search(query: SearchQuery):
    """Один упавший провайдер не должен ронять весь поиск."""

    def run(provider: Provider) -> list[MediaAsset]:
        try:
            return provider.search(query)
        except (ProviderError, MissingCredentials) as exc:
            log.warning("провайдер %s недоступен: %s", provider.name, exc)
            return []

    return run


def _dedupe(assets: list[MediaAsset]) -> list[MediaAsset]:
    seen: set[str] = set()
    unique: list[MediaAsset] = []
    for asset in assets:
        if asset.uid in seen:
            continue
        seen.add(asset.uid)
        unique.append(asset)
    return unique
