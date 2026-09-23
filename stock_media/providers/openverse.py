"""Openverse: агрегатор CC-контента (Flickr, Wikimedia и др.). Только фото.

Ключ не нужен — публичный анонимный доступ с лимитом по частоте запросов.
"""

from __future__ import annotations

from ..models import MediaAsset, MediaKind, Orientation, SearchQuery
from .base import Provider

SEARCH_URL = "https://api.openverse.org/v1/images/"

_ASPECT = {
    Orientation.PORTRAIT: "tall",
    Orientation.LANDSCAPE: "wide",
    Orientation.SQUARE: "square",
}


class OpenverseProvider(Provider):
    name = "openverse"
    supports = frozenset({"photo"})

    def search(self, query: SearchQuery) -> list[MediaAsset]:
        if query.kind is not MediaKind.PHOTO:
            return []

        params: dict = {
            "q": query.text,
            "page_size": min(query.limit, 20),
            "mature": "false",
        }
        aspect = _ASPECT.get(query.orientation)
        if aspect:
            params["aspect_ratio"] = aspect

        data = self._get_json(SEARCH_URL, params=params)
        return [a for a in map(self._parse, data.get("results", [])) if a]

    def _parse(self, item: dict) -> MediaAsset | None:
        url = item.get("url")
        # Без размеров нечем ранжировать — такие результаты пропускаем.
        if not url or not item.get("width") or not item.get("height"):
            return None
        return MediaAsset(
            provider=self.name,
            provider_id=str(item["id"]),
            kind=MediaKind.PHOTO,
            url=url,
            preview_url=item.get("thumbnail"),
            width=item["width"],
            height=item["height"],
            author=item.get("creator"),
            source_page=item.get("foreign_landing_url"),
            license=item.get("license"),
            tags=[t["name"] for t in item.get("tags", []) if t.get("name")],
        )
